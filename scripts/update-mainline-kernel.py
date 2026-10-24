#!/usr/bin/env python3
"""Explicitly check or update the ported x86/64 mainline kernel series."""
import argparse
from contextlib import ExitStack
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.request import urlopen

RELEASES = 'https://www.kernel.org/releases.json'
CDN = 'https://cdn.kernel.org/pub/linux/kernel'
VERSION = re.compile(r'[1-9][0-9]*\.[0-9]+(?:\.[0-9]+)?')


class SyncError(Exception):
    pass


def version_key(value):
    if not isinstance(value, str) or not VERSION.fullmatch(value):
        raise SyncError('Expected a final kernel version: ' + str(value))
    parts = tuple(map(int, value.split('.')))
    return parts + (0,) * (3 - len(parts))


def latest_release(data):
    if not isinstance(data, dict) or not isinstance(data.get('releases'), list):
        raise SyncError('Invalid kernel.org release metadata')
    if any(not isinstance(row, dict) for row in data['releases']):
        raise SyncError('Invalid kernel.org release entry')
    releases = [row['version'] for row in data.get('releases', [])
                if row.get('moniker') in ('mainline', 'stable')
                and isinstance(row.get('version'), str) and VERSION.fullmatch(row['version'])]
    if not releases:
        raise SyncError('kernel.org did not advertise a final mainline/stable release')
    return max(releases, key=version_key)


class Fetcher:
    def get(self, url):
        with urlopen(url, timeout=60) as response:
            if not response.url.startswith('https://'):
                raise SyncError('Refusing a non-HTTPS redirect')
            body = response.read(8 * 1024 * 1024 + 1)
            if len(body) > 8 * 1024 * 1024:
                raise SyncError('Upstream metadata exceeds 8 MiB')
            return body

    def download(self, url, destination):
        with urlopen(url, timeout=60) as response, destination.open('wb') as stream:
            if not response.url.startswith('https://'):
                raise SyncError('Refusing a non-HTTPS redirect')
            size = 0
            while block := response.read(1024 * 1024):
                size += len(block)
                if size > 2 * 1024 ** 3:
                    raise SyncError('Kernel archive exceeds 2 GiB')
                stream.write(block)


def current_kernel(root):
    selection = root / 'target/linux/x86/64/target.mk'
    matches = re.findall(r'^KERNEL_PATCHVER\s*:?=\s*([0-9]+\.[0-9]+)\s*$',
                         selection.read_text(), re.M)
    if len(matches) != 1:
        raise SyncError('x86/64 must explicitly select one ported mainline series')
    series = matches[0]
    metadata = root / ('target/linux/generic/kernel-' + series)
    text = metadata.read_text()
    suffixes = re.findall(r'^LINUX_VERSION-' + re.escape(series) + r'\s*=\s*(\.[0-9]+)?[ \t]*$',
                          text, re.M)
    if len(suffixes) != 1:
        raise SyncError('Expected one literal kernel version in ' + str(metadata))
    current = series + suffixes[0]
    version_key(current)
    if not re.search(r'^LINUX_KERNEL_HASH-' + re.escape(current) + r'\s*=\s*[0-9a-f]{64}\s*$',
                     text, re.M):
        raise SyncError('Missing SHA256 for kernel ' + current)
    return series, current, metadata


def patch_directories(root, series):
    return [root / ('target/linux/generic/' + name + '-' + series)
            for name in ('backport', 'pending', 'hack')] + [
                root / ('target/linux/x86/patches-' + series)]


def overlay_directories(root, series):
    return [root / ('target/linux/' + target + '/' + name)
            for target in ('generic', 'x86') for name in ('files', 'files-' + series)]


def input_state(root, series, metadata):
    paths = [metadata, root / 'target/linux/x86/Makefile',
             root / 'target/linux/x86/64/target.mk', root / '.config']
    paths += [root / ('target/linux/' + target + '/config-' + series)
              for target in ('generic', 'x86', 'x86/64')]
    paths += patch_directories(root, series) + overlay_directories(root, series)
    state = {}
    for path in paths:
        files = [path] + (sorted(path.rglob('*')) if path.is_dir() else [])
        for item in files:
            name = str(item.relative_to(root))
            if item.is_file():
                with item.open('rb') as stream:
                    state[name] = hashlib.file_digest(stream, 'sha256').hexdigest()
            elif item.is_symlink():
                state[name] = 'link:' + os.readlink(item)
            else:
                state[name] = 'directory' if item.is_dir() else 'missing'
    return state


