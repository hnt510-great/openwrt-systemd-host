#!/usr/bin/env python3
"""Exercise config migration without touching the host's Podman storage."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'package/custom/openwrt-podman-rootless/files/podman-native-storage'


class NativeStorageTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.base = self.root / 'overlay'
        self.base.mkdir()
        self.home = self.root / 'home'
        self.conf = self.home / '.config/containers/storage.conf'
        self.conf.parent.mkdir(parents=True)
        self.script = self.root / 'helper'
        source = HELPER.read_text()
        self.assertIn('base=/overlay/containers/$uid\n', source)
        source = source.replace('base=/overlay/containers/$uid', f'base={self.base}')
        # The helper refuses system accounts; use the actual owner's ID in CI.
        source = source.replace('[ "$uid" -ge 1000 ] || exit 1', ':')
        self.script.write_text(source)
        self.env = dict(os.environ, HOME=str(self.home))
        for key in ('XDG_CONFIG_HOME', 'XDG_DATA_HOME'):
            self.env.pop(key, None)

    def config(self, options='nodev'):
        return ('[storage]\ndriver = "overlay"\n'
                f'graphroot = "{self.base}/storage"\n\n'
                f'[storage.options.overlay]\nmountopt = "{options}"\n')

    def run_helper(self, success=True):
        result = subprocess.run(['sh', str(self.script)], env=self.env,
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stderr)

    def test_new_store(self):
        self.run_helper()
        self.assertEqual(self.conf.read_text(), self.config('nodev,xino=off'))
        self.assertEqual(self.conf.stat().st_mode & 0o777, 0o600)

    def test_upgrade_preserves_data_and_is_idempotent(self):
        self.conf.write_text(self.config())
        data = self.base / 'storage/layer'
        data.parent.mkdir()
        data.write_text('existing layer')
        self.run_helper()
        self.assertEqual(self.conf.read_text(), self.config('nodev,xino=off'))
        backup = self.conf.with_suffix('.conf.pre-xino')
        self.assertEqual(backup.read_text(), self.config())
        self.run_helper()
        self.assertEqual(data.read_text(), 'existing layer')
        self.assertEqual(backup.read_text(), self.config())

    def test_custom_config_retained(self):
        custom = self.config('nodev,noatime') + '# custom\n'
        self.conf.write_text(custom)
        self.run_helper()
        self.assertEqual(self.conf.read_text(), custom)

    def test_config_symlink_retained(self):
        target = self.root / 'target'
        target.write_text(self.config())
        self.conf.symlink_to(target)
        self.run_helper()
        self.assertTrue(self.conf.is_symlink())
        self.assertEqual(target.read_text(), self.config())

    def test_dangling_symlink_retained(self):
        self.conf.symlink_to(self.root / 'absent')
        self.run_helper()
        self.assertTrue(self.conf.is_symlink())
        self.assertFalse(self.conf.exists())

    def test_populated_old_store_retained(self):
        old = self.home / '.local/share/containers/storage/layer'
        old.parent.mkdir(parents=True)
        old.write_text('old layer')
        self.run_helper()
        self.assertFalse(self.conf.exists())
        self.assertEqual(old.read_text(), 'old layer')

    def test_backup_collision_aborts_without_changes(self):
        self.conf.write_text(self.config())
        backup = self.conf.with_suffix('.conf.pre-xino')
        backup.write_text('previous backup')
        self.run_helper(success=False)
        self.assertEqual(self.conf.read_text(), self.config())
        self.assertEqual(backup.read_text(), 'previous backup')
        self.assertEqual(list(self.conf.parent.glob('.storage.conf.*')), [])


if __name__ == '__main__':
    unittest.main()
