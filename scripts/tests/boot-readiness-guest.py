#!/usr/bin/env python3
"""Native bus ownership smoke; fault injection is disposable-VM-only."""
import argparse
import json
from pathlib import Path
import pwd
import shlex
import subprocess
import time


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=45)
    if check and result.returncode:
        raise AssertionError(f'{args}: {result.stdout}\n{result.stderr}')
    return result


def pid():
    return run('systemctl', 'show', 'dbus.service', '-p', 'MainPID', '--value').stdout.strip()


def smoke():
    original = pid()
    assert int(original) > 1
    run('/usr/libexec/openwrt-dbus-ready', '--check')
    for action in ('boot', 'start', 'restart', 'reload', 'stop', 'shutdown'):
        run('/etc/init.d/dbus', action)
        assert pid() == original, action
        assert json.loads(run('ubus', 'call', 'service', 'list', '{"name":"dbus"}').stdout) == {}
        run('/usr/libexec/openwrt-dbus-ready', '--check')
    run('hostnamectl', '--static', 'hostname')
    run('loginctl', 'list-sessions', '--no-pager')
    print('PASS: six legacy actions preserve native bus PID, ownership and activation', flush=True)


def containers(users):
    prepared = int(run('systemctl', 'show', 'podman-rootless-prepare.service',
                       '-p', 'ActiveEnterTimestampMonotonic', '--value').stdout)
    assert prepared > 0
    run('systemctl', 'is-active', 'podman-rootless-prepare.service')
    for user in users:
        uid = pwd.getpwnam(user).pw_uid
        started = int(run('systemctl', 'show', f'user@{uid}.service',
                          '-p', 'ExecMainStartTimestampMonotonic', '--value').stdout)
        assert prepared <= started, (user, prepared, started)
        def as_user(*args):
            command = ['env', f'XDG_RUNTIME_DIR=/run/user/{uid}',
                       f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', *args]
            return run('su', '-s', '/bin/sh', user, '-c', shlex.join(command))
        assert as_user('systemctl', '--user', 'show', 'boot-tun.service',
                       '-p', 'NRestarts', '--value').stdout.strip() == '0'
        as_user('systemctl', '--user', 'is-active', 'boot-tun.service')
        as_user('podman', 'exec', 'boot-tun', 'test', '-r', '/dev/null')
        acl = run('getfacl', '-n', '/dev/net/tun').stdout
        assert f'user:{uid}:rw-' in acl
        failed = as_user('systemctl', '--user', '--failed', '--no-legend', '--plain').stdout.strip()
        assert not failed, failed
        print(f'PASS: {user}: preparation before manager, direct ACL, container first start', flush=True)
    journal = run('journalctl', '-b', '_SYSTEMD_USER_UNIT=boot-tun.service', '--no-pager', '-o', 'cat').stdout
    assert 'Failed to open() /dev/net/tun' not in journal
    assert 'Failed to set up tap device' not in journal


def inject():
    # Intentionally bypass the repaired init guard to reconstruct the old
    # procd daemon's command and its socket replacement, only in a test VM.
    assert 'QEMU' in Path('/sys/class/dmi/id/product_name').read_text() or \
        'Standard PC' in Path('/sys/class/dmi/id/product_name').read_text()
    original = pid()
    with open('/tmp/boot-readiness-legacy-bus.log', 'w') as log:
        rogue = subprocess.Popen(['/usr/bin/dbus-daemon', '--system', '--nofork', '--nopidfile'],
                                 stdout=log, stderr=subprocess.STDOUT)
        try:
            time.sleep(2)
            assert rogue.poll() is None, 'legacy daemon did not start'
            assert pid() == original
            result = run('/usr/libexec/openwrt-dbus-ready', '--check', check=False)
            assert result.returncode != 0 and 'different daemon' in result.stderr, result.stderr
            result = run('hostnamectl', '--static', 'hostname', check=False)
            assert result.returncode != 0, 'legacy daemon unexpectedly activated hostnamed'
            print('PASS: reconstructed duplicate bus breaks hostname and is detected', flush=True)
        finally:
            rogue.terminate()
            rogue.wait(timeout=10)
            run('systemctl', 'stop', 'dbus.service', 'dbus.socket')
            run('systemctl', 'start', 'dbus.service')
            run('systemctl', 'restart', 'systemd-logind.service', 'polkit.service',
                'systemd-hostnamed.service')
    smoke()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--inject-legacy', action='store_true')
    parser.add_argument('--users', nargs='+', default=[])
    args = parser.parse_args()
    smoke()
    if args.inject_legacy:
        inject()
    if args.users:
        containers(args.users)
