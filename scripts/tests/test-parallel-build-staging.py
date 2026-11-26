#!/usr/bin/env python3
"""Fault-injection and regression tests for parallel build, staging, and packaging fixes."""
import concurrent.futures
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = ROOT / 'scripts'


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def build_shared_lib(cc, path, soname, needed=(), rpath=None, runpath=None):
    path.parent.mkdir(parents=True, exist_ok=True)
    src = path.with_suffix('.c')
    src.write_text('int sym(void) { return 42; }\n')
    cmd = [cc, '-shared', '-nostdlib', '-fPIC', '-Wl,--no-as-needed', f'-Wl,-soname,{soname}', '-o', str(path), str(src)]
    for lib_dir, lib_name in needed:
        cmd.extend([f'-L{lib_dir}', f'-l:{lib_name}'])
    if rpath:
        cmd.append(f'-Wl,--disable-new-dtags,-rpath,{rpath}')
    if runpath:
        cmd.append(f'-Wl,--enable-new-dtags,-rpath,{runpath}')
    subprocess.run(cmd, check=True)
    src.unlink()


class ParallelBuildStagingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix='test-parallel-staging-'))

    def tearDown(self):
        shutil.rmtree(self.tmp, ignore_errors=True)

    # --- Supplemental #1: Legacy co-owners (xfs-admin / xfs-fsck) & conflict ---
    def test_stage_legacy_co_owners_and_conflict(self):
        root = self.tmp / 'staging'
        pkg_dir = root / 'usr/lib/apk/packages'
        pkg_dir.mkdir(parents=True)
        (root / 'usr/sbin').mkdir(parents=True)
        (root / 'usr/sbin/xfs_db').write_bytes(b'SAME-BINARY')
        for name in ('xfs-admin', 'xfs-fsck'):
            (pkg_dir / f'{name}.elf.json').write_text(json.dumps({
                'schema': 1, 'package': name, 'version': '1-r1',
                'files': {'/usr/sbin/xfs_db': {'needed': [], 'soname': None, 'rpath': None, 'runpath': None, 'interpreter': None, 'class': 2, 'machine': 62}},
                'links': {},
            }))
        lock = self.tmp / 'root.flock'
        manifests = root / 'stamp/packages'

        # 1. Conflicting content from xfs-admin MUST fail and preserve original file.
        src_conflict = self.tmp / 'src_conflict'
        (src_conflict / 'usr/sbin').mkdir(parents=True)
        (src_conflict / 'usr/sbin/xfs_db').write_bytes(b'DIFFERENT-BINARY')
        res = subprocess.run([
            sys.executable, str(SCRIPTS / 'stage-package.py'),
            '--root', str(root), '--source', str(src_conflict),
            '--lock', str(lock), '--manifest', str(manifests / 'xfs-admin.list'),
            '--owner', 'xfs-admin', '--legacy-package', 'xfs-admin', '--legacy-base', 'xfs-admin',
        ], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('xfs_db', res.stderr)
        self.assertIn('xfs-admin', res.stderr)
        self.assertIn('xfs-fsck', res.stderr)
        self.assertEqual((root / 'usr/sbin/xfs_db').read_bytes(), b'SAME-BINARY')

        # 2. Identical content from xfs-admin succeeds (co-ownership).
        src_same = self.tmp / 'src_same'
        (src_same / 'usr/sbin').mkdir(parents=True)
        (src_same / 'usr/sbin/xfs_db').write_bytes(b'SAME-BINARY')
        subprocess.run([
            sys.executable, str(SCRIPTS / 'stage-package.py'),
            '--root', str(root), '--source', str(src_same),
            '--lock', str(lock), '--manifest', str(manifests / 'xfs-admin.list'),
            '--owner', 'xfs-admin', '--legacy-package', 'xfs-admin', '--legacy-base', 'xfs-admin',
        ], check=True)

        # 3. Removing xfs-admin leaves xfs_db readable for xfs-fsck.
        subprocess.run([
            sys.executable, str(SCRIPTS / 'stage-package.py'),
            '--root', str(root),
            '--lock', str(lock), '--manifest', str(manifests / 'xfs-admin.list'),
            '--owner', 'xfs-admin', '--legacy-package', 'xfs-admin', '--legacy-base', 'xfs-admin',
        ], check=True)
        self.assertEqual((root / 'usr/sbin/xfs_db').read_bytes(), b'SAME-BINARY')

    # --- Supplemental #2: Legacy ABI suffix change (example6 -> example7 / no suffix) ---
    def test_stage_legacy_abi_suffix_upgrade_cleans_old_files(self):
        root = self.tmp / 'staging'
        pkg_dir = root / 'usr/lib/apk/packages'
        pkg_dir.mkdir(parents=True)
        (root / 'usr/lib/old.so').write_bytes(b'OLD-LIB')
        (pkg_dir / 'example6.elf.json').write_text(json.dumps({
            'schema': 1, 'package': 'example6', 'version': '6-r1',
            'files': {'/usr/lib/old.so': {'needed': [], 'soname': 'old.so', 'rpath': None, 'runpath': None, 'interpreter': None, 'class': 2, 'machine': 62}},
            'links': {},
        }))
        lock = self.tmp / 'root.flock'
        manifests = root / 'stamp/packages'
        src_v7 = self.tmp / 'src_v7'
        (src_v7 / 'usr/lib').mkdir(parents=True)
        (src_v7 / 'usr/lib/new.so').write_bytes(b'NEW-LIB')

        subprocess.run([
            sys.executable, str(SCRIPTS / 'stage-package.py'),
            '--root', str(root), '--source', str(src_v7),
            '--lock', str(lock), '--manifest', str(manifests / 'example.list'),
            '--owner', 'example', '--legacy-package', 'example7', '--legacy-base', 'example',
        ], check=True)

        self.assertFalse((root / 'usr/lib/old.so').exists())
        self.assertFalse((pkg_dir / 'example6.elf.json').exists())
        self.assertEqual((root / 'usr/lib/new.so').read_bytes(), b'NEW-LIB')

    # --- Reader auto-recovery on interrupted .stage-pending ---
    def test_elf_abi_reader_recovers_pending_staging(self):
        root = self.tmp / 'staging'
        manifests = root / 'stamp/packages'
        manifests.mkdir(parents=True)
        (root / 'usr/lib/apk/packages').mkdir(parents=True)
        (root / 'usr/lib/good.txt').write_text('BEFORE')

        # Create a simulated interrupted transaction in .stage-pending.
        work = manifests / '.stage-interrupted'
        (work / 'backup/usr/lib').mkdir(parents=True)
        os.link(root / 'usr/lib/good.txt', work / 'backup/usr/lib/good.txt')
        (root / 'usr/lib/good.txt').unlink()
        (root / 'usr/lib/good.txt').write_text('PARTIAL-CORRUPT')
        (work / 'journal').write_text(json.dumps([['usr/lib/good.txt', 'file']]))
        (manifests / '.stage-pending').symlink_to(work.name)

        pkg_root = self.tmp / 'pkg_root'
        pkg_root.mkdir()
        lock = self.tmp / 'root.flock'
        subprocess.run([
            sys.executable, str(SCRIPTS / 'elf-abi.py'),
            '--root', str(pkg_root), '--package', 'reader', '--version', '1-r1',
            '--staging-root', str(root), '--staging-lock', str(lock),
            '--depends-output', str(self.tmp / 'elf.depends'),
            '--provides-output', str(self.tmp / 'elf.provides'),
        ], check=True)

        self.assertFalse((manifests / '.stage-pending').is_symlink())
        self.assertEqual((root / 'usr/lib/good.txt').read_text(), 'BEFORE')

    # --- P0 #4: Deterministic RPATH across PYTHONHASHSEED & record order ---
    def test_elf_abi_deterministic_rpath_and_private_stamp(self):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('host cc not available')
        staging = self.tmp / 'staging'
        priv_a = staging / 'usr/lib/priv-a'
        priv_b = staging / 'usr/lib/priv-b'
        build_shared_lib(cc, priv_a / 'libdup.so', 'libdup.so')
        build_shared_lib(cc, priv_b / 'libdup.so', 'libdup.so')

        elf_abi = load_module('elf_abi', SCRIPTS / 'elf-abi.py')
        inv_a = elf_abi.inspect(staging)
        # Split into two package records in staging.
        pkg_dir = staging / 'usr/lib/apk/packages'
        pkg_dir.mkdir(parents=True)
        rec_a = {'schema': 1, 'package': 'prov-a', 'version': '1-r1',
                 'files': {'/usr/lib/priv-a/libdup.so': inv_a['files']['/usr/lib/priv-a/libdup.so']}, 'links': {}}
        rec_b = {'schema': 1, 'package': 'prov-b', 'version': '1-r1',
                 'files': {'/usr/lib/priv-b/libdup.so': inv_a['files']['/usr/lib/priv-b/libdup.so']}, 'links': {}}
        (pkg_dir / 'prov-a.elf.json').write_text(json.dumps(rec_a))
        (pkg_dir / 'prov-b.elf.json').write_text(json.dumps(rec_b))

        consumer_root = self.tmp / 'consumer'
        build_shared_lib(
            cc, consumer_root / 'usr/lib/libcons.so', 'libcons.so',
            needed=[(priv_b, 'libdup.so')],
            rpath='/usr/lib/priv-b:/usr/lib/priv-a',
        )
        results = set()
        for seed in ('1', '2', '42', '999'):
            dep_out = self.tmp / f'dep-{seed}'
            prov_out = self.tmp / f'prov-{seed}'
            priv_stamp = self.tmp / f'priv-{seed}'
            subprocess.run([
                sys.executable, str(SCRIPTS / 'elf-abi.py'),
                '--root', str(consumer_root), '--package', 'consumer', '--version', '1-r1',
                '--staging-root', str(staging),
                '--depends-output', str(dep_out), '--provides-output', str(prov_out),
                '--private-stamp', str(priv_stamp),
            ], check=True, env={**os.environ, 'PYTHONHASHSEED': seed})
            results.add(dep_out.read_text().strip())
        # Loader order is /usr/lib/priv-b first, so prov-b=1-r1 must win every time.
        self.assertEqual(results, {'prov-b=1-r1'})

        # Verify --private-stamp changes when private lib provider version bumps, while .sonames stays same.
        prov_pkg = self.tmp / 'prov_pkg'
        build_shared_lib(cc, prov_pkg / 'usr/lib/priv-a/libdup.so', 'libdup.so')
        sonames = self.tmp / 'prov.sonames'
        pstamp = self.tmp / 'prov.private'
        subprocess.run([
            sys.executable, str(SCRIPTS / 'elf-abi.py'),
            '--root', str(prov_pkg), '--package', 'prov-a', '--version', '1-r1',
            '--depends-output', str(self.tmp / 'p.d'), '--provides-output', str(self.tmp / 'p.p'),
            '--stamp', str(sonames), '--private-stamp', str(pstamp),
        ], check=True)
        sonames_v1 = sonames.read_text()
        pstamp_v1 = pstamp.read_text()
        subprocess.run([
            sys.executable, str(SCRIPTS / 'elf-abi.py'),
            '--root', str(prov_pkg), '--package', 'prov-a', '--version', '1-r2',
            '--depends-output', str(self.tmp / 'p.d'), '--provides-output', str(self.tmp / 'p.p'),
            '--stamp', str(sonames), '--private-stamp', str(pstamp),
        ], check=True)
        self.assertEqual(sonames.read_text(), sonames_v1)
        self.assertNotEqual(pstamp.read_text(), pstamp_v1)
        self.assertEqual(pstamp.read_text().strip(), 'prov-a=1-r2')

    # --- Supplemental #4: Arbitrary-depth dependency closure with diamonds and cycles ---
    def test_find_library_dependency_names_deep_diamond_and_cycle(self):
        source = (ROOT / 'include/package.mk').read_text()
        closure = source.split('find_library_dependency_names =', 1)[1].split('find_library_dependencies =', 1)[0]
        makefile = (
            ''.join(f'Package/p{i}/depends := p{i+1}\n' for i in range(10))
            + 'Package/p3/depends += p6\n'  # diamond
            + 'Package/p8/depends += p2\n'  # cycle
            + 'find_library_dependency_names =' + closure
            + '\nall:\n\t@echo $(call find_library_dependency_names,p0)\n'
        )
        res = subprocess.run(['make', '-rRsf', '-'], cwd=self.tmp, input=makefile, text=True, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        got = set(res.stdout.strip().split())
        self.assertEqual(got, {f'p{i}' for i in range(1, 11)})

    # --- Supplemental #3: verify-install-set.py rejects missing .install ---
    def test_verify_install_set_rejects_missing(self):
        present = self.tmp / 'present.install'
        missing = self.tmp / 'missing.install'
        present.write_text('pkg-a\n')
        out = self.tmp / 'pkgs.txt'
        res = subprocess.run([
            sys.executable, str(SCRIPTS / 'verify-install-set.py'),
            '--output-pkgs', str(out), '--install-files', str(present), str(missing),
        ], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('missing.install', res.stderr)

        missing.write_text('pkg-b\n')
        res2 = subprocess.run([
            sys.executable, str(SCRIPTS / 'verify-install-set.py'),
            '--output-pkgs', str(out), '--install-files', str(present), str(missing),
        ], capture_output=True, text=True)
        self.assertEqual(res2.returncode, 0, res2.stderr)
        self.assertEqual(out.read_text().splitlines(), ['pkg-a', 'pkg-b'])

    # --- P0 #7: apk-index.py merge conflict detection ---
    def test_apk_index_merge_conflict_vs_identical(self):
        feed_a = self.tmp / 'feed_a'
        feed_b = self.tmp / 'feed_b'
        dest = self.tmp / 'all'
        feed_a.mkdir()
        feed_b.mkdir()
        (feed_a / 'foo-1.apk').write_bytes(b'IDENTICAL')
        (feed_b / 'foo-1.apk').write_bytes(b'IDENTICAL')
        subprocess.run([
            sys.executable, str(SCRIPTS / 'apk-index.py'), 'merge',
            '--dest', str(dest), '--ext', 'apk', str(feed_a), str(feed_b),
        ], check=True)
        self.assertTrue((dest / 'foo-1.apk').is_symlink())

        (feed_b / 'foo-1.apk').write_bytes(b'DIFFERENT')
        res = subprocess.run([
            sys.executable, str(SCRIPTS / 'apk-index.py'), 'merge',
            '--dest', str(dest), '--ext', 'apk', str(feed_a), str(feed_b),
        ], capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('Conflicting package filename', res.stderr)

    # --- P0 #8: download.pl concurrency and preserve-on-mismatch ---
    def test_download_pl_preserves_existing_on_mismatch_and_concurrent_ok(self):
        dl = self.tmp / 'dl'
        dl.mkdir()
        payload = b'good-archive-data'
        good_hash = hashlib.sha256(payload).hexdigest()
        bad_hash = '0' * 64
        (dl / 'sample.tar.gz').write_bytes(payload)

        # Hash mismatch must fail AND preserve existing archive.
        res = subprocess.run(
            [str(SCRIPTS / 'download.pl'), str(dl), 'sample.tar.gz', bad_hash],
            capture_output=True, text=True,
        )
        self.assertNotEqual(res.returncode, 0)
        self.assertEqual((dl / 'sample.tar.gz').read_bytes(), payload)

        # Concurrent checks of same file must all succeed.
        def check_once():
            r = subprocess.run(
                [str(SCRIPTS / 'download.pl'), str(dl), 'sample.tar.gz', good_hash],
                capture_output=True, text=True,
            )
            return r.returncode, r.stderr

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            futs = [pool.submit(check_once) for _ in range(4)]
            for f in futs:
                rc, err = f.result()
                self.assertEqual(rc, 0, err)

    # --- P0 #9: rstrip.sh, gen-dependencies.sh, clean-package.sh fail-fast ---
    def test_fail_fast_strip_gendep_clean(self):
        cc = shutil.which('cc')
        if not cc:
            self.skipTest('host cc not available')
        elf_dir = self.tmp / 'elfs'
        build_shared_lib(cc, elf_dir / 'libtest.so', 'libtest.so')

        # rstrip.sh with STRIP=false must fail.
        r1 = subprocess.run(
            [str(SCRIPTS / 'rstrip.sh'), str(elf_dir)],
            env={**os.environ, 'STRIP': 'false'},
            capture_output=True, text=True,
        )
        self.assertNotEqual(r1.returncode, 0)

        # gen-dependencies.sh with READELF=/bin/false must fail.
        r2 = subprocess.run(
            [str(SCRIPTS / 'gen-dependencies.sh'), str(elf_dir)],
            env={**os.environ, 'READELF': '/bin/false', 'TMP_DIR': str(self.tmp)},
            capture_output=True, text=True,
        )
        self.assertNotEqual(r2.returncode, 0)

        # clean-package.sh keeps non-empty shared dir.
        stage = self.tmp / 'clean_stage'
        (stage / 'usr/lib').mkdir(parents=True)
        (stage / 'usr/lib/mine').write_text('a')
        (stage / 'usr/lib/shared').write_text('b')
        lst = self.tmp / 'pkg.list'
        lst.write_text('./usr/lib/mine\n./usr/lib\n./usr\n')
        subprocess.run([str(SCRIPTS / 'clean-package.sh'), str(lst), str(stage)], check=True)
        self.assertFalse((stage / 'usr/lib/mine').exists())
        self.assertTrue((stage / 'usr/lib/shared').exists())

    # --- P1 #1: Stable checkout lock survives rm -rf tmp and verifies inheritance ---
    def test_checkout_lock_survives_dirclean_and_inherits(self):
        tree = self.tmp / 'checkout'
        (tree / '.git').mkdir(parents=True)
        (tree / 'tmp').mkdir()
        cl = load_module('checkout_lock', SCRIPTS / 'checkout-lock.py')

        with cl.acquire_checkout_lock(tree) as (fd, ident, lock_path):
            self.assertFalse(lock_path.is_relative_to(tree / 'tmp'))
            shutil.rmtree(tree / 'tmp')
            (tree / 'tmp').mkdir()
            # A second non-inheriting holder MUST fail with BlockingIOError.
            with self.assertRaises(BlockingIOError):
                with cl.acquire_checkout_lock(tree, nonblocking=True):
                    pass
            # Inheriting child with matching FD & ID MUST succeed without deadlocking.
            os.set_inheritable(fd, True)
            env = {**os.environ, cl.ENV_FD: str(fd), cl.ENV_ID: ident}
            res = subprocess.run(
                [sys.executable, str(SCRIPTS / 'checkout-lock.py'), '--tree', str(tree), '--nonblocking', '--', 'true'],
                env=env, pass_fds=(fd,),
            )
            self.assertEqual(res.returncode, 0)

    # --- P1 #7: Rootfs cache key boundary safety ---
    def test_rootfs_cache_key_boundary_safe(self):
        ov1 = self.tmp / 'ov1'
        ov2 = self.tmp / 'ov2'
        ov1.mkdir()
        ov2.mkdir()
        (ov1 / 'a').write_text('A')
        (ov1 / 'b').write_text('BC')
        (ov2 / 'a').write_text('AB')
        (ov2 / 'b').write_text('C')
        k1 = subprocess.check_output([
            sys.executable, str(SCRIPTS / 'rootfs-cache-key.py'),
            '--install-args', 'base-files=1', '--overlay-dir', str(ov1),
        ], text=True).strip()
        k2 = subprocess.check_output([
            sys.executable, str(SCRIPTS / 'rootfs-cache-key.py'),
            '--install-args', 'base-files=1', '--overlay-dir', str(ov2),
        ], text=True).strip()
        self.assertNotEqual(k1, k2)

    # --- P1 #3: subdir_variants does not leak BUILD_VARIANT to unrelated deps ---
    def test_subdir_variants_isolation(self):
        source = (ROOT / 'include/subdir.mk').read_text()
        line = next(l for l in source.splitlines() if l.startswith('subdir_variants ='))
        makefile = (
            line + '\n'
            'BUILD_VARIANT := full\n'
            'package/weechat/variants := full light\n'
            'package/libfoo/variants :=\n'
            'all:\n'
            '\t@echo "weechat=$(call subdir_variants,package/weechat) libfoo=$(call subdir_variants,package/libfoo)"\n'
        )
        res = subprocess.run(['make', '-rRsf', '-'], cwd=self.tmp, input=makefile, text=True, capture_output=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(res.stdout.strip(), 'weechat=full libfoo=__default')

    def test_stage_sqlite_migration_and_joint_crash_recovery(self):
        import sqlite3

        root = self.tmp / 'staging'
        manifests = root / 'stamp/packages'
        manifests.mkdir(parents=True)
        (root / 'usr/bin').mkdir(parents=True)
        (root / 'usr/bin/shared-tool').write_bytes(b'V1')
        (root / 'usr/bin/other-tool').write_bytes(b'OTHER')
        # Seed a legacy .owners.json to verify one-time migration to .owners.db.
        legacy_index = {
            'schema': 1,
            'paths': {
                'usr/bin/shared-tool': ['pkg-a', 'pkg-b'],
                'usr/bin/other-tool': ['pkg-b'],
            },
            'owners': {
                'pkg-a': ['usr/bin/shared-tool'],
                'pkg-b': ['usr/bin/other-tool', 'usr/bin/shared-tool'],
            },
            'meta': {'pkg-a': {'package': 'pkg-a', 'base': 'pkg-a'}, 'pkg-b': {'package': 'pkg-b', 'base': 'pkg-b'}},
        }
        (manifests / '.owners.json').write_text(json.dumps(legacy_index))
        lock = self.tmp / 'root.flock'

        # Commit pkg-a with an extra file; should migrate .owners.json -> .owners.db.
        src = self.tmp / 'src_a'
        (src / 'usr/bin').mkdir(parents=True)
        (src / 'usr/bin/shared-tool').write_bytes(b'V1')
        (src / 'usr/bin/only-a').write_bytes(b'ONLY-A')
        subprocess.run([
            sys.executable, str(SCRIPTS / 'stage-package.py'),
            '--root', str(root), '--source', str(src),
            '--lock', str(lock), '--manifest', str(manifests / 'pkg-a.list'),
            '--owner', 'pkg-a',
        ], check=True)
        self.assertTrue((manifests / '.owners.db').is_file())
        self.assertFalse((manifests / '.owners.json').exists())

        # Simulate a crash AFTER SQLite commit succeeded but BEFORE .stage-pending unlink.
        stage_mod = load_module('stage_pkg_recovery', SCRIPTS / 'stage-package.py')
        work = manifests / '.stage-post-db-crash'
        (work / 'backup/usr/bin').mkdir(parents=True)
        os.link(root / 'usr/bin/only-a', work / 'backup/usr/bin/only-a')
        (root / 'usr/bin/only-a').unlink()
        (root / 'usr/bin/only-a').write_bytes(b'CORRUPT-V2')
        (root / 'usr/bin/new-v2').write_bytes(b'NEW-V2')
        conn = sqlite3.connect(str(manifests / '.owners.db'))
        with conn:
            conn.execute("INSERT INTO ownership (path, owner_id) VALUES ('usr/bin/new-v2', 'pkg-a')")
        conn.close()
        (work / 'journal').write_text(json.dumps({
            'fs': [['usr/bin/only-a', 'file'], ['usr/bin/new-v2', 'absent']],
            'db_undo': {
                'db': 'stamp/packages/.owners.db',
                'delete_owners': ['pkg-a'],
                'restore_owners': {'pkg-a': ['usr/bin/only-a', 'usr/bin/shared-tool']},
                'restore_meta': {'pkg-a': json.dumps({'package': 'pkg-a', 'base': 'pkg-a'}, sort_keys=True)},
            },
        }))
        (manifests / '.stage-pending').symlink_to(work.name)

        # Recovery must revert BOTH the filesystem AND the SQLite ownership DB.
        self.assertTrue(stage_mod.recover_if_pending(root, manifests))
        self.assertFalse((manifests / '.stage-pending').is_symlink())
        self.assertEqual((root / 'usr/bin/only-a').read_bytes(), b'ONLY-A')
        self.assertFalse((root / 'usr/bin/new-v2').exists())
        conn = sqlite3.connect(str(manifests / '.owners.db'))
        rows = sorted(r[0] for r in conn.execute("SELECT path FROM ownership WHERE owner_id = 'pkg-a'"))
        conn.close()
        self.assertEqual(rows, ['usr/bin/only-a', 'usr/bin/shared-tool'])

    def test_config_packages_stamp_ignores_kernel_sequence_but_rebuilds_preinit_timeout(self):
        # Verify base-files declares CONFIG_TARGET_PREINIT_TIMEOUT in PKG_CONFIG_DEPENDS.
        base_mk = (ROOT / 'package/base-files/Makefile').read_text()
        self.assertIn('CONFIG_TARGET_PREINIT_TIMEOUT', base_mk.split('include $(INCLUDE_DIR)/package.mk', 1)[0])

        # Extract the ACTUAL .config-packages rule from include/package-pack.mk (not a copy).
        pack_mk = (ROOT / 'include/package-pack.mk').read_text()
        marker = '$(TMP_DIR)/.config-packages:'
        rule_block = pack_mk[pack_mk.index(marker):].split('\nendif', 1)[0]

        # Wrap grep in PATH to count how many times the 391 KB .config is scanned.
        shim_bin = self.tmp / 'shim_bin'
        shim_bin.mkdir()
        grep_log = self.tmp / 'grep.count'
        real_grep = shutil.which('grep')
        shim_grep = shim_bin / 'grep'
        shim_grep.write_text(f'#!/bin/sh\necho x >> "{grep_log}"\nexec "{real_grep}" "$@"\n')
        shim_grep.chmod(0o755)
        env = {**os.environ, 'PATH': f'{shim_bin}:{os.environ["PATH"]}'}

        cfg = self.tmp / '.config'
        cfg.write_text('CONFIG_OPENWRT_KERNEL_SEQUENCE=87\nCONFIG_TARGET_PREINIT_TIMEOUT=4\n')
        mk = (
            f'TOPDIR := {self.tmp}\n'
            f'TMP_DIR := {self.tmp}/tmp\n'
            + rule_block + '\n'
            '$(TMP_DIR)/pkg.installed: $(TMP_DIR)/.config-packages\n'
            '\t@echo REBUILT >> $(TMP_DIR)/events\n'
            '\t@touch $@\n'
            'FORCE:\n'
        )
        run_mk = lambda: subprocess.run(['make', '-rRsf', '-', f'{self.tmp}/tmp/pkg.installed'],
                                        cwd=self.tmp, input=mk, text=True, check=True, capture_output=True, env=env)
        run_mk()
        self.assertEqual((self.tmp / 'tmp/events').read_text().splitlines(), ['REBUILT'])
        self.assertEqual(len(grep_log.read_text().splitlines()), 1)

        # 1. Changing ONLY CONFIG_OPENWRT_KERNEL_SEQUENCE must NOT rebuild unrelated package,
        #    and 3 consecutive make runs must only invoke grep ONCE (not 3 times).
        time.sleep(0.02)
        cfg.write_text('CONFIG_OPENWRT_KERNEL_SEQUENCE=88\nCONFIG_TARGET_PREINIT_TIMEOUT=4\n')
        grep_log.unlink()
        for _ in range(3):
            run_mk()
        self.assertEqual((self.tmp / 'tmp/events').read_text().splitlines(), ['REBUILT'])
        self.assertEqual(len(grep_log.read_text().splitlines()), 1)

        # 2. Changing CONFIG_TARGET_PREINIT_TIMEOUT MUST re-scan and rebuild.
        time.sleep(0.02)
        cfg.write_text('CONFIG_OPENWRT_KERNEL_SEQUENCE=88\nCONFIG_TARGET_PREINIT_TIMEOUT=6\n')
        run_mk()
        self.assertEqual((self.tmp / 'tmp/events').read_text().splitlines(), ['REBUILT', 'REBUILT'])
        self.assertEqual(len(grep_log.read_text().splitlines()), 2)


if __name__ == '__main__':
    unittest.main()
