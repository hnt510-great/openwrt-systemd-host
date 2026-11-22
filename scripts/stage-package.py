#!/usr/bin/env python3
"""Transactionally commit one package's private install tree to a shared OpenWrt staging root."""
import argparse
import errno
import fcntl
import filecmp
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import tempfile


OWNERS_SCHEMA = 1
OWNERS_FILE = '.owners.json'
PENDING_LINK = '.stage-pending'


def relative(value):
    path = Path(value)
    if path.is_absolute() or '..' in path.parts:
        raise ValueError(f'invalid staging path {value!r}')
    posix = path.as_posix()
    return '' if posix == '.' else posix


def read_list(path):
    if not path.is_file():
        return set()
    entries = set()
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line in ('.', './'):
            continue
        rel = relative(line.removeprefix('./'))
        if rel:
            entries.add(rel)
    return entries


def legacy_elf_inventory(record):
    if not record.is_file():
        return set()
    try:
        data = json.loads(record.read_text())
    except (OSError, ValueError):
        return set()
    paths = list(data.get('files', ())) + [
        p for p, target in data.get('links', {}).items() if p != target
    ]
    result = {relative(p.lstrip('/')) for p in paths if relative(p.lstrip('/'))}
    result.add('usr/lib/apk/packages/' + record.name)
    return result


def abi_base_matches(record_pkg, base_name):
    """Return True if record_pkg is base_name or base_name with an OpenWrt ABI suffix."""
    if record_pkg == base_name:
        return True
    if not record_pkg.startswith(base_name):
        return False
    suffix = record_pkg[len(base_name):]
    if base_name and base_name[-1].isdigit():
        return bool(re.fullmatch(r'-[0-9][0-9A-Za-z._-]*', suffix))
    return bool(re.fullmatch(r'[0-9][0-9A-Za-z._-]*', suffix))


def contents(tree):
    files, dirs = set(), set()

    def walk(directory):
        for path in directory.iterdir():
            name = path.relative_to(tree).as_posix()
            if path.is_symlink() or not path.is_dir():
                files.add(name)
            else:
                dirs.add(name)
                walk(path)

    walk(tree)
    return files, dirs


def same(left, right):
    if left.is_symlink() or right.is_symlink():
        return left.is_symlink() and right.is_symlink() and os.readlink(left) == os.readlink(right)
    return (
        left.is_file()
        and right.is_file()
        and stat.S_IMODE(left.lstat().st_mode) == stat.S_IMODE(right.lstat().st_mode)
        and filecmp.cmp(left, right, shallow=False)
    )


def rollback(root, pending):
    """Idempotently roll back an interrupted staging transaction."""
    if not pending.is_symlink():
        return
    work = pending.resolve(strict=False)
    journal_path = work / 'journal'
    if not work.is_dir() or not journal_path.is_file():
        pending.unlink(missing_ok=True)
        return
    operations = json.loads(journal_path.read_text())
    for name, kind in reversed(operations):
        path = root / name
        if kind == 'dir':
            path.mkdir(parents=True, exist_ok=True)
        elif kind == 'absent':
            if not os.path.lexists(path):
                continue
            if path.is_dir() and not path.is_symlink():
                try:
                    path.rmdir()
                except OSError as error:
                    if error.errno != errno.ENOTEMPTY:
                        raise
            else:
                path.unlink(missing_ok=True)
        else:
            # Keep backups intact until pending is unlinked so recovery itself is retryable.
            backup = work / 'backup' / name
            if not os.path.lexists(backup):
                continue
            if os.path.lexists(path) and os.path.samestat(backup.lstat(), path.lstat()):
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            temporary = work / 'restore'
            temporary.unlink(missing_ok=True)
            os.link(backup, temporary, follow_symlinks=False)
            os.replace(temporary, path)
    pending.unlink(missing_ok=True)
    shutil.rmtree(work, ignore_errors=True)


def recover_if_pending(root, manifest_dir):
    """Caller must hold LOCK_EX on the staging lock."""
    pending = Path(manifest_dir) / PENDING_LINK
    if pending.is_symlink():
        rollback(Path(root).resolve(), pending)
        return True
    return False


