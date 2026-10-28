#!/usr/bin/env python3
"""Test the real target keyring bootstrap on a private bus and temporary home."""
import os
from pathlib import Path
import secrets
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
from urllib.parse import unquote

ROOT = Path(__file__).resolve().parents[2]
DAEMON = ROOT / 'build_dir/target-x86_64_glibc/gnome-keyring-51.1/ipkg-install/usr/bin/gnome-keyring-daemon'
HELPER = ROOT / 'package/custom/openwrt-desktop/files/desktop-keyring-unlock'
RUNNER = ROOT / 'scripts/gi-target-runner'


def isolated(directory):
    work = Path(directory)
    runtime = work / 'run'
    runtime.mkdir(mode=0o700)
    address = os.environ['DBUS_SESSION_BUS_ADDRESS']
    assert address.startswith('unix:path=')
    (runtime / 'bus').symlink_to(unquote(address.removeprefix('unix:path=').split(',', 1)[0]))
    credentials = work / 'credentials'
    credentials.mkdir(mode=0o700)
    binary = work / 'bin'
    binary.mkdir()
    secret = secrets.token_hex(32)
    credential = credentials / 'keyring-passphrase'
    credential.write_text(secret)
    credential.chmod(0o600)
    env = dict(os.environ, HOME=str(work), XDG_RUNTIME_DIR=str(runtime),
               XDG_CONFIG_HOME=str(work / '.config'),
               XDG_DATA_HOME=str(work / '.local/share'),
               GNOME_KEYRING_CONTROL=str(runtime / 'keyring'),
               CREDENTIALS_DIRECTORY=str(credentials))
    env.pop('DISPLAY', None)
    env.pop('WAYLAND_DISPLAY', None)
    (binary / 'systemctl').write_text('#!/bin/sh\n'
                                    '[ "$*" = "--user start gnome-keyring-daemon.service" ]\n')
    for tool in binary.iterdir():
        tool.chmod(0o755)
    env['PATH'] = str(binary) + ':' + env['PATH']
    with (work / 'daemon.log').open('w') as log:
        daemon = subprocess.Popen([str(RUNNER), str(DAEMON), '--foreground',
                                   '--components=pkcs11,secrets',
                                   '--control-directory=' + env['GNOME_KEYRING_CONTROL']],
                                  env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            deadline = time.monotonic() + 10
            while not (runtime / 'keyring/control').is_socket():
                if daemon.poll() is not None or time.monotonic() > deadline:
                    raise RuntimeError('Private keyring daemon did not start')
                time.sleep(.1)
            helper = work / 'bootstrap'
            helper.write_text(HELPER.read_text().replace(
                '/usr/libexec/desktop-keyring-control-unlock',
                str(ROOT / 'package/custom/openwrt-desktop/files/desktop-keyring-control-unlock')))
            def bootstrap(success):
                result = subprocess.run(['sh', str(helper)], env=env, capture_output=True,
                                        text=True, timeout=30)
                if (result.returncode == 0) != success:
                    probe_env = dict(env, DBUS_SESSION_BUS_ADDRESS='unix:path=' + str(runtime / 'bus'))
                    probe = subprocess.run(['gdbus', 'call', '--session', '--dest',
                                            'org.freedesktop.secrets', '--object-path',
                                            '/org/freedesktop/secrets/aliases/default', '--method',
                                            'org.freedesktop.DBus.Properties.Get',
                                            'org.freedesktop.Secret.Collection', 'Locked'],
                                           env=probe_env, capture_output=True, text=True)
                    details = subprocess.run(['gdbus', 'call', '--session', '--dest',
                                              'org.freedesktop.secrets', '--object-path',
                                              '/org/freedesktop/secrets', '--method',
                                              'org.freedesktop.DBus.Properties.GetAll',
                                              'org.freedesktop.Secret.Service'],
                                             env=probe_env, capture_output=True, text=True)
                    raise AssertionError(result.stderr + probe.stdout + probe.stderr + details.stdout + details.stderr)
                assert secret not in result.stdout + result.stderr

            def call(path, method, *arguments):
                return subprocess.check_output(['gdbus', 'call', '--session', '--dest',
                                                'org.freedesktop.secrets', '--object-path', path,
                                                '--method', method, *arguments], env=env, text=True)

            def locked():
                return call('/org/freedesktop/secrets/aliases/default',
                            'org.freedesktop.DBus.Properties.Get',
                            'org.freedesktop.Secret.Collection', 'Locked').strip()

            bootstrap(True)
            assert locked() == '(<false>,)'
            assert (work / '.local/share/keyrings/login.keyring').stat().st_size > 0
            call('/org/freedesktop/secrets', 'org.freedesktop.Secret.Service.Lock',
                 '["/org/freedesktop/secrets/collection/login"]')
            assert locked() == '(<true>,)'
            credential.write_text('invalid-fixture-passphrase')
            bootstrap(False)
            assert locked() == '(<true>,)'
            credential.write_text(secret)
            bootstrap(True)
            assert locked() == '(<false>,)'
        finally:
            daemon.terminate()
            try:
                daemon.wait(timeout=5)
            except subprocess.TimeoutExpired:
                daemon.kill()
                daemon.wait()

class KeyringBootstrap(unittest.TestCase):
    def test_new_keyring_rejects_wrong_password_and_unlocks_again(self):
        if os.getuid() < 1000:
            self.skipTest('run as an ordinary build user')
        if not DAEMON.exists():
            self.skipTest('build gnome-keyring first')
        if not shutil.which('dbus-run-session') or not shutil.which('gdbus'):
            self.skipTest('host dbus-run-session and gdbus are required')
        with tempfile.TemporaryDirectory(prefix='gnome-keyring-test-') as directory:
            subprocess.run(['dbus-run-session', '--', sys.executable, str(Path(__file__).resolve()),
                            '--isolated', directory], check=True, timeout=90)


if __name__ == '__main__':
    if len(sys.argv) == 3 and sys.argv[1] == '--isolated':
        isolated(sys.argv[2])
    else:
        unittest.main()
