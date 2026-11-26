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
try:
    import sqlite3
except ModuleNotFoundError:
    sqlite3 = None
import stat
import subprocess
import sys
import tempfile


def _find_host_python3():
    topdir = Path(__file__).resolve().parents[1]
    for candidate in (topdir / 'staging_dir/host/bin/python3', Path('/usr/bin/python3')):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            try:
                if Path(sys.executable).resolve() != candidate.resolve():
                    return str(candidate)
            except OSError:
                return str(candidate)
    return None


def _require_sqlite3_or_reexec():
    if sqlite3 is not None:
        return
    if not os.environ.get('_STAGE_PACKAGE_REEXEC'):
        host_py = _find_host_python3()
        if host_py:
            env = {**os.environ, '_STAGE_PACKAGE_REEXEC': '1'}
            os.execve(host_py, [host_py, str(Path(__file__).resolve()), *sys.argv[1:]], env)
    raise RuntimeError('stage-package.py requires a Python 3 interpreter with sqlite3 support')


OWNERS_SCHEMA = 1
OWNERS_FILE = '.owners.json'
OWNERS_DB = '.owners.db'
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


def _open_db(db_path):
    conn = sqlite3.connect(str(db_path))
    conn.execute('PRAGMA synchronous = NORMAL')
    conn.execute('PRAGMA temp_store = MEMORY')
    return conn


def _init_db_schema(conn):
    conn.executescript(
        'CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);'
        'CREATE TABLE IF NOT EXISTS owner_meta (owner_id TEXT PRIMARY KEY, data TEXT NOT NULL);'
        'CREATE TABLE IF NOT EXISTS ownership ('
        '  path TEXT NOT NULL,'
        '  owner_id TEXT NOT NULL,'
        '  PRIMARY KEY (path, owner_id)'
        ') WITHOUT ROWID;'
        'CREATE INDEX IF NOT EXISTS idx_ownership_owner ON ownership(owner_id, path);'
    )


def _apply_db_undo(root, db_undo):
    if not db_undo:
        return
    db_path = root / db_undo['db']
    if not db_path.is_file():
        return
    if sqlite3 is None:
        host_py = _find_host_python3()
        if not host_py:
            raise RuntimeError('stage-package.py recovery requires a Python 3 interpreter with sqlite3 support')
        subprocess.run(
            [host_py, str(Path(__file__).resolve()), '--apply-db-undo', str(root)],
            input=json.dumps(db_undo), text=True, check=True,
        )
        return
    conn = _open_db(db_path)
    try:
        with conn:
            affected = set(db_undo.get('delete_owners', ())) | set(db_undo.get('restore_owners', ())) | set(db_undo.get('restore_meta', ()))
            for owner_id in sorted(affected):
                conn.execute('DELETE FROM ownership WHERE owner_id = ?', (owner_id,))
                conn.execute('DELETE FROM owner_meta WHERE owner_id = ?', (owner_id,))
            rows = [
                (path, owner_id)
                for owner_id, paths in db_undo.get('restore_owners', {}).items()
                for path in paths
            ]
            if rows:
                conn.executemany('INSERT OR IGNORE INTO ownership (path, owner_id) VALUES (?, ?)', rows)
            for owner_id, meta_json in db_undo.get('restore_meta', {}).items():
                if meta_json is not None:
                    conn.execute(
                        'INSERT OR REPLACE INTO owner_meta (owner_id, data) VALUES (?, ?)',
                        (owner_id, meta_json),
                    )
    finally:
        conn.close()


def rollback(root, pending):
    """Idempotently roll back an interrupted staging transaction (filesystem + ownership DB)."""
    if not pending.is_symlink():
        return
    work = pending.resolve(strict=False)
    journal_path = work / 'journal'
    if not work.is_dir() or not journal_path.is_file():
        pending.unlink(missing_ok=True)
        return
    raw = json.loads(journal_path.read_text())
    if isinstance(raw, list):
        operations, db_undo = raw, None
    else:
        operations, db_undo = raw.get('fs', []), raw.get('db_undo')
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
    _apply_db_undo(root, db_undo)
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


