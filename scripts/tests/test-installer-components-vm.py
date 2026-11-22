#!/usr/bin/env python3
"""Disposable KVM acceptance for component-selectable installer ISO.

Covers:
  - Static ISO checks: format_version 2 manifest, signed offline repo, public key
    only, clean base squashfs (router/ops retained, zero component/personal leaks).
  - Four VM install + cold-boot cases across BIOS/UEFI, USB/CD-ROM, ext4/btrfs/xfs:
      1. base_only (ovmf, usb, nvme, ext4) + native failsafe recovery + kernelctl check
      2. gnome_core (bios, cdrom, sata, btrfs, gnome only, no autostart -> manual start + portal/PipeWire)
      3. full_desktop (ovmf, usb, virtio, xfs, omitted components -> all 9, autostart GNOME + Audio/IME/RDP/Sunshine/Flatpak/AppImage/virt-manager/Podman)
      4. headless_virt_containers (bios, cdrom, virtio, ext4, virtualization+containers, virsh + rootless podman, no GNOME/virt-manager)
  - LAN client DHCP, LuCI HTTPS 200, SSH password login on each case.
  - Rolling feed refresh + apk update + apk upgrade against a local HTTP mirror of
    the current build (plus kernelctl multi-generation boot/bless/fallback when gen-70
    kernel APK is available), verifying unselected components are never pulled back.
  - Same-build combined EFI image internal F2FS regression.

All evidence stays in --work outside the repository. Never touches the router.
"""
import argparse
import base64
import functools
import gzip
import hashlib
import http.server
import importlib.util
import json
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('installer_iso_vm', ROOT / 'scripts/tests/test-installer-iso-vm.py')
iso_vm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(iso_vm)
network = iso_vm.network
bap_spec = importlib.util.spec_from_file_location('build_and_publish', ROOT / 'scripts/build-and-publish.py')
bap = importlib.util.module_from_spec(bap_spec)
bap_spec.loader.exec_module(bap)


def start_feed_server(docroot, port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(docroot))
    # Suppress noisy per-request stderr logs.
    handler.log_message = lambda *args, **kwargs: None
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def build_local_feed(work_feed, port):
    """Stage a temporary signed feed tree from bin/systemd without touching /srv."""
    if work_feed.exists():
        shutil.rmtree(work_feed)
    work_feed.mkdir(parents=True, exist_ok=True)
    apk = ROOT / 'staging_dir/host/bin/apk'
    stage = work_feed / 'stage'
    stage.mkdir()
    userspace, channel, abi, _ = bap.project(ROOT, stage, apk)
    base_url = f'http://10.0.2.2:{port}'
    subprocess.run([
        'python3', str(ROOT / 'scripts/publish-lan-apk-feeds.py'),
        '--destination', str(work_feed),
        '--base-url', base_url,
        '--source-root', str(userspace),
        '--kernel', abi,
        '--kernel-upgrade-view',
    ], check=True)
    # Publish generation 70 first (if present in /srv/openwrt-feeds) so the local
    # kernel channel holds two real generations for kernelctl upgrade/rollback tests.
    srv_ku = Path('/srv/openwrt-feeds/public/kernel-upgrades')
    srv_manifest = srv_ku / 'manifest.json'
    if srv_manifest.is_file():
        m = json.loads(srv_manifest.read_text())
        if 'linux-image-7.3.5-70-openwrt' in m.get('images', {}):
            gen70 = work_feed / 'gen70'
            gen70.mkdir()
            for fname, entry in m['packages'].items():
                name = entry['info']['name']
                if name in ('linux-image-7.3.5-70-openwrt', 'linux-headers-7.3.5-70-openwrt') or (
                    name in ('linux-image-openwrt', 'kernel-dev-headers') and entry['info']['version'].endswith('-r70')
                ) or (
                    not name.startswith(('linux-', 'kernel-dev-headers'))
                ):
                    src = srv_ku / fname
                    if src.is_file():
                        shutil.copy2(src, gen70 / fname)
            subprocess.run([
                'python3', str(ROOT / 'scripts/publish-kernel-upgrade-feed.py'),
                '--source', str(gen70),
                '--destination', str(work_feed),
            ], check=True)
    subprocess.run([
        'python3', str(ROOT / 'scripts/publish-kernel-upgrade-feed.py'),
        '--source', str(channel),
        '--destination', str(work_feed),
    ], check=True)
    return work_feed / 'public'


