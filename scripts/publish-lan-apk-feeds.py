#!/usr/bin/env python3
"""Publish signed native-systemd/glibc APK feeds, optionally incrementally."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import datetime
import errno
import fcntl
import hashlib
import importlib.util
import json
import multiprocessing
import os
from pathlib import Path
import pickle
import re
import shutil
import subprocess
import tempfile

SCHEMA_VERSION = 4

_elf_spec = importlib.util.spec_from_file_location(
    'publish_elf_abi', Path(__file__).with_name('elf-abi.py'))
ELF = importlib.util.module_from_spec(_elf_spec)
_elf_spec.loader.exec_module(ELF)

_ucode_spec = importlib.util.spec_from_file_location(
    'publish_ucode_abi', Path(__file__).with_name('ucode-abi.py'))
UCODE = importlib.util.module_from_spec(_ucode_spec)
_ucode_spec.loader.exec_module(UCODE)
_guard_spec = importlib.util.spec_from_file_location(
    'lan_upgrade_preflight', Path(__file__).with_name('apk-upgrade-preflight.py'))
GUARD = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(GUARD)
_diagnose_spec = importlib.util.spec_from_file_location(
    'publish_diagnose_rebuild', Path(__file__).with_name('diagnose-apk-rebuild.py'))
DIAGNOSE = importlib.util.module_from_spec(_diagnose_spec)
_diagnose_spec.loader.exec_module(DIAGNOSE)
_allocate_spec = importlib.util.spec_from_file_location(
    'publish_allocate_rebuilds', Path(__file__).with_name('allocate-rebuild-releases.py'))
ALLOCATE = importlib.util.module_from_spec(_allocate_spec)
_allocate_spec.loader.exec_module(ALLOCATE)
DIAGNOSE_LIMIT = 8


class SameVersionRebuildError(ValueError):
    """Published identities whose rebuilt bytes changed; entries feed the allocator."""

    def __init__(self, message, entries):
        super().__init__(message)
        self.entries = entries


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def is_custom_origin(origin):
    return origin.startswith(('feeds/base/custom/', 'package/custom/', 'feeds/custom/'))


def dump_index(apk, index):
    result = json.loads(subprocess.check_output(
        [str(apk), 'adbdump', '--format', 'json', str(index)]))
    if 'info' not in result:
        result.setdefault('packages', [])
    return result


def dump_indexes(apk, paths):
    """Read metadata in bounded batches, preserving APK's input/output order."""
    paths = list(paths)

    def read(batch):
        output = subprocess.check_output(
            [str(apk), 'adbdump', '--format', 'json', *map(str, batch)], encoding='utf-8')
        decoder = json.JSONDecoder()
        offset = 0
        results = []
        for path in batch:
            while offset < len(output) and output[offset].isspace():
                offset += 1
            result, offset = decoder.raw_decode(output, offset)
            if 'info' not in result:
                result.setdefault('packages', [])
            results.append((path, result))
        if output[offset:].strip():
            raise ValueError('Unexpected extra APK metadata in adbdump output')
        return results

    with ThreadPoolExecutor(max_workers=4) as workers:
        # Limit both outstanding commands and buffered metadata. Consume results
        # in source order so duplicate selection and diagnostics stay stable.
        for start in range(0, len(paths), 128):
            batches = [paths[i:i + 32] for i in range(start, min(start + 128, len(paths)), 32)]
            for results in workers.map(read, batches):
                yield from results


def same_version_rebuild_error(apk, previous, payload, paths):
    """Name every same-version rebuild, classify it and explain the first few."""
    lines = ['Published APK changed without a new version; bump PKG_RELEASE: ' + ', '.join(paths)]
    entries = []
    for number, path in enumerate(paths):
        try:
            entry, report = ALLOCATE.classify(previous / path, payload / path, path, apk)
            if number < DIAGNOSE_LIMIT:
                lines.append(DIAGNOSE.format_report(report, label=path))
        except Exception as error:  # Diagnosis must never hide the publication error.
            entry = {'path': path, 'name': None, 'version': None, 'verdict': 'unknown',
                     'so_changed': False, 'so_removed': [], 'so_added': []}
            lines.append(f'{path}: diagnosis failed: {error}')
        entries.append(entry)
    if len(paths) > DIAGNOSE_LIMIT:
        lines.append(f'{len(paths) - DIAGNOSE_LIMIT} more not shown in detail; run '
                     'scripts/diagnose-apk-rebuild.py REPOSITORY/FILE.apk')
    lines.append('Allocate releases with scripts/allocate-rebuild-releases.py, or rerun '
                 'build-and-publish.py with --allocate-rebuilds')
    return SameVersionRebuildError('\n'.join(lines), entries)