def build_initial_owners_index(root, manifest_dir, legacy_elf_dir=None):
    """One-time migration of provable existing owners into .owners.json."""
    path_owners = {}
    owner_entries = {}
    owner_meta = {}

    def add_owner(owner_id, entries, meta=None):
        entries = sorted(e for e in entries if e)
        if not entries:
            return
        owner_entries[owner_id] = entries
        if meta:
            owner_meta[owner_id] = meta
        for entry in entries:
            owners = path_owners.setdefault(entry, [])
            if owner_id not in owners:
                owners.append(owner_id)

    for list_file in sorted(manifest_dir.glob('*.list')):
        owner_id = list_file.stem
        add_owner(owner_id, read_list(list_file))

    if legacy_elf_dir and legacy_elf_dir.is_dir():
        for record in sorted(legacy_elf_dir.glob('*.elf.json')):
            pkg_name = record.name.removesuffix('.elf.json')
            legacy_id = f'legacy-elf:{pkg_name}'
            inv = legacy_elf_inventory(record)
            add_owner(legacy_id, inv, {'legacy_package': pkg_name})

    for entry in path_owners:
        path_owners[entry].sort()

    return {
        'schema': OWNERS_SCHEMA,
        'paths': path_owners,
        'owners': owner_entries,
        'meta': owner_meta,
    }


def load_or_migrate_owners(root, manifest_dir, legacy_elf_dir=None):
    index_path = manifest_dir / OWNERS_FILE
    if index_path.is_file():
        try:
            data = json.loads(index_path.read_text())
            if isinstance(data, dict) and data.get('schema') == OWNERS_SCHEMA:
                data.setdefault('paths', {})
                data.setdefault('owners', {})
                data.setdefault('meta', {})
                return data, False
        except (OSError, ValueError):
            pass
    return build_initial_owners_index(root, manifest_dir, legacy_elf_dir), True


def matching_legacy_owners(index, owner_id, legacy_package=None, legacy_base=None):
    """Find legacy-elf:* entries belonging to this package (including prior ABI suffixes)."""
    matched = []
    for existing_owner, meta in list(index['meta'].items()):
        if not existing_owner.startswith('legacy-elf:'):
            continue
        pkg = meta.get('legacy_package', existing_owner.removeprefix('legacy-elf:'))
        if legacy_package and pkg == legacy_package:
            matched.append(existing_owner)
        elif legacy_base and abi_base_matches(pkg, legacy_base):
            # Do not steal a record whose exact package name already has its own active manifest.
            if pkg != legacy_base and pkg in index['owners'] and pkg != owner_id:
                continue
            matched.append(existing_owner)
    return sorted(set(matched))


