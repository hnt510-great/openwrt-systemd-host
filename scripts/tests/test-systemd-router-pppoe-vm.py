#!/usr/bin/env python3
"""Validate pure-router UEFI image in KVM: systemd PID 1, failsafe, PPPoE AC, LAN NAT, redial."""
import argparse
import base64
import gzip
import hashlib
import json
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import subprocess
import tempfile
import time


UNWANTED_PACKAGES = (
    'openwrt-desktop', 'gnome-shell', 'flatpak', 'openwrt-flatpak',
    'xdg-desktop-portal', 'podman', 'openwrt-podman-rootless',
    'luci-app-podman', 'distrobox', 'samba4-server', 'luci-app-samba4',
    'wsdd2', 'avahi-dbus-daemon', 'libvirt-daemon', 'qemu-x86_64-softmmu',
    'virt-manager', 'luci-app-qemu', 'video-support', 'openwrt-installer',
)


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def command_output(data, token):
    label = token.encode()
    chunks = re.findall(rb'^DATA_' + label + rb':([A-Za-z0-9+/=]*)$', data, re.M)
    digest = re.search(rb'^HASH_' + label + rb':([a-f0-9]{64})$', data, re.M)
    output = base64.b64decode(b''.join(chunks), validate=True)
    if not digest or hashlib.sha256(output).hexdigest().encode() != digest[1]:
        raise RuntimeError('Guest command output corrupted on serial console')
    return output.decode(errors='replace').replace('\r', '')