def verify(apk, keys, files):
    if files:
        subprocess.run([str(apk), 'verify', '--keys-dir', str(keys), *map(str, files)],
                       check=True, capture_output=True)


def index_repository(apk, tree, keys, repo, changed=None, allow_empty=False):
    packages = sorted(repo.glob('*.apk'))
    if not packages and not allow_empty:
        raise ValueError(f'No APKs in {repo}')
    verify(apk, keys, packages if changed is None else changed)
    # Unlink an index reused from an older snapshot before mkndx writes it.
    index = repo / 'packages.adb'
    index.unlink(missing_ok=True)
    subprocess.run([str(apk), 'mkndx', '--keys-dir', str(keys),
                    '--sign-key', str(tree / 'private-key.pem'),
                    # apk 3 cannot read a completely empty ADB root object.
                    *(['--description', 'OpenWrt empty ABI userspace view'] if not packages else []),
                    '--output', str(index), *map(str, packages)],
                   check=True, capture_output=True)
    verify(apk, keys, [index])
    return dump_index(apk, index)


def package_filename(info):
    filename = f'{info["name"]}-{info["version"]}.apk'
    if Path(filename).name != filename:
        raise ValueError(f'Invalid package filename: {filename}')
    return filename


def ucode_related(info):
    return (info['name'] == 'ucode' or info['name'].startswith('ucode-mod-')
            or re.fullmatch(r'libucode[0-9]+', info['name']) is not None
            or any(re.match(r'^(?:libucode[0-9]*|ucode|ucode-abi)(?:[<>=~]|$)', dep)
                   for dep in info.get('depends', [])))


def validate_ucode_abi(apk, keys, payload, indexes, work):
    """Validate newest solver candidates, including retained incremental APKs."""
    selected = {}
    for repo, index in indexes.items():
        for info in index['packages']:
            if not ucode_related(info):
                continue
            previous = selected.get(info['name'])
            if previous:
                order = subprocess.check_output(
                    [str(apk), 'version', '--test', previous[1]['version'], info['version']],
                    text=True).strip()
                if order != '<':
                    continue
            selected[info['name']] = (repo, info)
    if not selected:
        return None
    interpreter = selected.get('ucode')
    if not interpreter:
        raise ValueError('ucode ABI preflight: missing interpreter provider')
    providers = [value.split('=', 1)[1] for value in interpreter[1].get('provides', [])
                 if re.fullmatch(r'ucode-abi=[0-9]+', value)]
    if len(providers) != 1:
        raise ValueError('ucode ABI preflight: rebuild ucode with its ucode-abi provider '
                         'and bump PKG_RELEASE')
    abi = providers[0]
    checked = []
    for name, (repo, info) in sorted(selected.items()):
        root = work / 'ucode-abi-check' / name
        root.mkdir(parents=True)
        package = payload / repo / package_filename(info)
        subprocess.run([str(apk), 'extract', '--keys-dir', str(keys), '--no-chown',
                        '--destination', str(root), str(package)],
                       check=True, capture_output=True)
        required = UCODE.requirements(root, name, abi)
        dependencies = info.get('depends', [])
        locks = [dep for dep in dependencies if dep.startswith('ucode-abi=')]
        if locks and locks != [f'ucode-abi={abi}']:
            raise ValueError(f'ucode ABI preflight: {name} has incompatible lock {locks}; '
                             'rebuild and bump PKG_RELEASE')
        if any(dep not in dependencies for dep in required):
            raise ValueError(f'ucode ABI preflight: {name} lacks {required}; '
                             'rebuild and bump PKG_RELEASE')
        if required or name == 'ucode':
            checked.append(name)
    return {'abi': abi, 'packages': checked}


