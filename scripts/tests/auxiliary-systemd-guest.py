#!/usr/bin/env python3
"""Lifecycle, ordering, race and Linux 7.3.5 checks for native auxiliary units in a disposable VM."""
import argparse
import json
from pathlib import Path
import shutil
import socket
import subprocess
import time


def run(*args, check=True):
    result = subprocess.run(args, capture_output=True, text=True, timeout=60)
    if check and result.returncode:
        raise AssertionError(f'{args}: {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def wait(test, message, timeout=25):
    start = time.monotonic()
    while time.monotonic() - start < timeout:
        if test():
            return round(time.monotonic() - start, 3)
        time.sleep(0.1)
    raise AssertionError(message)


def unit_prop(unit, prop):
    return run('systemctl', 'show', unit, '-p', prop, '--value').stdout.strip()


def unit_pid(unit):
    return int(unit_prop(unit, 'MainPID') or 0)


def tcp_listening(host, port):
    try:
        with socket.create_connection((host, port), timeout=0.2):
            return True
    except OSError:
        return False


def procd_and_network_healthy():
    run('nslookup', 'localhost', '127.0.0.1')
    lan = json.loads(run('ubus', 'call', 'network.interface.lan', 'status').stdout)
    assert lan['up'], lan
    code = run('curl', '-sS', '--max-time', '10', '-o', '/dev/null',
               '-w', '%{http_code}', 'http://192.0.2.1/').stdout.strip()
    assert code in ('200', '301', '302', '403'), code
    services = json.loads(run('ubus', 'call', 'service', 'list').stdout)
    for name in ('network', 'dnsmasq', 'odhcpd', 'uhttpd', 'rpcd'):
        insts = services.get(name, {}).get('instances', {})
        assert any(i.get('running') for i in insts.values()), f'{name} not running: {insts}'
    return services


def reset_limits():
    run('systemctl', 'reset-failed', 'cron.service', 'nlbwmon.service', 'ddns-go.service')


def verify_ownership(expect_cron=True, expect_nlbwmon=True, expect_ddns=False):
    services = procd_and_network_healthy()
    for name in ('cron', 'nlbwmon', 'ddns-go', 'samba4', 'wsdd2', 'avahi-daemon'):
        assert name not in services, f'{name} still registered in procd: {services[name]}'
    assert unit_prop('auxiliary.slice', 'CPUWeight') == '100'
    for unit, expected in (
        ('cron.service', expect_cron),
        ('nlbwmon.service', expect_nlbwmon),
        ('ddns-go.service', expect_ddns),
    ):
        assert unit_prop(unit, 'Transient') == 'no', unit
        if expected:
            assert unit_prop(unit, 'ActiveState') == 'active', unit
            p = unit_pid(unit)
            assert p > 0, unit
            cg = Path(f'/proc/{p}/cgroup').read_text()
            assert f'/auxiliary.slice/{unit}' in cg, (unit, cg)
            assert '/openwrt.slice/' not in cg, (unit, cg)
        else:
            assert unit_prop(unit, 'ActiveState') == 'inactive', unit
    legacy = run('systemctl', 'list-units', '--all', '--no-legend',
                 'openwrt-cron@*.service', 'openwrt-nlbwmon@*.service',
                 'openwrt-ddns*go@*.service').stdout.strip()
    assert not legacy, legacy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-vm', action='store_true', required=True)
    parser.parse_args()
    assert run('systemd-detect-virt').stdout.strip() in ('kvm', 'qemu')

    results = {}

    # 1. Verify Linux 7.3.5 + kernelctl + upstream packages health.
    uname = run('uname', '-r').stdout.strip()
    results['kernel-release'] = uname
    assert uname.startswith('7.3.5-'), f'Expected Linux 7.3.5, got {uname}'
    assert Path('/sys/kernel/btf/vmlinux').exists(), 'Missing kernel BTF'
    run('kernelctl', 'check')
    results['kernelctl-check'] = 'PASS'

    # 2. Verify initial auxiliary slice and service states (nlbwmon active, cron/ddns-go match config).
    cron_has_entries = any(Path('/etc/crontabs').iterdir())
    ddns_enabled = run('uci', '-q', 'get', 'ddns-go.config.enabled', check=False).stdout.strip() == '1'
    verify_ownership(expect_cron=cron_has_entries, expect_nlbwmon=True, expect_ddns=ddns_enabled)
    if not ddns_enabled:
        assert unit_prop('ddns-go.service', 'ConditionResult') == 'no'
    if not cron_has_entries:
        assert unit_prop('cron.service', 'ConditionResult') == 'no'
        Path('/etc/crontabs/root').write_text('# initial test entry\n')
        wait(
            lambda: unit_prop('cron.service', 'ActiveState') == 'active'
            and unit_pid('cron.service') > 0,
            'cron-config.path did not auto-start cron when /etc/crontabs/root was created',
        )
    reset_limits()

    # 3. Bridge exclusion and idempotent init.d start.
    cron_before = unit_pid('cron.service')
    nlbw_before = unit_pid('nlbwmon.service')
    ddns_before = unit_pid('ddns-go.service') if ddns_enabled else 0
    for svc in ('cron', 'nlbwmon', 'ddns-go'):
        run('/etc/init.d/' + svc, 'start')
        denied = run('systemctl', 'start', f'openwrt@{svc}.service', check=False)
        assert denied.returncode != 0, svc
    assert unit_pid('cron.service') == cron_before
    assert unit_pid('nlbwmon.service') == nlbw_before
    if ddns_enabled:
        assert unit_pid('ddns-go.service') == ddns_before
    results['bridge-exclusion-and-idempotent-start'] = True

    # 4. Verify nlbwmon Nice=19, CLI arguments, and nlbw client socket communication.
    nlbw_cmdline = Path(f'/proc/{nlbw_before}/cmdline').read_bytes().replace(b'\x00', b' ').decode()
    assert '-o /var/lib/nlbwmon' in nlbw_cmdline and '-s 192.0.2.1/24' in nlbw_cmdline, nlbw_cmdline
    nlbw_stat = Path(f'/proc/{nlbw_before}/stat').read_text().split()
    assert int(nlbw_stat[18]) == 19, f'Expected Nice=19, got {nlbw_stat[18]}'
    run('/usr/sbin/nlbw', '-c', 'list')
    run('/usr/sbin/nlbw', '-c', 'commit')
    results['nlbwmon-cmdline-and-ipc'] = nlbw_cmdline.strip()

    # 5. Crash recovery for cron and nlbwmon.
    cron_before = unit_pid('cron.service')
    run('systemctl', 'kill', '--kill-whom=main', '--signal=KILL', 'cron.service')
    results['cron-crash-recovery-seconds'] = wait(
        lambda: unit_pid('cron.service') not in (0, cron_before)
        and unit_prop('cron.service', 'ActiveState') == 'active',
        'cron did not recover from SIGKILL',
    )
    nlbw_before = unit_pid('nlbwmon.service')
    run('systemctl', 'kill', '--kill-whom=main', '--signal=KILL', 'nlbwmon.service')
    results['nlbwmon-crash-recovery-seconds'] = wait(
        lambda: unit_pid('nlbwmon.service') not in (0, nlbw_before)
        and unit_prop('nlbwmon.service', 'ActiveState') == 'active',
        'nlbwmon did not recover from SIGKILL',
    )
    reset_limits()

    # 6. Cron path watcher and empty-crontabs condition.
    crontab = Path('/etc/crontabs/root')
    orig_crontab = crontab.read_bytes() if crontab.exists() else b''
    try:
        cron_before = unit_pid('cron.service')
        crontab.write_bytes(orig_crontab + b'# test comment\n')
        wait(
            lambda: unit_pid('cron.service') not in (0, cron_before)
            and unit_prop('cron.service', 'ActiveState') == 'active',
            'cron-config.path did not restart cron on crontab edit',
        )
        # Moving all crontabs away should stop cron cleanly via reconcile.
        backup_dir = Path('/tmp/crontabs-backup')
        backup_dir.mkdir(exist_ok=True)
        for p in Path('/etc/crontabs').iterdir():
            shutil.move(str(p), str(backup_dir / p.name))
        wait(
            lambda: unit_prop('cron.service', 'ActiveState') == 'inactive',
            'cron did not stop when /etc/crontabs became empty',
        )
        for p in backup_dir.iterdir():
            shutil.move(str(p), str(Path('/etc/crontabs') / p.name))
        wait(
            lambda: unit_prop('cron.service', 'ActiveState') == 'active'
            and unit_pid('cron.service') > 0,
            'cron-config.path did not auto-start cron after restoring /etc/crontabs',
        )
        results['cron-path-watcher-and-empty-condition'] = True
    finally:
        if orig_crontab:
            crontab.write_bytes(orig_crontab)
        elif not cron_has_entries and crontab.exists():
            crontab.unlink()
            wait(
                lambda: unit_prop('cron.service', 'ActiveState') == 'inactive',
                'cron did not stop after removing temporary /etc/crontabs/root',
            )

    # 7. nlbwmon hotplug: wan6 ignored, lan reconciles.
    nlbw_before = unit_pid('nlbwmon.service')
    run('env', 'ACTION=ifup', 'INTERFACE=wan6', 'sh', '/etc/hotplug.d/iface/30-nlbwmon')
    time.sleep(0.5)
    assert unit_pid('nlbwmon.service') == nlbw_before
    for _ in range(5):
        wait(lambda: unit_prop('nlbwmon-reconfigure.service', 'ActiveState') == 'inactive',
             'nlbwmon-reconfigure stuck active')
        cur = unit_pid('nlbwmon.service')
        run('env', 'ACTION=ifupdate', 'INTERFACE=lan', 'sh', '/etc/hotplug.d/iface/30-nlbwmon')
        wait(lambda: unit_pid('nlbwmon.service') not in (0, cur)
             and unit_prop('nlbwmon.service', 'ActiveState') == 'active',
             'nlbwmon lan hotplug did not reconcile')
    assert unit_prop('nlbwmon-config.path', 'ActiveState') == 'active'
    results['nlbwmon-hotplug-reconcile'] = True

    # 8. ddns-go UCI path watcher lifecycle + unprivileged user + crash recovery.
    run('uci-history', '--json', 'begin', '--timeout', '300', '--note', 'disposable auxiliary VM test')
    uci_ddns = Path('/etc/config/ddns-go')
    orig_ddns = uci_ddns.read_bytes()
    ddns_port = int((run('uci', '-q', 'get', 'ddns-go.config.port', check=False).stdout.strip() or '9876').split(':')[-1])
    ddns_noweb = run('uci', '-q', 'get', 'ddns-go.config.noweb', check=False).stdout.strip() == '1'
    try:
        if ddns_enabled:
            run('uci', 'set', 'ddns-go.config.enabled=0')
            run('uci', 'commit', 'ddns-go')
            wait(
                lambda: unit_prop('ddns-go.service', 'ActiveState') == 'inactive',
                'ddns-go did not stop when enabled=0 in UCI',
            )
        run('uci', 'set', 'ddns-go.config.enabled=1')
        run('uci', 'set', 'ddns-go.config.delay=0')
        run('uci', 'commit', 'ddns-go')
        wait(
            lambda: unit_prop('ddns-go.service', 'ActiveState') == 'active'
            and unit_pid('ddns-go.service') > 0,
            'ddns-go-config.path did not start ddns-go when enabled=1 in UCI',
        )
        if not ddns_noweb:
            wait(lambda: tcp_listening('127.0.0.1', ddns_port), f'ddns-go web UI not listening on {ddns_port}')
        verify_ownership(expect_cron=cron_has_entries, expect_nlbwmon=True, expect_ddns=True)
        ddns_pid = unit_pid('ddns-go.service')
        status_text = Path(f'/proc/{ddns_pid}/status').read_text()
        assert 'Uid:\t0\t' not in status_text, f'ddns-go running as root: {status_text}'
        assert Path('/etc/ddns-go').stat().st_uid != 0, '/etc/ddns-go not owned by ddns-go user'

        # Crash recovery for ddns-go.
        run('systemctl', 'kill', '--kill-whom=main', '--signal=KILL', 'ddns-go.service')
        results['ddns-go-crash-recovery-seconds'] = wait(
            lambda: unit_pid('ddns-go.service') not in (0, ddns_pid)
            and unit_prop('ddns-go.service', 'ActiveState') == 'active',
            'ddns-go did not recover from SIGKILL',
        )
        reset_limits()

        # Disable via UCI and verify path watcher stops ddns-go.service.
        run('uci', 'set', 'ddns-go.config.enabled=0')
        run('uci', 'commit', 'ddns-go')
        wait(
            lambda: unit_prop('ddns-go.service', 'ActiveState') == 'inactive',
            'ddns-go did not stop when enabled=0 in UCI',
        )
        results['ddns-go-uci-lifecycle'] = True
    finally:
        if uci_ddns.read_bytes() != orig_ddns:
            uci_ddns.write_bytes(orig_ddns)
            expected_state = 'active' if ddns_enabled else 'inactive'
            wait(
                lambda: unit_prop('ddns-go.service', 'ActiveState') == expected_state,
                f'ddns-go did not return to {expected_state} state',
            )
    run('uci-history', '--json', 'confirm')

    verify_ownership(expect_cron=cron_has_entries, expect_nlbwmon=True, expect_ddns=ddns_enabled)
    results['initial-cron-active'] = cron_has_entries
    results['initial-ddns-go-active'] = ddns_enabled
    reset_limits()
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()
