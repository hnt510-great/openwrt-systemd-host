#!/usr/bin/env python3
"""JSON-line controller for a disposable GNOME firmware VM.

Input: {"command": "...", "timeout": 120}, {"reconnect": true}, or
{"quit": true}. The immutable raw image is always used through qcow2.
"""
import argparse
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import sys
import time

import pexpect


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--raw', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--renderer', choices=['software', 'virgl'], default='software')
parser.add_argument('--render-node', default='/dev/dri/renderD128')
parser.add_argument('--rdp-port', type=int, default=23389)
parser.add_argument('--sunshine-port', type=int, default=48989)
parser.add_argument('--share', type=Path)
parser.add_argument('--ssh-port', type=int, default=22295)
parser.add_argument('--lan-udp', action='store_true',
                    help='Allow slirp UDP replies on the isolated test LAN; keep WAN restricted')
args = parser.parse_args()
os.umask(0o077)
args.out.mkdir(parents=True, exist_ok=True, mode=0o700)
disk = args.out / 'system.qcow2'
if not disk.exists():
    subprocess.run(['qemu-img', 'create', '-f', 'qcow2', '-F', 'raw',
                    '-b', str(args.raw.resolve()), str(disk)],
                   check=True, stdout=subprocess.DEVNULL)
options = ['-name', 'openwrt-gnome-disposable', '-machine', 'q35', '-enable-kvm', '-cpu', 'host',
           '-smp', '4', '-m', '6144', '-display', 'none', '-monitor', 'none',
           '-qmp', 'unix:' + str(args.out / 'qmp.sock') + ',server=on,wait=off',
           '-serial', 'stdio', '-drive', f'if=none,id=system,format=qcow2,file={disk}',
           '-device', 'virtio-blk-pci,drive=system,bootindex=1',
           '-netdev', 'user,id=lan,net=192.0.2.0/24,host=192.0.2.254,dhcpstart=192.0.2.240,' +
           ('restrict=off,' if args.lan_udp else 'restrict=on,') +
           f'hostfwd=tcp:127.0.0.1:{args.ssh_port}-192.0.2.1:22,' +
           f'hostfwd=tcp:127.0.0.1:{args.rdp_port}-192.0.2.1:3389' +
           ''.join(f',hostfwd={protocol}:127.0.0.1:{args.sunshine_port + offset}-192.0.2.1:{args.sunshine_port + offset}'
                   for protocol, offsets in [('tcp', [-5, 0, 1, 21]), ('udp', [9, 10, 11, 13, 21])]
                   for offset in offsets),
           '-device', 'virtio-net-pci,netdev=lan',
           '-netdev', 'user,id=wan,net=192.0.2.0/24,host=192.0.2.2,restrict=on',
           '-device', 'virtio-net-pci,netdev=wan',
           '-device', 'qemu-xhci', '-device', 'usb-kbd', '-device', 'usb-tablet',
           '-audiodev', 'driver=none,id=testaudio', '-device', 'intel-hda',
           '-device', 'hda-duplex,audiodev=testaudio']
if args.renderer == 'virgl':
    options[options.index('-display') + 1] = 'egl-headless,rendernode=' + args.render_node
    options += ['-device', 'virtio-vga-gl']
else:
    options += ['-device', 'virtio-vga']
if args.share:
    options += ['-virtfs', 'local,path=' + str(args.share.resolve()) +
                ',mount_tag=gnometest,security_model=none,readonly=on']
variables = args.out / 'OVMF_VARS.fd'
if not variables.exists():
    shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
options += ['-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
            '-drive', 'if=pflash,format=raw,file=' + str(variables)]
(args.out / 'qemu-command.json').write_text(json.dumps(['qemu-system-x86_64', *options], indent=2) + '\n')
log = (args.out / 'serial.log').open('a')
child = pexpect.spawn('qemu-system-x86_64', options, encoding='utf-8', codec_errors='replace',
                      timeout=30, maxread=65536)
