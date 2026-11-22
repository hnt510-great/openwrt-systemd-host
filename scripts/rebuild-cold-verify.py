#!/usr/bin/env python3
"""Build input provenance tracking and isolated single-shot cold rebuild (Phase 2b).

Captures verifiable recipe-level build inputs (Makefile, patches, local files,
referenced include/*.mk, relevant .config keys, toolchain fingerprint, and
whitelisted environment variables — never secrets or signing keys) and runs at
most one isolated cold rebuild per conflicting source recipe.

Isolated cold rebuild guarantees:
  * Private temporary build/output directory — never mutates active checkout
    bin/, staging_dir/, .config, or kernel sequence.
  * Bypasses .built stamps, Cargo incremental compilation, sccache, and ccache
    while reusing verified dl/ downloads and read-only toolchain/staging inputs.
  * Distinguishes a genuine fresh compile from a cache hit.
  * Preserves drift forensics (both APKs, input fingerprints, build command,
    and diagnosis report) whenever identical inputs produce different payloads.
"""
import argparse
import datetime
import hashlib
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

TREE = Path(__file__).resolve().parent.parent
APK = TREE / 'staging_dir/host/bin/apk'
DEFAULT_EVIDENCE_DIR = 'tmp/rebuild-evidence'

SCHEMA_VERSION = 1

ENV_WHITELIST = (
    'SOURCE_DATE_EPOCH',
    'MAKEFLAGS',
    'NINJA_ARGS',
    'CARGO_BUILD_JOBS',
    'LANG',
    'LC_ALL',
    'TZ',
)

CACHE_BYPASS_ENV = {
    'CARGO_INCREMENTAL': '0',
    'RUSTC_WRAPPER': '',
    'SCCACHE_DISABLE': '1',
    'CCACHE_DISABLE': '1',
}

HIGH_COST_INCLUDES = (
    'include/rust-package.mk',
    'include/rust-host-build.mk',
    'include/rust-values.mk',
    'include/gnome-rust.mk',
    'include/cargo.mk',
)

HIGH_COST_RECIPE_REGEXES = (
    ('qt', re.compile(r'(?:^|/)(?:qt[56][^/]*|kf[56][^/]*|kwin[^/]*|plasma[^/]*|qtwebengine[^/]*)(?:/|$)', re.I)),
    ('llvm', re.compile(r'(?:^|/)(?:llvm[^/]*|clang[^/]*|lld[^/]*|mesa[^/]*)(?:/|$)', re.I)),
    ('rust', re.compile(r'(?:^|/)(?:rust[^/]*|cargo[^/]*|librsvg|resources|loupe|glycin|papers)(?:/|$)', re.I)),
    ('browser_or_vm', re.compile(r'(?:^|/)(?:webkit[^/]*|firefox[^/]*|chromium[^/]*|qemu[^/]*|gcc[^/]*|glibc[^/]*|linux)(?:/|$)', re.I)),
)


def classify_cold_rebuild_cost(tree, makefile, includes=None):
    """Identify high-cost recipes (Qt, LLVM, Rust, etc.) blocked from automatic cold rebuild by default."""
    norm = str(makefile).replace('\\', '/')
    reasons = []
    for label, pattern in HIGH_COST_RECIPE_REGEXES:
        if pattern.search(norm):
            reasons.append(f'recipe_matches_{label}')
    inc_set = set(includes.keys() if isinstance(includes, dict) else (includes or ()))
    if not inc_set:
        mk_path = Path(tree) / makefile
        if mk_path.is_file():
            inc_set = {str(p.relative_to(Path(tree).resolve()))
                       for p in _referenced_includes(tree, mk_path)
                       if p.is_relative_to(Path(tree).resolve())}
    matched_inc = sorted(inc for inc in HIGH_COST_INCLUDES if inc in inc_set)
    if matched_inc:
        reasons.append('includes_rust_or_heavy_toolchain:' + ','.join(matched_inc))
    return {
        'high_cost': bool(reasons),
        'reasons': reasons,
        'recipe': norm,
    }

_diagnose_spec = importlib.util.spec_from_file_location(
    'cold_verify_diagnose', Path(__file__).with_name('diagnose-apk-rebuild.py'))
