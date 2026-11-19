"""Execute a validated whole-disk installation from live USB or optical media."""
import hashlib
import json
import os
from pathlib import Path
import re
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import time

import core

BASE = Path('/run/openwrt-installer')
INSTALLING_RE = re.compile(r'^\(\s*\d+/\d+\)\s+Installing\s+(\S+)\s+\(([^)]+)\)')
OK_SPACE_RE = re.compile(r'^OK:\s+([0-9]+(?:\.[0-9]+)?)\s+([A-Za-z]+)\s+in\s+\d+\s+packages?$')
SPACE_UNITS = {
    'B': 1,
    'KiB': 1024, 'KB': 1000, 'K': 1024,
    'MiB': 1024 ** 2, 'MB': 1000 ** 2, 'M': 1024 ** 2,
    'GiB': 1024 ** 3, 'GB': 1000 ** 3, 'G': 1024 ** 3,
    'TiB': 1024 ** 4, 'TB': 1000 ** 4, 'T': 1024 ** 4,
}


def run(*args, input=None, env=None):
    # Never print argv or stdin: UCI and account commands can contain secrets.
    result = subprocess.run(args, input=input, env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(f'{Path(args[0]).name} failed: ' + result.stderr[-1500:])
    return result.stdout.strip()


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, 'rb') as source:
        for chunk in iter(lambda: source.read(4 * core.MIB), b''):
            h.update(chunk)
    return h.hexdigest()


def parse_apk_simulate(output, base_installed_bytes=0):
    solved = []
    installed_bytes = 0
    for line in output.splitlines():
        s = line.strip()
        m = INSTALLING_RE.match(s)
        if m:
            solved.append((m.group(1), m.group(2)))
            continue
        om = OK_SPACE_RE.match(s)
        if om:
            val = float(om.group(1))
            unit = SPACE_UNITS.get(om.group(2), 1)
            total_bytes = int(round(val * unit))
            installed_bytes = max(0, total_bytes - max(0, int(base_installed_bytes)))
    return solved, installed_bytes


def read_installed_state(base_root):
    for rel in ('lib/apk/db/installed', 'usr/lib/apk/db/installed'):
        db = Path(base_root) / rel
        if db.exists():
            pkgs = {}
            total_installed_bytes = 0
            for block in db.read_text().strip().split('\n\n'):
                name = version = None
                for line in block.splitlines():
                    if line.startswith('P:'):
                        name = line[2:]
                    elif line.startswith('V:'):
                        version = line[2:]
                    elif line.startswith('I:'):
                        try:
                            total_installed_bytes += int(line[2:])
                        except ValueError:
                            pass
                if name:
                    pkgs[name] = version or ''
            digest = hashlib.sha256(
                ('\n'.join(f'{k}={pkgs[k]}' for k in sorted(pkgs)) + '\n').encode()
            ).hexdigest()
            return digest, total_installed_bytes
    raise ValueError(f'Base root APK database missing under {base_root}')


def read_installed_digest(base_root):
    return read_installed_state(base_root)[0]


def trusted_keys_dir(base_root):
    keys_dir = Path(base_root) / 'etc/apk/keys'
    if not keys_dir.is_dir():
        raise ValueError(f'Trusted base APK keys directory missing under {base_root}')
    pem_files = [p for p in keys_dir.iterdir() if p.is_file() and p.suffix == '.pem']
    if not pem_files:
        raise ValueError(f'No trusted APK public keys found under {keys_dir}')
    if any('private' in p.name.lower() for p in keys_dir.rglob('*') if p.is_file()):
        raise ValueError(f'Refusing to use keys directory containing private key material: {keys_dir}')
    return keys_dir


def query_repo_installed_sizes(sim_root, keys_dir, repo_index, apk_bin='apk'):
    out = run(
        str(apk_bin), '--root', str(sim_root), '--keys-dir', str(keys_dir),
        '--no-logfile', '--no-network', '--no-cache',
        '--repositories-file', '/dev/null',
        '--repository', f'file://{repo_index}',
        'query', '--available', '--fields', 'name,version,installed-size',
        '--format', 'json', '*',
    )
    entries = json.loads(out) if out else []
    sizes = {}
    for entry in entries:
        name = entry.get('name')
        version = entry.get('version')
        size = entry.get('installed-size')
        if name is not None and version is not None and size is not None:
            sizes[(str(name), str(version))] = int(size)
    return sizes


