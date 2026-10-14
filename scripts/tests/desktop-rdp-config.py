#!/usr/bin/env python3
"""Exercise listener validation and generated Weston configuration without a VM."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/custom/openwrt-desktop/files'


class DesktopRdpConfiguration(unittest.TestCase):
    def test_listener_boundaries(self):
        script = '. "$1"; logger() { :; }; desktop_validate_rdp "$2" "$3" "$4"'
        cases = [
            ('3389', '30', '5900', True),
            ('1024', '1', '5900', True),
            ('65535', '60', '5900', True),
            ('1023', '30', '5900', False),
            ('65536', '30', '5900', False),
            ('5900', '30', '5900', False),
            ('3389', '0', '5900', False),
            ('3389', '61', '5900', False),
            ('', '30', '5900', False),
            ('3389', '', '5900', False),
            ('3389;touch bad', '30', '5900', False),
        ]
        for port, rate, vnc, valid in cases:
            with self.subTest(port=port, rate=rate):
                result = subprocess.run(
                    ['sh', '-c', script, 'test', str(FILES / 'desktop-common.sh'), port, rate, vnc],
                    capture_output=True,
                )
                self.assertEqual(result.returncode == 0, valid)

    def test_display_mode_validation(self):
        script = '. "$1"; logger() { :; }; desktop_validate_mode "$2"'
        for mode, valid in [('preferred', True), ('1280x720', True),
                            ('1920x1080@60', True), ('1280x720@0', False),
                            ('1280x720@241', False), ('0x720', False),
                            ('1280x720\n[rdp]', False), ('1280x720;bad', False)]:
            with self.subTest(mode=mode):
                result = subprocess.run(['sh', '-c', script, 'test',
                                         str(FILES / 'desktop-common.sh'), mode],
                                        capture_output=True)
                self.assertEqual(result.returncode == 0, valid)

    def test_shared_session_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            (tmp / 'alice.sam').write_text('test fixture\n')
            stub = tmp / 'launch'
            stub.write_text('#!/usr/bin/env python3\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n')
            stub.chmod(0o755)
            script = (FILES / 'desktop-session').read_text()
            script = script.replace('/usr/libexec/desktop-common.sh', str(FILES / 'desktop-common.sh'))
            script = script.replace('/usr/libexec/desktop-dbus-session', str(stub))
            script = script.replace('/etc/desktop/rdp', str(tmp))
            # Disable optional host application detection in this isolated test.
            for name in ['flatpak', 'Xwayland']:
                script = script.replace('/usr/bin/' + name, str(tmp / name))
            for name in ['desktop-no-caps', 'virt-manager-launch', 'desktop-flatpak-session']:
                script = script.replace('/usr/libexec/' + name, str(tmp / name))
            session = tmp / 'session'
            session.write_text(script)
            env = dict(os.environ, HOME=str(tmp), XDG_RUNTIME_DIR=str(tmp), USER='alice')
            for enabled, mode in [('0', 'preferred'), ('1', '1280x720')]:
                result = subprocess.run(
                    ['sh', str(session), 'HDMI-A-1', '192.0.2.1', '5901', 'key', 'cert',
                     'pixman', enabled, '3390', '30', mode], env=env, capture_output=True, text=True,
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(result.stdout)
                config = (tmp / 'weston.ini').read_text()
                self.assertIn('--address=192.0.2.1', args)
                self.assertIn('--port=5901', args)
                self.assertIn('mirror-of=HDMI-A-1', config)
                self.assertIn('name=HDMI-A-1\nmode=' + mode, config)
                if enabled == '1':
                    self.assertIn('--backends=drm,vnc,rdp', args)
                    self.assertIn('--no-resizeable', args)
                    self.assertIn('name=rdp-0', config)
                    self.assertIn('address=192.0.2.1\nport=3390', config)
                    self.assertIn('nla-ntlm-db=' + str(tmp / 'alice.sam'), config)
                else:
                    self.assertIn('--backends=drm,vnc', args)
                    self.assertNotIn('[rdp]', config)


if __name__ == '__main__':
    unittest.main()
