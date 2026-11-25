#!/usr/bin/env python3
"""Read-only audit tool for upstream merges affecting udev and OpenWrt hotplug.

Compares real before/after Git commits across the main tree and feeds, lists
behavioral changes in hotplug JSON rules, hotplug.json.d fragment installers,
hardware-support packages, /etc/hotplug.d script install paths, procd pinned
versions, and systemd/custom udev rules, and enforces content-addressed
classification so silent behavioral divergence blocks acceptance.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLASSIFICATIONS = ROOT / 'configs/hotplug-merge-classifications.json'
VALID_DISPOSITIONS = ('udev_equivalent', 'compat_bridge', 'not_applicable')


def run_git(repo_path, *args):
    res = subprocess.run(
        ['git', '-C', str(repo_path), *args],
        capture_output=True, text=True, check=False,
    )
    return res.returncode, res.stdout, res.stderr


def git_diff_name_status(repo_path, base_ref, head_ref):
    rc, out, err = run_git(repo_path, 'diff', '--name-status', f'{base_ref}..{head_ref}')
    if rc != 0:
        raise RuntimeError(f'git diff failed in {repo_path} ({base_ref}..{head_ref}): {err.strip()}')
    changes = []
    for line in out.splitlines():
        if not line.strip():
            continue
        parts = line.split('\t')
        status = parts[0]
        if status.startswith(('R', 'C')) and len(parts) >= 3:
            changes.append((status, parts[2], parts[1]))
        elif len(parts) >= 2:
            changes.append((status, parts[1], None))
    return changes


def git_show_text(repo_path, ref, rel_path):
    rc, out, _ = run_git(repo_path, 'show', f'{ref}:{rel_path}')
    return out if rc == 0 else None


def git_show_bytes(repo_path, ref, rel_path):
    res = subprocess.run(
        ['git', '-C', str(repo_path), 'show', f'{ref}:{rel_path}'],
        capture_output=True, check=False,
    )
    return res.stdout if res.returncode == 0 else None


def discover_hotplug_json_files(root):
    """Find every stock/preinit/systemd hotplug JSON and every hotplug.json.d source fragment."""
    found = set()
    for p in (
        'package/system/procd/files/hotplug.json',
        'package/system/procd/files/hotplug-preinit.json',
        'package/system/procd/files/hotplug-systemd.json',
    ):
        if (root / p).is_file():
            found.add(p)

    # Discover every recipe referencing hotplug.json.d across package/ and independent feeds/
    search_roots = [root / 'package']
    feeds_dir = root / 'feeds'
    if feeds_dir.is_dir():
        for feed in sorted(feeds_dir.iterdir()):
            if feed.is_dir() and not feed.is_symlink() and not feed.name.startswith('.'):
                search_roots.append(feed)

    for base in search_roots:
        for mk in base.rglob('Makefile'):
            if 'package/feeds/' in str(mk.relative_to(root)):
                continue
            try:
                text = mk.read_text(encoding='utf-8', errors='replace')
            except OSError:
                continue
            if 'hotplug.json.d' not in text:
                continue
            pkg_dir = mk.parent
            files_dir = pkg_dir / 'files'
            if files_dir.is_dir():
                for jf in sorted(files_dir.glob('*.json')):
                    found.add(str(jf.relative_to(root)))
    return sorted(found)


def extract_procd_pin(text):
    if not text:
        return {}
    info = {}
    for key in ('PKG_SOURCE_DATE', 'PKG_SOURCE_VERSION', 'PKG_RELEASE'):
        m = re.search(rf'^{key}:=(.+)$', text, re.M)
        if m:
            info[key] = m.group(1).strip()
    return info


def audit_repo(name, repo_path, base_ref, head_ref):
    changes = git_diff_name_status(repo_path, base_ref, head_ref)
    report = {
        'repo': name,
        'path': str(repo_path),
        'base': base_ref,
        'head': head_ref,
        'stock_or_preinit_json': [],
        'hotplug_json_d_recipes': [],
        'hardware_support': [],
        'hotplug_d_scripts': [],
        'new_third_party_scripts': [],
        'procd_pin': None,
        'udev_rules': [],
    }

    for status, path, old_path in changes:
        item = {'status': status, 'path': path}
        if old_path:
            item['old_path'] = old_path

        # 1. Stock/preinit/systemd hotplug JSON
        if path in (
            'package/system/procd/files/hotplug.json',
            'package/system/procd/files/hotplug-preinit.json',
            'package/system/procd/files/hotplug-systemd.json',
        ):
            report['stock_or_preinit_json'].append(item)

        # 2. hardware-support package
        if path.startswith('package/system/hardware-support/'):
            report['hardware_support'].append(item)

        # 3. systemd / custom udev rules (exclude polkit JS rules)
        if path == 'package/system/systemd/Makefile':
            report['udev_rules'].append(item)
        elif path.endswith('.rules'):
            content = git_show_text(repo_path, head_ref, path) or git_show_text(repo_path, base_ref, path) or ''
            if 'polkit.addRule' not in content and 'polkit.addAdminRule' not in content:
                report['udev_rules'].append(item)

        # 4. procd pinned version
        if path == 'package/system/procd/Makefile':
            before = extract_procd_pin(git_show_text(repo_path, base_ref, path))
            after = extract_procd_pin(git_show_text(repo_path, head_ref, path))
            if before != after:
                report['procd_pin'] = {'before': before, 'after': after}

        # 5. Inspect diffs for hotplug.json.d and /etc/hotplug.d script installs
        if not path.startswith('scripts/') and (path.endswith('Makefile') or 'hotplug' in path):
            rc, diff_text, _ = run_git(repo_path, 'diff', f'{base_ref}..{head_ref}', '--', path)
            if rc == 0:
                if 'hotplug.json.d' in diff_text:
                    report['hotplug_json_d_recipes'].append(item)
                if 'hotplug.d/' in diff_text or '/hotplug.d' in diff_text or '.hotplug' in path:
                    report['hotplug_d_scripts'].append(item)
                    if status.startswith('A') or re.search(r'^\+.*hotplug\.d/[a-z0-9_-]+', diff_text, re.M):
                        if not path.startswith('package/custom/') and not path.startswith('package/system/procd/'):
                            report['new_third_party_scripts'].append(item)

    return report


def check_classifications(root, class_path):
    data = json.loads(class_path.read_text(encoding='utf-8'))
    entries = data.get('json_files', {})
    discovered = discover_hotplug_json_files(root)

    unclassified = []
    hash_mismatches = []
    invalid_dispositions = []
    classified = []

    for rel in discovered:
        full = root / rel
        digest = hashlib.sha256(full.read_bytes()).hexdigest()
        entry = entries.get(rel)
        if not entry:
            unclassified.append({'path': rel, 'sha256': digest})
            continue
        disp = entry.get('disposition')
        if disp not in VALID_DISPOSITIONS:
            invalid_dispositions.append({'path': rel, 'disposition': disp})
            continue
        if entry.get('sha256') != digest:
            hash_mismatches.append({
                'path': rel,
                'expected_sha256': entry.get('sha256'),
                'actual_sha256': digest,
            })
            continue
        classified.append({
            'path': rel,
            'disposition': disp,
            'sha256': digest,
            'reason': entry.get('reason', ''),
        })

    stale = [p for p in entries if p not in discovered]
    return {
        'discovered_count': len(discovered),
        'classified': classified,
        'unclassified': unclassified,
        'hash_mismatches': hash_mismatches,
        'invalid_dispositions': invalid_dispositions,
        'stale_entries': stale,
        'ok': not (unclassified or hash_mismatches or invalid_dispositions),
    }


def parse_repo_spec(spec):
    # Format: name=path:base:head
    name, rest = spec.split('=', 1)
    parts = rest.rsplit(':', 2)
    if len(parts) != 3:
        raise ValueError(f'Invalid --repo spec (expected NAME=PATH:BASE:HEAD): {spec}')
    return name, Path(parts[0]), parts[1], parts[2]


def default_repos(root):
    specs = []
    rc, _, _ = run_git(root, 'rev-parse', '--verify', 'origin/main')
    if rc == 0:
        specs.append(('main', root, 'origin/main', 'HEAD'))
    feeds_dir = root / 'feeds'
    if feeds_dir.is_dir():
        for feed in sorted(feeds_dir.iterdir()):
            if not (feed / '.git').exists():
                continue
            for upstream in ('origin/master', 'origin/main'):
                rc, _, _ = run_git(feed, 'rev-parse', '--verify', upstream)
                if rc == 0:
                    specs.append((f'feeds/{feed.name}', feed, upstream, 'HEAD'))
                    break
    return specs


def main(argv=None):
    parser = argparse.ArgumentParser(description='Audit upstream merges for udev/hotplug behavioral diffs.')
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--classifications', type=Path, default=DEFAULT_CLASSIFICATIONS)
    parser.add_argument('--repo', action='append', default=[],
                        help='Explicit repo range NAME=PATH:BASE:HEAD (repeatable)')
    parser.add_argument('--json', action='store_true', dest='as_json')
    parser.add_argument('--no-strict', action='store_true')
    args = parser.parse_args(argv)

    repo_specs = [parse_repo_spec(s) for s in args.repo] if args.repo else default_repos(args.root)
    repo_reports = [audit_repo(n, p, b, h) for n, p, b, h in repo_specs]
    class_report = check_classifications(args.root, args.classifications)

    result = {
        'ok': class_report['ok'],
        'classifications': class_report,
        'repos': repo_reports,
    }

    if args.as_json:
        print(json.dumps(result, indent=2, ensure_ascii=False))
    else:
        print(f"Hotplug JSON classifications: {len(class_report['classified'])}/{class_report['discovered_count']} verified")
        if class_report['unclassified']:
            print('UNCLASSIFIED JSON FILES (blocks acceptance):')
            for u in class_report['unclassified']:
                print(f"  - {u['path']} (sha256={u['sha256']})")
        if class_report['hash_mismatches']:
            print('CHANGED JSON CONTENT REQUIRING RE-CLASSIFICATION (blocks acceptance):')
            for m in class_report['hash_mismatches']:
                print(f"  - {m['path']} expected={m['expected_sha256']} actual={m['actual_sha256']}")
        if class_report['invalid_dispositions']:
            print('INVALID DISPOSITIONS (blocks acceptance):')
            for d in class_report['invalid_dispositions']:
                print(f"  - {d['path']}: {d['disposition']}")
        for rep in repo_reports:
            total = sum(len(rep[k]) for k in (
                'stock_or_preinit_json', 'hotplug_json_d_recipes', 'hardware_support',
                'hotplug_d_scripts', 'udev_rules',
            )) + (1 if rep['procd_pin'] else 0)
            print(f"\nRepo {rep['repo']} ({rep['base']}..{rep['head']}): {total} hotplug/udev-relevant change(s)")
            for label, key in (
                ('stock/preinit JSON', 'stock_or_preinit_json'),
                ('hotplug.json.d recipes', 'hotplug_json_d_recipes'),
                ('hardware-support', 'hardware_support'),
                ('hotplug.d scripts', 'hotplug_d_scripts'),
                ('new third-party scripts (smoke required)', 'new_third_party_scripts'),
                ('udev rules', 'udev_rules'),
            ):
                if rep[key]:
                    print(f'  {label}:')
                    for item in rep[key]:
                        print(f"    [{item['status']}] {item['path']}")
            if rep['procd_pin']:
                print(f"  procd pin changed: {rep['procd_pin']['before']} -> {rep['procd_pin']['after']}")

    if not args.no_strict and not result['ok']:
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
