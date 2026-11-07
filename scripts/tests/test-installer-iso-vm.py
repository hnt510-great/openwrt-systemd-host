#!/usr/bin/env python3
"""Install an exact hybrid ISO over USB or CD-ROM, then boot each target alone.

Evidence stays in the required --work directory outside the repository. This
runner only attaches newly created guest disks; it never accepts a host device.
"""
import argparse
import base64
import hashlib
import gzip
import importlib.util
import json
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import struct
import subprocess
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('network_vm', ROOT / 'scripts/test-image-network.py')
network = importlib.util.module_from_spec(spec); spec.loader.exec_module(network)


class Guest(network.Guest):
    def __init__(self, name, work, runtime, disk, iso=None, firmware='ovmf', bus='virtio', password=None, netargs=(), extra=(), media='usb'):
        self.name, self.work = name, work
        self.socket = self.process = None
        self.output = (work / (name + '.qemu.log')).open('ab')
        serial = runtime / (name + '.serial')
        self.qmp = runtime / (name + '.qmp')
        args = ['qemu-system-x86_64', '-name', 'openwrt-installer-' + name, '-machine', 'q35,accel=kvm', '-cpu', 'host', '-m', '4096' if disk else '1536', '-smp', '2', '-display', 'none', '-vga', 'std', '-monitor', 'none', '-qmp', f'unix:{self.qmp},server=on,wait=off', '-no-reboot',
                '-chardev', f'socket,id=serial,path={serial},server=on,wait=off,logfile={work / (name + ".serial.log")},logappend=on', '-serial', 'chardev:serial']
        if firmware == 'ovmf':
            variables = work / (name + '.vars.fd')
            shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
            args += ['-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd', '-drive', 'if=pflash,format=raw,file=' + str(variables)]
        if disk:
            args += ['-drive', f'if=none,id=target,format=qcow2,file={disk}']
            if bus == 'nvme':
                args += ['-device', 'nvme,drive=target,serial=INSTALLTARGET,bootindex=2']
            elif bus == 'sata':
                args += ['-device', 'ide-hd,drive=target,bus=ide.0,bootindex=2']
            else:
                args += ['-device', 'virtio-blk-pci,drive=target,bootindex=2']
        if iso:
            args += ['-drive', f'if=none,id=stick,format=raw,readonly=on,file={iso}']
            if media == 'cdrom':
                args += ['-device', 'ide-cd,drive=stick,bus=ide.1,bootindex=1']
            else:
                args += ['-device', 'qemu-xhci,id=xhci', '-device', 'usb-storage,drive=stick,bootindex=1,removable=on']
        args += list(extra) + list(netargs)
        try:
            self.process = subprocess.Popen(args, stdout=self.output, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 240
            while not serial.exists():
                self.alive(); time.sleep(.1)
                if time.monotonic() > deadline: raise TimeoutError('No serial socket')
            self.socket = socket.socket(socket.AF_UNIX); self.socket.connect(str(serial)); self.socket.settimeout(1)
            data = b''; entered = False; user_sent = False; password_sent = False
            while time.monotonic() < deadline:
                self.alive()
                try: data += self.socket.recv(65536)
                except socket.timeout: continue
                if b'Please press Enter' in data and not entered:
                    self.socket.sendall(b'\n'); entered = True
                if re.search(rb'login: *$', data) and not user_sent:
                    self.socket.sendall(b'root\n'); user_sent = True
                if b'Password:' in data and not password_sent and password:
                    self.socket.sendall(password.encode() + b'\n'); password_sent = True
                if re.search(rb'(root@[^\r\n]*[#%] |/ # )', data): break
            else:
                raise TimeoutError('No guest shell: ' + data[-1500:].decode(errors='replace'))
            # The live ash line editor truncates long framed commands at 512 bytes.
            self.socket.sendall(b'stty -echo; dmesg -n 1; exec /bin/sh +i\n')
            # Let the login terminal reset and live coldplug finish before framing.
            time.sleep(10)
            for attempt in range(3):
                try:
                    self.run('test "$(id -u)" = 0')
                    break
                except RuntimeError as error:
                    if 'corrupted on the console' not in str(error) or attempt == 2:
                        raise
                    time.sleep(2)
        except BaseException:
            self.close(); raise


    def screenshot(self, filename):
        with socket.socket(socket.AF_UNIX) as control:
            control.settimeout(10); control.connect(str(self.qmp))
            stream = control.makefile('rwb', buffering=0)
            json.loads(stream.readline())
            for command in ({'execute': 'qmp_capabilities'},
                            {'execute': 'screendump', 'arguments': {'filename': str(self.work / filename), 'format': 'png'}}):
                stream.write(json.dumps(command).encode() + b'\n')
                while True:
                    reply = json.loads(stream.readline())
                    if 'error' in reply: raise RuntimeError(str(reply['error']))
                    if 'return' in reply: break



def answers(disk, fs, proto, ipv6, user, fullcone, password_hash):
    wan = {'proto': proto}
    if proto == 'static': wan.update(ipaddr='10.0.2.20', netmask='255.255.255.0', gateway='10.0.2.2', dns=['10.0.2.3'])
    if proto == 'pppoe': wan.update(username='vm-test', password='vm-only-secret')
    return {'disk': disk, 'partitions': [{'role': 'boot', 'size_mib': 512}, {'role': 'rom', 'size_mib': 1536}, {'role': 'overlay', 'fs': fs, 'size_mib': None}],
            'network': {'wan_port': 'eth1', 'lan_ports': ['eth0'], 'lan': {'ipaddr': '192.168.71.1', 'netmask': '255.255.255.0', 'dhcp': True, 'start': 100, 'limit': 50}, 'wan': wan, 'ipv6': ipv6},
            'firewall': {'masq': True, 'fullcone': fullcone, 'lan_to_wan': True},
            'accounts': {'root_password_hash': password_hash, 'user': {'name': 'alice', 'password_hash': password_hash, 'gnome_autostart': True} if user else None}}


def combined_regression(image, work):
    work.mkdir()
    raw = work / 'combined.img'
    opener = gzip.open if image.suffix == '.gz' else open
    with opener(image, 'rb') as source, raw.open('wb') as dest:
        # Preserve holes in the large combined root partition.
        while True:
            chunk = source.read(4*1024**2)
            if not chunk: break
            if chunk.count(0) == len(chunk): dest.seek(len(chunk), 1)
            else: dest.write(chunk)
        dest.truncate()
    disk = work / 'system.qcow2'
    subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'raw', '-b', str(raw), str(disk)], check=True)
    net = ['-netdev', 'user,id=lan,restrict=on', '-device', 'e1000,netdev=lan']
    with tempfile.TemporaryDirectory(prefix='owrt-combined-') as runtime:
        guest = Guest('combined', work, Path(runtime), disk, netargs=net)
        try:
            guest.run('test "$(findmnt -nro FSTYPE /overlay)" = f2fs; findmnt /overlay; findmnt /boot')
        finally: guest.close()
    return {'sha256': network.sha256(image), 'internal_f2fs': 'pass'}


