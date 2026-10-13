#!/usr/bin/env python3
"""Freeze the reviewed AppImage additions for an existing systemd desktop."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess

NAMES = {
    'libfuse1', 'fuse-utils', 'libnss', 'nspr', 'libfontenc', 'libXfont2',
    'libxkbfile', 'libxcvt', 'libxshmfence', 'libXxf86vm', 'xkbcomp',
    'xwayland', 'openwrt-appimage', 'openwrt-desktop', 'openwrt-flatpak',
    'weston', 'libcairo', 'libglvnd', 'libmesa-virtualization',
    'libcups-runtime', 'unshare',
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path, help='New bundle directory')
    args = parser.parse_args()
    repo = Path(__file__).resolve().parent.parent
    apk = repo / 'staging_dir/host/bin/apk'
    packages = []
    for path in sorted((repo / 'bin/systemd/packages/x86_64').glob('*/*.apk')):
        if not any(path.name.startswith(name + '-') for name in NAMES):
            continue
        dump = subprocess.check_output([str(apk), 'adbdump', str(path)], text=True)
        name = re.search(r'^  name: (.*)$', dump, re.M)[1]
        if name not in NAMES:
            continue
        subprocess.run([str(apk), '--keys-dir', str(repo), 'verify', str(path)],
                       check=True, capture_output=True)
        version = re.search(r'^  version: (.*)$', dump, re.M)[1]
        packages.append({'name': name, 'version': version, 'file': path.name,
                         'source': str(path), 'size': path.stat().st_size,
                         'sha256': hashlib.sha256(path.read_bytes()).hexdigest()})
    if len(packages) != len(NAMES) or {p['name'] for p in packages} != NAMES:
        raise RuntimeError('Build all 21 packages; remove stale APK versions through the build rules')
    args.output.mkdir()  # Never overwrite an existing bundle.
    packages.sort(key=lambda p: p['name'])
    for package in packages:
        destination = args.output / package['file']
        shutil.copy2(package['source'], destination)
        if hashlib.sha256(destination.read_bytes()).hexdigest() != package['sha256']:
            raise RuntimeError('Build output changed while creating the bundle')
    shutil.copy2(repo / 'scripts/appimage-bundle-install.sh', args.output / 'install.sh')
    (args.output / 'manifest.json').write_text(json.dumps(packages, indent=2) + '\n')
    (args.output / 'SHA256SUMS').write_text(''.join(
        p['sha256'] + '  ' + p['file'] + '\n' for p in packages))
    print('Verified bundle:', len(packages), 'signed APKs,',
          sum(p['size'] for p in packages), 'bytes')


if __name__ == '__main__':
    main()
