#!/usr/bin/env python3
"""Exact-image KVM gate on disposable router/client disks; never targets SSH hosts.

The supplied image must contain UCI history and configuration backup support.
"""
import argparse
import gzip
import importlib.util
import json
import re
from pathlib import Path
import shlex
import socket
import sys
import tempfile
import time

HERE = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location('image_network', HERE.parents[1] / 'test-image-network.py')
NET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NET)
CLI = 'uci-history --json '
REQUIRED = {'installed', 'cli-change-captured', 'luci-attribution', 'rpcd-timeout-rollback',
            'client-access-lost', 'automatic-revert', 'client-luci-restored', 'restore-diff',
            'init-reload-scenario', 'init-reload-revert', 'firewall-abort-runtime',
            'boot-revert', 'fresh-disk-backup-restore'}


class PacedSocket:
    """Avoid dropping long serial console commands during busy guest startup."""
    def __init__(self, sock):
        self.sock = sock

    def sendall(self, data):
        for offset in range(0, len(data), 32):
            self.sock.sendall(data[offset:offset + 32])
            time.sleep(0.01)

    def __getattr__(self, name):
        return getattr(self.sock, name)


class Guest(NET.Guest):
    console_ready = False

    def prepare_console(self):
        if not isinstance(self.socket, PacedSocket):
            self.socket = PacedSocket(self.socket)
        # First-boot getty can start ash before the zsh defaults run. Its line
        # editor accepts only 512 bytes, shorter than the harness's hash frame.
        # A short bootstrap selects a noninteractive shell before any long frame.
        token = 'HISTORY_CONSOLE_' + str(time.monotonic_ns())
        self.socket.sendall(b'stty -echo; exec /bin/sh +i\n')
        self.socket.sendall(("printf '\\n" + token + "\\n'\n").encode())
        deadline, data = time.monotonic() + 30, b''
        while time.monotonic() < deadline:
            self.alive()
            try:
                data += self.socket.recv(65536).replace(b'\r', b'')
            except socket.timeout:
                continue
            if ('\n' + token + '\n').encode() in data:
                self.console_ready = True
                return
        raise TimeoutError('Unable to prepare noninteractive guest console')

    def run(self, command, timeout=60):
        if not self.console_ready:
            self.prepare_console()
        return super().run(command, timeout)


def wait_reboot_console(guest, timeout=360):
    deadline = time.monotonic() + timeout
    boot, activated = b'', False
    while time.monotonic() < deadline:
        guest.alive()
        try:
            boot += guest.socket.recv(65536)
        except socket.timeout:
            continue
        if not activated and b'Please press Enter' in boot:
            guest.socket.sendall(b'\n')
            activated, boot = True, b''
            continue
        if activated and re.search(rb'root@[^\r\n]*[#%] ', boot):
            return
    raise TimeoutError('sysupgrade did not reach a fresh serial shell')


def wait(guest, command, timeout=90):
    return guest.run(f'for n in $(seq 1 {timeout // 2}); do if {command}; then exit 0; fi; sleep 2; done; exit 1', timeout=timeout + 30)


def isolate(guest):
    # Only disposable guests: stop disabled personal proxy boot workers before
    # provisioning the test network. Otherwise their delayed hooks race DNS and
    # every fresh test has to wait several minutes for their sleeps to finish.
    guest.run("uci -q set passwall.@global[0].enabled=0 || :; "
              "uci -q set passwall_server.@global[0].enabled=0 || :; "
              "uci -q commit passwall || :; uci -q commit passwall_server || :; "
              "history_boot_workers=$(busybox pgrep -f '[S]99passwall.*boot' || true); "
              "[ -z \"$history_boot_workers\" ] || kill -KILL $history_boot_workers; true")
    NET.disable_external_integrations(guest)


def cli(guest, command):
    data = json.loads(guest.run(CLI + command))
    if not data['ok']:
        raise AssertionError(data['error'])
    return data


def ubus(guest, obj, method, args):
    output = guest.run('ubus call ' + shlex.quote(obj) + ' ' + shlex.quote(method) + ' ' + shlex.quote(json.dumps(args)))
    return json.loads(output or '{}')


