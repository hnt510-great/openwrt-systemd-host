#!/usr/bin/env python3
"""Guard the device-manager ownership boundary and validate rule syntax."""
from pathlib import Path
import re
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
RULE = ROOT / 'package/system/systemd/files/99-systemd.rules'


class Boundary(unittest.TestCase):
    def test_no_policy_writers(self):
        rules = '\n'.join(x for x in RULE.read_text().splitlines() if not x.startswith('#'))
        self.assertNotRegex(rules, r'RUN|NAME=|SYSTEMD_RFKILL|systemd-(sysctl|rfkill|backlight|loop|machine-tag)')
        self.assertNotRegex(rules, r'DM_NAME|DM_UUID|ID_FS_USAGE|IMPORT\{db\}')
        self.assertIn('SUBSYSTEM=="block", KERNEL!="dm-*", TAG+="systemd"', rules)
        wants = set(re.findall(r'ENV\{SYSTEMD_(?:USER_)?WANTS\}\+="([^"]+)"', rules))
        self.assertEqual(wants, {'bluetooth.target', 'smartcard.target', 'sound.target',
                                'printer.target', 'usb-gadget.target', 'tpm2.target',
                                'sys-fs-fuse-connections.mount', 'sys-kernel-config.mount'})

    def test_packaged_and_required(self):
        recipe = (ROOT / 'package/system/systemd/Makefile').read_text()
        install = recipe.split('define Package/systemd-udev/install', 1)[1].split('endef', 1)[0]
        self.assertIn('$(INSTALL_DATA) ./files/99-systemd.rules', install)
        self.assertIn('KERNEL=="tpmrm[0-9]*", TAG+="systemd"', RULE.read_text())
        self.assertIn('KERNEL=="tpm[0-9]*", TAG+="systemd"', RULE.read_text())
        desktop = (ROOT / 'package/custom/openwrt-desktop/files/desktop.init').read_text()
        self.assertNotIn('dev-tpmrm0.device', desktop)

    @unittest.skipUnless(shutil.which('udevadm'), 'udevadm unavailable')
    def test_rule_syntax(self):
        result = subprocess.run(['udevadm', 'verify', '--no-style', str(RULE)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
