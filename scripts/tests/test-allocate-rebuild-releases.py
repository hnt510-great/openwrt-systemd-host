#!/usr/bin/env python3
"""Automatic ELF rebuild ledger allocation for same-version rebuilds."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

TREE = Path(__file__).resolve().parents[2]


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, TREE / 'scripts' / filename)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


A = load('allocate_rebuilds_test', 'allocate-rebuild-releases.py')
B = load('allocate_build_publish_test', 'build-and-publish.py')

PACKAGEINFO = '''Source-Makefile: package/custom/nautilus/Makefile
Package: nautilus
Version: 51.1-r3

Source-Makefile: package/feeds/packages/samba4/Makefile
Package: samba4-libs
Version: 4.24.5-r5

Package: samba4-server
Version: 4.24.5-r5

Source-Makefile: package/system/mtd/Makefile
Package: mtd
Version: 29
'''

LEDGER = '''# header
ELF_REBUILD_samba4-libs_4.24.5-r2:=4.24.5-r4
ELF_REBUILD_samba4-libs_4.24.5-r3:=4.24.5-r4
ELF_DEP_samba4-libs_4.24.5-r3:=samba4-libs=4.24.5-r4
ELF_REBUILD_mtd_29:=29-r2
'''


def entry(path, name, version, verdict='change', so_changed=False):
    return {'path': path, 'name': name, 'version': version, 'verdict': verdict,
            'so_changed': so_changed, 'so_removed': [], 'so_added': []}


class AllocationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='allocate-rebuilds-')
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.tree, self.destination = root / 'tree', root / 'feeds'
        (self.tree / 'tmp').mkdir(parents=True)
        (self.tree / 'configs').mkdir()
        (self.tree / 'tmp/.packageinfo').write_text(PACKAGEINFO)
        (self.tree / A.LEDGER).write_text(LEDGER)
        self.base = self.tree / A.PACKAGE_ROOT / 'base'
        self.base.mkdir(parents=True)
        for snapshot, files in (('20261101T000000Z', ['nautilus-51.1-r2.apk',
                                                       'samba4-libs-4.24.5-r1.apk']),
                                ('20261108T000000Z', ['nautilus-51.1-r3.apk',
                                                       'samba4-libs-4.24.5-r5.apk',
                                                       'nautilus-extra-51.1-r9.apk'])):
            repository = self.destination / 'public/snapshots' / snapshot / 'base'
            repository.mkdir(parents=True)
            for name in files:
                (repository / name).touch()
        (self.base / 'nautilus-51.1-r3.apk').touch()
        (self.base / 'samba4-libs-4.24.5-r5.apk').touch()

    def ledger(self):
        return (self.tree / A.LEDGER).read_text()

    def test_allocates_next_free_release_beyond_published_built_and_ledger(self):
        plan = A.plan(self.tree, self.destination, [
            entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3'),
            entry('packages/samba4-libs-4.24.5-r5.apk', 'samba4-libs', '4.24.5-r5', 'change', True),
            entry('base/mtd-29-r2.apk', 'mtd', '29-r2')])
        self.assertEqual({a['name']: a['release'] for a in plan},
                         {'nautilus': '51.1-r4', 'samba4-libs': '4.24.5-r6', 'mtd': '29-r3'})
        self.assertEqual(A.rebuild_targets(plan), [
            'package/custom/nautilus/compile', 'package/feeds/packages/samba4/compile',
            'package/system/mtd/compile'])

    def test_unknown_with_so_changed_is_refused(self):
        self.assertFalse(A.eligible({'verdict': 'unknown', 'so_changed': True}))
        with self.assertRaisesRegex(ValueError, 'Refusing'):
            A.plan(self.tree, self.destination, [
                entry('packages/samba4-libs-4.24.5-r5.apk', 'samba4-libs', '4.24.5-r5', 'unknown', True)])

    def test_unrelated_package_with_name_prefix_does_not_reserve(self):
        plan = A.plan(self.tree, self.destination,
                      [entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3')])
        self.assertEqual(plan[0]['release'], '51.1-r4')

    def test_refuses_benign_and_unknown_without_dependency_change(self):
        for verdict in ('benign', 'unknown'):
            with self.subTest(verdict=verdict), self.assertRaisesRegex(ValueError, 'Refusing'):
                A.plan(self.tree, self.destination,
                       [entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3', verdict)])
        self.assertEqual(self.ledger(), LEDGER)

    def test_unknown_is_allocated_only_when_accepted(self):
        plan = A.plan(self.tree, self.destination,
                      [entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3', 'unknown')],
                      accept=('unknown',))
        self.assertEqual(plan[0]['release'], '51.1-r4')
        with self.assertRaisesRegex(ValueError, 'Refusing'):
            A.plan(self.tree, self.destination,
                   [entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3', 'benign')],
                   accept=('unknown',))

    def test_refuses_a_version_that_is_not_the_current_effective_version(self):
        with self.assertRaisesRegex(ValueError, 'not the current effective version'):
            A.plan(self.tree, self.destination,
                   [entry('base/nautilus-51.1-r2.apk', 'nautilus', '51.1-r2')])

    def test_apply_updates_only_current_recipe_keys_and_appends_once(self):
        plan = A.plan(self.tree, self.destination, [
            entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3'),
            entry('base/samba4-libs-4.24.5-r5.apk', 'samba4-libs', '4.24.5-r5'),
            entry('base/mtd-29-r2.apk', 'mtd', '29-r2')])
        A.apply(self.tree, plan, today='2026-11-09')
        text = self.ledger()
        # Older keys keep reserving their published outputs.
        self.assertIn('ELF_REBUILD_samba4-libs_4.24.5-r3:=4.24.5-r4\n', text)
        self.assertIn('ELF_DEP_samba4-libs_4.24.5-r3:=samba4-libs=4.24.5-r4\n', text)
        self.assertIn('ELF_REBUILD_mtd_29:=29-r3\n', text)
        self.assertEqual(text.count('# 2026-11-09 ' + A.SECTION), 1)
        tail = text.split('# 2026-11-09 ' + A.SECTION + '\n', 1)[1]
        self.assertEqual(tail.splitlines(), [
            '# reserved: ELF_REBUILD_mtd_29 -> 29-r2',
            'ELF_DEP_mtd_29:=mtd=29-r3',
            'ELF_REBUILD_nautilus_51.1-r3:=51.1-r4',
            'ELF_DEP_nautilus_51.1-r3:=nautilus=51.1-r4',
            'ELF_REBUILD_samba4-libs_4.24.5-r5:=4.24.5-r6',
            'ELF_DEP_samba4-libs_4.24.5-r5:=samba4-libs=4.24.5-r6'])
        # A later round on the same day reuses the section header.
        (self.base / 'nautilus-51.1-r4.apk').touch()
        again = A.plan(self.tree, self.destination,
                       [entry('base/nautilus-51.1-r4.apk', 'nautilus', '51.1-r4')])
        self.assertEqual(again[0]['release'], '51.1-r5')
        A.apply(self.tree, again, today='2026-11-09')
        self.assertEqual(self.ledger().count('# 2026-11-09 ' + A.SECTION), 1)
        self.assertIn('ELF_REBUILD_nautilus_51.1-r3:=51.1-r5\n', self.ledger())

    def test_abbreviates_full_git_commit_hashes_in_packageinfo(self):
        (self.tree / 'tmp/.packageinfo').write_text(
            PACKAGEINFO + '\n'
            'Source-Makefile: package/network/services/hostapd/Makefile\n'
            'Package: wpad-mbedtls\n'
            'Version: 2026.08.07~831364bf02710ad09c2f27d3efa92abeeb5634c0-r6\n')
        (self.base / 'wpad-mbedtls-2026.08.07~831364bf-r6.apk').touch()
        plan = A.plan(self.tree, self.destination, [
            entry('base/wpad-mbedtls-2026.08.07~831364bf-r6.apk',
                  'wpad-mbedtls', '2026.08.07~831364bf-r6')])
        self.assertEqual(plan[0]['recipe'], '2026.08.07~831364bf-r6')
        self.assertEqual(plan[0]['release'], '2026.08.07~831364bf-r7')

    def test_abi_suffixed_package_uses_recipe_key_and_suffixed_dependency(self):
        (self.tree / 'tmp/.packageinfo').write_text(
            'Source-Makefile: feeds/packages/utils/bzip2/Makefile\n'
            'Package: libbz2\n'
            'Version: 1.0.8-r1\n'
            'ABI-Version: 1.0\n')
        (self.tree / A.LEDGER).write_text(
            'ELF_REBUILD_libbz2_1.0.8-r0:=1.0.8-r9\n'
            'ELF_REBUILD_libbz2_1.0.8-r1:=1.0.8-r5\n')
        plan = A.plan(self.tree, self.destination, [
            entry('base/libbz2-1.0-1.0.8-r5.apk', 'libbz2-1.0', '1.0.8-r5')])
        self.assertEqual(plan[0]['ledger_name'], 'libbz2')
        self.assertEqual(plan[0]['recipe'], '1.0.8-r1')
        # Historical keys under the unsuffixed name reserve their outputs too.
        self.assertEqual(plan[0]['release'], '1.0.8-r10')
        A.apply(self.tree, plan, today='2026-11-20')
        text = self.ledger()
        self.assertIn('ELF_REBUILD_libbz2_1.0.8-r1:=1.0.8-r10\n', text)
        self.assertIn('ELF_DEP_libbz2_1.0.8-r1:=libbz2=1.0.8-r10\n', text)
        self.assertIn('ELF_DEP_libbz2-1.0_1.0.8-r1:=libbz2-1.0=1.0.8-r10\n', text)
        self.assertIn('ELF_REBUILD_libbz2_1.0.8-r0:=1.0.8-r9\n', text)

    def test_luci_release_placeholder_second_rebuild_updates_original_key(self):
        (self.tree / 'tmp/.packageinfo').write_text(
            'Source-Makefile: feeds/luci/modules/luci-base/Makefile\n'
            'Package: luci-base\n'
            'Version: x-r5\n')
        (self.tree / A.LEDGER).write_text(
            'ELF_REBUILD_luci-base_26.321.07849~ad028ec-r5:=26.321.07849~ad028ec-r6\n')
        plan = A.plan(self.tree, self.destination, [
            entry('luci/luci-base-26.321.07849~ad028ec-r6.apk',
                  'luci-base', '26.321.07849~ad028ec-r6')])
        self.assertEqual(plan[0]['recipe'], '26.321.07849~ad028ec-r5')
        self.assertEqual(plan[0]['release'], '26.321.07849~ad028ec-r7')
        A.apply(self.tree, plan, today='2026-11-20')
        text = self.ledger()
        self.assertIn('ELF_REBUILD_luci-base_26.321.07849~ad028ec-r5:='
                      '26.321.07849~ad028ec-r7\n', text)
        self.assertNotIn('ELF_REBUILD_luci-base_26.321.07849~ad028ec-r6:=', text)

    def test_base_files_uses_the_built_commit_count_version(self):
        (self.tree / 'tmp/.packageinfo').write_text(
            'Source-Makefile: package/base-files/Makefile\n'
            'Package: base-files\n'
            'Version: 0.20~8b34d6283f\n')
        (self.tree / A.LEDGER).write_text('# header\n')
        plan = A.plan(self.tree, self.destination, [
            entry('target/base-files-1769.20~8b34d6283f.apk',
                  'base-files', '1769.20~8b34d6283f')])
        self.assertEqual(plan[0]['recipe'], '1769.20~8b34d6283f')
        self.assertEqual(plan[0]['release'], '1769.20~8b34d6283f-r1')

    def test_base_files_second_rebuild_updates_the_original_key(self):
        (self.tree / 'tmp/.packageinfo').write_text(
            'Source-Makefile: package/base-files/Makefile\n'
            'Package: base-files\n'
            'Version: 0.20~8b34d6283f\n')
        (self.tree / A.LEDGER).write_text(
            'ELF_REBUILD_base-files_1769.20~8b34d6283f:=1769.20~8b34d6283f-r1\n')
        plan = A.plan(self.tree, self.destination, [
            entry('target/base-files-1769.20~8b34d6283f-r1.apk',
                  'base-files', '1769.20~8b34d6283f-r1')])
        self.assertEqual(plan[0]['recipe'], '1769.20~8b34d6283f')
        self.assertEqual(plan[0]['release'], '1769.20~8b34d6283f-r2')
        A.apply(self.tree, plan, today='2026-11-20')
        self.assertIn('ELF_REBUILD_base-files_1769.20~8b34d6283f:='
                      '1769.20~8b34d6283f-r2\n', self.ledger())

    def test_luci_bare_placeholder_second_rebuild_updates_original_key(self):
        (self.tree / 'tmp/.packageinfo').write_text(
            'Source-Makefile: feeds/luci/libs/luci-lib-ip/Makefile\n'
            'Package: luci-lib-ip\n'
            'Version: x\n')
        (self.tree / A.LEDGER).write_text(
            'ELF_REBUILD_luci-lib-ip_24.322.80622~82bde8c:=24.322.80622~82bde8c-r1\n')
        plan = A.plan(self.tree, self.destination, [
            entry('luci/luci-lib-ip-24.322.80622~82bde8c-r1.apk',
                  'luci-lib-ip', '24.322.80622~82bde8c-r1')])
        self.assertEqual(plan[0]['recipe'], '24.322.80622~82bde8c')
        self.assertEqual(plan[0]['release'], '24.322.80622~82bde8c-r2')

    def test_abi_version_does_not_leak_between_packages(self):
        (self.tree / 'tmp/.packageinfo').write_text(
            'Source-Makefile: feeds/packages/utils/bzip2/Makefile\n'
            'Package: libbz2\n'
            'Version: 1.0.8-r1\n'
            'ABI-Version: 1.0\n'
            '\n'
            'Package: no-version\n'
            'ABI-Version: 9\n')
        versions = A.recipe_versions(self.tree)
        self.assertEqual(versions['libbz2'],
                         ['1.0.8-r1', 'feeds/packages/utils/bzip2/Makefile', '1.0'])
        self.assertNotIn('no-version', versions)

    def test_deduplicates_projected_custom_and_rejects_digest_conflict(self):
        e1 = {**entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3'),
              'old_sha256': 'aaa', 'new_sha256': 'bbb'}
        e2 = {**entry('custom/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3'),
              'old_sha256': 'aaa', 'new_sha256': 'bbb'}
        planned = A.plan(self.tree, self.destination, [e1, e2])
        self.assertEqual(len(planned), 1)
        self.assertEqual(planned[0]['sources'],
                         ['base/nautilus-51.1-r3.apk', 'custom/nautilus-51.1-r3.apk'])

        e3 = {**entry('custom/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3'),
              'old_sha256': 'aaa', 'new_sha256': 'ccc'}
        with self.assertRaisesRegex(ValueError, 'conflicting candidate digests'):
            A.plan(self.tree, self.destination, [e1, e3])

    def test_digest_bound_approval_and_policy_mismatch(self):
        review_entry = {
            **entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3', 'unknown'),
            'old_sha256': 'old111',
            'new_sha256': 'new222',
            'report_sha256': 'rep333',
            'decision': {'action': A.DIAGNOSE.ACTION_REVIEW, 'reasons': ['missing_type_abi_evidence'],
                         'blockers': ['missing type'], 'unresolved': [{'path': 'x', 'detail': 'y'}]},
        }
        good_approval = [{
            'schema': 1,
            'policy_version': A.DIAGNOSE.POLICY_VERSION,
            'old_sha256': 'old111',
            'new_sha256': 'new222',
            'report_sha256': 'rep333',
            'name': 'nautilus',
            'reason': 'maintainer verified ABI',
        }]
        bad_policy = [{**good_approval[0], 'policy_version': 'old-policy'}]
        bad_digest = [{**good_approval[0], 'new_sha256': 'different'}]
        self.assertFalse(A.eligible(review_entry))
        self.assertFalse(A.eligible(review_entry, approvals=bad_policy))
        self.assertFalse(A.eligible(review_entry, approvals=bad_digest))
        self.assertTrue(A.eligible(review_entry, approvals=good_approval))
        planned = A.plan(self.tree, self.destination, [review_entry], approvals=good_approval)
        self.assertEqual(planned[0]['release'], '51.1-r4')

    def test_concurrent_ledger_change_and_crash_recovery(self):
        e = {**entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3'),
             'old_sha256': 'old111', 'new_sha256': 'new222', 'report_sha256': 'rep333'}
        planned = A.plan(self.tree, self.destination, [e])
        # Simulate concurrent modification before apply.
        (self.tree / A.LEDGER).write_text(self.ledger() + '# concurrent edit\n')
        with self.assertRaisesRegex(ValueError, 'Ledger changed concurrently'):
            A.apply(self.tree, planned, today='2026-11-22')

        # Re-plan and apply cleanly.
        planned = A.plan(self.tree, self.destination, [e])
        A.apply(self.tree, planned, today='2026-11-22')
        self.assertIn('ELF_REBUILD_nautilus_51.1-r3:=51.1-r4\n', self.ledger())

        # Simulate interrupted rebuild: retry planning with the exact same conflict.
        # Must recover 51.1-r4 instead of failing or allocating 51.1-r5!
        recovered = A.plan(self.tree, self.destination, [e])
        self.assertEqual(recovered[0]['release'], '51.1-r4')
        self.assertTrue(recovered[0]['recovered'])
        ledger_before = self.ledger()
        A.apply(self.tree, recovered, today='2026-11-22')
        self.assertEqual(self.ledger(), ledger_before)


class PublishAllocatingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='allocate-publish-')
        self.addCleanup(self.temp.cleanup)
        self.data = {'destination': Path(self.temp.name)}
        self.error = B.LAN.SameVersionRebuildError(
            'rejected', [entry('base/nautilus-51.1-r3.apk', 'nautilus', '51.1-r3')])
        self.allocation = [{'name': 'nautilus', 'version': '51.1-r3', 'release': '51.1-r4',
                            'recipe': '51.1-r3', 'verdict': 'change', 'so_changed': False,
                            'makefile': 'package/custom/nautilus/Makefile'}]

    def test_without_flag_the_rejection_is_raised(self):
        def publish_once():
            raise self.error
        with patch.object(B, 'run_make') as make, self.assertRaises(B.LAN.SameVersionRebuildError):
            B.publish_allocating(TREE, self.data, publish_once)
        make.assert_not_called()

    def test_allocates_rebuilds_and_retries(self):
        attempts = []

        def publish_once():
            attempts.append(1)
            if len(attempts) == 1:
                raise self.error
            return {'status': 'published'}
        with patch.object(B.ALLOCATE, 'plan', return_value=self.allocation) as plan, \
                patch.object(B.ALLOCATE, 'apply') as apply, \
                patch.object(B, 'run_make') as make:
            result = B.publish_allocating(TREE, self.data, publish_once,
                                          ['-j', '16', 'V=s', 'CONFIG_PACKAGE_x=m'], True)
        self.assertEqual(result, {'status': 'published'})
        plan.assert_called_once_with(TREE, self.data['destination'], self.error.entries)
        apply.assert_called_once_with(TREE, self.allocation)
        make.assert_called_once_with(TREE, ['-j', '16', 'V=s', 'package/custom/nautilus/compile'])

    def test_gives_up_after_bounded_rounds(self):
        def publish_once():
            raise self.error
        with patch.object(B.ALLOCATE, 'plan', return_value=self.allocation), \
                patch.object(B.ALLOCATE, 'apply'), patch.object(B, 'run_make') as make, \
                self.assertRaises(B.LAN.SameVersionRebuildError):
            B.publish_allocating(TREE, self.data, publish_once, [], True)
        self.assertEqual(make.call_count, B.ALLOCATION_ROUNDS)
        self.assertTrue(make.call_args.args[1][0].startswith('-j'))

    def test_dry_run_with_allocate_has_zero_ledger_or_make_side_effects(self):
        def publish_once():
            raise self.error
        with patch.object(B.ALLOCATE, 'plan', return_value=self.allocation) as plan, \
                patch.object(B.ALLOCATE, 'apply') as apply, \
                patch.object(B, 'run_make') as make:
            result = B.publish_allocating(TREE, self.data, publish_once, [], True, dry_run=True)
        self.assertEqual(result['status'], 'dry-run-conflict')
        self.assertEqual(result['planned_allocations'], self.allocation)
        plan.assert_called_once()
        apply.assert_not_called()
        make.assert_not_called()


@unittest.skipUnless(A.APK.exists() and (TREE / 'public-key.pem').is_file()
                     and (TREE / 'private-key.pem').is_file(),
                     'host apk or signing keys not present')
class PostAllocationVerificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='verify-rebuilt-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.keys = self.root / 'keys'
        self.keys.mkdir()
        shutil.copyfile(TREE / 'public-key.pem', self.keys / 'public-key.pem')

    def build_apk(self, label, version, payload_bytes):
        payload = self.root / ('payload-' + label)
        (payload / 'usr/share/demo').mkdir(parents=True)
        (payload / 'usr/share/demo/file.txt').write_bytes(payload_bytes)
        out = self.root / f'demo-{version}-{label}.apk'
        subprocess.run([str(A.APK), 'mkpkg', '--sign-key', str(TREE / 'private-key.pem'),
                        '--info', 'name:demo', '--info', f'version:{version}',
                        '--info', 'arch:x86_64', '--info', 'license:MIT',
                        '--info', 'description:test', '--files', str(payload),
                        '--output', str(out)], check=True, capture_output=True)
        return out

    def test_accepts_release_bump_only_and_rejects_payload_drift(self):
        cand = self.build_apk('cand', '1.0-r1', b'same content\n')
        good = self.build_apk('good', '1.0-r2', b'same content\n')
        drift = self.build_apk('drift', '1.0-r2', b'drifted content\n')
        A.verify_rebuilt_package(cand, good, 'demo', apk=A.APK, keys_dir=self.keys)
        with self.assertRaisesRegex(ValueError, 'drifted beyond release-bump metadata'):
            A.verify_rebuilt_package(cand, drift, 'demo', apk=A.APK, keys_dir=self.keys)


if __name__ == '__main__':
    unittest.main()