def static_checks(iso, work):
    base = iso_vm.static_checks(iso, work)
    manifest = json.loads((work / 'manifest.json').read_text())
    if manifest.get('format_version') != 2:
        raise ValueError(f"Expected manifest format_version=2, got {manifest.get('format_version')}")
    comp_dir = work / 'extracted-components'
    if comp_dir.exists():
        shutil.rmtree(comp_dir)
    comp_dir.mkdir(parents=True)
    subprocess.run(
        ['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', '/install/components', str(comp_dir)],
        capture_output=True, check=True,
    )
    for p in comp_dir.rglob('*'):
        if p.is_file() and 'private' in p.name.lower():
            raise ValueError(f'Private key material leaked into ISO: {p}')
    comp_json = comp_dir / 'components.json'
    repo_index = comp_dir / 'repo/packages.adb'
    pub_keys = list((comp_dir / 'keys').glob('*.pem'))
    if not comp_json.is_file() or not repo_index.is_file() or not pub_keys:
        raise ValueError('Missing components.json, repo/packages.adb, or public key in ISO')
    if network.sha256(comp_json) != manifest['components_sha256']:
        raise ValueError('components_sha256 mismatch in manifest')
    if network.sha256(repo_index) != manifest['repo_index_sha256']:
        raise ValueError('repo_index_sha256 mismatch in manifest')
    catalog = json.loads(comp_json.read_text())

    with iso.open('rb') as f:
        f.seek(446 + 2 * 16 + 8)
        offset = struct.unpack('<I', f.read(4))[0] * 512
    unsquash = ROOT / 'staging_dir/host/bin/unsquashfs4'
    db_text = subprocess.check_output(
        [str(unsquash), '-o', str(offset), '-cat', str(iso), 'usr/lib/apk/db/installed'],
        text=True,
    )
    base_pkgs = {line[2:] for line in db_text.splitlines() if line.startswith('P:')}
    cfg = json.loads((ROOT / 'configs/installer-components.json').read_text())
    missing = [p for p in cfg['base']['required_packages'] if p not in base_pkgs]
    if missing:
        raise ValueError(f'Base squashfs missing required packages: {missing}')
    leaked = [p for p in cfg['base']['forbidden_packages'] if p in base_pkgs]
    if leaked:
        raise ValueError(f'Component packages leaked into base squashfs: {leaked}')

    base['format_version'] = 2
    base['base_package_count'] = len(base_pkgs)
    base['offline_repo_apk_count'] = len(catalog['repo_files'])
    return base


def make_answers(disk, fs, proto, ipv6, user, fullcone, password_hash, components, gnome_autostart):
    a = iso_vm.answers(disk, fs, proto, ipv6, user, fullcone, password_hash)
    if a['accounts']['user']:
        a['accounts']['user']['gnome_autostart'] = gnome_autostart
    if components is not None:
        a['components'] = components
    return a


def check_installed_packages(guest, required, forbidden):
    installed = set(guest.run('apk list --installed --manifest | cut -d" " -f1').splitlines())
    missing = [p for p in required if p not in installed]
    leaked = [p for p in forbidden if p in installed]
    if missing:
        raise RuntimeError(f'Missing expected packages: {missing}')
    if leaked:
        raise RuntimeError(f'Unexpected/forbidden packages present: {leaked}')
    return len(installed)


