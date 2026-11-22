#!/usr/bin/env python3
"""Allocate new effective releases for APKs rebuilt under published versions.

When a provider changes its SONAME (ICU 78 -> 79, libubox 20261103), the
build correctly relinks its consumers, but their recipe versions do not move
and the publisher rejects the new bytes under already-published identities.
This tool turns eligible rejections into ELF rebuild ledger entries
(configs/apk-elf-rebuilds.mk) so the consumers can be repackaged under the
next free release.

Release decisions are shared with scripts/diagnose-apk-rebuild.py:
  * action "allocate_release" -> eligible automatically
  * action "review_before_allocate" -> requires digest-bound --approval FILE
    (or standalone CLI --accept-unknown, never used by the production coordinator)
  * action "reuse_published", "benign_nondeterminism", "keep_existing", "reject"
    -> never allocated

Only the ledger key for the package's current recipe version is written or
updated. Older keys and superseded effective releases stay reserved against
reuse by future recipe releases.

Usage:
  allocate-rebuild-releases.py base/nautilus-51.1-r3.apk [...]          # plan only
  allocate-rebuild-releases.py --apply base/nautilus-51.1-r3.apk [...]  # edit the ledger
"""
import argparse
import datetime
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

TREE = Path(__file__).resolve().parent.parent
APK = TREE / 'staging_dir/host/bin/apk'
LEDGER = 'configs/apk-elf-rebuilds.mk'
JOURNAL = 'tmp/.apk-rebuild-allocations.json'
PACKAGE_ROOT = 'bin/systemd/packages/x86_64'
TARGET_PACKAGES = 'bin/systemd/targets/x86/64-glibc/packages'
SECTION = 'automatic same-version rebuild allocations'

_diagnose_spec = importlib.util.spec_from_file_location(
    'allocate_diagnose_rebuild', Path(__file__).with_name('diagnose-apk-rebuild.py'))
DIAGNOSE = importlib.util.module_from_spec(_diagnose_spec)
_diagnose_spec.loader.exec_module(DIAGNOSE)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def atomic_write_text(path, text):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False,
                                     prefix='.' + path.name + '.tmp-') as stream:
        temporary = Path(stream.name)
        try:
            if path.exists():
                os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
            stream.write(text)
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(temporary, path)
        finally:
            temporary.unlink(missing_ok=True)


def split_version(version):
    """Split an APK version into (upstream, release); a bare version is release 0."""
    match = re.fullmatch(r'(.+)-r(\d+)', version)
    return (match[1], int(match[2])) if match else (version, 0)


def package_info(apk, package):
    return json.loads(subprocess.check_output(
        [str(apk), 'adbdump', '--format', 'json', str(package)]))['info']


def so_dependencies(info):
    return sorted(d for d in info.get('depends', []) if d.startswith('so:'))


def classify(old, new, path, apk=APK, keys_dir=None, context=None,
             abi_store=None, cold_evidence=None):
    """Return (entry, report) for one same-version rebuild."""
    report = DIAGNOSE.diagnose(
        old, new, apk, keys_dir=keys_dir, context=context,
        abi_store=abi_store, cold_evidence=cold_evidence)
    before, after = package_info(apk, old), package_info(apk, new)
    old_so, new_so = so_dependencies(before), so_dependencies(after)
    decision = report.effective_decision()
    entry = {
        'path': path,
        'sources': [path],
        'old_path': str(old),
        'new_path': str(new),
        'old_sha256': report.old_sha256,
        'new_sha256': report.new_sha256,
        'report_sha256': report.report_sha256(),
        'name': after['name'],
        'version': after['version'],
        'verdict': report.verdict,
        'decision': decision,
        'trust': report.trust,
        'unresolved': decision.get('unresolved', []),
        'so_changed': old_so != new_so,
        'so_removed': sorted(set(old_so) - set(new_so)),
        'so_added': sorted(set(new_so) - set(old_so)),
    }
    if context and context.get('baseline_snapshot'):
        entry['snapshot'] = context['baseline_snapshot']
    return entry, report


