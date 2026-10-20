#!/usr/bin/env python3
"""Lock ELF ucode consumers and native modules to the interpreter's ABI."""
import argparse
import mmap
from pathlib import Path
import re
import subprocess


def inspect(root, readelf='readelf'):
    """Return actual DT_NEEDED ABIs and whether the package owns a C module."""
    abis = set()
    module = False
    for path in root.rglob('*'):
        if path.is_symlink() or not path.is_file():
            continue
        relative = path.relative_to(root).as_posix()
        native_module = (relative.startswith(('usr/lib/ucode/', 'lib/ucode/'))
                         and path.suffix == '.so')
        with path.open('rb') as stream:
            if stream.read(4) != b'\x7fELF':
                continue
            module |= native_module
            with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
                if data.find(b'libucode.so.') < 0:
                    continue
        dynamic = subprocess.check_output([str(readelf), '-d', str(path)], text=True)
        abis.update(re.findall(r'\(NEEDED\).*\[libucode\.so\.([0-9]+)\]', dynamic))
    return abis, module


def requirements(root, name, abi, readelf='readelf'):
    abis, module = inspect(root, readelf)
    if not abis and not module:
        return []
    if not re.fullmatch(r'[0-9]+', abi):
        raise ValueError(f'{name}: missing staged libucode ABI; build libucode first')
    if abis - {abi}:
        raise ValueError(f'{name}: ELF uses libucode ABI {sorted(abis)}, expected {abi}; '
                         'rebuild this package against the current headers/library')
    # ucode is the sole ABI provider. The unique interpreter package makes
    # different module/embedded-runtime ABIs mutually exclusive in the solver,
    # while unrelated versioned libucode libraries can still coexist.
    if name == 'ucode':
        return []
    return [f'libucode{abi}', f'ucode-abi={abi}']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--package', required=True)
    parser.add_argument('--abi', default='')
    parser.add_argument('--readelf', default='readelf')
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    try:
        dependencies = requirements(args.root, args.package, args.abi, args.readelf)
        args.output.write_text(' '.join(dependencies) + '\n')
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