def kernel_channel_package(info):
    """Packages that belong to the kernel channel rather than userspace feeds.

    Kernel images, headers and their metapackages are installed side by side
    from the kernel channel. Since kernel packages carry their own modules,
    kmod-* are kernel-independent configuration packages and stay in the
    userspace feeds; only legacy per-generation payloads and the trackers that
    pinned them (to a payload or an exact kernel ABI) are excluded.
    """
    name = info['name']
    if name in ('kernel', 'kernel-dev-headers') or name.startswith(
            ('linux-image-', 'linux-headers-', 'kernel-dev-headers-')):
        return True
    return name.startswith('kmod-') and ('-owrt-' in name or any(
        '-owrt-' in dep or re.match(r'^kernel(?:[<>=~]|$)', dep) for dep in info.get('depends', [])))


WORKERS = min(8, os.cpu_count() or 1)


def forked_map(function, items, workers=WORKERS):
    """Ordered map over forked worker processes for CPU-bound Python checks.

    Children inherit ``function`` and ``items`` through fork, so neither is
    pickled (this importlib-loaded module cannot be pickled by reference);
    only results and exceptions travel back. Results keep input order and the
    first failure in input order is raised, exactly as a serial loop would.
    """
    items = list(items)
    count = min(workers, len(items))
    if count < 2:
        return [function(item) for item in items]
    context = multiprocessing.get_context('fork')

    def worker(indices, connection):
        outcomes = []
        for index in indices:
            try:
                outcomes.append((index, True, function(items[index])))
            except BaseException as error:
                try:
                    pickle.dumps(error)
                except Exception:
                    error = RuntimeError(f'{type(error).__name__}: {error}')
                outcomes.append((index, False, error))
                break
        connection.send(outcomes)
        connection.close()

    processes = []
    try:
        for offset in range(count):
            receiver, sender = context.Pipe(duplex=False)
            process = context.Process(target=worker, args=(range(offset, len(items), count), sender))
            process.start()
            sender.close()
            processes.append((process, receiver))
        results = [None] * len(items)
        failures = []
        for process, receiver in processes:
            try:
                outcomes = receiver.recv()
            except EOFError:
                outcomes = []
                failures.append((-1, RuntimeError('Parallel check worker exited unexpectedly')))
            process.join()
            if process.exitcode:
                failures.append((-1, RuntimeError(f'Parallel check worker failed: {process.exitcode}')))
            for index, success, value in outcomes:
                if success:
                    results[index] = value
                else:
                    failures.append((index, value))
        if failures:
            raise min(failures, key=lambda failure: failure[0])[1]
        return results
    finally:
        for process, receiver in processes:
            receiver.close()
            if process.is_alive():
                process.terminate()
            process.join()


def validate_alternatives(pool, alternatives, capabilities):
    """Each migration alternative rebuilds a full ELF context; check in parallel."""
    def check(key):
        name, version = key
        record = alternatives[name][version]
        inventories = {key: item['elf'] for key, item in pool.items()}
        for dependency in record.get('depends', []):
            match = re.fullmatch(r'([^=<>~]+)=(.+)', dependency)
            if match:
                provider = alternatives.get(match[1], {}).get(match[2])
                if provider:
                    inventories['selected#' + match[1]] = provider['elf']
        inventories['selected#' + name] = record['elf']
        ELF.validate_record(name, record, ELF.Context(inventories), capabilities)

    forked_map(check, [(name, version) for name, versions in alternatives.items()
                       for version in versions])


