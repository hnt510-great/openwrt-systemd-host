#!/usr/bin/env python3
"""Destructive lifecycle checks for Samba, only in an explicitly disposable VM."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import tempfile
import shutil
import subprocess
import time


def run(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if check and result.returncode:
        raise AssertionError(f'{args}: {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def wait(test, message, timeout=20):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if test():
            return round(time.monotonic() - start, 3)
        time.sleep(.1)
    raise AssertionError(message)


def pid():
    return int(run('systemctl', 'show', 'samba4@smbd.service', '-p', 'MainPID', '--value').stdout)


def listening():
    try:
        with socket.create_connection(('192.0.2.1', 445), timeout=.2):
            return True
    except OSError:
        return False


def dns():
    run('nslookup', 'localhost', '127.0.0.1')
    lan = json.loads(run('ubus', 'call', 'network.interface.lan', 'status').stdout)
    assert lan['up']
    code = run('curl', '-sS', '--max-time', '10', '-o', '/dev/null',
               '-w', '%{http_code}', 'http://192.0.2.1/').stdout
    assert code in ('200', '301', '302', '403'), code


def reset_limits():
    # Each scenario is independent; repeated test restarts must not consume the
    # normal crash-loop rate limit for the next scenario.
    run('systemctl', 'reset-failed', 'samba4@smbd.service', 'samba4@nmbd.service')


def ownership():
    assert json.loads(run('ubus', 'call', 'service', 'list', '{"name":"samba4"}').stdout) == {}
    assert run('systemctl', 'show', 'samba4@smbd.service', '-p', 'Transient', '--value').stdout.strip() == 'no'
    assert '/nas.slice/samba4@smbd.service' in Path(f'/proc/{pid()}/cgroup').read_text()
    for name in ('smbd', 'nmbd'):
        for process in run('pidof', name, check=False).stdout.split():
            assert '/nas.slice/' in Path(f'/proc/{process}/cgroup').read_text()
    services = json.loads(run('ubus', 'call', 'service', 'list').stdout)
    assert any(i.get('running') for i in services['dnsmasq']['instances'].values())
    dns()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-vm', action='store_true', required=True)
    parser.parse_args()
    assert run('systemd-detect-virt').stdout.strip() in ('kvm', 'qemu')
    assert Path('/root/samba-test').is_dir(), 'Dedicated fixture directory required'
    results = {}
    wait(listening, 'SMB never listened at initial check')
    ownership()
    reset_limits()
    before = pid()
    run('/etc/init.d/samba4', 'start')
    assert pid() == before
    denied = run('systemctl', 'start', 'openwrt@samba4.service', check=False)
    assert denied.returncode != 0 and pid() == before
    results['native-ownership-and-idempotent-start'] = True
    run('env', 'ACTION=ifup', 'INTERFACE=wan6', 'sh', '/etc/hotplug.d/iface/60-samba4')
    time.sleep(.5)
    assert pid() == before
    results['unselected-interface-keeps-pid'] = True
    for _ in range(7):
        wait(lambda: run('systemctl', 'show', 'samba4-reconfigure.service', '-p',
                         'ActiveState', '--value').stdout.strip() == 'inactive',
             'Reconfigure service did not finish')
        before = pid()
        run('env', 'ACTION=ifupdate', 'INTERFACE=lan', 'sh', '/etc/hotplug.d/iface/60-samba4')
        wait(lambda: pid() not in (0, before) and listening(), 'Rapid update lost SMB')
    run('systemctl', 'is-active', '--quiet', 'samba4-config.path')
    results['rapid-reconfigure-keeps-watcher'] = True
    ownership()
    reset_limits()

    run('systemctl', 'stop', 'samba4.service')
    wait(lambda: not listening(), 'SMB still listening after group stop')
    assert not run('pidof', 'smbd', check=False).stdout.strip()
    assert not run('pidof', 'nmbd', check=False).stdout.strip()
    dns()
    started = time.monotonic()
    run('systemctl', 'start', 'samba4.service')
    wait(listening, 'SMB did not return after start')
    results['start-to-port-seconds'] = round(time.monotonic() - started, 3)
    ownership()
    reset_limits()

    before = pid()
    run('systemctl', 'kill', '--kill-whom=main', '--signal=KILL', 'samba4@smbd.service')
    results['crash-recovery-seconds'] = wait(lambda: pid() not in (0, before) and listening(), 'Native restart did not restore SMB', 15)
    ownership()
    reset_limits()

    run('uci-history', '--json', 'begin', '--timeout', '300', '--note', 'disposable Samba VM test')
    template = Path('/etc/samba/smb.conf.template')
    original = template.read_bytes()
    uci_config = Path('/etc/config/samba4')
    original_uci = uci_config.read_bytes()
    try:
        share = Path(tempfile.mkdtemp(prefix='samba-vm-share-'))
        share.chmod(0o777)
        (share / 'hello.txt').write_text('Samba VM native test\n')
        for setting in ('samba4.vmtest=sambashare', 'samba4.vmtest.name=vmtest',
                        f'samba4.vmtest.path={share}', 'samba4.vmtest.guest_ok=yes',
                        'samba4.vmtest.read_only=no'):
            run('uci', 'set', setting)
        before = pid()
        run('uci', 'commit', 'samba4')
        wait(lambda: pid() not in (0, before) and listening(), 'Path watcher did not apply UCI')
        target = '//192.0.2.1/vmtest'
        run('smbclient', target, '-N', '-U', '%', '-c', 'get hello.txt /tmp/samba-vm-download.txt')
        assert Path('/tmp/samba-vm-download.txt').read_bytes() == (share / 'hello.txt').read_bytes()
        Path('/tmp/samba-vm-upload.txt').write_text('upload via SMB\n')
        run('smbclient', target, '-N', '-U', '%', '-c', 'put /tmp/samba-vm-upload.txt uploaded.txt')
        assert (share / 'uploaded.txt').read_bytes() == Path('/tmp/samba-vm-upload.txt').read_bytes()
        results['uci-watch-and-smb-read-write'] = True
        ownership()
        reset_limits()

        before = pid()
        run('uci', 'set', 'samba4.@samba[0].disable_netbios=1')
        run('uci', 'commit', 'samba4')
        wait(lambda: pid() not in (0, before) and listening() and
             not run('pidof', 'nmbd', check=False).stdout.strip(),
             'Optional NetBIOS daemon did not stop')
        results['optional-netbios-disable'] = True
        ownership()
        reset_limits()

        before = pid()
        generated = Path('/var/etc/smb.conf')
        digest = hashlib.sha256(generated.read_bytes()).hexdigest()
        template.write_bytes(original + b'\n[global]\nsecurity = INVALID_VM_TEST\n')
        rejected = run('/etc/init.d/samba4', 'reload', check=False)
        assert rejected.returncode != 0, 'Invalid configuration was accepted'
        time.sleep(1)
        assert pid() == before and listening()
        assert hashlib.sha256(generated.read_bytes()).hexdigest() == digest
        results['invalid-config-keeps-serving'] = True
        template.write_bytes(original)
        wait(lambda: pid() not in (0, before) and listening(), 'Valid template restore not applied')
        before = pid()
        run('env', 'ACTION=ifupdate', 'INTERFACE=lan', 'sh', '/etc/hotplug.d/iface/60-samba4')
        wait(lambda: pid() not in (0, before) and listening(), 'Interface hotplug did not reconcile')
        results['interface-reconfigure'] = True
        ownership()
        reset_limits()
    finally:
        if template.read_bytes() != original:
            template.write_bytes(original)
        reset_limits()
        if uci_config.read_bytes() != original_uci:
            before = pid()
            uci_config.write_bytes(original_uci)
            wait(lambda: pid() not in (0, before) and listening(), 'Fixture cleanup not applied')
        if 'share' in locals():
            shutil.rmtree(share)
    run('uci-history', '--json', 'confirm')

    run('systemctl', 'stop', 'samba4.service')
    wait(lambda: not listening(), 'Stop after fixture failed')
    run('/etc/init.d/samba4', 'reload')
    time.sleep(.5)
    assert not listening()
    results['inactive-reload-stays-stopped'] = True
    run('systemctl', 'start', 'samba4.service')
    wait(listening, 'Final start failed')
    ownership()
    reset_limits()
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()
