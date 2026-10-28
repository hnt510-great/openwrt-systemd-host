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
            script = tmp / 'session'
            script.write_text((FILES / 'desktop-ime-session').read_text()
                              .replace('/usr/share/openwrt-desktop-ime', str(FILES))
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



if __name__ == '__main__':
    unittest.main()