class VmGuest:
    def __init__(self, name, work, runtime, base, netargs, memory=1024):
        self.name = name
        self.work = work
        self.runtime = runtime
        self.socket = None
        self.process = None
        self.disk = work / f'{name}.qcow2'
        self.variables = work / f'{name}.vars.fd'
        self.qmp = runtime / f'{name}.qmp'
        if not self.disk.exists():
            subprocess.run(
                ['/usr/bin/qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'raw',
                 '-b', str(base), str(self.disk)],
                check=True,
            )
        if not self.variables.exists():
            shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', self.variables)
        serial = runtime / f'{name}.serial'
        self.output = (work / f'{name}.qemu.log').open('ab')
        args = [
            '/usr/bin/qemu-system-x86_64', '-name', f'openwrt-router-{name}',
            '-machine', 'q35,accel=kvm', '-cpu', 'host', '-m', str(memory), '-smp', '2',
            '-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
            '-drive', f'if=pflash,format=raw,file={self.variables}',
            '-drive', f'if=virtio,format=qcow2,file={self.disk}',
            '-display', 'none', '-vga', 'std',
            '-qmp', f'unix:{self.qmp},server=on,wait=off',
            '-chardev', f'socket,id=serial,path={serial},server=on,wait=off,logfile={work / (name + ".serial.log")},logappend=on',
            '-serial', 'chardev:serial',
            *netargs,
        ]
        try:
            self.process = subprocess.Popen(
                args, stdout=self.output, stderr=subprocess.STDOUT, start_new_session=True
            )
            deadline = time.monotonic() + 240
            while not serial.exists():
                self.alive()
                if time.monotonic() > deadline:
                    raise TimeoutError(f'{name}: serial socket did not appear')
                time.sleep(0.2)
            self.socket = socket.socket(socket.AF_UNIX)
            self.socket.connect(str(serial))
            self.socket.settimeout(1)
            self._wait_prompt(deadline=deadline, wait_ubus=True)
        except BaseException:
            self.close()
            raise

    def alive(self):
        if self.process and self.process.poll() is not None:
            raise RuntimeError(f'{self.name} exited: ' + (self.work / f'{self.name}.qemu.log').read_text())

    def _wait_prompt(self, deadline, wait_ubus=True):
        data = b''
        activated = False
        while time.monotonic() < deadline:
            self.alive()
            try:
                data += self.socket.recv(65536)
            except socket.timeout:
                if activated:
                    self.socket.sendall(b'\n')
                continue
            if b'Please press Enter' in data and not activated:
                self.socket.sendall(b'\n')
                activated = True
            if re.search(rb'root@[^\r\n]*[#%] ', data) or re.search(rb'\r?\n/# ', data):
                break
        else:
            raise TimeoutError(f'{self.name}: console did not reach prompt: '
                               + data[-2000:].decode(errors='replace'))
        self.send_wire(
            "PS1=''; python3 -c 'import termios; a=termios.tcgetattr(0); a[3]&=~termios.ECHO; "
            "termios.tcsetattr(0,0,a)' 2>/dev/null || stty -echo 2>/dev/null || :\n"
        )
        time.sleep(0.2)
        self.run('test "$(id -u)" = 0', timeout=30)
        if wait_ubus:
            self.run('for n in $(seq 1 60); do ubus call system board >/dev/null 2>&1 && exit 0; sleep 2; done; exit 1', timeout=150)

    def send_wire(self, text):
        raw = text.encode()
        for offset in range(0, len(raw), 64):
            self.socket.sendall(raw[offset:offset + 64])
            time.sleep(0.01)

    def reconnect_after_reboot(self, wait_ubus=True, timeout=240):
        deadline = time.monotonic() + timeout
        time.sleep(4)
        self._wait_prompt(deadline=deadline, wait_ubus=wait_ubus)

    def send_raw(self, text):
        self.socket.sendall(text.encode())

    def qmp_reset(self):
        with socket.socket(socket.AF_UNIX) as ctrl:
            ctrl.settimeout(10)
            ctrl.connect(str(self.qmp))
            stream = ctrl.makefile('rwb', buffering=0)
            json.loads(stream.readline())
            for cmd in ({'execute': 'qmp_capabilities'}, {'execute': 'system_reset'}):
                stream.write(json.dumps(cmd).encode() + b'\n')
                while True:
                    reply = json.loads(stream.readline())
                    if 'error' in reply:
                        raise RuntimeError(str(reply['error']))
                    if 'return' in reply:
                        break

    def run(self, command, timeout=60, check=True):
        token = secrets.token_hex(12)
        begin, end = 'BEGIN_' + token, 'END_' + token
        cmd_b64 = base64.b64encode(command.encode()).decode()
        lines = [
            f"printf '\\n{begin}\\n'",
            "umask 077",
            f": > /tmp/vc-{token}.b64",
        ]
        for i in range(0, len(cmd_b64), 120):
            lines.append(f"printf %s {shlex.quote(cmd_b64[i:i + 120])} >> /tmp/vc-{token}.b64")
        lines.extend([
            f"python3 -c \"import base64,pathlib;pathlib.Path('/tmp/vc-{token}.sh').write_bytes(base64.b64decode(pathlib.Path('/tmp/vc-{token}.b64').read_text()))\"",
            f"/bin/sh -e /tmp/vc-{token}.sh > /tmp/vc-{token}.out 2>&1; rc=$?",
            f"python3 -c \"import base64,hashlib,pathlib;d=pathlib.Path('/tmp/vc-{token}.out').read_bytes();b=base64.b64encode(d).decode();print();[print('DATA_{token}:'+b[i:i+76]) for i in range(0,len(b),76)];print('HASH_{token}:'+hashlib.sha256(d).hexdigest())\"",
            f"rm -f /tmp/vc-{token}.b64 /tmp/vc-{token}.sh /tmp/vc-{token}.out",
            f"printf '\\n{end}:%s\\n' \"$rc\"",
        ])
        self.send_wire('\n'.join(lines) + '\n')
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
                output = command_output(data[:match.start()], token)
                rc = int(match[1])
                with (self.work / f'{self.name}.commands.log').open('a') as log:
                    log.write(f'{command}\n{output}\nstatus={rc}\n')
                if check and rc != 0:
                    raise RuntimeError(f'{self.name} command failed ({rc}): {command}\n{output}')
                return (rc, output.strip()) if not check else output.strip()
        raise TimeoutError(f'{self.name} command timed out: {command}\n'
                           + data[-2000:].decode(errors='replace'))

    def upload_file(self, src_path, dest_path):
        b64 = base64.b64encode(Path(src_path).read_bytes()).decode()
        tmp = dest_path + '.b64'
        self.run(f'rm -f {shlex.quote(tmp)} {shlex.quote(dest_path)}')
        for i in range(0, len(b64), 400):
            chunk = b64[i:i + 400]
            self.run(f'printf %s {shlex.quote(chunk)} >> {shlex.quote(tmp)}')
        self.run(
            f"python3 -c \"import base64,pathlib;pathlib.Path({dest_path!r}).write_bytes(base64.b64decode(pathlib.Path({tmp!r}).read_text()))\" && rm -f {shlex.quote(tmp)}"
        )

    def close(self):
        if self.process and self.process.poll() is None:
            if self.socket:
                try:
                    self.socket.sendall(b'sync; /bin/busybox poweroff -f || systemctl poweroff\n')
                    self.process.wait(timeout=15)
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


