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
        for mode, valid in [('', True), ('kms', True), ('weston', True), ('auto', False), ('weston\n[bad]', False)]:
            with self.subTest(mode=mode):
                result = subprocess.run(['sh', str(script)], env=dict(self.env, CAPTURE=mode), capture_output=True, text=True)
                self.assertEqual(result.returncode == 0, valid, result.stderr)
                if valid:
                    args = json.loads(result.stdout)
                    self.assertIn('capture=' + (mode or 'kms'), args)
                    self.assertEqual('output_name=weston.pipewire' in args, mode == 'weston')

    def test_pipewire_mirror_and_start_failure_preserve_remote_backends(self):
        source = (ROOT / 'package/custom/openwrt-desktop/files/desktop-session').read_text()
        source = source.replace('/usr/libexec/desktop-common.sh', str(ROOT / 'package/custom/openwrt-desktop/files/desktop-common.sh'))
        source = source.replace('/usr/libexec/desktop-dbus-session', str(self.bin / 'record'))
        source = source.replace('/etc/desktop/rdp', str(self.path))
        (self.path / 'alice.sam').touch()
        (self.path / 'systemd').mkdir()
        source = source.replace('/run/systemd/system', str(self.path / 'systemd'))
        module = self.path / 'modules/libweston-16'
        module.mkdir(parents=True)
        (module / 'pipewire-backend.so').touch()
        video = self.path / 'libspa-videoconvert.so'
        video.touch()
        source = source.replace('/usr/lib/spa-0.2/videoconvert/libspa-videoconvert.so', str(video))
        source = source.replace('/usr/lib/libweston-', str(self.path / 'modules/libweston-'))
        source = source.replace('/usr/bin/desktop-applications', str(self.tool('desktop-applications', ':')))
        for name in ['desktop-no-caps', 'desktop-flatpak-session', 'desktop-audio-session', 'desktop-ime-session', 'virt-manager-launch']:
            source = source.replace('/usr/libexec/' + name, str(self.path / name))
        for name in ['Xwayland', 'flatpak', 'firefox-esr']:
            source = source.replace('/usr/bin/' + name, str(self.path / name))
        script = self.path / 'desktop-session'
        script.write_text(source)
        for mode, failure, missing in [('kms', '0', False), ('weston', '0', False),
                                       ('weston', '1', False), ('weston', '0', True)]:
            with self.subTest(mode=mode, failure=failure, missing_video_plugin=missing):
                if missing:
                    video.unlink()
                result = subprocess.run(['sh', str(script), 'HDMI-A-1', '192.0.2.1', '5900', 'key', 'cert', 'gl', '1', '3389', '60'],
                                        env=dict(self.env, CAPTURE=mode, PIPEWIRE_FAILURE=failure), capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(result.stdout)
                active = mode == 'weston' and failure == '0' and not missing
                self.assertIn('--backends=drm,vnc,rdp' + (',pipewire' if active else ''), args)
                config = (self.path / 'weston.ini').read_text()
                self.assertEqual('name=pipewire\nmirror-of=HDMI-A-1' in config, active)
                self.assertIn('name=rdp-0\nmirror-of=HDMI-A-1', config)
                self.assertIn('path=' + str(self.bin / 'desktop-applications'), config)


if __name__ == '__main__':
    unittest.main()
