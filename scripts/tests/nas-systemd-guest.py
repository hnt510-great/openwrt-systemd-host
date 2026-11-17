#!/usr/bin/env python3
"""Lifecycle, discovery and race checks for native NAS units in a disposable VM."""
import argparse
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
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


def unit_prop(unit, prop):
    return run('systemctl', 'show', unit, '-p', prop, '--value').stdout.strip()


def unit_pid(unit):
    return int(unit_prop(unit, 'MainPID') or 0)


def smb_listening():
    try:
        with socket.create_connection(('192.0.2.1', 445), timeout=.2):
            return True
    except OSError:
        return False


def avahi_has_smb():
    res = run('avahi-browse', '-t', '-p', '-r', '_smb._tcp', check=False)
    if res.returncode != 0:
        return False
    return ';OpenWrt;_smb._tcp;' in res.stdout


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
    run('systemctl', 'reset-failed', 'samba4@smbd.service', 'samba4@nmbd.service',
        'wsdd2.service', 'avahi-daemon.service')


def verify_ownership():
    services = procd_and_network_healthy()
    for name in ('samba4', 'wsdd2', 'avahi-daemon'):
        assert name not in services, f'{name} still registered in procd: {services[name]}'
    for unit in ('samba4@smbd.service', 'wsdd2.service', 'avahi-daemon.service'):
        assert unit_prop(unit, 'ActiveState') == 'active', unit
        assert unit_prop(unit, 'Transient') == 'no', unit
        p = unit_pid(unit)
        assert p > 0, unit
        cg = Path(f'/proc/{p}/cgroup').read_text()
        assert f'/nas.slice/{unit}' in cg, (unit, cg)
        assert '/openwrt.slice/' not in cg, (unit, cg)
    legacy = run('systemctl', 'list-units', '--all', '--no-legend',
                 'openwrt-samba4@*.service', 'openwrt-wsdd2@*.service',
                 'openwrt-avahi-daemon@*.service').stdout.strip()
    assert not legacy, legacy


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-vm', action='store_true', required=True)
    parser.parse_args()
    assert run('systemd-detect-virt').stdout.strip() in ('kvm', 'qemu')

    results = {}
    wait(smb_listening, 'SMB not listening at initial check')
    wait(avahi_has_smb, 'Avahi did not publish _smb._tcp at initial check')
    verify_ownership()
    reset_limits()

    # Idempotency, recovery/bridge exclusion, and service-bridge non-interference.
    wsdd_before = unit_pid('wsdd2.service')
    avahi_before = unit_pid('avahi-daemon.service')
    smb_before = unit_pid('samba4@smbd.service')
    for svc in ('samba4', 'wsdd2', 'avahi-daemon'):
        run('/etc/init.d/' + svc, 'start')
        denied = run('systemctl', 'start', f'openwrt@{svc}.service', check=False)
        assert denied.returncode != 0, svc
    assert unit_pid('wsdd2.service') == wsdd_before
    assert unit_pid('avahi-daemon.service') == avahi_before
    assert unit_pid('samba4@smbd.service') == smb_before
    results['native-ownership-and-idempotent-start'] = True

    # Check wsdd2 resolved CLI arguments and listening sockets without sleep 5 hack.
    wsdd_cmdline = Path(f'/proc/{wsdd_before}/cmdline').read_bytes().replace(b'\x00', b' ').decode()
    assert '-i br-lan' in wsdd_cmdline and '-N ' in wsdd_cmdline and '-G ' in wsdd_cmdline, wsdd_cmdline
    results['wsdd2-cmdline'] = wsdd_cmdline.strip()

    # Stopping samba4.service must stop wsdd2 (PartOf=samba4.service) while keeping avahi-daemon alive.
    run('systemctl', 'stop', 'samba4.service')
    wait(lambda: not smb_listening(), 'SMB still listening after stop')
    wait(lambda: unit_prop('wsdd2.service', 'ActiveState') == 'inactive', 'wsdd2 did not stop with samba4')
    assert unit_prop('avahi-daemon.service', 'ActiveState') == 'active'
    procd_and_network_healthy()

    # Starting samba4.service must automatically start wsdd2 (WantedBy=samba4.service) after smbd.
    t0 = time.monotonic()
    run('systemctl', 'start', 'samba4.service')
    wait(smb_listening, 'SMB did not start')
    wait(lambda: unit_prop('wsdd2.service', 'ActiveState') == 'active', 'wsdd2 did not start with samba4')
    results['samba-and-wsdd2-start-seconds'] = round(time.monotonic() - t0, 3)
    wait(avahi_has_smb, 'Avahi did not re-publish _smb._tcp after samba4 restart')
    verify_ownership()
    reset_limits()

    # Crash recovery for wsdd2 and avahi-daemon (and verify smbd re-registers _smb._tcp after avahi crash).
    wsdd_before = unit_pid('wsdd2.service')
    run('systemctl', 'kill', '--kill-whom=main', '--signal=KILL', 'wsdd2.service')
    results['wsdd2-crash-recovery-seconds'] = wait(
        lambda: unit_pid('wsdd2.service') not in (0, wsdd_before) and unit_prop('wsdd2.service', 'ActiveState') == 'active',
        'wsdd2 did not recover from SIGKILL',
    )
    avahi_before = unit_pid('avahi-daemon.service')
    run('systemctl', 'kill', '--kill-whom=main', '--signal=KILL', 'avahi-daemon.service')
    results['avahi-crash-recovery-seconds'] = wait(
        lambda: unit_pid('avahi-daemon.service') not in (0, avahi_before) and unit_prop('avahi-daemon.service', 'ActiveState') == 'active',
        'avahi-daemon did not recover from SIGKILL',
    )
    results['avahi-republish-after-crash-seconds'] = wait(
        avahi_has_smb, 'smbd did not re-publish _smb._tcp after avahi crash', 25,
    )
    verify_ownership()
    reset_limits()

    # Reload avahi-daemon (SIGHUP) and verify _smb._tcp remains advertised.
    avahi_before = unit_pid('avahi-daemon.service')
    run('/etc/init.d/avahi-daemon', 'reload')
    time.sleep(.5)
    assert unit_pid('avahi-daemon.service') == avahi_before
    assert avahi_has_smb()
    results['avahi-reload-preserves-pid'] = True

    # UCI workgroup change on samba4 must cascade through /var/etc/smb.conf -> wsdd2-config.path -> wsdd2 restart.
    run('uci-history', '--json', 'begin', '--timeout', '300', '--note', 'disposable NAS VM test')
    uci_samba = Path('/etc/config/samba4')
    orig_samba = uci_samba.read_bytes()
    try:
        wsdd_before = unit_pid('wsdd2.service')
        run('uci', 'set', 'samba4.@samba[0].workgroup=VMWORKGRP')
        run('uci', 'commit', 'samba4')
        wait(
            lambda: unit_pid('wsdd2.service') not in (0, wsdd_before)
            and '-G VMWORKGRP' in Path(f"/proc/{unit_pid('wsdd2.service')}/cmdline").read_bytes().replace(b'\x00', b' ').decode(),
            'wsdd2 did not pick up updated workgroup from samba4 config change',
        )
        results['samba-uci-cascades-to-wsdd2'] = True

        # Interface hotplug: wan6 ignored, lan reconciles wsdd2.
        wsdd_before = unit_pid('wsdd2.service')
        run('env', 'ACTION=ifup', 'INTERFACE=wan6', 'sh', '/etc/hotplug.d/iface/65-wsdd2')
        time.sleep(.5)
        assert unit_pid('wsdd2.service') == wsdd_before
        for _ in range(5):
            wait(lambda: unit_prop('wsdd2-reconfigure.service', 'ActiveState') == 'inactive',
                 'wsdd2-reconfigure stuck active')
            cur = unit_pid('wsdd2.service')
            run('env', 'ACTION=ifupdate', 'INTERFACE=lan', 'sh', '/etc/hotplug.d/iface/65-wsdd2')
            wait(lambda: unit_pid('wsdd2.service') not in (0, cur)
                 and unit_prop('wsdd2.service', 'ActiveState') == 'active',
                 'wsdd2 lan hotplug did not reconcile')
        assert unit_prop('wsdd2-config.path', 'ActiveState') == 'active'
        results['wsdd2-hotplug-reconcile'] = True
    finally:
        if uci_samba.read_bytes() != orig_samba:
            wsdd_before = unit_pid('wsdd2.service')
            uci_samba.write_bytes(orig_samba)
            wait(lambda: unit_pid('wsdd2.service') not in (0, wsdd_before)
                 and '-G WORKGROUP' in Path(f"/proc/{unit_pid('wsdd2.service')}/cmdline").read_bytes().replace(b'\x00', b' ').decode(),
                 'wsdd2 did not restore original workgroup')
    run('uci-history', '--json', 'confirm')

    # Inactive wsdd2 must stay stopped when config/hotplug fires.
    run('systemctl', 'stop', 'wsdd2.service')
    wait(lambda: unit_prop('wsdd2.service', 'ActiveState') == 'inactive', 'wsdd2 stop failed')
    run('env', 'ACTION=ifupdate', 'INTERFACE=lan', 'sh', '/etc/hotplug.d/iface/65-wsdd2')
    run('/etc/init.d/wsdd2', 'reload')
    time.sleep(.5)
    assert unit_prop('wsdd2.service', 'ActiveState') == 'inactive'
    results['inactive-wsdd2-stays-stopped'] = True

    run('systemctl', 'start', 'wsdd2.service')
    wait(lambda: unit_prop('wsdd2.service', 'ActiveState') == 'active', 'Final wsdd2 start failed')
    verify_ownership()
    reset_limits()
    print(json.dumps(results, indent=2), flush=True)


if __name__ == '__main__':
    main()
