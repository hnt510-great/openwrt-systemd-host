#!/usr/bin/env python3
"""Test explicit capture selection and safe compositor startup configuration."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]


class Capture(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.bin = self.path / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        XDG_RUNTIME_DIR=str(self.path), WAYLAND_DISPLAY='wayland-1',
                        OPENWRT_DESKTOP_LAN_ADDRESS='192.0.2.1', OPENWRT_DESKTOP_OUTPUT='HDMI-A-1',
                        USER='alice', HOME=str(self.path))
        self.tool('id', 'case "$1" in -u) echo 1000;; -un) echo alice;; esac')
        self.tool('uci', 'case "$*" in *sunshine_capture*) printf "%s" "${CAPTURE:-}";; *) echo alice;; esac')
        self.tool('systemctl', 'exit "${PIPEWIRE_FAILURE:-0}"')
        self.tool('record', '/usr/bin/python3 -c \'import json,sys; print(json.dumps(sys.argv[1:]))\' "$@"')

    def tool(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)
        return path

    def test_sunshine_selection_and_no_fallback(self):
        source = (ROOT / 'package/custom/sunshine/files/sunshine-session').read_text()
        common = self.path / 'common'
        common.write_text('')
        source = source.replace('/usr/libexec/desktop-common.sh', str(common))
        source = source.replace('/sys/class/drm', str(self.path / 'drm'))
        source = source.replace('/usr/bin/sunshine', str(self.bin / 'record'))
        script = self.path / 'sunshine-session'
        script.write_text(source)
        for mode, valid in [('', True), ('kms', True), ('portal', True), ('weston', False), ('auto', False), ('portal\n[bad]', False)]:
            with self.subTest(mode=mode):
                result = subprocess.run(['sh', str(script)], env=dict(self.env, CAPTURE=mode), capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, valid, result.stderr)
                if valid:
                    args = json.loads(result.stdout)
                    self.assertIn('capture=' + (mode or 'portal'), args)
                    self.assertIn('bind_address=192.0.2.1', args)


    def test_gnome_handoff_cleans_environment_and_requires_keyring(self):
        import socket
        bus = socket.socket(socket.AF_UNIX)
        self.addCleanup(bus.close)
        bus.bind(str(self.path / 'bus'))
        keyring = self.tool('keyring', 'exit "${KEYRING_FAILURE:-0}"')
        output = self.path / 'session.json'
        recorder = self.tool('gnome-session',
                             "/usr/bin/python3 -c 'import json,os,sys; "
                             'json.dump([sys.argv[1:],dict(os.environ)],'
                             'open(os.environ["SESSION_OUTPUT"],"w"))\' "$@"')
        source = (ROOT / 'package/custom/openwrt-desktop/files/desktop-session').read_text()
        source = source.replace('/usr/libexec/desktop-keyring-unlock', str(keyring))
        source = source.replace('/usr/bin/gnome-session', str(recorder))
        script = self.path / 'desktop-session'
        script.write_text(source)
        inherited = dict(WAYLAND_SOCKET='9999', GTK_IM_MODULE='fcitx',
                         GTK_IM_MODULE_FILE='old-module', LIBSEAT_BACKEND='seatd')
        for failure in ['1', '0']:
            with self.subTest(keyring_failure=failure):
                result = subprocess.run(['sh', str(script)], capture_output=True, text=True,
                                        env=dict(self.env, **inherited, KEYRING_FAILURE=failure,
                                                 SESSION_OUTPUT=str(output)))
                self.assertEqual(result.returncode == 0, failure == '0', result.stderr)
                if failure == '1':
                    self.assertFalse(output.exists())
                else:
                    arguments, environment = json.loads(output.read_text())
                    self.assertEqual(arguments, ['--session=gnome'])
                    self.assertEqual(environment['XDG_CURRENT_DESKTOP'], 'GNOME')
                    self.assertEqual(environment['XDG_SESSION_TYPE'], 'wayland')
                    for name in inherited:
                        self.assertNotIn(name, environment)


if __name__ == '__main__':
    unittest.main()
