#!/usr/bin/env python3
"""Derive APK shared-library contracts from ELF payloads without executing them."""
import argparse
import json
import mmap
import os
from pathlib import Path
import posixpath
import re
import struct

SCHEMA = 1
PUBLIC = ('/usr/lib', '/usr/lib64')
POLICY_FILE = Path(__file__).resolve().parents[1] / 'configs/elf-abi-policy.json'
POLICY = json.loads(POLICY_FILE.read_text()) if POLICY_FILE.exists() else {'loader_paths': {}}
REBUILDS_FILE = Path(__file__).resolve().parents[1] / 'configs/apk-elf-rebuilds.mk'


def migration_releases():
    """Explicit, exact-version ledger; never loosen arbitrary world pins."""
    result = {}
    for line in REBUILDS_FILE.read_text().splitlines():
        if not line.startswith('ELF_DEP_'):
            continue
        key, value = line.removeprefix('ELF_DEP_').split(':=', 1)
        name, after = value.split('=', 1)
        if not key.startswith(name + '_'):
            raise ValueError('Invalid ELF metadata migration ledger entry: ' + line)
        result.setdefault(name, []).append({'before': key[len(name) + 1:], 'after': after})
    return result


def canonical(path):
    path = posixpath.normpath('/' + path.lstrip('/'))
    for old, new in (('/lib64', '/usr/lib'), ('/lib', '/usr/lib'),
                     ('/bin', '/usr/bin'), ('/sbin', '/usr/sbin')):
        if path == old or path.startswith(old + '/'):
            return new + path[len(old):]
    return path


def elf(path):
    """Read program headers/dynamic strings, including stripped 32/64-bit ELF."""
    with Path(path).open('rb') as stream:
        header = stream.read(64)
        if header[:4] != b'\x7fELF':
            return None
        if len(header) < 52 or header[4] not in (1, 2) or header[5] not in (1, 2):
            raise ValueError(f'{path}: invalid ELF header')
        endian = '<' if header[5] == 1 else '>'
        wide = header[4] == 2
        kind, machine = struct.unpack_from(endian + 'HH', header, 16)
        if kind not in (2, 3):
            return None
        phoff = struct.unpack_from(endian + ('Q' if wide else 'I'), header, 32 if wide else 28)[0]
        phsize, count = struct.unpack_from(endian + 'HH', header, 54 if wide else 42)
        if not count:
            return None
        expected = 56 if wide else 32
        if phsize != expected or count == 65535:
            raise ValueError(f'{path}: unsupported ELF program headers')
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            def unpack(fmt, offset):
                size = struct.calcsize(endian + fmt)
                if offset < 0 or offset + size > len(data):
                    raise ValueError(f'{path}: truncated ELF')
                return struct.unpack_from(endian + fmt, data, offset)

            loads, dynamic, interp = [], None, None
            for i in range(count):
                values = unpack('IIQQQQQQ' if wide else 'IIIIIIII', phoff + i * phsize)
                typ = values[0]
                offset, address, size = (values[2], values[3], values[5]) if wide else (values[1], values[2], values[4])
                if offset + size > len(data):
                    raise ValueError(f'{path}: truncated ELF segment')
                if typ == 1:
                    loads.append((address, offset, size))
                elif typ == 2:
                    dynamic = (offset, size)
                elif typ == 3:
                    interp = data[offset:offset + size].rstrip(b'\0').decode()
            if dynamic is None:
                return None
            tags = {}
            step = 16 if wide else 8
            for offset in range(dynamic[0], sum(dynamic), step):
                tag, value = unpack('qQ' if wide else 'iI', offset)
                if tag == 0:
                    break
                tags.setdefault(tag, []).append(value)
            strings = tags.get(5, [None])[0]
            length = tags.get(10, [0])[0]
            base = next((off + strings - addr for addr, off, size in loads
                         if strings is not None and addr <= strings < addr + size), None)
            if base is None or not length or base + length > len(data):
                raise ValueError(f'{path}: invalid ELF string table')

            def string(index):
                if not 0 <= index < length:
                    raise ValueError(f'{path}: invalid ELF string offset')
                end = data.find(b'\0', base + index, base + length)
                if end < 0:
                    raise ValueError(f'{path}: unterminated ELF string')
                return data[base + index:end].decode()

            return {'needed': sorted({string(i) for i in tags.get(1, [])}),
                    'soname': string(tags[14][0]) if 14 in tags else None,
                    'rpath': string(tags[15][0]) if 15 in tags else None,
                    'runpath': string(tags[29][0]) if 29 in tags else None,
                    'interpreter': interp, 'class': header[4], 'machine': machine}