def extroot_regression(work, installed_disk, netargs, password):
    """Clone an installed disk and move only that clone to a separate ext4 extroot."""
    work.mkdir()
    disk = work / 'system.qcow2'; extroot = work / 'extroot.qcow2'
    subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', '-F', 'qcow2', '-b', str(installed_disk), str(disk)], check=True)
    subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', str(extroot), '4G'], check=True)
    extra = ['-drive', f'if=none,id=extroot,format=qcow2,file={extroot}', '-device', 'virtio-blk-pci,drive=extroot']
    with tempfile.TemporaryDirectory(prefix='owrt-extroot-') as runtime:
        guest = Guest('prepare', work, Path(runtime), disk, bus='nvme', password=password, netargs=netargs, extra=extra)
        try:
            guest.run('test "$(lsblk -bdno SIZE /dev/vda)" = 4294967296; printf "label: gpt\\n, , L\\n" | sfdisk /dev/vda; partx -u /dev/vda; udevadm settle; mkfs.ext4 -F -L installer_extroot /dev/vda1')
            guest.run('uuid=$(blkid -s UUID -o value /dev/vda1); uci set fstab.installer_extroot=mount; uci set fstab.installer_extroot.target=/overlay; uci set fstab.installer_extroot.uuid="$uuid"; uci set fstab.installer_extroot.enabled=1; uci commit fstab; echo installer-extroot-test > /overlay/installer-preservation; mkdir -p /mnt/installer-extroot; mount /dev/vda1 /mnt/installer-extroot; cp -a /overlay/. /mnt/installer-extroot/; sync; umount /mnt/installer-extroot')
        finally: guest.close()
    with tempfile.TemporaryDirectory(prefix='owrt-extroot-') as runtime:
        guest = Guest('reboot', work, Path(runtime), disk, bus='nvme', password=password, netargs=netargs, extra=extra)
        try:
            guest.run('test "$(findmnt -nro SOURCE /overlay)" = /dev/vda1; test "$(findmnt -nro FSTYPE /overlay)" = ext4; grep -qx installer-extroot-test /overlay/installer-preservation; findmnt /boot; kernelctl list')
        finally: guest.close()
    return 'pass'


