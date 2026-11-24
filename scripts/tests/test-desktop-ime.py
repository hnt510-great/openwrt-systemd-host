#!/usr/bin/env python3
"""Exercise first-use IME setup, user configuration preservation, and GNOME input handoff."""
import os
from pathlib import Path
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
            client.write_text('#!/usr/bin/env python3\nimport os,sys\n'
                              'assert "WAYLAND_SOCKET" not in os.environ\n'
                              'assert sys.argv[1:]==["--replace","--enable=ibusfrontend"]\nprint("ready")\n')
            client.chmod(0o755)
            init_script = tmp / 'desktop-ime-init'
            init_script.write_text((FILES / 'desktop-ime-init').read_text()
                                   .replace('/usr/share/openwrt-desktop-ime', str(FILES)))
            init_script.chmod(0o755)
            script = tmp / 'session'
            script.write_text((FILES / 'desktop-ime-session').read_text()
                              .replace('/usr/libexec/desktop-ime-init', str(init_script))
                              .replace('/usr/bin/fcitx5', str(client)))
            env = dict(os.environ, HOME=str(tmp), XDG_CONFIG_HOME=str(tmp / 'custom config'),
                       WAYLAND_SOCKET='9999')
            config = tmp / 'custom config/fcitx5'

            def launch():
                result = subprocess.run(['sh', str(script)], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout.strip(), 'ready')

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

    def test_plasma_uses_kwin_wayland_input_method_not_standalone_service(self):
        fcitx_mk = (ROOT / 'package/custom/fcitx5/Makefile').read_text()
        self.assertIn('/usr/share/applications/org.fcitx.Fcitx5.desktop', fcitx_mk)
        self.assertFalse((FILES / 'openwrt-fcitx5-plasma.service').exists())

        ime_mk = (ROOT / 'package/custom/openwrt-desktop-ime/Makefile').read_text()
        self.assertNotIn('openwrt-fcitx5-plasma.service', ime_mk)

        plasma_session = (ROOT / 'package/custom/openwrt-desktop-plasma/files/sessions.d/plasma').read_text()
        self.assertIn('XMODIFIERS=@im=fcitx', plasma_session)
        self.assertIn('rm -f "$wants/openwrt-fcitx5-plasma.service"', plasma_session)
        self.assertNotIn('for unit in openwrt-plasma-remotes.service openwrt-fcitx5-plasma.service', plasma_session)

        # Exercise desktop-plasma-settings --init-only KWin InputMethod + VirtualKeyboardEnabled setup
        with tempfile.TemporaryDirectory() as directory:
            tmp = Path(directory)
            fake_bin = tmp / 'bin'
            fake_bin.mkdir()
            state = tmp / 'kwinrc.json'
            state.write_text('{}')
            (fake_bin / 'id').write_text('#!/bin/sh\necho 1000\n')
            (fake_bin / 'id').chmod(0o755)
            (fake_bin / 'kreadconfig6').write_text(
                '#!/usr/bin/env python3\n'
                'import json, sys\n'
                f'data = json.loads(open({str(state)!r}).read())\n'
                'args = sys.argv[1:]\n'
                'key = (args[args.index("--file")+1], args[args.index("--group")+1], args[args.index("--key")+1])\n'
                'val = data.get(":".join(key), "")\n'
                'if val: print(val)\n'
            )
            (fake_bin / 'kreadconfig6').chmod(0o755)
            (fake_bin / 'kwriteconfig6').write_text(
                '#!/usr/bin/env python3\n'
                'import json, sys\n'
                f'p = {str(state)!r}\n'
                'data = json.loads(open(p).read())\n'
                'args = sys.argv[1:]\n'
                'key = (args[args.index("--file")+1], args[args.index("--group")+1], args[args.index("--key")+1])\n'
                'data[":".join(key)] = args[-1]\n'
                'open(p, "w").write(json.dumps(data))\n'
            )
            (fake_bin / 'kwriteconfig6').chmod(0o755)

            desktop_file = tmp / 'org.fcitx.Fcitx5.desktop'
            desktop_file.write_text('[Desktop Entry]\nX-KDE-Wayland-VirtualKeyboard=true\n')
            init_stub = tmp / 'desktop-ime-init'
            init_stub.write_text('#!/bin/sh\nexit 0\n')
            init_stub.chmod(0o755)

            settings_src = (ROOT / 'package/custom/openwrt-desktop-plasma/files/desktop-plasma-settings').read_text()
            settings_src = settings_src.replace('/usr/libexec/desktop-ime-init', str(init_stub))
            settings_src = settings_src.replace('/usr/share/applications/org.fcitx.Fcitx5.desktop', str(desktop_file))
            settings_script = tmp / 'desktop-plasma-settings'
            settings_script.write_text(settings_src)

            env = dict(os.environ, PATH=f'{fake_bin}:{os.environ["PATH"]}', HOME=str(tmp))
            res = subprocess.run(['sh', str(settings_script), '--init-only'],
                                 env=env, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            import json
            written = json.loads(state.read_text())
            self.assertEqual(written['kwinrc:Wayland:InputMethod'], str(desktop_file))
            self.assertEqual(written['kwinrc:Wayland:VirtualKeyboardEnabled'], 'true')

            # Explicit user override is preserved on subsequent runs
            written['kwinrc:Wayland:VirtualKeyboardEnabled'] = 'false'
            state.write_text(json.dumps(written))
            res = subprocess.run(['sh', str(settings_script), '--init-only'],
                                 env=env, capture_output=True, text=True)
            self.assertEqual(res.returncode, 0, res.stderr)
            self.assertEqual(json.loads(state.read_text())['kwinrc:Wayland:VirtualKeyboardEnabled'], 'false')



if __name__ == '__main__':
    unittest.main()