DIAGNOSE = importlib.util.module_from_spec(_diagnose_spec)
_diagnose_spec.loader.exec_module(DIAGNOSE)


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


def sha256_file(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic_write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(mode='w', dir=path.parent, delete=False,
                                     prefix='.' + path.name + '.tmp-') as stream:
        tmp = Path(stream.name)
        try:
            stream.write(json.dumps(data, indent=2, sort_keys=True) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
            os.replace(tmp, path)
        finally:
            tmp.unlink(missing_ok=True)


def _walk_files(root):
    root = Path(root)
    if not root.exists():
        return []
    if root.is_file():
        return [root]
    result = []
    for child in sorted(root.rglob('*')):
        if any(part in ('.git', '__pycache__', '.DS_Store') for part in child.parts):
            continue
        if child.is_file() and not child.is_symlink():
            result.append(child)
    return result


def _referenced_includes(tree, makefile_path):
    """Collect include/*.mk files transitively included by a recipe Makefile."""
    tree = Path(tree)
    seen = set()
    pending = [Path(makefile_path)]
    while pending:
        current = pending.pop()
        if not current.is_file():
            continue
        text = current.read_text(errors='replace')
        for match in re.findall(r'include\s+\$\(INCLUDE_DIR\)/([A-Za-z0-9_./-]+)', text):
            inc = tree / 'include' / match
            if inc.is_file() and inc not in seen:
                seen.add(inc)
                pending.append(inc)
    return sorted(seen)


def _read_config_subset(tree, recipe_text, package_names):
    cfg_path = Path(tree) / '.config'
    if not cfg_path.is_file():
        return {}
    all_cfg = {}
    for line in cfg_path.read_text(errors='replace').splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            k, v = line.split('=', 1)
            all_cfg[k] = v
    wanted = set(re.findall(r'CONFIG_[A-Za-z0-9_-]+', recipe_text))
    for pkg in package_names:
        wanted.add('CONFIG_PACKAGE_' + pkg)
    wanted |= {k for k in all_cfg if k.startswith((
        'CONFIG_ARCH', 'CONFIG_LIBC', 'CONFIG_GCC_', 'CONFIG_BINUTILS_',
        'CONFIG_USE_STRIP', 'CONFIG_STRIP_ARGS', 'CONFIG_USE_APK',
        'CONFIG_OPENWRT_SYSTEMD'))}
    return {k: all_cfg[k] for k in sorted(wanted) if k in all_cfg}


def _toolchain_fingerprint(tree):
    info = {}
    apk_bin = Path(tree) / 'staging_dir/host/bin/apk'
    if apk_bin.is_file():
        info['apk_sha256'] = sha256_file(apk_bin)
    for cc_glob in ('staging_dir/toolchain-*/bin/*-gcc',):
        matches = sorted(Path(tree).glob(cc_glob))
        if matches:
            info['target_cc'] = str(matches[0].relative_to(tree))
            try:
                info['target_cc_version'] = subprocess.check_output(
                    [str(matches[0]), '--version'], text=True, stderr=subprocess.STDOUT
                ).splitlines()[0]
            except (OSError, subprocess.CalledProcessError):
                pass
            break
    return info


def capture_build_inputs(tree, makefile, *, package_names=(), effective_release='',
                         jobs=None, env=None, source_date_epoch=None):
    """Build a verifiable, secret-free input fingerprint for one source recipe."""
    tree = Path(tree).resolve()
    mk_path = (tree / makefile).resolve()
    recipe_dir = mk_path.parent
    files = {}
    recipe_text = ''
    for path in _walk_files(recipe_dir):
        rel = str(path.relative_to(tree)) if path.is_relative_to(tree) else str(path)
        files[rel] = {'sha256': sha256_file(path), 'mode': path.stat().st_mode & 0o777}
        if path.name == 'Makefile' or path.suffix == '.mk':
            recipe_text += '\n' + path.read_text(errors='replace')

    includes = {}
    for inc in _referenced_includes(tree, mk_path):
        rel = str(inc.relative_to(tree))
        includes[rel] = sha256_file(inc)
        recipe_text += '\n' + inc.read_text(errors='replace')

    env_src = os.environ if env is None else env
    env_subset = {k: env_src[k] for k in ENV_WHITELIST if k in env_src}
    if source_date_epoch is not None:
        env_subset['SOURCE_DATE_EPOCH'] = str(source_date_epoch)

    ledger = tree / 'configs/apk-elf-rebuilds.mk'
    ledger_sha = sha256_file(ledger) if ledger.is_file() else None

    record = {
        'schema': SCHEMA_VERSION,
        'makefile': str(makefile),
        'package_names': sorted(set(package_names)),
        'effective_release': effective_release,
        'jobs': jobs,
        'files': files,
        'includes': includes,
        'config': _read_config_subset(tree, recipe_text, package_names),
        'toolchain': _toolchain_fingerprint(tree),
        'ledger_sha256': ledger_sha,
        'env_whitelist': env_subset,
    }
    record['input_sha256'] = sha256_bytes(json.dumps(record, sort_keys=True).encode('utf-8'))
    return record


def compare_build_inputs(before, after):
    """Compare two build input fingerprints and return structured differences."""
    if before.get('input_sha256') == after.get('input_sha256'):
        return {'identical': True, 'differences': []}
    diffs = []
    for section in ('files', 'includes', 'config', 'toolchain', 'env_whitelist',
                    'effective_release', 'ledger_sha256', 'jobs'):
        if before.get(section) != after.get(section):
            diffs.append({'section': section, 'before': before.get(section), 'after': after.get(section)})
    return {'identical': False, 'differences': diffs}


def _default_cold_runner(tree, makefile, work_dir, env, jobs):
    """Execute a single isolated cold compile of one recipe without touching active outputs."""
    tree = Path(tree).resolve()
    pkg_dir = Path(makefile).parent
    iso_bin = work_dir / 'bin'
    iso_build = work_dir / 'build_dir'
    iso_bin.mkdir(parents=True, exist_ok=True)
    iso_build.mkdir(parents=True, exist_ok=True)
    cmd = [
        'make',
        f'-j{jobs}',
        f'{pkg_dir}/compile',
        f'BUILD_DIR={iso_build}',
        f'BIN_DIR={iso_bin}',
        'V=s',
    ]
    started = time.monotonic()
    res = subprocess.run(cmd, cwd=tree, env=env, capture_output=True, text=True)
    elapsed = round(time.monotonic() - started, 3)
    return {
        'command': cmd,
        'returncode': res.returncode,
        'elapsed_seconds': elapsed,
        'stdout_tail': res.stdout[-4000:],
        'stderr_tail': res.stderr[-4000:],
        'output_dir': iso_bin,
        'build_dir': iso_build,
    }


def _find_rebuilt_apk(output_dir, filename):
    matches = sorted(Path(output_dir).rglob(filename))
    return matches[0] if matches else None


def cold_rebuild_recipe(tree, makefile, candidate_apks, *, apk=APK, keys_dir=None,
                        evidence_dir=None, jobs=None, runner=None, source_date_epoch=None,
                        allow_high_cost=False, authorized_recipes=()):
    """Perform at most one isolated cold rebuild for a recipe and verify reproducibility.

    High-cost recipes (Qt, LLVM, Rust, etc.) are blocked from automatic cold
    rebuild by default unless explicitly authorized via allow_high_cost=True
    or authorized_recipes; instead, an evidence-backed manual review record is
    returned immediately without invoking the build runner.

    candidate_apks: mapping of {package_name: Path_to_candidate_apk}
    runner: optional callable(tree, makefile, work_dir, env, jobs) -> dict (for testing/injection)
    """
    tree = Path(tree).resolve()
    evidence_root = Path(evidence_dir) if evidence_dir else (tree / DEFAULT_EVIDENCE_DIR)
    jobs = jobs or max(1, min(4, os.cpu_count() or 1))
    pkg_names = sorted(candidate_apks.keys())

    inputs_before = capture_build_inputs(
        tree, makefile, package_names=pkg_names, jobs=jobs,
        source_date_epoch=source_date_epoch)

    cost = classify_cold_rebuild_cost(tree, makefile, includes=inputs_before['includes'])
    auth_set = set(authorized_recipes or ())
    recipe_dir_name = Path(makefile).parent.name
    explicitly_authorized = (
        allow_high_cost
        or str(makefile) in auth_set
        or recipe_dir_name in auth_set
        or any(name in auth_set for name in pkg_names)
    )
    if cost['high_cost'] and not explicitly_authorized:
        review_record = {
            'schema': SCHEMA_VERSION,
            'makefile': str(makefile),
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'status': 'skipped_high_cost_recipe',
            'reproducible': None,
            'cold_build_verified': False,
            'high_cost': cost,
            'input_sha256': inputs_before['input_sha256'],
            'inputs_stable': True,
            'packages': {},
        }
        for pkg_name, cand_path in sorted(candidate_apks.items()):
            cand_sha = sha256_file(cand_path) if Path(cand_path).is_file() else ''
            review_record['packages'][pkg_name] = {
                'status': 'skipped_high_cost_recipe',
                'reproducible': None,
                'cold_build_verified': False,
                'high_cost': cost,
                'candidate_sha256': cand_sha,
                'reason': (
                    f'high-cost recipe ({", ".join(cost["reasons"])}) is blocked from automatic '
                    'cold rebuild by default; review manually with evidence or explicitly authorize'
                ),
            }
        atomic_write_json(
            evidence_root / 'provenance' / f'review-{inputs_before["input_sha256"][:16]}.json',
            {'inputs': inputs_before, 'result': review_record})
        return review_record

    env = {**os.environ, **CACHE_BYPASS_ENV}
    if source_date_epoch is not None:
        env['SOURCE_DATE_EPOCH'] = str(source_date_epoch)

    run_fn = runner or _default_cold_runner
    with tempfile.TemporaryDirectory(prefix='cold-rebuild-') as tmp:
        work_dir = Path(tmp)
        run_result = run_fn(tree, makefile, work_dir, env, jobs)

        inputs_after = capture_build_inputs(
            tree, makefile, package_names=pkg_names, jobs=jobs,
            source_date_epoch=source_date_epoch)
        input_diff = compare_build_inputs(inputs_before, inputs_after)

        base_record = {
            'schema': SCHEMA_VERSION,
            'makefile': str(makefile),
            'timestamp': datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'input_sha256': inputs_before['input_sha256'],
            'inputs_stable': input_diff['identical'],
            'input_differences': input_diff['differences'],
            'cold_build_verified': True,
            'cache_bypass_env': CACHE_BYPASS_ENV,
            'elapsed_seconds': run_result.get('elapsed_seconds', 0.0),
            'returncode': run_result['returncode'],
            'command': run_result.get('command', []),
            'packages': {},
        }

        if not input_diff['identical']:
            base_record['status'] = 'inputs_changed_during_rebuild'
            base_record['reproducible'] = False
            return base_record

        if run_result['returncode'] != 0:
            base_record['status'] = 'cold_rebuild_failed'
            base_record['reproducible'] = False
            base_record['stderr_tail'] = run_result.get('stderr_tail', '')
            return base_record

        all_reproducible = True
        any_drift = False
        for pkg_name, cand_path in sorted(candidate_apks.items()):
            cand_path = Path(cand_path)
            cand_sha = sha256_file(cand_path)
            rebuilt_path = _find_rebuilt_apk(run_result['output_dir'], cand_path.name)
            if rebuilt_path is None:
                all_reproducible = False
                base_record['packages'][pkg_name] = {
                    'status': 'missing_cold_output',
                    'reproducible': False,
                    'candidate_sha256': cand_sha,
                    'cold_sha256': '',
                }
                continue
            cold_sha = sha256_file(rebuilt_path)
            if cand_sha == cold_sha:
                base_record['packages'][pkg_name] = {
                    'status': 'reproduced_exact',
                    'reproducible': True,
                    'exact_bytes': True,
                    'adb_stream_identical': True,
                    'payload_identical': True,
                    'candidate_sha256': cand_sha,
                    'cold_sha256': cold_sha,
                }
                continue

            report = DIAGNOSE.diagnose(cand_path, rebuilt_path, apk=apk, keys_dir=keys_dir)
            if report.adb_stream_identical:
                base_record['packages'][pkg_name] = {
                    'status': 'reproduced_adb_stream',
                    'reproducible': True,
                    'exact_bytes': False,
                    'adb_stream_identical': True,
                    'payload_identical': True,
                    'candidate_sha256': cand_sha,
                    'cold_sha256': cold_sha,
                }
            elif report.verdict == DIAGNOSE.BENIGN:
                base_record['packages'][pkg_name] = {
                    'status': 'reproduced_payload',
                    'reproducible': True,
                    'exact_bytes': False,
                    'adb_stream_identical': False,
                    'payload_identical': True,
                    'candidate_sha256': cand_sha,
                    'cold_sha256': cold_sha,
                    'benign_findings': [f.detail for f in report.findings],
                }
            else:
                all_reproducible = False
                any_drift = True
                ts = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                forensics_dir = evidence_root / 'drift' / f'{pkg_name}-{ts}-{cand_sha[:8]}'
                forensics_dir.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(cand_path, forensics_dir / ('candidate-' + cand_path.name))
                shutil.copyfile(rebuilt_path, forensics_dir / ('cold-' + rebuilt_path.name))
                atomic_write_json(forensics_dir / 'inputs.json', inputs_before)
                atomic_write_json(forensics_dir / 'diagnosis.json', report.to_dict())
                atomic_write_json(forensics_dir / 'run.json', {
                    'command': run_result.get('command', []),
                    'elapsed_seconds': run_result.get('elapsed_seconds', 0.0),
                    'candidate_sha256': cand_sha,
                    'cold_sha256': cold_sha,
                })
                base_record['packages'][pkg_name] = {
                    'status': 'payload_drift',
                    'reproducible': False,
                    'exact_bytes': False,
                    'adb_stream_identical': False,
                    'payload_identical': False,
                    'candidate_sha256': cand_sha,
                    'cold_sha256': cold_sha,
                    'forensics_dir': str(forensics_dir),
                    'first_finding': (report.findings[0].path + ': ' + report.findings[0].detail
                                      if report.findings else 'unknown drift'),
                }

        if any_drift:
            base_record['status'] = 'payload_drift'
            base_record['reproducible'] = False
        elif all_reproducible and base_record['packages']:
            statuses = {p['status'] for p in base_record['packages'].values()}
            base_record['status'] = (
                'reproduced_exact' if statuses == {'reproduced_exact'} else
                'reproduced_adb_stream' if statuses <= {'reproduced_exact', 'reproduced_adb_stream'} else
                'reproduced_payload')
            base_record['reproducible'] = True
        else:
            base_record['status'] = 'incomplete'
            base_record['reproducible'] = False

        atomic_write_json(
            evidence_root / 'provenance' / f'{inputs_before["input_sha256"][:16]}.json',
            {'inputs': inputs_before, 'result': base_record})
        return base_record


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    parser.add_argument('--makefile', required=True, help='Source-Makefile relative to repo root')
    parser.add_argument('--candidate', action='append', required=True,
                        help='NAME=PATH_TO_CANDIDATE.apk (repeatable)')
    parser.add_argument('--keys-dir', type=Path)
    parser.add_argument('--evidence-dir', type=Path)
    parser.add_argument('--jobs', type=int)
    parser.add_argument('--allow-high-cost', action='store_true',
                        help='Explicitly authorize cold rebuild of high-cost recipes (Qt/LLVM/Rust)')
    args = parser.parse_args(argv)
    candidates = {}
    for item in args.candidate:
        name, sep, path = item.partition('=')
        if not sep:
            parser.error(f'Expected NAME=PATH, got {item}')
        candidates[name] = Path(path)
    result = cold_rebuild_recipe(
        TREE, args.makefile, candidates,
        keys_dir=args.keys_dir, evidence_dir=args.evidence_dir, jobs=args.jobs,
        allow_high_cost=args.allow_high_cost)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result.get('reproducible') else 1


if __name__ == '__main__':
    sys.exit(main())
