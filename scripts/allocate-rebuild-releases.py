#!/usr/bin/env python3
"""Allocate new effective releases for APKs rebuilt under published versions.

When a provider changes its SONAME (ICU 78 -> 79, libubox 20261103), the
build correctly relinks its consumers, but their recipe versions do not move
and the publisher rejects the new bytes under already-published identities.
This tool turns that rejection into ELF rebuild ledger entries
(configs/apk-elf-rebuilds.mk) so the consumers can be repackaged under the
next free release.

Only differences that need a new identity are allocated automatically:

  * verdict "change" from diagnose-apk-rebuild.py, or
  * any verdict when the package's so: dependencies changed (relinked
    against a new provider ABI).

"benign" or "unknown" differences without a dependency change are refused:
nondeterminism should be fixed. After reviewing the diagnosis by hand,
--accept-unknown allocates "unknown" differences as well.

Only the ledger key for the package's current recipe version is written or
updated. Older keys stay unchanged so their outputs remain reserved against
reuse by future recipe releases.

Usage:
  allocate-rebuild-releases.py base/nautilus-51.1-r3.apk [...]          # plan only
  allocate-rebuild-releases.py --apply base/nautilus-51.1-r3.apk [...]  # edit the ledger
"""
import argparse
import datetime
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys

TREE = Path(__file__).resolve().parent.parent
APK = TREE / 'staging_dir/host/bin/apk'
LEDGER = 'configs/apk-elf-rebuilds.mk'
PACKAGE_ROOT = 'bin/systemd/packages/x86_64'
TARGET_PACKAGES = 'bin/systemd/targets/x86/64-glibc/packages'
SECTION = 'automatic same-version rebuild allocations'

_diagnose_spec = importlib.util.spec_from_file_location(
    'allocate_diagnose_rebuild', Path(__file__).with_name('diagnose-apk-rebuild.py'))
DIAGNOSE = importlib.util.module_from_spec(_diagnose_spec)
_diagnose_spec.loader.exec_module(DIAGNOSE)


def split_version(version):
    """Split an APK version into (upstream, release); a bare version is release 0."""
    match = re.fullmatch(r'(.+)-r(\d+)', version)
    return (match[1], int(match[2])) if match else (version, 0)


def package_info(apk, package):
    return json.loads(subprocess.check_output(
        [str(apk), 'adbdump', '--format', 'json', str(package)]))['info']


def so_dependencies(info):
    return sorted(d for d in info.get('depends', []) if d.startswith('so:'))


def classify(old, new, path, apk=APK):
    """Return (entry, report) for one same-version rebuild."""
    report = DIAGNOSE.diagnose(old, new, apk)
    before, after = package_info(apk, old), package_info(apk, new)
    old_so, new_so = so_dependencies(before), so_dependencies(after)
    entry = {'path': path, 'name': after['name'], 'version': after['version'],
             'verdict': report.verdict, 'so_changed': old_so != new_so,
             'so_removed': sorted(set(old_so) - set(new_so)),
             'so_added': sorted(set(new_so) - set(old_so))}
    return entry, report


def eligible(entry, accept=()):
    return entry['verdict'] in (DIAGNOSE.CHANGE, *accept) or entry['so_changed']


def recipe_versions(tree):
    """Map package name -> (recipe version, Source-Makefile) from tmp/.packageinfo."""
    result, makefile, name = {}, None, None
    for line in (tree / 'tmp/.packageinfo').read_text().splitlines():
        if line.startswith('Source-Makefile: '):
            makefile, name = line.removeprefix('Source-Makefile: '), None
        elif line.startswith('Package: '):
            name = line.removeprefix('Package: ')
        elif name and line.startswith('Version: '):
            result[name] = (line.removeprefix('Version: '), makefile)
            name = None
    return result


def ledger_entries(text):
    entries = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(ELF_(?:REBUILD|DEP)_\S+?):=(.*)', line)
        if match:
            entries[match[1]] = match[2]
    return entries


def built_filenames(tree):
    roots = [tree / TARGET_PACKAGES, *sorted((tree / PACKAGE_ROOT).glob('*'))]
    return {entry.name for root in roots if root.is_dir()
            for entry in os.scandir(root) if entry.name.endswith('.apk')}


def published_filenames(destination):
    names = set()
    public = Path(destination) / 'public'
    for kind in ('snapshots', 'userspace-snapshots'):
        for snapshot in sorted((public / kind).glob('*')):
            for repository in snapshot.iterdir() if snapshot.is_dir() else ():
                if repository.is_dir():
                    names.update(e.name for e in os.scandir(repository) if e.name.endswith('.apk'))
    return names