def static_checks(iso, work):
    report = subprocess.run(['xorriso', '-indev', str(iso), '-report_el_torito', 'plain'], capture_output=True, text=True, check=True)
    (work / 'el-torito.txt').write_text(report.stdout + report.stderr)
    if 'BIOS' not in report.stdout + report.stderr or 'UEFI' not in report.stdout + report.stderr:
        raise ValueError('Missing hybrid BIOS/UEFI boot entries')
    with iso.open('rb') as f:
        mbr = f.read(512)
        entries = [mbr[446 + n*16:462 + n*16] for n in range(4)]
        if entries[1][4] != 0xef or entries[2][4] != 0x83:
            raise ValueError('Expected MBR p2 ESP and p3 Linux payload')
        offset = struct.unpack_from('<I', entries[2], 8)[0] * 512
    manifest_path = work / 'manifest.json'
    subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', '/install/manifest.json', str(manifest_path)], capture_output=True, check=True)
    manifest = json.loads(manifest_path.read_text())
    config_path = work / 'grub.cfg'
    subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', '/boot/grub/grub.cfg', str(config_path)], capture_output=True, check=True)
    grub = config_path.read_text()
    if grub.count('initrd /boot/installer-initramfs.gz') != 2 or 'noinitrd' in grub:
        raise ValueError('Both installer entries must load the optical bootstrap')
    signature = f'{struct.unpack_from("<I", mbr, 440)[0]:08x}'
    if grub.count('openwrt.installer.signature=' + signature) != 2:
        raise ValueError('GRUB media identity does not match the hybrid MBR')
    bootstrap = work / 'installer-initramfs.gz'
    subprocess.run(['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', '/boot/installer-initramfs.gz', str(bootstrap)], capture_output=True, check=True)
    if b'installer bootstrap:' not in gzip.decompress(bootstrap.read_bytes()):
        raise ValueError('Installer bootstrap missing init')
    digest = hashlib.sha256(); remaining = manifest['squashfs_size']
    with iso.open('rb') as f:
        f.seek(offset)
        while remaining:
            chunk = f.read(min(4*1024**2, remaining))
            if not chunk: raise ValueError('Truncated payload')
            digest.update(chunk); remaining -= len(chunk)
    if digest.hexdigest() != manifest['squashfs_sha256']:
        raise ValueError('Appended payload does not match manifest')
    unsquash = ROOT / 'staging_dir/host/bin/unsquashfs4'
    listing = subprocess.check_output([str(unsquash), '-o', str(offset), '-l', str(iso)], text=True)
    (work / 'squashfs-list.txt').write_text(listing)
    if 'squashfs-root/etc/uci-defaults/99-multiuser' not in listing:
        raise ValueError('Missing tracked multiuser defaults')
    for path in ('etc/uci-defaults/99-zz-example-user', 'etc/uci-defaults/99-zzz-local-settings', 'etc/config/passwall', 'etc/config/network'):
        if 'squashfs-root/' + path in set(listing.splitlines()): raise ValueError('Personal overlay entered ISO: ' + path)
    passwd = subprocess.check_output([str(unsquash), '-o', str(offset), '-cat', str(iso), 'etc/passwd'], text=True)
    if any(line.startswith('example-user:') for line in passwd.splitlines()): raise ValueError('Personal account entered ISO')
    return {'hybrid_boot': 'pass', 'kernel_release': manifest['kernel_release'], 'payload_sha256': digest.hexdigest(), 'clean_rootfs': 'pass', 'mbr_signature': f'{struct.unpack_from("<I", mbr, 440)[0]:08x}'}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iso', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--case', choices=['a', 'b', 'c', 'all'], default='all')
    p.add_argument('--boot-only', action='store_true')
    p.add_argument('--media', choices=['usb', 'cdrom'], default='usb')
    p.add_argument('--static-only', action='store_true')
    p.add_argument('--combined', type=Path, help='Same build combined EFI .img.gz for internal F2FS regression')
    a = p.parse_args(); a.iso = a.iso.resolve(); a.work = a.work.resolve()
    if a.work == ROOT or ROOT in a.work.parents: p.error('--work must be outside the repository')
    a.work.mkdir(parents=True, exist_ok=True)
    receipt = {'iso': str(a.iso), 'sha256': network.sha256(a.iso), 'media': a.media, 'cases': {}}
    receipt['static'] = static_checks(a.iso, a.work)
    if a.static_only:
        (a.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return
    cases = [('a', 'ovmf', 'nvme', 'ext4', 'dhcp', True, True, False), ('b', 'bios', 'sata', 'btrfs', 'static', False, False, False), ('c', 'ovmf', 'virtio', 'xfs', 'pppoe', True, False, True)]
    password = 'Vm-' + secrets.token_hex(8)
    password_hash = subprocess.check_output(['openssl', 'passwd', '-6', '-stdin'], input=password + '\n', text=True).strip()
    try:
        for name, firmware, bus, fs, proto, ipv6, user, fullcone in cases:
            if a.case not in ('all', name): continue
            work = a.work / name; work.mkdir(exist_ok=True)
            disk = work / 'target.qcow2'
            if disk.exists(): raise ValueError('Evidence target already exists: ' + str(disk))
            subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', str(disk), '16G'], check=True)
            with tempfile.TemporaryDirectory(prefix='owrt-iso-') as runtime:
                with socket.socket() as sock:
                    sock.bind(('127.0.0.1', 0)); lan_port = sock.getsockname()[1]
                net = ['-netdev', f'socket,id=lan,listen=127.0.0.1:{lan_port}', '-device', 'e1000,netdev=lan,mac=52:54:00:10:00:01', '-netdev', 'user,id=wan', '-device', 'e1000,netdev=wan,mac=52:54:00:10:00:02']
                live = Guest('live', work, Path(runtime), disk, a.iso, firmware, bus, netargs=net, media=a.media)
                try:
                    live.run('for i in $(seq 1 30); do test -e /sys/class/net/eth1/device && break; sleep 1; done; grep -qw openwrt.installer=1 /proc/cmdline; findmnt -rn -t tmpfs | grep /tmp/root; systemctl is-active openwrt-installer.target; ls /sys/class/net/eth0/device /sys/class/net/eth1/device')
                    receipt['cases'][name] = {'media_boot': 'pass', 'media': a.media}
                    live.screenshot('installer.png')
                    if a.media == 'cdrom':
                        live.run('test "$(findmnt -nro SOURCE /rom)" = /dev/loop0; test "$(cat /sys/class/block/loop0/ro)" = 1; test "$(cat /sys/class/block/loop0/loop/backing_file)" = /dev/sr0')
                    if a.boot_only: continue
                    target = {'nvme': '/dev/nvme0n1', 'sata': '/dev/sda', 'virtio': '/dev/vda'}[bus]
                    # SATA order is discovered rather than assuming the USB enumeration order.
                    listing = json.loads(live.run('lsblk -J -b -o NAME,PATH,SIZE,TYPE,TRAN'))
                    candidates = [d['path'] for d in listing['blockdevices'] if d['type'] == 'disk' and int(d['size']) == 16*1024**3]
                    if len(candidates) != 1: raise RuntimeError('Target disk discovery failed')
                    config = answers(candidates[0], fs, proto, ipv6, user, fullcone, password_hash)
                    encoded = base64.b64encode(json.dumps(config).encode()).decode()
                    live.run('umask 077; echo ' + shlex.quote(encoded) + ' | base64 -d > /tmp/answers.json; openwrt-installer --answers /tmp/answers.json --dry-run')
                    live.run('openwrt-installer --answers /tmp/answers.json', timeout=600)
                    receipt['cases'][name]['installation'] = 'pass'
                finally: live.close()
            if a.boot_only: continue
            with tempfile.TemporaryDirectory(prefix='owrt-disk-') as runtime:
                installed = Guest('installed', work, Path(runtime), disk, firmware=firmware, bus=bus, password=password, netargs=net)
                client = None
                client_runtime = tempfile.TemporaryDirectory(prefix='owrt-client-')
                try:
                    client_net = ['-netdev', f'socket,id=lan,connect=127.0.0.1:{lan_port}', '-device', 'e1000,netdev=lan,mac=52:54:00:10:00:99']
                    client = Guest('client', work, Path(client_runtime.name), None, a.iso, 'bios', netargs=client_net)
                    installed.run('for i in $(seq 1 90); do systemctl is-active openwrt-services.service && break; sleep 2; done')
                    installed.run('for i in $(seq 1 120); do test ! -e /etc/openwrt-installer/firstboot.json && break; sleep 2; done', timeout=260)
                    installed.run('test "$(uname -r)" = ' + shlex.quote(receipt['static']['kernel_release']))
                    installed.run('dev=$(findmnt -nro SOURCE /overlay); dev=$(readlink -f "$dev"); test "$(cat /sys/class/block/${dev##*/}/partition)" = 3')
                    installed.run(f'test "$(findmnt -nro FSTYPE /overlay)" = {fs}; findmnt /overlay; findmnt /boot; kernelctl list; test -z "$(systemctl --failed --no-legend)"')
                    installed.run('! id example-user; test ! -e /etc/openwrt-installer/firstboot.json; test "$(uci -q get passwall.@global[0].enabled)" = 0; ! uci -q show passwall | grep -Fq .address=')
                    if user:
                        installed.run('id alice | grep sudo; for i in $(seq 1 90); do loginctl list-sessions --no-legend | grep "alice.*seat0" && pgrep -u alice -x gnome-shell && exit 0; sleep 2; done; exit 1', timeout=200)
                        time.sleep(5)
                        installed.screenshot('gnome.png')
                        receipt['cases'][name]['gnome'] = 'seat0 and gnome-shell; screenshot recorded'
                    if name == 'a':
                        probe = """import gzip, importlib.machinery, pathlib, platform
m = importlib.machinery.SourceFileLoader('kernelctl_probe', '/usr/sbin/kernelctl').load_module()
p = pathlib.Path('/tmp/installer-bootstrap.gz')
m.KernelManager().bootstrap(platform.release(), p)
data = gzip.decompress(p.read_bytes())
for name in (b'btrfs.ko', b'xfs.ko', b'etc/modules-boot.d/30-fs-btrfs', b'etc/modules-boot.d/30-fs-xfs'):
    assert name in data, name
print('kernelctl bootstrap contains btrfs/xfs modules and early rules')
p.unlink()
"""
                        installed.run('python3 -c ' + shlex.quote(probe), timeout=180)
                        receipt['cases'][name]['bootstrap_modules'] = 'pass'
                    installed.run('test "$(uci get network.wan.proto)" = ' + proto)
                    if proto == 'dhcp':
                        installed.run('for i in $(seq 1 30); do test "$(ubus call network.interface.wan status | jsonfilter -e @.up)" = true && exit 0; sleep 1; done; exit 1')
                    if proto == 'pppoe':
                        installed.run('test "$(uci get network.wan.username)" = vm-test; test "$(uci get network.wan.ipv6)" = auto')
                    if not ipv6:
                        installed.run('test "$(uci get dhcp.lan.ra)" = disabled; test "$(uci get dhcp.lan.dhcpv6)" = disabled; ! uci -q get network.wan6')
                    rules = installed.run('nft list ruleset')
                    if 'masquerade' not in rules or (fullcone and 'masquerade fullcone' not in rules): raise RuntimeError('Missing NAT rule')
                    if not fullcone and 'masquerade fullcone' in rules: raise RuntimeError('Unexpected full-cone NAT')
                    if 'Accept lan to wan forwarding' not in rules: raise RuntimeError('Missing LAN to WAN forwarding')
                    receipt['cases'][name]['installed_boot'] = 'pass'
                    script = '#!/bin/sh\nif [ "$1" = bound ] || [ "$1" = renew ]; then ip addr flush dev eth0; ip addr add "$ip/24" dev eth0; echo "$ip" > /tmp/lease; fi\n'
                    encoded = base64.b64encode(script.encode()).decode()
                    client.run('echo ' + encoded + ' | base64 -d > /tmp/dhcp-script; chmod 700 /tmp/dhcp-script; ip link set eth0 up; udhcpc -i eth0 -n -q -t 10 -T 3 -s /tmp/dhcp-script', timeout=60)
                    lease = client.run('cat /tmp/lease')
                    if not re.fullmatch(r'192\.168\.71\.(?:1[0-4][0-9])', lease): raise RuntimeError('Lease outside requested pool: ' + lease)
                    login = 'code=$(curl --noproxy "*" -k -L -sS --max-time 20 -o /tmp/luci.html -w "%{http_code}" -c /tmp/luci.cookies --data-urlencode luci_username=root --data-urlencode ' + shlex.quote('luci_password=' + password) + ' https://192.168.71.1/cgi-bin/luci/); echo HTTPS_STATUS="$code"; test "$code" = 200; grep -qi luci /tmp/luci.html'
                    client.run(login)
                    askpass = '#!/bin/sh\nprintf "%s\\n" ' + shlex.quote(password) + '\n'
                    encoded = base64.b64encode(askpass.encode()).decode()
                    client.run('echo ' + encoded + ' | base64 -d > /tmp/askpass; chmod 700 /tmp/askpass; SSH_ASKPASS_REQUIRE=force SSH_ASKPASS=/tmp/askpass DISPLAY=:0 ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o PreferredAuthentications=password -n root@192.168.71.1 true')
                    receipt['cases'][name]['lan_client'] = {'dhcp': lease, 'luci_https': 200, 'ssh_password': 'pass'}
                finally:
                    if client is not None:
                        client.close()
                    client_runtime.cleanup()
                    installed.close()
            if name == 'a':
                receipt['extroot_regression'] = extroot_regression(a.work / 'extroot', disk, net, password)
        if a.combined and not a.boot_only:
            receipt['combined_regression'] = combined_regression(a.combined.resolve(), a.work / 'combined')
    finally:
        (a.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