def extract_base(image, base):
    with gzip.open(image, 'rb') as source, base.open('wb') as target:
        zero = bytes(1024 * 1024)
        while chunk := source.read(1024 * 1024):
            if chunk == zero[:len(chunk)]:
                target.seek(len(chunk), 1)
            else:
                target.write(chunk)
        target.truncate()
    base.chmod(0o400)


def write_guest_text(guest, path, content):
    b64 = base64.b64encode(content.encode()).decode()
    guest.run(
        f"python3 -c \"import base64,pathlib,sys;pathlib.Path({path!r}).write_bytes(base64.b64decode(sys.argv[1]))\" {shlex.quote(b64)}"
    )


def test_coldboot_and_failsafe(base, work, runtime):
    guest = VmGuest('coldboot', work, runtime, base, [], memory=1024)
    try:
        assert guest.run('cat /proc/1/comm') == 'systemd'
        guest.run('findmnt /overlay && touch /etc/router-overlay-write-test && rm /etc/router-overlay-write-test')
        guest.run('systemctl is-active --quiet openwrt-ubusd openwrt-procd openwrt-services sshd')
        guest.run('grep -q "^sudo:" /etc/group && test -f /etc/ssh/ssh_host_ed25519_key && /usr/sbin/sshd -t')
        installed = set(guest.run("apk info").splitlines())
        unwanted = sorted(pkg for pkg in UNWANTED_PACKAGES if pkg in installed)
        assert not unwanted, f'Unwanted packages installed: {unwanted}'
        guest.run('kernelctl check')
        grub = guest.run('cat /boot/grub/grub.cfg')
        assert 'failsafe=true' in grub and 'openwrt.init=' not in grub

        # Test native failsafe recovery entry
        guest.run('kernelctl migrate')
        guest.run('grub-editenv /boot/grub/grubenv set next_entry=owrt-rescue-failsafe && sync')
        guest.send_raw('systemctl reboot\n')
        guest.reconnect_after_reboot(wait_ubus=False, timeout=240)
        cmdline = guest.run('cat /proc/cmdline')
        assert 'failsafe=true' in cmdline, cmdline
        assert guest.run('cat /proc/1/comm') == 'init'
        guest.run('mount_root && findmnt /overlay && echo router-failsafe-ok > /etc/failsafe-check && sync')
        guest.send_raw('reboot\n')
        try:
            guest.reconnect_after_reboot(wait_ubus=True, timeout=90)
            failsafe_reboot = 'plain_reboot'
        except TimeoutError:
            failsafe_reboot = 'qmp_reset'
            guest.qmp_reset()
            guest.reconnect_after_reboot(wait_ubus=True, timeout=240)
        assert guest.run('cat /proc/1/comm') == 'systemd'
        assert guest.run('cat /etc/failsafe-check') == 'router-failsafe-ok'
        return {
            'status': 'passed',
            'installed_package_count': len(installed),
            'kernel': guest.run('uname -r'),
            'failsafe_reboot': failsafe_reboot,
        }
    finally:
        guest.close()