def load_approvals(path):
    """Load one or more digest-bound review approvals from a JSON file."""
    data = json.loads(Path(path).read_text())
    return data if isinstance(data, list) else [data]


def verify_approval(entry, approval):
    """Verify that an approval binds to the exact conflict report, digests, and policy."""
    if not isinstance(approval, dict):
        return False
    if approval.get('schema') != 1:
        return False
    if approval.get('policy_version') != DIAGNOSE.POLICY_VERSION:
        return False
    if not str(approval.get('reason', '')).strip():
        return False
    for key in ('old_sha256', 'new_sha256', 'report_sha256'):
        if not entry.get(key) or approval.get(key) != entry.get(key):
            return False
    if entry.get('snapshot') and approval.get('snapshot') and approval['snapshot'] != entry['snapshot']:
        return False
    if approval.get('name') and entry.get('name') and approval['name'] != entry['name']:
        return False
    return True


def matching_approval(entry, approvals):
    if not approvals:
        return None
    for item in approvals:
        if verify_approval(entry, item):
            return item
    return None


def eligible(entry, accept=(), approvals=None, require_trust=False):
    """Return True only when the entry is allowed to allocate a new release."""
    if require_trust and entry.get('trust') and not entry['trust'].get('verified'):
        return False
    decision = entry.get('decision')
    if decision:
        action = decision.get('action')
        if action == DIAGNOSE.ACTION_ALLOCATE_RELEASE:
            return True
        if action == DIAGNOSE.ACTION_REVIEW:
            if matching_approval(entry, approvals):
                return True
            return DIAGNOSE.UNKNOWN in accept
        return False
    # Legacy dict without decision: never let unknown+so_changed or unresolved pass.
    if entry.get('unresolved'):
        if matching_approval(entry, approvals):
            return True
        return DIAGNOSE.UNKNOWN in accept
    verdict = entry.get('verdict')
    if verdict == DIAGNOSE.CHANGE:
        return True
    if verdict == DIAGNOSE.UNKNOWN:
        if matching_approval(entry, approvals):
            return True
        return DIAGNOSE.UNKNOWN in accept
    return False


def deduplicate_entries(rejected):
    """Merge identical (name, version, old_sha256, new_sha256) projections; reject digest conflicts."""
    by_identity = {}
    for entry in rejected:
        key = (entry.get('name'), entry.get('version'))
        existing = by_identity.get(key)
        if existing is None:
            merged = dict(entry)
            sources = list(entry.get('sources') or ([entry['path']] if entry.get('path') else []))
            merged['sources'] = sorted(set(sources))
            by_identity[key] = merged
            continue
        if (entry.get('old_sha256') and existing.get('old_sha256')
                and entry['old_sha256'] != existing['old_sha256']):
            raise ValueError(
                f'{key[0]}-{key[1]}: conflicting baseline digests across '
                f'{existing["sources"]} and {entry.get("path")}')
        if (entry.get('new_sha256') and existing.get('new_sha256')
                and entry['new_sha256'] != existing['new_sha256']):
            raise ValueError(
                f'{key[0]}-{key[1]}: conflicting candidate digests across '
                f'{existing["sources"]} and {entry.get("path")}')
        sources = set(existing['sources'])
        sources.update(entry.get('sources') or ([entry['path']] if entry.get('path') else []))
        existing['sources'] = sorted(sources)
    return list(by_identity.values())


def normalize_packageinfo_version(version):
    """Match rules.mk version_abbrev when DUMP=1 leaves full git commit hashes."""
    return re.sub(r'~([0-9a-f]{40,})(?=-r\d+$|$)', lambda m: '~' + m[1][:8], version)


def abi_package_name(name, abi):
    """Reproduce FormatABISuffix from include/feeds.mk."""
    if not abi or name.startswith('kmod-'):
        return None
    return name + ('-' if name[-1].isdigit() else '') + abi