def inspect(root):
    root = Path(root)
    files, links = {}, {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs[:] + names:
            path = Path(directory) / name
            relative = '/' + path.relative_to(root).as_posix()
            if path.is_symlink():
                links[canonical(relative)] = canonical(posixpath.join(posixpath.dirname(relative), os.readlink(path)))
                if name in dirs:
                    dirs.remove(name)
            elif name in names and path.is_file():
                item = elf(path)
                if item:
                    files[canonical(relative)] = item
    return {'schema': SCHEMA, 'files': files, 'links': links}


def resolve(path, files, links):
    path = canonical(path)
    seen = set()
    while path not in seen:
        seen.add(path)
        if path in files:
            return path
        components = path.split('/')
        for i in range(len(components), 1, -1):
            prefix = '/'.join(components[:i])
            if prefix in links and links[prefix] != prefix:
                path = canonical(posixpath.join(links[prefix], *components[i:]))
                break
        else:
            return None
    raise ValueError(f'ELF ABI: symlink loop at {path}')


def search_paths(path, item, inherited=()):
    paths = []
    runpath = item.get('runpath')
    for entry in (runpath if runpath is not None else item.get('rpath') or '').split(':'):
        if not entry:
            continue
        entry = entry.replace('${ORIGIN}', posixpath.dirname(path)).replace('$ORIGIN', posixpath.dirname(path))
        if '$' in entry or not entry.startswith('/'):
            # Never use cwd-dependent or unresolved loader paths as ABI proof.
            # Defaults must still resolve every dependency (some upstream
            # binaries contain a harmless literal "$" RUNPATH).
            continue
        paths.append(canonical(entry))
    return list(dict.fromkeys(paths + (list(inherited) if runpath is None else []) + list(PUBLIC)))


class Context(dict):
    """Index selected payloads once, including inherited DT_RPATH search paths."""
    def __init__(self, records):
        super().__init__(records)
        self.files, self.links, self.owners, self.inherited = {}, {}, {}, {}
        for package, record in records.items():
            owner = record.get('package', package)
            self.files.update(record['files'])
            self.links.update(record['links'])
            if not package.startswith('@'):
                self.owners.update({p: (owner, record.get('version')) for p in record['files']})
                for path in record['files']:
                    self.inherited[path] = set(POLICY['loader_paths'].get(owner, []))
        # DT_RPATH is inherited by descendants; DT_RUNPATH is direct-only.
        changed = True
        while changed:
            changed = False
            for path, item in self.files.items():
                inherited = self.inherited.setdefault(path, set())
                propagated = set(search_paths(path, item, inherited)) - set(PUBLIC)
                if item.get('runpath') is not None:
                    propagated = inherited
                if not propagated:
                    continue
                for needed in item['needed']:
                    targets = [needed] if '/' in needed else [posixpath.join(p, needed) for p in search_paths(path, item, inherited)]
                    child = next((r for p in targets if (r := resolve(p, self.files, self.links))), None)
                    if child:
                        before = self.inherited.setdefault(child, set())
                        if propagated - before:
                            before.update(propagated)
                            changed = True


def public_provides(inventory):
    result = set()
    for path, item in inventory['files'].items():
        if posixpath.dirname(path) not in PUBLIC:
            continue
        soname = item['soname'] or posixpath.basename(path)
        if '.so' not in soname or '/' in soname:
            continue
        target = resolve(posixpath.join(posixpath.dirname(path), soname),
                         inventory['files'], inventory['links'])
        if target == path:
            result.add('so:' + soname + '=0')
    return sorted(result)


def contracts(inventory, name, context=None):
    """Private libraries satisfy only objects whose real search path reaches them."""
    files = dict(inventory['files'])
    links = dict(inventory['links'])
    owners = {}
    inherited = {p: set(POLICY['loader_paths'].get(name, [])) for p in files}
    if context:
        index = context if isinstance(context, Context) else Context({**context, name: inventory})
        files = {**index.files, **files}
        links = {**index.links, **links}
        owners = index.owners
        inherited = index.inherited
    else:
        inherited = Context({name: inventory}).inherited
    dependencies = set()
    for path, item in inventory['files'].items():
        for needed in item['needed'] + ([item['interpreter']] if item['interpreter'] else []):
            if '/' in needed and not needed.startswith('/'):
                raise ValueError(f'{name}: {path}: relative ELF dependency cannot be verified: {needed}')
            candidates = [needed] if '/' in needed else [posixpath.join(p, needed) for p in search_paths(path, item, inherited.get(path, ()))]
            target = next((resolved for p in candidates if (resolved := resolve(p, files, links))), None)
            if target and (files[target]['class'], files[target]['machine']) != (item['class'], item['machine']):
                raise ValueError(f'{name}: {path} -> {needed}: ELF architecture mismatch')
            if target in inventory['files']:
                continue
            if target and posixpath.dirname(target) not in PUBLIC:
                package, version = owners.get(target, (None, None))
                if not package or not version:
                    raise ValueError(f'{name}: {path} -> {needed}: private library has no versioned package owner')
                dependencies.add(f'{package}={version}')
            else:
                soname = posixpath.basename(needed)
                if not re.fullmatch(r'[A-Za-z0-9_.+\-]+', soname):
                    raise ValueError(f'{name}: {path}: invalid needed library {needed!r}')
                if context is not None and target is None:
                    raise ValueError(f'{name}: {path} -> {needed}: missing library; rebuild the consumer/provider')
                dependencies.add('so:' + soname)
    return sorted(dependencies), public_provides(inventory)


def validate_record(name, record, context, capabilities, require_metadata=True):
    dependencies, provides = contracts(record['elf'], name, context)
    if require_metadata:
        missing = set(dependencies) - set(record.get('depends', []))
        absent = set(provides) - set(record.get('provides', []))
        if missing or absent:
            raise ValueError(f'{name}: missing ELF metadata depends={sorted(missing)} provides={sorted(absent)}; bump release and rebuild')
        for dependency in dependencies:
            if dependency.startswith('so:') and dependency not in capabilities:
                raise ValueError(f'{name}: no provider for {dependency}')


def validate(records, require_metadata=True):
    """Validate a complete, selected package set, never historical fallback APKs."""
    errors = []
    capabilities = {value.split('=', 1)[0] for r in records.values()
                    for value in r.get('provides', [])}
    context = Context({n: r['elf'] for n, r in records.items()})
    for name, record in sorted(records.items()):
        try:
            validate_record(name, record, context, capabilities, require_metadata)
        except ValueError as error:
            errors.append(str(error))
    if errors:
        raise ValueError('ELF ABI preflight:\n' + '\n'.join(errors))
    return {'schema': SCHEMA, 'packages': len(records),
            'elf_files': sum(len(r['elf']['files']) for r in records.values())}


def write_changed(path, content, mode=None):
    path = Path(path)
    if path.exists() and path.read_text() == content:
        if mode is not None:
            path.chmod(mode)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + f'.{os.getpid()}.tmp')
    temporary.write_text(content)
    if mode is not None:
        temporary.chmod(mode)
    os.replace(temporary, path)


