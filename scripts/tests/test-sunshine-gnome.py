#!/usr/bin/env python3
"""Test explicit Sunshine capture selection without fallback to unsupported modes."""
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


if __name__ == '__main__':
    unittest.main()