child.logfile_read = log
(args.out / 'qemu.pid').write_text(str(child.pid) + '\n')


def connect():
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            index = child.expect([r'Please press Enter to activate this console',
                                  r'[^\r\n]*login:', r'Password:',
                                  r'(?:root@[A-Za-z0-9_.()-]+:[^\r\n]*# |GNOME_TEST# )'], timeout=10)
        except pexpect.TIMEOUT:
            child.sendline('')
            continue
        if index == 0:
            child.sendline('')
        elif index == 1:
            child.sendline('root')
        elif index == 2:
            raise RuntimeError('Unexpected console password on disposable image')
        else:
            child.sendline("stty -echo; export TERM=dumb PS1='GNOME_TEST# '; exec /bin/ash")
            child.expect(r'[\r\n]GNOME_TEST# ')
            return
    raise TimeoutError('No serial shell')


selector = None
try:
    connect()
    print(json.dumps({'ready': True, 'pid': child.pid, 'renderer_requested': args.renderer,
                      'ssh_port': args.ssh_port, 'rdp_port': args.rdp_port,
                      'sunshine_port': args.sunshine_port}), flush=True)
    # Drain the serial console while idle too. SSH-triggered reboots and noisy
    # services must not fill the PTY and delay the guest while stdin is quiet.
    selector = selectors.SelectSelector()
    selector.register(sys.stdin.fileno(), selectors.EVENT_READ, 'input')
    selector.register(child.child_fd, selectors.EVENT_READ, 'serial')
    pending = b''
    input_closed = False
    while True:
        if input_closed and not pending:
            break
        if b'\n' not in pending:
            powered_off = False
            for key, _events in selector.select():
                if key.data == 'input':
                    data = os.read(sys.stdin.fileno(), 65536)
                    if data:
                        pending += data
                    else:
                        input_closed = True
                        selector.unregister(sys.stdin.fileno())
                        if pending:
                            pending += b'\n'
                else:
                    try:
                        child.read_nonblocking(65536, timeout=0)
                    except pexpect.TIMEOUT:
                        pass
                    except pexpect.EOF:
                        powered_off = True
            if powered_off:
                print(json.dumps({'powered_off': True}), flush=True)
                break
            if b'\n' not in pending:
                continue
        line, pending = pending.split(b'\n', 1)
        request = json.loads(line)
        if request.get('quit'):
            break
        if request.get('reconnect'):
            connect()
            print(json.dumps({'ready': True}), flush=True)
            continue
        if request.get('reboot'):
            child.sendline('sync; systemctl reboot')
            child.expect(r'Rebooting|Restarting system|GNU GRUB', timeout=120)
            connect()
            print(json.dumps({'ready': True}), flush=True)
            continue
        if 'reboot_keys' in request:
            child.sendline('sync; systemctl reboot')
            child.expect(r'Rebooting|Restarting system|GNU GRUB', timeout=120)
            child.expect('highlighted entry will be executed automatically', timeout=60)
            child.send(request['reboot_keys'])
            connect()
            print(json.dumps({'ready': True}), flush=True)
            continue
        if 'keys' in request:
            child.send(request['keys'])
            print(json.dumps({'keys_sent': True}), flush=True)
            continue
        command = request['command']
        child.sendline(command + "; test_rc=$?; printf '\\nGNOME_TEST_RC=%s\\n' \"$test_rc\"")
        try:
            child.expect(r'GNOME_TEST_RC=(\d+)', timeout=request.get('timeout', 120))
        except pexpect.EOF:
            if 'Power down' not in child.before:
                raise
            print(json.dumps({'status': 0, 'powered_off': True, 'output': child.before}), flush=True)
            break
        output, status = child.before, int(child.match[1])
        child.expect('GNOME_TEST# ')
        print(json.dumps({'status': status, 'output': output}), flush=True)
finally:
    if selector is not None:
        selector.close()
    child.terminate(force=True)
    log.close()
