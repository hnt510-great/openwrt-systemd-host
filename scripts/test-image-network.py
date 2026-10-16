#!/usr/bin/env python3
"""Boot an exact image and a LAN client on private QEMU networks; emit a receipt."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import sys
import tempfile
import time

REQUIRED = {'native-init', 'router-services', 'wan-dhcp', 'lan-dhcp', 'dns',
            'routing-nat', 'luci-http', 'luci-auth', 'ubus-board'}


def sha256(path):
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def wan_response(token):
    """QEMU guestfwd runs one private responder per TCP connection."""
    first = sys.stdin.buffer.readline(8192).decode('ascii', errors='replace').split()
    total = 0
    while total < 65536:
        line = sys.stdin.buffer.readline(8192)
        total += len(line)
        if line in (b'\r\n', b'\n', b''):
            break
    found = len(first) == 3 and first[0] == 'GET' and first[1] == '/' + token
    body = token.encode() if found else b'Not found'
    status = '200 OK' if found else '404 Not Found'
    sys.stdout.buffer.write((f'HTTP/1.1 {status}\r\nContent-Length: {len(body)}\r\n'
                             'Connection: close\r\n\r\n').encode() + body)
    sys.stdout.buffer.flush()


class Guest:
    def __init__(self, name, work, runtime, base, netargs, memory):
        self.name, self.work = name, work
        self.socket = None
        self.process = None
        disk, variables = work / (name + '.qcow2'), work / (name + '.vars.fd')
        subprocess.run(['/usr/bin/qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'raw',
                        '-b', str(base), str(disk)], check=True)
        shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
        serial = runtime / (name + '.serial')
        self.output = (work / (name + '.qemu.log')).open('wb')
        args = ['/usr/bin/qemu-system-x86_64', '-name', 'openwrt-scheduled-' + name,
            '-machine', 'q35,accel=kvm', '-cpu', 'host', '-m', str(memory), '-smp', '2',
            '-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
            '-drive', 'if=pflash,format=raw,file=' + str(variables),
            '-drive', 'if=virtio,format=qcow2,file=' + str(disk),
            '-display', 'none', '-vga', 'std', '-monitor', 'none',
            '-chardev', f'socket,id=serial,path={serial},server=on,wait=off,logfile={work / (name + ".serial.log")}',
            '-serial', 'chardev:serial', *netargs]
        try:
            self.process = subprocess.Popen(args, stdout=self.output, stderr=subprocess.STDOUT,
                                            start_new_session=True)
            deadline = time.monotonic() + 240
            while not serial.exists():
                self.alive()
                if time.monotonic() > deadline:
                    raise TimeoutError('Serial socket did not appear')
                time.sleep(.2)
            self.socket = socket.socket(socket.AF_UNIX)
            self.socket.connect(str(serial))
            self.socket.settimeout(1)
            data = b''
            activated = False
            while time.monotonic() < deadline:
                self.alive()
                try:
                    data += self.socket.recv(65536)
                except socket.timeout:
                    continue
                if b'Please press Enter' in data and not activated:
                    self.socket.sendall(b'\n')
                    activated = True
                if re.search(rb'root@[^\r\n]*[#%] ', data):
                    break
            else:
                raise TimeoutError('Guest console did not reach login: ' + data[-2000:].decode(errors='replace'))
            self.run('stty -echo; test "$(id -u)" = 0', timeout=30)
            self.run('for n in $(seq 1 60); do ubus call system board >/dev/null 2>&1 && exit 0; sleep 2; done; exit 1', timeout=150)
        except BaseException:
            self.close()
            raise

    def alive(self):
        if self.process and self.process.poll() is not None:
            raise RuntimeError(self.name + ' exited: ' + (self.work / (self.name + '.qemu.log')).read_text())

    def run(self, command, timeout=60):
        token = secrets.token_hex(12)
        begin, end = 'BEGIN_' + token, 'END_' + token
        wire = "printf '\\n" + begin + "\\n'; /bin/sh -ec " + shlex.quote(command) + "; rc=$?; printf '\\n" + end + ":%s\\n' \"$rc\"\n"
        self.socket.sendall(wire.encode())
        data = b''
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.alive()
            try:
                data += self.socket.recv(65536).replace(b'\r', b'')
            except socket.timeout:
                continue
            match = re.search(rb'\r?\n' + end.encode() + rb':(\d+)\r?\n', data)
            if match:
                start = re.search(rb'\r?\n' + begin.encode() + rb'\r?\n', data)
                output = data[start.end() if start else 0:match.start()].decode(errors='replace').replace('\r', '')
                with (self.work / (self.name + '.commands.log')).open('a') as log:
                    log.write(command + '\n' + output + '\nstatus=' + match[1].decode() + '\n')
                if int(match[1]):
                    raise RuntimeError(self.name + ' command failed: ' + command + '\n' + output)
                return output.strip()
        raise TimeoutError(self.name + ' command timed out: ' + command + '\n' + data[-2000:].decode(errors='replace'))

    def close(self):
        if self.process and self.process.poll() is None:
            if self.socket:
                try:
                    self.socket.sendall(b'sync; systemctl poweroff\n')
                    self.process.wait(timeout=20)
                except (OSError, subprocess.TimeoutExpired):
                    self.process.terminate()
            try:
                self.process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.socket:
            self.socket.close()
        self.output.close()


def network_config(client=False):
    # Guest-only files: source overlays and the physical router remain untouched.
    network = """config interface 'loopback'
 option device 'lo'
 option proto 'static'
 option ipaddr '127.0.0.1'
 option netmask '255.0.0.0'
