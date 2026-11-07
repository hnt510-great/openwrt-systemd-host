#!/usr/bin/env python3
"""Exercise coldplug with bound, unbound and unsupported PCI display devices."""
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'package/custom/openwrt-desktop/files/desktop-gpu-coldplug'


class Coldplug(unittest.TestCase):
    def probe(self, bound=False, display=True, status=0):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); pci = root / 'pci'; device = pci / '0000:00:01.0'
            device.mkdir(parents=True)
            (device / 'class').write_text('0x030000' if display else '0x020000')
            (device / 'modalias').write_text('pci:probe-alias')
            if bound:
                (root / 'driver').mkdir(); (device / 'driver').symlink_to(root / 'driver')
            record = root / 'calls'
            modprobe = root / 'modprobe'
            modprobe.write_text('#!/bin/sh\nprintf "%s\\n" "$*" >> ' + str(record) + '\nexit ' + str(status) + '\n')
            modprobe.chmod(0o755)
            script = root / 'coldplug'
            script.write_text(SOURCE.read_text().replace('/sys/bus/pci/devices', str(pci)).replace('/usr/sbin/modprobe', str(modprobe)))
            result = subprocess.run(['/bin/sh', str(script)], capture_output=True)
            return result.returncode, record.read_text() if record.exists() else ''

    def test_bound_builtin_needs_no_modprobe(self):
        self.assertEqual(self.probe(bound=True, status=1), (0, ''))

    def test_unbound_gpu_is_probed(self):
        self.assertEqual(self.probe(), (0, '--use-blacklist pci:probe-alias\n'))

    def test_unsupported_gpu_still_fails(self):
        self.assertEqual(self.probe(status=1)[0], 1)

    def test_other_pci_devices_are_ignored(self):
        self.assertEqual(self.probe(display=False, status=1), (0, ''))


if __name__ == '__main__':
    unittest.main()
