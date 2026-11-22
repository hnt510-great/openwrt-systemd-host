#!/usr/bin/env python3
"""Compute a boundary-safe SHA-256 cache key for OpenWrt rootfs assembly."""
import argparse
import hashlib
import os
from pathlib import Path
import stat
import sys


def update_record(h, tag, payload):
    data = payload.encode('utf-8') if isinstance(payload, str) else payload
    h.update(f'{tag}:{len(data)}:'.encode('ascii'))
    h.update(data)
    h.update(b'\n')


def hash_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def hash_tree(h, root):
    root = Path(root)
    if not root.is_dir():
        update_record(h, 'overlay-absent', str(root))
        return
    entries = []
    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        dirnames.sort()
        filenames.sort()
        base = Path(dirpath)
        for name in dirnames + filenames:
            full = base / name
            rel = full.relative_to(root).as_posix()
            entries.append((rel, full))
    entries.sort(key=lambda item: item[0])
    for rel, full in entries:
        st = full.lstat()
        mode = oct(stat.S_IMODE(st.st_mode))
        if stat.S_ISLNK(st.st_mode):
            update_record(h, 'overlay-link', f'{rel}\0{mode}\0{os.readlink(full)}')
        elif stat.S_ISDIR(st.st_mode):
            update_record(h, 'overlay-dir', f'{rel}\0{mode}')
        elif stat.S_ISREG(st.st_mode):
            update_record(h, 'overlay-file', f'{rel}\0{mode}\0{st.st_size}\0{hash_file(full)}')
        else:
            update_record(h, 'overlay-other', f'{rel}\0{mode}\0{st.st_mode}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--install-args', required=True)
    parser.add_argument('--epoch', default='')
    parser.add_argument('--input-file', action='append', default=[])
    parser.add_argument('--overlay-dir', action='append', default=[])
    args = parser.parse_args()

    h = hashlib.sha256()
    update_record(h, 'schema', '2')
    update_record(h, 'install-args', args.install_args)
    update_record(h, 'epoch', args.epoch)
    for raw in args.input_file:
        if not raw:
            continue
        path = Path(raw)
        if path.is_file():
            st = path.stat()
            update_record(h, 'input-file', f'{path}\0{st.st_size}\0{hash_file(path)}')
        else:
            update_record(h, 'input-missing', str(path))
    for raw in args.overlay_dir:
        if raw:
            hash_tree(h, raw)
    print(h.hexdigest())


if __name__ == '__main__':
    main()
