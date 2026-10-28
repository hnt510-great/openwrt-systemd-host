#!/usr/bin/env python3
"""Check audio opt-in, account isolation and the SSH stream contract."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
DESKTOP = ROOT / 'package/custom/openwrt-desktop/files'
AUDIO = ROOT / 'package/custom/openwrt-desktop-audio/files'


class DesktopAudio(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.tmp = Path(self.directory.name)
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        HOME=str(self.tmp), USER='alice', AUDIO_USER='alice', AUDIO_ENABLED='1')
        self.tool('uci', '#!/bin/sh\ncase "$*" in *audio_user*) echo "$AUDIO_USER";; '
                  '*audio_enabled*) echo "$AUDIO_ENABLED";; esac\n')

    def tool(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)
        return path

    def test_audio_requires_enrolled_native_session(self):
        native = self.tmp / 'native'
        native.mkdir()
        log = self.tmp / 'units'
        self.env.update(XDG_RUNTIME_DIR=str(self.tmp), UNIT_LOG=str(log))
        self.tool('id', '#!/bin/sh\necho alice\n')
        self.tool('systemctl', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$UNIT_LOG"\n')
        text = (AUDIO / 'desktop-audio-session').read_text()
        text = text.replace('/run/systemd/system', str(native))
        path = self.tmp / 'audio-session'
        path.write_text(text)
        cases = [('1', 'alice', True, True), ('0', 'alice', True, False),
                 ('1', 'bob', True, False), ('1', 'alice', False, False)]
        for enabled, user, systemd, expected in cases:
            with self.subTest(enabled=enabled, user=user, systemd=systemd):
                if not systemd:
                    native.rmdir()
                log.unlink(missing_ok=True)
                result = subprocess.run(['sh', str(path)],
                                        env=dict(self.env, AUDIO_ENABLED=enabled, AUDIO_USER=user),
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                units = log.read_text() if log.exists() else ''
                self.assertEqual('start pipewire.socket pipewire-pulse.socket wireplumber.service' in units,
                                 expected)
                self.assertNotIn('stop ', units)

    def test_ssh_stream_account_and_format(self):
        runtime = self.tmp / 'run'
        runtime.mkdir()
        self.tool('id', '#!/bin/sh\ncase "$1" in -u) echo 1000;; -un) echo alice;; esac\n')
        self.tool('stat', '#!/bin/sh\necho 1000\n')
        self.tool('parec', '#!/usr/bin/env python3\nimport json,os,sys\n'
                  'print(json.dumps([sys.argv[1:],os.environ["PULSE_SERVER"]]))\n')
        text = (AUDIO / 'desktop-audio-stream').read_text().replace('/run/user/$uid', str(runtime))
        path = self.tmp / 'stream'
        path.write_text(text)
        result = subprocess.run(['sh', str(path)], env=self.env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        args, server = json.loads(result.stdout)
        self.assertIn('--device=@DEFAULT_MONITOR@', args)
        for flag in ['--raw', '--format=s16le', '--rate=48000', '--channels=2']:
            self.assertIn(flag, args)
        self.assertEqual(server, 'unix:' + str(runtime) + '/pulse/native')
        for changes, arguments in [({'AUDIO_USER': 'bob'}, []),
                                   ({'AUDIO_ENABLED': '0'}, []), ({}, ['unexpected'])]:
            result = subprocess.run(['sh', str(path), *arguments],
                                    env=dict(self.env, **changes), capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(result.stdout, b'')

    def test_sunshine_gpu_probe_workaround_is_device_specific(self):
        self.tool('id', '#!/bin/sh\ncase \"$1\" in -u) echo 1000;; -un) echo alice;; esac\n')
        self.tool('uci', '#!/bin/sh\ncase \"$*\" in *sunshine_capture*) echo kms;; *) echo alice;; esac\n')
        sunshine = self.tool('sunshine', '#!/usr/bin/env python3\nimport json,sys\n'
                             'print(json.dumps(sys.argv[1:]))\n')
        common = self.tmp / 'common.sh'
        common.write_text('')
        drm = self.tmp / 'drm'
        drm.mkdir()
        text = (ROOT / 'package/custom/sunshine/files/sunshine-session').read_text()
        text = text.replace('/usr/libexec/desktop-common.sh', str(common))
        text = text.replace('/sys/class/drm', str(drm))
        text = text.replace('/usr/bin/sunshine', str(sunshine))
        session = self.tmp / 'sunshine-session'
        session.write_text(text)
        env = dict(self.env, XDG_RUNTIME_DIR=str(self.tmp), WAYLAND_DISPLAY='wayland-1',
                   OPENWRT_DESKTOP_LAN_ADDRESS='192.0.2.1')
        cases = [([], False), ([('0x8086', '0x4e61')], True),
                 ([('0x8086', '0x1234')], False), ([('0x1002', '0x4e61')], False),
                 ([('0x8086', '0x4e61'), ('0x1002', '0x73ff')], False)]
        for devices, expected in cases:
            with self.subTest(devices=devices):
                for old in drm.glob('renderD*/device/*'):
                    old.unlink()
                for index, (vendor, device) in enumerate(devices):
                    path = drm / f'renderD{128 + index}' / 'device'
                    path.mkdir(parents=True, exist_ok=True)
                    (path / 'vendor').write_text(vendor + '\n')
                    (path / 'device').write_text(device + '\n')
                result = subprocess.run(['sh', str(session)], env=env,
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                args = json.loads(result.stdout)
                self.assertEqual('hevc_mode=1' in args, expected)
                self.assertEqual('av1_mode=1' in args, expected)
                self.assertIn('capture=kms', args)
                self.assertIn('bind_address=192.0.2.1', args)
                self.assertIn('upnp=disabled', args)


if __name__ == '__main__':
    unittest.main()
