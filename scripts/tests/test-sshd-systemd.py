#!/usr/bin/env python3
"""Execute SSH integration scripts in an isolated filesystem with fake daemons."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


TREE = Path(__file__).resolve().parents[2]
OPENSSH = TREE / 'feeds/packages/net/openssh/files'
LUCI = TREE / 'feeds/luci/modules/luci-mod-system'


class SshdTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='sshd-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        for name in ('etc/ssh/sshd_config.d', 'etc/init.d', 'etc/systemd/system',
                     'usr/bin', 'usr/sbin', 'usr/libexec', 'usr/lib/systemd/system',
                     'var/lock', 'root/.ssh', 'bin'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        self.log = self.root / 'commands'
        self.env = {**os.environ, 'PATH': str(self.root / 'bin') + ':' + os.environ['PATH'],
                    'IPKG_INSTROOT': '', 'PKG_UPGRADE': '0'}
        self.write_executable('bin/systemctl', '''#!/bin/sh
printf '%s\\n' "$*" >> "$TEST_ROOT/commands"
case "$1" in
show) cat "$TEST_ROOT/state" ;;
reload)
 if [ -f "$TEST_ROOT/fail-reload" ]; then
  rm "$TEST_ROOT/fail-reload"
  exit 1
 fi ;;
esac
''')
        self.write_executable('usr/sbin/sshd', '''#!/bin/sh
case "$1" in
-t) ! grep -q INVALID "$TEST_ROOT/etc/ssh/sshd_config.d/00-openwrt-access.conf" ;;
-T) echo 'port 22' ;;
*) exit 1 ;;
esac
''')
        self.write_executable('etc/init.d/sshd', '''#!/bin/sh
echo "procd $*" >> "$TEST_ROOT/commands"
''')
        self.env['TEST_ROOT'] = str(self.root)
        (self.root / 'state').write_text('active\n')
        self.config = self.root / 'etc/ssh/sshd_config.d/00-openwrt-access.conf'
        self.original = '# retain this comment\nPort 22\nPasswordAuthentication yes\n'
        self.config.write_text(self.original)
        (self.root / 'root/.ssh/authorized_keys').write_text('test-key\n')

    def write_executable(self, name, text):
        path = self.root / name
        path.write_text(text)
        path.chmod(0o755)
        return path

    def script(self, source):
        # Redirect absolute target paths; execute the original shell logic.
        text = source.read_text()
        for prefix in ('/usr/', '/etc/', '/var/', '/run/', '/root/'):
            text = text.replace(prefix, str(self.root) + prefix)
        return self.write_executable('bin/' + source.name, text)

    def run_script(self, source, *args, **env):
        return subprocess.run(['sh', str(self.script(source)), *args], text=True,
                              capture_output=True, env={**self.env, **env}, timeout=15)

    def native(self):
        (self.root / 'run/systemd/system').mkdir(parents=True)
        (self.root / 'usr/lib/systemd/system/sshd.service').touch()

    def actions(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def save(self, port='2222'):
        return self.run_script(LUCI / 'root/usr/libexec/luci-openssh',
                               'save', port, 'yes', 'yes', 'yes', 'no')

    def test_backend_requires_native_manager_and_unit(self):
        helper = LUCI / 'root/usr/libexec/luci-openssh'
        self.assertEqual(self.run_script(helper, 'backend').stdout.strip(), 'procd')
        (self.root / 'usr/lib/systemd/system/sshd.service').touch()
        self.assertEqual(self.run_script(helper, 'backend').stdout.strip(), 'procd')
        self.native()
        self.assertEqual(self.run_script(helper, 'backend').stdout.strip(), 'systemd')
        self.assertNotEqual(self.run_script(helper, 'backend', 'extra').returncode, 0)

    def test_luci_native_reload_and_recovery_reload(self):
        self.assertEqual(self.save().returncode, 0)
        self.assertEqual(self.actions(), ['procd reload'])
        self.log.unlink()
        self.native()
        self.assertEqual(self.save('2223').returncode, 0)
        self.assertEqual(self.actions(), ['show -p ActiveState --value sshd.service',
                                         'reload sshd.service'])
        self.assertIn('# retain this comment', self.config.read_text())

    def test_luci_save_does_not_start_inactive_or_failed_listener(self):
        self.native()
        for state in ('inactive', 'failed'):
            with self.subTest(state=state):
                (self.root / 'state').write_text(state + '\n')
                self.assertEqual(self.save().returncode, 0)
        self.assertTrue(all(a.startswith('show ') for a in self.actions()))

    def test_luci_reload_failure_restores_original_config(self):
        self.native()
        (self.root / 'fail-reload').touch()
        self.assertNotEqual(self.save().returncode, 0)
        self.assertEqual(self.config.read_text(), self.original)
        self.assertEqual(self.actions().count('reload sshd.service'), 2)
        self.assertFalse(list(self.config.parent.glob('*.luci-*')))

    def test_luci_invalid_config_does_not_signal_listener(self):
        self.native()
        self.config.write_text(self.original + 'INVALID\n')
        self.assertNotEqual(self.save().returncode, 0)
        self.assertEqual(self.config.read_text(), self.original + 'INVALID\n')
        self.assertEqual(self.actions(), [])

    def test_luci_transitional_state_rolls_back(self):
        self.native()
        (self.root / 'state').write_text('activating\n')
        self.assertNotEqual(self.save().returncode, 0)
        self.assertEqual(self.config.read_text(), self.original)
        self.assertNotIn('reload sshd.service', self.actions())

    def test_native_init_rejects_runtime_actions(self):
        self.native()
        script = self.script(OPENSSH / 'sshd.init')
        for action in ('boot', 'shutdown', 'start', 'stop', 'restart', 'reload', 'status', 'running'):
            done = subprocess.run(['sh', '-c', 'action=$1; . "$2"', 'test', action, str(script)],
                                  env=self.env, capture_output=True, text=True)
            self.assertNotEqual(done.returncode, 0, action)
            self.assertIn('systemctl', done.stderr)
        for action in ('enable', 'disable', 'enabled'):
            done = subprocess.run(['sh', '-c', 'action=$1; . "$2"', 'test', action, str(script)],
                                  env=self.env, capture_output=True, text=True)
            self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.actions(), [])

    def test_rc_queue_skips_ssh_only_when_native_unit_is_installed(self):
        rc = self.root / 'etc/rc.d'
        rc.mkdir()
        (self.root / 'usr/bin/timeout').symlink_to(shutil.which('timeout'))
        self.write_executable('usr/libexec/openwrt-cgroup', '#!/bin/sh\nshift 2\nexec "$@"\n')
        self.write_executable('etc/init.d/sample', '#!/bin/sh\necho "sample $1" >> "$TEST_ROOT/commands"\n')
        for prefix in ('S50', 'K50'):
            (rc / (prefix + 'sshd')).symlink_to('../init.d/sshd')
            (rc / (prefix + 'sample')).symlink_to('../init.d/sample')
        source = TREE / 'package/system/systemd-openwrt/files/openwrt-rcS'
        for action in ('boot', 'shutdown'):
            self.assertEqual(self.run_script(source, action).returncode, 0)
        self.assertEqual(self.actions(), ['sample boot', 'procd boot', 'sample shutdown', 'procd shutdown'])
        self.log.unlink()
        self.native()
        for action in ('boot', 'shutdown'):
            self.assertEqual(self.run_script(source, action).returncode, 0)
        self.assertEqual(self.actions(), ['sample boot', 'sample shutdown'])

    def test_recovery_init_retains_procd_implementation(self):
        script = self.script(OPENSSH / 'sshd.init')
        done = subprocess.run(['sh', '-c', 'action=start; . "$1"; test "$USE_PROCD" = 1; '
                               'command -v start_service; command -v shutdown', 'test', str(script)],
                              env=self.env, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)

    def test_offline_install_enables_only_native_link_without_host_systemctl(self):
        root = self.root
        wants = root / 'etc/systemd/system/multi-user.target.wants/sshd.service'
        done = subprocess.run(['sh', str(OPENSSH / 'sshd-systemd'), 'postinst'],
                              env={**self.env, 'IPKG_INSTROOT': str(root)}, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(os.readlink(wants), '/usr/lib/systemd/system/sshd.service')
        wants.unlink()
        done = subprocess.run(['sh', str(OPENSSH / 'sshd-systemd'), 'postinst'],
                              env={**self.env, 'IPKG_INSTROOT': str(root), 'PKG_UPGRADE': '1'},
                              capture_output=True)
        self.assertEqual(done.returncode, 0)
        self.assertFalse(wants.is_symlink())
        self.assertEqual(self.actions(), [])

    def test_online_upgrade_preserves_enablement_and_uses_only_try_restart(self):
        self.native()
        done = self.run_script(OPENSSH / 'sshd-systemd', 'postinst', PKG_UPGRADE='1')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.actions(), ['daemon-reload', 'try-restart sshd.service'])

    def test_package_install_preserves_native_mask(self):
        self.native()
        (self.root / 'etc/systemd/system/sshd.service').symlink_to('/dev/null')
        done = self.run_script(OPENSSH / 'sshd-systemd', 'postinst')
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.actions(), ['daemon-reload'])
        self.log.unlink()
        done = subprocess.run(['sh', str(OPENSSH / 'sshd-systemd'), 'postinst'],
                              env={**self.env, 'IPKG_INSTROOT': str(self.root)}, capture_output=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertFalse((self.root / 'etc/systemd/system/multi-user.target.wants').exists())
        self.assertEqual(self.actions(), [])

    def test_recovery_package_hooks_do_not_contact_systemd(self):
        for action in ('postinst', 'prerm'):
            self.assertEqual(self.run_script(OPENSSH / 'sshd-systemd', action).returncode, 0)
        self.assertEqual(self.actions(), [])

    def test_native_package_removal_stops_listener(self):
        self.native()
        self.assertEqual(self.run_script(OPENSSH / 'sshd-systemd', 'prerm').returncode, 0)
        self.assertEqual(self.actions(), ['stop sshd.service', 'disable sshd.service'])

    def test_prepare_preserves_existing_and_invalid_keys(self):
        self.write_executable('bin/chown', '#!/bin/sh\nexit 0\n')
        keygen = shutil.which('ssh-keygen')
        if not keygen:
            self.skipTest('ssh-keygen is required')
        (self.root / 'usr/bin/ssh-keygen').symlink_to(keygen)
        prepare = OPENSSH / 'sshd-prepare'
        done = self.run_script(prepare)
        self.assertEqual(done.returncode, 0, done.stderr)
        keys = {p: p.read_bytes() for p in (self.root / 'etc/ssh').glob('ssh_host_*')}
        self.assertEqual(self.run_script(prepare).returncode, 0)
        self.assertEqual(keys, {p: p.read_bytes() for p in keys})
        invalid = self.root / 'etc/ssh/ssh_host_rsa_key'
        invalid.write_text('invalid private key\n')
        self.assertNotEqual(self.run_script(prepare).returncode, 0)
        self.assertEqual(invalid.read_text(), 'invalid private key\n')

    def test_startup_acl_has_only_fixed_backend_command(self):
        acl = json.loads((LUCI / 'root/usr/share/rpcd/acl.d/luci-mod-system.json').read_text())
        read = acl['luci-mod-system-init']['read']
        self.assertEqual([k for k, v in read['file'].items() if 'exec' in v],
                         ['/usr/libexec/luci-openssh backend'])
        self.assertIn('exec', read['ubus']['file'])


if __name__ == '__main__':
    unittest.main()
