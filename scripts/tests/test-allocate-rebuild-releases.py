#!/usr/bin/env python3
"""Automatic ELF rebuild ledger allocation for same-version rebuilds."""
import importlib.util
from pathlib import Path
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
            entry('packages/samba4-libs-4.24.5-r5.apk', 'samba4-libs', '4.24.5-r5', 'unknown', True),
            entry('base/mtd-29-r2.apk', 'mtd', '29-r2')])
        self.assertEqual({a['name']: a['release'] for a in plan},
                         {'nautilus': '51.1-r4', 'samba4-libs': '4.24.5-r6', 'mtd': '29-r3'})
        self.assertEqual(A.rebuild_targets(plan), [
            'package/custom/nautilus/compile', 'package/feeds/packages/samba4/compile',
            'package/system/mtd/compile'])

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


if __name__ == '__main__':
    unittest.main()
