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


def configuration(tree):
    path = tree / '.config'
    if not path.exists():
        return {}
    return dict(line.split('=', 1) for line in path.read_text().splitlines()
                if line.startswith('CONFIG_') and '=' in line)


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
    reuse = (previous and previous.get('schema') == 1 and previous.get('inputs') == inputs
             and current <= previous['sequence'] and previous['sequence'] >= published)
    selected = previous['sequence'] if reuse else max(current, published + 1)
    output = tree / 'bin/systemd/targets/x86/64-glibc/packages'
    # Reuse partial immutable outputs only with the same proven inputs/time.
    # Unknown or changed inputs must never overwrite an existing generation.
    while not reuse and selected <= 999999 and any(output.glob(f'linux-image-*-g{selected}-*.apk')):
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


def project(tree, work, apk):
    config = configuration(tree)
    sequence = int(config.get('CONFIG_OPENWRT_KERNEL_SEQUENCE', '0'))
    abi = (tree / 'staging_dir/target-x86_64_glibc/kernel.version').read_text().strip()
    match = re.fullmatch(r'(.+)~([0-9a-f]{32})-r([0-9]+)', abi)
    if not match or not 1 <= sequence <= 999999:
        raise ValueError('Missing/invalid completed kernel build metadata')
    generation = (match[1].replace('_rc', '-rc') + '-owrt-' + match[2] +
                  '-r' + match[3] + '-g' + str(sequence))
    releases = list((tree / 'build_dir/target-x86_64_glibc/linux-x86_64').glob(
        'linux-*/include/config/kernel.release'))
    if not any(path.read_text().strip() == generation for path in releases):
        raise ValueError('Compiled kernel release does not match configured generation; '
                         'run a complete build before publishing')
    image = 'linux-image-' + generation
    root = tree / 'bin/systemd'
    repos = [('target', root / 'targets/x86/64-glibc/packages')] + [
        (p.name, p) for p in sorted((root / 'packages/x86_64').iterdir())
        if p.is_dir() and any(p.glob('*.apk'))]
    userspace = work / 'userspace'
    channel = work / 'kernel'
    channel.mkdir()
    candidates = {}
    payloads = {}
    support = {}
    for repo, folder in repos:
        output = userspace / ('bin/systemd/targets/x86/64-glibc/packages' if repo == 'target'
                              else 'bin/systemd/packages/x86_64/' + repo)
        output.mkdir(parents=True, exist_ok=True)
        for path in sorted(folder.glob('*.apk')):
            info = json.loads(subprocess.check_output(
                [str(apk), 'adbdump', '--format', 'json', str(path)]))['info']
            name = info['name']
            # All kernel packages, including stale logical trackers left in
            # bin/, are selected separately. Userspace remains ABI-specific.
            family = name in ('kernel', 'kernel-dev-headers') or name.startswith(
                ('kmod-', 'linux-image-', 'kernel-dev-headers-'))
            if family:
                if '-owrt-' in name:
                    if name.endswith('-' + generation):
                        if name in payloads and LAN.sha256(path) != LAN.sha256(payloads[name][0]):
                            raise ValueError('Conflicting generation payload copies: ' + name)
                        payloads[name] = (path, info)
                else:
                    candidates.setdefault(name, []).append((path, info))
                continue
            copy_package(path, output / path.name)
            if name in {'apk-mbedtls', 'apk-openssl', 'ubox', 'systemd-openwrt',
                        'lan-apk-feeds', 'openwrt-kernel-upgrade', 'grub2',
                        'grub2-efi', 'grub2-editenv'}:
                support.setdefault(name, []).append((path, info))
    for entries in support.values():
        path, _ = newest(entries, apk)
        copy_package(path, channel / path.name)
    if image not in payloads or payloads[image][1]['version'] != abi:
        raise ValueError('Matching immutable kernel image is missing')
    selected = dict(payloads)
    required = {name.removeprefix('CONFIG_PACKAGE_') for name, value in config.items()
                if value in ('y', 'm') and (name.startswith('CONFIG_PACKAGE_kmod-') or
                                          name == 'CONFIG_PACKAGE_kernel-dev-headers')}
    required.update(name.removesuffix('-' + generation) for name in payloads if name != image)
    required.update(('kernel', 'linux-image-openwrt'))
    for name in sorted(required):
        if name == 'kernel':
            valid = [p for p in candidates.get(name, []) if p[1]['version'] == abi]
        elif name == 'linux-image-openwrt':
            valid = [p for p in candidates.get(name, []) if p[1]['version'] == f'1-r{sequence}'
                     and image + '=' + abi in p[1].get('depends', [])
                     and 'kernel=' + abi in p[1].get('depends', [])]
        else:
            payload = payloads.get(name + '-' + generation)
            valid = [p for p in candidates.get(name, []) if payload
                     and p[1]['version'] == payload[1]['version']
                     and 'kernel=' + abi in p[1].get('depends', [])
                     and name + '-' + generation + '=' + p[1]['version'] in p[1].get('depends', [])]
        if not valid:
            raise ValueError('Missing matching kernel tracker/payload: ' + name)
        if len({LAN.sha256(p[0]) for p in valid}) != 1:
            raise ValueError('Conflicting kernel tracker copies: ' + name)
        selected[name] = valid[0]
    for name, (path, info) in selected.items():
        for dep in info.get('depends', []):
            dependency, comparator, version = re.fullmatch(r'([^<>=~]+)([<>=~]*)(.*)', dep).groups()
            if dependency.startswith(('kmod-', 'linux-image-')):
                if dependency not in selected:
                    raise ValueError('Incomplete kernel dependency closure: ' + dep)
                if comparator == '=' and selected[dependency][1]['version'] != version:
                    raise ValueError('Kernel dependency version mismatch: ' + dep)
        copy_package(path, channel / path.name)
    return userspace, channel, abi, generation