def recipe_versions(tree):
    """Map package name -> (recipe version, Source-Makefile, ABI-Version)."""
    result, makefile, name, last = {}, None, None, None
    for line in (tree / 'tmp/.packageinfo').read_text().splitlines():
        if line.startswith('Source-Makefile: '):
            makefile, name, last = line.removeprefix('Source-Makefile: '), None, None
        elif line.startswith('Package: '):
            name, last = line.removeprefix('Package: '), None
        elif name and line.startswith('Version: '):
            result[name] = [normalize_packageinfo_version(line.removeprefix('Version: ')),
                            makefile, '']
            last, name = result[name], None
        elif last is not None and line.startswith('ABI-Version: '):
            last[2] = line.removeprefix('ABI-Version: ').strip()
    return result


def ledger_entries(text):
    entries = {}
    for line in text.splitlines():
        match = re.fullmatch(r'(ELF_(?:REBUILD|DEP)_\S+?):=(.*)', line)
        if match:
            entries[match[1]] = match[2]
    return entries


def ledger_reservations(text):
    """Parse permanently reserved historical effective versions from ledger comments."""
    reserved = {}
    for line in text.splitlines():
        match = re.fullmatch(r'#\s*reserved:\s*ELF_REBUILD_(\S+?)\s*->\s*(\S+)', line.strip())
        if match:
            reserved.setdefault(match[1], set()).add(match[2])
    return reserved


def load_journal(tree):
    path = Path(tree) / JOURNAL
    if not path.is_file():
        return {'schema': 1, 'records': []}
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict) and isinstance(data.get('records'), list):
            return data
    except (ValueError, OSError):
        pass
    return {'schema': 1, 'records': []}


def save_journal(tree, journal):
    atomic_write_text(Path(tree) / JOURNAL, json.dumps(journal, indent=2, sort_keys=True) + '\n')


def find_recoverable_allocation(journal, entry, entries):
    """Find an interrupted/pending allocation matching the exact conflict digests."""
    if not entry.get('old_sha256') or not entry.get('new_sha256'):
        return None
    for record in reversed(journal.get('records', [])):
        if record.get('status') not in ('allocated', 'rebuilt_verified'):
            continue
        if (record.get('name') == entry.get('name')
                and record.get('from_version') == entry.get('version')
                and record.get('old_sha256') == entry.get('old_sha256')
                and record.get('new_sha256') == entry.get('new_sha256')):
            ledger_name = record.get('ledger_name', record['name'])
            key = f'ELF_REBUILD_{ledger_name}_{record["recipe"]}'
            if entries.get(key) == record.get('to_version'):
                return record
    return None


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


def taken_releases(name, upstream, filenames, entries, reservations=None, journal=None):
    pattern = re.compile(re.escape(f'{name}-{upstream}') + r'(?:-r(\d+))?\.apk')
    taken = {int(m[1] or 0) for f in filenames if (m := pattern.fullmatch(f))}
    prefix = f'ELF_REBUILD_{name}_'
    for key, value in entries.items():
        if key.startswith(prefix):
            value_upstream, release = split_version(value)
            if value_upstream == upstream:
                taken.add(release)
    if reservations:
        for key, values in reservations.items():
            if key.startswith(f'{name}_'):
                for value in values:
                    value_upstream, release = split_version(value)
                    if value_upstream == upstream:
                        taken.add(release)
    if journal:
        for record in journal.get('records', []):
            if record.get('name') == name or record.get('ledger_name') == name:
                for field_name in ('from_version', 'to_version'):
                    val = record.get(field_name)
                    if val:
                        value_upstream, release = split_version(val)
                        if value_upstream == upstream:
                            taken.add(release)
    return taken


