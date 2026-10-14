#!/usr/bin/env python3
"""Publish signed native-systemd/glibc APK feeds, optionally incrementally."""
import argparse
import datetime
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

SCHEMA_VERSION = 2


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def is_custom_origin(origin):
    return origin.startswith(('feeds/base/custom/', 'package/custom/', 'feeds/custom/'))


def dump_index(apk, index):
    return json.loads(subprocess.check_output(
        [str(apk), 'adbdump', '--format', 'json', str(index)]))


def verify(apk, keys, files):
    if files:
        subprocess.run([str(apk), 'verify', '--keys-dir', str(keys), *map(str, files)],
                       check=True, capture_output=True)


def index_repository(apk, tree, keys, repo, changed=None):
    packages = sorted(repo.glob('*.apk'))
    if not packages:
        raise ValueError(f'No APKs in {repo}')
    verify(apk, keys, packages if changed is None else changed)
    # Unlink an index reused from an older snapshot before mkndx writes it.
    index = repo / 'packages.adb'
    index.unlink(missing_ok=True)
    subprocess.run([str(apk), 'mkndx', '--keys-dir', str(keys),
                    '--sign-key', str(tree / 'private-key.pem'),
                    '--output', str(index), *map(str, packages)],
                   check=True, capture_output=True)
    verify(apk, keys, [index])
    return dump_index(apk, index)


def package_filename(info):
    filename = f'{info["name"]}-{info["version"]}.apk'
    if Path(filename).name != filename:
        raise ValueError(f'Invalid package filename: {filename}')
    return filename


def link_file(source, destination):
    destination.unlink(missing_ok=True)
    os.link(source, destination)


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


def publish(args):
    tree = Path(__file__).resolve().parent.parent
    source_root = (args.source_root or tree).resolve()
    apk = tree / 'staging_dir/host/bin/apk'
    args.kernel = args.kernel or detect_kernel(source_root, apk)
    sources = [('target', source_root / 'bin/systemd/targets/x86/64-glibc/packages')]
    package_root = source_root / 'bin/systemd/packages/x86_64'
    sources += [(p.name, p) for p in sorted(package_root.iterdir())
                if p.is_dir() and any(p.glob('*.apk'))]
    destination = args.destination.resolve()
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
            if not packages:
                if args.incremental and old and name in old['repositories']:
                    continue
                raise ValueError(f'No APKs in {source}')
            for package in packages:
                source_files[f'{name}/{package.name}'] = (package, sha256(package))
        changes = sorted(path for path, (_, digest) in source_files.items()
                         if not args.incremental or previous_hashes.get(path) != digest)
        origin = args.base_url.rstrip('/')
        baseline_needed = bool(old and old.get('schema_version') != SCHEMA_VERSION)
        if args.incremental and old and not changes and not baseline_needed and old.get('base_url') == origin:
            return {'status': 'unchanged', 'kernel': args.kernel,
                    'snapshot': str(previous.resolve()), 'changed_packages': [],
                    'affected_repositories': [], 'source_files_examined': len(source_files)}
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
                                                         changed_files.get(repo.name))
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
                    if info['name'].startswith('kmod-') and not dependencies:
                        raise ValueError(f'Unpinned kmod: {info["name"]}')
                    if info['name'] == 'kernel':
                        kernel_versions.append(info['version'])
                    if info['name'] == 'kernel' or dependencies or info['name'].startswith('kmod-'):
                        manifest['kernel_packages'][path] = digest
                manifest['repositories'][name] = {'packages': len(index['packages']),
                                                  'index_sha256': sha256(repo / 'packages.adb')}
            if kernel_versions != [args.kernel]:
                raise ValueError(f'Expected exactly kernel {args.kernel}, found {kernel_versions}')
            if old:
                for path, digest in old['kernel_packages'].items():
                    if manifest['kernel_packages'].get(path) != digest:
                        raise ValueError(f'Existing ABI package changed or disappeared: {path}')
            urls = [f'{origin}/abi/{args.kernel}/{name}/packages.adb' for name in indexes]
            (payload / 'repositories.list').write_text(
                '# Local native-systemd/glibc feeds, pinned to kernel ABI.\n' + '\n'.join(urls) + '\n')
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
            if not args.dry_run:
                final = snapshots / snapshot_name
                payload.rename(final)
                temporary_link = aliases / ('.' + args.kernel + '.new')
                temporary_link.unlink(missing_ok=True)
                temporary_link.symlink_to(Path('../snapshots') / snapshot_name)
                os.replace(temporary_link, previous)
                result['snapshot'] = str(final)
            return result
        finally:
            shutil.rmtree(work)


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
