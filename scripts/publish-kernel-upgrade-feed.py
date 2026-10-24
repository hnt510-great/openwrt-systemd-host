#!/usr/bin/env python3
"""Publish a signed, immutable multi-generation kernel channel, never a router."""
import argparse
import fcntl
from functools import cmp_to_key
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import tempfile
import time

KEEP_GENERATIONS = 2
_guard_spec = importlib.util.spec_from_file_location(
    'kernel_upgrade_preflight', Path(__file__).with_name('apk-upgrade-preflight.py'))
GUARD = importlib.util.module_from_spec(_guard_spec)
_guard_spec.loader.exec_module(GUARD)


def retained_packages(packages, images, image_sequences, apk):
    """Keep the newest publication generations and their exact dependency pins."""
    keep_images = set(sorted(images, key=image_sequences.get, reverse=True)[:KEEP_GENERATIONS])
    retired_payloads = {entry['info']['name'] for entry in packages.values()
        if '-owrt-' in entry['info']['name'] and
        entry['info']['name'].startswith(('linux-image-', 'kmod-', 'kernel-dev-headers-')) and
        not any(entry['info']['name'].endswith(image[len('linux-image-'):]) for image in keep_images)}
    keep_abis = {images[name] for name in keep_images}
    candidates = {}
    for filename, entry in packages.items():
        info = entry['info']
        if info['name'] in retired_payloads:
            continue
        if info['name'] == 'kernel' and info['version'] not in keep_abis:
            continue
        if any(dep.split('=', 1)[0] in retired_payloads or
               (dep.startswith('kernel=') and dep.split('=', 1)[1] not in keep_abis)
               for dep in info.get('depends', [])):
            continue
        candidates[filename] = entry
    # Support packages also need a bound; use APK ordering, not lexical order.
    by_name = {}
    for filename, entry in candidates.items():
        by_name.setdefault(entry['info']['name'], []).append(filename)
    def compare(left, right):
        order = subprocess.check_output([str(apk), 'version', '--test',
            candidates[left]['info']['version'], candidates[right]['info']['version']], text=True).strip()
        return {'<': -1, '=': 0, '>': 1}[order]
    retained = {filename for versions in by_name.values()
                for filename in sorted(versions, key=cmp_to_key(compare), reverse=True)[:KEEP_GENERATIONS]}
    return ({name: entry for name, entry in candidates.items() if name in retained},
            {name: abi for name, abi in images.items() if name in keep_images})


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def publish(source, destination, apk, key, keys, dry_run=False, stage_only=False):
    GUARD.require_coordinator(destination, stage_only or dry_run)
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / '.kernel-publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        active = destination / 'public/kernel-upgrades'
        previous = json.loads((active / 'manifest.json').read_text()) if active.exists() else None
        public_key = subprocess.check_output(['openssl', 'pkey', '-in', str(key), '-pubout'])
        fingerprint = hashlib.sha256(public_key).hexdigest()
        if previous and previous['signing_key_sha256'] != fingerprint:
            raise ValueError('Signing key changed; existing client trust must be preserved')
        with tempfile.TemporaryDirectory(dir=destination) as tmp:
            stage = Path(tmp) / 'channel'
            stage.mkdir()
            packages = dict(previous['packages']) if previous else {}
            if previous:
                for filename in packages:
                    if digest(active / filename) != packages[filename]['sha256']:
                        raise ValueError('Retained kernel channel package changed: ' + filename)
                    shutil.copy2(active / filename, stage / filename)
            allowed = {'kernel', 'kernel-dev-headers', 'openwrt-kernel-upgrade',
                       'linux-image-openwrt', 'apk-mbedtls', 'apk-openssl', 'ubox',
                       'systemd-openwrt', 'lan-apk-feeds', 'grub2', 'grub2-efi', 'grub2-editenv'}
            incoming = {}
            retained_payloads = {entry['info']['name']: entry['info']['version']
                for entry in packages.values() if '-owrt-' in entry['info']['name']}
            for path in sorted(source.rglob('*.apk')):
                metadata = json.loads(subprocess.check_output(
                    [str(apk), 'adbdump', '--format', 'json', str(path)], text=True))
                info = metadata['info']
                name = info['name']
                if name not in allowed and not name.startswith(('kmod-', 'linux-image-', 'kernel-dev-headers-')):
                    continue
                if info['arch'] != 'x86_64':
                    raise ValueError('Wrong architecture: ' + name)
                if info.get('origin') == 'kernel-generations':
                    for directory in metadata.get('paths', []):
                        for entry in [directory, *directory.get('files', [])]:
                            acl = entry.get('acl', {})
                            # APK encodes symlink targets with a little-endian
                            # file type. Their conventional 0777 mode is inert.
                            target = bytes.fromhex(entry.get('target', ''))
                            symlink = int.from_bytes(target[:2], 'little') == stat.S_IFLNK
                            if (acl.get('user', 'root') != 'root' or
                                    acl.get('group', 'root') != 'root' or
                                    (not symlink and acl.get('mode', 0) & 0o022)):
                                raise ValueError('Unsafe kernel payload ownership/mode: ' + name)
                subprocess.run([str(apk), 'verify', '--keys-dir', str(keys), str(path)],
                               check=True, capture_output=True)
                filename = name + '-' + info['version'] + '.apk'
                if filename != path.name:
                    raise ValueError('Invalid package filename')
                checksum = digest(path)
                if name in retained_payloads and retained_payloads[name] != info['version']:
                    raise ValueError('Generation payload version changed: ' + name)
                if '-owrt-' in name:
                    retained_payloads[name] = info['version']
                if filename in incoming and incoming[filename] != checksum:
                    raise ValueError('Conflicting package copies: ' + filename)
                incoming[filename] = checksum
                if filename in packages and packages[filename]['sha256'] != checksum:
                    if name in allowed and name not in ('kernel', 'kernel-dev-headers', 'linux-image-openwrt'):
                        raise ValueError('Published kernel channel package changed: ' + filename +
                                         '; bump this support package PKG_RELEASE and rebuild. '
                                         'The published file will not be overwritten')
                    raise ValueError('Published kernel channel package changed: ' + filename)
                packages[filename] = {'sha256': checksum, 'info': info}
                shutil.copy2(path, stage / filename)
            images = {entry['info']['name']: entry['info']['version'] for entry in packages.values()
                      if entry['info']['name'].startswith('linux-image-') and
                      entry['info']['name'] != 'linux-image-openwrt'}
            trackers = [entry['info'] for entry in packages.values()
                        if entry['info']['name'] == 'linux-image-openwrt']
            if not images or not trackers:
                raise ValueError('No versioned image and rolling tracker found')
            image_sequences = {}
            for name, abi in images.items():
                identity = re.fullmatch(r'(.+)~([0-9a-f]{32})-r([0-9]+)', abi)
                if not identity:
                    raise ValueError('Invalid image ABI: ' + name)
                prefix = ('linux-image-' + identity[1].replace('_rc', '-rc') +
                          '-owrt-' + identity[2] + '-r' + identity[3] + '-g')
                suffix = name.removeprefix(prefix)
                if not name.startswith(prefix) or not suffix.isdigit() or not 1 <= int(suffix) <= 999999:
                    raise ValueError('Image generation and ABI disagree: ' + name)
                image_sequences[name] = int(suffix)
            for tracker in trackers:
                version = re.fullmatch(r'1-r([0-9]+)', tracker['version'])
                pins = [d.split('=', 1) for d in tracker.get('depends', [])
                        if d.startswith('linux-image-') and '=' in d]
                if (not version or len(pins) != 1 or images.get(pins[0][0]) != pins[0][1]
                        or image_sequences[pins[0][0]] != int(version[1])
                        or 'kernel=' + pins[0][1] not in tracker.get('depends', [])):
                    raise ValueError('Rolling tracker and image generation disagree')
            for entry in packages.values():
                info = entry['info']
                if '-owrt-' in info['name'] and info['name'].startswith(('kmod-', 'kernel-dev-headers-')):
                    dependencies = [d for d in info.get('depends', []) if d.startswith('linux-image-')]
                    if len(dependencies) != 1 or '=' not in dependencies[0]:
                        raise ValueError('Unpinned generation payload: ' + info['name'])
                    image, version = dependencies[0].split('=', 1)
                    if images.get(image) != version or not info['name'].endswith(image[len('linux-image-'):]):
                        raise ValueError('Module/image ABI mismatch: ' + info['name'])
            sequence = max(int(info['version'].split('-r')[1]) for info in trackers)
            incoming_sequences = [int(entry['info']['version'].split('-r')[1])
                for filename, entry in packages.items() if filename in incoming and
                entry['info']['name'] == 'linux-image-openwrt']
            packages, images = retained_packages(packages, images, image_sequences, apk)
            for path in stage.glob('*.apk'):
                if path.name not in packages:
                    path.unlink()
            new_images = set(images) - set(previous['images']) if previous else set(images)
            if previous and incoming_sequences and max(incoming_sequences) < previous['sequence']:
                raise ValueError('Refusing to publish a stale kernel generation')
            if previous and any(image_sequences[name] <= previous['sequence'] for name in new_images):
                raise ValueError('New kernel generations require an increasing publication sequence')
            if previous and packages.keys() == previous['packages'].keys() and all(
                    entry['sha256'] == previous['packages'][name]['sha256']
                    for name, entry in packages.items()):
                if digest(active / 'packages.adb') != previous['index_sha256']:
                    raise ValueError('Retained kernel channel index changed')
                subprocess.run([str(apk), 'verify', '--keys-dir', str(keys), str(active / 'packages.adb')],
                               check=True, capture_output=True)
                return {'status': 'unchanged', 'packages': len(packages),
                        'images': len(images), 'channel': str(active), 'snapshot': str(active.resolve()),
                        'alias': str(active), 'previous': str(active.resolve())}
            subprocess.run([str(apk), 'mkndx', '--keys-dir', str(keys), '--sign-key', str(key), '--output', str(stage / 'packages.adb'),
                            *map(str, sorted(stage.glob('*.apk')))], check=True, capture_output=True)
            subprocess.run([str(apk), 'verify', '--keys-dir', str(keys), str(stage / 'packages.adb')],
                           check=True, capture_output=True)
            manifest = {'schema': 1, 'packages': packages, 'images': images, 'sequence': sequence,
                        'keep_generations': KEEP_GENERATIONS,
                        'signing_key_sha256': fingerprint,
                        'index_sha256': digest(stage / 'packages.adb')}
            (stage / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
            if stage_only:
                snapshots = destination / 'public/kernel-snapshots'
                snapshots.mkdir(parents=True, exist_ok=True)
                final = snapshots / str(time.time_ns())
                stage.rename(final)
                return {'status': 'prepared', 'packages': len(packages), 'images': len(images),
                        'channel': str(active), 'snapshot': str(final), 'alias': str(active),
                        'previous': str(active.resolve()) if active.exists() else None}
            if not dry_run:
                snapshots = destination / 'public/kernel-snapshots'
                snapshots.mkdir(parents=True, exist_ok=True)
                final = snapshots / str(time.time_ns())
                stage.rename(final)
                pending = active.with_name('.kernel-upgrades.new')
                pending.unlink(missing_ok=True)
                pending.symlink_to(Path('kernel-snapshots') / final.name)
                os.replace(pending, active)
                # Only this channel owns these snapshots. Collect after the
                # signed replacement is live, never during validation/dry-run.
                for snapshot in snapshots.iterdir():
                    if snapshot != final and snapshot.name.isdigit() and not snapshot.is_symlink():
                        shutil.rmtree(snapshot)
            return {'status': 'dry-run' if dry_run else 'published', 'packages': len(packages),
                    'images': len(images), 'channel': str(active)}


def promote(result, destination, receipt):
    GUARD.authorize(destination, result, receipt, 'kernel')
    GUARD.check_alias(result)
    if result['status'] == 'unchanged':
        return result
    active = Path(result['alias'])
    final = Path(result['snapshot'])
    pending = active.with_name('.kernel-upgrades.new')
    pending.unlink(missing_ok=True)
    pending.symlink_to(Path('kernel-snapshots') / final.name)
    os.replace(pending, active)
    warnings = []
    try:
        for snapshot in final.parent.iterdir():
            if snapshot != final and snapshot.name.isdigit() and not snapshot.is_symlink():
                try:
                    shutil.rmtree(snapshot)
                except OSError as error:
                    warnings.append(str(error))
    except OSError as error:
        warnings.append(str(error))
    return {**result, 'status': 'published', 'cleanup_warnings': warnings}


if __name__ == '__main__':
    tree = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--apk', type=Path, default=tree / 'staging_dir/host/bin/apk')
    parser.add_argument('--key', type=Path, default=tree / 'private-key.pem')
    parser.add_argument('--keys', type=Path, default=tree)
    parser.add_argument('--dry-run', action='store_true')
    args = parser.parse_args()
    print(json.dumps(publish(args.source, args.destination, args.apk, args.key, args.keys, args.dry_run), indent=2))