def _resolve_recipe(entry, recipes, entries):
    name = entry['name']
    ledger_name = name
    if name not in recipes:
        candidates = [base for base, (version, makefile, abi) in recipes.items()
                      if abi_package_name(base, abi) == name]
        if len(candidates) == 1:
            ledger_name = candidates[0]
    if ledger_name not in recipes:
        raise ValueError(f'{name}: no recipe in tmp/.packageinfo')
    recipe, makefile, abi = recipes[ledger_name]
    if '<LIBC_VERSION>' in recipe:
        recipe = recipe.replace('<LIBC_VERSION>', split_version(entry['version'])[0])
    if '<' in recipe:
        raise ValueError(f'{name}: version {recipe} is derived from another package')
    if recipe == 'x' or recipe.startswith('x-r'):
        built_upstream = split_version(entry['version'])[0]
        recipe = (built_upstream if recipe == 'x'
                  else f'{built_upstream}-r{split_version(recipe)[1]}')
    if ledger_name == 'gcc' and recipe.isdigit():
        # gcc derives PKG_VERSION from CONFIG_GCC_VERSION (empty under DUMP=1),
        # leaving only PKG_RELEASE in tmp/.packageinfo (e.g. "13" for 15.3.0-r13).
        built_upstream = split_version(entry['version'])[0]
        if built_upstream != recipe:
            recipe = f'{built_upstream}-r{recipe}'
    if ledger_name == 'base-files':
        prefix = f'ELF_REBUILD_{ledger_name}_'
        matches = [key[len(prefix):] for key, value in entries.items()
                   if key.startswith(prefix) and value == entry['version']]
        recipe = matches[0] if len(matches) == 1 else entry['version']
    return ledger_name, recipe, makefile


def suggest_release(tree, destination, entry, recipes=None, entries=None,
                    reservations=None, filenames=None, journal=None):
    """Compute the next free release for one entry without checking eligibility."""
    recipes = recipes if recipes is not None else recipe_versions(tree)
    ledger_text = (tree / LEDGER).read_text()
    entries = entries if entries is not None else ledger_entries(ledger_text)
    reservations = reservations if reservations is not None else ledger_reservations(ledger_text)
    filenames = filenames if filenames is not None else (
        built_filenames(tree) | published_filenames(destination))
    journal = journal if journal is not None else load_journal(tree)

    name = entry['name']
    ledger_name, recipe, makefile = _resolve_recipe(entry, recipes, entries)
    current = entries.get(f'ELF_REBUILD_{ledger_name}_{recipe}', recipe)
    upstream, release = split_version(current)
    taken = taken_releases(name, upstream, filenames, entries, reservations, journal)
    if ledger_name != name:
        taken |= taken_releases(ledger_name, upstream, filenames, entries, reservations, journal)
    taken |= {release, split_version(recipe)[1]}
    return {
        'ledger_name': ledger_name,
        'recipe': recipe,
        'makefile': makefile,
        'current': current,
        'suggested_release': f'{upstream}-r{max(taken) + 1}',
    }


