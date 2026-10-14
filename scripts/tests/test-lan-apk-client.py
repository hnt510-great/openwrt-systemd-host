#!/usr/bin/env python3
"""Exercise ABI selection and restored router configuration without a live router."""
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
FILES = TREE / 'package/custom/lan-apk-feeds/files'
BASE = 'http://192.0.2.164:8088'
OLD = '6.18.55~old-r1'
NEW = '6.18.55~new-r1'


class ClientTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='lan-feed-client-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repos = self.root / 'etc/apk/repositories.d'
        self.repos.mkdir(parents=True)
        self.config = self.root / 'etc/lan-apk-feeds.conf'
        self.config.write_bytes((FILES / 'lan-apk-feeds.conf').read_bytes())
        self.db = self.root / 'lib/apk/db/installed'
        self.db.parent.mkdir(parents=True)
        self.install_kernel(OLD)
        self.list = self.repos / 'lan-local.list'
        self.custom = self.repos / 'customfeeds.list'
        self.command = ['sh', str(FILES / 'lan-apk-feeds-sync'), '--root', str(self.root)]

    def install_kernel(self, version):
        self.db.write_text(f'P:libc\nV:2.42-r1\n\nP:kernel-dev-headers\nV:1\n\nP:kernel\nV:{version}\n\n')

    def sync(self):
        result = subprocess.run(self.command, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        return self.list.read_text()

    def test_old_router_stays_old_until_installed_kernel_changes(self):
        self.assertIn('/abi/' + OLD + '/', self.sync())
        self.install_kernel(NEW)
        current = self.sync()
        self.assertIn('/abi/' + NEW + '/', current)
        self.assertNotIn(OLD, current)
        self.assertEqual(len([x for x in current.splitlines() if x.startswith('http')]), 9)

    def test_migrate_manual_lists_preserves_unrelated_custom_feeds(self):
        self.list.write_text('# Local feeds\n' + BASE + '/abi/' + OLD + '/target/packages.adb\n')
        external = 'https://example.org/other/packages.adb\n'
        self.custom.write_text('# Custom\n' + BASE + '/abi/' + OLD + '/custom/packages.adb\n' + external)
        self.sync()
        self.assertEqual(self.custom.read_text(), '# Custom\n' + external)

    def test_restored_old_list_is_regenerated_after_upgrade(self):
        self.list.write_text('# Local feeds\n' + BASE + '/abi/' + OLD + '/target/packages.adb\n')
        self.install_kernel(NEW)
        self.assertNotIn(OLD, self.sync())

    def test_noop_preserves_inode_and_db(self):
        self.sync()
        inode = self.list.stat().st_ino
        db = self.db.read_bytes()
        self.sync()
        self.assertEqual(self.list.stat().st_ino, inode)
        self.assertEqual(self.db.read_bytes(), db)

    def test_unmanaged_list_is_not_overwritten(self):
        self.list.write_text('https://example.org/other/packages.adb\n')
        before = self.list.read_bytes()
        result = subprocess.run(self.command, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.list.read_bytes(), before)

    def test_missing_or_ambiguous_kernel_rejected(self):
        for data in ('P:kernel-dev-headers\nV:1\n', 'P:kernel\nV:1\n\nP:kernel\nV:2\n'):
            self.db.write_text(data)
            result = subprocess.run(self.command, capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(self.list.exists())

    def test_shell_content_is_never_executed(self):
        self.config.write_text('base_url=$(touch /tmp/lan-feeds-invalid)\nrepositories=target\n')
        result = subprocess.run(self.command, capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(self.list.exists())

    def test_mirror_change_retains_installed_abi(self):
        self.sync()
        self.config.write_text('base_url=http://192.0.2.20:8088\nrepositories=target custom\n')
        self.assertIn('http://192.0.2.20:8088/abi/' + OLD, self.sync())


if __name__ == '__main__':
    unittest.main(verbosity=2)
