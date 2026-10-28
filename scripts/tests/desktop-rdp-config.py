#!/usr/bin/env python3
"""Exercise listener validation and the GNOME session environment without a VM."""
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
        script = '. "$1"; logger() { :; }; desktop_validate_rdp "$2"'
        for port, valid in [('3389', True), ('1024', True), ('65535', True),
                            ('1023', False), ('65536', False), ('', False),
                            ('3389;touch bad', False), ('-1', False)]:
            with self.subTest(port=port):
                result = subprocess.run(['sh', '-c', script, 'test',
                                         str(FILES / 'desktop-common.sh'), port],
                                        capture_output=True)
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

    def test_gnome_session_sanitizes_inherited_environment(self):
        import socket
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            binary = tmp / 'bin'
            binary.mkdir()
            launch = binary / 'gnome-session'
            launch.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                              'print(json.dumps([sys.argv[1:],dict(os.environ)]))\n')
            launch.chmod(0o755)
            for name in ['systemctl', 'keyring']:
                path = binary / name
                path.write_text('#!/bin/sh\nexit 0\n')
                path.chmod(0o755)
            # A real Unix socket satisfies the launcher readiness condition,
            # while all service operations are isolated by the PATH stubs.
            bus = socket.socket(socket.AF_UNIX)
            self.addCleanup(bus.close)
            bus.bind(str(tmp / 'bus'))
            script = (FILES / 'desktop-session').read_text()
            script = script.replace('/usr/bin/gnome-session', str(launch))
            script = script.replace('/usr/libexec/desktop-keyring-unlock', str(binary / 'keyring'))
            path = tmp / 'session'
            path.write_text(script)
            env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                       HOME=str(tmp), USER='alice', XDG_RUNTIME_DIR=str(tmp),
                       WAYLAND_SOCKET='9999', GTK_IM_MODULE='legacy',
                       GTK_IM_MODULE_FILE='/obsolete/cache', LIBSEAT_BACKEND='seatd')
            result = subprocess.run(['sh', str(path)], env=env, capture_output=True,
                                    text=True, check=True)
            args, actual = json.loads(result.stdout)
            self.assertEqual(args, ['--session=gnome'])
            self.assertEqual(actual['XDG_CURRENT_DESKTOP'], 'GNOME')
            self.assertEqual(actual['XDG_SESSION_TYPE'], 'wayland')
            for name in ['WAYLAND_SOCKET', 'GTK_IM_MODULE', 'GTK_IM_MODULE_FILE', 'LIBSEAT_BACKEND']:
                self.assertNotIn(name, actual)

    def test_credential_password_stays_on_stdin(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            binary = tmp / 'bin'
            binary.mkdir()
            tool = binary / 'grdctl'
            tool.write_text('#!/usr/bin/env python3\nimport json,os,sys\n'
                            'if sys.argv[1:3]==["rdp","set-credentials"]:\n'
                            ' open(os.environ["CREDENTIAL_CAPTURE"],"w").write('
                            'json.dumps([sys.argv[1:],sys.stdin.read()]))\n')
            tool.chmod(0o755)
            for name, body in [('id', 'case "$1" in -u) echo 1000;; -un) echo alice;; esac'),
                               ('uci', 'echo 3389'), ('gsettings', 'exit 0')]:
                tool = binary / name
                tool.write_text('#!/bin/sh\n' + body + '\n')
                tool.chmod(0o755)
            capture = tmp / 'capture.json'
            env = dict(os.environ, PATH=str(binary) + ':' + os.environ['PATH'],
                       USER='alice', CREDENTIAL_CAPTURE=str(capture))
            fixture = 'fixture-only-password'
            script = tmp / 'configure'
            script.write_text((FILES / 'desktop-rdp-configure').read_text().replace(
                '/sbin/uci', str(binary / 'uci')))
            subprocess.run(['sh', str(script)],
                           input=fixture + '\n', text=True, env=env,
                           capture_output=True, check=True)
            args, data = json.loads(capture.read_text())
            self.assertEqual(args, ['rdp', 'set-credentials', 'alice'])
            self.assertEqual(data, fixture + '\n')
            self.assertNotIn(fixture, args)


if __name__ == '__main__':
    unittest.main()