def validate_elf_abi(apk, keys, payload, indexes, work):
    """Inspect actual newest payloads, including retained legacy consumers."""
    selected = {}
    for repo, index in indexes.items():
        for info in index['packages']:
            name = info['name']
            if name in ('kernel', 'kernel-dev-headers') or name.startswith(
                    ('kmod-', 'linux-image-', 'linux-headers-', 'kernel-dev-headers-')):
                continue
            previous = selected.get(name)
            if previous:
                order = subprocess.check_output([str(apk), 'version', '--test',
                    previous[1]['version'], info['version']], text=True).strip()
                if order != '<':
                    continue
            selected[name] = (repo, info)
    records = {}
    inventory_errors = []
    ledger = ELF.migration_releases()

    def check_inventory(root, inventory, name, version):
        if not inventory['files']:
            return
        stamp = root / 'usr/lib/apk/packages' / (name + '.elf.json')
        try:
            valid = stamp.exists() and json.loads(stamp.read_text()) == inventory
        except (ValueError, UnicodeError):
            valid = False
        if not valid:
            migration = next((e['after'] for e in ledger.get(name, []) if e['before'] == version), None)
            action = ('rebuild using allocated migration release ' + migration if migration else
                      'bump release and rebuild')
            inventory_errors.append(f'{name}-{version}: missing/stale ELF inventory; {action}')

    def extract(job):
        root, package = job
        root.mkdir(parents=True)
        subprocess.run([str(apk), 'extract', '--keys-dir', str(keys), '--no-chown',
                        '--destination', str(root), str(package)], check=True, capture_output=True)
        return ELF.inspect(root)

    def inspect_all(jobs):
        # Independent apk extractions plus pure-Python ELF parsing (GIL-bound
        # in threads). Results and the first raised error keep serial order.
        return forked_map(extract, jobs)

    newest = sorted(selected.items())
    inventories = inspect_all([(work / 'elf-abi-check' / name, payload / repo / package_filename(info))
                               for name, (repo, info) in newest])
    for (name, (repo, info)), inventory in zip(newest, inventories):
        inventory.update(package=name, version=info['version'])
        check_inventory(work / 'elf-abi-check' / name, inventory, name, info['version'])
        records[name] = {**info, 'elf': inventory}
    alternatives = {}
    wanted = {}
    for repo, index in indexes.items():
        for info in index['packages']:
            name, version = info['name'], info['version']
            if name not in records or version == records[name]['version']:
                continue
            if not any(e['after'] == version for e in ledger.get(name, [])):
                continue
            wanted.setdefault((name, version), (repo, info))
    inventories = inspect_all([(work / 'elf-alternative-check' / name / version,
                                payload / repo / package_filename(info))
                               for (name, version), (repo, info) in wanted.items()])
    for ((name, version), (repo, info)), inventory in zip(wanted.items(), inventories):
        inventory.update(package=name, version=version)
        check_inventory(work / 'elf-alternative-check' / name / version, inventory, name, version)
        alternative = {**info, 'elf': inventory}
        alternatives.setdefault(name, {})[version] = alternative
    if inventory_errors:
        raise ValueError('ELF ABI preflight: ' + str(len(inventory_errors)) +
                         ' packages need rebuilding:\n  ' + '\n  '.join(inventory_errors) +
                         '\nIncremental feeds retain packages even when excluded from .config. '
                         'Rebuild them with CONFIG_PACKAGE_<name>=m; do not reuse a published identity.')
    report = ELF.validate(records)
    report['package_info'] = {name: {k: record.get(k, [] if k in ('depends', 'provides') else '')
                                    for k in ('name', 'version', 'hashes', 'depends', 'provides')}
                              for name, record in records.items()}
    report['alternatives'] = alternatives
    # Historical migration pairs may use an older SONAME together. Inspect
    # their contracts against the audited pool; the router gate below checks
    # the ACTUAL single-version-per-package transaction, never this union.
    pool = dict(records)
    for name, versions in report['alternatives'].items():
        for version, record in versions.items():
            pool[name + '#' + version] = record
    capabilities = {value.split('=', 1)[0] for record in pool.values()
                    for value in record.get('provides', [])}
    validate_alternatives(pool, report['alternatives'], capabilities)
    report['migration'] = {n: entries for n, entries in ledger.items() if n in records}
    report['inventories'] = {name: record['elf'] for name, record in records.items()
                             if record['elf']['files']}
    return report