def plan(tree, destination, rejected, accept=(), approvals=None, require_trust=False, snapshot=None):
    """Choose the next free release for each eligible rejected package."""
    deduped = deduplicate_entries(rejected)
    ledger_text = (tree / LEDGER).read_text()
    ledger_sha = sha256_bytes(ledger_text.encode('utf-8'))
    recipes = recipe_versions(tree)
    entries = ledger_entries(ledger_text)
    reservations = ledger_reservations(ledger_text)
    filenames = built_filenames(tree) | published_filenames(destination)
    journal = load_journal(tree)

    refused = [e for e in deduped if not eligible(e, accept, approvals=approvals,
                                                  require_trust=require_trust)]
    if refused:
        details = []
        for e in refused:
            action = (e.get('decision') or {}).get('action', e.get('verdict', 'unknown'))
            hint = ''
            try:
                if e.get('name') and e.get('version'):
                    s = suggest_release(tree, destination, e, recipes, entries,
                                        reservations, filenames, journal)
                    hint = f', suggested={s["suggested_release"]}'
            except ValueError:
                pass
            details.append(f'{e["path"]} ({action}{hint})')
        raise ValueError('Refusing automatic release allocation for differences requiring review '
                         'or without an eligible content change; inspect with '
                         'scripts/diagnose-apk-rebuild.py: ' + ', '.join(details))

    allocations = []
    for entry in sorted(deduped, key=lambda e: e['name']):
        name = entry['name']
        recovered = find_recoverable_allocation(journal, entry, entries)
        if recovered is not None:
            allocations.append({
                **entry,
                'name': name,
                'ledger_name': recovered['ledger_name'],
                'recipe': recovered['recipe'],
                'makefile': recovered['makefile'],
                'release': recovered['to_version'],
                'recovered': True,
                'ledger_sha256': ledger_sha,
                'snapshot': snapshot or entry.get('snapshot'),
                'approval': matching_approval(entry, approvals),
            })
            continue
        info = suggest_release(tree, destination, entry, recipes, entries,
                               reservations, filenames, journal)
        if info['current'] != entry['version']:
            raise ValueError(f'{name}: rejected {entry["version"]} is not the current effective '
                             f'version {info["current"]} of recipe {info["ledger_name"]} '
                             f'{info["recipe"]}; rebuild first')
        allocations.append({
            **entry,
            'name': name,
            'ledger_name': info['ledger_name'],
            'recipe': info['recipe'],
            'makefile': info['makefile'],
            'release': info['suggested_release'],
            'recovered': False,
            'ledger_sha256': ledger_sha,
            'snapshot': snapshot or entry.get('snapshot'),
            'approval': matching_approval(entry, approvals),
        })
    return allocations


def apply(tree, allocations, today=None, destination=None):
    """Atomically write ledger entries keyed by each current recipe version."""
    if not allocations:
        return
    ledger = Path(tree) / LEDGER
    before_text = ledger.read_text()
    before_sha = sha256_bytes(before_text.encode('utf-8'))

    # Pre-write concurrency checks: fail closed if ledger or snapshot moved.
    expected_shas = {a['ledger_sha256'] for a in allocations if a.get('ledger_sha256')}
    if expected_shas and expected_shas != {before_sha}:
        raise ValueError('Ledger changed concurrently since planning; re-plan before applying')
    if destination is not None:
        dest = Path(destination)
        for a in allocations:
            snap = a.get('snapshot')
            if snap and Path(snap).is_dir():
                aliases = dest / 'public/abi'
                if aliases.is_dir():
                    resolved_aliases = {str(p.resolve()) for p in aliases.iterdir() if p.is_symlink()}
                    if resolved_aliases and str(Path(snap).resolve()) not in resolved_aliases:
                        raise ValueError('Active published snapshot moved concurrently; re-plan required')

    if all(a.get('recovered') for a in allocations):
        return

    lines = before_text.splitlines()
    existing_entries = ledger_entries(before_text)
    existing_reservations = ledger_reservations(before_text)
    header = f'# {today or datetime.date.today().isoformat()} {SECTION}'
    appended = []
    new_reservations = []
    for allocation in allocations:
        if allocation.get('recovered'):
            continue
        name, recipe, release = allocation['name'], allocation['recipe'], allocation['release']
        ledger_name = allocation.get('ledger_name', name)
        rebuild_key = f'ELF_REBUILD_{ledger_name}_{recipe}'
        prev_effective = existing_entries.get(rebuild_key)
        if prev_effective and prev_effective != release:
            res_key = f'{ledger_name}_{recipe}'
            if prev_effective not in existing_reservations.get(res_key, ()):
                new_reservations.append(f'# reserved: {rebuild_key} -> {prev_effective}')
        entries = [(rebuild_key, release),
                   (f'ELF_DEP_{ledger_name}_{recipe}', f'{ledger_name}={release}')]
        if name != ledger_name:
            # ABI_VERSION packages are depended on under the suffixed name.
            entries.append((f'ELF_DEP_{name}_{recipe}', f'{name}={release}'))
        for key, value in entries:
            indexes = [i for i, line in enumerate(lines) if line.startswith(key + ':=')]
            for index in indexes:
                lines[index] = f'{key}:={value}'
            if not indexes:
                appended.append(f'{key}:={value}')
    if new_reservations or appended:
        last_header = next((line for line in reversed(lines) if line.startswith('#')
                            and not line.startswith('# reserved:')), None)
        if last_header != header:
            lines.append(header)
        lines.extend(new_reservations)
        lines.extend(appended)
    after_text = '\n'.join(lines) + '\n'
    after_sha = sha256_bytes(after_text.encode('utf-8'))
    atomic_write_text(ledger, after_text)

    journal = load_journal(tree)
    timestamp = datetime.datetime.now(datetime.timezone.utc).isoformat()
    for allocation in allocations:
        if allocation.get('recovered'):
            continue
        journal['records'].append({
            'timestamp': timestamp,
            'status': 'allocated',
            'policy_version': DIAGNOSE.POLICY_VERSION,
            'name': allocation['name'],
            'ledger_name': allocation.get('ledger_name', allocation['name']),
            'recipe': allocation['recipe'],
            'makefile': allocation.get('makefile'),
            'from_version': allocation['version'],
            'to_version': allocation['release'],
            'old_sha256': allocation.get('old_sha256', ''),
            'new_sha256': allocation.get('new_sha256', ''),
            'report_sha256': allocation.get('report_sha256', ''),
            'snapshot': allocation.get('snapshot'),
            'approval': allocation.get('approval'),
            'ledger_before_sha256': before_sha,
            'ledger_after_sha256': after_sha,
        })
    save_journal(tree, journal)