def publish(tree, data, dry_run=False):
    apk = TREE / 'staging_dir/host/bin/apk'
    if configuration(tree).get('CONFIG_OPENWRT_KERNEL_UPGRADE') != 'y':
        return LAN.publish(argparse.Namespace(source_root=tree, kernel=data.get('kernel'),
            destination=data['destination'], base_url=data['base_url'], incremental=True,
            dry_run=dry_run, kernel_upgrade_view=False))
    destination = data['destination']
    destination.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='.build-publish-', dir=destination) as temporary:
        userspace, channel, abi, generation = project(tree, Path(temporary), apk)
        if data.get('kernel') and data['kernel'] != abi:
            raise ValueError('Requested ABI differs from compiled generation')
        args = argparse.Namespace(source_root=userspace, kernel=abi, destination=destination,
            base_url=data['base_url'], incremental=True, dry_run=True, kernel_upgrade_view=True)
        # Validate BOTH views before exposing either. Expose userspace first;
        # it contains no new kernel trackers, so a trial cannot race its feeds.
        lan = LAN.publish(args)
        kernel = KERNEL.publish(channel, destination, apk, TREE / 'private-key.pem', TREE, True)
        if not dry_run:
            args.dry_run = False
            lan = LAN.publish(args)
            kernel = KERNEL.publish(channel, destination, apk, TREE / 'private-key.pem', TREE)
        return {'userspace': lan, 'kernel': kernel, 'generation': generation}


def run_make(tree, arguments):
    # Package scripts/lists and temporary roots inherit the build's umask.
    # Keep their recorded ACLs stable across shells and validation checkouts.
    subprocess.run(['make', *arguments], cwd=tree, check=True, umask=0o022)


def build(tree, make_args, publish_after=True):
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
        fcntl.flock(lock, fcntl.LOCK_EX)
        targets = [arg for arg in make_args if not arg.startswith('-') and '=' not in arg
                   and not arg.isdigit()]
        enabled = configuration(tree).get('CONFIG_OPENWRT_KERNEL_UPGRADE') == 'y'
        full = not targets or targets == ['world']
        plan = None
        if enabled and (full or state_path(tree).exists()):
            run_make(tree, ['prepare-tmpinfo'])
        if enabled and full:
            prepare_sequence(tree, data['destination'], make_args)
            plan = json.loads(state_path(tree).read_text())
        elif enabled and state_path(tree).exists():
            plan = json.loads(state_path(tree).read_text())
            if INPUTS.fingerprint(tree, configuration(tree), make_args) != plan['inputs']:
                raise ValueError('Kernel inputs changed; run a complete build to reserve a new generation')
        arguments = list(make_args)
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
            if after['tools'] != plan['inputs']['tools'] and plan['sequence'] <= published:
                raise ValueError('Kernel build tools changed; retry with a new generation')
            plan.update(inputs=after, phase='built')
            save_state(tree, plan)
        if publish_after:
            return publish(tree, data)
        return {'status': 'built', 'tree': str(tree),
                'sequence': plan['sequence'] if plan else None}


def main():
    if len(sys.argv) > 1 and sys.argv[1] in ('build', 'build-only'):
        result = build(TREE, sys.argv[2:], publish_after=sys.argv[1] == 'build')
    else:
        parser = argparse.ArgumentParser(description=__doc__)
        parser.add_argument('--config', type=Path, default=TREE / 'configs/lan-apk-feeds.json')
        parser.add_argument('--source-root', type=Path, default=TREE)
        parser.add_argument('--destination', type=Path)
        parser.add_argument('--base-url')
        parser.add_argument('--kernel')
        parser.add_argument('--incremental', action='store_true', help='Compatibility; always incremental')
        parser.add_argument('--dry-run', action='store_true')
        args = parser.parse_args()
        data = json.loads(args.config.read_text())
        data.update({k: v for k, v in vars(args).items()
                     if k in ('destination', 'base_url', 'kernel') and v is not None})
        data['destination'] = Path(data['destination']).resolve()
        tree = args.source_root.resolve()
        lockdir = tree / 'tmp'
        lockdir.mkdir(exist_ok=True)
        with (lockdir / '.build-and-publish.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            result = publish(tree, data, args.dry_run)
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
