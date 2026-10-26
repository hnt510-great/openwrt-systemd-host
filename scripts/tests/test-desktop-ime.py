#!/usr/bin/env python3
"""Exercise first-use IME setup, user configuration preservation, and Weston wiring."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/custom/openwrt-desktop-ime/files'


class DesktopIme(unittest.TestCase):
    def test_setup_preserves_settings_and_wayland_socket(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            client = tmp / 'fcitx'
            client.write_text('#!/usr/bin/env python3\nimport os,socket,sys\n'
                              's=socket.socket(fileno=int(os.environ["WAYLAND_SOCKET"]))\n'
                              's.send(b"ready")\nassert sys.argv[1:]==["--disable=ibusfrontend"]\n')
            client.chmod(0o755)
            script = tmp / 'session'
            script.write_text((FILES / 'desktop-ime-session').read_text()
                              .replace('/usr/share/openwrt-desktop-ime', str(FILES))
                              .replace('/usr/bin/fcitx5', str(client)))
            env = dict(os.environ, HOME=str(tmp), XDG_CONFIG_HOME=str(tmp / 'custom config'))
            config = tmp / 'custom config/fcitx5'

            def launch():
                parent, child = socket.socketpair()
                try:
                    env['WAYLAND_SOCKET'] = str(child.fileno())
                    result = subprocess.run(['sh', str(script)], env=env,
                                            pass_fds=(child.fileno(),), capture_output=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    parent.settimeout(2)
                    self.assertEqual(parent.recv(5), b'ready')
                finally:
                    parent.close()
                    child.close()

            launch()
            self.assertEqual((config / 'profile').read_bytes(), (FILES / 'profile').read_bytes())
            self.assertEqual((config / 'config').stat().st_mode & 0o777, 0o600)
            (config / 'config').write_text('personal hotkeys\n')
            (config / 'profile').write_text('personal methods\n')
            (config / 'conf/classicui.conf').unlink()
            (config / 'conf/classicui.conf').symlink_to(tmp / 'missing')
            launch()
            self.assertEqual((config / 'config').read_text(), 'personal hotkeys\n')
            self.assertEqual((config / 'profile').read_text(), 'personal methods\n')
            self.assertTrue((config / 'conf/classicui.conf').is_symlink())
            self.assertFalse((tmp / 'missing').exists())

    def test_generated_weston_config_with_and_without_ime(self):
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            stub = tmp / 'launch'
            stub.write_text('#!/bin/sh\nprintf "%s\\n" "${GTK_IM_MODULE:-}" "${GTK_IM_MODULE_FILE:-}"\n')
            stub.chmod(0o755)
            script = (ROOT / 'package/custom/openwrt-desktop/files/desktop-session').read_text()
            script = script.replace('/usr/libexec/desktop-common.sh', str(ROOT / 'package/custom/openwrt-desktop/files/desktop-common.sh'))
            script = script.replace('/usr/libexec/desktop-dbus-session', str(stub))
            script = script.replace('/usr/libexec/desktop-ime-session', str(tmp / 'ime'))
            for name in ['desktop-no-caps', 'desktop-audio-session', 'desktop-flatpak-session', 'virt-manager-launch']:
                script = script.replace('/usr/libexec/' + name, str(tmp / name))
            for name in ['flatpak', 'Xwayland', 'firefox-esr']:
                script = script.replace('/usr/bin/' + name, str(tmp / name))
            session = tmp / 'session'
            session.write_text(script)
            env = dict(os.environ, HOME=str(tmp), USER='alice', XDG_RUNTIME_DIR=str(tmp))
            env.pop('GTK_IM_MODULE', None)
            env.pop('GTK_IM_MODULE_FILE', None)
            for enabled in [False, True]:
                if enabled:
                    (tmp / 'ime').write_text('#!/bin/sh\n')
                    (tmp / 'ime').chmod(0o755)
                result = subprocess.run(['sh', str(session), 'HDMI-A-1', '192.0.2.1', '5900', 'key', 'cert'],
                                        env=env, capture_output=True, text=True, check=True)
                config = (tmp / 'weston.ini').read_text()
                self.assertEqual('[input-method]' in config, enabled)
                self.assertEqual(result.stdout.splitlines()[0], 'fcitx' if enabled else '')
                if enabled:
                    self.assertIn('path=' + str(tmp / 'ime'), config)
                    self.assertIn('/usr/share/fcitx5-gtk/immodules.cache', result.stdout)
                self.assertIn('name=vnc\nmirror-of=HDMI-A-1', config)


if __name__ == '__main__':
    unittest.main()
