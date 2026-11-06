#!/usr/bin/env python3
"""Exercise the boot ordering graph, including the path/basic target boundary."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/custom/uci-history/files'


@unittest.skipUnless(shutil.which('systemd-analyze'), 'systemd-analyze is required')
class UnitGraphTest(unittest.TestCase):
    def verify(self, legacy=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            units = root / 'usr/lib/systemd/system'
            units.mkdir(parents=True)
            for name in ('uci-history.path', 'uci-history-boot.service', 'uci-history-snapshot.service'):
                text = (FILES / name).read_text()
                if legacy and name.endswith('.path'):
                    text = text.replace('DefaultDependencies=no\n', '')
                (units / name).write_text(text)
            (units / 'multi-user.target').write_text(
                '[Unit]\nRequires=basic.target\nAfter=basic.target\n'
                'Wants=uci-history.path uci-history-boot.service openwrt-services.service\n')
            (units / 'basic.target').write_text(
                '[Unit]\nRequires=sysinit.target\nWants=paths.target\nAfter=sysinit.target paths.target\n')
            for name in ('paths.target', 'sysinit.target', 'local-fs.target', 'shutdown.target'):
                (units / name).write_text('[Unit]\nDescription=Fixture target\n')
            (units / 'openwrt-services.service').write_text(
                '[Unit]\nRequires=basic.target\nAfter=basic.target\nBefore=multi-user.target\n[Service]\nType=oneshot\nExecStart=/bin/true\n')
            for name in ('bin/true', 'usr/sbin/uci-history'):
                dest = root / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile('/bin/true', dest)
                dest.chmod(0o755)
            return subprocess.run(['systemd-analyze', '--root=' + tmp, 'verify', 'multi-user.target', 'uci-history.path', 'uci-history-boot.service', 'openwrt-services.service'],
                                  capture_output=True, text=True)

    def test_full_boot_graph(self):
        result = self.verify()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertNotIn('ordering cycle', result.stderr)

    def test_fixture_detects_the_original_cycle(self):
        result = self.verify(legacy=True)
        # systemd may repair the transaction by dropping a job and still exit 0.
        self.assertIn('ordering cycle', result.stderr)


if __name__ == '__main__':
    unittest.main()