"""
    network += ("""config interface 'probe'
 option device 'eth0'
 option proto 'dhcp'
""" if client else """config device
 option name 'br-lan'
 option type 'bridge'
 list ports 'eth0'
config interface 'lan'
 option device 'br-lan'
 option proto 'static'
 option ipaddr '192.0.2.1'
 option netmask '255.255.255.0'
config interface 'wan'
 option device 'eth1'
 option proto 'dhcp'
""")
    encoded = __import__('base64').b64encode(network.encode()).decode()
    return ('printf %s ' + shlex.quote(encoded) + ' | base64 -d > /etc/config/network; '
            '/etc/init.d/network restart')


def disable_external_integrations(guest):
    guest.run("uci -q set passwall.@global[0].enabled=0 || :; "
              "uci -q set passwall.@global[0].enabled_acl=0 || :; "
              "uci -q set passwall.@global[0].acl_enable=0 || :; "
              "uci -q set passwall_server.@global[0].enabled=0 || :; "
              "uci -q set passwall_server.@global[0].enable=0 || :; "
              "uci -q commit passwall || :; uci -q commit passwall_server || :; "
              "for s in passwall passwall_server ddns-go acme sqm; do "
              "[ ! -x /etc/init.d/$s ] || { /etc/init.d/$s disable; /etc/init.d/$s stop; }; done; true")
    # Disabling an init script does not cancel a boot_func already sleeping in
    # the background. Let those guest-only workers finish before provisioning
    # DHCP/DNS; their stop/restart hooks otherwise race the test configuration.
    guest.run("for n in $(seq 1 180); do busybox pgrep -f '[S]99passwall.*boot' > /dev/null || exit 0; "
              "sleep 1; done; exit 1", timeout=200)
    guest.run("for s in passwall passwall_server; do "
              "[ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true")


def test_image(image, work):
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    image = image.resolve()
    digest = sha256(image)
    receipt = {'schema': 1, 'image': str(image), 'image_sha256': digest,
               'checks': {}, 'status': 'running', 'started_at': time.time()}
    result = work / 'validation.json'
    result.write_text(json.dumps(receipt, indent=2))
    token = secrets.token_hex(24)

    base = work / 'base.img'
    guests = []
    try:
        # Sparse extraction retains the exact raw image while avoiding zero-filled allocations.
        with gzip.open(image, 'rb') as source, base.open('wb') as target:
            zero = bytes(1024 * 1024)
            while chunk := source.read(1024 * 1024):
                if chunk == zero[:len(chunk)]:
                    target.seek(len(chunk), 1)
                else:
                    target.write(chunk)
            target.truncate()
        base.chmod(0o400)
        with tempfile.TemporaryDirectory(prefix='owrt-smoke-') as temporary:
            runtime = Path(temporary)
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            lan_port = listener.getsockname()[1]
            listener.close()
            responder = shlex.join([sys.executable, str(Path(__file__).resolve()), '--wan-response', token])
            wan = ('user,id=wan,net=10.203.0.0/24,host=10.203.0.2,dns=10.203.0.3,'
                   'ipv6=off,restrict=on,guestfwd=tcp:10.203.0.100:8080-cmd:' + responder)
            router = Guest('router', work, runtime, base,
                ['-netdev', f'socket,id=lan,listen=127.0.0.1:{lan_port}',
                 '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ed:01:01',
                 '-netdev', wan, '-device', 'virtio-net-pci,netdev=wan,mac=52:54:00:ed:01:02'], 2048)
            guests.append(router)
            receipt['checks']['native-init'] = router.run('test "$(cat /proc/1/comm)" = systemd; cat /proc/1/comm') == 'systemd'
            router.run('systemctl is-active --quiet openwrt-procd openwrt-services')
            receipt['checks']['router-services'] = True
            # Disable external integrations only inside this disposable VM.
            disable_external_integrations(router)
            router.run(network_config())
            router.run("for n in $(seq 1 40); do ubus call network.interface.wan status | grep -q '\"up\": true' && ip -4 addr show dev br-lan | grep -q '192.0.2.1/24' && exit 0; sleep 2; done; exit 1", timeout=100)
            router.run("uci set dhcp.lan.interface=lan; uci set dhcp.lan.ignore=0; uci set dhcp.lan.start=100; uci set dhcp.lan.limit=20; uci add_list dhcp.@dnsmasq[0].address='/scheduler.test/10.203.0.100'; uci commit dhcp; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart")
            router.run("for n in $(seq 1 30); do nslookup -type=A scheduler.test 127.0.0.1 > /tmp/scheduler-dns-ready.log 2>&1 && exit 0; sleep 1; done; cat /tmp/scheduler-dns-ready.log; exit 1", timeout=90)
            receipt['checks']['wan-dhcp'] = True
            # Prove the isolated WAN endpoint is usable before involving the LAN client.
            assert router.run('curl --noproxy "*" -fsS --max-time 15 http://10.203.0.100:8080/' + token) == token
            client = Guest('client', work, runtime, base,
                ['-netdev', f'socket,id=lan,connect=127.0.0.1:{lan_port}',
                 '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ed:02:01'], 1536)
            guests.append(client)
            disable_external_integrations(client)
            client.run('for s in passwall passwall_server dnsmasq odhcpd firewall; do [ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
            client.run(network_config(client=True))
            lease = client.run("for n in $(seq 1 40); do ip -4 addr show dev eth0 | grep -q '192.0.2.1[0-9][0-9]/24' && ip -4 route | grep -q 'default via 192.0.2.1' && { ip -4 addr show dev eth0; ip -4 route; exit 0; }; sleep 2; done; exit 1", timeout=100)
            receipt['checks']['lan-dhcp'] = '192.0.2.' in lease
            # The client image normally points resolv.conf at its own dnsmasq,
            # which was stopped to turn this second router image into a client.
            # Use the DNS server actually advertised by the router's DHCP lease.
            client_status = json.loads(client.run('ubus call network.interface.probe status'))
            assert client_status['dns-server'] == ['192.0.2.1']
            client.run("printf 'nameserver 192.0.2.1\\n' > /tmp/scheduler-resolv.conf; "
                       "ln -sf /tmp/scheduler-resolv.conf /etc/resolv.conf")
            dns = client.run('nslookup -type=A scheduler.test 192.0.2.1')
            assert '10.203.0.100' in dns
            receipt['checks']['dns'] = True
            router.run("nft list chain inet fw4 srcnat_wan; cat /proc/sys/net/ipv4/ip_forward; "
                       "test \"$(cat /proc/sys/net/ipv4/ip_forward)\" = 1")
            router.run("tcpdump -nli any 'tcp port 8080' > /tmp/scheduler-flow.log 2>&1 < /dev/null & "
                       "echo $! > /tmp/scheduler-flow.pid")
            assert client.run('curl -4 --noproxy "*" -fsS --max-time 20 http://scheduler.test:8080/' + token) == token
            router.run("nft list chain inet fw4 srcnat_wan | grep -q masquerade; test \"$(cat /proc/sys/net/ipv4/ip_forward)\" = 1")
            receipt['checks']['routing-nat'] = True
            password = secrets.token_urlsafe(24)
            router.run('printf %s ' + shlex.quote('root:' + password + '\n') + ' | chpasswd')

            def rpc(session, obj, method, arguments):
                body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'call',
                                   'params': [session, obj, method, arguments]})
                output = client.run('curl --noproxy "*" -fsS --max-time 20 -H "Content-Type: application/json" --data ' +
                                    shlex.quote(body) + ' http://192.0.2.1/ubus')
                value = json.loads(output)
                if 'error' in value or value['result'][0] != 0:
                    raise RuntimeError('LuCI RPC failed: ' + output)
                return value['result'][1]

            session = rpc('0' * 32, 'session', 'login', {'username': 'root', 'password': password})['ubus_rpc_session']
            assert re.fullmatch('[0-9a-f]{32}', session)
            rpc(session, 'uci', 'get', {'config': 'system'})
            receipt['checks']['luci-auth'] = True
            # LuCI deliberately returns 403 for its unauthenticated login form.
            # Exercise the actual web login and follow its authenticated redirect.
            html = client.run('curl --noproxy "*" -fsSL --max-time 20 '
                '-c /tmp/scheduler-luci.cookies --data-urlencode luci_username=root '
                '--data-urlencode ' + shlex.quote('luci_password=' + password) +
                ' http://192.0.2.1/cgi-bin/luci/')
            assert 'luci' in html.lower()
            receipt['checks']['luci-http'] = True
            board = rpc(session, 'system', 'board', {})
            assert board['release']['target'] == 'x86/64'
            receipt['checks']['ubus-board'] = True
            receipt['guest_kernel'] = board['kernel']
            receipt['guest_release'] = board['release']
            assert set(receipt['checks']) == REQUIRED and all(receipt['checks'].values())
            assert sha256(image) == digest, 'Image changed during validation'
            receipt['status'] = 'passed'
    except BaseException as error:
        receipt.update(status='failed', error=str(error))
        for guest in guests:
            try:
                guest.run("ubus call service list '{\"name\":\"dnsmasq\"}'; "
                          "ss -lntup; uci show dhcp; ip -4 route; "
                          "cat /proc/sys/net/ipv4/ip_forward; nft list table inet fw4; "
                          "cat /tmp/scheduler-flow.log 2>/dev/null || :; "
                          "logread -l 100 2>/dev/null || :; "
                          "journalctl -b -n 100 --no-pager", timeout=15)
            except Exception:
                pass
        raise
    finally:
        for guest in reversed(guests):
            guest.close()
        receipt['completed_at'] = time.time()
        result.write_text(json.dumps(receipt, indent=2) + '\n')
        # Keep logs and the receipt; test disks are disposable, including on failure.
        for pattern in ('*.qcow2', '*.vars.fd', 'base.img'):
            for path in work.glob(pattern):
                path.unlink(missing_ok=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--wan-response', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.wan_response:
        wan_response(args.wan_response)
    elif not args.image or not args.work_dir:
        parser.error('--image and --work-dir are required')
    else:
        print(json.dumps(test_image(args.image, args.work_dir.resolve()), indent=2))
