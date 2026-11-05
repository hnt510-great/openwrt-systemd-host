#!/usr/bin/env python3
"""Exercise the wizard account/permission boundary in an isolated filesystem."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
PACKAGE = ROOT / 'package/custom/luci-app-desktop-setup'
PLUGIN = PACKAGE / 'root/usr/libexec/rpcd/luci.desktop-setup'
sys.dont_write_bytecode = True
loader = importlib.machinery.SourceFileLoader('desktop_setup', str(PLUGIN))
spec = importlib.util.spec_from_loader(loader.name, loader)
M = importlib.util.module_from_spec(spec)
loader.exec_module(M)


class FakeBackend(M.Backend):
    def __init__(self, root):
        super().__init__(root)
        self.calls = []
        self.settings = {}
        self.failure = None
        self.delay = 0
        self.native = True
        self.lan = '192.0.2.1'
        self.available = {key: True for key in M.HELPERS}
        for folder in ['etc', 'home', 'bin']:
            self.path(folder).mkdir(exist_ok=True)
        self.path('/bin/sh').write_text('#!/bin/sh\n')
        self.path('/bin/sh').chmod(0o755)
        self.path('/etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\n')
        self.path('/etc/shadow').write_text('root:$6$root:1:0:99999:7:::\n')

    def add_account(self, name='alice', uid=1000, gid=1000, password='$6$fixture', shell='/bin/sh'):
        self.path('/home/' + name).mkdir(exist_ok=True)
        with self.path('/etc/passwd').open('a') as stream:
            stream.write(f'{name}:x:{uid}:{gid}::/home/{name}:{shell}\n')
        with self.path('/etc/shadow').open('a') as stream:
            stream.write(f'{name}:{password}:1:0:99999:7:::\n')

    def platform(self):
        return {'native': self.native, 'lan_address': self.lan, 'available': self.available}

    def capture(self, args):
        return self.settings.get('manager_pid', '')

    def uci(self, key):
        return self.settings.get(key, '')

    def command(self, args, secret=None, timeout=120, check=True):
        self.calls.append((args, secret))
        if self.delay:
            time.sleep(self.delay)
        if self.failure and self.failure in args:
            raise M.SetupError('helper_failed')
        if args[0].endswith('/useradd'):
            self.add_account(args[-1], password='!')
        if args[0].endswith('/chpasswd'):
            name = secret.split(':', 1)[0]
            lines = self.path('/etc/shadow').read_text().splitlines()
            self.path('/etc/shadow').write_text('\n'.join(
                name + ':$6$changed:1:0:99999:7:::' if line.startswith(name + ':') else line for line in lines) + '\n')
        if args[0] == M.HELPERS['desktop']:
            self.settings['desktop.main.user'] = args[1]
        if args[0] == M.HELPERS['rdp']:
            self.settings['desktop.main.rdp_enabled'] = '1'
        return 0


class WizardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='desktop-setup-test-')
        self.addCleanup(self.temp.cleanup)
        self.backend = FakeBackend(Path(self.temp.name))

    def request(self, **overrides):
        value = dict(username='alice', mode='create', password='unix-password-fixture',
                     rdp_password='rdp-password-fixture', keyring_password='',
                     capture='portal', confirm_restart=True, **{key: True for key in M.FEATURES})
        value.update(overrides)
        return value

    def execute(self, **overrides):
        plan = self.backend.validate(self.request(**overrides))
        job = {'status': 'running', 'username': plan['username'], 'steps': []}
        self.backend.execute(plan, job)
        return self.backend.read(self.backend.runtime / 'job.json')

    def reject(self, code, **overrides):
        with self.assertRaisesRegex(M.SetupError, '^' + code + '$'):
            self.backend.validate(self.request(**overrides))
        self.assertEqual(self.backend.calls, [])

    def test_rpc_schema_and_acl(self):
        schema = json.loads(subprocess.check_output([str(PLUGIN), 'list'], text=True))
        self.assertEqual(set(schema), {'status', 'apply', 'defer'})
        self.assertIs(schema['apply']['rdp'], True)
        self.assertEqual(schema['apply']['password'], '')
        acl = json.loads((PACKAGE / 'root/usr/share/rpcd/acl.d/luci-app-desktop-setup.json').read_text())['luci-app-desktop-setup']
        self.assertEqual(acl['read'], {'ubus': {'luci.desktop-setup': ['status']}})
        self.assertEqual(acl['write'], {'ubus': {'luci.desktop-setup': ['apply', 'defer']}})

    def test_complete_new_enrollment(self):
        job = self.execute()
        self.assertEqual(job['status'], 'done')
        self.assertTrue(self.backend.state()['completed'])
        args = [a for a, _ in self.backend.calls]
        self.assertIn(['/usr/sbin/useradd', '-m', '-U', 'alice'], args)
        self.assertIn([M.HELPERS['desktop'], 'alice', '--keyring-password-stdin'], args)
        self.assertIn([M.HELPERS['rdp'], 'alice', '--password-stdin'], args)
        self.assertLess(args.index([M.HELPERS['virtual_machines'], 'alice']), args.index([M.HELPERS['desktop'], 'alice', '--keyring-password-stdin']))
        self.assertIn([M.HELPERS['moonlight'], 'alice', '--capture=portal'], args)
        for key in ('containers', 'flatpak', 'virtual_machines'):
            self.assertIn([M.HELPERS[key], 'alice'], args)
        self.assertIn(['/sbin/uci', '-q', 'del_list', 'luci_podman.main.users=alice'], args)
        self.assertIn(['/sbin/uci', 'add_list', 'luci_podman.main.users=alice'], args)
        self.assertFalse(any('sudo' in arg for call in args for arg in call))

    def test_passwords_only_on_stdin_and_never_in_state(self):
        self.execute()
        for args, _ in self.backend.calls:
            self.assertNotIn('unix-password-fixture', ' '.join(args))
            self.assertNotIn('rdp-password-fixture', ' '.join(args))
        for filename in self.backend.root.rglob('*'):
            if filename.is_file():
                self.assertNotIn('unix-password-fixture', filename.read_text())
                self.assertNotIn('rdp-password-fixture', filename.read_text())
        self.assertIn((['/usr/sbin/chpasswd', '-c', 'SHA512'], 'alice:unix-password-fixture\n'), self.backend.calls)

    def test_reject_injection_and_root_before_any_command(self):
        for name in ['root\n', 'root', '-alice', 'alice;reboot', '$(id)', 'a' * 33, 'alice\x00', 'Alice']:
            with self.subTest(name=name):
                code = 'account_exists' if name == 'root' else 'invalid_username'
                self.reject(code, username=name)
        self.reject('invalid_request', containers='true')
        self.reject('invalid_request', capture='portal; reboot')
        self.reject('restart_confirmation_required', confirm_restart=False)
        self.reject('invalid_password', password='hello\nworld-unsafe')
        self.reject('password_too_short', password='short')
        self.reject('invalid_request', executable='/bin/sh')

    def test_preconditions_do_not_create_accounts(self):
        self.backend.native = False
        self.reject('native_systemd_required')
        self.backend.native = True
        self.backend.lan = ''
        self.reject('lan_required')
        self.backend.lan = '192.0.2.1'
        self.backend.available['flatpak'] = False
        self.reject('missing_package')

    def test_existing_password_and_data_preserved(self):
        self.backend.add_account()
        marker = self.backend.path('/home/alice/important.txt')
        marker.write_text('personal data')
        before = self.backend.path('/etc/shadow').read_bytes()
        self.execute(mode='existing', password='')
        self.assertEqual(self.backend.path('/etc/shadow').read_bytes(), before)
        self.assertEqual(marker.read_text(), 'personal data')
        self.assertFalse(any(a[0].endswith(('/useradd', '/chpasswd')) for a, _ in self.backend.calls))
        self.backend.calls.clear()
        self.reject('existing_password_preserved', mode='existing')

    def test_ordinary_account_filter(self):
        self.backend.add_account('service', uid=999)
        self.backend.add_account('rootgroup', gid=0)
        self.backend.add_account('locked', password='!')
        self.backend.add_account('nologin', shell='/bin/nologin')
        self.backend.add_account()
        self.assertEqual([a['username'] for a in self.backend.accounts()], ['alice'])
        self.reject('invalid_existing_account', mode='existing', username='root', password='')

    def test_existing_rdp_credentials_can_be_retained_only_for_same_user(self):
        self.backend.add_account()
        self.backend.settings.update({'desktop.main.user': 'alice', 'desktop.main.rdp_enabled': '1'})
        job = self.execute(mode='existing', password='', rdp_password='')
        self.assertEqual(job['status'], 'done')
        self.assertFalse(any(a[0] == M.HELPERS['rdp'] for a, _ in self.backend.calls))
        self.backend.calls.clear()
        self.backend.settings['desktop.main.user'] = 'someone_else'
        self.reject('rdp_password_required', mode='existing', password='', rdp_password='')

    def test_existing_keyring_passphrase_transport(self):
        self.backend.add_account()
        folder = self.backend.path('/home/alice/.local/share/keyrings')
        folder.mkdir(parents=True)
        (folder / 'login.keyring').write_text('existing encrypted keyring')
        self.reject('keyring_password_required', mode='existing', password='')
        job = self.execute(mode='existing', password='', keyring_password='old keyring secret')
        self.assertEqual(job['status'], 'done')
        self.assertIn(([M.HELPERS['desktop'], 'alice', '--keyring-password-stdin'], 'old keyring secret\n'), self.backend.calls)
        self.assertNotIn('old keyring secret', json.dumps(self.backend.state()))

    def test_failure_retains_progress_and_locked_account_can_resume(self):
        self.backend.failure = '/usr/sbin/chpasswd'
        job = self.execute()
        self.assertEqual(job['status'], 'failed')
        self.assertEqual(job['steps'][0], {'id': 'account', 'status': 'done'})
        self.assertFalse(self.backend.state().get('completed', False))
        account = self.backend.accounts()[0]
        self.assertTrue(account['recoverable'])
        self.backend.failure = None
        self.backend.calls.clear()
        self.assertEqual(self.execute(mode='existing')['status'], 'done')
        self.assertFalse(any(a[0].endswith('/useradd') for a, _ in self.backend.calls))

    def test_unchecked_features_are_not_revoked(self):
        self.assertEqual(self.execute(**{key: False for key in M.FEATURES})['status'], 'done')
        args = [a for a, _ in self.backend.calls]
        for key in M.FEATURES:
            self.assertFalse(any(call[0] == M.HELPERS[key] for call in args))
        self.assertFalse(any('disable' in call or 'revoke' in call for call in args))

    def test_rdp_only_audio_and_kms_mode(self):
        self.execute(moonlight=False)
        self.assertIn((['/usr/sbin/desktop-audio-setup', 'alice'], None), self.backend.calls)
        self.backend.calls.clear()
        self.assertEqual(self.execute(mode='existing', password='', capture='kms')['status'], 'done')
        self.assertIn(([M.HELPERS['moonlight'], 'alice', '--enable-kms'], None), self.backend.calls)

    def test_lock_and_async_worker(self):
        self.backend.delay = .03
        self.assertTrue(self.backend.submit(self.request())['accepted'])
        with self.assertRaisesRegex(M.SetupError, '^busy$'):
            self.backend.defer()
        _, status = os.waitpid(-1, 0)
        self.assertEqual(status, 0)
        self.assertEqual(self.backend.read(self.backend.runtime / 'job.json')['status'], 'done')
        self.assertTrue(self.backend.state()['completed'])

    def test_first_visit_defer_completion_and_interruption(self):
        self.assertTrue(self.backend.status()['automatic'])
        self.backend.defer()
        self.assertFalse(self.backend.status()['automatic'])
        self.assertTrue(M.Backend(self.backend.root).state()['deferred'])
        self.assertEqual(self.backend.calls, [])
        self.backend.write(self.backend.runtime / 'job.json', {'status': 'running', 'username': 'alice'})
        self.assertEqual(self.backend.status()['job']['status'], 'interrupted')
        self.execute()
        self.assertFalse(self.backend.status()['automatic'])

    def test_status_exposes_only_the_public_certificate_fingerprint(self):
        self.backend.add_account()
        self.backend.settings['desktop.main.user'] = 'alice'
        certificate = self.backend.path('/etc/desktop/tls/alice.crt')
        certificate.parent.mkdir(parents=True)
        certificate.write_text('public certificate fixture')
        fingerprint = ':'.join(['AB'] * 32)
        self.backend.capture = lambda args: 'sha256 Fingerprint=' + fingerprint if args[0].endswith('/openssl') else ''
        result = self.backend.status()
        self.assertEqual(result['rdp_fingerprint'], fingerprint)
        self.assertNotIn('$6$fixture', json.dumps(result))
        self.backend.capture = lambda args: 'unexpected private-looking output'
        self.assertEqual(self.backend.status()['rdp_fingerprint'], '')

    def test_completion_between_poll_and_lock_is_not_reported_as_interrupted(self):
        self.backend.write(self.backend.runtime / 'job.json', {'status': 'running', 'username': 'alice'})
        original = self.backend.lock
        def finish_before_status_lock():
            fd = original()
            self.backend.write(self.backend.runtime / 'job.json', {'status': 'done', 'username': 'alice'})
            return fd
        self.backend.lock = finish_before_status_lock
        result = self.backend.status()
        self.assertFalse(result['running'])
        self.assertEqual(result['job']['status'], 'done')

    def test_old_user_manager_groups_are_reported_without_killing_workloads(self):
        self.backend.add_account()
        self.backend.path('/etc/group').write_text('libvirt-admin:x:123:alice\nrender:x:124:alice\n')
        process = self.backend.path('/proc/1234')
        process.mkdir(parents=True)
        (process / 'status').write_text('Gid:\t1000\t1000\t1000\t1000\nGroups:\t124\n')
        self.backend.settings.update({'manager_pid': '1234', 'desktop.main.user': 'alice'})
        self.assertTrue(self.backend.status()['group_refresh_required'])
        (process / 'status').write_text('Gid:\t1000\t1000\t1000\t1000\nGroups:\t123 124\n')
        self.assertFalse(self.backend.status()['group_refresh_required'])
        self.assertEqual(self.backend.calls, [])

    def test_symlink_state_directory_is_rejected(self):
        external = self.backend.root / 'external'
        external.mkdir()
        self.backend.runtime.parent.mkdir(parents=True)
        self.backend.runtime.symlink_to(external, target_is_directory=True)
        with self.assertRaisesRegex(M.SetupError, 'unsafe_state_directory'):
            self.backend.lock()
        self.assertEqual(list(external.iterdir()), [])


class KeyringStdinTests(unittest.TestCase):
    def test_existing_keyring_uses_stdin_and_failed_refresh_preserves_secret(self):
        with tempfile.TemporaryDirectory(prefix='desktop-keyring-stdin-') as temporary:
            work = Path(temporary)
            tools = work / 'bin'
            tools.mkdir()
            home = work / 'home'
            (home / '.local/share/keyrings').mkdir(parents=True)
            (home / '.local/share/keyrings/login.keyring').write_text('encrypted fixture')
            native = work / 'native'
            native.mkdir()
            credentials = work / 'credentials'
            helper_log = work / 'helper-args'
            common = work / 'common'
            common.write_text('desktop_error() { echo "$*" >&2; return 1; }\n'
                              'desktop_validate_user() { DESKTOP_USER_UID=1001; DESKTOP_USER_GID=1001; '
                              'DESKTOP_USER_HOME="' + str(home) + '"; }\n'
                              'desktop_setup_tls() { :; }\n')
            commands = {
                'id': '#!/bin/sh\nprintf 0\n',
                'stat': '#!/bin/sh\nprintf 0:600\n',
                'systemd-run': '#!/bin/sh\nprintf "%s\\n" "$@" > "' + str(helper_log) + '"\nexit "${SETUP_TEST_FAILURE:-0}"\n',
                'chown': '#!/bin/sh\nexit 0\n',
                'usermod': '#!/bin/sh\nexit 0\n',
                'su': '#!/bin/sh\nexit 0\n',
                'uci': '#!/bin/sh\nexit 0\n',
                'gnome-session': '#!/bin/sh\nexit 0\n',
                'desktop': '#!/bin/sh\nexit 0\n',
            }
            for name, source in commands.items():
                tool = tools / name
                tool.write_text(source)
                tool.chmod(0o755)
            source = (ROOT / 'package/custom/openwrt-desktop/files/desktop-setup').read_text()
            source = source.replace('/usr/libexec/desktop-common.sh', str(common))
            source = source.replace('/run/systemd/system', str(native))
            source = source.replace('/usr/bin/gnome-session', str(tools / 'gnome-session'))
            source = source.replace('secret_dir=/etc/desktop/gnome', 'secret_dir=' + str(credentials))
            source = source.replace('/etc/init.d/desktop', str(tools / 'desktop'))
            script = work / 'desktop-setup'
            script.write_text(source)
            environment = dict(os.environ, PATH=str(tools) + ':' + os.environ['PATH'])
            secret = 'existing-keyring-secret'
            result = subprocess.run(['sh', str(script), 'alice', '--keyring-password-stdin'],
                                    input=secret + '\n', text=True, capture_output=True, env=environment, timeout=5)
            self.assertEqual(result.returncode, 0, result.stderr)
            target = credentials / '1001.keyring-passphrase'
            self.assertEqual(target.read_text(), secret)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)
            self.assertNotIn(secret, result.stdout + result.stderr + helper_log.read_text())
            environment['SETUP_TEST_FAILURE'] = '1'
            result = subprocess.run(['sh', str(script), 'alice', '--refresh-keyring', '--keyring-password-stdin'],
                                    input='wrong-secret\n', text=True, capture_output=True, env=environment, timeout=5)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(target.read_text(), secret)
            self.assertEqual(sorted(p.name for p in credentials.iterdir()), ['1001.keyring-passphrase'])


if __name__ == '__main__':
    unittest.main()