def check_lan_client(client, password):
    script = '#!/bin/sh\nif [ "$1" = bound ] || [ "$1" = renew ]; then ip addr flush dev eth0; ip addr add "$ip/24" dev eth0; echo "$ip" > /tmp/lease; fi\n'
    encoded = base64.b64encode(script.encode()).decode()
    client.run('echo ' + encoded + ' | base64 -d > /tmp/dhcp-script; chmod 700 /tmp/dhcp-script; ip link set eth0 up; udhcpc -i eth0 -n -q -t 10 -T 3 -s /tmp/dhcp-script', timeout=60)
    lease = client.run('cat /tmp/lease')
    if not re.fullmatch(r'192\.168\.71\.(?:1[0-4][0-9])', lease):
        raise RuntimeError('Lease outside requested pool: ' + lease)
    login = ('code=$(curl --noproxy "*" -k -L -sS --max-time 20 -o /tmp/luci.html -w "%{http_code}" '
             '-c /tmp/luci.cookies --data-urlencode luci_username=root --data-urlencode '
             + shlex.quote('luci_password=' + password)
             + ' https://192.168.71.1/cgi-bin/luci/); echo HTTPS_STATUS="$code"; test "$code" = 200; grep -qi luci /tmp/luci.html')
    client.run(login)
    askpass = '#!/bin/sh\nprintf "%s\\n" ' + shlex.quote(password) + '\n'
    encoded = base64.b64encode(askpass.encode()).decode()
    client.run('echo ' + encoded + ' | base64 -d > /tmp/askpass; chmod 700 /tmp/askpass; '
               'SSH_ASKPASS_REQUIRE=force SSH_ASKPASS=/tmp/askpass DISPLAY=:0 '
               'ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null '
               '-o PreferredAuthentications=password -n root@192.168.71.1 true')
    return {'dhcp': lease, 'luci_https': 200, 'ssh_password': 'pass'}


def test_rolling_upgrade(guest, port, forbidden):
    guest.run(
        f'sed -i "s|^base_url=.*|base_url=http://10.0.2.2:{port}|" /etc/lan-apk-feeds.conf && '
        'lan-apk-feeds-sync && apk update && apk upgrade && kernelctl check',
        timeout=180,
    )
    installed = set(guest.run('apk list --installed --manifest | cut -d" " -f1').splitlines())
    leaked = [p for p in forbidden if p in installed]
    if leaked:
        raise RuntimeError(f'Rolling upgrade pulled back forbidden packages: {leaked}')
    return 'pass'


def test_failsafe(disk, work, firmware, bus, password, netargs):
    with tempfile.TemporaryDirectory(prefix='owrt-fs-') as runtime:
        g = iso_vm.Guest('failsafe-arm', work, Path(runtime), disk, firmware=firmware, bus=bus, password=password, netargs=netargs)
        try:
            g.run('kernelctl check && kernelctl migrate')
            g.run('grub-editenv /boot/grub/grubenv set next_entry=owrt-rescue-failsafe && sync')
        finally:
            g.close()
    serial_log = work / 'failsafe-boot.serial.log'
    with tempfile.TemporaryDirectory(prefix='owrt-fs-boot-') as runtime:
        rt = Path(runtime)
        serial = rt / 'fs.serial'
        qmp = rt / 'fs.qmp'
        args = ['qemu-system-x86_64', '-name', 'openwrt-failsafe', '-machine', 'q35,accel=kvm', '-cpu', 'host',
                '-m', '2048', '-smp', '2', '-display', 'none', '-vga', 'std', '-monitor', 'none',
                '-qmp', f'unix:{qmp},server=on,wait=off', '-no-reboot',
                '-chardev', f'socket,id=serial,path={serial},server=on,wait=off,logfile={serial_log},logappend=on',
                '-serial', 'chardev:serial']
        if firmware == 'ovmf':
            vars_fd = work / 'failsafe.vars.fd'
            shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', vars_fd)
            args += ['-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
                     '-drive', 'if=pflash,format=raw,file=' + str(vars_fd)]
        args += ['-drive', f'if=none,id=target,format=qcow2,file={disk}',
                 '-device', 'nvme,drive=target,serial=INSTALLTARGET,bootindex=1' if bus == 'nvme' else 'virtio-blk-pci,drive=target,bootindex=1']
        proc = subprocess.Popen(args, stdout=(work / 'failsafe-boot.qemu.log').open('ab'), stderr=subprocess.STDOUT)
        sock = None
        try:
            deadline = time.monotonic() + 180
            while not serial.exists():
                if proc.poll() is not None:
                    raise RuntimeError('Failsafe QEMU exited early')
                time.sleep(.1)
            sock = socket.socket(socket.AF_UNIX)
            sock.connect(str(serial))
            sock.settimeout(1)
            buf = b''
            entered = False
            while time.monotonic() < deadline:
                if proc.poll() is not None:
                    raise RuntimeError('Failsafe QEMU exited')
                try:
                    buf += sock.recv(65536)
                except socket.timeout:
                    if entered:
                        sock.sendall(b'\n')
                    continue
                if b'Please press Enter' in buf and not entered:
                    sock.sendall(b'\n')
                    entered = True
                if re.search(rb'root@[^\r\n]*[#%] ', buf) or re.search(rb'\r?\n/# ', buf):
                    break
            else:
                raise TimeoutError('Failsafe shell prompt not reached: ' + buf[-1500:].decode(errors='replace'))
            sock.sendall(b'grep -qw failsafe=true /proc/cmdline && test "$(cat /proc/1/comm)" = init && mount_root && findmnt /overlay >/dev/null && touch /overlay/.failsafe-tested && sync && printf "FAILSAFE_%s\\n" OK\n')
            deadline2 = time.monotonic() + 30
            out = b''
            while time.monotonic() < deadline2 and b'FAILSAFE_OK' not in out:
                try:
                    out += sock.recv(65536)
                except socket.timeout:
                    continue
            if b'FAILSAFE_OK' not in out:
                raise RuntimeError('mount_root failed in failsafe: ' + out[-1000:].decode(errors='replace'))
        finally:
            if sock is not None:
                sock.close()
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=15)
    # Normal boot back to systemd PID 1 and verify marker survived
    with tempfile.TemporaryDirectory(prefix='owrt-fs-rec-') as runtime:
        g = iso_vm.Guest('failsafe-recovered', work, Path(runtime), disk, firmware=firmware, bus=bus, password=password, netargs=netargs)
        try:
            g.run('test "$(cat /proc/1/comm)" = systemd && test -f /overlay/.failsafe-tested && rm -f /overlay/.failsafe-tested && kernelctl check')
        finally:
            g.close()
    return 'pass'


