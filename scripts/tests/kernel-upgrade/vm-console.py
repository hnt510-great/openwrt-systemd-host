#!/usr/bin/env python3
"""JSON-line serial controller for an isolated, disposable OpenWrt EFI VM.

Input: {"command": "...", "timeout": 120}, {"reconnect": true}, or
{"quit": true}. The immutable raw image is always used through qcow2.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

import pexpect


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--raw', type=Path, required=True)
parser.add_argument('--out', type=Path, required=True)
parser.add_argument('--bios', action='store_true')
parser.add_argument('--share', type=Path)
parser.add_argument('--ssh-port', type=int, default=22295)
args = parser.parse_args()
args.out.mkdir(parents=True, exist_ok=True)
disk = args.out / 'system.qcow2'
extroot = args.out / 'extroot.qcow2'
for path, creation in [(disk, ['-F', 'raw', '-b', str(args.raw.resolve())]),
                       (extroot, ['8G'])]:
    if not path.exists():
        command = ['qemu-img', 'create', '-f', 'qcow2']
        if path == disk:
            command += creation + [str(path)]
        else:
            command += [str(path), '8G']
        subprocess.run(command, check=True, stdout=subprocess.DEVNULL)
options = ['-name', 'openwrt-kernel-upgrade-test', '-enable-kvm', '-cpu', 'host',
           '-smp', '2', '-m', '2048', '-display', 'none', '-monitor', 'none',
           '-qmp', 'unix:' + str(args.out / 'qmp.sock') + ',server=on,wait=off',
           '-serial', 'stdio', '-drive', f'if=none,id=system,format=qcow2,file={disk}',
           '-device', 'virtio-blk-pci,drive=system,bootindex=1',
           '-drive', f'if=none,id=extroot,format=qcow2,file={extroot}',
           '-device', 'nvme,drive=extroot,serial=kernel-upgrade-test',
           '-netdev', 'user,id=lan,net=192.0.2.0/24,host=192.0.2.254,dhcpstart=192.0.2.240,restrict=on,' +
           f'hostfwd=tcp:127.0.0.1:{args.ssh_port}-192.0.2.1:22',
           '-device', 'virtio-net-pci,netdev=lan',
           '-netdev', 'user,id=wan,net=192.0.2.0/24,host=192.0.2.2,restrict=on',
           '-device', 'virtio-net-pci,netdev=wan', '-device', 'virtio-vga']
if args.share:
    options += ['-virtfs', 'local,path=' + str(args.share.resolve()) +
                ',mount_tag=kerneltest,security_model=none,readonly=on']
if not args.bios:
    variables = args.out / 'OVMF_VARS.fd'
    if not variables.exists():
        shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
    options += ['-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
                '-drive', 'if=pflash,format=raw,file=' + str(variables)]
log = (args.out / 'serial.log').open('a')
child = pexpect.spawn('qemu-system-x86_64', options, encoding='utf-8', codec_errors='replace',
                      timeout=30, maxread=65536, logfile=log)
(args.out / 'qemu.pid').write_text(str(child.pid) + '\n')


def connect():
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            index = child.expect([r'Please press Enter to activate this console',
                                  r'[^\r\n]*login:', r'Password:',
                                  r'root@[A-Za-z0-9_.()-]+:[^\r\n]*# '], timeout=10)
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
            child.sendline("stty -echo; export TERM=dumb PS1='KERNEL_TEST# '; exec /bin/ash")
            child.expect(r'[\r\n]KERNEL_TEST# ')
            return
    raise TimeoutError('No serial shell')


try:
    connect()
    print(json.dumps({'ready': True, 'pid': child.pid}), flush=True)
    for line in sys.stdin:
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
        child.sendline(command + "; test_rc=$?; printf '\\nKERNEL_TEST_RC=%s\\n' \"$test_rc\"")
        try:
            child.expect(r'KERNEL_TEST_RC=(\d+)', timeout=request.get('timeout', 120))
        except pexpect.EOF:
            if 'Power down' not in child.before:
                raise
            print(json.dumps({'status': 0, 'powered_off': True, 'output': child.before}), flush=True)
            break
        output, status = child.before, int(child.match[1])
        child.expect('KERNEL_TEST# ')
        print(json.dumps({'status': status, 'output': output}), flush=True)
finally:
    child.terminate(force=True)
    log.close()
