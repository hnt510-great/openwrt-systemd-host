#!/usr/bin/env python3
"""Phase 2 tests: out-of-APK type ABI evidence (2a) and isolated cold rebuild (2b)."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

TREE = Path(__file__).resolve().parents[2]
APK = TREE / 'staging_dir/host/bin/apk'
GCC = shutil.which('gcc')
STRIP = shutil.which('strip')


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TREE / 'scripts' / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


TYPE_ABI = load('phase2_elf_type_abi', 'elf-type-abi.py')
COLD = load('phase2_rebuild_cold_verify', 'rebuild-cold-verify.py')
DIAGNOSE = load('phase2_diagnose', 'diagnose-apk-rebuild.py')
ALLOCATE = load('phase2_allocate', 'allocate-rebuild-releases.py')
B = load('phase2_build_publish', 'build-and-publish.py')


def build_signed_apk(root, label, name, version, files, signed=True):
    payload = root / f'payload-{label}'
    if payload.exists():
        shutil.rmtree(payload)
    for rel, data in files.items():
        target = payload / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(data, Path):
            shutil.copyfile(data, target)
            target.chmod(0o755)
        else:
            target.write_bytes(data)
    out = root / f'{label}.apk'
    cmd = [
        str(APK), 'mkpkg',
        '--info', f'name:{name}',
        '--info', f'version:{version}',
        '--info', 'arch:x86_64',
        '--info', 'license:MIT',
        '--info', 'description:phase2 test',
        '--files', str(payload),
        '--output', str(out),
    ]
    if signed:
        cmd += ['--sign-key', str(TREE / 'private-key.pem')]
    subprocess.run(cmd, check=True, capture_output=True)
    return out


@unittest.skipUnless(GCC and STRIP and APK.exists()
                     and (TREE / 'public-key.pem').is_file()
                     and (TREE / 'private-key.pem').is_file(),
                     'gcc, strip, host apk, or signing keys not present')
class Phase2aTypeAbiTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='phase2a-abi-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.store = self.root / 'abi-store'
        self.keys = self.root / 'keys'
        self.keys.mkdir()
        shutil.copyfile(TREE / 'public-key.pem', self.keys / 'public-key.pem')

    def compile_lib(self, label, c_source, debug=True):
        src = self.root / f'{label}.c'
        src.write_text(c_source)
        unstripped = self.root / f'{label}.unstripped.so'
        stripped = self.root / f'{label}.so'
        flags = ['-shared', '-fPIC', '-O1', '-Wl,-soname,libdemo.so.1']
        if debug:
            flags.append('-g')
        subprocess.run([GCC, *flags, str(src), '-o', str(unstripped)],
                       check=True, capture_output=True)
        shutil.copyfile(unstripped, stripped)
        subprocess.run([STRIP, '--strip-all', str(stripped)], check=True, capture_output=True)
        return unstripped, stripped

    def test_abidiff_exit_bitmask_decoding(self):
        self.assertEqual(TYPE_ABI.decode_abidiff_exit(0), {
            'raw_code': 0, 'error': False, 'usage_error': False,
            'abi_change': False, 'abi_incompatible_change': False})
        bits = TYPE_ABI.decode_abidiff_exit(TYPE_ABI.ABIDIFF_ABI_CHANGE | TYPE_ABI.ABIDIFF_ABI_INCOMPATIBLE_CHANGE)
        self.assertTrue(bits['abi_change'])
        self.assertTrue(bits['abi_incompatible_change'])
        self.assertFalse(bits['error'])

    def test_same_soname_compatible_impl_change_with_type_abi_and_cold_rebuild(self):
        u1, s1 = self.compile_lib('v1', '''
struct Item { int a; int b; };
int compute(struct Item *p) { return p->a + p->b; }
''')
        u2, s2 = self.compile_lib('v2', '''
struct Item { int a; int b; };
int compute(struct Item *p) { volatile int t = p->a; return t + p->b; }
''')
        self.assertNotEqual(s1.read_bytes(), s2.read_bytes())
        TYPE_ABI.capture_evidence(u1, s1, self.store, package='libdemo', version='1.0-r1', path='usr/lib/libdemo.so.1')
        TYPE_ABI.capture_evidence(u2, s2, self.store, package='libdemo', version='1.0-r1', path='usr/lib/libdemo.so.1')

        apk1 = build_signed_apk(self.root, 'lib-v1', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s1})
        apk2 = build_signed_apk(self.root, 'lib-v2', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s2})

        # With type ABI verified but without cold rebuild -> still review_before_allocate.
        r_no_cold = DIAGNOSE.diagnose(apk1, apk2, APK, keys_dir=self.keys, abi_store=self.store)
        self.assertEqual(r_no_cold.type_abi['status'], 'verified_compatible')
        self.assertEqual(r_no_cold.effective_decision()['action'], DIAGNOSE.ACTION_REVIEW)

        # With both type ABI verified AND cold rebuild reproduced -> allocate_release!
        r_with_cold = DIAGNOSE.diagnose(
            apk1, apk2, APK, keys_dir=self.keys, abi_store=self.store,
            cold_evidence={'status': 'reproduced_exact', 'reproducible': True, 'input_sha256': 'abc'})
        self.assertEqual(r_with_cold.effective_decision()['action'], DIAGNOSE.ACTION_ALLOCATE_RELEASE)
        self.assertEqual(r_with_cold.effective_decision()['reasons'], ['public_lib_impl_reproduced_abi_verified'])

    def test_same_soname_parameter_type_change_is_rejected(self):
        u1, s1 = self.compile_lib('p1', 'int compute(int a, int b) { return a + b; }\n')
        u2, s2 = self.compile_lib('p2', 'int compute(long a, int b) { return (int)a + b; }\n')
        TYPE_ABI.capture_evidence(u1, s1, self.store)
        TYPE_ABI.capture_evidence(u2, s2, self.store)

        apk1 = build_signed_apk(self.root, 'p1', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s1})
        apk2 = build_signed_apk(self.root, 'p2', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s2})

        report = DIAGNOSE.diagnose(
            apk1, apk2, APK, keys_dir=self.keys, abi_store=self.store,
            cold_evidence={'status': 'reproduced_exact', 'reproducible': True})
        self.assertEqual(report.type_abi['status'], 'abi_incompatible_change')
        self.assertEqual(report.effective_decision()['action'], DIAGNOSE.ACTION_REJECT)
        self.assertIn('type_abi_incompatible', report.effective_decision()['reasons'])

    def test_same_soname_struct_layout_change_is_rejected(self):
        u1, s1 = self.compile_lib('s1', '''
struct Item { int a; int b; };
int compute(struct Item *p) { return p->a + p->b; }
''')
        u2, s2 = self.compile_lib('s2', '''
struct Item { int pad; int a; int b; };
int compute(struct Item *p) { return p->a + p->b; }
''')
        TYPE_ABI.capture_evidence(u1, s1, self.store)
        TYPE_ABI.capture_evidence(u2, s2, self.store)

        apk1 = build_signed_apk(self.root, 's1', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s1})
        apk2 = build_signed_apk(self.root, 's2', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s2})

        report = DIAGNOSE.diagnose(apk1, apk2, APK, keys_dir=self.keys, abi_store=self.store)
        self.assertEqual(report.type_abi['status'], 'abi_incompatible_change')
        self.assertEqual(report.effective_decision()['action'], DIAGNOSE.ACTION_REJECT)

    def test_stripped_dwarf_or_missing_evidence_falls_back_to_review(self):
        u1, s1 = self.compile_lib('nd1', 'int compute(int a) { return a + 1; }\n', debug=False)
        u2, s2 = self.compile_lib('nd2', 'int compute(int a) { return a + 2; }\n', debug=False)
        rec1 = TYPE_ABI.capture_evidence(u1, s1, self.store)
        TYPE_ABI.capture_evidence(u2, s2, self.store)
        self.assertFalse(rec1['has_dwarf'])

        apk1 = build_signed_apk(self.root, 'nd1', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s1})
        apk2 = build_signed_apk(self.root, 'nd2', 'libdemo', '1.0-r1', {'usr/lib/libdemo.so.1': s2})

        report = DIAGNOSE.diagnose(
            apk1, apk2, APK, keys_dir=self.keys, abi_store=self.store,
            cold_evidence={'status': 'reproduced_exact', 'reproducible': True})
        self.assertEqual(report.type_abi['status'], 'insufficient_coverage')
        self.assertEqual(report.effective_decision()['action'], DIAGNOSE.ACTION_REVIEW)

        # Mismatched unstripped/stripped binding must fail closed.
        with self.assertRaisesRegex(ValueError, 'does not match'):
            TYPE_ABI.capture_evidence(u1, self.compile_lib('other', 'int other_fn(void) { return 0; }\n')[1], self.store)


@unittest.skipUnless(GCC and STRIP and APK.exists()
                     and (TREE / 'public-key.pem').is_file()
                     and (TREE / 'private-key.pem').is_file(),
                     'gcc, strip, host apk, or signing keys not present')
class Phase2bColdRebuildTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='phase2b-cold-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree = self.root / 'tree'
        self.dest = self.root / 'feeds'
        self.evidence = self.root / 'evidence'
        self.keys = self.root / 'keys'
        self.keys.mkdir()
        shutil.copyfile(TREE / 'public-key.pem', self.keys / 'public-key.pem')

        # Build a minimal OpenWrt-like checkout for input tracking and ledger writes.
        (self.tree / 'include').mkdir(parents=True)
        (self.tree / 'configs').mkdir(parents=True)
        (self.tree / 'tmp').mkdir(parents=True)
        (self.tree / 'package/custom/demo-app/patches').mkdir(parents=True)
        (self.tree / 'include/package.mk').write_text('# package.mk\n')
        (self.tree / 'package/custom/demo-app/Makefile').write_text(
            'include $(INCLUDE_DIR)/package.mk\n'
            'PKG_NAME:=demo-app\n'
            'PKG_VERSION:=1.0\n'
            'PKG_RELEASE:=1\n')
        (self.tree / 'package/custom/demo-app/patches/001-init.patch').write_text('--- a\n+++ b\n')
        (self.tree / '.config').write_text('CONFIG_PACKAGE_demo-app=y\nCONFIG_USE_STRIP=y\n')
        (self.tree / 'configs/apk-elf-rebuilds.mk').write_text('# ledger\n')
        (self.tree / 'tmp/.packageinfo').write_text(
            'Source-Makefile: package/custom/demo-app/Makefile\n'
            'Package: demo-app\n'
            'Version: 1.0-r1\n')
        shutil.copyfile(TREE / 'public-key.pem', self.tree / 'public-key.pem')

    def compile_exe(self, label, c_source):
        src = self.root / f'{label}.c'
        src.write_text(c_source)
        exe = self.root / f'{label}.bin'
        subprocess.run([GCC, '-fPIE', '-pie', '-O1', str(src), '-o', str(exe)],
                       check=True, capture_output=True)
        subprocess.run([STRIP, '--strip-all', str(exe)], check=True, capture_output=True)
        return exe

    def test_input_provenance_tracks_changes_and_excludes_secrets(self):
        env = {'SOURCE_DATE_EPOCH': '1700000000', 'SECRET_KEY': 'super-secret', 'API_TOKEN': 'tok'}
        before = COLD.capture_build_inputs(
            self.tree, 'package/custom/demo-app/Makefile',
            package_names=['demo-app'], env=env)
        self.assertNotIn('SECRET_KEY', before['env_whitelist'])
        self.assertNotIn('API_TOKEN', before['env_whitelist'])
        self.assertEqual(before['env_whitelist']['SOURCE_DATE_EPOCH'], '1700000000')
        self.assertIn('include/package.mk', before['includes'])

        # Modify a patch -> input fingerprint changes and reports 'files'.
        (self.tree / 'package/custom/demo-app/patches/001-init.patch').write_text('--- a\n+++ b\n+new\n')
        after = COLD.capture_build_inputs(
            self.tree, 'package/custom/demo-app/Makefile',
            package_names=['demo-app'], env=env)
        diff = COLD.compare_build_inputs(before, after)
        self.assertFalse(diff['identical'])
        self.assertEqual([d['section'] for d in diff['differences']], ['files'])

    def test_stable_executable_cold_rebuilds_once_and_allocates(self):
        exe1 = self.compile_exe('app1', 'int main(void) { return 0; }\n')
        exe2 = self.compile_exe('app2', 'int main(void) { volatile int x = 7; return x - 7; }\n')
        apk_old = build_signed_apk(self.root, 'demo-app-old', 'demo-app', '1.0-r1', {'usr/bin/demo-app': exe1})
        apk_new = build_signed_apk(self.root, 'demo-app-1.0-r1', 'demo-app', '1.0-r1', {'usr/bin/demo-app': exe2})

        entry, report = ALLOCATE.classify(apk_old, apk_new, 'base/demo-app-1.0-r1.apk',
                                          apk=APK, keys_dir=self.keys)
        # Without cold rebuild, Phase 1 conservative policy requires review.
        self.assertEqual(report.effective_decision()['action'], DIAGNOSE.ACTION_REVIEW)

        runner_calls = []

        def stable_runner(tree, makefile, work_dir, env, jobs):
            runner_calls.append((makefile, dict(env)))
            out_dir = work_dir / 'bin' / 'base'
            out_dir.mkdir(parents=True)
            shutil.copyfile(apk_new, out_dir / apk_new.name)
            return {'returncode': 0, 'elapsed_seconds': 0.05, 'command': ['fake-make'],
                    'output_dir': work_dir / 'bin', 'build_dir': work_dir / 'build_dir'}

        attempts = []

        def publish_once():
            attempts.append(1)
            if len(attempts) == 1:
                raise B.LAN.SameVersionRebuildError('conflict', [entry])
            return {'status': 'published'}

        # Prepare a matching post-bump APK when rebuild runs.
        def fake_make(tree, args):
            out = self.tree / ALLOCATE.PACKAGE_ROOT / 'base'
            out.mkdir(parents=True, exist_ok=True)
            rebuilt = build_signed_apk(self.root, 'demo-app-1.0-r2', 'demo-app', '1.0-r2',
                                       {'usr/bin/demo-app': exe2})
            shutil.copyfile(rebuilt, out / 'demo-app-1.0-r2.apk')

        with patch.object(B, 'run_make', side_effect=fake_make):
            res = B.publish_allocating(
                self.tree, {'destination': self.dest}, publish_once,
                allocate=True, cold_rebuild=True, cold_runner=stable_runner,
                evidence_dir=self.evidence)

        self.assertEqual(res, {'status': 'published'})
        self.assertEqual(len(runner_calls), 1)
        self.assertEqual(runner_calls[0][1]['CARGO_INCREMENTAL'], '0')
        self.assertEqual(runner_calls[0][1]['SCCACHE_DISABLE'], '1')
        self.assertEqual(runner_calls[0][1]['CCACHE_DISABLE'], '1')
        self.assertEqual(runner_calls[0][1]['RUSTC_WRAPPER'], '')
        ledger = (self.tree / 'configs/apk-elf-rebuilds.mk').read_text()
        self.assertIn('ELF_REBUILD_demo-app_1.0-r1:=1.0-r2\n', ledger)

    def test_drifting_executable_writes_zero_ledger_and_saves_forensics(self):
        exe1 = self.compile_exe('d1', 'int main(void) { return 0; }\n')
        exe2 = self.compile_exe('d2', 'int main(void) { volatile int x = 1; return x - 1; }\n')
        exe3 = self.compile_exe('d3', 'int main(void) { volatile int x = 99; return x - 99; }\n')
        apk_old = build_signed_apk(self.root, 'drift-old', 'demo-app', '1.0-r1', {'usr/bin/demo-app': exe1})
        apk_cand = build_signed_apk(self.root, 'demo-app-1.0-r1', 'demo-app', '1.0-r1', {'usr/bin/demo-app': exe2})
        apk_drift = build_signed_apk(self.root, 'drift-cold', 'demo-app', '1.0-r1', {'usr/bin/demo-app': exe3})

        entry, _ = ALLOCATE.classify(apk_old, apk_cand, 'base/demo-app-1.0-r1.apk',
                                     apk=APK, keys_dir=self.keys)

        def drifting_runner(tree, makefile, work_dir, env, jobs):
            out_dir = work_dir / 'bin' / 'base'
            out_dir.mkdir(parents=True)
            shutil.copyfile(apk_drift, out_dir / apk_cand.name)
            return {'returncode': 0, 'elapsed_seconds': 0.05, 'command': ['fake-make'],
                    'output_dir': work_dir / 'bin', 'build_dir': work_dir / 'build_dir'}

        def publish_once():
            raise B.LAN.SameVersionRebuildError('conflict', [entry])

        with patch.object(B, 'run_make') as make, self.assertRaisesRegex(ValueError, 'Refusing'):
            B.publish_allocating(
                self.tree, {'destination': self.dest}, publish_once,
                allocate=True, cold_rebuild=True, cold_runner=drifting_runner,
                evidence_dir=self.evidence)

        make.assert_not_called()
        self.assertEqual((self.tree / 'configs/apk-elf-rebuilds.mk').read_text(), '# ledger\n')
        drift_dirs = list((self.evidence / 'drift').glob('demo-app-*'))
        self.assertEqual(len(drift_dirs), 1)
        self.assertTrue((drift_dirs[0] / 'inputs.json').is_file())
        self.assertTrue((drift_dirs[0] / 'diagnosis.json').is_file())
        self.assertTrue((drift_dirs[0] / 'run.json').is_file())

    def test_hot_build_without_conflict_triggers_zero_cold_rebuilds(self):
        runner = MagicMock()
        res = B.publish_allocating(
            self.tree, {'destination': self.dest}, lambda: {'status': 'published'},
            allocate=True, cold_rebuild=True, cold_runner=runner)
        self.assertEqual(res, {'status': 'published'})
        runner.assert_not_called()

    def test_high_cost_recipes_blocked_by_default_and_allowed_when_explicitly_authorized(self):
        # Create a Rust/Cargo recipe (via include $(INCLUDE_DIR)/gnome-rust.mk) plus Qt & LLVM checks.
        (self.tree / 'include/gnome-rust.mk').write_text('# gnome-rust.mk\n')
        (self.tree / 'package/custom/rust-app').mkdir(parents=True)
        (self.tree / 'package/custom/rust-app/Makefile').write_text(
            'include $(INCLUDE_DIR)/package.mk\n'
            'include $(INCLUDE_DIR)/gnome-rust.mk\n')
        (self.tree / 'tmp/.packageinfo').write_text(
            (self.tree / 'tmp/.packageinfo').read_text() + '\n'
            'Source-Makefile: package/custom/rust-app/Makefile\n'
            'Package: rust-app\n'
            'Version: 1.0-r1\n')

        # Verify cost classifier catches Qt, LLVM, and Rust-include recipes.
        self.assertTrue(COLD.classify_cold_rebuild_cost(self.tree, 'package/custom/qt6base/Makefile')['high_cost'])
        self.assertTrue(COLD.classify_cold_rebuild_cost(self.tree, 'package/custom/llvm/Makefile')['high_cost'])
        self.assertTrue(COLD.classify_cold_rebuild_cost(self.tree, 'package/custom/rust-app/Makefile')['high_cost'])
        self.assertFalse(COLD.classify_cold_rebuild_cost(self.tree, 'package/custom/demo-app/Makefile')['high_cost'])

        exe1 = self.compile_exe('r1', 'int main(void) { return 0; }\n')
        exe2 = self.compile_exe('r2', 'int main(void) { volatile int x = 3; return x - 3; }\n')
        apk_old = build_signed_apk(self.root, 'rust-old', 'rust-app', '1.0-r1', {'usr/bin/rust-app': exe1})
        apk_new = build_signed_apk(self.root, 'rust-app-1.0-r1', 'rust-app', '1.0-r1', {'usr/bin/rust-app': exe2})

        entry, _ = ALLOCATE.classify(apk_old, apk_new, 'base/rust-app-1.0-r1.apk',
                                     apk=APK, keys_dir=self.keys)

        runner = MagicMock()
        # Default: high-cost recipe must NOT run cold rebuild; returns evidence-backed review report.
        cold_blocked = COLD.cold_rebuild_recipe(
            self.tree, 'package/custom/rust-app/Makefile', {'rust-app': apk_new},
            apk=APK, keys_dir=self.keys, evidence_dir=self.evidence, runner=runner)
        runner.assert_not_called()
        self.assertEqual(cold_blocked['status'], 'skipped_high_cost_recipe')
        self.assertIsNone(cold_blocked['reproducible'])
        review_files = list((self.evidence / 'provenance').glob('review-*.json'))
        self.assertTrue(review_files)

        # In publish_allocating without explicit authorization: zero runner calls, zero ledger writes.
        with patch.object(B, 'run_make') as make, self.assertRaisesRegex(ValueError, 'Refusing'):
            B.publish_allocating(
                self.tree, {'destination': self.dest},
                lambda: (_ for _ in ()).throw(B.LAN.SameVersionRebuildError('conflict', [entry])),
                allocate=True, cold_rebuild=True, cold_runner=runner,
                evidence_dir=self.evidence)
        runner.assert_not_called()
        make.assert_not_called()
        self.assertEqual((self.tree / 'configs/apk-elf-rebuilds.mk').read_text(), '# ledger\n')

        # Explicitly authorized recipe: cold rebuild runs once and succeeds!
        def auth_runner(tree, makefile, work_dir, env, jobs):
            out_dir = work_dir / 'bin' / 'base'
            out_dir.mkdir(parents=True)
            shutil.copyfile(apk_new, out_dir / apk_new.name)
            return {'returncode': 0, 'elapsed_seconds': 0.05, 'command': ['fake-make'],
                    'output_dir': work_dir / 'bin', 'build_dir': work_dir / 'build_dir'}

        cold_auth = COLD.cold_rebuild_recipe(
            self.tree, 'package/custom/rust-app/Makefile', {'rust-app': apk_new},
            apk=APK, keys_dir=self.keys, evidence_dir=self.evidence, runner=auth_runner,
            authorized_recipes=['rust-app'])
        self.assertEqual(cold_auth['status'], 'reproduced_exact')
        self.assertTrue(cold_auth['reproducible'])


if __name__ == '__main__':
    unittest.main()