def load_components_catalog(manifest, payload_dir):
    fmt = manifest.get('format_version', 1)
    if fmt == 1 and 'components_manifest' not in manifest:
        return None
    if fmt != 2:
        raise ValueError(f'Unsupported installer payload format version: {fmt}')
    if payload_dir is None:
        raise ValueError('Installer payload directory is required for component catalog')
    comp_rel = manifest.get('components_manifest')
    if not comp_rel:
        raise ValueError('Installer manifest is missing components_manifest')
    comp_path = Path(payload_dir) / comp_rel
    if not comp_path.exists():
        raise ValueError(f'Missing components catalog: {comp_path}')
    if sha256_file(comp_path) != manifest.get('components_sha256'):
        raise ValueError('Components catalog checksum mismatch')
    catalog = json.loads(comp_path.read_text())
    if catalog.get('format_version') != 2:
        raise ValueError('Unsupported components catalog format version')
    if catalog.get('version') != manifest.get('version') or catalog.get('kernel_release') != manifest.get('kernel_release'):
        raise ValueError('Components catalog version or kernel release does not match installer manifest')
    comp_dir = comp_path.parent
    repo_index = comp_dir / 'repo/packages.adb'
    if not repo_index.exists():
        raise ValueError('Offline component repository index is missing')
    index_hash = sha256_file(repo_index)
    if index_hash != manifest.get('repo_index_sha256') or index_hash != catalog.get('repo_index_sha256'):
        raise ValueError('Offline component repository index checksum mismatch')
    if any('private' in p.name.lower() for p in comp_dir.rglob('*') if p.is_file()):
        raise ValueError('Refusing to use installer media containing private key material')
    return catalog


def preflight_components(selected, catalog, payload_dir, base_root=Path('/rom'), apk_bin='apk'):
    chosen = core.validate_components(selected, catalog)
    if not catalog:
        return None
    actual_base, base_installed_bytes = read_installed_state(base_root)
    if catalog.get('base_packages_sha256') and actual_base != catalog['base_packages_sha256']:
        raise ValueError('Base rootfs package set does not match component catalog identity')
    top_pkgs = core.resolve_component_packages(chosen, catalog)
    if not top_pkgs:
        return {
            'components': chosen,
            'top_packages': [],
            'packages': [],
            'install_count': 0,
            'installed_bytes': 0,
            'min_overlay_mib': core.MIN_OVERLAY_MIB,
        }
    comp_dir = Path(payload_dir) / 'components'
    repo_dir = comp_dir / 'repo'
    repo_index = repo_dir / 'packages.adb'
    # Verify offline repository signatures against the booted base system's trusted keys,
    # never against unverified keys copied alongside the offline repository.
    keys_dir = trusted_keys_dir(base_root)
    repo_files = catalog.get('repo_files') or {}
    with tempfile.TemporaryDirectory(prefix='installer-sim-') as tmp:
        sim_root = Path(tmp) / 'sim'
        for rel in ('lib/apk/db/installed', 'etc/apk/arch', 'etc/apk/world'):
            src = Path(base_root) / rel
            if not src.exists() and rel.startswith('lib/'):
                src = Path(base_root) / ('usr/' + rel)
            if src.exists():
                dst = sim_root / rel
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(src, dst)
        (sim_root / 'lib/apk/db').mkdir(parents=True, exist_ok=True)
        (sim_root / 'tmp').mkdir(parents=True, exist_ok=True)
        out = run(
            str(apk_bin), '--root', str(sim_root), '--keys-dir', str(keys_dir),
            '--no-logfile', '--no-network', '--no-cache',
            '--repositories-file', '/dev/null',
            '--repository', f'file://{repo_index}', '--simulate', 'add', *top_pkgs
        )
        solved, sim_delta_bytes = parse_apk_simulate(out, base_installed_bytes=base_installed_bytes)
        if not solved:
            raise ValueError('Offline APK simulation returned no packages for selected components')
        repo_sizes = query_repo_installed_sizes(sim_root, keys_dir, repo_index, apk_bin=apk_bin)
    compressed_total = 0
    for name, version in solved:
        filename = f'{name}-{version}.apk'
        meta = repo_files.get(filename)
        if not meta:
            raise ValueError(f'Solved package {filename} is missing from component catalog')
        apk_path = repo_dir / filename
        if not apk_path.exists():
            raise ValueError(f'Solved package {filename} is missing from offline repository')
        if sha256_file(apk_path) != meta['sha256']:
            raise ValueError(f'Corrupt package in offline repository: {filename}')
        compressed_total += int(meta.get('size', 0))
    if all((name, version) in repo_sizes for name, version in solved):
        installed_bytes = sum(repo_sizes[(name, version)] for name, version in solved)
    elif sim_delta_bytes > 0:
        installed_bytes = sim_delta_bytes
    elif compressed_total > 0:
        installed_bytes = compressed_total * 3
    else:
        installed_bytes = 0
    return {
        'components': chosen,
        'top_packages': top_pkgs,
        'packages': [f'{n}={v}' for n, v in solved],
        'install_count': len(solved),
        'installed_bytes': installed_bytes,
        'min_overlay_mib': core.min_overlay_mib(installed_bytes),
    }