def test_kernel_upgrade_and_rollback(disk, work, firmware, bus, password, netargs):
    """Install a second kernel generation from local feed, reboot to bless it, then rollback."""
    with tempfile.TemporaryDirectory(prefix='owrt-kctl-1-') as runtime:
        g = iso_vm.Guest('kctl-install', work, Path(runtime), disk, firmware=firmware, bus=bus, password=password, netargs=netargs)
        try:
            running = g.run('uname -r')
            g.run('apk update', timeout=60)
            avail = g.run(
                "apk list 'linux-image-*-openwrt*' | python3 -c \"import re,sys; print('\\n'.join(sorted(set(re.findall(r'linux-image-([0-9]+\\.[0-9]+\\.[0-9]+-[0-9]+-openwrt)', sys.stdin.read())))))\""
            ).splitlines()
            other = [k for k in avail if k and k != running and 'openwrt' in k]
            if not other:
                return 'skipped (single kernel in local feed)'
            target_k = other[0]
            g.run(f'mkdir -p /tmp/apk-cache && apk --cache-dir /tmp/apk-cache add linux-image-{shlex.quote(target_k)} && kernelctl list && kernelctl set-default {shlex.quote(target_k)} && sync')
        finally:
            g.close()
    with tempfile.TemporaryDirectory(prefix='owrt-kctl-2-') as runtime:
        g = iso_vm.Guest('kctl-newboot', work, Path(runtime), disk, firmware=firmware, bus=bus, password=password, netargs=netargs)
        try:
            g.run(f'test "$(uname -r)" = {shlex.quote(target_k)}')
            g.run('for i in $(seq 1 30); do systemctl is-active openwrt-kernel-boot.service && break; sleep 1; done; kernelctl check')
            g.run('kernelctl rollback && sync')
        finally:
            g.close()
    with tempfile.TemporaryDirectory(prefix='owrt-kctl-3-') as runtime:
        g = iso_vm.Guest('kctl-rollback', work, Path(runtime), disk, firmware=firmware, bus=bus, password=password, netargs=netargs)
        try:
            g.run(f'test "$(uname -r)" = {shlex.quote(running)} && kernelctl check')
        finally:
            g.close()
    return f'pass ({running} -> {target_k} -> rollback {running})'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iso', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--case', choices=['base_only', 'gnome_core', 'full_desktop', 'headless_virt_containers', 'all'], default='all')
    p.add_argument('--static-only', action='store_true')
    p.add_argument('--combined', type=Path)
    a = p.parse_args()
    a.iso = a.iso.resolve()
    a.work = a.work.resolve()
    if a.work == ROOT or ROOT in a.work.parents:
        p.error('--work must be outside the repository')
    a.work.mkdir(parents=True, exist_ok=True)

    receipt = {'iso': str(a.iso), 'sha256': network.sha256(a.iso), 'cases': {}}
    receipt['static'] = static_checks(a.iso, a.work)
    if a.static_only:
        (a.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        return

    feed_port = free_port()
    feed_root = build_local_feed(a.work / 'local-feed', feed_port)
    server = start_feed_server(feed_root, feed_port)

    password = 'Vm-' + secrets.token_hex(8)
    password_hash = subprocess.check_output(['openssl', 'passwd', '-6', '-stdin'], input=password + '\n', text=True).strip()

    cases = [
        # name, firmware, media, bus, fs, proto, ipv6, components, gnome_autostart
        ('base_only', 'ovmf', 'usb', 'nvme', 'ext4', 'dhcp', True, [], False),
        ('gnome_core', 'bios', 'cdrom', 'sata', 'btrfs', 'dhcp', True, ['gnome'], False),
        ('full_desktop', 'ovmf', 'usb', 'virtio', 'xfs', 'dhcp', True, None, True),
        ('headless_virt_containers', 'bios', 'cdrom', 'virtio', 'ext4', 'dhcp', True, ['virtualization', 'containers'], False),
    ]

    try:
        for name, firmware, media, bus, fs, proto, ipv6, comps, autostart in cases:
            if a.case not in ('all', name):
                continue
            work = a.work / name
            work.mkdir(exist_ok=True)
            disk = work / 'target.qcow2'
            if disk.exists():
                raise ValueError(f'Evidence target already exists: {disk}')
            subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', str(disk), '16G'], check=True)
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0))
                lan_port = sock.getsockname()[1]
            net = [
                '-netdev', f'socket,id=lan,listen=127.0.0.1:{lan_port}',
                '-device', 'e1000,netdev=lan,mac=52:54:00:10:00:01',
                '-netdev', 'user,id=wan',
                '-device', 'e1000,netdev=wan,mac=52:54:00:10:00:02',
            ]
            # 1. Live installer boot & unattended component install
            with tempfile.TemporaryDirectory(prefix='owrt-comp-iso-') as runtime:
                live = iso_vm.Guest('live', work, Path(runtime), disk, a.iso, firmware, bus, netargs=net, media=media)
                try:
                    live.run('for i in $(seq 1 30); do test -e /sys/class/net/eth1/device && break; sleep 1; done; grep -qw openwrt.installer=1 /proc/cmdline; findmnt -rn -t tmpfs | grep /tmp/root; systemctl is-active openwrt-installer.target')
                    if media == 'cdrom':
                        live.run('test "$(findmnt -nro SOURCE /rom)" = /dev/loop0; test "$(cat /sys/class/block/loop0/ro)" = 1; test "$(cat /sys/class/block/loop0/loop/backing_file)" = /dev/sr0')
                    listing = json.loads(live.run('lsblk -J -b -o NAME,PATH,SIZE,TYPE,TRAN'))
                    candidates = [d['path'] for d in listing['blockdevices'] if d['type'] == 'disk' and int(d['size']) == 16 * 1024**3]
                    if len(candidates) != 1:
                        raise RuntimeError('Target disk discovery failed')
                    config = make_answers(candidates[0], fs, proto, ipv6, True, False, password_hash, comps, autostart)
                    encoded = base64.b64encode(json.dumps(config).encode()).decode()
                    live.run('umask 077; echo ' + shlex.quote(encoded) + ' | base64 -d > /tmp/answers.json; openwrt-installer --answers /tmp/answers.json --dry-run > /tmp/dry-run.json')
                    live.run('openwrt-installer --answers /tmp/answers.json', timeout=900)
                    receipt['cases'][name] = {'media_boot': 'pass', 'firmware': firmware, 'media': media, 'bus': bus, 'fs': fs}
                finally:
                    live.close()

            # 2. Cold boot target disk alone (media removed)
            with tempfile.TemporaryDirectory(prefix='owrt-comp-disk-') as runtime:
                installed = iso_vm.Guest('installed', work, Path(runtime), disk, firmware=firmware, bus=bus, password=password, netargs=net)
                client = None
                client_runtime = tempfile.TemporaryDirectory(prefix='owrt-comp-client-')
                try:
                    client_net = ['-netdev', f'socket,id=lan,connect=127.0.0.1:{lan_port}', '-device', 'e1000,netdev=lan,mac=52:54:00:10:00:99']
                    client = iso_vm.Guest('client', work, Path(client_runtime.name), None, a.iso, 'bios', netargs=client_net)
                    installed.run('test "$(cat /proc/1/comm)" = systemd')
                    installed.run('for i in $(seq 1 90); do systemctl is-active openwrt-services.service && break; sleep 2; done')
                    installed.run('for i in $(seq 1 120); do test ! -e /etc/openwrt-installer/firstboot.json && break; sleep 2; done', timeout=260)
                    installed.run('ubus list service >/dev/null && test -z "$(systemctl --failed --no-legend)"')
                    installed.run(f'test "$(findmnt -nro FSTYPE /overlay)" = {fs}; touch /overlay/.rw-probe && rm /overlay/.rw-probe; findmnt /boot; kernelctl check')
                    installed.run('! id example-user; id alice | grep -qw sudo; test "$(uci -q get passwall.@global[0].enabled)" = 0')
                    installed.run('for i in $(seq 1 30); do test "$(ubus call network.interface.wan status | jsonfilter -e @.up)" = true && exit 0; sleep 1; done; exit 1')

                    base_req = ['systemd-openwrt', 'procd', 'netifd', 'firewall4', 'dnsmasq-full', 'luci', 'luci-app-passwall', 'smartdns', 'samba4-server', 'router-audit', 'uci-history', 'openwrt-kernel-upgrade', 'lan-apk-feeds', 'apk-transaction-guard']
                    if name == 'base_only':
                        req = base_req + ['ppp-mod-pppoe']
                        forb = ['openwrt-desktop-core', 'gnome-shell', 'gnome-remote-desktop', 'flatpak', 'openwrt-desktop-audio', 'openwrt-desktop-ime', 'sunshine', 'openwrt-appimage', 'libvirt-daemon', 'qemu-x86_64-softmmu', 'virt-manager', 'podman', 'distrobox']
                        pkg_count = check_installed_packages(installed, req, forb)
                    elif name == 'gnome_core':
                        req = base_req + ['openwrt-desktop-core', 'gnome-shell', 'xdg-desktop-portal', 'xdg-desktop-portal-gnome', 'firefox-esr-bin', 'google-chrome-bin']
                        forb = ['openwrt-desktop-rdp', 'gnome-remote-desktop', 'flatpak', 'openwrt-flatpak', 'openwrt-desktop-audio', 'wireplumber', 'openwrt-desktop-ime', 'sunshine', 'openwrt-appimage', 'libvirt-daemon', 'qemu-x86_64-softmmu', 'virt-manager', 'podman', 'distrobox']
                        pkg_count = check_installed_packages(installed, req, forb)
                        # Verify desktop did NOT autostart
                        installed.run('test "$(uci -q get desktop.main.enabled)" = 0 && ! pgrep -u alice -x gnome-shell')
                        # Start GNOME manually and verify session, portal, and PipeWire screen-sharing socket
                        installed.run('uci set desktop.main.enabled=1 && uci commit desktop && /etc/init.d/desktop start')
                        installed.run('for i in $(seq 1 90); do loginctl list-sessions --no-legend | grep "alice.*seat0" && pgrep -u alice -x gnome-shell && exit 0; sleep 2; done; exit 1', timeout=200)
                        installed.run(
                            'uid=$(id -u alice); su -s /bin/sh -c "'
                            'export XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus; '
                            'gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop --method org.freedesktop.DBus.Properties.Get org.freedesktop.portal.FileChooser version >/dev/null && '
                            'gdbus call --session --dest org.freedesktop.portal.Desktop --object-path /org/freedesktop/portal/desktop --method org.freedesktop.DBus.Properties.Get org.freedesktop.portal.ScreenCast version >/dev/null && '
                            'systemctl --user is-active xdg-desktop-portal.service xdg-desktop-portal-gnome.service && '
                            'systemctl --user start pipewire.socket && systemctl --user is-active pipewire.socket'
                            '" alice',
                            timeout=60,
                        )
                        installed.screenshot('gnome.png')
                    elif name == 'full_desktop':
                        req = base_req + ['openwrt-desktop-core', 'openwrt-desktop-rdp', 'gnome-remote-desktop', 'openwrt-desktop-audio', 'openwrt-desktop-ime', 'sunshine', 'openwrt-flatpak', 'flatpak', 'openwrt-appimage', 'libvirt-daemon', 'qemu-x86_64-softmmu', 'virt-manager', 'podman', 'distrobox']
                        forb = []
                        pkg_count = check_installed_packages(installed, req, forb)
                        installed.run('for i in $(seq 1 90); do loginctl list-sessions --no-legend | grep "alice.*seat0" && pgrep -u alice -x gnome-shell && exit 0; sleep 2; done; exit 1', timeout=200)
                        installed.run(
                            'uid=$(id -u alice); for i in $(seq 1 30); do '
                            'su -s /bin/sh -c "XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus '
                            'systemctl --user is-active openwrt-fcitx5.service pipewire.socket pipewire-pulse.socket wireplumber.service >/dev/null 2>&1" alice && exit 0; '
                            'sleep 1; done; exit 1',
                            timeout=60,
                        )
                        installed.run(
                            'uid=$(id -u alice); su -s /bin/sh -c "'
                            'export XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus; '
                            'gdbus call --session --dest org.freedesktop.portal.Flatpak --object-path /org/freedesktop/portal/Flatpak --method org.freedesktop.DBus.Properties.Get org.freedesktop.portal.Flatpak version >/dev/null'
                            '" alice',
                            timeout=30,
                        )
                        installed.run('virsh --connect qemu:///system list --all >/dev/null && podman --version >/dev/null && flatpak --version >/dev/null')
                        installed.screenshot('gnome.png')
                    elif name == 'headless_virt_containers':
                        req = base_req + ['libvirt-daemon', 'qemu-x86_64-softmmu', 'virsh', 'virt-install', 'luci-app-qemu', 'podman', 'openwrt-podman-rootless', 'distrobox', 'luci-app-podman']
                        forb = ['openwrt-desktop-core', 'gnome-shell', 'virt-manager', 'flatpak', 'openwrt-flatpak', 'openwrt-desktop-audio', 'openwrt-desktop-ime', 'sunshine', 'openwrt-appimage']
                        pkg_count = check_installed_packages(installed, req, forb)
                        installed.run('virsh --connect qemu:///system list --all >/dev/null && qemu-system-x86_64 --version >/dev/null && podman --version >/dev/null && distrobox --version >/dev/null')

                    receipt['cases'][name]['installed_package_count'] = pkg_count
                    receipt['cases'][name]['lan_client'] = check_lan_client(client, password)
                    receipt['cases'][name]['rolling_upgrade'] = test_rolling_upgrade(installed, feed_port, forb)
                finally:
                    if client is not None:
                        client.close()
                    client_runtime.cleanup()
                    installed.close()

            if name == 'base_only':
                receipt['cases'][name]['failsafe'] = test_failsafe(disk, work, firmware, bus, password, net)
                receipt['cases'][name]['kernel_upgrade_rollback'] = test_kernel_upgrade_and_rollback(disk, work, firmware, bus, password, net)

        if a.combined:
            receipt['combined_regression'] = iso_vm.combined_regression(a.combined.resolve(), a.work / 'combined')
    finally:
        server.shutdown()
        (a.work / 'receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')


if __name__ == '__main__':
    main()
