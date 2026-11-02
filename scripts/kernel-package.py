#!/usr/bin/env python3
"""Stage kernel, module and header files for the per-release kernel packages.

Runs from the package-pack hook after strip and merge-usr, before mkpkg. The
kmod-* packages keep only their configuration (autoload, modprobe.d) and
dependencies; module binaries, the kernel image and the header tree are moved
into a staging tree that scripts/kernel-bundle.py turns into
linux-image-<release> and linux-headers-<release>, like a distribution kernel.
Never operates on a live /boot.
"""
import argparse
import os
from pathlib import Path
import re
import shutil
import tempfile

RELEASE = re.compile(r'[0-9][A-Za-z0-9._+-]{1,62}')


def replace_tree(entries, destination):
    """Atomically replace destination with the given (source, relative) moves."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix='.' + destination.name + '.', dir=destination.parent))
    try:
        for source, relative in entries:
            target = staging / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if source.is_symlink() or source.is_file():
                shutil.move(str(source), target)
            elif source.is_dir():
                shutil.move(str(source), target)
        old = destination.with_name('.' + destination.name + '.old')
        if destination.exists():
            if old.exists():
                shutil.rmtree(old)
            destination.rename(old)
        staging.rename(destination)
        if old.exists():
            shutil.rmtree(old)
    finally:
        if staging.exists():
            shutil.rmtree(staging)


def check_vermagic(tree, release):
    for module in sorted(tree.rglob('*.ko')):
        vermagic = re.search(rb'vermagic=([^\x00]+)', module.read_bytes())
        if not vermagic or vermagic[1].split()[0].decode() != release:
            raise ValueError('Compiled module release differs from kernel release: ' + module.name)


def file_list(root, name):
    """Rewrite OpenWrt's supplementary file list for the files that remain."""
    lists = root / 'usr/lib/apk/packages'
    if not lists.is_dir():
        return
    # Same order and content as the previous payload splitter, so packages
    # whose remaining files do not change keep identical bytes.
    (lists / (name + '.list')).write_text(''.join(
        '/' + p.relative_to(root).as_posix() + '\n'
        for p in sorted(root.rglob('*')) if p.is_file() or p.is_symlink()))


def stage(args):
    root, release, name = args.root, args.release, args.name
    if not RELEASE.fullmatch(release):
        raise ValueError('Invalid or overlong kernel release')
    modules = root / 'usr/lib/modules' / release
    if name == 'kernel':
        actual = (args.linux / 'include/config/kernel.release').read_text().strip()
        if actual != release:
            raise ValueError('Compiled kernel release differs from the configured release')
        entries = [(modules, Path('usr/lib/modules') / release)] if modules.exists() else []
        replace_tree(entries, args.stage / 'kernel')
        kernel = args.stage / 'kernel'
        for source, target in ((args.linux / 'arch/x86/boot/bzImage', 'vmlinuz'),
                               (args.linux / '.config', 'config'),
                               (args.linux / 'System.map', 'System.map')):
            if source.is_file():
                shutil.copyfile(source, kernel / target)
        if not (kernel / 'vmlinuz').is_file():
            raise ValueError('Kernel image is missing; build the kernel first')
    elif name == 'kernel-dev-headers':
        headers = root / 'usr/src' / ('linux-headers-' + release)
        entries = [(path, path.relative_to(root)) for path in (headers, modules) if path.exists()]
        if not headers.is_dir():
            raise ValueError('Kernel header tree is missing')
        replace_tree(entries, args.stage / 'headers')
    elif name.startswith('kmod-'):
        if modules.exists():
            check_vermagic(modules, release)
        entries = [(modules, Path('usr/lib/modules') / release)] if modules.exists() else []
        # An empty entry records that the selected kmod was packed for this release.
        replace_tree(entries, args.stage / 'kmods' / name)
    else:
        raise ValueError('Not a kernel package: ' + name)
    # The parent usr/lib/modules directory stays, as it always has.
    if modules.is_dir() and not any(modules.iterdir()):
        modules.rmdir()
    file_list(root, name)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for option in ('root', 'stage', 'linux'):
        parser.add_argument('--' + option, type=Path, required=True)
    parser.add_argument('--name', required=True)
    parser.add_argument('--release', required=True)
    try:
        stage(parser.parse_args())
    except (OSError, ValueError) as error:
        raise SystemExit('kernel-package: ' + str(error))