def validate_patches(root, series, archive, work, version):
    for target in ('generic', 'x86', 'x86/64'):
        if not (root / ('target/linux/' + target + '/config-' + series)).is_file():
            raise SyncError('Missing ported kernel configuration: ' + target)
    with tarfile.open(archive, 'r:xz') as stream:
        stream.extractall(work, filter='data')
    source = work / ('linux-' + version)
    if not (source / 'Makefile').is_file():
        raise SyncError('Kernel archive has an unexpected root directory')
    for overlay in overlay_directories(root, series):
        if overlay.is_dir():
            shutil.copytree(overlay, source, dirs_exist_ok=True, symlinks=True)
    for directory in patch_directories(root, series):
        if not directory.is_dir():
            raise SyncError('Missing ported patch directory: ' + str(directory))
        series_file = directory / 'series'
        if series_file.exists():
            names = [line.split('#', 1)[0].strip() for line in series_file.read_text().splitlines()]
            patches = []
            for name in filter(None, names):
                path = directory / name
                if not path.resolve().is_relative_to(directory.resolve()) or not path.is_file():
                    raise SyncError('Invalid patch series entry: ' + name)
                patches.append(path)
        else:
            patches = sorted(directory.glob('*.patch'))
        for patch in patches:
            result = subprocess.run(['patch', '--batch', '--forward', '--fuzz=0', '-p1',
                                     '-i', str(patch.resolve())], cwd=source,
                                    capture_output=True, text=True, timeout=120)
            if result.returncode:
                raise SyncError('Kernel port needs review: ' + str(patch.relative_to(root)) +
                                '\n' + result.stdout[-4000:] + result.stderr[-1000:])


def sync(root, update=False, fetcher=None, validator=validate_patches):
    root = root.resolve()
    fetcher = fetcher or Fetcher()
    with ExitStack() as stack:
        if update:
            gitdir = Path(subprocess.check_output(
                ['git', '-C', str(root), 'rev-parse', '--absolute-git-dir'], text=True).strip())
            (root / 'tmp').mkdir(exist_ok=True)
            for path in (gitdir / 'mainline-kernel-update.lock', root / 'tmp/.build-and-publish.lock'):
                lock = stack.enter_context(path.open('a'))
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as error:
                    raise SyncError('A kernel sync or build is already running') from error
        series, current, metadata = current_kernel(root)
        latest = latest_release(json.loads(fetcher.get(RELEASES)))
        report = {'current': current, 'latest': latest, 'series': series}
        if version_key(latest) <= version_key(current):
            return dict(report, status='current'), 0
        if '.'.join(latest.split('.')[:2]) != series:
            return dict(report, status='port-required',
                        message='Port the new series before changing the working kernel selection'), 2
        if not update:
            return dict(report, status='available'), 1
        relative = str(metadata.relative_to(root))
        dirty = subprocess.run(['git', '-C', str(root), 'diff', '--quiet', 'HEAD', '--', relative,
                                'target/linux/x86/64/target.mk'], check=False)
        if dirty.returncode:
            raise SyncError('Commit or preserve local kernel metadata edits before syncing')
        before = input_state(root, series, metadata)
        original = metadata.read_bytes()
        name = 'linux-' + latest + '.tar.xz'
        base = CDN + '/v' + latest.split('.')[0] + '.x/'
        sums = fetcher.get(base + 'sha256sums.asc').decode()
        hashes = re.findall(r'^([0-9a-f]{64})[ \t]+\*?' + re.escape(name) + r'\s*$', sums, re.M)
        if len(hashes) != 1:
            raise SyncError('Expected exactly one kernel.org SHA256 for ' + name)
        digest = hashes[0]
        (root / 'build_dir').mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='mainline-sync-', dir=root / 'build_dir') as directory:
            work = Path(directory)
            cached = root / 'dl' / name
            archive = cached if cached.exists() else work / name
            if not cached.exists():
                fetcher.download(base + name, archive)
            with archive.open('rb') as stream:
                actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual != digest:
                raise SyncError('SHA256 mismatch for ' + name)
            validator(root, series, archive, work, latest)
            if input_state(root, series, metadata) != before:
                raise SyncError('Kernel inputs changed during validation; retry with stable inputs')
            if not cached.exists():
                cached.parent.mkdir(exist_ok=True)
                try:
                    os.link(archive, cached)
                except FileExistsError:
                    with cached.open('rb') as stream:
                        if hashlib.file_digest(stream, 'sha256').hexdigest() != digest:
                            raise SyncError('Kernel archive cache changed during validation')
            text = original.decode()
            text = re.sub(r'^(LINUX_VERSION-' + re.escape(series) + r'\s*=)[^\n]*',
                          lambda match: match[1] + ' ' + latest[len(series):], text, flags=re.M)
            text = re.sub(r'^LINUX_KERNEL_HASH-' + re.escape(current) + r'\s*=[^\n]*',
                          'LINUX_KERNEL_HASH-' + latest + ' = ' + digest, text, flags=re.M)
            with tempfile.NamedTemporaryFile('w', dir=metadata.parent, delete=False) as stream:
                temporary = Path(stream.name)
                try:
                    os.fchmod(stream.fileno(), metadata.stat().st_mode & 0o777)
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                    if metadata.read_bytes() != original:
                        raise SyncError('Kernel metadata changed before replacement')
                    os.replace(temporary, metadata)
                finally:
                    temporary.unlink(missing_ok=True)
        return dict(report, status='updated', sha256=digest,
                    message='Source metadata updated; build and VM validation are still required'), 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Read-only check (default)')
    mode.add_argument('--update', action='store_true', help='Verify patches and update source metadata only')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        report, status = sync(args.root, args.update)
        print(json.dumps(report, indent=2))
        return status
    except (SyncError, OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as error:
        print('Kernel sync failed: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
