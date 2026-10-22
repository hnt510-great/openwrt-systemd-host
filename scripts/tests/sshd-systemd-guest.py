#!/usr/bin/env python3
"""Exercise SSH listener ownership inside a disposable VM, including stop/crash."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import time


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=120)
    if check and result.returncode:
        raise AssertionError(f'{args}: exit {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def wait_for(test, message, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if test():
            return
        time.sleep(.2)
    raise AssertionError(message)


def main_pid():
    return int(run('systemctl', 'show', '-p', 'MainPID', '--value', 'sshd.service').stdout)


def procd_ssh():
    return json.loads(run('ubus', 'call', 'service', 'list', '{"name":"sshd"}').stdout)


def enabled_recovery():
    return {str(p): os.readlink(p) for p in Path('/etc/rc.d').glob('[SK]??sshd')}


def host_keys():
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in Path('/etc/ssh').glob('ssh_host_*') if p.is_file()}


def listening(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            return True
    except OSError:
        return False


def native():
    assert Path('/proc/1/comm').read_text().strip() == 'systemd'
    run('systemctl', 'is-active', 'sshd.service')
    assert procd_ssh() == {}, procd_ssh()
    assert run('systemctl', 'show', '-p', 'Type', '--value', 'sshd.service').stdout.strip() == 'notify-reload'
    pid = main_pid()
    assert f'/sshd.service' in Path(f'/proc/{pid}/cgroup').read_text()
    settings = {key.lower(): value for key, value in
                (line.split(None, 1) for line in run('/usr/sbin/sshd', '-T').stdout.splitlines())}
    port = int(settings['port'])
    links, keys = enabled_recovery(), host_keys()
    print('PASS: native listener, readiness, cgroup ownership, no procd SSH registration', flush=True)

    for action in ('start', 'stop', 'restart', 'reload', 'shutdown'):
        assert run('/etc/init.d/sshd', action, check=False).returncode != 0
        assert main_pid() == pid and procd_ssh() == {}
    if Path('/run/openwrt-service-bridge/control').exists():
        result = run('systemctl', 'start', 'openwrt@sshd.service', check=False)
        assert result.returncode != 0
        assert 'sshd.service' in result.stderr
    print('PASS: legacy and optional bridge controls cannot create a second owner', flush=True)

    run('systemctl', 'reload', 'sshd.service')
    assert main_pid() == pid
    invalid = Path('/etc/ssh/sshd_config.d/99-sshd-validation-invalid.conf')
    assert not invalid.exists()
    try:
        invalid.write_text('InvalidSshdValidationOption yes\n')
        assert run('systemctl', 'reload', 'sshd.service', check=False).returncode != 0
        assert main_pid() == pid
        run('systemctl', 'is-active', 'sshd.service')
    finally:
        invalid.unlink()
    run('systemctl', 'reload', 'sshd.service')
    print('PASS: completed reload and invalid-config refusal keep the listener alive', flush=True)

    config = Path('/etc/ssh/sshd_config.d/00-openwrt-access.conf')
    original = config.read_bytes()
    override = Path('/run/systemd/system/sshd.service.d/sshd-validation.conf')
    assert not override.exists()
    try:
        helper = '/usr/libexec/luci-openssh'
        args = [str(port), settings['passwordauthentication'], settings['pubkeyauthentication'],
                settings['permitrootlogin'], settings['gatewayports']]
        run(helper, 'save', *args)
        assert main_pid() == pid
        try:
            override.parent.mkdir(parents=True, exist_ok=True)
            override.write_text('[Service]\nExecReload=\nExecReload=/bin/false\n')
            run('systemctl', 'daemon-reload')
            saved = config.read_bytes()
            failed_args = [str(port % 65535 + 1), *args[1:]]
            assert run(helper, 'save', *failed_args, check=False).returncode != 0
            assert config.read_bytes() == saved
            assert main_pid() == pid
        finally:
            override.unlink(missing_ok=True)
            run('systemctl', 'daemon-reload')
        print('PASS: actual reload failure restores the LuCI configuration', flush=True)
        run('systemctl', 'stop', 'sshd.service')
        assert not listening(port)
        run(helper, 'save', *args)
        assert main_pid() == 0
        assert not listening(port)
        assert procd_ssh() == {}
        print('PASS: LuCI active reload and inactive save; established test session survived stop', flush=True)
        try:
            invalid.write_text('InvalidSshdValidationOption yes\n')
            assert run('systemctl', 'start', 'sshd.service', check=False).returncode != 0
            assert main_pid() == 0 and not listening(port)
        finally:
            run('systemctl', 'stop', 'sshd.service')
            invalid.unlink(missing_ok=True)
            run('systemctl', 'reset-failed', 'sshd.service')
        print('PASS: invalid startup configuration cannot open a listener', flush=True)
    finally:
        config.write_bytes(original)
        run('systemctl', 'start', 'sshd.service')

    before = main_pid()
    run('systemctl', 'restart', 'sshd.service')
    assert main_pid() > 0 and main_pid() != before
    assert listening(port)
    before = main_pid()
    os.kill(before, signal.SIGKILL)
    wait_for(lambda: main_pid() > 0 and main_pid() != before and listening(port),
             'Native listener did not recover from SIGKILL')
    assert procd_ssh() == {}
    print('PASS: listener restart and crash recovery preserve the established test session', flush=True)

    was_enabled = run('systemctl', 'is-enabled', 'sshd.service', check=False).returncode == 0
    try:
        run('systemctl', 'disable', 'sshd.service')
        assert enabled_recovery() == links
        run('systemctl', 'is-active', 'sshd.service')
        run('systemctl', 'enable', 'sshd.service')
        assert enabled_recovery() == links
    finally:
        if not was_enabled:
            run('systemctl', 'disable', 'sshd.service')
    assert keys == host_keys()
    key = Path('/etc/ssh/ssh_host_rsa_key')
    original_key = key.read_bytes()
    try:
        key.write_bytes(b'invalid validation host key\n')
        assert run('/usr/libexec/sshd-prepare', check=False).returncode != 0
        assert key.read_bytes() == b'invalid validation host key\n'
    finally:
        key.write_bytes(original_key)
    assert keys == host_keys()
    print('PASS: enablement independence and unchanged host keys', flush=True)

    for unit in ('openwrt-procd', 'openwrt-services', 'systemd-logind', 'dbus', 'systemd-journald'):
        run('systemctl', 'is-active', unit)
    run('ubus', 'call', 'network.interface.lan', 'status')
    run('nslookup', 'localhost', '127.0.0.1')
    run('logread')
    print('PASS: router and native-service regressions', flush=True)


def recovery():
    assert Path('/proc/1/comm').read_text().strip() == 'procd'
    assert not Path('/run/systemd/system').exists()
    assert procd_ssh().get('sshd', {}).get('instances')
    run('/etc/init.d/sshd', 'running')
    run('/etc/init.d/sshd', 'reload')
    assert run('/usr/libexec/luci-openssh', 'backend').stdout.strip() == 'procd'
    assert not Path('/run/openwrt-service-bridge/control').exists()
    print('PASS: procd recovery SSH, original controls, LuCI backend, no native bridge', flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable', action='store_true', required=True)
    parser.add_argument('--recovery', action='store_true')
    args = parser.parse_args()
    recovery() if args.recovery else native()
