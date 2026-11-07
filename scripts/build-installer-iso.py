#!/usr/bin/env python3
"""Assemble the hybrid USB installer from an already prepared clean squashfs."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import shutil
import struct
import subprocess


def run(*args):
    subprocess.run([str(x) for x in args], check=True)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'squashfs', 'esp-tree', 'grub-dir', 'kernel', 'template', 'initramfs'):
        p.add_argument('--' + name, required=True, type=Path)
    for name in ('epoch', 'signature', 'root-partuuid', 'release', 'version', 'serial', 'terminal', 'cmdline', 'title', 'timeout'):
        p.add_argument('--' + name, required=True)
    a = p.parse_args()
    if not shutil.which('xorriso'):
        p.error('xorriso is required to build INSTALLER_ISO_IMAGES')
    tree = Path(str(a.output) + '.iso'); esp = Path(str(a.output) + '.esp.img')
    if tree.exists():
        shutil.rmtree(tree)
    (tree / 'boot/grub').mkdir(parents=True)
    (tree / 'install').mkdir()
    shutil.copytree(a.esp_tree, tree / 'install/esp', symlinks=True)
    shutil.copyfile(a.kernel, tree / 'boot/vmlinuz')
    shutil.copyfile(a.initramfs, tree / 'boot/installer-initramfs.gz')
    shutil.copyfile(a.grub_dir / 'installer-eltorito.img', tree / 'boot/grub/bios.img')
    values = {'SERIAL_CONFIG': a.serial, 'TERMINAL_CONFIG': a.terminal, 'CMDLINE': a.cmdline + ' openwrt.installer.signature=' + a.signature,
              'TITLE': a.title, 'TIMEOUT': a.timeout, 'INSTALLER_ROOT': 'root=PARTUUID=' + a.signature + '-03'}
    cfg = a.template.read_text()
    for key, value in values.items():
        cfg = cfg.replace('@' + key + '@', value)
    (tree / 'boot/grub/grub.cfg').write_text(cfg)
    digest = hashlib.sha256()
    with a.squashfs.open('rb') as f:
        for chunk in iter(lambda: f.read(4 * 1024 * 1024), b''):
            digest.update(chunk)
    (tree / 'install/manifest.json').write_text(json.dumps({'version': a.version, 'kernel_release': a.release,
        'squashfs_size': a.squashfs.stat().st_size, 'squashfs_sha256': digest.hexdigest(),
        'root_partuuid': a.root_partuuid}, indent=2) + '\n')
    # GRUB uses ISO9660 modification time as YYYY-MM-DD-hh-mm-ss-cc UUID.
    date = datetime.datetime.fromtimestamp(int(a.epoch), datetime.timezone.utc)
    iso_date = date.strftime('%Y%m%d%H%M%S') + '00'
    iso_uuid = date.strftime('%Y-%m-%d-%H-%M-%S') + '-00'
    stub = Path(str(a.output) + '.stub.cfg')
    stub.write_text(f'search --no-floppy --fs-uuid --set=root {iso_uuid}\nset prefix=($root)/boot/grub\nconfigfile $prefix/grub.cfg\n')
    esp.unlink(missing_ok=True)
    run('mkfs.fat', '--invariant', '-C', esp, '-S', '512', '8192')
    run('mmd', '-i', esp, '::/efi', '::/efi/boot', '::/boot', '::/boot/grub')
    run('mcopy', '-i', esp, a.grub_dir / 'installer-bootx64.efi', '::/efi/boot/bootx64.efi')
    run('mcopy', '-i', esp, stub, '::/boot/grub/grub.cfg')
    run('xorriso', '-as', 'mkisofs', '-R', '-J', '-V', 'OPENWRT_INSTALL', '--modification-date=' + iso_date,
        '-o', a.output, '--grub2-mbr', a.grub_dir / 'boot_hybrid.img', '-partition_offset', '16',
        '--mbr-force-bootable', '-append_partition', '2', '0xef', esp,
        '-append_partition', '3', '0x83', a.squashfs, '-c', 'boot/boot.cat',
        '-b', 'boot/grub/bios.img', '-no-emul-boot', '-boot-load-size', '4', '-boot-info-table',
        '--grub2-boot-info', '-eltorito-alt-boot', '-e', '--interval:appended_partition_2:all::',
        '-no-emul-boot', tree)
    with a.output.open('r+b') as f:
        f.seek(440); f.write(struct.pack('<I', int(a.signature, 16)))


if __name__ == '__main__':
    main()
