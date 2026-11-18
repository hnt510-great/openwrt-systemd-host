#!/usr/bin/env python3
"""Exercise native Samba adapters without starting Samba or contacting a manager."""
import os
import re
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
FILES = TREE / 'feeds/packages/net/samba4/files'


class SambaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='samba4-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.env = {**os.environ, 'TEST_ROOT': str(self.root), 'IPKG_INSTROOT': '',
                    'PATH': str(self.root / 'bin') + ':' + os.environ['PATH']}
        for name in ('bin', 'lib', 'usr/libexec', 'usr/sbin', 'usr/bin',
                     'usr/lib/systemd/system', 'etc/samba', 'etc/systemd/system', 'var/etc'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.write('lib/functions.sh', '''config_load() { :; }
config_foreach() { "$1" samba; }
config_get_bool() { eval "$1=\\${$3:-$4}"; }
config_get() { eval "$1=\\${$3:-$4}"; }
''')
        self.write('usr/libexec/samba4-config.sh', '''init_config() {
 printf '%s\\n' "${CONFIG_TEXT:-valid}" > "$SAMBA_CONFIG_OUTPUT"
 [ -e "$TEST_ROOT/etc/samba/smb.conf" ] || ln -s "$TEST_ROOT/var/etc/smb.conf" "$TEST_ROOT/etc/samba/smb.conf"
}
''')
        self.write('usr/bin/testparm', '#!/bin/sh\n! grep -q INVALID "$2"\n')
        self.write('bin/systemctl', '''#!/bin/sh
printf '%s\\n' "$*" >> "$TEST_ROOT/commands"
if [ "$1" = is-active ]; then test "${ACTIVE:-1}" = 1; fi
''')
        self.write('bin/nice', '#!/bin/sh\nshift 2\nexec "$@"\n')
        for name in ('smbd', 'nmbd', 'samba', 'winbindd'):
            self.write('usr/sbin/' + name, '#!/bin/sh\necho "daemon $0 $*" >> "$TEST_ROOT/commands"\n')
        (self.root / 'etc/samba/smb.conf').symlink_to(self.root / 'var/etc/smb.conf')
        (self.root / 'var/etc/smb.conf').write_text('original\n')

    def write(self, name, text):
        path = self.root / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def script(self, name):
        source = (FILES / name).read_text()
        source = re.sub(r'/(?:usr|etc|var|run|lib)/',
                        lambda match: str(self.root) + match[0], source)
        return self.write('bin/' + name, source)

    def run_script(self, name, *args, **env):
        return subprocess.run(['sh', str(self.script(name)), *args], text=True,
                              capture_output=True, env={**self.env, **env}, timeout=10)

    def actions(self):
        path = self.root / 'commands'
        return path.read_text().splitlines() if path.exists() else []

    def native(self):
        (self.root / 'run/systemd/system').mkdir(parents=True)
        (self.root / 'usr/lib/systemd/system/samba4.service').touch()

    def test_mode_selection(self):
        for role, expected in (('samba', 0), ('smbd', 1), ('nmbd', 1), ('winbindd', 1)):
            self.assertEqual(self.run_script('samba4-systemd', 'condition', role).returncode, expected)
        for role, expected in (('samba', 1), ('smbd', 0), ('nmbd', 0), ('winbindd', 0)):
            self.assertEqual(self.run_script('samba4-systemd', 'condition', role,
                                            disable_ad_dc='1').returncode, expected)
        for role in ('nmbd', 'winbindd'):
            self.assertEqual(self.run_script('samba4-systemd', 'condition', role,
                                            disable_ad_dc='1', disable_netbios='1',
                                            disable_winbind='1').returncode, 1)

    def test_missing_optional_binary_is_skipped(self):
        (self.root / 'usr/sbin/nmbd').unlink()
        (self.root / 'usr/sbin/samba').unlink()
        self.assertEqual(self.run_script('samba4-systemd', 'condition', 'nmbd').returncode, 1)
        self.assertEqual(self.run_script('samba4-systemd', 'condition', 'smbd').returncode, 0)

    def test_prepare_atomically_replaces_valid_config(self):
        done = self.run_script('samba4-systemd', 'prepare')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual((self.root / 'var/etc/smb.conf').read_text(), 'valid\n')
        self.assertFalse(list((self.root / 'var/etc').glob('*.new.*')))

    def test_invalid_generated_config_keeps_previous(self):
        done = self.run_script('samba4-systemd', 'prepare', CONFIG_TEXT='INVALID')
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual((self.root / 'var/etc/smb.conf').read_text(), 'original\n')
        self.assertFalse(list((self.root / 'var/etc').glob('*.new.*')))
        self.assertEqual(self.actions(), [])

    def test_custom_config_is_preserved_and_validated(self):
        config = self.root / 'etc/samba/smb.conf'
        config.unlink()
        config.write_text('custom\n')
        self.assertEqual(self.run_script('samba4-systemd', 'prepare').returncode, 0)
        self.assertEqual(config.read_text(), 'custom\n')
        config.write_text('INVALID\n')
        self.assertNotEqual(self.run_script('samba4-systemd', 'prepare').returncode, 0)
        self.assertEqual(config.read_text(), 'INVALID\n')

    def test_reload_does_not_start_inactive_group(self):
        self.assertEqual(self.run_script('samba4-systemd', 'reload', ACTIVE='0').returncode, 0)
        self.assertEqual(self.actions(), ['is-active --quiet samba4.service'])

    def test_active_reload_and_reconcile(self):
        self.assertEqual(self.run_script('samba4-systemd', 'reload').returncode, 0)
        self.assertEqual(self.actions()[-1], 'reload samba4.service')
        self.assertEqual(self.run_script('samba4-systemd', 'reconcile').returncode, 0)
        self.assertTrue(self.actions()[-2].startswith('reset-failed samba4@smbd.service'))
        self.assertTrue(self.actions()[-1].startswith('--no-block restart samba4@smbd.service'))
        self.assertIn('StartLimitIntervalSec=0', (FILES / 'samba4-reconfigure.service').read_text())

    def test_foreground_exec_and_invalid_role(self):
        done = self.run_script('samba4-systemd', 'run', 'smbd', samba_nice='3')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn('smbd -F --no-process-group', self.actions()[-1])
        self.assertNotEqual(self.run_script('samba4-systemd', 'run', '../bad').returncode, 0)

    def test_native_init_never_registers_procd_or_starts_during_rc_boot(self):
        self.native()
        self.script('samba4-systemd')
        (self.root / 'usr/libexec/samba4-systemd').write_text('#!/bin/sh\necho "$*" >> "$TEST_ROOT/commands"\n')
        (self.root / 'usr/libexec/samba4-systemd').chmod(0o755)
        init = self.script('samba.init')
        for action in ('boot', 'shutdown', 'start', 'stop', 'reload', 'enable', 'enabled'):
            done = subprocess.run(['sh', '-c', 'action=$1; script=$2; shift 2; . "$script"', 'test', action, str(init)],
                                  capture_output=True, text=True, env=self.env)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.actions(), ['start', 'stop', 'reload', 'enable', 'enabled'])

    def test_recovery_retains_procd(self):
        init = self.script('samba.init')
        done = subprocess.run(['sh', '-c', '. "$1"; test "$USE_PROCD" = 1; '
                               'command -v start_service; command -v service_triggers', 'test', str(init)],
                              capture_output=True, text=True, env=self.env)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.actions(), [])

    def test_offline_install_and_upgrade(self):
        for upgrade in ('0', '1'):
            root = self.root / ('offline-' + upgrade)
            root.mkdir()
            done = subprocess.run(['sh', str(FILES / 'samba4-package'), 'postinst'],
                                  env={**self.env, 'IPKG_INSTROOT': str(root), 'PKG_UPGRADE': upgrade},
                                  capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
            link = root / 'etc/systemd/system/multi-user.target.wants/samba4.service'
            self.assertEqual(link.is_symlink(), upgrade == '0')
        self.assertEqual(self.actions(), [])

    def test_online_upgrade_does_not_start_inactive_native_units(self):
        self.native()
        (self.root / 'etc/rc.d').mkdir(parents=True, exist_ok=True)
        (self.root / 'etc/rc.d/S98samba4').symlink_to('../init.d/samba4')
        self.assertEqual(self.run_script('samba4-package', 'postinst', PKG_UPGRADE='1').returncode, 0)
        self.assertEqual(self.actions(), [
            'daemon-reload', 'enable samba4.service samba4-config.path', 'try-restart samba4.service',
        ])
        self.assertTrue((self.root / 'etc/systemd/openwrt-migrated/samba4').is_file())

        (self.root / 'commands').unlink()
        self.assertEqual(self.run_script('samba4-package', 'postinst', PKG_UPGRADE='1').returncode, 0)
        self.assertEqual(self.actions(), ['daemon-reload', 'try-restart samba4.service'])

    def test_hotplug_ignores_unselected_networks(self):
        self.native()
        (self.root / 'usr/libexec/samba4-systemd').symlink_to(self.script('samba4-systemd'))
        for name in ('wan', 'wan6'):
            self.assertEqual(self.run_script('samba4.hotplug', ACTION='ifup', INTERFACE=name).returncode, 0)
        self.assertEqual(self.actions(), [])
        self.assertEqual(self.run_script('samba4.hotplug', ACTION='ifupdate', INTERFACE='lan').returncode, 0)
        self.assertEqual(self.actions(), ['--no-block start samba4-reconfigure.service'])
        self.assertEqual(self.run_script('samba4-systemd', 'interface', 'storage', interface='lan storage').returncode, 0)

    def test_unit_ownership_and_reload_validation_order(self):
        unit = (FILES / 'samba4@.service').read_text()
        self.assertIn('Slice=nas.slice', unit)
        self.assertIn('PartOf=samba4.service', unit)
        self.assertIn('KillMode=control-group', unit)
        group = (FILES / 'samba4.service').read_text()
        self.assertLess(group.index('ExecReload=/usr/libexec/samba4-systemd prepare'),
                        group.index('ExecReload=/usr/libexec/samba4-systemd reconcile'))
        self.assertIn('CPUWeight=100', (FILES / 'nas.slice').read_text())
        self.assertIn('After=network-online.target', group)
        self.assertNotIn('After=openwrt-services.service', group)
        self.assertNotIn('After=openwrt-services.service', (FILES / 'samba4-config.path').read_text())


if __name__ == '__main__':
    unittest.main()