def verify_rebuilt_package(candidate_apk, rebuilt_apk, name, apk=APK, keys_dir=None,
                           co_allocated_names=()):
    """Ensure a post-allocation rebuilt APK only differs in release-bump metadata.

    Any unexpected payload or ELF drift between the pre-bump candidate and the
    post-bump rebuilt APK is rejected so a new release number cannot bypass review.
    """
    report = DIAGNOSE.diagnose(candidate_apk, rebuilt_apk, apk=apk, keys_dir=keys_dir)
    if keys_dir is not None and not report.trust.get('verified'):
        raise ValueError(f'Post-allocation signature verification failed for {rebuilt_apk}')
    if report.elf_summary:
        raise ValueError(
            f'Post-allocation rebuild of {name} introduced ELF drift: '
            + ', '.join(e['path'] for e in report.elf_summary))

    elf_json_path = f'usr/lib/apk/packages/{name}.elf.json'
    list_path = f'usr/lib/apk/packages/{name}.list'
    co_names = set(co_allocated_names) | {name}
    unexpected = []
    for finding in report.findings:
        if finding.verdict == DIAGNOSE.BENIGN:
            continue
        if finding.path == '(info)' and finding.detail.startswith(('version:', 'installed-size:')):
            continue
        if finding.path == '(info)' and finding.detail.startswith('depends:'):
            # Allow exact-version dependency updates for co-allocated packages.
            if any(dep_name in finding.detail for dep_name in co_names):
                continue
        if finding.path == elf_json_path:
            # Verify only the "version" field changed in the ELF inventory JSON.
            with tempfile.TemporaryDirectory(prefix='verify-rebuilt-') as tmp:
                a_dir, b_dir = Path(tmp) / 'a', Path(tmp) / 'b'
                a_dir.mkdir()
                b_dir.mkdir()
                DIAGNOSE.extract(apk, candidate_apk, a_dir, keys_dir=keys_dir)
                DIAGNOSE.extract(apk, rebuilt_apk, b_dir, keys_dir=keys_dir)
                a_json = json.loads((a_dir / elf_json_path).read_text())
                b_json = json.loads((b_dir / elf_json_path).read_text())
                a_json.pop('version', None)
                b_json.pop('version', None)
                if a_json == b_json:
                    continue
        if finding.path == list_path and finding.verdict == DIAGNOSE.BENIGN:
            continue
        unexpected.append(f'{finding.path}: {finding.detail}')
    if unexpected:
        raise ValueError(
            f'Post-allocation rebuild of {name} drifted beyond release-bump metadata: '
            + '; '.join(unexpected))
    return report


