#!/usr/bin/env python3
"""Optical source safety and execution of the frozen target bootstrap tools."""
import gzip
import importlib.machinery
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'package/custom/openwrt-installer/files'))
import apply
builder = importlib.machinery.SourceFileLoader('installer_bootstrap', str(ROOT / 'scripts/build-installer-initramfs.py')).load_module()


class Optical(unittest.TestCase):
    def test_media_identity(self):
        with tempfile.TemporaryDirectory() as tmp:
            sysfs = Path(tmp)
            root = sysfs / 'devices/virtual/block/loop0'
            (root / 'loop').mkdir(parents=True)
            (root / 'loop/backing_file').write_text('/dev/sr0\n')
            (root / 'ro').write_text('1\n')
            cd = sysfs / 'class/block/sr0'
            (cd / 'device').mkdir(parents=True)
            (cd / 'device/type').write_text('5\n')
            (cd / 'ro').write_text('1\n')
            (sysfs / 'dev/block').mkdir(parents=True)
            (sysfs / 'dev/block/7:0').symlink_to(root)
            with patch.object(apply, 'run', return_value='7:0'):
                self.assertEqual(apply.live_media(sysfs), ('/dev/loop0', '/dev/sr0'))
                for backing in ('/tmp/payload.iso', '/dev/vda'):
                    (root / 'loop/backing_file').write_text(backing)
                    with self.assertRaises(ValueError): apply.live_media(sysfs)
                (root / 'loop/backing_file').write_text('/dev/sr0')
                (root / 'ro').write_text('0')
                with self.assertRaises(ValueError): apply.live_media(sysfs)
                (root / 'ro').write_text('1')
                (cd / 'ro').write_text('0')
                with self.assertRaises(ValueError): apply.live_media(sysfs)
            disk = sysfs / 'devices/pci/block/sda'
            (disk / 'sda3').mkdir(parents=True)
            (disk / 'sda3/partition').write_text('3')
            (sysfs / 'dev/block/8:3').symlink_to(disk / 'sda3')
            with patch.object(apply, 'run', return_value='8:3'):
                self.assertEqual(apply.live_media(sysfs), ('/dev/sda3', '/dev/sda'))

    @unittest.skipUnless(os.environ.get('INSTALLER_TEST_ROOT'), 'set INSTALLER_TEST_ROOT to prepared target root')
    def test_frozen_tools(self):
        source = Path(os.environ['INSTALLER_TEST_ROOT'])
        config = Path(os.environ['INSTALLER_TEST_KERNEL_CONFIG'])
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            archive = work / 'bootstrap.gz'
            builder.build(source, ROOT / 'package/custom/openwrt-installer/files/live-init', config, archive)
            # Extract and actually execute using the target loader and libraries.
            unpack = work / 'root'; unpack.mkdir()
            subprocess.run(['cpio', '-id', '--quiet', '--no-absolute-filenames'], input=gzip.decompress(archive.read_bytes()), cwd=unpack, check=True, capture_output=True)
            command = ['sudo', '-n', 'chroot', str(unpack)]
            subprocess.run(command + ['/bin/sh', '-c', 'test "$(printf 1234 | hexdump -n 4 -e \'1/4 "%08x"\')" = 34333231; mkdir /probe; ln -s /probe /probe-link; test -d /probe-link; cat /init | head -n 1'], check=True, capture_output=True)
            for tool in ('mount', 'umount', 'losetup', 'blkid', 'switch_root'):
                result = subprocess.run(command + ['/bin/' + tool, '--help'], capture_output=True)
                self.assertIn(result.returncode, (0, 1), (tool, result.stderr))
                self.assertNotIn(b'error while loading shared libraries', result.stderr)
            again = work / 'again.gz'
            builder.build(source, ROOT / 'package/custom/openwrt-installer/files/live-init', config, again)
            self.assertEqual(archive.read_bytes(), again.read_bytes())
            config_bad = work / 'config'
            config_bad.write_text(config.read_text().replace('CONFIG_BLK_DEV_SR=y', '# CONFIG_BLK_DEV_SR is not set'))
            with self.assertRaisesRegex(ValueError, 'BLK_DEV_SR'):
                builder.build(source, ROOT / 'package/custom/openwrt-installer/files/live-init', config_bad, again)


if __name__ == '__main__':
    unittest.main()