def link_file(source, destination):
    destination.unlink(missing_ok=True)
    try:
        os.link(source, destination)
    except OSError as error:
        # Retained snapshots may belong to a different publishing user;
        # protected_hardlinks then forbids linking otherwise readable files.
        if error.errno not in (errno.EPERM, errno.EXDEV, errno.EOPNOTSUPP, errno.EMLINK):
            raise
        shutil.copyfile(source, destination)
        destination.chmod(0o644)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, help='JSON defaults for this LAN server')
    parser.add_argument('--kernel', help='Override automatic build kernel APK version detection')
    parser.add_argument('--destination', type=Path)
    parser.add_argument('--base-url', help='LAN HTTP origin, including port')
    parser.add_argument('--source-root', type=Path, help='Build output checkout; defaults to this tree')
    parser.add_argument('--incremental', action='store_true',
                        help='Publish new/changed APKs; retain previously published packages')
    parser.add_argument('--dry-run', action='store_true',
                        help='Stage and verify changes without switching the active feed')
    parser.add_argument('--kernel-upgrade-view', action='store_true',
                        help='Keep new kernel packages in the independent kernel channel')
    args = parser.parse_args()
    defaults = json.loads(args.config.read_text()) if args.config else {}
    args.kernel = args.kernel or defaults.get('kernel')
    args.base_url = args.base_url or defaults.get('base_url')
    args.destination = args.destination or Path(defaults.get('destination', '/srv/openwrt-feeds'))
    if args.kernel and not re.fullmatch(r'[A-Za-z0-9._~+-]+', args.kernel):
        parser.error('--kernel or config.kernel must specify an exact kernel version')
    if not args.base_url or '\n' in args.base_url:
        parser.error('--base-url or config.base_url is required')
    return args


def detect_kernel(source_root, apk):
    """Use build metadata, cross-checking any available kernel APK metadata."""
    version_file = source_root / 'staging_dir/target-x86_64_glibc/kernel.version'
    version = version_file.read_text().strip() if version_file.exists() else None
    packages = sorted((source_root / 'bin/systemd/targets/x86/64-glibc/packages').glob('kernel-*.apk'))
    if len(packages) > 1:
        raise ValueError('Multiple kernel APKs in build output; finish/resolve the build first')
    if packages:
        info = dump_index(apk, packages[0])['info']
        if info['name'] != 'kernel':
            raise ValueError('Expected kernel APK metadata')
        if version and version != info['version']:
            raise ValueError('Build kernel.version does not match kernel APK; finish the build first')
        version = info['version']
    if not version or not re.fullmatch(r'[A-Za-z0-9._~+-]+', version):
        raise ValueError('Cannot detect build kernel ABI; build the kernel or specify --kernel')
    return version


def point_current(public, snapshot):
    """Kernel-independent routers follow public/current (Debian/Fedora style)."""
    current = public / 'current'
    previous = os.readlink(current) if current.is_symlink() else None
    temporary = public / '.current.new'
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path('snapshots') / Path(snapshot).name)
    os.replace(temporary, current)
    return previous