def open_or_migrate_owners_db(root, manifest_dir, legacy_elf_dir=None):
    db_path = manifest_dir / OWNERS_DB
    if db_path.is_file():
        try:
            conn = _open_db(db_path)
            row = conn.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
            if row and row[0] == str(OWNERS_SCHEMA):
                return conn
            conn.close()
        except sqlite3.Error:
            pass

    json_path = manifest_dir / OWNERS_FILE
    data = None
    if json_path.is_file():
        try:
            loaded = json.loads(json_path.read_text())
            if isinstance(loaded, dict) and loaded.get('schema') == OWNERS_SCHEMA:
                loaded.setdefault('owners', {})
                loaded.setdefault('meta', {})
                data = loaded
        except (OSError, ValueError):
            pass
    if data is None:
        data = build_initial_owners_index(root, manifest_dir, legacy_elf_dir)

    tmp_db = manifest_dir / f'{OWNERS_DB}.{os.getpid()}.tmp'
    tmp_db.unlink(missing_ok=True)
    conn = _open_db(tmp_db)
    try:
        with conn:
            _init_db_schema(conn)
            conn.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('schema', ?)", (str(OWNERS_SCHEMA),))
            meta_rows = [(oid, json.dumps(meta, sort_keys=True)) for oid, meta in data.get('meta', {}).items()]
            if meta_rows:
                conn.executemany('INSERT OR REPLACE INTO owner_meta (owner_id, data) VALUES (?, ?)', meta_rows)
            own_rows = [
                (entry, oid)
                for oid, entries in data.get('owners', {}).items()
                for entry in entries
            ]
            if own_rows:
                conn.executemany('INSERT OR IGNORE INTO ownership (path, owner_id) VALUES (?, ?)', own_rows)
        conn.close()
        os.replace(tmp_db, db_path)
        json_path.unlink(missing_ok=True)
    except BaseException:
        try:
            conn.close()
        except Exception:
            pass
        tmp_db.unlink(missing_ok=True)
        raise
    return _open_db(db_path)


def query_path_owners(conn, paths):
    result = {}
    path_list = sorted(paths)
    for i in range(0, len(path_list), 500):
        chunk = path_list[i:i + 500]
        placeholders = ','.join('?' * len(chunk))
        for path, owner in conn.execute(
            f'SELECT path, owner_id FROM ownership WHERE path IN ({placeholders})', chunk
        ):
            result.setdefault(path, []).append(owner)
    return result