def validate(image, work):
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    image = image.resolve()
    digest = NET.sha256(image)
    receipt = dict(schema_version=1, status='running', image=str(image), image_sha256=digest,
                   checks={}, scope='Disposable KVM router and LAN client; no physical device was flashed', started_at=time.time())
    result_file = work / 'validation.json'

    class Checks(dict):
        def __setitem__(self, key, value):
            super().__setitem__(key, value)
            result_file.write_text(json.dumps(receipt, indent=2) + '\n')

    checks, guests = Checks(), []
    receipt['checks'] = checks
    result_file.write_text(json.dumps(receipt, indent=2) + '\n')
    base = work / 'base.img'
    try:
        with gzip.open(image, 'rb') as src, base.open('wb') as dst:
            zero = bytes(1024 * 1024)
            while block := src.read(len(zero)):
                if block == zero[:len(block)]:
                    dst.seek(len(block), 1)
                else:
                    dst.write(block)
            dst.truncate()
        base.chmod(0o400)
        with tempfile.TemporaryDirectory(prefix='uci-history-vm-') as tmp:
            runtime = Path(tmp)
            sock = socket.socket()
            sock.bind(('127.0.0.1', 0))
            port = sock.getsockname()[1]
            sock.close()
            wan = 'user,id=wan,net=10.203.0.0/24,host=10.203.0.2,dns=10.203.0.3,ipv6=off,restrict=on'
            router_net = ['-netdev', f'socket,id=lan,listen=127.0.0.1:{port}',
                          '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ec:01:01',
                          '-netdev', wan, '-device', 'virtio-net-pci,netdev=wan,mac=52:54:00:ec:01:02']
            client_net = ['-netdev', f'socket,id=lan,connect=127.0.0.1:{port}',
                          '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ec:02:01']

            def boot_router():
                guest = Guest('router', work, runtime, base, router_net, 3072)
                guests.append(guest)
                guest.run('dmesg -n 1')
                return guest

            router = boot_router()
            router.run('test -x /usr/sbin/uci-history; test -f /usr/share/rpcd/ucode/luci.uci-history; test "$(cat /proc/1/comm)" = systemd')
            expected_cli = NET.sha256(HERE.parents[2] / 'package/custom/uci-history/files/uci-history')
            actual_cli = router.run('sha256sum /usr/sbin/uci-history').split()[0]
            if actual_cli != expected_cli:
                raise AssertionError('Image CLI differs from the checkout under test')
            receipt['cli_sha256'] = actual_cli
            receipt['guest_kernel'] = router.run('uname -r')
            checks['installed'] = True
            isolate(router)
            router.run(NET.network_config())
            router.run('uci set dhcp.lan.interface=lan; uci set dhcp.lan.ignore=0; uci commit dhcp; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart')
            wait(router, 'systemctl is-active --quiet uci-history-events.service && systemctl is-active --quiet uci-history.path')
            cli(router, 'snapshot --source boot')
            client = Guest('client', work, runtime, base, client_net, 2048)
            guests.append(client)
            isolate(client)
            client.run('systemctl stop uci-history.path uci-history-sweep.timer; for s in daed dnsmasq odhcpd firewall; do [ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
            client.run(NET.network_config(client=True))
            client.run('ip addr add 192.0.2.2/24 dev eth0 || true')
            # Current LuCI deliberately serves its login form with HTTP 403.
            # Accept that authenticated endpoint's explicit login-required header,
            # never a generic forbidden/error page or a mere open HTTP socket.
            curl = ('( code=$(curl --noproxy "*" -kLsS --max-time 4 '
                    '-D /tmp/history-luci.headers -o /tmp/history-luci.html '
                    '-w "%{http_code}" http://192.0.2.1/cgi-bin/luci/) && '
                    '{ [ "$code" = 200 ] || { [ "$code" = 403 ] && '
                    'grep -qi "^X-LuCI-Login-Required: yes" /tmp/history-luci.headers; }; } && '
                    'grep -qi "<html" /tmp/history-luci.html )')
            wait(client, curl)
            router.run("uci set system.@system[0].hostname=history-cli; uci commit system")
            wait(router, CLI + 'status | grep -q \'"drift": false\'')
            # The watcher cannot distinguish libuci CLI from an editor: no hint => external.
            checks['cli-change-captured'] = cli(router, 'log --config system --limit 1')['revisions'][0]['source'] == 'external'
            session = ubus(router, 'session', 'create', {})['ubus_rpc_session']
            ubus(router, 'session', 'set', dict(ubus_rpc_session=session, values=dict(username='vm-operator')))
            for scope, objects in [('uci', [['system', 'read'], ['system', 'write']]), ('ubus', [['uci', '*']])]:
                ubus(router, 'session', 'grant', dict(ubus_rpc_session=session, scope=scope, objects=objects))
            values = ubus(router, 'uci', 'get', dict(config='system', type='system'))['values']
            section = next(iter(values))
            ubus(router, 'uci', 'set', dict(ubus_rpc_session=session, config='system', section=section, values=dict(hostname='history-luci')))
            ubus(router, 'uci', 'apply', dict(ubus_rpc_session=session, rollback=True, timeout=10))
            wait(router, CLI + 'log --config system --limit 1 | grep -q \'"actor": "vm-operator"\'', 8)
            rev = cli(router, 'log --config system --limit 1')['revisions'][0]
            checks['luci-attribution'] = rev['source'] == 'luci' and rev['actor'] == 'vm-operator'
            wait(router, 'test "$(uci get system.@system[0].hostname)" = history-cli', 30)
            wait(router, CLI + 'log --config system --limit 1 | grep -q \'"source": "rpcd-rollback"\'', 20)
            checks['rpcd-timeout-rollback'] = True
            # rpcd restores its own saved deltas; discard that test session before transaction tests.
            ubus(router, 'session', 'destroy', dict(ubus_rpc_session=session))
            cli(router, 'begin --timeout 60 --actor vm-client --note lan-recovery')
            router.run('uci set network.lan.ipaddr=192.0.2.9; uci commit network; reload_config')
            wait(client, '! ' + curl, 20)
            checks['client-access-lost'] = True
            wait(router, 'test "$(uci get network.lan.ipaddr)" = 192.0.2.1', 90)
            checks['automatic-revert'] = cli(router, 'status')['transaction'] is None
            wait(client, curl, 45)
            checks['client-luci-restored'] = True
            # Regression for the reverted-file/running-service split: apply the
            # change with the init script, which leaves reload_config's checksum
            # baseline at the checkpoint content.
            cli(router, 'begin --timeout 60 --actor vm-client --note init-reload-recovery')
            baseline = router.run('cat /var/run/config.md5')
            router.run('uci set network.lan.ipaddr=192.0.2.9; uci commit network; /etc/init.d/network reload')
            wait(client, '! ' + curl, 30)
            checks['init-reload-scenario'] = (router.run('cat /var/run/config.md5') == baseline and
                                              '192.0.2.9' in router.run('ubus call network.interface.lan status'))
            wait(router, CLI + 'status | grep -q \'"transaction": null\'', 90)
            # Check the running interface, not only the UCI file.
            wait(router, 'ubus call network.interface.lan status | grep -q \'"address": "192.0.2.1"\'', 45)
            wait(client, curl, 45)
            checks['init-reload-revert'] = True
            # Same split for another service, through an explicit abort.
            if router.run('uci get firewall.@zone[0].name').strip() != 'lan':
                raise AssertionError('firewall zone 0 is not lan')
            cli(router, 'begin --timeout 300 --actor vm-client --note firewall-abort')
            router.run('uci set firewall.@zone[0].input=REJECT; uci commit firewall; /etc/init.d/firewall reload')
            wait(client, '! ' + curl, 30)
            cli(router, 'abort')
            wait(client, curl, 45)
            # wait() raises unless the client reaches LuCI through the reloaded firewall.
            checks['firewall-abort-runtime'] = router.run('uci get firewall.@zone[0].input').strip() == 'ACCEPT'
            checkpoint = cli(router, 'snapshot')['revision']
            router.run("uci set system.@system[0].hostname=history-restore; uci commit system")
            cli(router, f'restore {checkpoint} --config system')
            checks['restore-diff'] = not cli(router, f'diff {checkpoint} --config system')['changes']
            cli(router, 'begin --timeout 300 --note boot-recovery')
            router.run("uci set system.@system[0].hostname=history-boot; uci commit system; sync")
            client.close()
            guests.remove(client)
            router.close()
            guests.remove(router)
            router = boot_router()
            wait(router, 'test "$(uci get system.@system[0].hostname)" = history-cli', 180)
            checks['boot-revert'] = cli(router, 'status')['transaction'] is None
            before = cli(router, 'snapshot')['revision']
            oid = cli(router, 'log --limit 1')['revisions'][0]['oid']
            router.run('sysupgrade -l | grep -q etc/uci-history/repo')
            router.run('sysupgrade -b /tmp/history-backup.tar.gz')
            digest_backup = router.run('sha256sum /tmp/history-backup.tar.gz').split()[0]
            blocks = int(router.run("wc -c </tmp/history-backup.tar.gz"))
            # Transfer via bounded serial frames into a clean disk booted from the same image.
            payload = [router.run(f'dd if=/tmp/history-backup.tar.gz bs=1024 skip={i} count=1 2>/dev/null | base64 | tr -d "\\n"')
                       for i in range((blocks + 1023) // 1024)]
            router.close()
            guests.remove(router)
            router = Guest('restored', work, runtime, base, router_net, 3072)
            guests.append(router)
            router.run('umask 077; : >/tmp/history-backup.tar.gz')
            for block in payload:
                for offset in range(0, len(block), 256):
                    router.run(f'printf %s {shlex.quote(block[offset:offset + 256])} | base64 -d >>/tmp/history-backup.tar.gz')
            router.run(f'echo {shlex.quote(digest_backup + "  /tmp/history-backup.tar.gz")} | sha256sum -c -')
            router.run('systemctl stop uci-history.path uci-history-events.service uci-history-sweep.timer')
            router.run('sysupgrade -r /tmp/history-backup.tar.gz && rm -f /tmp/history-backup.tar.gz')
            restored = cli(router, 'log --limit 100')['revisions']
            checks['fresh-disk-backup-restore'] = (cli(router, 'status')['head'] >= before and
                                                   any(row['oid'] == oid for row in restored) and
                                                   router.run('stat -c %a /etc/uci-history') == '700')
            if not all(checks.values()):
                raise AssertionError('Failed checks: ' + str([k for k, v in checks.items() if not v]))
            missing = REQUIRED - checks.keys()
            receipt['missing_checks'] = sorted(missing)
            receipt['status'] = 'incomplete' if missing else 'passed'
            assert NET.sha256(image) == digest, 'Image changed during test'
    except BaseException as e:
        receipt.update(status='failed', error=str(e))
        for guest in guests:
            try:
                guest.run('ip -br -4 address; ip -4 route; '
                          'systemctl --no-pager --full status uci-history-boot.service uci-history-events.service uci-history.path || true; systemctl --no-pager list-units "openwrt-uhttpd@*" || true; '
                          'cat /tmp/history-luci.headers 2>/dev/null || true; '
                          'journalctl -b -u uci-history-boot.service -u uci-history-events.service -u uci-history-snapshot.service -n 30 --no-pager || true', timeout=30)
            except Exception:
                pass
        raise
    finally:
        for guest in reversed(guests):
            guest.close()
        receipt['completed_at'] = time.time()
        (work / 'validation.json').write_text(json.dumps(receipt, indent=2) + '\n')
        if receipt['status'] != 'failed':
            for name in ('router.qcow2', 'client.qcow2', 'router.vars.fd', 'client.vars.fd', 'restored.qcow2', 'restored.vars.fd', 'base.img'):
                (work / name).unlink(missing_ok=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--work-dir', type=Path)
    args = parser.parse_args()
    if not args.image or not args.work_dir:
        parser.error('--image and --work-dir are required')
    result = validate(args.image, args.work_dir.resolve())
    print(json.dumps(result, indent=2))
    sys.exit(0 if result['status'] == 'passed' else 1)
