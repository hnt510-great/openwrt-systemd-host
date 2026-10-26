#!/usr/bin/env python3
"""Exercise GIO desktop entry discovery and launch semantics with isolated data."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Launcher(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        target = ROOT / 'staging_dir/target-x86_64_glibc/root-x86-systemd/usr/lib'
        binary = ROOT / 'build_dir/target-x86_64_glibc/openwrt-desktop-launcher-1/desktop-applications'
        if not binary.exists():
            self.skipTest('build openwrt-desktop-launcher first')
        self.assertTrue((target.parent / 'libexec/gio-launch-desktop').is_file(),
                        'glib2-gio must package its desktop launch helper')
        self.command = [str(target / 'ld-linux-x86-64.so.2'), '--library-path', str(target), str(binary)]
        self.env = dict(os.environ, XDG_DATA_HOME=str(self.path / 'user'),
                        XDG_DATA_DIRS=str(self.path / 'system'), XDG_CURRENT_DESKTOP='Weston',
                        XDG_CACHE_HOME=str(self.path / 'cache'), XDG_CONFIG_HOME=str(self.path / 'config'),
                        GIO_LAUNCH_DESKTOP=str(target.parent / 'libexec/gio-launch-desktop'))
        self.user = self.path / 'user/applications'
        self.system = self.path / 'system/applications'
        self.user.mkdir(parents=True)
        self.system.mkdir(parents=True)

    def entry(self, directory, name, extra='', command='/bin/true'):
        (directory / name).write_text('[Desktop Entry]\nType=Application\nName=' + name + '\nExec=' + command + '\n' + extra)

    def run_launcher(self, *args, **changes):
        return subprocess.run(self.command + list(args), env=dict(self.env, **changes),
                              capture_output=True, text=True, timeout=10)

    def test_visibility_user_overrides_and_missing_executables(self):
        for name in ['visible.desktop', 'hidden.desktop', 'override.desktop']:
            self.entry(self.system, name)
        self.entry(self.user, 'override.desktop', 'Hidden=true\n')
        self.entry(self.user, 'hidden.desktop', 'NoDisplay=true\n')
        self.entry(self.user, 'other.desktop', 'OnlyShowIn=GNOME;\n')
        self.entry(self.user, 'weston.desktop', 'OnlyShowIn=Weston;\n')
        self.entry(self.user, 'missing.desktop', 'TryExec=/nonexistent/openwrt-launcher-test\n')
        result = self.run_launcher('--list')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual({line.split('\t')[0] for line in result.stdout.splitlines()},
                         {'visible.desktop', 'weston.desktop'})

    def test_launch_arguments_cwd_and_wayland_environment(self):
        output = self.path / 'launch.json'
        helper = self.path / 'helper.py'
        helper.write_text('import json,os,sys\n'
                          'open(sys.argv[1],"w").write(json.dumps([sys.argv[2:],os.getcwd(),'
                          'os.environ.get("WAYLAND_SOCKET"),os.environ.get("GTK_IM_MODULE")]))\n')
        self.entry(self.user, 'fixture.desktop', 'Path=' + str(self.path) + '\n',
                   f'/usr/bin/python3 "{helper}" "{output}" "two words" "literal;token" %f')
        result = self.run_launcher('--launch', 'fixture.desktop', WAYLAND_SOCKET='9999', GTK_IM_MODULE='fcitx')
        self.assertEqual(result.returncode, 0, result.stderr)
        for _ in range(50):
            if output.exists():
                break
            time.sleep(.02)
        args, cwd, socket, ime = json.loads(output.read_text())
        self.assertEqual(args, ['two words', 'literal;token'])
        self.assertEqual(cwd, str(self.path))
        self.assertIsNone(socket)
        self.assertEqual(ime, 'fcitx')

    def test_missing_and_hidden_launch_errors(self):
        self.entry(self.user, 'hidden.desktop', 'NoDisplay=true\n')
        for entry in ['absent.desktop', 'hidden.desktop']:
            result = self.run_launcher('--launch', entry)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn('unavailable', result.stderr)


if __name__ == '__main__':
    unittest.main()
