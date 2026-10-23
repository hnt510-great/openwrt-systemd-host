#!/usr/bin/env python3
"""Exercise opt-in ACLs against real Unix sockets without root privileges."""
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/custom/libvirt/files'


class LibvirtAudio(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.uid = os.getuid()
        self.runtime = self.work / str(self.uid)
        self.runtime.mkdir(mode=0o700)
        self.bin = self.work / 'bin'
        self.bin.mkdir()
        # Run the same su command body as this unprivileged test account.
        su = self.bin / 'su'
        su.write_text('#!/bin/sh\n[ "$1" = -s ] && [ "$3" = -c ] && [ "$5" = -- ] || exit 90\nexec /bin/sh -c "$4" "$7"\n')
        su.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'])
        text = (FILES / 'libvirt-pipewire-access').read_text()
        text = text.replace('[ "$(id -u)" = 0 ]', '[ 0 = 0 ]', 1)
        text = text.replace('/run/user/', str(self.work) + '/')
        text = text.replace('libvirt-qemu', '65534')
        self.helper = self.work / 'access'
        self.helper.write_text(text)

    def run_helper(self, *args):
        return subprocess.run(['sh', str(self.helper), *map(str, args)],
                              env=self.env, capture_output=True, text=True)

    def acl(self, path):
        return subprocess.check_output(['getfacl', '-cpn', str(path)], text=True)

    def bind(self):
        server = socket.socket(socket.AF_UNIX)
        server.bind(str(self.runtime / 'pipewire-0'))
        self.addCleanup(server.close)

    def test_grant_recreated_socket_and_revoke(self):
        self.bind()
        unrelated = self.runtime / 'bus'
        unrelated.write_text('private')
        before = self.acl(unrelated)
        self.assertEqual(self.run_helper(self.uid).returncode, 0)
        self.assertIn('user:65534:--x', self.acl(self.runtime))
        self.assertIn('user:65534:rw-', self.acl(self.runtime / 'pipewire-0'))
        self.assertEqual(self.acl(unrelated), before)
        changed = self.runtime.stat().st_ctime_ns
        self.assertEqual(self.run_helper(self.uid).returncode, 0)
        self.assertEqual(self.runtime.stat().st_ctime_ns, changed)
        (self.runtime / 'pipewire-0').unlink()
        self.bind()
        self.assertEqual(self.run_helper(self.uid).returncode, 0)
        self.assertIn('user:65534:rw-', self.acl(self.runtime / 'pipewire-0'))
        self.assertEqual(self.run_helper(self.uid, 'revoke').returncode, 0)
        self.assertNotIn('user:65534:', self.acl(self.runtime))
        self.assertNotIn('user:65534:', self.acl(self.runtime / 'pipewire-0'))

    def test_absent_runtime_and_socket(self):
        self.assertEqual(self.run_helper(self.uid).returncode, 0)
        self.assertEqual(self.run_helper(self.uid, 'revoke').returncode, 0)
        self.runtime.rmdir()
        self.assertEqual(self.run_helper(self.uid).returncode, 0)

    def test_symlinks_are_ignored(self):
        other = self.work / 'other'
        other.mkdir(mode=0o700)
        before = self.acl(other)
        self.runtime.rmdir()
        self.runtime.symlink_to(other)
        self.assertEqual(self.run_helper(self.uid).returncode, 0)
        self.assertEqual(self.acl(other), before)
        self.runtime.unlink()
        self.runtime.mkdir(mode=0o700)
        (self.runtime / 'pipewire-0').symlink_to(other)
        self.assertEqual(self.run_helper(self.uid).returncode, 0)
        self.assertEqual(self.acl(other), before)

    def test_reject_root_malformed_and_unknown_uid(self):
        for uid in ['0', '00', '01', '-1', '../1000', 'alice', '999999999']:
            with self.subTest(uid=uid):
                self.assertNotEqual(self.run_helper(uid).returncode, 0)
        self.assertNotEqual(self.run_helper(self.uid, 'bad-action').returncode, 0)

    def test_examples_have_matching_sound_and_backend(self):
        for name, backend in [('openwrt-graphics-vm.xml', 'spice'),
                              ('openwrt-graphics-gl-vm.xml', 'spice'),
                              ('openwrt-graphics-pipewire-vm.xml', 'pipewire')]:
            devices = ET.parse(FILES / name).getroot().find('devices')
            self.assertEqual(devices.find('sound/audio').get('id'),
                             devices.find('audio').get('id'))
            self.assertEqual(devices.find('audio').get('type'), backend)
            subprocess.run(['virt-xml-validate', str(FILES / name), 'domain'],
                           check=True, capture_output=True)


if __name__ == '__main__':
    unittest.main()
