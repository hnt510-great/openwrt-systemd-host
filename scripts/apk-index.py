#!/usr/bin/env python3
"""Atomic APK package merge and per-feed index generation with conflict checks."""
import argparse
import filecmp
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def merge_links(args):
    dest = Path(args.dest)
    ext = '.' + args.ext.lstrip('.')
    seen = {}
    overrides = set()
    for raw_dir in getattr(args, 'override_dirs', ()) or ():
        pdir = Path(raw_dir)
        if not pdir.is_dir():
            continue
        for entry in sorted(pdir.iterdir()):
            if not entry.name.endswith(ext) or not entry.is_file():
                continue
            prev = seen.get(entry.name)
            if prev is not None:
                if prev.resolve() == entry.resolve():
                    continue
                if not filecmp.cmp(prev, entry, shallow=False):
                    raise ValueError(
                        f'Conflicting override package filename {entry.name}: {prev} vs {entry}'
                    )
                continue
            seen[entry.name] = entry
            overrides.add(entry.name)

    for raw_dir in args.dirs:
        pdir = Path(raw_dir)
        if not pdir.is_dir():
            continue
        for entry in sorted(pdir.iterdir()):
            if not entry.name.endswith(ext) or not entry.is_file():
                continue
            if entry.name in overrides:
                continue
            prev = seen.get(entry.name)
            if prev is not None:
                if prev.resolve() == entry.resolve():
                    continue
                if not filecmp.cmp(prev, entry, shallow=False):
                    raise ValueError(
                        f'Conflicting package filename {entry.name}: {prev} vs {entry}'
                    )
                continue
            seen[entry.name] = entry

    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_dir = Path(tempfile.mkdtemp(dir=dest.parent, prefix=f'.{dest.name}.new.'))
    old_dir = None
    try:
        for name, src in sorted(seen.items()):
            os.symlink(src, tmp_dir / name)
        if dest.exists():
            old_dir = Path(tempfile.mkdtemp(dir=dest.parent, prefix=f'.{dest.name}.old.'))
            old_dir.rmdir()
            os.replace(dest, old_dir)
        os.replace(tmp_dir, dest)
        if old_dir is not None and old_dir.exists():
            shutil.rmtree(old_dir)
    except BaseException:
        if old_dir is not None and old_dir.exists() and not dest.exists():
            os.replace(old_dir, dest)
        if tmp_dir.exists():
            shutil.rmtree(tmp_dir, ignore_errors=True)
        raise


def validate_index_json(path):
    if not path.is_file() or path.stat().st_size == 0:
        return False
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError):
        return False
    return isinstance(data, dict) and 'packages' in data


def validate_adb(apk_bin, adb_path):
    if not adb_path.is_file() or adb_path.stat().st_size == 0:
        return False
    res = subprocess.run(
        [str(apk_bin), 'adbdump', '--format', 'json', str(adb_path)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    return res.returncode == 0


def index_dir(args):
    directory = Path(args.dir)
    directory.mkdir(parents=True, exist_ok=True)
    apks = sorted(p.name for p in directory.iterdir() if p.name.endswith('.apk') and p.is_file())
    adb = directory / 'packages.adb'
    index_json = directory / 'index.json'
    stamp = directory / '.index.manifest'

    if not apks:
        adb.unlink(missing_ok=True)
        index_json.unlink(missing_ok=True)
        stamp.unlink(missing_ok=True)
        return

    manifest_lines = []
    for name in apks:
        st = (directory / name).stat()
        manifest_lines.append(f'{name}\t{st.st_size}\t{st.st_mtime_ns}\t{st.st_ctime_ns}')
    if args.sign:
        st = Path(args.sign).stat()
        manifest_lines.append(f'@sign\t{args.sign}\t{st.st_size}\t{st.st_mtime_ns}')
    manifest = '\n'.join(manifest_lines) + '\n'

    if (
        not args.force
        and stamp.is_file()
        and stamp.read_text() == manifest
        and validate_index_json(index_json)
        and validate_adb(args.apk, adb)
    ):
        return

    with tempfile.TemporaryDirectory(dir=directory, prefix='.index-tmp.') as tmp:
        tmp_path = Path(tmp)
        tmp_adb = tmp_path / 'packages.adb'
        tmp_json = tmp_path / 'index.json'
        tmp_stamp = tmp_path / '.index.manifest'

        cmd = [
            str(args.apk), 'mkndx',
            '--root', str(args.root),
            '--keys-dir', str(args.keys_dir),
            '--allow-untrusted',
        ]
        if args.sign:
            cmd.extend(['--sign', str(args.sign)])
        cmd.extend(['--output', str(tmp_adb), *apks])
        subprocess.run(cmd, cwd=directory, check=True)

        if not tmp_adb.is_file() or tmp_adb.stat().st_size == 0:
            raise ValueError(f'{directory}: apk mkndx produced empty index')

        if args.make_index_json:
            dump = subprocess.run(
                [str(args.apk), 'adbdump', '--format', 'json', str(tmp_adb)],
                cwd=directory,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if dump.returncode != 0:
                sys.stderr.write(dump.stderr.decode(errors='replace'))
                raise ValueError(f'{directory}: apk adbdump failed with exit {dump.returncode}')
            gen = subprocess.run(
                [str(args.make_index_json), '-f', 'apk', '-a', args.arch, '-'],
                input=dump.stdout,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
            if gen.returncode != 0:
                sys.stderr.write(gen.stderr.decode(errors='replace'))
                raise ValueError(f'{directory}: make-index-json.py failed with exit {gen.returncode}')
            tmp_json.write_bytes(gen.stdout)
            if not validate_index_json(tmp_json):
                raise ValueError(f'{directory}: generated invalid index.json')

        tmp_stamp.write_text(manifest)
        os.replace(tmp_adb, adb)
        if args.make_index_json:
            os.replace(tmp_json, index_json)
        os.replace(tmp_stamp, stamp)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='cmd', required=True)

    p_merge = sub.add_parser('merge')
    p_merge.add_argument('--dest', required=True)
    p_merge.add_argument('--ext', default='apk')
    p_merge.add_argument('--override-dir', dest='override_dirs', action='append', default=[])
    p_merge.add_argument('dirs', nargs='*')

    p_idx = sub.add_parser('index')
    p_idx.add_argument('--dir', required=True)
    p_idx.add_argument('--apk', required=True)
    p_idx.add_argument('--root', required=True)
    p_idx.add_argument('--keys-dir', required=True)
    p_idx.add_argument('--sign', default='')
    p_idx.add_argument('--make-index-json', default='')
    p_idx.add_argument('--arch', default='')
    p_idx.add_argument('--force', action='store_true')

    args = parser.parse_args()
    try:
        if args.cmd == 'merge':
            merge_links(args)
        elif args.cmd == 'index':
            index_dir(args)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f'apk-index.py: {exc}')


if __name__ == '__main__':
    main()