def staged_inventory(root, inventory, merged_usr=True):
    """Read only referenced staged paths, never follow absolute links on the host."""
    result = {'files': {}, 'links': {}, 'schema': SCHEMA}

    def local_path(path):
        # The toolchain sysroot stores runtime libraries in /lib; package
        # inventories use the target's canonical /usr/lib namespace.
        if not merged_usr and (path == '/usr/lib' or path.startswith('/usr/lib/')):
            path = path.removeprefix('/usr')
        return root / path.lstrip('/')

    requested = set()
    for path, item in inventory['files'].items():
        for needed in item['needed']:
            requested.update([needed] if '/' in needed else
                             [posixpath.join(p, needed) for p in search_paths(path, item)])
        if item['interpreter']:
            requested.add(item['interpreter'])
    for path in sorted(requested):
        path = canonical(path)
        seen = set()
        while path not in seen:
            seen.add(path)
            parts = path.strip('/').split('/')
            changed = False
            for i in range(1, len(parts) + 1):
                relative = '/' + '/'.join(parts[:i])
                local = local_path(relative)
                if local.is_symlink():
                    target = canonical(posixpath.join(posixpath.dirname(relative), os.readlink(local)))
                    if target == relative:
                        continue
                    result['links'][relative] = target
                    path = canonical(posixpath.join(target, *parts[i:]))
                    changed = True
                    break
            if changed:
                continue
            local = local_path(path)
            if local.is_file() and (item := elf(local)):
                result['files'][path] = item
            break
        else:
            raise ValueError(f'ELF ABI: staged symlink loop at {path}')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--package', required=True)
    parser.add_argument('--version', required=True)
    parser.add_argument('--staging-root', type=Path)
    parser.add_argument('--bootstrap-root', type=Path,
                        help='Current toolchain sysroot, only for toolchain runtime packages')
    parser.add_argument('--depends-output', type=Path, required=True)
    parser.add_argument('--provides-output', type=Path, required=True)
    parser.add_argument('--stamp', type=Path)
    args = parser.parse_args()
    try:
        inventory = inspect(args.root)
        inventory.update(package=args.package, version=args.version)
        context = None
        if args.staging_root:
            context = {}
            for path in (args.staging_root / 'usr/lib/apk/packages').glob('*.elf.json'):
                record = json.loads(path.read_text())
                context[record['package']] = record
            # Bootstrap the metadata migration from the actual staged payload.
            staged = staged_inventory(args.staging_root, inventory)
            context['@staged'] = staged
        if args.bootstrap_root:
            if context is None:
                context = {}
            # Keep the check strict: only actual, architecture-matched runtime
            # files from this toolchain can satisfy the bootstrap dependencies.
            bootstrap = staged_inventory(args.bootstrap_root, inventory, merged_usr=False)
            context = {'@bootstrap': bootstrap, **context}
        depends, provides = contracts(inventory, args.package, context)
        write_changed(args.depends_output, ' '.join(depends) + '\n')
        write_changed(args.provides_output, ' '.join(provides) + '\n')
        if inventory['files']:
            output = args.root / 'usr/lib/apk/packages' / (args.package + '.elf.json')
            write_changed(output, json.dumps(inventory, sort_keys=True, separators=(',', ':')) + '\n', mode=0o644)
            filelist = output.with_name(args.package + '.list')
            if filelist.exists():
                write_changed(filelist, '\n'.join(sorted(set(filelist.read_text().splitlines() +
                    ['/usr/lib/apk/packages/' + args.package + '.elf.json']))) + '\n')
        if args.stamp:
            write_changed(args.stamp, '\n'.join(provides) + '\n')
    except (OSError, ValueError, struct.error) as error:
        parser.exit(1, str(error) + '\n')


if __name__ == '__main__':
    main()
