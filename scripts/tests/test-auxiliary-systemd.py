#!/usr/bin/env python3
"""Exercise native cron, nlbwmon, and ddns-go adapters without touching a manager."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
CRON_FILES = TREE / 'package/utils/busybox/files'
NLBWMON_FILES = TREE / 'feeds/packages/net/nlbwmon/files'
DDNS_GO_FILES = TREE / 'feeds/taskplan/ddns-go/files'
SLICE_FILE = TREE / 'package/system/systemd-openwrt/files/auxiliary.slice'


class AuxiliarySystemdTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='aux-systemd-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {
            **os.environ,
            'TEST_ROOT': str(self.root),
            'IPKG_INSTROOT': '',
            'PATH': str(self.root / 'bin') + ':' + os.environ['PATH'],
        }
        for name in (
            'bin', 'sbin', 'lib/functions', 'usr/libexec', 'usr/bin', 'usr/sbin',
            'usr/lib/systemd/system', 'etc/crontabs', 'etc/ddns-go', 'etc/init.d',
            'etc/systemd/system', 'var/spool', 'var/lib/nlbwmon', 'proc',
        ):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        (self.root / 'proc/uptime').write_text('500.00 1000.00\n')
        self.write('lib/functions.sh', '''config_load() { LAST_CONFIG="$1"; }
config_foreach() {
  case "$LAST_CONFIG" in
    nlbwmon) "$1" main ;;
    dhcp) "$1" lan ;;
    ddns-go) "$1" config ;;
  esac
}
config_get() {
  eval "val=\\${MOCK_${3}:-$4}"
  eval "$1=\\$val"
}
config_get_bool() {
  eval "val=\\${MOCK_${3}:-$4}"
  case "$val" in
    1|on|true|yes|enabled) eval "$1=1" ;;
    *) eval "$1=0" ;;
  esac
}
config_list_foreach() {
  for item in ${MOCK_LOCAL_NETWORKS:-192.168.0.0/16 lan}; do
    "$3" "$item"
  done
}
uci_get() {
  printf '%s' "${MOCK_CRONLOGLEVEL:-}"
}
''')
        self.write('lib/functions/network.sh', '''network_get_subnets() {
  [ "$2" = lan ] || return 1
  eval "$1='${MOCK_LAN_SUBNETS:-192.0.2.1/24}'"
}
network_get_subnets6() {
  [ "$2" = lan ] || return 1
  eval "$1='${MOCK_LAN_SUBNETS6:-fd00::1/64}'"
}
''')
        self.write('sbin/validate_data', '''#!/bin/sh
case "$2" in
  ''|*[!0-9]*) exit 1 ;;
  *) exit 0 ;;
esac
''')
        self.write('bin/systemctl', '''#!/bin/sh
printf '%s\\n' "$*" >> "$TEST_ROOT/commands"
if [ "$1" = is-active ]; then
  test "${ACTIVE:-1}" = 1
elif [ "$1" = show ]; then
  case "$*" in
    *openwrt-services.service*) printf '%s\\n' "${RC_STATE:-active}" ;;
    *ExecMainStartTimestampMonotonic*) printf '%s\\n' "${CRON_START_MONO:-12345}" ;;
  esac
fi
''')
        self.write('bin/chown', '#!/bin/sh\nprintf "chown %s\\n" "$*" >> "$TEST_ROOT/commands"\n')
        self.write('usr/sbin/crond', '#!/bin/sh\nprintf "crond %s\\n" "$*" >> "$TEST_ROOT/commands"\n')
        self.write('usr/sbin/nlbwmon', '#!/bin/sh\nprintf "nlbwmon %s\\n" "$*" >> "$TEST_ROOT/commands"\n')
        self.write('usr/bin/ddns-go', '#!/bin/sh\nprintf "ddns-go %s\\n" "$*" >> "$TEST_ROOT/commands"\n')

    def write(self, name, text):
        path = self.root / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def script(self, directory, name):
        source = (directory / name).read_text()
        source = re.sub(
            r'/(?:usr|etc|var|run|lib|tmp|proc|sbin)/',
            lambda match: str(self.root) + match[0],
            source,
        )
        return self.write('bin/' + name, source)

    def run_script(self, directory, name, *args, **env):
        return subprocess.run(
            ['sh', str(self.script(directory, name)), *args],
            text=True,
            capture_output=True,
            env={**self.env, **env},
            timeout=10,
        )

    def actions(self):
        path = self.root / 'commands'
        return path.read_text().splitlines() if path.exists() else []

    def clear_actions(self):
        path = self.root / 'commands'
        if path.exists():
            path.unlink()

    def native_mode(self):
        (self.root / 'run/systemd/system').mkdir(parents=True, exist_ok=True)
        for unit in ('cron.service', 'nlbwmon.service', 'ddns-go.service'):
            (self.root / 'usr/lib/systemd/system' / unit).touch()

    def install_configs(self):
        (self.root / 'usr/libexec/cron-config.sh').write_text(
            self.script(CRON_FILES, 'cron-config.sh').read_text())
        (self.root / 'usr/libexec/nlbwmon-config.sh').write_text(
            self.script(NLBWMON_FILES, 'nlbwmon-config.sh').read_text())
        (self.root / 'usr/libexec/ddns-go-config.sh').write_text(
            self.script(DDNS_GO_FILES, 'ddns-go-config.sh').read_text())

    def test_cron_condition_run_and_reconcile(self):
        self.native_mode()
        self.install_configs()
        self.assertEqual(self.run_script(CRON_FILES, 'cron-systemd', 'condition').returncode, 1)
        self.assertEqual(self.run_script(CRON_FILES, 'cron-systemd', 'reconcile', ACTIVE='1').returncode, 0)
        self.assertEqual(self.actions()[-1], '--no-block stop cron.service')
        self.assertTrue((self.root / 'run/cron-systemd.empty-stopped').exists())
        (self.root / 'run/cron-systemd.empty-stopped').unlink()

        (self.root / 'etc/crontabs/root').write_text('0 * * * * /bin/true\n')
        self.assertEqual(self.run_script(CRON_FILES, 'cron-systemd', 'condition').returncode, 0)
        done = self.run_script(CRON_FILES, 'cron-systemd', 'run', MOCK_CRONLOGLEVEL='5')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertTrue((self.root / 'var/spool/cron/crontabs').is_symlink())
        self.assertEqual(
            self.actions()[-1],
            f'crond -f -c {self.root}/etc/crontabs -l 5',
        )

        self.assertNotEqual(
            self.run_script(CRON_FILES, 'cron-systemd', 'run', MOCK_CRONLOGLEVEL='bad').returncode,
            0,
        )
        self.clear_actions()
        self.assertEqual(
            self.run_script(CRON_FILES, 'cron-systemd', 'reconcile', ACTIVE='0').returncode,
            0,
        )
        # Previously running and manually stopped (no empty stamp, monotonic != 0): stay stopped.
        self.assertEqual(self.actions(), [
            'is-active --quiet cron.service',
            'show -p ExecMainStartTimestampMonotonic --value cron.service',
        ])

        # Skipped at boot due to empty /etc/crontabs (monotonic == 0): start when entries appear.
        self.clear_actions()
        self.assertEqual(
            self.run_script(CRON_FILES, 'cron-systemd', 'reconcile', ACTIVE='0', CRON_START_MONO='0').returncode,
            0,
        )
        self.assertEqual(self.actions()[-2:], ['reset-failed cron.service', '--no-block start cron.service'])

        # Stopped earlier due to empty /etc/crontabs (empty stamp present): start when entries appear.
        (self.root / 'etc/crontabs/root').unlink()
        self.assertEqual(self.run_script(CRON_FILES, 'cron-systemd', 'reconcile', ACTIVE='1').returncode, 0)
        self.assertTrue((self.root / 'run/cron-systemd.empty-stopped').exists())
        (self.root / 'etc/crontabs/root').write_text('0 * * * * /bin/true\n')
        self.clear_actions()
        self.assertEqual(self.run_script(CRON_FILES, 'cron-systemd', 'reconcile', ACTIVE='0').returncode, 0)
        self.assertFalse((self.root / 'run/cron-systemd.empty-stopped').exists())
        self.assertEqual(self.actions()[-2:], ['reset-failed cron.service', '--no-block start cron.service'])

        # RC boot non-blocking restart/reload when openwrt-services.service is activating.
        self.clear_actions()
        self.assertEqual(
            self.run_script(CRON_FILES, 'cron-systemd', 'restart', RC_STATE='activating').returncode,
            0,
        )
        self.assertEqual(self.actions()[-1], '--no-block restart cron.service')
        self.assertEqual(
            self.run_script(CRON_FILES, 'cron-systemd', 'reload', RC_STATE='active').returncode,
            0,
        )
        self.assertEqual(self.actions()[-1], 'restart cron.service')

        self.assertEqual(
            self.run_script(CRON_FILES, 'cron-systemd', 'reconcile', ACTIVE='1').returncode,
            0,
        )
        self.assertEqual(self.actions()[-2:], [
            'reset-failed cron.service',
            '--no-block restart cron.service',
        ])

    def test_nlbwmon_run_reconcile_and_hotplug(self):
        self.native_mode()
        self.install_configs()
        done = self.run_script(NLBWMON_FILES, 'nlbwmon-systemd', 'run')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            self.actions()[-1],
            f'nlbwmon -o {self.root}/var/lib/nlbwmon -b 524288 -i 24h -r 30s '
            f'-p {self.root}/usr/share/nlbwmon/protocols -G 10 -I 1 -L 10000 -Z '
            f'-s 192.168.0.0/16 -s 192.0.2.1/24 -s fd00::1/64',
        )

        self.clear_actions()
        (self.root / 'usr/libexec/nlbwmon-systemd').write_text(
            self.script(NLBWMON_FILES, 'nlbwmon-systemd').read_text())
        (self.root / 'usr/libexec/nlbwmon-systemd').chmod(0o755)
        self.assertEqual(
            self.run_script(
                NLBWMON_FILES, 'nlbwmon.hotplug',
                ACTION='ifup', INTERFACE='wan', ACTIVE='1', MOCK_interface='lan',
            ).returncode,
            0,
        )
        self.assertEqual(self.actions(), ['is-active --quiet nlbwmon.service'])
        self.assertEqual(
            self.run_script(
                NLBWMON_FILES, 'nlbwmon.hotplug',
                ACTION='ifupdate', INTERFACE='lan', ACTIVE='1', MOCK_interface='lan',
            ).returncode,
            0,
        )
        self.assertEqual(self.actions()[-1], '--no-block start nlbwmon-reconfigure.service')

    def test_ddns_go_condition_prepare_run_and_reconcile(self):
        self.native_mode()
        self.install_configs()
        self.assertEqual(
            self.run_script(DDNS_GO_FILES, 'ddns-go-systemd', 'condition', MOCK_enabled='0').returncode,
            1,
        )
        self.assertEqual(
            self.run_script(DDNS_GO_FILES, 'ddns-go-systemd', 'reconcile', MOCK_enabled='0', ACTIVE='0').returncode,
            0,
        )
        self.assertEqual(self.actions(), ['is-active --quiet ddns-go.service'])

        self.assertEqual(
            self.run_script(DDNS_GO_FILES, 'ddns-go-systemd', 'reconcile', MOCK_enabled='0', ACTIVE='1').returncode,
            0,
        )
        self.assertEqual(self.actions()[-1], '--no-block stop ddns-go.service')

        self.clear_actions()
        self.assertEqual(
            self.run_script(DDNS_GO_FILES, 'ddns-go-systemd', 'reconcile', MOCK_enabled='1', ACTIVE='0').returncode,
            0,
        )
        self.assertEqual(self.actions(), [
            'reset-failed ddns-go.service',
            '--no-block restart ddns-go.service',
        ])

        self.clear_actions()
        self.assertEqual(
            self.run_script(DDNS_GO_FILES, 'ddns-go-systemd', 'prepare', MOCK_enabled='0').returncode,
            1,
        )
        self.assertEqual(
            self.run_script(
                DDNS_GO_FILES, 'ddns-go-systemd', 'prepare',
                MOCK_enabled='1', MOCK_port='9876', MOCK_time='300',
                MOCK_ctimes='5', MOCK_dns='223.5.5.5', MOCK_noweb='1', MOCK_skipverify='1',
            ).returncode,
            0,
        )
        self.assertEqual(self.actions(), [f'chown -R ddns-go:ddns-go {self.root}/etc/ddns-go'])
        self.assertTrue((self.root / 'run/ddns-go/env').is_file())

        done = self.run_script(DDNS_GO_FILES, 'ddns-go-systemd', 'run', MOCK_enabled='0')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(
            self.actions()[-1],
            f'ddns-go -c {self.root}/etc/ddns-go/ddns-go-config.yaml '
            f'-l :9876 -f 300 -cacheTimes 5 -dns 223.5.5.5 -noweb -skipVerify',
        )

    def test_native_init_adapters(self):
        self.install_configs()
        for name, directory, init_name, helper in (
            ('cron', CRON_FILES, 'cron-native.init', 'cron-systemd'),
            ('nlbwmon', NLBWMON_FILES, 'nlbwmon-native.init', 'nlbwmon-systemd'),
            ('ddns-go', DDNS_GO_FILES, 'ddns-go-native.init', 'ddns-go-systemd'),
        ):
            self.native_mode()
            self.clear_actions()
            self.write(f'usr/libexec/{helper}', '#!/bin/sh\necho "$*" >> "$TEST_ROOT/commands"\n')
            init = self.script(directory, init_name)
            for action in ('boot', 'shutdown', 'start', 'stop', 'reload', 'running', 'enable', 'enabled'):
                done = subprocess.run(
                    ['sh', str(init), action],
                    capture_output=True, text=True, env=self.env,
                )
                self.assertEqual(done.returncode, 0, f'{name} {action}: {done.stderr}')
            self.assertEqual(self.actions(), ['start', 'stop', 'reload', 'running', 'enable', 'enabled'])

    def test_offline_and_upgrade_package_hooks(self):
        (self.root / 'etc/rc.d').mkdir(parents=True, exist_ok=True)
        for name, directory, pkg, rc_link, units, wants in (
            ('cron', CRON_FILES, 'cron-package', 'S50cron', ('cron.service', 'cron-config.path'), (
                'multi-user.target.wants/cron.service',
                'multi-user.target.wants/cron-config.path',
            )),
            ('nlbwmon', NLBWMON_FILES, 'nlbwmon-package', 'S60nlbwmon', ('nlbwmon.service', 'nlbwmon-config.path'), (
                'multi-user.target.wants/nlbwmon.service',
                'multi-user.target.wants/nlbwmon-config.path',
            )),
            ('ddns-go', DDNS_GO_FILES, 'ddns-go-package', 'S99ddns-go', ('ddns-go.service', 'ddns-go-config.path'), (
                'multi-user.target.wants/ddns-go.service',
                'multi-user.target.wants/ddns-go-config.path',
            )),
        ):
            for upgrade in ('0', '1'):
                root = self.root / f'{name}-offline-{upgrade}'
                root.mkdir()
                done = subprocess.run(
                    ['sh', str(directory / pkg), 'postinst'],
                    env={**self.env, 'IPKG_INSTROOT': str(root), 'PKG_UPGRADE': upgrade},
                    capture_output=True, text=True,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                for rel in wants:
                    self.assertEqual((root / 'etc/systemd/system' / rel).is_symlink(), upgrade == '0')
                self.assertFalse((root / 'etc/systemd/openwrt-migrated' / name).exists())

            migrated_root = self.root / f'{name}-offline-migrated'
            (migrated_root / 'etc/init.d').mkdir(parents=True)
            (migrated_root / 'etc/rc.d').mkdir(parents=True)
            init_target = migrated_root / 'etc/init.d' / name
            init_target.write_text('#!/bin/sh\n')
            init_target.chmod(0o755)
            (migrated_root / 'etc/rc.d' / rc_link).symlink_to(f'../init.d/{name}')
            done = subprocess.run(
                ['sh', str(directory / pkg), 'postinst'],
                env={**self.env, 'IPKG_INSTROOT': str(migrated_root), 'PKG_UPGRADE': '1'},
                capture_output=True, text=True,
            )
            self.assertEqual(done.returncode, 0, done.stderr)
            for rel in wants:
                self.assertFalse((migrated_root / 'etc/systemd/system' / rel).is_symlink())
        self.assertEqual(self.actions(), [])

        self.native_mode()
        for name, directory, pkg, rc_link, units in (
            ('cron', CRON_FILES, 'cron-package', 'S50cron', ('cron.service', 'cron-config.path')),
            ('nlbwmon', NLBWMON_FILES, 'nlbwmon-package', 'S60nlbwmon', ('nlbwmon.service', 'nlbwmon-config.path')),
            ('ddns-go', DDNS_GO_FILES, 'ddns-go-package', 'S99ddns-go', ('ddns-go.service', 'ddns-go-config.path')),
        ):
            self.clear_actions()
            self.assertEqual(self.run_script(directory, pkg, 'postinst', PKG_UPGRADE='1').returncode, 0)
            self.assertEqual(self.actions(), ['daemon-reload', f'try-restart {units[0]}'])

    def test_unit_properties_and_slice_placement(self):
        self.assertIn('CPUWeight=100', SLICE_FILE.read_text())

        cron_unit = (CRON_FILES / 'cron.service').read_text()
        self.assertIn('Slice=auxiliary.slice', cron_unit)
        self.assertIn('After=openwrt-services.service', cron_unit)
        self.assertIn('Also=cron-config.path', cron_unit)
        self.assertIn('StartLimitIntervalSec=0', (CRON_FILES / 'cron-reconfigure.service').read_text())

        nlbwmon_unit = (NLBWMON_FILES / 'nlbwmon.service').read_text()
        self.assertIn('Slice=auxiliary.slice', nlbwmon_unit)
        self.assertIn('Nice=19', nlbwmon_unit)
        self.assertIn('After=network-online.target', nlbwmon_unit)
        self.assertNotIn('openwrt-services.service', nlbwmon_unit)
        self.assertIn('StartLimitIntervalSec=0', (NLBWMON_FILES / 'nlbwmon-reconfigure.service').read_text())

        ddns_unit = (DDNS_GO_FILES / 'ddns-go.service').read_text()
        self.assertIn('Slice=auxiliary.slice', ddns_unit)
        self.assertIn('User=ddns-go', ddns_unit)
        self.assertIn('ExecCondition=+/usr/libexec/ddns-go-systemd condition', ddns_unit)
        self.assertIn('ExecStartPre=+/usr/libexec/ddns-go-systemd prepare', ddns_unit)
        self.assertIn('After=network-online.target', ddns_unit)
        self.assertNotIn('openwrt-services.service', ddns_unit)
        self.assertIn('StartLimitIntervalSec=0', (DDNS_GO_FILES / 'ddns-go-reconfigure.service').read_text())


if __name__ == '__main__':
    unittest.main()