def install_components(target, component_plan, payload_dir, base_root=Path('/rom'), apk_bin='apk'):
    if not component_plan or not component_plan.get('top_packages'):
        return
    comp_dir = Path(payload_dir) / 'components'
    repo_index = comp_dir / 'repo/packages.adb'
    keys_dir = trusted_keys_dir(base_root)
    env = dict(os.environ, IPKG_INSTROOT=str(target))
    run(
        str(apk_bin), '--root', str(target), '--keys-dir', str(keys_dir),
        '--no-logfile', '--no-network', '--no-cache',
        '--commit-hooks=no', '--force-no-chroot', '--preserve-env',
        '--repositories-file', '/dev/null',
        '--repository', f'file://{repo_index}',
        'add', *component_plan['top_packages'],
        env=env,
    )


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
    data = json.loads(run('lsblk', '-J', '-b', '-o', 'NAME,PATH,SIZE,MODEL,SERIAL,TRAN,RO,RM,TYPE'))
    return rom, media, core.disks(data, [media])


def prepare(a, manifest, payload_dir=None):
    if 'openwrt.installer=1' not in Path('/proc/cmdline').read_text().split():
        raise ValueError('Installation requires the live installer boot entry')
    rom, media, candidates = discover()
    disk = next((d for d in candidates if d['path'] == a['disk']), None)
    if not disk or not stat.S_ISBLK(os.stat(a['disk']).st_mode):
        raise ValueError('Target is not an eligible disk')
    catalog = load_components_catalog(manifest, payload_dir)
    users = [l.split(':')[0] for l in Path('/etc/passwd').read_text().splitlines()]
    a = core.validate_answers(a, users, catalog=catalog)
    component_plan = preflight_components(a.get('components'), catalog, payload_dir) if catalog is not None else None
    min_overlay = component_plan['min_overlay_mib'] if component_plan else core.MIN_OVERLAY_MIB
    plan = core.layout(a['partitions'], int(disk['size']), manifest['squashfs_size'], min_overlay=min_overlay)
    # Generate every configurable string before the first destructive operation.
    core.network_batch(a)
    core.policy_batch(a, run('uci', '-X', 'show', 'firewall'))
    return a, plan, rom, media, component_plan


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
    prepared = prepare(a, manifest, payload_dir)
    if len(prepared) == 4:
        a, plan, source, media = prepared
        component_plan = None
    else:
        a, plan, source, media, component_plan = prepared
    if dry_run:
        result = {'summary': json.loads(core.summary(a)), 'layout': plan,
                  'sfdisk': core.sfdisk_script(a['disk'], plan),
                  'disk': next(d for d in discover()[2] if d['path'] == a['disk'])}
        if component_plan is not None:
            result['components'] = component_plan
        return result
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
        if component_plan and component_plan.get('top_packages'):
            progress(65, 'Installing selected components')
            install_components(target, component_plan, payload_dir, base_root=rom)
        progress(80, 'Writing network, firewall and accounts')
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
            fb = dict(a['accounts']['user'])
            if 'components' in a and a['components'] is not None:
                fb['components'] = list(a['components'])
            write_private(settings / 'firstboot.json', json.dumps(fb))
        write_private(settings / 'install.json', core.summary(a) + '\n')
        progress(95, 'Synchronizing disks')
    finally:
        # Keep cleanup failures visible and attempt every unmount.
        original_error = sys.exc_info()[1]
        errors = []
        for path in reversed(mounted):
            try:
                run('umount', str(path))
            except Exception as exc:
                errors.append(str(exc))
        os.sync()
        if errors:
            cleanup_error = 'Unmount cleanup failed: ' + '; '.join(errors)
            if original_error is None:
                raise RuntimeError(cleanup_error)
            raise RuntimeError(str(original_error) + '\n' + cleanup_error) from original_error
    progress(100, 'Installation complete')
    return plan
