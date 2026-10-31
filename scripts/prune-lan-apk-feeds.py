#!/usr/bin/env python3
"""Remove published APK snapshots that no ABI alias or channel references.

Every publication creates an immutable directory under public/snapshots and
repoints public/abi/<kernel> at it. Superseded snapshots stay behind. This tool
deletes only snapshots that are unreachable from any symlink in the published
tree (abi/*, userspace, rolling, kernel-upgrades). It never edits a live
snapshot, so published APK identities and the ABI aliases are untouched.

Dry run by default; pass --apply to delete.
"""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import sys
import time

LOCKS = ('.upgrade-publish.lock', '.publish.lock', '.kernel-publish.lock')


def referenced(public):
    """Resolved directories reachable through any symlink below public/."""
    found = set()
    for top in public.iterdir():
        links = [top] if top.is_symlink() else (
            [p for p in top.iterdir() if p.is_symlink()] if top.is_dir() else [])
        for link in links:
            try:
                found.add(link.resolve(strict=True))
            except OSError:
                print(f'warning: dangling link {link}', file=sys.stderr)
    return found


def tree_stats(path, seen):
    """Bytes that deleting path would free (hardlinks shared elsewhere excluded)."""
    freed = 0
    for item in path.rglob('*'):
        if item.is_file() and not item.is_symlink():
            st = item.stat()
            key = (st.st_dev, st.st_ino)
            if key in seen:
                continue
            seen.add(key)
            freed += st.st_size
    return freed


def prune(destination, apply, grace):
    public = destination / 'public'
    snapshots = public / 'snapshots'
    handles = []
    try:
        for name in LOCKS:
            handle = (destination / name).open('a')
            handles.append(handle)
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('A publication is in progress; try again later')
    live = referenced(public)
    live_files = set()
    for snapshot in live:
        if snapshot.is_dir():
            for item in snapshot.rglob('*'):
                if item.is_file():
                    st = item.stat()
                    live_files.add((st.st_dev, st.st_ino))
    now = time.time()
    removed = []
    freed_total = 0
    for snapshot in sorted(snapshots.iterdir()):
        if not snapshot.is_dir() or snapshot.is_symlink() or snapshot.resolve() in live:
            continue
        if now - snapshot.stat().st_mtime < grace:
            print(f'skip (newer than grace period): {snapshot.name}')
            continue
        freed = tree_stats(snapshot, set(live_files))
        freed_total += freed
        removed.append({'snapshot': snapshot.name, 'freed_bytes': freed})
        print(f'{"remove" if apply else "would remove"}: {snapshot.name} '
              f'({freed / 2**20:.1f} MiB unique)')
        if apply:
            shutil.rmtree(snapshot)
    kept = sum(1 for s in live if s.parent == snapshots)
    print(json.dumps({'applied': apply, 'removed': len(removed), 'kept_live': kept,
                      'freed_bytes': freed_total}, indent=2))


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--config', type=Path,
                        default=Path(__file__).resolve().parent.parent / 'configs/lan-apk-feeds.json')
    parser.add_argument('--grace-seconds', type=int, default=3600,
                        help='Never touch snapshots modified more recently than this')
    parser.add_argument('--apply', action='store_true', help='Delete (default is a dry run)')
    args = parser.parse_args()
    destination = args.destination or Path(
        json.loads(args.config.read_text()).get('destination', '/srv/openwrt-feeds'))
    prune(destination.resolve(), args.apply, args.grace_seconds)


if __name__ == '__main__':
    main()
