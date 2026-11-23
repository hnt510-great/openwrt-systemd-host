#!/usr/bin/env python3
"""Verify, stage, and inspect published kernel generations for safe reuse."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile


def sha256(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def public_key_fingerprint(public_key_path):
    """Return SHA-256 of canonical PEM public key (matches publish-kernel-upgrade-feed.py)."""
    raw = subprocess.check_output(
        ['openssl', 'pkey', '-in', str(public_key_path), '-pubin', '-pubout'],
        stderr=subprocess.PIPE,
    )
    return hashlib.sha256(raw).hexdigest()


def resolve_aliases(destination):
    """Pin live kernel and userspace snapshot paths once."""
    destination = Path(destination)
    k_alias = destination / 'public/kernel-upgrades'
    u_alias = destination / 'public/current'
    return {
        'kernel_alias': str(k_alias),
        'kernel_snapshot': str(k_alias.resolve()) if k_alias.exists() else None,
        'userspace_alias': str(u_alias),
        'userspace_snapshot': str(u_alias.resolve()) if u_alias.exists() else None,
    }


def load_published_state(destination):
    """Read pinned snapshots, manifest, and per-generation records."""
    snapshots = resolve_aliases(destination)
    k_snap = Path(snapshots['kernel_snapshot']) if snapshots['kernel_snapshot'] else None
    manifest = None
    if k_snap and (k_snap / 'manifest.json').is_file():
        manifest = json.loads((k_snap / 'manifest.json').read_text())
    return snapshots, manifest


def build_generation_record(sequence, release, version, abi, timestamp, inputs,
                            config, signing_key_sha256, kernel_packages, kmod_packages):
    """Construct a versioned, verifiable per-generation publication record."""
    return {
        'schema': 1,
        'sequence': int(sequence),
        'release': release,
        'version': version,
        'abi': abi,
        'target': {
            'board': config.get('CONFIG_TARGET_BOARD', '"x86"').strip('"'),
            'subtarget': config.get('CONFIG_TARGET_SUBTARGET', '').strip('"'),
            'arch': config.get('CONFIG_ARCH', '"x86_64"').strip('"'),
        },
        'timestamp': timestamp,
        'inputs': inputs,
        'signing_key_sha256': signing_key_sha256,
        'kernel_packages': kernel_packages,
        'kmod_packages': kmod_packages,
    }


def selected_kmods(config):
    return sorted(
        key.removeprefix('CONFIG_PACKAGE_')
        for key, value in config.items()
        if key.startswith('CONFIG_PACKAGE_kmod-') and value in ('y', 'm')
    )


def verify_published_generation(tree, destination, record, config, apk, *,
                                pinned_snapshots=None, manifest=None, keys_dir=None):
    """Verify that a published generation record and all its signed APKs are intact."""
    issues = []
    if not record or record.get('schema') != 1:
        return False, ['missing or unsupported published generation record'], None

    snapshots = pinned_snapshots or resolve_aliases(destination)
    k_snap_str = snapshots.get('kernel_snapshot')
    u_snap_str = snapshots.get('userspace_snapshot')
    if not k_snap_str or not Path(k_snap_str).is_dir():
        return False, ['published kernel-upgrades snapshot is missing'], None
    if not u_snap_str or not Path(u_snap_str).is_dir():
        return False, ['published current userspace snapshot is missing'], None

    k_snap = Path(k_snap_str)
    u_snap = Path(u_snap_str)
    if manifest is None:
        mpath = k_snap / 'manifest.json'
        if not mpath.is_file():
            return False, ['published kernel manifest.json is missing'], None
        manifest = json.loads(mpath.read_text())

    key_root = Path(tree) if (Path(tree) / 'public-key.pem').is_file() else (Path(keys_dir) if keys_dir else Path(tree))
    pub_key = key_root / 'public-key.pem'
    if not pub_key.is_file():
        return False, ['checkout public-key.pem is missing'], None
    expected_fp = public_key_fingerprint(pub_key)
    if manifest.get('signing_key_sha256') != expected_fp:
        issues.append('kernel channel signing_key_sha256 does not match checkout public-key.pem')
    if record.get('signing_key_sha256') != expected_fp:
        issues.append('generation record signing_key_sha256 does not match checkout public-key.pem')
    if issues:
        return False, issues, None

    sequence = int(record['sequence'])
    release = record['release']
    version = record['version']
    abi = record['abi']
    manifest_pkgs = manifest.get('packages', {})

    # Required kernel-channel packages
    required_kernel_names = {f'linux-image-{release}', 'linux-image-openwrt', 'kernel'}
    if config.get('CONFIG_PACKAGE_kernel-dev-headers') in ('y', 'm'):
        required_kernel_names |= {f'linux-headers-{release}', 'kernel-dev-headers'}

    rec_kpkgs = record.get('kernel_packages') or {}
    verified_kernel = {}
    seen_knames = set()
    for filename, meta in sorted(rec_kpkgs.items()):
        name = meta.get('name')
        path = k_snap / filename
        if not path.is_file():
            issues.append(f'missing published kernel package: {filename}')
            continue
        m_entry = manifest_pkgs.get(filename)
        if not m_entry or m_entry.get('sha256') != meta.get('sha256'):
            issues.append(f'kernel manifest digest mismatch for {filename}')
            continue
        actual_hash = sha256(path)
        if actual_hash != meta.get('sha256'):
            issues.append(f'kernel package digest mismatch on disk: {filename}')
            continue
        ver_res = subprocess.run(
            [str(apk), 'verify', '--keys-dir', str(key_root.resolve()), str(path)],
            capture_output=True, text=True,
        )
        if ver_res.returncode != 0:
            issues.append(f'kernel package signature verification failed: {filename}')
            continue
        verified_kernel[filename] = {'path': path, 'meta': meta}
        seen_knames.add(name)

    missing_knames = sorted(required_kernel_names - seen_knames)
    if missing_knames:
        issues.append('missing required kernel packages in record: ' + ', '.join(missing_knames))

    # Required selected kmod packages in userspace snapshot
    wanted_kmods = selected_kmods(config)
    rec_kmods = record.get('kmod_packages') or {}
    verified_kmods = {}
    for kmod_name in wanted_kmods:
        meta = rec_kmods.get(kmod_name)
        if not meta:
            issues.append(f'selected kmod missing from published generation record: {kmod_name}')
            continue
        repo = meta.get('repo')
        filename = meta.get('filename')
        path = u_snap / repo / filename if (repo and filename) else None
        if not path or not path.is_file():
            issues.append(f'missing published kmod package: {repo}/{filename}')
            continue
        actual_hash = sha256(path)
        if actual_hash != meta.get('sha256'):
            issues.append(f'published kmod digest mismatch: {repo}/{filename}')
            continue
        ver_res = subprocess.run(
            [str(apk), 'verify', '--keys-dir', str(key_root.resolve()), str(path)],
            capture_output=True, text=True,
        )
        if ver_res.returncode != 0:
            issues.append(f'published kmod signature verification failed: {repo}/{filename}')
            continue
        verified_kmods[kmod_name] = {'path': path, 'meta': meta}

    if issues:
        return False, issues, None

    return True, [], {
        'sequence': sequence,
        'release': release,
        'version': version,
        'abi': abi,
        'timestamp': record.get('timestamp'),
        'snapshots': snapshots,
        'key_root': str(key_root.resolve()),
        'kernel_packages': verified_kernel,
        'kmod_packages': verified_kmods,
    }


def stage_reused_kernel(tree, destination, record, config, apk, stage_dir, *,
                        pinned_snapshots=None, manifest=None, keys_dir=None):
    """Verify and stage an isolated copy of a published kernel generation."""
    ok, issues, verified = verify_published_generation(
        tree, destination, record, config, apk,
        pinned_snapshots=pinned_snapshots, manifest=manifest, keys_dir=keys_dir,
    )
    if not ok:
        raise ValueError('Cannot reuse published kernel generation: ' + '; '.join(issues))

    stage_dir = Path(stage_dir)
    kernel_dir = stage_dir / 'kernel'
    kmods_dir = stage_dir / 'kmods'
    kernel_dir.mkdir(parents=True, exist_ok=True)
    kmods_dir.mkdir(parents=True, exist_ok=True)

    staged_kernel = {}
    image_apk = None
    release = verified['release']
    for filename, item in sorted(verified['kernel_packages'].items()):
        dest = kernel_dir / filename
        shutil.copyfile(item['path'], dest)
        if sha256(dest) != item['meta']['sha256']:
            raise ValueError(f'Kernel package changed during reuse staging: {filename}')
        dest.chmod(0o644)
        staged_kernel[filename] = {**item['meta'], 'staged_path': str(dest)}
        if item['meta']['name'] == f'linux-image-{release}':
            image_apk = dest

    if image_apk is None:
        raise ValueError(f'Verified generation lacks linux-image-{release}')

    staged_kmods = {}
    for kmod_name, item in sorted(verified['kmod_packages'].items()):
        repo = item['meta']['repo']
        filename = item['meta']['filename']
        dest = kmods_dir / repo / filename
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(item['path'], dest)
        if sha256(dest) != item['meta']['sha256']:
            raise ValueError(f'kmod package changed during reuse staging: {repo}/{filename}')
        dest.chmod(0o644)
        staged_kmods[kmod_name] = {**item['meta'], 'staged_path': str(dest)}

    # Extract vmlinuz, config, and optional System.map from the verified signed image APK
    with tempfile.TemporaryDirectory(prefix='extract-kernel-', dir=stage_dir) as extract_tmp:
        subprocess.run(
            [str(apk), 'extract', '--keys-dir', verified['key_root'],
             '--destination', extract_tmp, str(image_apk)],
            check=True, capture_output=True, text=True,
        )
        extracted_root = Path(extract_tmp) / 'usr/lib/openwrt-kernel' / release
        for item_name, required in (('vmlinuz', True), ('config', True), ('System.map', False)):
            src = extracted_root / item_name
            if not src.is_file():
                if required:
                    raise ValueError(f'Verified linux-image-{release} lacks {item_name}')
                continue
            shutil.copyfile(src, stage_dir / item_name)
            (stage_dir / item_name).chmod(0o644)

    (stage_dir / 'release').write_text(release + '\n')
    (stage_dir / 'kernel.version').write_text(verified['abi'] + '\n')
    (stage_dir / 'kernel-package.version').write_text(verified['version'] + '\n')
    if verified['timestamp']:
        (stage_dir / 'timestamp').write_text(verified['timestamp'] + '\n')

    metadata = {
        'schema': 1,
        'sequence': verified['sequence'],
        'release': release,
        'version': verified['version'],
        'abi': verified['abi'],
        'timestamp': verified['timestamp'],
        'snapshots': verified['snapshots'],
        'vmlinuz_sha256': sha256(stage_dir / 'vmlinuz'),
        'config_sha256': sha256(stage_dir / 'config'),
        'kernel_packages': staged_kernel,
        'kmod_packages': staged_kmods,
    }
    (stage_dir / 'metadata.json').write_text(json.dumps(metadata, sort_keys=True, indent=2) + '\n')
    return metadata


def recorded_timestamp(tree, sequence):
    """Return recorded KBUILD_BUILD_TIMESTAMP if it matches the requested sequence."""
    reuse_dir = os.environ.get('KERNEL_REUSE_DIR', '').strip()
    if reuse_dir:
        meta_path = Path(reuse_dir) / 'metadata.json'
        if meta_path.is_file():
            try:
                meta = json.loads(meta_path.read_text())
                if int(meta.get('sequence', -1)) == int(sequence) and meta.get('timestamp'):
                    return meta['timestamp']
            except (OSError, ValueError):
                pass
    state_file = Path(tree) / 'tmp/.kernel-publication-inputs.json'
    if state_file.is_file():
        try:
            state = json.loads(state_file.read_text())
            if int(state.get('sequence', -1)) == int(sequence) and state.get('timestamp'):
                return state['timestamp']
        except (OSError, ValueError):
            pass
    return ''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    ts = sub.add_parser('timestamp', help='Print recorded KBUILD_BUILD_TIMESTAMP for a sequence')
    ts.add_argument('--tree', type=Path, required=True)
    ts.add_argument('--sequence', type=int, required=True)
    args = parser.parse_args()
    if args.command == 'timestamp':
        value = recorded_timestamp(args.tree, args.sequence)
        if value:
            print(value)


if __name__ == '__main__':
    main()
