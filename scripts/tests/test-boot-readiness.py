#!/usr/bin/env python3
"""Exercise boot helpers with isolated device, ACL and bus fixtures."""
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]
PODMAN = ROOT / 'package/custom/openwrt-podman-rootless/files'
DBUS = ROOT / 'package/system/systemd-openwrt/files/openwrt-dbus-ready'


class Helpers(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}', FIXTURE=str(self.root))
        self.env.pop('MAINPID', None)

    def command(self, name, body):
        path = self.bin / name
        path.write_text('#!/usr/bin/env python3\n' + body)
        path.chmod(0o755)

    def run_helper(self, path, *args, ok=True):
        result = subprocess.run(['sh', str(path), *args], env=self.env,
                                text=True, capture_output=True, timeout=30)
        self.assertEqual(result.returncode == 0, ok, result.stderr)
        return result


class TunPermissions(Helpers):
    def setUp(self):
        super().setUp()
        self.device = self.root / 'tun'
        self.device.symlink_to('/dev/null')
        self.group = self.root / 'group'
        self.group.write_text('podman:x:989:alice,bob\n')
        self.acls = self.root / 'acls.json'
        self.acls.write_text(json.dumps({'9999': 'r', '1003': 'rw'}))
        (self.root / 'state').write_text('1003\n')
        (self.root / 'podman.service').touch()
        source = (PODMAN / 'podman-tun-permissions').read_text()
        for old, new in [('/dev/net/tun', str(self.device)),
                         ('/etc/group', str(self.group)),
                         ('/usr/lib/systemd/user/podman.service', str(self.root / 'podman.service')),
                         ('/run/podman-tun-permissions.lock', str(self.root / 'lock')),
                         ('/run/podman-tun-acl-uids', str(self.root / 'state'))]:
            source = source.replace(old, new)
        self.helper = self.root / 'helper'
        self.helper.write_text(source)
        self.command('id', "import sys\nprint({'alice':1001,'bob':1002}[sys.argv[-1]])\n")
        self.command('chmod', 'pass\n')
        self.command('chgrp', "import os,time\nfrom pathlib import Path\np=Path(os.environ['FIXTURE'])/'events'\nwith p.open('a') as f:f.write('begin\\n')\ntime.sleep(.1)\n")
        self.command('setfacl', """import json,os,sys
from pathlib import Path
root=Path(os.environ['FIXTURE'])
path=root/'acls.json'
acls=json.loads(path.read_text())
parts=sys.argv[2].split(':')
if sys.argv[1]=='-m':acls[parts[1]]=parts[2]
else:acls.pop(parts[1],None)
path.write_text(json.dumps(acls))
with (root/'events').open('a') as f:f.write(sys.argv[2]+'\\n')
""")

    def test_grants_revokes_and_preserves_unrelated_acl(self):
        self.run_helper(self.helper, '--require-device')
        self.assertEqual(json.loads(self.acls.read_text()), {'9999': 'r', '1001': 'rw', '1002': 'rw'})
        self.assertEqual((self.root / 'state').read_text(), '1001\n1002\n')
        self.run_helper(self.helper, '--require-device')
        self.group.write_text('podman:x:989:bob\n')
        self.run_helper(self.helper, '--require-device')
        self.assertEqual(json.loads(self.acls.read_text()), {'9999': 'r', '1002': 'rw'})

    def test_missing_device_is_strict_but_legacy_is_compatible(self):
        self.device.unlink()
        self.assertIn('not a character device', self.run_helper(self.helper, '--require-device', ok=False).stderr)
        self.run_helper(self.helper)
        self.assertFalse((self.root / 'events').exists())

    def test_concurrent_updates_are_serialized(self):
        processes = [subprocess.Popen(['sh', str(self.helper), '--require-device'], env=self.env,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(2)]
        for process in processes:
            _, err = process.communicate(timeout=30)
            self.assertEqual(process.returncode, 0, err)
        events = (self.root / 'events').read_text().splitlines()
        self.assertEqual(events, ['begin', 'u:1001:rw', 'u:1002:rw', 'u:1003',
                                  'begin', 'u:1001:rw', 'u:1002:rw'])


class BusReadiness(Helpers):
    def setUp(self):
        super().setUp()
        self.socket = socket.socket(socket.AF_UNIX)
        self.addCleanup(self.socket.close)
        self.socket.bind(str(self.root / 'bus'))
        (self.root / 'proc/2345').mkdir(parents=True)
        self.cmdline = self.root / 'proc/2345/cmdline'
        self.cmdline.write_bytes(b'dbus-daemon\0--system\0--systemd-activation\0')
        self.helper = self.root / 'helper'
        self.helper.write_text(DBUS.read_text().replace('/run/dbus/system_bus_socket', str(self.root / 'bus'))
                               .replace('/proc/$expected/cmdline', str(self.root / 'proc/$expected/cmdline')))
        self.command('systemctl', "print('2345')\n")
        self.command('busctl', """import os,sys
if os.environ.get('BUS_FAIL'):sys.exit(1)
print('u '+(os.environ.get('BUS_PID','2345') if sys.argv[-1]=='org.freedesktop.DBus' else os.environ.get('MANAGER_PID','1')))
""")

    def test_healthy_bus(self):
        self.run_helper(self.helper, '--check')

    def test_socket_alone_is_insufficient(self):
        self.env['BUS_FAIL'] = '1'
        self.run_helper(self.helper, '--check', ok=False)

    def test_wrong_daemon_and_disconnected_pid1(self):
        self.env['BUS_PID'] = '7890'
        self.assertIn('different daemon', self.run_helper(self.helper, '--check', ok=False).stderr)
        self.env['BUS_PID'] = '2345'
        self.env['MANAGER_PID'] = '99'
        self.assertIn('PID 1', self.run_helper(self.helper, '--check', ok=False).stderr)

    def test_activation_required(self):
        self.cmdline.write_bytes(b'dbus-daemon\0--system\0--nofork\0')
        self.assertIn('lacks systemd activation', self.run_helper(self.helper, '--check', ok=False).stderr)

    def test_startup_does_not_wait_for_pid1_reconnect(self):
        self.env['MANAGER_PID'] = '0'
        self.run_helper(self.helper)
        self.run_helper(self.helper, '--check', ok=False)


class LegacyBusOwnership(Helpers):
    def setUp(self):
        super().setUp()
        source = (ROOT / 'feeds/packages/utils/dbus/files/dbus.init').read_text()
        self.init = self.root / 'dbus.init'
        source = source.replace('/run/systemd/system', str(self.root / 'native'))
        source = source.replace('/usr/lib/systemd/system/dbus.service', str(self.root / 'dbus.service'))
        source = source.replace('/usr/bin/systemctl', str(self.bin / 'systemctl'))
        self.init.write_text(source)
        (self.root / 'native').mkdir()
        (self.root / 'dbus.service').touch()
        self.command('systemctl', "import sys\nprint('systemctl '+' '.join(sys.argv[1:]))\n")

    def invoke(self, action, offline=False):
        env = dict(self.env, IPKG_INSTROOT='/offline' if offline else '')
        return subprocess.run(['sh', '-c', 'action=$1; . "$2"; echo traditional-path',
                               'fixture', action, str(self.init)], env=env,
                              capture_output=True, text=True, check=True).stdout.strip()

    def test_native_actions_delegate_without_traditional_daemon(self):
        for action in ('boot', 'start', 'restart', 'reload'):
            with self.subTest(action=action):
                self.assertEqual(self.invoke(action), 'systemctl start dbus.service')
        for action in ('stop', 'shutdown'):
            self.assertEqual(self.invoke(action), '')

    def test_recovery_and_offline_install_keep_traditional_path(self):
        self.assertEqual(self.invoke('start', offline=True), 'traditional-path')
        (self.root / 'native').rmdir()
        self.assertEqual(self.invoke('start'), 'traditional-path')


if __name__ == '__main__':
    unittest.main()