def matching_legacy_owners(conn, owner_id, legacy_package=None, legacy_base=None):
    """Find legacy-elf:* entries belonging to this package (including prior ABI suffixes)."""
    matched = []
    for existing_owner, meta_json in conn.execute(
        "SELECT owner_id, data FROM owner_meta WHERE owner_id LIKE 'legacy-elf:%'"
    ):
        try:
            meta = json.loads(meta_json)
        except ValueError:
            meta = {}
        pkg = meta.get('legacy_package', existing_owner.removeprefix('legacy-elf:'))
        if legacy_package and pkg == legacy_package:
            matched.append(existing_owner)
        elif legacy_base and abi_base_matches(pkg, legacy_base):
            # Do not steal a record whose exact package name already has its own active manifest.
            if pkg != legacy_base and pkg != owner_id:
                has_active = conn.execute(
                    'SELECT 1 FROM ownership WHERE owner_id = ? LIMIT 1', (pkg,)
                ).fetchone()
                if has_active:
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
    conn = open_or_migrate_owners_db(root, manifest_dir, legacy_elf_dir)
    try:
        owner_id = args.owner or manifest.stem

        # Collect previous entries owned by this owner_id AND any matching legacy ELF records
        # (e.g. old ABI suffix example6.elf.json when upgrading to example7 or removing suffix).
        prev_owner_paths = [
            row[0] for row in conn.execute('SELECT path FROM ownership WHERE owner_id = ? ORDER BY path', (owner_id,))
        ]
        prev_owner_meta_row = conn.execute('SELECT data FROM owner_meta WHERE owner_id = ?', (owner_id,)).fetchone()
        prev_owner_meta = prev_owner_meta_row[0] if prev_owner_meta_row else None

        old = set(prev_owner_paths)
        if not old and manifest.is_file():
            old.update(read_list(manifest))

        retired_legacy = matching_legacy_owners(
            conn, owner_id, legacy_package=args.legacy_package, legacy_base=args.legacy_base
        )
        restore_owners = {owner_id: prev_owner_paths}
        restore_meta = {owner_id: prev_owner_meta}
        for leg_id in retired_legacy:
            leg_paths = [
                row[0] for row in conn.execute('SELECT path FROM ownership WHERE owner_id = ? ORDER BY path', (leg_id,))
            ]
            leg_meta_row = conn.execute('SELECT data FROM owner_meta WHERE owner_id = ?', (leg_id,)).fetchone()
            restore_owners[leg_id] = leg_paths
            restore_meta[leg_id] = leg_meta_row[0] if leg_meta_row else None
            old.update(leg_paths)

        new = files | dirs
        obsolete = old - new
        incoming = work / 'incoming'

        # Exclude this owner and its retired legacy IDs when checking other owners.
        self_ids = {owner_id, *retired_legacy}
        path_owners = query_path_owners(conn, files | obsolete)

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
        owners_db_rel = (manifest_dir / OWNERS_DB).relative_to(root).as_posix()
        owners_json_rel = (manifest_dir / OWNERS_FILE).relative_to(root).as_posix()
        bookkeeping_rel = manifest_dir.relative_to(root).as_posix()
        for n in new:
            if (n in (manifest_rel, owners_db_rel, owners_json_rel, bookkeeping_rel)
                    or n.startswith(bookkeeping_rel + '/')):
                raise ValueError(f'{owner_id}: payload overlaps staging bookkeeping: {n}')

        if args.source:
            (work / 'manifest').write_text(''.join('./' + n + '\n' for n in sorted(new)))

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
        for name in create_dirs + sorted(files_to_write) + remove_files + remove_dirs + [manifest_rel]:
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

        db_undo = {
            'db': owners_db_rel,
            'delete_owners': [owner_id],
            'restore_owners': restore_owners,
            'restore_meta': restore_meta,
        }
        (work / 'journal').write_text(json.dumps({'fs': operations, 'db_undo': db_undo}))
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

            with conn:
                for leg_id in retired_legacy:
                    conn.execute('DELETE FROM ownership WHERE owner_id = ?', (leg_id,))
                    conn.execute('DELETE FROM owner_meta WHERE owner_id = ?', (leg_id,))
                if args.source:
                    removed_self = old - new
                    if removed_self:
                        rem_list = sorted(removed_self)
                        for i in range(0, len(rem_list), 500):
                            chunk = rem_list[i:i + 500]
                            placeholders = ','.join('?' * len(chunk))
                            conn.execute(
                                f'DELETE FROM ownership WHERE owner_id = ? AND path IN ({placeholders})',
                                [owner_id, *chunk],
                            )
                    added_self = new - set(prev_owner_paths)
                    if added_self:
                        conn.executemany(
                            'INSERT OR IGNORE INTO ownership (path, owner_id) VALUES (?, ?)',
                            [(entry, owner_id) for entry in sorted(added_self)],
                        )
                    meta_json = json.dumps({
                        'package': args.legacy_package or owner_id,
                        'base': args.legacy_base or owner_id,
                    }, sort_keys=True)
                    conn.execute(
                        'INSERT OR REPLACE INTO owner_meta (owner_id, data) VALUES (?, ?)',
                        (owner_id, meta_json),
                    )
                else:
                    conn.execute('DELETE FROM ownership WHERE owner_id = ?', (owner_id,))
                    conn.execute('DELETE FROM owner_meta WHERE owner_id = ?', (owner_id,))
            pending.unlink()
        except BaseException:
            conn.close()
            rollback(root, pending)
            raise
    finally:
        try:
            conn.close()
        except Exception:
            pass


def main():
    _require_sqlite3_or_reexec()
    if len(sys.argv) == 3 and sys.argv[1] == '--apply-db-undo':
        _apply_db_undo(Path(sys.argv[2]).resolve(), json.loads(sys.stdin.read()))
        return
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