def locate_built_apk(tree, name, version):
    filename = f'{name}-{version}.apk'
    roots = [Path(tree) / TARGET_PACKAGES, *sorted((Path(tree) / PACKAGE_ROOT).glob('*'))]
    for root in roots:
        candidate = root / filename
        if candidate.is_file():
            return candidate
    return None


def verify_rebuilt_packages(tree, allocations, apk=APK, keys_dir=None):
    """Verify every rebuilt APK after allocation and update the recovery journal."""
    co_names = {a['name'] for a in allocations} | {a.get('ledger_name', a['name']) for a in allocations}
    journal = load_journal(tree)
    updated = False
    for allocation in allocations:
        candidate_path = allocation.get('new_path')
        if not candidate_path or not Path(candidate_path).is_file():
            continue
        rebuilt = locate_built_apk(tree, allocation['name'], allocation['release'])
        if rebuilt is None:
            raise ValueError(
                f'Post-allocation rebuild missing expected APK: '
                f'{allocation["name"]}-{allocation["release"]}.apk')
        verify_rebuilt_package(candidate_path, rebuilt, allocation['name'],
                               apk=apk, keys_dir=keys_dir, co_allocated_names=co_names)
        rebuilt_sha = DIAGNOSE.file_sha256(rebuilt)
        for record in reversed(journal['records']):
            if (record.get('name') == allocation['name']
                    and record.get('to_version') == allocation['release']
                    and record.get('status') == 'allocated'):
                record['status'] = 'rebuilt_verified'
                record['rebuilt_sha256'] = rebuilt_sha
                updated = True
                break
    if updated:
        save_journal(tree, journal)


def rebuild_targets(allocations):
    return sorted({str(Path(a['makefile']).parent / 'compile') for a in allocations})


def describe(allocations):
    lines = []
    for a in allocations:
        action = (a.get('decision') or {}).get('action', a['verdict'])
        reason = action
        if a.get('so_changed'):
            reason += '; so: ' + ' '.join(a.get('so_removed', [])) + ' -> ' + ' '.join(a.get('so_added', []))
        if a.get('recovered'):
            reason += '; recovered'
        lines.append(f'{a["name"]}: {a["version"]} -> {a["release"]} (recipe {a["recipe"]}; {reason})')
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('packages', nargs='+', help='REPOSITORY/FILE.apk paths from the publisher')
    parser.add_argument('--apply', action='store_true', help='write the ledger entries')
    parser.add_argument('--accept-unknown', action='store_true',
                        help='standalone CLI override to allocate unknown/review items')
    parser.add_argument('--approval', type=Path,
                        help='JSON file with digest-bound review approval(s)')
    parser.add_argument('--keys-dir', type=Path,
                        help='verify APKs against this keys directory before planning')
    parser.add_argument('--destination', type=Path,
                        help='feed destination (default: configs/lan-apk-feeds.json)')
    args = parser.parse_args(argv)
    if not APK.exists():
        parser.error(f'{APK} is missing; build the host apk tool first')
    destination = args.destination or Path(
        json.loads((TREE / 'configs/lan-apk-feeds.json').read_text())['destination'])
    approvals = load_approvals(args.approval) if args.approval else None
    rejected = []
    for path in args.packages:
        old, new = DIAGNOSE.resolve(path, destination=destination)
        rejected.append(classify(old, new, path, keys_dir=args.keys_dir)[0])
    allocations = plan(TREE, destination, rejected,
                       (DIAGNOSE.UNKNOWN,) if args.accept_unknown else (),
                       approvals=approvals,
                       require_trust=args.keys_dir is not None)
    print(describe(allocations))
    if args.apply:
        apply(TREE, allocations, destination=destination)
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