def publish(args):
    tree = Path(__file__).resolve().parent.parent
    source_root = (args.source_root or tree).resolve()
    apk = tree / 'staging_dir/host/bin/apk'
    kernel_upgrade_view = getattr(args, 'kernel_upgrade_view', False)
    args.kernel = args.kernel or detect_kernel(source_root, apk)
    sources = [('target', source_root / 'bin/systemd/targets/x86/64-glibc/packages')]
    package_root = source_root / 'bin/systemd/packages/x86_64'
    sources += [(p.name, p) for p in sorted(package_root.iterdir())
                if p.is_dir() and any(p.glob('*.apk'))]
    destination = args.destination.resolve()
    stage_only = getattr(args, 'stage_only', False)
    GUARD.require_coordinator(destination, stage_only or args.dry_run)
    destination.mkdir(parents=True, exist_ok=True)
    public = destination / 'public'
    snapshots = public / 'snapshots'
    aliases = public / 'abi'
    snapshots.mkdir(parents=True, exist_ok=True)
    aliases.mkdir(exist_ok=True)
    with (destination / '.publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = aliases / args.kernel
        old = json.loads((previous / 'manifest.json').read_text()) if previous.exists() else None
        key_hash = sha256(tree / 'public-key.pem')
        if old and old['signing_key_sha256'] != key_hash:
            raise ValueError('Signing key changed; configure trust before publishing')
        previous_hashes = old.get('apk_files', {}) if old else {}
        if old and not previous_hashes:
            previous_hashes = {f'{name}/{p.name}': sha256(p)
                               for name in old['repositories']
                               for p in (previous / name).glob('*.apk')}
        source_files = {}
        for name, source in sources:
            packages = sorted(source.glob('*.apk'))
            if not packages and not kernel_upgrade_view:
                if args.incremental and old and name in old['repositories']:
                    continue
                raise ValueError(f'No APKs in {source}')
            for package in packages:
                if kernel_upgrade_view and package.name.startswith(
                        ('kernel-', 'kmod-', 'linux-image-', 'linux-headers-')):
                    # A userspace package literally named "kmod" also has
                    # a kmod-<version>.apk filename. Classify package names,
                    # not the ambiguous filename prefix.
                    if kernel_channel_package(dump_index(apk, package)['info']):
                        continue
                # Immutable payloads belong to the multi-generation channel.
                # ABI-specific views retain only their logical trackers, whose
                # exact global kernel dependency this publisher checks below.
                if '-owrt-' in package.name and package.name.startswith(
                        ('linux-image-', 'kmod-', 'kernel-dev-headers-')):
                    continue
                source_files[f'{name}/{package.name}'] = (package, sha256(package))
        changes = sorted(path for path, (_, digest) in source_files.items()
                         if not args.incremental or previous_hashes.get(path) != digest)
        origin = args.base_url.rstrip('/')
        baseline_needed = bool(old and old.get('schema_version') != SCHEMA_VERSION)
        if args.incremental and old and not changes and not baseline_needed and old.get('base_url') == origin:
            return {'status': 'unchanged', 'kernel': args.kernel,
                    'snapshot': str(previous.resolve()), 'changed_packages': [],
                    'affected_repositories': [], 'source_files_examined': len(source_files),
                    'alias': str(previous), 'previous': str(previous.resolve())}
        snapshot_name = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        work = Path(tempfile.mkdtemp(prefix='.publish-', dir=destination))
        try:
            payload = work / 'payload'
            payload.mkdir()
            keys = work / 'keys'
            keys.mkdir()
            shutil.copyfile(tree / 'public-key.pem', keys / 'public-key.pem')
            changed_files = {}
            if args.incremental and old:
                for name in old['repositories']:
                    repo = payload / name
                    repo.mkdir()
                    for package in (previous / name).glob('*.apk'):
                        link_file(package, repo / package.name)
                    old_index = previous / name / 'packages.adb'
                    verify(apk, keys, [old_index])
                    link_file(old_index, repo / 'packages.adb')
            for name, _ in sources:
                (payload / name).mkdir(exist_ok=True)
            for path in changes:
                source, digest = source_files[path]
                target = payload / path
                # Copy through a new inode so retained snapshots never change.
                temporary = target.with_name('.' + target.name + '.new')
                shutil.copyfile(source, temporary)
                temporary.chmod(0o644)
                if sha256(temporary) != digest:
                    raise ValueError(f'APK changed during publication; finish the build first: {path}')
                os.replace(temporary, target)
                changed_files.setdefault(target.parent.name, []).append(target)
            indexes = {}
            affected = set()
            for repo in sorted(payload.iterdir()):
                if repo.name in changed_files or not (repo / 'packages.adb').exists():
                    indexes[repo.name] = index_repository(apk, tree, keys, repo,
                                                         changed_files.get(repo.name),
                                                         allow_empty=kernel_upgrade_view)
                    affected.add(repo.name)
                else:
                    indexes[repo.name] = dump_index(apk, repo / 'packages.adb')
            custom_packages = {}
            # Canonical source repositories take precedence over an older
            # projected custom copy, which may have the same version/name.
            for name in sorted(indexes, key=lambda name: (name == 'custom', name)):
                for info in indexes[name]['packages']:
                    if is_custom_origin(info.get('origin', '')):
                        filename = package_filename(info)
                        path = f'{name}/{filename}'
                        if name == 'custom' and path not in source_files and filename in custom_packages:
                            continue
                        package = payload / path
                        digest = source_files.get(path, (None, None))[1]
                        digest = digest or previous_hashes.get(path) or sha256(package)
                        earlier = custom_packages.get(filename)
                        if earlier and earlier[1] != digest:
                            raise ValueError(f'Conflicting custom APKs: {filename}')
                        custom_packages[filename] = (package, digest)
            if custom_packages:
                custom_repo = payload / 'custom'
                custom_repo.mkdir(exist_ok=True)
                custom_changes = []
                for filename, (package, digest) in custom_packages.items():
                    target = custom_repo / filename
                    if package == target:
                        continue
                    if target.exists():
                        existing = previous_hashes.get(f'custom/{filename}') or sha256(target)
                        if existing == digest:
                            continue
                        if f'custom/{filename}' in source_files:
                            raise ValueError(f'Conflicting custom APKs: {filename}')
                    link_file(package, target)
                    custom_changes.append(target)
                if custom_changes or 'custom' not in indexes:
                    indexes['custom'] = index_repository(apk, tree, keys, custom_repo, custom_changes)
                    affected.add('custom')
            manifest = {'schema_version': SCHEMA_VERSION, 'kernel': args.kernel,
                        'variant': 'native-systemd-glibc', 'snapshot': snapshot_name,
                        'base_url': origin, 'signing_key_sha256': key_hash,
                        'repositories': {}, 'kernel_packages': {}, 'apk_files': {}}
            kernel_versions = []
            changed_packages = []
            same_version_rebuilds = []
            for name, index in indexes.items():
                repo = payload / name
                for info in index['packages']:
                    filename = package_filename(info)
                    path = f'{name}/{filename}'
                    digest = source_files.get(path, (None, None))[1]
                    if name == 'custom' and filename in custom_packages:
                        digest = custom_packages[filename][1]
                    digest = digest or previous_hashes.get(path) or sha256(repo / filename)
                    manifest['apk_files'][path] = digest
                    if path in changes:
                        changed_packages.append({'repository': name, 'name': info['name'],
                                                 'version': info['version'], 'filename': filename})
                        if path in previous_hashes and digest != previous_hashes[path]:
                            same_version_rebuilds.append(path)
                    if info['arch'] not in ('x86_64', 'all', 'noarch'):
                        raise ValueError(f'Wrong architecture: {info["name"]}')
                    dependencies = [d for d in info.get('depends', [])
                                    if re.match(r'^kernel(?:[<>=~]|$)', d)]
                    if any(d != 'kernel=' + args.kernel for d in dependencies):
                        raise ValueError(f'Kernel ABI mismatch: {info["name"]}: {dependencies}')
                    configuration = (kernel_upgrade_view and info['name'].startswith('kmod-') and
                                     any(re.match(r'linux-image-openwrt(?:[<>=~]|$)', dep)
                                         for dep in info.get('depends', [])))
                    if info['name'].startswith('kmod-') and not dependencies and not configuration:
                        raise ValueError(f'Unpinned kmod: {info["name"]}')
                    if info['name'] == 'kernel':
                        kernel_versions.append(info['version'])
                    if info['name'] == 'kernel' or dependencies or (
                            info['name'].startswith('kmod-') and not configuration):
                        manifest['kernel_packages'][path] = digest
                manifest['repositories'][name] = {'packages': len(index['packages']),
                                                  'index_sha256': sha256(repo / 'packages.adb')}
            if kernel_versions != [args.kernel] and not (kernel_upgrade_view and not kernel_versions):
                raise ValueError(f'Expected exactly kernel {args.kernel}, found {kernel_versions}')
            if old:
                for path, digest in old['kernel_packages'].items():
                    if manifest['kernel_packages'].get(path) != digest:
                        raise ValueError(f'Existing ABI package changed or disappeared: {path}')
            manifest['ucode_abi'] = validate_ucode_abi(apk, keys, payload, indexes, work)
            manifest['elf_abi'] = validate_elf_abi(apk, keys, payload, indexes, work)
            if same_version_rebuilds:
                raise same_version_rebuild_error(apk, previous, payload, same_version_rebuilds)
            urls = [f'{origin}/abi/{args.kernel}/{name}/packages.adb' for name in indexes]
            (payload / 'repositories.list').write_text(
                '# Local native-systemd/glibc feeds; kernel packages are in kernel-upgrades.\n' +
                ''.join(f'{origin}/current/{name}/packages.adb\n' for name in indexes))
            (payload / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            for directory in [payload, *payload.iterdir()]:
                if directory.is_dir():
                    directory.chmod(0o755)
            result = {'status': 'dry-run' if args.dry_run else 'published', 'kernel': args.kernel,
                      'snapshot': str(previous.resolve()) if args.dry_run and old else None,
                      'changed_packages': changed_packages, 'affected_repositories': sorted(affected),
                      'same_version_rebuilds': same_version_rebuilds,
                      'baseline_created': baseline_needed, 'source_files_examined': len(source_files),
                      'repositories': urls, 'packages': sum(r['packages'] for r in manifest['repositories'].values()),
                      'kernel_packages': len(manifest['kernel_packages'])}
            result['ucode_abi'] = manifest['ucode_abi']
            if stage_only:
                final = snapshots / snapshot_name
                payload.rename(final)
                result.update(status='prepared', snapshot=str(final), alias=str(previous),
                              previous=str(previous.resolve()) if previous.exists() else None,
                              current=str(public / 'current'),
                              current_previous=(os.readlink(public / 'current')
                                                if (public / 'current').is_symlink() else None))
            elif not args.dry_run:
                final = snapshots / snapshot_name
                payload.rename(final)
                temporary_link = aliases / ('.' + args.kernel + '.new')
                temporary_link.unlink(missing_ok=True)
                temporary_link.symlink_to(Path('../snapshots') / snapshot_name)
                os.replace(temporary_link, previous)
                point_current(public, final)
                result['snapshot'] = str(final)
            return result
        finally:
            shutil.rmtree(work)


def promote(result, destination, receipt):
    GUARD.authorize(destination, result, receipt, 'userspace')
    GUARD.check_alias(result)
    if result['status'] == 'unchanged':
        return result
    alias = Path(result['alias'])
    temporary = alias.with_name('.' + alias.name + '.new')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(Path('../snapshots') / Path(result['snapshot']).name)
    os.replace(temporary, alias)
    if result.get('current'):
        point_current(Path(result['current']).parent, result['snapshot'])
    return {**result, 'status': 'published'}


def restore_alias(result):
    """Undo only our first pointer if the kernel pointer could not commit."""
    if result['status'] != 'prepared':
        return
    alias = Path(result['alias'])
    current = Path(result['current']) if result.get('current') else None
    if (current and current.is_symlink() and
            current.resolve() == Path(result['snapshot']).resolve()):
        if result.get('current_previous'):
            temporary = current.with_name('.current.rollback')
            temporary.unlink(missing_ok=True)
            temporary.symlink_to(result['current_previous'])
            os.replace(temporary, current)
        else:
            current.unlink()
    if not alias.exists() or alias.resolve() != Path(result['snapshot']).resolve():
        return
    if result['previous'] is None:
        alias.unlink()
        return
    temporary = alias.with_name('.' + alias.name + '.rollback')
    temporary.unlink(missing_ok=True)
    temporary.symlink_to(result['previous'])
    os.replace(temporary, alias)


if __name__ == '__main__':
    try:
        print(json.dumps(publish(parse_args()), indent=2))
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        if isinstance(error, subprocess.CalledProcessError):
            output = (error.stdout or b'') + (error.stderr or b'')
            print(output.decode(errors='replace') if output else str(error))
        else:
            print(error)
        raise SystemExit(1)
