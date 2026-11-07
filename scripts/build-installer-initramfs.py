#!/usr/bin/env python3
"""Freeze trusted target tools into the installer's small optical bootstrap."""
import argparse
import gzip
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


# Import the shared helpers without dirtying tracked/generated source caches.
_bytecode = sys.dont_write_bytecode
try:
    sys.dont_write_bytecode = True
    elf = load('installer_elf', ROOT / 'scripts/elf-abi.py')
    cpio = load('installer_cpio', ROOT / 'package/custom/openwrt-kernel-upgrade/files/kernelctl')
finally:
    sys.dont_write_bytecode = _bytecode


def build(source, init, config, output):
    source = source.resolve()
    settings = set(config.read_text().splitlines())
    for name in ('BLK_DEV_INITRD', 'RD_GZIP', 'DEVTMPFS', 'BLK_DEV_SR', 'BLK_DEV_LOOP', 'ISO9660_FS', 'SQUASHFS'):
        if f'CONFIG_{name}=y' not in settings:
            raise ValueError('Installer bootstrap needs built-in CONFIG_' + name)
    with tempfile.TemporaryDirectory(prefix='installer-initramfs-') as temp:
        root = Path(temp)
        for directory in ('dev', 'proc', 'sys', 'run', 'newroot', 'usr/bin', 'usr/sbin', 'usr/lib'):
            (root / directory).mkdir(parents=True, exist_ok=True)
        for name, target in (('bin', 'usr/bin'), ('sbin', 'usr/sbin'), ('lib', 'usr/lib'), ('lib64', 'usr/lib'), ('usr/lib64', 'lib')):
            (root / name).symlink_to(target)
        copied = set()

        def resolve(path):
            # Absolute target symlinks belong to the target root, never the host.
            pending = list(path.relative_to(source).parts)
            parts = []
            links = 0
            while pending:
                part = pending.pop(0)
                if part == '..':
                    if not parts:
                        raise ValueError('Target symlink escapes bootstrap root')
                    parts.pop()
                elif part not in ('', '.'):
                    candidate = source.joinpath(*parts, part)
                    if candidate.is_symlink():
                        links += 1
                        if links > 64:
                            raise ValueError('Target symlink cycle')
                        target = Path(os.readlink(candidate))
                        if target.is_absolute():
                            parts = []
                        pending = [p for p in target.parts if p != '/'] + pending
                    else:
                        parts.append(part)
            return source.joinpath(*parts)

        def copy_binary(path):
            path = resolve(path)
            if not path.is_relative_to(source) or not path.is_file():
                raise ValueError('Missing or escaping target bootstrap binary: ' + str(path))
            relative = path.relative_to(source)
            if path in copied:
                return '/' + relative.as_posix()
            copied.add(path)
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
            metadata = elf.elf(path)
            if metadata:
                for needed in metadata['needed'] + ([metadata['interpreter']] if metadata['interpreter'] else []):
                    candidates = [source / needed.lstrip('/')] if '/' in needed else [source / 'usr/lib' / needed]
                    library = next((p for p in candidates if resolve(p).is_file()), None)
                    if library is None:
                        raise ValueError('Missing target library: ' + needed)
                    actual = copy_binary(library)
                    alias = root / elf.canonical('/' + library.relative_to(source).as_posix()).lstrip('/')
                    if not alias.exists() and not alias.is_symlink():
                        alias.symlink_to(actual)
            return '/' + relative.as_posix()

        for name in ('sh', 'mount', 'umount', 'mkdir', 'cat', 'head', 'ln', 'sleep', 'switch_root', 'hexdump', 'blkid', 'losetup'):
            path = next((source / directory / name for directory in ('usr/bin', 'usr/sbin') if resolve(source / directory / name).is_file()), None)
            if path is None:
                raise ValueError('Missing target bootstrap tool: ' + name)
            binary = copy_binary(path)
            link = root / 'usr/bin' / name
            if not link.exists() and not link.is_symlink():
                link.symlink_to(binary)
        shutil.copy2(init, root / 'init')
        (root / 'init').chmod(0o755)
        output.write_bytes(gzip.compress(cpio.cpio_archive(root), mtime=0))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('root', 'init', 'kernel-config', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    args = parser.parse_args()
    build(args.root, args.init, args.kernel_config, args.output)


if __name__ == '__main__':
    main()
