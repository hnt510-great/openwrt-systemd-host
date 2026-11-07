"""Execute a validated whole-disk installation from live USB or optical media."""
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import time

import core

BASE = Path('/run/openwrt-installer')


def run(*args, input=None):
    # Never print argv or stdin: UCI and account commands can contain secrets.
    result = subprocess.run(args, input=input, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed: ' + result.stderr[-1500:])
    return result.stdout.strip()


def optical_media(device, sysfs=Path('/sys')):
    kind = sysfs / 'class/block' / Path(device).name / 'device/type'
    return kind.exists() and kind.read_text().strip() == '5'


def live_media(sysfs=Path('/sys')):
    devnum = run('findmnt', '-nro', 'MAJ:MIN', '/rom')
    root = (sysfs / 'dev/block' / devnum).resolve(strict=True)
    if (root / 'partition').exists():
        return '/dev/' + root.name, '/dev/' + root.parent.name
    backing = root / 'loop/backing_file'
    if backing.exists():
        media = Path(backing.read_text().strip()).resolve()
        # Only the bootstrap's read-only optical loop is an accepted alternative.
        # Never infer a writable source or target from a generic loop backing file.
        if (media.parent == Path('/dev') and optical_media(media, sysfs)
                and (root / 'ro').read_text().strip() == '1'
                and (sysfs / 'class/block' / media.name / 'ro').read_text().strip() == '1'):
            return '/dev/' + root.name, str(media)
    raise ValueError('Cannot determine installer source media')


def discover():
    rom, media = live_media()
    data = json.loads(run('lsblk', '-J', '-b', '-o', 'NAME,PATH,SIZE,MODEL,TRAN,RO,RM,TYPE'))
    return rom, media, core.disks(data, [media])


def prepare(a, manifest):
    if 'openwrt.installer=1' not in Path('/proc/cmdline').read_text().split():
        raise ValueError('Installation requires the live installer boot entry')
    rom, media, candidates = discover()
    disk = next((d for d in candidates if d['path'] == a['disk']), None)
    if not disk or not stat.S_ISBLK(os.stat(a['disk']).st_mode):
        raise ValueError('Target is not an eligible disk')
    users = [l.split(':')[0] for l in Path('/etc/passwd').read_text().splitlines()]
    a = core.validate_answers(a, users)
    plan = core.layout(a['partitions'], int(disk['size']), manifest['squashfs_size'])
    # Generate every configurable string before the first destructive operation.
    core.network_batch(a)
    core.policy_batch(a, run('uci', '-X', 'show', 'firewall'))
    return a, plan, rom, media


def digest(device, size):
    h = hashlib.sha256()
    with open(device, 'rb', buffering=0) as source:
        while size:
            chunk = source.read(min(size, 4 * core.MIB))
            if not chunk:
                raise ValueError('Short squashfs read')
            h.update(chunk); size -= len(chunk)
    return h.hexdigest()


def write_private(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, 'w') as stream:
        stream.write(text)
    os.chmod(path, 0o600)


def install(a, manifest, payload_dir, progress=lambda n, text: None, dry_run=False):
    a, plan, source, media = prepare(a, manifest)
    if dry_run:
        return {'summary': json.loads(core.summary(a)), 'layout': plan,
                'sfdisk': core.sfdisk_script(a['disk'], plan)}
    disk = a['disk']
    if digest(source, manifest['squashfs_size']) != manifest['squashfs_sha256']:
        raise ValueError('Installer payload checksum mismatch')
    mounted = []
    def mount(device, name, *options):
        dest = BASE / name; dest.mkdir(parents=True, exist_ok=True)
        run('mount', *options, device, str(dest)); mounted.append(dest)
        return dest
    try:
        progress(5, 'Partitioning target disk')
        # Children first, without touching the USB or any other disk.
        devices = json.loads(run('lsblk', '-J', '-o', 'PATH,MOUNTPOINTS', disk))['blockdevices']
        def unmount(nodes):
            for node in nodes:
                unmount(node.get('children', []))
                for point in reversed(node.get('mountpoints') or []):
                    if point:
                        run('umount', point)
        unmount(devices)
        run('wipefs', '-a', disk)
        run('sfdisk', '--wipe', 'always', disk, input=core.sfdisk_script(disk, plan))
        run('partx', '-u', disk); run('udevadm', 'settle')
        for p in plan['partitions'] + [{'number': 128}]:
            device = core.partition(disk, p['number'])
            deadline = time.monotonic() + 30
            while not Path(device).exists():
                if time.monotonic() > deadline:
                    raise RuntimeError('Partition device did not appear')
                time.sleep(.2)
        progress(15, 'Copying and verifying system image')
        run('dd', 'if=' + source, 'of=' + core.partition(disk, 2), 'bs=4M',
            'iflag=count_bytes', 'count=' + str(manifest['squashfs_size']), 'conv=fsync')
        if digest(core.partition(disk, 2), manifest['squashfs_size']) != manifest['squashfs_sha256']:
            raise RuntimeError('Target squashfs checksum mismatch')
        progress(40, 'Installing UEFI and BIOS boot loaders')
        serial = secrets.token_hex(4)
        run('mkfs.fat', '-F', '32', '-n', 'kernel', '-i', serial, core.partition(disk, 1))
        esp = mount(core.partition(disk, 1), 'esp')
        shutil.copytree(payload_dir / 'esp', esp, dirs_exist_ok=True, symlinks=True)
        cfg = esp / 'boot/grub/grub.cfg'
        cfg.write_text(core.rewrite_grub(cfg.read_text(), manifest['root_partuuid'],
                                        plan['partitions'][1]['uuid'], serial[:4].upper() + '-' + serial[4:].upper()))
        device_map = BASE / 'device.map'; device_map.write_text('(hd0) ' + disk + '\n')
        run('grub-bios-setup', '-m', str(device_map), '-d', str(esp / 'boot/grub'), '-r', 'hd0,gpt1', disk)
        progress(55, 'Formatting overlay and data partitions')
        for p in plan['partitions'][2:]:
            fs = p['fs']; dev = core.partition(disk, p['number'])
            if fs != 'unformatted':
                run('mkfs.' + fs, '-F' if fs == 'ext4' else '-f', '-L', p['name'], dev)
        ov = mount(core.partition(disk, 3), 'overlay')
        (ov / 'upper').mkdir(); (ov / 'work').mkdir(); (ov / '.fs_state').symlink_to('2')
        rom = mount(core.partition(disk, 2), 'rom', '-t', 'squashfs', '-o', 'ro')
        target = mount('overlay', 'target', '-t', 'overlay', '-o', f'lowerdir={rom},upperdir={ov}/upper,workdir={ov}/work')
        progress(75, 'Writing network, firewall and accounts')
        config = target / 'etc/config'
        write_private(config / 'network', '')
        run('uci', '-c', str(config), 'batch', input=core.network_batch(a))
        run('uci', '-c', str(config), 'batch', input=core.policy_batch(a, run('uci', '-c', str(config), '-X', 'show', 'firewall')))
        shadow = target / 'etc/shadow'
        lines = shadow.read_text().splitlines()
        if not any(line.startswith('root:') for line in lines):
            raise ValueError('Target root account missing')
        updated = []
        for line in lines:
            fields = line.split(':')
            if fields[0] == 'root':
                fields[1] = a['accounts']['root_password_hash']
            updated.append(':'.join(fields))
        write_private(shadow, '\n'.join(updated) + '\n')
        settings = target / 'etc/openwrt-installer'
        if a['accounts'].get('user'):
            write_private(settings / 'firstboot.json', json.dumps(a['accounts']['user']))
        write_private(settings / 'install.json', core.summary(a) + '\n')
        progress(95, 'Synchronizing disks')
    finally:
        # Keep cleanup failures visible and attempt every unmount.
        errors = []
        for path in reversed(mounted):
            try:
                run('umount', str(path))
            except Exception as exc:
                errors.append(str(exc))
        os.sync()
        if errors:
            raise RuntimeError('; '.join(errors))
    progress(100, 'Installation complete')
    return plan