def commit(args, work, files, dirs):
    root = args.root
    manifest = args.manifest
    manifest_dir = manifest.parent
    pending = manifest_dir / PENDING_LINK
    if pending.is_symlink():
        rollback(root, pending)

    legacy_elf_dir = root / 'usr/lib/apk/packages' if (args.legacy_package or args.legacy_base) else None
    index, migrated = load_or_migrate_owners(root, manifest_dir, legacy_elf_dir)
    owner_id = args.owner or manifest.stem

    # Collect previous entries owned by this owner_id AND any matching legacy ELF records
    # (e.g. old ABI suffix example6.elf.json when upgrading to example7 or removing suffix).
    old = set(index['owners'].get(owner_id, ()))
    if not old and manifest.is_file():
        old.update(read_list(manifest))

    retired_legacy = matching_legacy_owners(
        index, owner_id, legacy_package=args.legacy_package, legacy_base=args.legacy_base
    )
    for leg_id in retired_legacy:
        old.update(index['owners'].get(leg_id, ()))

    # Also check any previous package_name stored in meta (e.g. ABI suffix changed between
    # two new-style commits).
    new = files | dirs
    obsolete = old - new
    incoming = work / 'incoming'

    # Exclude this owner and its retired legacy IDs when checking other owners.
    self_ids = {owner_id, *retired_legacy}
    path_owners = index['paths']

    # Check conflicts for all incoming files that already exist on disk.
    skip_write = set()
    for name in sorted(files):
        dest_path = root / name
        if not os.path.lexists(dest_path):
            continue
        other_owners = sorted(o for o in path_owners.get(name, ()) if o not in self_ids)
        if other_owners:
            if not same(incoming / name, dest_path):
                raise ValueError(
                    f'{owner_id}: conflicting staged file /{name} already owned by {", ".join(other_owners)}'
                )
            skip_write.add(name)

    files_to_write = files - skip_write

    # Only remove obsolete paths that have no other remaining owners.
    removable_obsolete = set()
    for name in obsolete:
        other_owners = [o for o in path_owners.get(name, ()) if o not in self_ids]
        if not other_owners:
            removable_obsolete.add(name)

    # Bookkeeping paths live on the destination filesystem.
    manifest_rel = manifest.relative_to(root).as_posix()
    owners_rel = (manifest_dir / OWNERS_FILE).relative_to(root).as_posix()
    bookkeeping_rel = manifest_dir.relative_to(root).as_posix()
    for n in new:
        if n == manifest_rel or n == owners_rel or n == bookkeeping_rel or n.startswith(bookkeeping_rel + '/'):
            raise ValueError(f'{owner_id}: payload overlaps staging bookkeeping: {n}')

    # Update in-memory owners index for atomic commit.
    for leg_id in retired_legacy:
        for entry in index['owners'].pop(leg_id, ()):
            owners = path_owners.get(entry)
            if owners and leg_id in owners:
                owners.remove(leg_id)
                if not owners:
                    path_owners.pop(entry, None)
        index['meta'].pop(leg_id, None)

    for entry in old - new:
        owners = path_owners.get(entry)
        if owners and owner_id in owners:
            owners.remove(owner_id)
            if not owners:
                path_owners.pop(entry, None)

    if args.source:
        index['owners'][owner_id] = sorted(new)
        index['meta'][owner_id] = {
            'package': args.legacy_package or owner_id,
            'base': args.legacy_base or owner_id,
        }
        for entry in new:
            owners = path_owners.setdefault(entry, [])
            if owner_id not in owners:
                owners.append(owner_id)
                owners.sort()
        (work / 'manifest').write_text(''.join('./' + n + '\n' for n in sorted(new)))
    else:
        index['owners'].pop(owner_id, None)
        index['meta'].pop(owner_id, None)

    (work / 'owners.json').write_text(json.dumps(index, sort_keys=True) + '\n')

    create_dirs = []
    for name in sorted(dirs):
        path = root / name
        if not os.path.lexists(path):
            create_dirs.append(name)
        elif path.is_symlink() or not path.is_dir():
            raise ValueError(f'{path} is not a directory')

    remove_dirs = []
    remove_files = []
    for name in sorted(removable_obsolete, key=lambda n: (-n.count('/'), n)):
        path = root / name
        if not os.path.lexists(path):
            continue
        if path.is_dir() and not path.is_symlink():
            remove_dirs.append(name)
        else:
            remove_files.append(name)

    operations = []
    seen_ops = set()
    for name in create_dirs + sorted(files_to_write) + remove_files + remove_dirs + [manifest_rel, owners_rel]:
        if name in seen_ops:
            continue
        seen_ops.add(name)
        path = root / name
        if not path.parent.resolve().is_relative_to(root):
            raise ValueError(f'staging path escapes {root}: {name}')
        if not os.path.lexists(path):
            kind = 'absent'
        elif not path.is_symlink() and path.is_dir():
            if name in files_to_write:
                raise ValueError(f'cannot replace staging directory with file: {path}')
            kind = 'dir'
        else:
            kind = 'file'
            backup = work / 'backup' / name
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.link(path, backup, follow_symlinks=False)
        operations.append((name, kind))

    (work / 'journal').write_text(json.dumps(operations))
    pending.symlink_to(work.name)
    try:
        for name in create_dirs:
            path = root / name
            path.mkdir(parents=True, exist_ok=True)
            path.chmod(stat.S_IMODE((incoming / name).stat().st_mode))
        for name in sorted(files_to_write):
            target_path = root / name
            target_path.parent.mkdir(parents=True, exist_ok=True)
            os.replace(incoming / name, target_path)
        for name in remove_files:
            (root / name).unlink(missing_ok=True)
        for name in remove_dirs:
            try:
                (root / name).rmdir()
            except OSError as error:
                if error.errno not in (errno.ENOTEMPTY, errno.ENOENT):
                    raise
        if args.source:
            os.replace(work / 'manifest', manifest)
        else:
            manifest.unlink(missing_ok=True)
        os.replace(work / 'owners.json', manifest_dir / OWNERS_FILE)
        pending.unlink()
    except BaseException:
        rollback(root, pending)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--lock', type=Path, required=True)
    parser.add_argument('--source', type=Path)
    parser.add_argument('--owner', help='Stable owner key (defaults to manifest stem)')
    parser.add_argument('--legacy-package', help='Current ABI-suffixed package name')
    parser.add_argument('--legacy-base', help='Base binary package name for ABI-change migration')
    args = parser.parse_args()
    args.root = args.root.resolve()
    args.manifest = args.manifest.absolute()
    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.lock.parent.mkdir(parents=True, exist_ok=True)

    work = Path(tempfile.mkdtemp(dir=args.manifest.parent, prefix='.stage-'))
    try:
        files, dirs = set(), set()
        if args.source:
            incoming = work / 'incoming'
            incoming.mkdir()
            subprocess.run(
                ['cp', '-pPR', '--reflink=auto', str(args.source) + '/.', str(incoming)],
                check=True,
            )
            files, dirs = contents(incoming)
        with args.lock.open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            commit(args, work, files, dirs)
    finally:
        pending = args.manifest.parent / PENDING_LINK
        if not pending.is_symlink() or pending.resolve(strict=False) != work:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        sys.exit(f'stage-package.py: {exc}')
