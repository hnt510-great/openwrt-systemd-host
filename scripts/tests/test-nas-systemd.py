#!/usr/bin/env python3
"""Exercise native wsdd2 and avahi-daemon adapters without touching a manager."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
WSDD2_FILES = TREE / 'feeds/packages/net/wsdd2/files'
AVAHI_FILES = TREE / 'feeds/packages/libs/avahi/files'


class NasSystemdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='nas-systemd-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, 'TEST_ROOT': str(self.root), 'IPKG_INSTROOT': '',
                    'PATH': str(self.root / 'bin') + ':' + os.environ['PATH']}
        for name in ('bin', 'lib/functions', 'usr/libexec', 'usr/bin', 'usr/sbin',
                     'usr/lib/systemd/system', 'etc/samba', 'etc/ksmbd', 'etc/init.d',
                     'etc/systemd/system', 'var/etc', 'tmp/sysinfo', 'proc/sys/kernel'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / 'proc/sys/kernel/hostname').write_text('RouterHost.lan\n')
        (self.root / 'tmp/sysinfo/board_name').write_text('azw,eq\n')
        (self.root / 'tmp/sysinfo/model').write_text('AZW EQ: N5105\n')
        self.write('lib/functions.sh', 'config_load() { :; }\n')
        self.write('lib/functions/network.sh',
                   'network_get_device() { eval "$1=${MOCK_LAN_DEV:-br-lan}"; }\n')
        self.write('bin/systemctl', '''#!/bin/sh
printf '%s\\n' "$*" >> "$TEST_ROOT/commands"
if [ "$1" = is-active ]; then
  if [ "$3" = samba4.service ]; then
    test "${SAMBA_ACTIVE:-1}" = 1
  else
    test "${ACTIVE:-1}" = 1
  fi
fi
''')
        self.write('bin/logger', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_ROOT/logs"\n')
        self.write('usr/bin/wsdd2', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$TEST_ROOT/commands"\n')
        self.write('etc/init.d/ksmbd', '#!/bin/sh\ntest "${KSMBD_RUNNING:-0}" = 1\n')
        self.write('etc/init.d/samba4', '#!/bin/sh\ntest "${SAMBA_RUNNING:-0}" = 1\n')
        self.write('etc/init.d/samba', '#!/bin/sh\ntest "${SAMBA3_RUNNING:-0}" = 1\n')

    def write(self, name, text):
        path = self.root / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def script(self, directory, name):
        source = (directory / name).read_text()
        source = re.sub(r'/(?:usr|etc|var|run|lib|tmp|proc)/',
                        lambda match: str(self.root) + match[0], source)
        return self.write('bin/' + name, source)

    def run_script(self, directory, name, *args, **env):
        return subprocess.run(['sh', str(self.script(directory, name)), *args], text=True,
                              capture_output=True, env={**self.env, **env}, timeout=10)

    def actions(self):
        path = self.root / 'commands'
        return path.read_text().splitlines() if path.exists() else []

    def native_wsdd2(self):
        (self.root / 'run/systemd/system').mkdir(parents=True, exist_ok=True)
        (self.root / 'usr/lib/systemd/system/wsdd2.service').touch()
        (self.root / 'usr/lib/systemd/system/samba4.service').touch()

    def native_avahi(self):
        (self.root / 'run/systemd/system').mkdir(parents=True, exist_ok=True)
        (self.root / 'usr/lib/systemd/system/avahi-daemon.service').touch()

    def test_wsdd2_condition_and_run_with_samba4(self):
        self.native_wsdd2()
        (self.root / 'etc/samba/smb.conf').write_text(
            '[global]\n\tnetbios name = OpenWrt\n\tmdns name = mdns\n\tworkgroup = HOME\n')
        (self.root / 'usr/libexec/wsdd2-config.sh').write_text(
            self.script(WSDD2_FILES, 'wsdd2-config.sh').read_text())
        self.assertEqual(self.run_script(WSDD2_FILES, 'wsdd2-systemd', 'condition').returncode, 0)
        done = self.run_script(WSDD2_FILES, 'wsdd2-systemd', 'run')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            self.actions()[-1],
            '-i br-lan -N OpenWrt -G HOME -b vendor:azw,model:AZW_EQ,sku:eq',
        )

    def test_wsdd2_condition_skips_when_smb_inactive(self):
        self.native_wsdd2()
        (self.root / 'etc/samba/smb.conf').write_text('[global]\n\tworkgroup = WORKGROUP\n')
        (self.root / 'usr/libexec/wsdd2-config.sh').write_text(
            self.script(WSDD2_FILES, 'wsdd2-config.sh').read_text())
        self.assertEqual(
            self.run_script(WSDD2_FILES, 'wsdd2-systemd', 'condition', SAMBA_ACTIVE='0').returncode,
            1,
        )

    def test_wsdd2_reconcile_and_reload_respect_active_state(self):
        self.native_wsdd2()
        (self.root / 'etc/samba/smb.conf').write_text('[global]\n\tworkgroup = WORKGROUP\n')
        (self.root / 'usr/libexec/wsdd2-config.sh').write_text(
            self.script(WSDD2_FILES, 'wsdd2-config.sh').read_text())
        self.assertEqual(
            self.run_script(WSDD2_FILES, 'wsdd2-systemd', 'reconcile', ACTIVE='0').returncode, 0)
        self.assertEqual(self.actions(), ['is-active --quiet wsdd2.service'])
        self.assertEqual(
            self.run_script(WSDD2_FILES, 'wsdd2-systemd', 'reconcile', ACTIVE='1', SAMBA_ACTIVE='1').returncode,
            0,
        )
        self.assertEqual(self.actions()[-2:], [
            'reset-failed wsdd2.service',
            '--no-block restart wsdd2.service',
        ])
        self.assertEqual(
            self.run_script(WSDD2_FILES, 'wsdd2-systemd', 'reconcile', ACTIVE='1', SAMBA_ACTIVE='0').returncode,
            0,
        )
        self.assertEqual(self.actions()[-1], '--no-block stop wsdd2.service')

    def test_wsdd2_native_init_and_recovery_mode(self):
        self.native_wsdd2()
        self.write('usr/libexec/wsdd2-systemd', '#!/bin/sh\necho "$*" >> "$TEST_ROOT/commands"\n')
        init = self.script(WSDD2_FILES, 'wsdd2.init')
        for action in ('boot', 'shutdown', 'start', 'stop', 'reload', 'enable', 'enabled'):
            done = subprocess.run(['sh', '-c', 'action=$1; script=$2; shift 2; . "$script"', 'test', action, str(init)],
                                  capture_output=True, text=True, env=self.env)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.actions(), ['start', 'stop', 'reload', 'enable', 'enabled'])

        (self.root / 'run/systemd/system').rmdir()
        (self.root / 'usr/libexec/wsdd2-config.sh').write_text(
            self.script(WSDD2_FILES, 'wsdd2-config.sh').read_text())
        done = subprocess.run(['sh', '-c', '. "$1"; test "$USE_PROCD" = 1; '
                               'command -v start_service; command -v service_triggers', 'test', str(init)],
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_wsdd2_hotplug_only_acts_on_active_lan(self):
        self.native_wsdd2()
        for iface, active in (('wan', '1'), ('lan', '0')):
            self.assertEqual(
                self.run_script(WSDD2_FILES, 'wsdd2.hotplug', ACTION='ifup', INTERFACE=iface, ACTIVE=active).returncode,
                0,
            )
        self.assertEqual(self.actions(), ['is-active --quiet wsdd2.service'])
        self.assertEqual(
            self.run_script(WSDD2_FILES, 'wsdd2.hotplug', ACTION='ifupdate', INTERFACE='lan', ACTIVE='1').returncode,
            0,
        )
        self.assertEqual(self.actions()[-1], '--no-block start wsdd2-reconfigure.service')

    def test_avahi_native_init_and_recovery_mode(self):
        self.native_avahi()
        self.write('usr/libexec/avahi-daemon-systemd', '#!/bin/sh\necho "$*" >> "$TEST_ROOT/commands"\n')
        init = self.script(AVAHI_FILES, 'avahi-daemon.init')
        for action in ('boot', 'shutdown', 'start', 'stop', 'reload', 'running', 'enable', 'enabled'):
            done = subprocess.run(['sh', '-c', 'action=$1; script=$2; shift 2; . "$script"', 'test', action, str(init)],
                                  capture_output=True, text=True, env=self.env)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.actions(), ['start', 'stop', 'reload', 'running', 'enable', 'enabled'])

        (self.root / 'run/systemd/system').rmdir()
        done = subprocess.run(['sh', '-c', '. "$1"; test "$USE_PROCD" = 1; '
                               'command -v start_service; command -v reload_service', 'test', str(init)],
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_offline_and_upgrade_package_hooks(self):
        for name, directory, pkg, wants in (
            ('wsdd2', WSDD2_FILES, 'wsdd2-package', ('multi-user.target.wants/wsdd2.service',
                                                      'multi-user.target.wants/wsdd2-config.path',
                                                      'samba4.service.wants/wsdd2.service')),
            ('avahi', AVAHI_FILES, 'avahi-daemon-package', ('multi-user.target.wants/avahi-daemon.service',)),
        ):
            for upgrade in ('0', '1'):
                root = self.root / f'{name}-offline-{upgrade}'
                root.mkdir()
                done = subprocess.run(['sh', str(directory / pkg), 'postinst'],
                                      env={**self.env, 'IPKG_INSTROOT': str(root), 'PKG_UPGRADE': upgrade},
                                      capture_output=True, text=True)
                self.assertEqual(done.returncode, 0, done.stderr)
                for rel in wants:
                    self.assertEqual((root / 'etc/systemd/system' / rel).is_symlink(), upgrade == '0')
        self.assertEqual(self.actions(), [])

        self.native_wsdd2()
        self.native_avahi()
        self.assertEqual(self.run_script(WSDD2_FILES, 'wsdd2-package', 'postinst', PKG_UPGRADE='1').returncode, 0)
        self.assertEqual(self.run_script(AVAHI_FILES, 'avahi-daemon-package', 'postinst', PKG_UPGRADE='1').returncode, 0)
        self.assertEqual(self.actions(), [
            'daemon-reload', 'try-restart wsdd2.service',
            'daemon-reload', 'try-restart avahi-daemon.service',
        ])

    def test_unit_properties_and_ordering(self):
        wsdd2_unit = (WSDD2_FILES / 'wsdd2.service').read_text()
        self.assertIn('Slice=nas.slice', wsdd2_unit)
        self.assertIn('After=network-online.target samba4.service samba4@smbd.service', wsdd2_unit)
        self.assertIn('PartOf=samba4.service', wsdd2_unit)
        self.assertIn('WantedBy=multi-user.target samba4.service', wsdd2_unit)
        self.assertNotIn('openwrt-services.service', wsdd2_unit)
        self.assertIn('StartLimitIntervalSec=0', (WSDD2_FILES / 'wsdd2-reconfigure.service').read_text())

        avahi_unit = (AVAHI_FILES / 'avahi-daemon.service').read_text()
        self.assertIn('Slice=nas.slice', avahi_unit)
        self.assertIn('Type=dbus', avahi_unit)
        self.assertIn('BusName=org.freedesktop.Avahi', avahi_unit)
        self.assertIn('After=dbus.service network-online.target', avahi_unit)
        self.assertIn('Before=samba4.service', avahi_unit)
        self.assertNotIn('openwrt-services.service', avahi_unit)

        avahi_nodbus = (AVAHI_FILES / 'avahi-daemon-nodbus.service').read_text()
        self.assertIn('Slice=nas.slice', avahi_nodbus)
        self.assertIn('Type=simple', avahi_nodbus)
        self.assertNotIn('BusName=', avahi_nodbus)


if __name__ == '__main__':
    unittest.main()
