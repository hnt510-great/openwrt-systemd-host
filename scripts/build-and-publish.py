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


def project(tree, work, apk, progress=None):
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
            if legacy_kernel_package(info):
                continue
            # Kernel packages and their metapackages form the kernel channel;
            # everything else, including the config-only kmods, is userspace
            # and no longer depends on a particular kernel.
            if name in ('kernel', 'kernel-dev-headers', 'linux-image-openwrt') or name.startswith(
                    ('linux-image-', 'linux-headers-')):
                candidates.setdefault(name, []).append((path, info))
                continue
            if name.startswith('kmod-'):
                kmods.setdefault(name, []).append(info)
            copy_package(path, output / path.name)
            if name in {'apk-mbedtls', 'apk-openssl', 'ubox', 'systemd-openwrt',
                        'lan-apk-feeds', 'openwrt-kernel-upgrade', 'grub2',
                        'grub2-efi', 'grub2-editenv'}:
                support.setdefault(name, []).append((path, info))
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


def capture_artifacts(tree, bundle):
    """Called while the checkout build lock is held; never copy signing keys."""
    bundle = Path(bundle)
    bundle.mkdir(mode=0o700, parents=True, exist_ok=False)
    userspace, channel, abi, release = project(tree, bundle, TREE / 'staging_dir/host/bin/apk')
    image = tree / 'bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz'
    copy_package(image, bundle / 'image.img.gz')
    copy_package(tree / '.config', bundle / 'build.config')
    copy_package(state_path(tree), bundle / 'kernel-inputs.json')
    manifest = {'schema': 1, 'abi': abi, 'release': release,
                'public_key_sha256': LAN.sha256(TREE / 'public-key.pem'),
                'files': {str(p.relative_to(bundle)): LAN.sha256(p)
                          for p in sorted(bundle.rglob('*')) if p.is_file()}}
    for name in manifest['files']:
        (bundle / name).chmod(0o444)
    (bundle / 'manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')
    verify_artifacts(bundle)
    return manifest


def publish(tree, data, dry_run=False, progress=None, artifacts=None):
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
        result = publish_locked(tree, data, apk, dry_run, progress, artifacts)
    if progress:
        progress(100, 'Dry run complete' if dry_run else 'Publication complete')
    return result


def publish_locked(tree, data, apk, dry_run, progress=None, artifacts=None):
    destination = data['destination']
    prepared = []
    with tempfile.TemporaryDirectory(prefix='.build-publish-', dir=destination) as temporary:
        if progress:
            progress(2, 'Read and stage APKs')
        if artifacts is None:
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
            for name, digest in manifest['files'].items():
                if name.startswith(('userspace/', 'kernel/')) and LAN.sha256(Path(temporary) / name) != digest:
                    raise ValueError('Artifact changed during publication staging: ' + name)
            userspace, channel = Path(temporary) / 'userspace', Path(temporary) / 'kernel'
            abi, generation = manifest['abi'], manifest['release']
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
            stage_only=True)
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


def publish_allocating(tree, data, publish_once, make_args=(), allocate=False):
    """Publish; on same-version rebuilds optionally allocate releases, rebuild, retry."""
    for round_number in range(ALLOCATION_ROUNDS + 1):
        try:
            return publish_once()
        except LAN.SameVersionRebuildError as error:
            if not allocate or round_number == ALLOCATION_ROUNDS:
                raise
            allocations = ALLOCATE.plan(tree, data['destination'], error.entries)
            print('Allocating new releases for same-version rebuilds:\n' +
                  ALLOCATE.describe(allocations), file=sys.stderr)
            ALLOCATE.apply(tree, allocations)
            targets = ALLOCATE.rebuild_targets(allocations)
            print('Rebuilding: ' + ' '.join(targets), file=sys.stderr)
            run_make(tree, [*make_options(list(make_args)), *targets])


def run_make(tree, arguments):
    # Package scripts/lists and temporary roots inherit the build's umask.
    # Keep their recorded ACLs stable across shells and validation checkouts.
    subprocess.run(['make', *arguments], cwd=tree, check=True, umask=0o022)


def build(tree, make_args, publish_after=True, artifact_directory=None, lock_fd=None,
          allocate_rebuilds=False):
    for argument in make_args:
        if argument in ('-n', '--just-print', '--dry-run', '--recon', '-q', '--question', '-t', '--touch'):
            raise ValueError('A make preview/touch cannot be used for build-and-publish')
        if argument.startswith(('-C', '--directory', 'TOPDIR=')):
            raise ValueError('Build-and-publish must build this checkout')
    data = settings(tree)
    # Serialize the full build against this checkout, not just the final index.
    lockdir = tree / 'tmp'
    lockdir.mkdir(exist_ok=True)
    with (lockdir / '.build-and-publish.lock').open('a') as lock:
        if lock_fd is None:
            fcntl.flock(lock, fcntl.LOCK_EX)
        elif (os.fstat(lock_fd).st_dev, os.fstat(lock_fd).st_ino) != (os.fstat(lock.fileno()).st_dev, os.fstat(lock.fileno()).st_ino):
            raise ValueError('Inherited build lock does not belong to this checkout')
        targets = [arg for arg in make_args if not arg.startswith('-') and '=' not in arg
                   and not arg.isdigit()]
        enabled = configuration(tree).get('CONFIG_OPENWRT_KERNEL_UPGRADE') == 'y'
        full = not targets or targets == ['world']
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
        if publish_after:
            return publish_allocating(tree, data, lambda: publish(tree, data), make_args,
                                      allocate_rebuilds)
        return {'status': 'built', 'tree': str(tree),
                'sequence': plan['sequence'] if plan else None}


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('build', 'build-only'):
        make_args = [arg for arg in sys.argv[2:] if arg != '--allocate-rebuilds']
        result = build(TREE, make_args, publish_after=sys.argv[1] == 'build',
                       allocate_rebuilds='--allocate-rebuilds' in sys.argv[2:])
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
        parser.add_argument('--allocate-rebuilds', action='store_true',
                            help='Allocate ELF rebuild ledger releases for same-version rebuilds, '
                                 'rebuild those packages and retry')
        args = parser.parse_args()
        data = json.loads(args.config.read_text())
        data.update({k: v for k, v in vars(args).items()
                     if k in ('destination', 'base_url', 'kernel') and v is not None})
        data['destination'] = Path(data['destination']).resolve()
        tree = args.source_root.resolve()
        lockdir = tree / 'tmp'
        lockdir.mkdir(exist_ok=True)
        with Progress(enabled=not args.no_progress) as progress, \
                (lockdir / '.build-and-publish.lock').open('a') as lock:
            progress(0, 'Wait for build/publication lock')
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = publish_allocating(tree, data,
                lambda: publish(tree, data, args.dry_run, progress), allocate=args.allocate_rebuilds)
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