def test_pppoe_and_lan_nat(base, work, runtime, ac_apks):
    wan_port = free_port()
    lan_port = free_port()
    token = secrets.token_hex(24)
    guests = []
    try:
        ac = VmGuest(
            'pppoe-ac', work, runtime, base,
            ['-netdev', f'socket,id=wan,listen=127.0.0.1:{wan_port}',
             '-device', 'virtio-net-pci,netdev=wan,mac=52:54:00:ac:01:01'],
            memory=1024,
        )
        guests.append(ac)
        ac.run('for s in dnsmasq odhcpd firewall; do [ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
        uploaded = []
        for idx, apk in enumerate(ac_apks):
            dest = f'/tmp/ac-pkg-{idx}.apk'
            ac.upload_file(apk, dest)
            uploaded.append(dest)
        ac.run('mkdir -p /tmp/apk-cache && apk add --cache-dir /tmp/apk-cache --no-network --allow-untrusted ' + ' '.join(uploaded))
        write_guest_text(ac, '/etc/config/network', """config interface 'loopback'
 option device 'lo'
 option proto 'static'
 option ipaddr '127.0.0.1'
 option netmask '255.0.0.0'
config interface 'acnet'
 option device 'eth0'
 option proto 'none'
""")
        ac.run('/etc/init.d/network restart; sleep 2; ip link set eth0 up; modprobe pppoe || true')
        write_guest_text(ac, '/etc/ppp/pppoe-server-options', """require-pap
lcp-echo-interval 3
lcp-echo-failure 3
ms-dns 198.51.100.1
noipdefault
default-asyncmap
mtu 1492
mru 1492
""")
        write_guest_text(ac, '/etc/ppp/pap-secrets', '"vm-pppoe-user" * "vm-pppoe-secret" *\n')
        ac.run('chmod 600 /etc/ppp/pap-secrets')
        ac.run('mkdir -p /tmp/ac-www && printf %s ' + shlex.quote(token) + ' > /tmp/ac-www/' + token)
        ac.run('ip addr add 198.51.100.1/32 dev lo 2>/dev/null || true')
        ac.run('python3 -m http.server 8080 --bind 198.51.100.1 --directory /tmp/ac-www >/tmp/ac-http.log 2>&1 < /dev/null &')
        ac.run('pppoe-server -k -I eth0 -L 198.51.100.1 -R 198.51.100.10 -N 10 -C router-test-ac -S isp-test')
        ac.run('pgrep -x pppoe-server')

        router = VmGuest(
            'pppoe-router', work, runtime, base,
            ['-netdev', f'socket,id=lan,listen=127.0.0.1:{lan_port}',
             '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:aa:01:01',
             '-netdev', f'socket,id=wan,connect=127.0.0.1:{wan_port}',
             '-device', 'virtio-net-pci,netdev=wan,mac=52:54:00:aa:01:02'],
            memory=1024,
        )
        guests.append(router)
        assert router.run('cat /proc/1/comm') == 'systemd'
        write_guest_text(router, '/etc/config/network', """config interface 'loopback'
 option device 'lo'
 option proto 'static'
 option ipaddr '127.0.0.1'
 option netmask '255.0.0.0'
config device
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
 option proto 'pppoe'
 option username 'vm-pppoe-user'
 option password 'vm-pppoe-secret'
 option ipv6 '0'
 option keepalive '3 2'
""")
        router.run('/etc/init.d/network restart')
        wan_status = router.run(
            "for n in $(seq 1 45); do "
            "ubus call network.interface.wan status | grep -q '\"up\": true' && "
            "ip -4 route show default | grep -q 'pppoe-wan' && "
            "{ ubus call network.interface.wan status; exit 0; }; sleep 2; done; exit 1",
            timeout=110,
        )
        assert 'pppoe-wan' in wan_status and '198.51.100.' in wan_status
        router.run(
            "uci set dhcp.lan.interface=lan; uci set dhcp.lan.ignore=0; "
            "uci set dhcp.lan.start=100; uci set dhcp.lan.limit=20; "
            "uci add_list dhcp.@dnsmasq[0].address='/pppoe.test/198.51.100.1'; "
            "uci commit dhcp; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart"
        )
        assert router.run('curl -4 --noproxy "*" -fsS --max-time 15 http://198.51.100.1:8080/' + token) == token

        client = VmGuest(
            'pppoe-client', work, runtime, base,
            ['-netdev', f'socket,id=lan,connect=127.0.0.1:{lan_port}',
             '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:aa:02:01'],
            memory=1024,
        )
        guests.append(client)
        client.run('for s in dnsmasq odhcpd firewall; do [ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
        write_guest_text(client, '/etc/config/network', """config interface 'loopback'
 option device 'lo'
 option proto 'static'
 option ipaddr '127.0.0.1'
 option netmask '255.0.0.0'
config interface 'probe'
 option device 'eth0'
 option proto 'dhcp'
""")
        client.run('/etc/init.d/network restart')
        lease = client.run(
            "for n in $(seq 1 40); do "
            "ip -4 addr show dev eth0 | grep -q '192.0.2.1[0-9][0-9]/24' && "
            "ip -4 route | grep -q 'default via 192.0.2.1' && "
            "{ ip -4 addr show dev eth0; ip -4 route; exit 0; }; sleep 2; done; exit 1",
            timeout=100,
        )
        assert '192.0.2.' in lease
        client.run("printf 'nameserver 192.0.2.1\\n' > /tmp/test-resolv.conf && ln -sf /tmp/test-resolv.conf /etc/resolv.conf")
        dns_out = client.run('nslookup -type=A pppoe.test 192.0.2.1')
        assert '198.51.100.1' in dns_out
        assert client.run('curl -4 --noproxy "*" -fsS --max-time 20 http://pppoe.test:8080/' + token) == token

        # Disconnect on AC side and verify Router redials PPPoE and restores LAN NAT
        old_pid = router.run('pgrep -f "pppd.*pppoe" | head -n 1')
        ac.run('killall -TERM pppd')
        router.run(
            f"for n in $(seq 1 45); do "
            f"new_pid=$(pgrep -f 'pppd.*pppoe' | head -n 1 || true); "
            f"if [ -n \"$new_pid\" ] && [ \"$new_pid\" != {shlex.quote(old_pid)} ] && "
            f"ubus call network.interface.wan status | grep -q '\"up\": true' && "
            f"ip -4 route show default | grep -q 'pppoe-wan'; then echo \"$new_pid\"; exit 0; fi; "
            f"sleep 2; done; exit 1",
            timeout=110,
        )
        assert client.run('curl -4 --noproxy "*" -fsS --max-time 20 http://pppoe.test:8080/' + token) == token
        router.run('nft list chain inet fw4 srcnat_wan | grep -q masquerade')
        return {'status': 'passed', 'pppoe_redial': True, 'lan_nat_after_redial': True}
    except BaseException:
        for guest in guests:
            try:
                guest.run('ip link; ip addr; ip route; ubus call network.interface.wan status 2>/dev/null || :; journalctl -b -n 40 --no-pager', timeout=20, check=False)
            except Exception:
                pass
        raise
    finally:
        for guest in reversed(guests):
            guest.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path, required=True)
    parser.add_argument('--work-dir', type=Path, required=True)
    parser.add_argument('--ac-apk', type=Path, nargs='+', required=True)
    args = parser.parse_args()

    work = args.work_dir.resolve()
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    image = args.image.resolve()
    digest = sha256(image)
    receipt = {
        'schema': 1,
        'image': str(image),
        'image_sha256': digest,
        'checks': {},
        'status': 'running',
        'started_at': time.time(),
    }
    result = work / 'validation.json'
    result.write_text(json.dumps(receipt, indent=2) + '\n')

    base = work / 'base.img'
    try:
        extract_base(image, base)
        with tempfile.TemporaryDirectory(prefix='owrt-router-vm-') as temporary:
            runtime = Path(temporary)
            receipt['checks']['coldboot_and_failsafe'] = test_coldboot_and_failsafe(base, work, runtime)
            receipt['checks']['pppoe_ac_and_lan_nat'] = test_pppoe_and_lan_nat(
                base, work, runtime, [p.resolve() for p in args.ac_apk]
            )
        assert sha256(image) == digest, 'Image changed during validation'
        receipt['status'] = 'passed'
    except BaseException as exc:
        receipt['status'] = 'failed'
        receipt['error'] = str(exc)
        raise
    finally:
        receipt['completed_at'] = time.time()
        result.write_text(json.dumps(receipt, indent=2) + '\n')
        for pattern in ('*.qcow2', '*.vars.fd', 'base.img'):
            for path in work.glob(pattern):
                path.unlink(missing_ok=True)
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    main()
