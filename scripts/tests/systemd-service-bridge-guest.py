#!/usr/bin/env python3
"""Destructive service tests for a disposable OpenWrt native-systemd VM only."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def run(*args, check=True):
    result = subprocess.run(args, text=True, capture_output=True, timeout=120)
    if check and result.returncode:
        raise AssertionError(f'{args}: exit {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def wait_for(test, description, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if test():
            return
        time.sleep(0.2)
    raise AssertionError('Timed out: ' + description)


def service():
    data = json.loads(run('ubus', 'call', 'service', 'list',
                          '{"name":"bridge-smoke","verbose":true}').stdout)
    return data.get('bridge-smoke', {}).get('instances', {})


def active():
    return run('systemctl', 'is-active', 'openwrt@bridge-smoke', check=False)


def network_matrix():
    for name in ['network', 'firewall', 'dnsmasq', 'sshd', 'rpcd', 'cron']:
        run('systemctl', 'is-active', 'openwrt@' + name)
    for name in ['network', 'firewall', 'dnsmasq']:
        run('systemctl', 'reload', 'openwrt@' + name)
    run('systemctl', 'restart', 'openwrt@cron')
    for name in ['passwall', 'passwall_server']:
        if Path('/etc/init.d/' + name).exists():
            run('systemctl', 'restart', 'openwrt@' + name)
            result = run('systemctl', 'status', 'openwrt@' + name, check=False)
            assert result.returncode in (0, 3), result
    run('nslookup', 'localhost', '127.0.0.1')
    data = json.loads(run('ubus', 'call', 'network.interface.lan', 'status').stdout)
    assert data['up']
    address = data['ipv4-address'][0]
    namespace, inside, outside = 'bridge-test-client', 'brt-client', 'brt-router'
    lease = Path('/tmp/bridge-test-dhcp.lease')
    script = Path('/tmp/bridge-test-dhcp.script')
    lease.unlink(missing_ok=True)
    script.write_text('''#!/bin/sh
case "$1" in
 bound|renew) printf '%s' "$ip" > /tmp/bridge-test-dhcp.lease ;;
esac
exit 0
''')
    script.chmod(0o755)
    run('ip', 'netns', 'add', namespace)
    try:
        run('ip', 'link', 'add', outside, 'type', 'veth', 'peer', 'name', inside)
        run('ip', 'link', 'set', outside, 'master', data.get('device', 'br-lan'))
        run('ip', 'link', 'set', outside, 'up')
        run('ip', 'link', 'set', inside, 'netns', namespace)
        run('ip', '-n', namespace, 'link', 'set', inside, 'up')
        run('ip', 'netns', 'exec', namespace, 'udhcpc', '-i', inside, '-n', '-q',
            '-t', '3', '-T', '2', '-s', str(script))
        leased = lease.read_text().strip()
        assert leased and leased != address['address']
        run('ip', '-n', namespace, 'addr', 'add', f"{leased}/{address['mask']}",
            'dev', inside)
        run('ip', 'netns', 'exec', namespace, 'nslookup', 'localhost', address['address'])
    finally:
        run('ip', 'netns', 'del', namespace, check=False)
        run('ip', 'link', 'del', outside, check=False)
        lease.unlink(missing_ok=True)
        script.unlink(missing_ok=True)
    print('PASS: router controls, PassWall restart adapters, LAN, DHCP client lease, and DNS')


def apk_transaction(package):
    run('apk', 'verify', '--keys-dir', '/etc/apk/keys', package)
    run('apk', 'add', '--simulate', '--no-network', '--repositories-file', '/dev/null', package)
    run('apk', 'add', '--no-network', '--repositories-file', '/dev/null', package)
    unit = 'openwrt@bridge-apk-smoke.service'
    assert Path('/etc/init.d/bridge-apk-smoke').exists()
    run('systemctl', 'enable', '--now', unit)
    wait_for(lambda: run('systemctl', 'is-active', unit, check=False).returncode == 0,
             'APK service running')
    run('apk', 'del', '--no-network', '--repositories-file', '/dev/null', 'bridge-apk-smoke')
    assert run('systemctl', 'cat', unit, check=False).returncode != 0
    assert not Path('/etc/init.d/bridge-apk-smoke').exists()
    assert run('systemctl', 'is-active', unit, check=False).returncode != 0
    print('PASS: signed offline APK verification/simulation/install/removal and script discovery')


def reconnect():
    bridge = run('systemctl', 'show', 'openwrt-service-bridge', '-p', 'MainPID',
                 '--value').stdout.strip()
    procd = run('pidof', 'procd').stdout.strip()
    fixture = service()['main']['pid']
    os.kill(int(run('pidof', 'ubusd').stdout.strip()), signal.SIGKILL)
    wait_for(lambda: run('ubus', 'list', 'service', check=False).returncode == 0,
             'ubus service object reconnect')
    wait_for(lambda: active().returncode == 0, 'bridge status after reconnect')
    assert run('systemctl', 'show', 'openwrt-service-bridge', '-p', 'MainPID',
               '--value').stdout.strip() == bridge
    assert run('pidof', 'procd').stdout.strip() == procd
    assert service()['main']['pid'] == fixture
    run('nslookup', 'localhost', '127.0.0.1')
    print('PASS: ubusd failure/reconnect without restarting bridge, procd, or fixture')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable', action='store_true', required=True)
    parser.add_argument('--after-reboot', action='store_true')
    parser.add_argument('--recovery', action='store_true')
    parser.add_argument('--network', action='store_true')
    parser.add_argument('--apk')
    parser.add_argument('--reconnect', action='store_true')
    args = parser.parse_args()
    if args.recovery:
        assert Path('/proc/1/comm').read_text().strip() == 'procd'
        assert not Path('/run/openwrt-service-bridge/control').exists()
        run('/etc/init.d/bridge-smoke', 'start')
        assert service()['main']['running']
        run('/etc/init.d/bridge-smoke', 'stop')
        print('PASS: procd recovery, original init controls, bridge absent')
        return
    assert Path('/proc/1/comm').read_text().strip() == 'systemd'
    run('systemctl', 'is-active', 'openwrt-service-bridge', 'openwrt-procd', 'openwrt-services')
    if args.network:
        network_matrix()
    if args.apk:
        apk_transaction(args.apk)
    if args.reconnect:
        reconnect()
    if args.after_reboot:
        assert run('systemctl', 'is-enabled', 'openwrt@bridge-smoke').stdout.strip() == 'enabled'
        wait_for(lambda: active().returncode == 0, 'enabled fixture after reboot')
        print('PASS: shared enablement and automatic service startup survived reboot')
        return
    script = Path('/etc/init.d/bridge-smoke')
    if script.exists():
        raise RuntimeError('Fixture already exists; use a fresh disposable VM')
    script.write_text('''#!/bin/sh /etc/rc.common
START=99
STOP=10
USE_PROCD=1
start_service() {
    echo start >> /tmp/bridge-smoke-actions
    procd_open_instance main
    procd_set_param command /bin/sleep 3600
    procd_set_param respawn 3600 1 2
    procd_close_instance
    if [ -f /tmp/bridge-smoke-partial ]; then
        procd_open_instance failing
        procd_set_param command /bin/false
        procd_set_param respawn 3600 1 1
        procd_close_instance
    fi
}
stop_service() {
    echo stop >> /tmp/bridge-smoke-actions
}
restart() {
    echo custom-restart >> /tmp/bridge-smoke-actions
    stop
    start
}
reload_service() {
    echo reload >> /tmp/bridge-smoke-actions
}
service_triggers() {
    procd_add_reload_trigger bridge_smoke
}
''')
    script.chmod(0o755)
    run('/usr/libexec/openwrt-service-bridge', 'refresh')
    run('systemctl', 'enable', '--now', 'openwrt@bridge-smoke')
    assert run('systemctl', 'is-enabled', 'openwrt@bridge-smoke').stdout.strip() == 'enabled'
    wait_for(lambda: active().returncode == 0, 'fixture running')
    wait_for(lambda: service()['main'].get('systemd_placement') == 'managed',
             'actual daemon placed in its systemd scope')
    assert run('systemctl', 'cat', 'openwrt@bridge-smoke.service', check=False).returncode != 0
    run('systemctl', 'restart', 'openwrt@bridge-smoke')
    actions = Path('/tmp/bridge-smoke-actions')
    assert actions.read_text().splitlines().count('custom-restart') == 1
    count = len(actions.read_text().splitlines())
    time.sleep(3)
    assert len(actions.read_text().splitlines()) == count, 'observer repeated an action'
    run('/etc/init.d/bridge-smoke', 'stop')
    wait_for(lambda: active().stdout.strip() == 'inactive', 'external stop reflected')
    run('/etc/init.d/bridge-smoke', 'start')
    wait_for(lambda: active().returncode == 0, 'external start reflected')
    run('ubus', 'call', 'service', 'event',
        '{"type":"config.change","data":{"package":"bridge_smoke"}}')
    wait_for(lambda: 'reload' in actions.read_text().splitlines(), 'UCI trigger retained')
    pid = service()['main']['pid']
    os.kill(pid, signal.SIGKILL)
    wait_for(lambda: service().get('main', {}).get('pid', pid) != pid, 'procd respawn')
    Path('/tmp/bridge-smoke-partial').touch()
    run('systemctl', 'restart', 'openwrt@bridge-smoke')
    wait_for(lambda: '1/2' in run('systemctl', 'status', 'openwrt@bridge-smoke',
                                 check=False).stdout, 'partial instance failure')
    Path('/tmp/bridge-smoke-partial').unlink()
    run('systemctl', 'restart', 'openwrt@bridge-smoke')
    for _ in range(3):
        wait_for(lambda: bool(service().get('main', {}).get('running')), 'instance running')
        pid = service()['main']['pid']
        os.kill(pid, signal.SIGKILL)
        time.sleep(1.3)
    wait_for(lambda: active().stdout.strip() == 'failed', 'crash loop failure')
    run('systemctl', 'restart', 'openwrt@bridge-smoke')
    wait_for(lambda: active().returncode == 0, 'explicit recovery from crash loop')
    # A read-only user may inspect status but cannot invoke an action.
    code = '''import os
os.setgroups([])
os.setgid(65534)
os.setuid(65534)
os.execv('/usr/bin/systemctl', ['systemctl', 'restart', 'openwrt@bridge-smoke'])
'''
    before = actions.read_text()
    denied = run('python3', '-c', code, check=False)
    assert denied.returncode != 0 and 'require root' in denied.stderr, denied
    assert actions.read_text() == before
    code = code.replace("'restart'", "'status'")
    assert run('python3', '-c', code, check=False).returncode == 0
    pid = service()['main']['pid']
    netifd = run('pidof', 'netifd').stdout.strip()
    run('systemctl', 'disable', '--now', 'openwrt-service-bridge.service')
    assert service()['main']['pid'] == pid
    assert run('pidof', 'netifd').stdout.strip() == netifd
    assert run('systemctl', 'stop', 'openwrt@bridge-smoke', check=False).returncode != 0
    assert service()['main']['pid'] == pid
    run('systemctl', 'enable', '--now', 'openwrt-service-bridge.service')
    wait_for(lambda: active().returncode == 0, 'bridge restart adopts existing service')
    assert service()['main']['pid'] == pid
    run('systemctl', 'disable', 'openwrt@bridge-smoke')
    assert run('systemctl', 'is-enabled', 'openwrt@bridge-smoke', check=False).returncode != 0
    assert service()['main']['pid'] == pid, 'disable unexpectedly stopped daemon'
    run('/etc/init.d/bridge-smoke', 'enable')
    assert run('systemctl', 'is-enabled', 'openwrt@bridge-smoke').returncode == 0
    # Leave the enabled fixture for the explicit reboot/recovery phases.
    print('PASS: real procd actions, custom restart, live health, UCI triggers, '
          'respawn/failure, authorization, shared enablement, and safe bridge shutdown')


if __name__ == '__main__':
    main()