def taken_releases(name, upstream, filenames, entries):
    pattern = re.compile(re.escape(f'{name}-{upstream}') + r'(?:-r(\d+))?\.apk')
    taken = {int(m[1] or 0) for f in filenames if (m := pattern.fullmatch(f))}
    prefix = f'ELF_REBUILD_{name}_'
    for key, value in entries.items():
        if key.startswith(prefix):
            value_upstream, release = split_version(value)
            if value_upstream == upstream:
                taken.add(release)
    return taken


def plan(tree, destination, rejected, accept=()):
    """Choose the next free release for each eligible rejected package."""
    refused = [e for e in rejected if not eligible(e, accept)]
    if refused:
        raise ValueError('Refusing automatic release allocation for differences without a '
                         'content or so: dependency change; inspect with '
                         'scripts/diagnose-apk-rebuild.py: ' +
                         ', '.join(f'{e["path"]} ({e["verdict"]})' for e in refused))
    recipes = recipe_versions(tree)
    entries = ledger_entries((tree / LEDGER).read_text())
    filenames = built_filenames(tree) | published_filenames(destination)
    allocations = []
    for entry in sorted(rejected, key=lambda e: e['name']):
        name = entry['name']
        if name not in recipes:
            raise ValueError(f'{name}: no recipe in tmp/.packageinfo')
        recipe, makefile = recipes[name]
        current = entries.get(f'ELF_REBUILD_{name}_{recipe}', recipe)
        if current != entry['version']:
            raise ValueError(f'{name}: rejected {entry["version"]} is not the current effective '
                             f'version {current} of recipe {recipe}; rebuild first')
        upstream, release = split_version(current)
        taken = taken_releases(name, upstream, filenames, entries)
        taken |= {release, split_version(recipe)[1]}
        allocations.append({**entry, 'recipe': recipe, 'makefile': makefile,
                            'release': f'{upstream}-r{max(taken) + 1}'})
    return allocations


def apply(tree, allocations, today=None):
    """Write ledger entries keyed by each current recipe version."""
    ledger = tree / LEDGER
    lines = ledger.read_text().splitlines()
    header = f'# {today or datetime.date.today().isoformat()} {SECTION}'
    appended = []
    for allocation in allocations:
        name, recipe, release = allocation['name'], allocation['recipe'], allocation['release']
        for key, value in ((f'ELF_REBUILD_{name}_{recipe}', release),
                           (f'ELF_DEP_{name}_{recipe}', f'{name}={release}')):
            indexes = [i for i, line in enumerate(lines) if line.startswith(key + ':=')]
            for index in indexes:
                lines[index] = f'{key}:={value}'
            if not indexes:
                appended.append(f'{key}:={value}')
    if appended:
        last_header = next((line for line in reversed(lines) if line.startswith('#')), None)
        if last_header != header:
            lines.append(header)
        lines.extend(appended)
    ledger.write_text('\n'.join(lines) + '\n')


def rebuild_targets(allocations):
    return sorted({str(Path(a['makefile']).parent / 'compile') for a in allocations})


def describe(allocations):
    lines = []
    for a in allocations:
        reason = a['verdict']
        if a['so_changed']:
            reason += '; so: ' + ' '.join(a['so_removed']) + ' -> ' + ' '.join(a['so_added'])
        lines.append(f'{a["name"]}: {a["version"]} -> {a["release"]} (recipe {a["recipe"]}; {reason})')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('packages', nargs='+', help='REPOSITORY/FILE.apk paths from the publisher')
    parser.add_argument('--apply', action='store_true', help='write the ledger entries')
    parser.add_argument('--accept-unknown', action='store_true',
                        help='also allocate differences diagnosed as unknown (after manual review)')
    parser.add_argument('--destination', type=Path,
                        help='feed destination (default: configs/lan-apk-feeds.json)')
    args = parser.parse_args(argv)
    if not APK.exists():
        parser.error(f'{APK} is missing; build the host apk tool first')
    destination = args.destination or Path(
        json.loads((TREE / 'configs/lan-apk-feeds.json').read_text())['destination'])
    rejected = []
    for path in args.packages:
        old, new = DIAGNOSE.resolve(path)
        rejected.append(classify(old, new, path)[0])
    allocations = plan(TREE, destination, rejected,
                       (DIAGNOSE.UNKNOWN,) if args.accept_unknown else ())
    print(describe(allocations))
    if args.apply:
        apply(TREE, allocations)
        print(f'Updated {LEDGER}; rebuild with: make ' + ' '.join(rebuild_targets(allocations)))
    else:
        print('Plan only; pass --apply to update ' + LEDGER)
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print('Allocation failed: ' + str(error), file=sys.stderr)
        sys.exit(1)
