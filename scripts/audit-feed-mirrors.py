#!/usr/bin/env python3
"""Read-only byte-for-byte replay audit for mirrored feeds against patches/feeds/."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = ROOT / 'configs/feed-mirrors-snapshot.json'


def replay_and_verify(root, feed, spec):
    feed_dir = root / 'feeds' / feed
    if not (feed_dir / '.git').exists():
        return {'feed': feed, 'skipped': True, 'ok': True, 'reason': 'missing feed checkout'}

    patch_path = root / spec['patch']
    if not patch_path.is_file():
        return {'feed': feed, 'ok': False, 'error': f'missing patch file: {spec["patch"]}'}

    upstream = spec.get('upstream', 'origin/master')
    upstream_oid = subprocess.check_output(
        ['git', '-C', str(feed_dir), 'rev-parse', upstream], text=True
    ).strip()
    head_oid = subprocess.check_output(
        ['git', '-C', str(feed_dir), 'rev-parse', 'HEAD'], text=True
    ).strip()
    head_tree = subprocess.check_output(
        ['git', '-C', str(feed_dir), 'rev-parse', 'HEAD^{tree}'], text=True
    ).strip()
    base_oid = spec['base']

    git_dir = Path(subprocess.check_output(
        ['git', '-C', str(feed_dir), 'rev-parse', '--absolute-git-dir'], text=True
    ).strip())

    # Replay base + patch in an isolated temporary object/index directory:
    # zero writes to feeds/<feed> or its .git directory.
    with tempfile.TemporaryDirectory(prefix=f'feed-audit-{feed}-') as td:
        tmp_objects = Path(td) / 'objects'
        tmp_objects.mkdir()
        tmp_index = Path(td) / 'index'
        env = {
            **os.environ,
            'GIT_DIR': str(git_dir),
            'GIT_OBJECT_DIRECTORY': str(tmp_objects),
            'GIT_ALTERNATE_OBJECT_DIRECTORIES': str(git_dir / 'objects'),
            'GIT_INDEX_FILE': str(tmp_index),
        }
        subprocess.run(['git', 'read-tree', base_oid], env=env, check=True, capture_output=True)
        patch_bytes = patch_path.read_bytes()
        if patch_bytes:
            applied = subprocess.run(
                ['git', 'apply', '--cached', '--binary'],
                input=patch_bytes, env=env, capture_output=True,
            )
            if applied.returncode != 0:
                return {
                    'feed': feed, 'ok': False,
                    'base': base_oid, 'upstream': upstream_oid, 'head': head_oid,
                    'error': 'patch failed to apply cleanly to base: ' + applied.stderr.decode(errors='replace').strip(),
                }
        replayed_tree = subprocess.check_output(
            ['git', 'write-tree'], env=env, text=True
        ).strip()
        diffs = []
        if replayed_tree != head_tree:
            raw_diff = subprocess.check_output(
                ['git', 'diff-tree', '-r', '--name-status', replayed_tree, head_tree],
                env=env, text=True,
            )
            diffs = [line for line in raw_diff.splitlines() if line]

    base_matches_upstream = (base_oid == upstream_oid)
    ok = (replayed_tree == head_tree) and base_matches_upstream
    return {
        'feed': feed,
        'patch': spec['patch'],
        'base': base_oid,
        'upstream': upstream_oid,
        'base_matches_upstream': base_matches_upstream,
        'head': head_oid,
        'head_tree': head_tree,
        'replayed_tree': replayed_tree,
        'tree_matches': replayed_tree == head_tree,
        'diffs': diffs,
        'ok': ok,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=ROOT)
    parser.add_argument('--manifest', type=Path, default=None)
    parser.add_argument('--json', action='store_true', dest='as_json')
    args = parser.parse_args(argv)
    root = args.root.resolve()
    manifest_path = (args.manifest or (root / 'configs/feed-mirrors-snapshot.json')).resolve()
    manifest = json.loads(manifest_path.read_text())
    reports = [replay_and_verify(root, feed, spec) for feed, spec in sorted(manifest.items())]
    ok = all(r.get('ok', False) for r in reports)
    if args.as_json:
        print(json.dumps({'ok': ok, 'feeds': reports}, indent=2))
    else:
        for r in reports:
            if r.get('skipped'):
                print(f"feeds/{r['feed']}: skipped ({r['reason']})")
            elif r.get('error'):
                print(f"feeds/{r['feed']}: FAIL ({r['error']})")
            else:
                status = 'OK (exact tree match)' if r['ok'] else 'DRIFT'
                print(f"feeds/{r['feed']}: {status} [base==upstream: {r['base_matches_upstream']}, diffs: {len(r['diffs'])}]")
                for d in r['diffs'][:20]:
                    print(f'  {d}')
    return 0 if ok else 1


if __name__ == '__main__':
    sys.exit(main())
