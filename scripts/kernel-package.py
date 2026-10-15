#!/usr/bin/env python3
"""Split an OpenWrt tracker into a signed, independently installable payload.

Runs after strip and merge-usr, before mkpkg. Never operates on a live /boot.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, sort_keys=True, indent=2) + '\n')


def inventory(root):
    return {p.relative_to(root).as_posix():
            {'link': os.readlink(p)} if p.is_symlink() else {'sha256': digest(p)}
            for p in sorted(root.rglob('*')) if p.is_file() or p.is_symlink()}


def package(apk, key, root, output, name, version, depends, description, tags):
    # Payloads are built outside the normal package-pack fakeroot invocation.
    # Never encode the build user's ownership or temporary-directory mode.
    root.chmod(0o755)
    for path in root.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    fakeroot = Path(apk).with_name('fakeroot')
    if not fakeroot.is_file():
        raise ValueError('Host fakeroot is required for root-owned kernel payloads')
    command = [str(fakeroot), apk, 'mkpkg', '--info', 'name:' + name,
               '--info', 'version:' + version, '--info', 'arch:x86_64',
               '--info', 'license:GPL-2.0-only', '--info', 'origin:kernel-generations',
               '--info', 'description:' + description, '--info', 'tags:' + tags,
               '--info', 'depends:' + ' '.join(depends), '--files', str(root)]
    if key:
        command += ['--sign', key]
    # Building the same generation twice must never silently change its bytes.
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        candidate = Path(tmp) / (name + '-' + version + '.apk')
        subprocess.run(command + ['--output', str(candidate)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})
        destination = output / candidate.name
        if '-owrt-' in name and any(p.name != candidate.name for p in output.glob(name + '-*.apk')):
            raise ValueError('Immutable generation version changed: ' + name + '; increase sequence')
        if destination.exists() and digest(destination) != digest(candidate):
            raise ValueError('Immutable generation changed: ' + name + '; increase sequence')
        if not destination.exists():
            candidate.replace(destination)


def split(args):
    root = args.root
    generation = args.generation
    if not re.fullmatch(r'[0-9][A-Za-z0-9._+-]{1,62}', generation):
        raise ValueError('Invalid or overlong kernel release')
    match = re.fullmatch(r'(.+)~([0-9a-f]{32})-r([0-9]+)', args.abi)
    if (not match or '-owrt-' + match[2] + '-r' + match[3] + '-g' not in generation
            or not generation.endswith('-g' + str(args.sequence))):
        raise ValueError('Generation and exact OpenWrt ABI disagree')
    depends = [re.sub(r'\s|[()]', '', d) for d in args.depends.split(',') if d.strip()]
    image = 'linux-image-' + generation
    name = image if args.name == 'kernel' else args.name + '-' + generation
    with tempfile.TemporaryDirectory(prefix='kernel-payload-', dir=root.parent) as tmp:
        payload = Path(tmp)
        moves = [('usr/lib/modules/' + generation, 'usr/lib/modules/' + generation),
                 ('usr/src/linux-headers-' + generation, 'usr/src/linux-headers-' + generation),
                 ('etc/modules.d', 'usr/lib/modules/' + generation + '/openwrt/modules.d'),
                 ('etc/modules-boot.d', 'usr/lib/modules/' + generation + '/openwrt/modules-boot.d'),
                 ('etc/modprobe.d', 'usr/lib/modules/' + generation + '/openwrt/modprobe.d')]
        for source, target in moves:
            src, dst = root / source, payload / target
            if src.exists():
                dst.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), dst)
        metadata = payload / 'usr/lib/openwrt-kernel' / generation
        metadata.mkdir(parents=True, exist_ok=True)
        for module in payload.rglob('*.ko'):
            vermagic = re.search(rb'vermagic=([^\x00]+)', module.read_bytes())
            if not vermagic or vermagic[1].split()[0].decode() != generation:
                raise ValueError('Compiled module release differs from generation: ' + module.name)
        if args.name == 'kernel':
            actual_release = args.config.parent / 'include/config/kernel.release'
            if actual_release.read_text().strip() != generation:
                raise ValueError('Compiled kernel release differs from payload directory')
            shutil.copyfile(args.kernel, metadata / 'vmlinuz')
            shutil.copyfile(args.config, metadata / 'config')
            write_json(metadata / 'image.json', {
                'schema': 1, 'generation': generation, 'release': generation,
                'abi': args.abi, 'sequence': args.sequence,
                'package': name, 'version': args.version,
                'kernel_sha256': digest(metadata / 'vmlinuz'),
                'config_sha256': digest(metadata / 'config'), 'files': inventory(payload)})
            payload_depends = []
        else:
            payload_depends = [image + '=' + args.abi]
            for dependency in depends:
                if dependency.startswith('kmod-'):
                    dep_name, comparator, version = re.fullmatch(
                        r'([^<>=~]+)([<>=~]*)(.*)', dependency).groups()
                    payload_depends.append(dep_name + '-' + generation + comparator + version)
            write_json(metadata / 'kmods' / (args.name + '.json'), {
                'name': args.name, 'package': name, 'version': args.version,
                'abi': args.abi, 'release': generation,
                'files': inventory(payload)})
        # OpenWrt's supplementary file list is consumed by package scripts.
        lists = root / 'usr/lib/apk/packages'
        (lists / (args.name + '.list')).write_text(
            ''.join('/' + p + '\n' for p in inventory(root)))
        package(args.apk, args.key, payload, args.output, name, args.version,
                payload_depends, 'Immutable OpenWrt kernel payload',
                'openwrt:kernel-generation=' + generation)
        if args.name == 'kernel':
            with tempfile.TemporaryDirectory(dir=root.parent) as tracking:
                tracker = Path(tracking)
                write_json(tracker / 'usr/share/openwrt-kernel/selected.json', {
                    'generation': generation, 'abi': args.abi, 'sequence': args.sequence})
                package(args.apk, args.key, tracker, args.output, 'linux-image-openwrt',
                        '1-r' + str(args.sequence), [image + '=' + args.abi,
                        'kernel=' + args.abi, 'openwrt-kernel-upgrade',
                        'openwrt-kernel-policy>=3.0.5-r5'],
                        'OpenWrt kernel upgrade track', 'openwrt:kernel-tracker')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('root', 'output', 'kernel', 'config'):
        parser.add_argument('--' + option, type=Path, required=True)
    for option in ('name', 'version', 'abi', 'generation', 'apk'):
        parser.add_argument('--' + option, required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--depends', default='')
    parser.add_argument('--key')
    split(parser.parse_args())
