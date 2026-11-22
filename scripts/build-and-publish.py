#!/usr/bin/env python3
"""Build and publish signed userspace plus a complete kernel generation."""
import argparse
from datetime import datetime, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time

TREE = Path(__file__).resolve().parents[1]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TREE / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


LAN = load('build_lan_publisher', 'publish-lan-apk-feeds.py')
KERNEL = load('build_kernel_publisher', 'publish-kernel-upgrade-feed.py')
INPUTS = load('kernel_build_inputs', 'kernel-build-inputs.py')
GUARD = load('build_upgrade_preflight', 'apk-upgrade-preflight.py')
CHECKOUT_LOCK = load('checkout_lock', 'checkout-lock.py')
COLD_VERIFY = load('rebuild_cold_verify', 'rebuild-cold-verify.py')
ALLOCATE = LAN.ALLOCATE
# Each round may change exact-version dependents (ELF_DEP_*), so allow a short
# cascade, but never loop on a rebuild that keeps producing new bytes.
ALLOCATION_ROUNDS = 3


class Progress:
    """Show workflow progress on stderr, keeping stdout available for JSON."""
    def __init__(self, enabled=True, stream=None):
        self.stream = stream if stream is not None else sys.stderr
        self.enabled = enabled
        self.terminal = self.stream.isatty()
        self.started = time.monotonic()
        self.updated = 0
        self.percent = 0
        self.phase = None

    def __enter__(self):
        return self

    def __exit__(self, *error):
        if self.enabled and self.terminal and self.phase is not None:
            print(file=self.stream, flush=True)

    def __call__(self, percent, phase, detail=''):
        if not self.enabled:
            return
        now = time.monotonic()
        changed = phase != self.phase
        self.percent = max(self.percent, min(100, int(percent)))
        if not changed and (not self.terminal or now - self.updated < 0.1):
            return
        self.phase = phase
        self.updated = now
        label = phase + (': ' + detail if detail else '')
        elapsed = f'{now - self.started:.1f}s'
        if self.terminal:
            filled = self.percent // 5
            bar = '#' * filled + '-' * (20 - filled)
            width = max(1, shutil.get_terminal_size().columns - 1)
            prefix, suffix = f'[{bar}] {self.percent:3d}% ', f' ({elapsed})'
            available = max(0, width - len(prefix) - len(suffix))
            if len(label) > available:
                label = label[:max(0, available - 3)] + '...'[:available]
            line = prefix + label + suffix
            print('\r\033[2K' + line[:width], end='', file=self.stream, flush=True)
        else:
            print(f'[{self.percent:3d}%] {label} ({elapsed})', file=self.stream, flush=True)


def configuration(tree):
    path = tree / '.config'
    if not path.exists():
        return {}
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line.startswith('CONFIG_') and '=' in line)


def retained_migration_options(tree, make_args, destination=None):
    """Include unselected legacy APKs with an allocated ELF rebuild identity."""
    ledger = tree / 'configs/apk-elf-rebuilds.mk'
    metadata = tree / 'tmp/.packageinfo'
    if not ledger.is_file() or not metadata.is_file():
        return []
    versions = {}
    name = None
    for line in metadata.read_text().splitlines():
        if line.startswith('Package: '):
            name = line.removeprefix('Package: ')
        elif name and line.startswith('Version: '):
            versions[name] = line.removeprefix('Version: ')
    selected = configuration(tree)
    selected.update(arg.split('=', 1) for arg in make_args if arg.startswith('CONFIG_PACKAGE_') and '=' in arg)
    outputs = [tree / 'bin/systemd/packages/x86_64']
    abi_file = tree / 'staging_dir/target-x86_64_glibc/kernel.version'
    if destination is not None and abi_file.is_file():
        outputs.append(destination / 'public/abi' / abi_file.read_text().strip())
    filenames = {p.name for output in outputs for p in output.glob('*/*.apk')}
    options = []
    for name, entries in sorted(LAN.ELF.migration_releases(ledger).items()):
        if name.startswith(('kmod-', 'kernel-dev-headers', 'linux-image-')) or name == 'kernel':
            continue
        key = 'CONFIG_PACKAGE_' + name
        # Respect both configured selections and explicit command-line intent.
        if key in selected:
            continue
        entry = next((e for e in entries if e['before'] == versions.get(name)), None)
        if (entry and f'{name}-{entry["before"]}.apk' in filenames and
                f'{name}-{entry["after"]}.apk' not in filenames):
            apk = TREE / 'staging_dir/host/bin/apk'
            newer = False
            for output in outputs:
                for package in output.glob(f'*/{name}-*.apk'):
                    info = LAN.dump_index(apk, package)['info']
                    if info['name'] != name:
                        continue
                    order = subprocess.check_output([str(apk), 'version', '--test',
                        entry['after'], info['version']], text=True).strip()
                    if order in ('<', '='):
                        newer = True
            if newer:
                continue
            options.append(key + '=m')
    return options


def settings(tree):
    data = json.loads((tree / 'configs/lan-apk-feeds.json').read_text())
    if not data.get('base_url') or not data.get('destination'):
        raise ValueError('LAN feed destination and base_url must be configured')
    data['destination'] = Path(data['destination']).resolve()
    return data


def state_path(tree):
    return tree / 'tmp/.kernel-publication-inputs.json'


