#!/usr/bin/env python3
"""Build distribution-style kernel packages from the staged kernel build.

Produces, for kernel release R (``<kver>-<N>-openwrt``) and version V:

* ``linux-image-R``: vmlinuz, config, System.map and every selected module,
* ``linux-headers-R``: the prepared header tree (when kernel-dev-headers is
  selected),
* ``linux-image-openwrt``: the metapackage that always follows the newest R.

The kmod-* packages keep only their configuration, so userspace no longer
depends on a particular kernel. Published package identities are immutable:
the same name and version with different bytes require a new build number.
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

RELEASE = re.compile(r'[0-9][A-Za-z0-9._+-]{1,62}')
ORIGIN = 'kernel-packages'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def inventory(root):
    return {p.relative_to(root).as_posix():
            {'link': os.readlink(p)} if p.is_symlink() else {'sha256': digest(p)}
            for p in sorted(root.rglob('*')) if p.is_file() or p.is_symlink()}


def selected_kmods(config):
    names = set()
    for line in config.read_text().splitlines():
        match = re.fullmatch(r'CONFIG_PACKAGE_(kmod-[A-Za-z0-9._+-]+)=[ym]', line)
        if match:
            names.add(match[1])
    return names


def selected(config, name):
    return any(re.fullmatch(r'CONFIG_PACKAGE_' + re.escape(name) + '=[ym]', line)
               for line in config.read_text().splitlines())


def merge(source, destination, owners, owner):
    """Copy a staged tree, refusing two packages that disagree on a file."""
    for path in sorted(source.rglob('*')):
        relative = path.relative_to(source)
        target = destination / relative
        if path.is_dir() and not path.is_symlink():
            target.mkdir(parents=True, exist_ok=True)
            continue
        key = relative.as_posix()
        if target.exists() or target.is_symlink():
            same = (os.readlink(path) == os.readlink(target) if path.is_symlink() and target.is_symlink()
                    else not path.is_symlink() and not target.is_symlink() and digest(path) == digest(target))
            if not same:
                raise ValueError(f'Conflicting staged file {key}: {owners[key]} and {owner}')
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if path.is_symlink():
            target.symlink_to(os.readlink(path))
        else:
            shutil.copy2(path, target)
        owners[key] = owner


def package(apk, fakeroot, key, root, output, name, version, depends, description, tags):
    """Sign one reproducible package; never replace an existing identity."""
    root.chmod(0o755)
    for path in root.rglob('*'):
        if not path.is_symlink():
            path.chmod(0o755 if path.is_dir() or path.stat().st_mode & 0o111 else 0o644)
    command = [str(fakeroot), str(apk), 'mkpkg', '--info', 'name:' + name,
               '--info', 'version:' + version, '--info', 'arch:x86_64',
               '--info', 'license:GPL-2.0-only', '--info', 'origin:' + ORIGIN,
               '--info', 'description:' + description, '--info', 'tags:' + tags,
               '--info', 'depends:' + ' '.join(depends), '--files', str(root)]
    if key:
        command += ['--sign', str(key)]
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=output) as tmp:
        candidate = Path(tmp) / (name + '-' + version + '.apk')
        subprocess.run(command + ['--output', str(candidate)], check=True,
                       env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})
        destination = output / candidate.name
        if destination.exists():
            if digest(destination) != digest(candidate):
                raise ValueError('Immutable kernel package changed: ' + destination.name +
                                 '; build with a new kernel build number')
            return destination
        candidate.replace(destination)
        return destination


def bundle(args):
    release, version = args.release, args.version
    if not RELEASE.fullmatch(release):
        raise ValueError('Invalid or overlong kernel release')
    if not re.fullmatch(r'[0-9][0-9a-z._]*-r' + str(args.sequence), version):
        raise ValueError('Kernel package version must end with the build number')
    stage = args.stage
    kernel = stage / 'kernel'
    if not (kernel / 'vmlinuz').is_file() or not (kernel / 'config').is_file():
        raise ValueError('Kernel image was not staged for ' + release + '; run a complete build')
    wanted = selected_kmods(args.config)
    packed = {p.name for p in (stage / 'kmods').iterdir()} if (stage / 'kmods').is_dir() else set()
    missing = sorted(wanted - packed)
    if missing:
        raise ValueError('Selected kmods were not packed for ' + release + ': ' + ', '.join(missing) +
                         '; run a complete build')
    output = args.output
    built = []
    with tempfile.TemporaryDirectory(prefix='kernel-bundle-', dir=stage.parent) as temp:
        image = Path(temp) / 'image'
        owners = {}
        modules = kernel / 'usr/lib/modules' / release
        if modules.is_dir():
            merge(modules, image / 'usr/lib/modules' / release, owners, 'kernel')
        (image / 'usr/lib/modules' / release).mkdir(parents=True, exist_ok=True)
        for name in sorted(wanted):
            tree = stage / 'kmods' / name / 'usr/lib/modules' / release
            if tree.is_dir():
                merge(tree, image / 'usr/lib/modules' / release, owners, name)
        count = sum(1 for _ in (image / 'usr/lib/modules' / release).rglob('*.ko'))
        metadata = image / 'usr/lib/openwrt-kernel' / release
        metadata.mkdir(parents=True)
        for item in ('vmlinuz', 'config', 'System.map'):
            if (kernel / item).is_file():
                shutil.copyfile(kernel / item, metadata / item)
        files = inventory(image)
        (metadata / 'image.json').write_text(json.dumps({
            'schema': 2, 'release': release, 'version': version, 'sequence': args.sequence,
            'package': 'linux-image-' + release,
            'kernel_sha256': digest(metadata / 'vmlinuz'),
            'config_sha256': digest(metadata / 'config'),
            'modules': count, 'kmods': sorted(wanted), 'files': files},
            sort_keys=True, indent=2) + '\n')
        built.append(package(args.apk, args.fakeroot, args.key, image, output,
                             'linux-image-' + release, version, ['openwrt-kernel-upgrade'],
                             'Linux kernel ' + release + ' with its modules',
                             'openwrt:kernel-image=' + release))
        if selected(args.config, 'kernel-dev-headers'):
            headers = stage / 'headers'
            if not headers.is_dir():
                raise ValueError('Kernel headers were not staged for ' + release)
            tree = Path(temp) / 'headers'
            shutil.copytree(headers, tree, symlinks=True)
            built.append(package(args.apk, args.fakeroot, args.key, tree, output,
                                 'linux-headers-' + release, version, [],
                                 'Linux kernel headers for ' + release,
                                 'openwrt:kernel-headers=' + release))
        meta = Path(temp) / 'meta'
        meta.mkdir()
        built.append(package(args.apk, args.fakeroot, args.key, meta, output,
                             'linux-image-openwrt', version,
                             ['linux-image-' + release + '=' + version, 'openwrt-kernel-upgrade',
                              'openwrt-kernel-policy>=3.0.5-r17'],
                             'Latest OpenWrt kernel', 'openwrt:kernel-meta'))
    for path in built:
        print('kernel-bundle: ' + path.name)
    return built


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('stage', 'config', 'output', 'apk', 'fakeroot'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--release', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--sequence', type=int, required=True)
    parser.add_argument('--key', type=Path)
    try:
        bundle(parser.parse_args())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        raise SystemExit('kernel-bundle: ' + str(error))