def save_state(tree, data):
    path = state_path(tree)
    path.parent.mkdir(exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        try:
            stream.write(json.dumps(data, sort_keys=True, indent=2) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def compiled_release(tree, sequence):
    """The compiled distribution-style kernel release and package version."""
    releases = []
    for path in (tree / 'build_dir/target-x86_64_glibc/linux-x86_64').glob(
            'linux-*/include/config/kernel.release'):
        release = path.read_text().strip()
        match = re.fullmatch(r'(.+)-' + str(sequence) + r'-openwrt', release)
        if match:
            releases.append((release, match[1].replace('-rc', '_rc') + '-r' + str(sequence), path))
    return releases[0] if len(releases) == 1 else None


def image_outputs(output, sequence):
    """Existing image APKs for a build number, in either naming scheme."""
    return (list(output.glob(f'linux-image-*-g{sequence}-*.apk')) +
            list(output.glob(f'linux-image-*-{sequence}-openwrt-*.apk')))


def generation_matches_compiled_image(tree, sequence, timestamp):
    """An input record alone cannot prove that existing immutable bytes match."""
    output = tree / 'bin/systemd/targets/x86/64-glibc/packages'
    images = image_outputs(output, sequence)
    if not images:
        return True
    compiled = compiled_release(tree, sequence)
    if not compiled:
        return False
    release, version, kernel_release = compiled
    releases = [kernel_release]
    image = output / ('linux-image-' + release + '-' + version + '.apk')
    if image not in images:
        return False
    metadata = LAN.dump_index(TREE / 'staging_dir/host/bin/apk', image)
    files = {item['name']: item.get('hash') for directory in metadata.get('paths', [])
             if directory.get('name') == 'usr/lib/openwrt-kernel/' + release
             for item in directory.get('files', [])}
    linux = releases[0].parents[2]
    binary = linux / 'arch/x86/boot/bzImage'
    if not binary.is_file():
        return False
    image_bytes = binary.read_bytes()
    # x86 boot protocol: kernel_version is relative to the real-mode header
    # at offset 0x200. Check the embedded version, not a possibly newer .h file.
    if len(image_bytes) < 0x210 or image_bytes[0x202:0x206] != b'HdrS':
        return False
    start = 0x200 + int.from_bytes(image_bytes[0x20e:0x210], 'little')
    end = image_bytes.find(b'\0', start)
    if end < 0 or not timestamp or not image_bytes[start:end].endswith((' ' + timestamp).encode()):
        return False
    return all(path.is_file() and files.get(name) == LAN.sha256(path)
               for name, path in (('vmlinuz', binary),
                                  ('config', linux / '.config')))


def prepare_sequence(tree, destination, make_args=(), inputs=None):
    """Reuse a proven generation, reserving a new one only for changed inputs."""
    config = configuration(tree)
    value = config.get('CONFIG_OPENWRT_KERNEL_SEQUENCE', '1')
    if not value.isdigit() or not 1 <= int(value) <= 999999:
        raise ValueError('Invalid CONFIG_OPENWRT_KERNEL_SEQUENCE')
    current = int(value)
    manifest = destination / 'public/kernel-upgrades/manifest.json'
    published = json.loads(manifest.read_text())['sequence'] if manifest.exists() else 0
    inputs = inputs or INPUTS.fingerprint(tree, config, make_args)
    previous = json.loads(state_path(tree).read_text()) if state_path(tree).exists() else None
    reuse = (previous and previous.get('schema') == 1 and INPUTS.same_inputs(previous['inputs'], inputs)
             and current <= previous['sequence'] and previous['sequence'] >= published)
    if reuse and not generation_matches_compiled_image(tree, previous['sequence'], previous.get('timestamp')):
        print('Recorded generation differs from existing compiled image/config/timestamp; '
              'reserving an unused generation.', flush=True)
        reuse = False
    selected = previous['sequence'] if reuse else max(current, published + 1)
    output = tree / 'bin/systemd/targets/x86/64-glibc/packages'
    # Reuse partial immutable outputs only with the same proven inputs/time.
    # Unknown or changed inputs must never overwrite an existing generation.
    while not reuse and selected <= 999999 and image_outputs(output, selected):
        selected += 1
    if selected > 999999:
        raise ValueError('Kernel publication sequence exhausted')
    if selected != current or 'CONFIG_OPENWRT_KERNEL_SEQUENCE' not in config:
        path = tree / '.config'
        text = path.read_text()
        line = 'CONFIG_OPENWRT_KERNEL_SEQUENCE=' + str(selected)
        if 'CONFIG_OPENWRT_KERNEL_SEQUENCE' in config:
            text = re.sub(r'^CONFIG_OPENWRT_KERNEL_SEQUENCE=.*$', line, text, flags=re.M)
        else:
            text += '\n' + line + '\n'
        with tempfile.NamedTemporaryFile(mode='w', dir=tree, delete=False) as stream:
            temporary = Path(stream.name)
            try:
                os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
                stream.write(text)
                stream.flush()
                os.fsync(stream.fileno())
                os.replace(temporary, path)
            finally:
                temporary.unlink(missing_ok=True)
    if reuse and previous['inputs'] != inputs:
        # Same generation; record the current host programs and digest format.
        save_state(tree, {**previous, 'inputs': inputs})
    if not reuse:
        explicit = [arg.split('=', 1)[1] for arg in make_args
                    if arg.startswith('KBUILD_BUILD_TIMESTAMP=')]
        timestamp = explicit[-1] if explicit else os.environ.get('KBUILD_BUILD_TIMESTAMP')
        if not timestamp:
            epoch = int(os.environ.get('SOURCE_DATE_EPOCH', str(int(time.time()))))
            timestamp = datetime.fromtimestamp(epoch, timezone.utc).strftime('%Y-%m-%d %H:%M:%S +0000')
        save_state(tree, {'schema': 1, 'inputs': inputs, 'sequence': selected,
                         'timestamp': timestamp, 'phase': 'reserved'})
    action = 'reuse unchanged inputs' if reuse else 'new/changed or unrecorded inputs'
    print(f'Kernel publication sequence: {selected} ({action}; published: {published})', flush=True)
    return selected


def copy_package(source, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    # Freeze validated inputs. Never hard-link build outputs that make may
    # later overwrite in place.
    checksum = LAN.sha256(source)
    shutil.copyfile(source, target)
    if LAN.sha256(target) != checksum:
        raise ValueError('APK changed during staging; finish the build first: ' + str(source))
    target.chmod(0o644)


def newest(entries, apk):
    selected = entries[0]
    for entry in entries[1:]:
        comparison = subprocess.check_output([str(apk), 'version', '--test',
            selected[1]['version'], entry[1]['version']], text=True).strip()
        if comparison == '<':
            selected = entry
        elif comparison == '=' and LAN.sha256(selected[0]) != LAN.sha256(entry[0]):
            raise ValueError('Conflicting package copies: ' + entry[1]['name'])
    return selected


def legacy_kernel_package(info):
    """Old per-generation payloads and the trackers that pinned them.

    They are already in the kernel channel and are never republished from bin/.
    """
    name = info['name']
    return '-owrt-' in name or (
        (name.startswith('kmod-') or name in ('kernel-dev-headers', 'linux-image-openwrt')) and
        any('-owrt-' in dep for dep in info.get('depends', [])))


def project(tree, work, apk, progress=None, expected=None):
    config = configuration(tree)
    sequence = int(config.get('CONFIG_OPENWRT_KERNEL_SEQUENCE', '0'))
    abi = (tree / 'staging_dir/target-x86_64_glibc/kernel.version').read_text().strip()
    if not re.fullmatch(r'(.+)~([0-9a-f]{32})-r([0-9]+)', abi) or not 1 <= sequence <= 999999:
        raise ValueError('Missing/invalid completed kernel build metadata')
    compiled = compiled_release(tree, sequence)
    if not compiled:
        raise ValueError('Compiled kernel release does not match the configured build number; '
                         'run a complete build before publishing')
    release, version, _ = compiled
    image = 'linux-image-' + release
    headers = 'linux-headers-' + release
    root = tree / 'bin/systemd'
    repos = [('target', root / 'targets/x86/64-glibc/packages')] + [
        (p.name, p) for p in sorted((root / 'packages/x86_64').iterdir())
        if p.is_dir() and any(p.glob('*.apk'))]
    inputs = [(repo, sorted(folder.glob('*.apk'))) for repo, folder in repos]
    total = sum(len(paths) for _, paths in inputs)
    examined = 0
    userspace = work / 'userspace'
    channel = work / 'kernel'
    channel.mkdir()
    candidates = {}
    kmods = {}
    support = {}
    userspace_expected = {}
    seen = set()
    for repo, paths in inputs:
        output = userspace / ('bin/systemd/targets/x86/64-glibc/packages' if repo == 'target'
                              else 'bin/systemd/packages/x86_64/' + repo)
        output.mkdir(parents=True, exist_ok=True)
        for path, metadata in LAN.dump_indexes(apk, paths):
            examined += 1
            if progress:
                progress(2 + 26 * examined / total, 'Read and stage APKs',
                         f'{examined}/{total} ({repo})')
            info = metadata['info']
            name = info['name']
            if expected is not None and path in expected:
                identity = (name, info['version'], info['arch'])
                if identity != expected[path]:
                    raise ValueError(f'Unexpected built APK identity: {path}: {identity}')
                seen.add(path)
                if not LAN.kernel_channel_package(info):
                    userspace_expected[f'{repo}/{path.name}'] = identity
            if legacy_kernel_package(info):
                if expected is not None and path in expected:
                    raise ValueError(f'Expected build APK is a legacy kernel payload: {path}')
                continue
            # Kernel packages and their metapackages form the kernel channel;
            # everything else, including the config-only kmods, is userspace
            # and no longer depends on a particular kernel.
            if name in ('kernel', 'kernel-dev-headers', 'linux-image-openwrt') or name.startswith(
                    ('linux-image-', 'linux-headers-')):
                candidates.setdefault(name, []).append((path, info))
                continue
            if expected is not None and path not in expected:
                continue
            if name.startswith('kmod-'):
                kmods.setdefault(name, []).append(info)
            copy_package(path, output / path.name)
            if name in {'apk-mbedtls', 'apk-openssl', 'ubox', 'systemd-openwrt',
                        'lan-apk-feeds', 'openwrt-kernel-upgrade', 'grub2',
                        'grub2-efi', 'grub2-editenv'}:
                support.setdefault(name, []).append((path, info))
    if expected is not None and seen != expected.keys():
        missing = sorted(str(path) for path in expected.keys() - seen)
        raise ValueError('Missing expected build APKs: ' + ', '.join(missing))
    for entries in support.values():
        path, _ = newest(entries, apk)
        copy_package(path, channel / path.name)
    requirements = {
        image: lambda info: info['version'] == version,
        'linux-image-openwrt': lambda info: (info['version'] == version and
                                              image + '=' + version in info.get('depends', [])),
        'kernel': lambda info: info['version'] == abi,
    }
    if config.get('CONFIG_PACKAGE_kernel-dev-headers') in ('y', 'm'):
        requirements[headers] = lambda info: info['version'] == version
        requirements['kernel-dev-headers'] = lambda info: (
            info['version'].startswith(f'1000.{sequence}.') and
            headers + '=' + version in info.get('depends', []))
    selected = {}
    for name, accept in requirements.items():
        valid = [p for p in candidates.get(name, []) if accept(p[1])]
        if not valid:
            raise ValueError('Missing matching kernel package: ' + name)
        if len(valid) > 1 and len({LAN.sha256(p[0]) for p in valid}) != 1:
            raise ValueError('Conflicting kernel package copies: ' + name)
        selected[name] = valid[0]
    # Every selected kmod must be this build's configuration package.
    for key, value in config.items():
        if value in ('y', 'm') and key.startswith('CONFIG_PACKAGE_kmod-'):
            name = key.removeprefix('CONFIG_PACKAGE_')
            if not any(info['version'].startswith(f'1000.{sequence}.') and
                       any(re.match(r'linux-image-openwrt(?:[<>=~]|$)', dep)
                           for dep in info.get('depends', []))
                       for info in kmods.get(name, [])):
                raise ValueError('Missing kmod configuration package for this kernel build: ' + name)
    for name, (path, info) in selected.items():
        copy_package(path, channel / path.name)
    if expected is not None:
        return userspace, channel, abi, release, userspace_expected
    return userspace, channel, abi, release


def verify_artifacts(bundle):
    """Validate an independent, complete saved projection before reuse."""
    bundle = Path(bundle).resolve()
    manifest = json.loads((bundle / 'manifest.json').read_text())
    if manifest.get('schema') != 1 or not manifest.get('files'):
        raise ValueError('Invalid artifact manifest')
    actual = {str(p.relative_to(bundle)) for p in bundle.rglob('*') if p.is_file()
              and p != bundle / 'manifest.json'}
    if actual != set(manifest['files']):
        raise ValueError('Artifact file set changed')
    for name, digest in manifest['files'].items():
        path = bundle / name
        if path.is_symlink() or not path.resolve().is_relative_to(bundle) or LAN.sha256(path) != digest:
            raise ValueError('Saved artifact changed: ' + name)
    return manifest


def capture_artifacts(tree, bundle, include_iso=False, expected=None):
    """Called while the checkout build lock is held; never copy signing keys."""
    bundle = Path(bundle)
    bundle.mkdir(mode=0o700, parents=True, exist_ok=False)
    projection = project(tree, bundle, TREE / 'staging_dir/host/bin/apk', expected=expected)
    _, _, abi, release = projection[:4]
    image = tree / 'bin/systemd/targets/x86/64-glibc' / VM_IMAGE
    copy_package(image, bundle / 'image.img.gz')
    if include_iso:
        copy_package(image.with_name(VM_ISO), bundle / 'installer.iso')
    copy_package(tree / '.config', bundle / 'build.config')
    copy_package(state_path(tree), bundle / 'kernel-inputs.json')
    manifest = {'schema': 1, 'abi': abi, 'release': release,
                'public_key_sha256': LAN.sha256(TREE / 'public-key.pem'),
                'files': {str(p.relative_to(bundle)): LAN.sha256(p)
                          for p in sorted(bundle.rglob('*')) if p.is_file()}}
    if expected is not None:
        manifest['expected_userspace'] = projection[4]
    for name in manifest['files']:
        (bundle / name).chmod(0o444)
    (bundle / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    verify_artifacts(bundle)
    return manifest


def publish(tree, data, dry_run=False, progress=None, artifacts=None, expected=None):
    apk = TREE / 'staging_dir/host/bin/apk'
    if progress:
        progress(0, 'Wait for publication lock')
    if artifacts is None and configuration(tree).get('CONFIG_OPENWRT_KERNEL_UPGRADE') != 'y':
        if progress:
            progress(5, 'Prepare userspace feeds', 'signatures and ABI checks')
        result = LAN.publish(argparse.Namespace(source_root=tree, kernel=data.get('kernel'),
            destination=data['destination'], base_url=data['base_url'], incremental=True,
            dry_run=dry_run, kernel_upgrade_view=False))
        if progress:
            progress(100, 'Dry run complete' if dry_run else 'Publication complete')
        return result
    destination = data['destination']
    destination.mkdir(parents=True, exist_ok=True)
    with (destination / '.upgrade-publish.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        result = publish_locked(tree, data, apk, dry_run, progress, artifacts, expected)
    if progress:
        progress(100, 'Dry run complete' if dry_run else 'Publication complete')
    return result


def publish_locked(tree, data, apk, dry_run, progress=None, artifacts=None, expected=None):
    destination = data['destination']
    prepared = []
    with tempfile.TemporaryDirectory(prefix='.build-publish-', dir=destination) as temporary:
        if progress:
            progress(2, 'Read and stage APKs')
        userspace_expected = None
        if expected is not None:
            userspace, channel, abi, generation, userspace_expected = project(
                tree, Path(temporary), apk, progress, expected=expected)
        elif artifacts is None:
            userspace, channel, abi, generation = project(tree, Path(temporary), apk, progress)
        else:
            artifacts = Path(artifacts).resolve()
            manifest = verify_artifacts(artifacts)
            if manifest['public_key_sha256'] != LAN.sha256(TREE / 'public-key.pem'):
                raise ValueError('Artifact signing key changed')
            # Copy again into private publication staging so later edits cannot
            # substitute inputs between verification and the solver simulations.
            for folder in ('userspace', 'kernel'):
                shutil.copytree(artifacts / folder, Path(temporary) / folder)
            staged_names = {str(path.relative_to(temporary))
                            for path in Path(temporary).rglob('*') if path.is_file()}
            if staged_names != {name for name in manifest['files']
                                if name.startswith(('userspace/', 'kernel/'))}:
                raise ValueError('Artifact file set changed during publication staging')
            for name, digest in manifest['files'].items():
                if name.startswith(('userspace/', 'kernel/')) and LAN.sha256(Path(temporary) / name) != digest:
                    raise ValueError('Artifact changed during publication staging: ' + name)
            userspace, channel = Path(temporary) / 'userspace', Path(temporary) / 'kernel'
            abi, generation = manifest['abi'], manifest['release']
            userspace_expected = manifest.get('expected_userspace')
        if data.get('kernel') and data['kernel'] != abi:
            raise ValueError('Requested ABI differs from compiled generation')
        if progress:
            progress(29, 'Read router baseline and check trackers')
        # The only complete router scan before promotion: the simulation is
        # bound to it, and the promotion recheck below must still match it.
        baseline = GUARD.readiness(destination,
            (metadata['info'] for _, metadata in LAN.dump_indexes(apk, sorted(channel.glob('*.apk')))), abi,
            full=True)
        args = argparse.Namespace(source_root=userspace, kernel=abi, destination=destination,
            base_url=data['base_url'], incremental=True, dry_run=False, kernel_upgrade_view=True,
            stage_only=True, expected=userspace_expected, frozen_artifacts=artifacts is not None)
        try:
            if progress:
                progress(30, 'Prepare userspace feeds', 'signatures and ABI checks')
            lan = LAN.publish(args)
            prepared.append(lan)
            if progress:
                progress(45, 'Prepare kernel feed', 'signatures and generation checks')
            kernel = KERNEL.publish(channel, destination, apk, TREE / 'private-key.pem', TREE,
                                    stage_only=True)
            prepared.append(kernel)
            def preflight_progress(percent, phase):
                progress(55 + percent * 0.25, phase)
            # Reuse the readiness scan, and leave the single post-simulation
            # rescan to the promotion check below, which compares the same
            # receipt baseline after the snapshots are rehashed.
            receipt = GUARD.preflight(destination, data['base_url'], lan, kernel,
                                      baseline=baseline, recheck=False,
                                      progress=preflight_progress if progress else None)
            if userspace_expected:
                published_files = receipt['stages']['userspace']['files']
                for path, digest in lan.pop('expected_digests').items():
                    if published_files.get(path) != digest:
                        raise ValueError(f'Expected rolling APK bytes differ in prepared snapshot: {path}')
            # Recheck BOTH before moving either alias. These are the exact
            # staged snapshots, never a second projection of mutable bin/.
            for name, result in (('userspace', lan), ('kernel', kernel)):
                if progress:
                    progress(82 if name == 'userspace' else 86, 'Verify prepared ' + name + ' snapshot')
                GUARD.authorize(destination, result, receipt, name)
                GUARD.check_alias(result)
            selected_policy = GUARD.policy(destination)
            if progress and selected_policy:
                progress(90, 'Recheck router before promotion')
            if selected_policy and not GUARD.same_baseline(
                    receipt['baseline'], GUARD.capture(selected_policy['ssh_target'])):
                raise ValueError('Router baseline changed before release promotion')
            if not dry_run:
                if progress:
                    progress(94, 'Save publication receipt')
                receipts = destination / 'upgrade-receipts'
                receipts.mkdir(exist_ok=True)
                save_receipt = receipts / (str(time.time_ns()) + '.json')
                with open(save_receipt, 'x', opener=lambda path, flags: os.open(path, flags, 0o600)) as stream:
                    stream.write(json.dumps(receipt, sort_keys=True, indent=2) + '\n')
                    stream.flush()
                    os.fsync(stream.fileno())
                try:
                    if progress:
                        progress(96, 'Promote userspace feed')
                    lan = LAN.promote(lan, destination, receipt)
                    if progress:
                        progress(98, 'Promote kernel feed')
                    kernel = KERNEL.promote(kernel, destination, receipt)
                except BaseException:
                    # The kernel pointer is the commit boundary. An interrupt
                    # after it moved must leave the matching userspace exposed.
                    if (prepared[1]['status'] == 'unchanged' or
                            Path(prepared[1]['alias']).resolve() != Path(prepared[1]['snapshot']).resolve()):
                        LAN.restore_alias(prepared[0])
                    raise
            if progress:
                progress(99, 'Clean up staging snapshots')
            return {'userspace': {**lan, 'status': 'dry-run' if dry_run and lan['status'] != 'unchanged' else lan['status']},
                    'kernel': {**kernel, 'status': 'dry-run' if dry_run and kernel['status'] != 'unchanged' else kernel['status']},
                    'generation': generation, 'upgrade_preflight': receipt}
        finally:
            for result in prepared:
                path = Path(result['snapshot'])
                alias = Path(result['alias'])
                if result['status'] == 'prepared' and (not alias.exists() or alias.resolve() != path.resolve()):
                    shutil.rmtree(path, ignore_errors=True)


def make_options(make_args):
    """Keep job and verbosity options for a targeted rebuild."""
    options = []
    for index, argument in enumerate(make_args):
        if (argument.startswith(('-j', '--jobs', 'V=')) or
                (argument.isdigit() and index and make_args[index - 1] in ('-j', '--jobs'))):
            options.append(argument)
    if not any(option.startswith(('-j', '--jobs')) for option in options):
        options.insert(0, f'-j{os.cpu_count() or 1}')
    return options


def _maybe_cold_verify_entries(tree, entries, *, abi_store=None, cold_runner=None,
                               evidence_dir=None, attempted_recipes=None,
                               allow_high_cost=False, authorized_cold_recipes=()):
    """Run at most one isolated cold rebuild per recipe for reviewable ELF candidates."""
    attempted = attempted_recipes if attempted_recipes is not None else set()
    recipes = ALLOCATE.recipe_versions(tree) if (tree / 'tmp/.packageinfo').is_file() else {}
    by_recipe = {}
    for idx, entry in enumerate(entries):
        decision = entry.get('decision') or {}
        if decision.get('action') != LAN.DIAGNOSE.ACTION_REVIEW:
            continue
        if not entry.get('old_path') or not entry.get('new_path'):
            continue
        if not Path(entry['old_path']).is_file() or not Path(entry['new_path']).is_file():
            continue
        name = entry.get('name')
        if not name or name not in recipes:
            continue
        makefile = recipes[name][1]
        if makefile in attempted:
            continue
        by_recipe.setdefault(makefile, []).append((idx, entry))

    if not by_recipe:
        return entries

    updated = list(entries)
    pub_key = tree / 'public-key.pem'
    for makefile, group in sorted(by_recipe.items()):
        attempted.add(makefile)
        candidates = {e['name']: Path(e['new_path']) for _, e in group}
        if pub_key.is_file():
            with tempfile.TemporaryDirectory(prefix='cold-verify-keys-') as keys_tmp:
                shutil.copyfile(pub_key, Path(keys_tmp) / 'public-key.pem')
                cold = COLD_VERIFY.cold_rebuild_recipe(
                    tree, makefile, candidates,
                    apk=TREE / 'staging_dir/host/bin/apk',
                    keys_dir=Path(keys_tmp),
                    evidence_dir=evidence_dir,
                    runner=cold_runner,
                    allow_high_cost=allow_high_cost,
                    authorized_recipes=authorized_cold_recipes)
                for idx, entry in group:
                    pkg_ev = cold.get('packages', {}).get(entry['name'])
                    if not pkg_ev:
                        continue
                    combined_ev = {
                        **pkg_ev,
                        'input_sha256': cold.get('input_sha256'),
                        'inputs_stable': cold.get('inputs_stable'),
                        'cold_build_verified': cold.get('cold_build_verified', False),
                    }
                    new_entry, _ = ALLOCATE.classify(
                        entry['old_path'], entry['new_path'], entry['path'],
                        apk=TREE / 'staging_dir/host/bin/apk',
                        keys_dir=Path(keys_tmp),
                        abi_store=abi_store,
                        cold_evidence=combined_ev)
                    if entry.get('snapshot'):
                        new_entry['snapshot'] = entry['snapshot']
                    updated[idx] = new_entry
    return updated


def publish_allocating(tree, data, publish_once, make_args=(), allocate=False, rebuild=None,
                       dry_run=False, approvals=None, cold_rebuild=False, abi_store=None,
                       cold_runner=None, evidence_dir=None, allow_high_cost=False,
                       authorized_cold_recipes=()):
    """Publish; on same-version rebuilds optionally allocate releases, rebuild, retry."""
    attempted_recipes = set()
    for round_number in range(ALLOCATION_ROUNDS + 1):
        try:
            return publish_once()
        except LAN.SameVersionRebuildError as error:
            if not allocate or round_number == ALLOCATION_ROUNDS:
                raise
            entries = error.entries
            if cold_rebuild and not dry_run:
                entries = _maybe_cold_verify_entries(
                    tree, entries, abi_store=abi_store, cold_runner=cold_runner,
                    evidence_dir=evidence_dir, attempted_recipes=attempted_recipes,
                    allow_high_cost=allow_high_cost,
                    authorized_cold_recipes=authorized_cold_recipes)
            plan_kwargs = {}
            if approvals is not None:
                plan_kwargs['approvals'] = approvals
            if getattr(error, 'snapshot', None):
                plan_kwargs['snapshot'] = error.snapshot
            allocations = ALLOCATE.plan(tree, data['destination'], entries, **plan_kwargs)
            if dry_run:
                print('Dry run: planned release allocations (no ledger writes or rebuilds):\n' +
                      ALLOCATE.describe(allocations), file=sys.stderr)
                return {
                    'status': 'dry-run-conflict',
                    'planned_allocations': allocations,
                    'entries': error.entries,
                }
            print('Allocating new releases for same-version rebuilds:\n' +
                  ALLOCATE.describe(allocations), file=sys.stderr)
            apply_kwargs = {}
            if getattr(error, 'snapshot', None):
                apply_kwargs['destination'] = data['destination']
            ALLOCATE.apply(tree, allocations, **apply_kwargs)
            if rebuild is None:
                targets = ALLOCATE.rebuild_targets(allocations)
                print('Rebuilding: ' + ' '.join(targets), file=sys.stderr)
                run_make(tree, [*make_options(list(make_args)), *targets])
            else:
                rebuild()
            pub_key = tree / 'public-key.pem'
            if pub_key.is_file() and any(a.get('new_path') and Path(a['new_path']).is_file()
                                         for a in allocations):
                with tempfile.TemporaryDirectory(prefix='verify-rebuilt-keys-') as keys_tmp:
                    shutil.copyfile(pub_key, Path(keys_tmp) / 'public-key.pem')
                    ALLOCATE.verify_rebuilt_packages(
                        tree, allocations, apk=TREE / 'staging_dir/host/bin/apk',
                        keys_dir=Path(keys_tmp))


_ACTIVE_LOCK = None


def run_make(tree, arguments):
    # Package scripts/lists and temporary roots inherit the build's umask.
    # Keep their recorded ACLs stable across shells and validation checkouts.
    env = None
    pass_fds = ()
    if _ACTIVE_LOCK is not None:
        fd, ident = _ACTIVE_LOCK
        os.set_inheritable(fd, True)
        env = {**os.environ, CHECKOUT_LOCK.ENV_FD: str(fd), CHECKOUT_LOCK.ENV_ID: ident}
        pass_fds = (fd,)
    subprocess.run(['make', *arguments], cwd=tree, check=True, umask=0o022,
                   env=env, pass_fds=pass_fds)


VM_IMAGE = 'openwrt-x86-64-generic-squashfs-combined-efi.img.gz'
VM_ISO = 'openwrt-x86-64-generic-installer.iso'


def read_apk_inventory(tree, directory):
    """Read the APK identities evaluated by this invocation of Make."""
    expected = {}
    for fragment in sorted(Path(directory).rglob('*')):
        if not fragment.is_file():
            continue
        filename, name, version, arch = fragment.read_text().rstrip('\n').split('\t')
        path = Path(filename)
        identity = (name, version, arch)
        if (not path.is_relative_to(tree / 'bin/systemd') or not path.is_file()
                or expected.setdefault(path, identity) != identity):
            raise ValueError(f'Missing or conflicting build APK output: {path}')
    if not expected:
        raise ValueError('Build did not report any APKs')
    return expected


def rolling_inventory(tree, arguments):
    with tempfile.TemporaryDirectory(prefix='rolling-apks-', dir=tree / 'tmp') as directory:
        run_make(tree, [*arguments, f'ROLLING_APK_DIR={directory}', 'rolling-packages'])
        return read_apk_inventory(tree, directory)


def build(tree, make_args, publish_after=True, artifact_directory=None, lock_fd=None,
          allocate_rebuilds=False, rolling=False, dry_run=False, vm_artifacts=None):
    if dry_run and (not rolling or not publish_after or allocate_rebuilds):
        raise ValueError('Build --dry-run requires --rolling without automatic release allocation')
    if vm_artifacts is not None and (rolling or publish_after or artifact_directory is not None):
        raise ValueError('--vm-artifacts requires a full build-only invocation')
    for argument in make_args:
        if argument in ('-n', '--just-print', '--dry-run', '--recon', '-q', '--question', '-t', '--touch'):
            raise ValueError('A make preview/touch cannot be used for build-and-publish')
        if argument.startswith(('-C', '--directory', 'TOPDIR=')):
            raise ValueError('Build-and-publish must build this checkout')
    data = settings(tree)
    # Serialize the full build against this checkout using a lock outside tmp/
    # so dirclean cannot replace its inode.
    lockdir = tree / 'tmp'
    lockdir.mkdir(exist_ok=True)
    global _ACTIVE_LOCK
    cfg = configuration(tree)
    extra_dirs = [cfg['CONFIG_BINARY_FOLDER'].strip('"')] if cfg.get('CONFIG_BINARY_FOLDER', '').strip('"') else []
    prev_lock = _ACTIVE_LOCK
    with CHECKOUT_LOCK.acquire_checkout_lock(tree, lock_fd=lock_fd, extra_dirs=extra_dirs) as (held_fd, ident, _):
        _ACTIVE_LOCK = (held_fd, ident)
        try:
            return _build_locked(tree, make_args, data, lockdir, publish_after, artifact_directory,
                                 allocate_rebuilds, rolling, dry_run, vm_artifacts)
        finally:
            _ACTIVE_LOCK = prev_lock


def _build_locked(tree, make_args, data, lockdir, publish_after, artifact_directory,
                  allocate_rebuilds, rolling, dry_run, vm_artifacts):
    if True:
        targets = [arg for arg in make_args if not arg.startswith('-') and '=' not in arg
                   and not arg.isdigit()]
        enabled = configuration(tree).get('CONFIG_OPENWRT_KERNEL_UPGRADE') == 'y'
        full = not targets or targets == ['world']
        if rolling and (targets or not enabled or any(
                arg.startswith(('CONFIG_', 'ROLLING_APK_DIR=', 'VM_MEDIA_DIR=')) for arg in make_args)):
            raise ValueError('--rolling requires the configured kernel-upgrade target and no make targets or config overrides')
        if vm_artifacts is not None:
            if not full or not enabled or any(
                    arg.startswith(('CONFIG_', 'ROLLING_APK_DIR=', 'VM_MEDIA_DIR=')) for arg in make_args):
                raise ValueError('--vm-artifacts requires the configured full build')
            config = configuration(tree)
            if any(config.get(key) != 'y' for key in (
                    'CONFIG_INSTALLER_ISO_IMAGES', 'CONFIG_GRUB_EFI_IMAGES', 'CONFIG_TARGET_IMAGES_GZIP')):
                raise ValueError('--vm-artifacts requires the configured installer ISO and compressed EFI image')
            if vm_artifacts.exists() or vm_artifacts.is_symlink():
                raise ValueError(f'Artifact directory already exists: {vm_artifacts}')
        plan = None
        if full or (enabled and state_path(tree).exists()):
            run_make(tree, ['prepare-tmpinfo'])
        if enabled and full:
            prepare_sequence(tree, data['destination'], make_args)
            plan = json.loads(state_path(tree).read_text())
        elif enabled and state_path(tree).exists():
            plan = json.loads(state_path(tree).read_text())
            if not INPUTS.same_inputs(plan['inputs'], INPUTS.fingerprint(tree, configuration(tree), make_args)):
                raise ValueError('Kernel inputs changed; run a complete build to reserve a new generation')
        arguments = list(make_args)
        if full:
            migrations = retained_migration_options(tree, make_args, data['destination'])
            if migrations:
                print('Including retained ELF migration packages: ' + ' '.join(migrations), file=sys.stderr)
                arguments.extend(migrations)
        if plan and not any(arg.startswith('KBUILD_BUILD_TIMESTAMP=') for arg in arguments):
            arguments.append('KBUILD_BUILD_TIMESTAMP=' + plan['timestamp'])
        expected = None
        if rolling:
            expected = rolling_inventory(tree, arguments)
        elif vm_artifacts is not None:
            with tempfile.TemporaryDirectory(prefix='vm-media-', dir=lockdir) as directory:
                media = Path(directory) / 'media'
                inventory = Path(directory) / 'inventory'
                media.mkdir()
                inventory.mkdir()
                run_make(tree, [*arguments, f'VM_MEDIA_DIR={media}', f'ROLLING_APK_DIR={inventory}'])
                if any(not (media / name).is_file() for name in (VM_IMAGE, VM_ISO)):
                    raise ValueError('The build did not produce both required VM media files')
                expected = read_apk_inventory(tree, inventory)
        else:
            run_make(tree, arguments)
        if plan:
            after = INPUTS.fingerprint(tree, configuration(tree), make_args)
            if after['source'] != plan['inputs']['source']:
                raise ValueError('Kernel source/configuration changed during build; retry before publishing')
            # A newly built toolchain may first appear during a fresh build.
            # Replacing tools under an existing published generation is refused.
            manifest = data['destination'] / 'public/kernel-upgrades/manifest.json'
            published = json.loads(manifest.read_text())['sequence'] if manifest.exists() else 0
            if not INPUTS.same_tools(plan['inputs'], after) and plan['sequence'] <= published:
                raise ValueError('Kernel build tools changed; retry with a new generation')
            plan.update(inputs=after, phase='built')
            save_state(tree, plan)
        if artifact_directory is not None:
            capture_artifacts(tree, artifact_directory)
        if vm_artifacts is not None:
            capture_artifacts(tree, vm_artifacts, include_iso=True, expected=expected)
        if rolling and publish_after:
            def rebuild_rolling():
                nonlocal expected
                expected = rolling_inventory(tree, arguments)
                after = INPUTS.fingerprint(tree, configuration(tree), make_args)
                if not INPUTS.same_inputs(plan['inputs'], after):
                    raise ValueError('Kernel inputs changed during allocation retry')

            with Progress() as progress:
                return publish_allocating(tree, data,
                    lambda: publish(tree, data, dry_run, progress, expected=expected),
                    make_args, allocate_rebuilds, rebuild=rebuild_rolling)
        if rolling:
            for path, metadata in LAN.dump_indexes(TREE / 'staging_dir/host/bin/apk', sorted(expected)):
                info = metadata['info']
                if (info['name'], info['version'], info['arch']) != expected[path]:
                    raise ValueError(f'Unexpected built APK identity: {path}')
        if publish_after:
            return publish_allocating(tree, data, lambda: publish(tree, data), make_args,
                                      allocate_rebuilds)
        result = {'status': 'built', 'tree': str(tree),
                  'sequence': plan['sequence'] if plan else None}
        if rolling:
            result['expected_apks'] = len(expected)
        return result


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('build', 'build-only'):
        parser = argparse.ArgumentParser(add_help=False, allow_abbrev=False)
        parser.add_argument('--allocate-rebuilds', action='store_true')
        parser.add_argument('--rolling', action='store_true')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--vm-artifacts', type=Path)
        options, make_args = parser.parse_known_args(sys.argv[2:])
        result = build(TREE, make_args, publish_after=sys.argv[1] == 'build',
                       allocate_rebuilds=options.allocate_rebuilds, rolling=options.rolling,
                       dry_run=options.dry_run, vm_artifacts=options.vm_artifacts)
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--config', type=Path, default=TREE / 'configs/lan-apk-feeds.json')
        parser.add_argument('--source-root', type=Path, default=TREE)
        parser.add_argument('--destination', type=Path)
        parser.add_argument('--base-url')
        parser.add_argument('--kernel')
        parser.add_argument('--incremental', action='store_true', help='Compatibility; always incremental')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--no-progress', action='store_true', help='Disable progress on stderr')
        parser.add_argument('--artifacts', type=Path, help='Publish a verified frozen artifact bundle')
        parser.add_argument('--allocate-rebuilds', action='store_true',
                            help='Allocate ELF rebuild ledger releases for same-version rebuilds, '
                                 'rebuild those packages and retry')
        parser.add_argument('--approval', type=Path,
                            help='JSON file with digest-bound review approval(s)')
        parser.add_argument('--cold-rebuild', action='store_true',
                            help='Run at most one isolated cold rebuild per conflicting recipe (Phase 2b)')
        parser.add_argument('--allow-high-cost-cold-rebuild', action='store_true',
                            help='Explicitly authorize cold rebuild of high-cost recipes (Qt/LLVM/Rust)')
        parser.add_argument('--authorize-cold-recipe', action='append', default=[],
                            help='Explicitly authorize one high-cost recipe/package for cold rebuild (repeatable)')
        parser.add_argument('--abi-store', type=Path,
                            help='Out-of-APK type ABI evidence directory (Phase 2a)')
        args = parser.parse_args()
        if args.artifacts and args.allocate_rebuilds:
            parser.error('Frozen artifact publication cannot allocate and rebuild packages')
        approvals = ALLOCATE.load_approvals(args.approval) if args.approval else None
        data = json.loads(args.config.read_text())
        data.update({k: v for k, v in vars(args).items()
                     if k in ('destination', 'base_url', 'kernel') and v is not None})
        data['destination'] = Path(data['destination']).resolve()
        tree = args.source_root.resolve()
        lockdir = tree / 'tmp'
        lockdir.mkdir(exist_ok=True)
        global _ACTIVE_LOCK
        prev_lock = _ACTIVE_LOCK
        with Progress(enabled=not args.no_progress) as progress:
            progress(0, 'Wait for build/publication lock')
            with CHECKOUT_LOCK.acquire_checkout_lock(tree) as (held_fd, ident, _):
                _ACTIVE_LOCK = (held_fd, ident)
                try:
                    result = publish_allocating(tree, data,
                        lambda: publish(tree, data, args.dry_run, progress, artifacts=args.artifacts),
                        allocate=args.allocate_rebuilds, dry_run=args.dry_run,
                        approvals=approvals, cold_rebuild=args.cold_rebuild,
                        abi_store=args.abi_store,
                        allow_high_cost=args.allow_high_cost_cold_rebuild,
                        authorized_cold_recipes=args.authorize_cold_recipe)
                finally:
                    _ACTIVE_LOCK = prev_lock
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Build/publication failed: ' + str(error), file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError) and error.stderr:
            print(error.stderr.decode(errors='replace') if isinstance(error.stderr, bytes)
                  else error.stderr, file=sys.stderr)
        sys.exit(1)
