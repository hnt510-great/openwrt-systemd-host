#!/usr/bin/env python3
"""Cross-version omissions, explicit migrations and immutable prepared releases."""
import importlib.util
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

TREE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('upgrade_preflight_test', TREE / 'scripts/apk-upgrade-preflight.py')
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)
OLD = '6.18.55~' + 'a' * 32 + '-r1'
NEW = '6.18.55~' + 'b' * 32 + '-r1'
GEN = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'


class PreflightTests(unittest.TestCase):
    def baseline_in(self, root):
        """Run the remote BASELINE script with absolute paths mapped into root."""
        import builtins, contextlib, io, pathlib, sys, types
        mapped = lambda name: pathlib.Path(root, str(name).lstrip('/'))
        fake = types.ModuleType('pathlib')
        fake.Path = lambda *parts: mapped(pathlib.PurePosixPath(*parts))
        output = io.StringIO()
        with patch.dict(sys.modules, {'pathlib': fake}), \
                patch.object(os, 'uname', return_value=types.SimpleNamespace(release=GEN)), \
                contextlib.redirect_stdout(output):
            exec(G.BASELINE, {'__builtins__': builtins,
                              'open': lambda name, *args: builtins.open(mapped(name), *args)})
        return json.loads(output.getvalue())

    def baseline_root(self, root, state):
        for name, data in (('lib/apk/db/lock', ''), ('lib/apk/db/installed', 'P:x\n'),
                           ('etc/apk/world', 'x\n'), ('etc/openwrt-kernel/protected', ''),
                           ('etc/openwrt-kernel/state.json', json.dumps(state)),
                           ('usr/bin/apk', 'apk'), ('proc/sys/kernel/random/boot_id', 'boot\n')):
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text(data)

    def test_baseline_distinguishes_generation_and_package_routers(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            self.baseline_root(root, {'schema': 1, 'phase': 'ready', 'pending': None,
                                      'generations': {GEN: {'release': GEN, 'abi': NEW}}})
            legacy = self.baseline_in(root)
            self.assertEqual((legacy['model'], legacy['abi']), ('generations', NEW))
            self.baseline_root(root, {'schema': 2, 'phase': 'ready', 'kernels': {GEN: {'kind': 'package'}}})
            packaged = self.baseline_in(root)
            self.assertEqual((packaged['model'], packaged['abi']), ('packages', None))
            self.assertFalse(G.same_baseline(legacy, packaged))
            self.assertTrue(G.same_baseline(packaged, self.baseline_in(root)))
            self.baseline_root(root, {'schema': 2, 'phase': 'adopting', 'kernels': {GEN: {}}})
            with self.assertRaises(SystemExit):
                self.baseline_in(root)

    def test_package_router_skips_generation_transition_checks(self):
        baseline = {'model': 'packages', 'abi': None, 'installed': 'P:kmod-nic\nV:1\n\n', 'world': ''}
        G.validate_transition(baseline, [], OLD)

    def test_metadata_migration_preserves_pin_types_tags_and_kernel_pins(self):
        baseline = {'installed': 'P:libc\nV:1-r1\nC:Q1old\n\nP:app\nV:1-r1\nC:Q1app\n\n',
                    'world': 'libc=1-r1\napp@lan><Q1app\nother>=2\nkmod-test><Q1kernel\n'}
        audit = {'migration': {'libc': {'before': '1-r1', 'after': '1-r2'},
                               'app': {'before': '1-r1', 'after': '1-r2'}},
                 'package_info': {'libc': {'version': '1-r2'},
                                  'app': {'version': '1-r2', 'hashes': '00' * 20}}}
        world, changes = G.migration_world(baseline, {'elf_abi': audit})
        self.assertIn('libc=1-r2\n', world)
        self.assertIn('app@lan><Q1' + 'A' * 27 + '=\n', world)
        self.assertIn('other>=2\nkmod-test><Q1kernel\n', world)
        self.assertEqual(len(changes), 2)
        baseline['world'] = 'libc=0-r1\napp\n'
        self.assertEqual(G.migration_world(baseline, {'elf_abi': audit})[1], [])

    def test_pinned_older_upstream_selects_its_audited_metadata_alternative(self):
        baseline = {'installed': 'P:engine\nV:5-r7\nC:Q1old\n\n', 'world': 'engine><Q1old\n'}
        audit = {'migration': {'engine': [{'before': '6-r2', 'after': '6-r3'},
                                          {'before': '5-r7', 'after': '5-r8'}]},
                 'package_info': {'engine': {'version': '6-r3', 'hashes': '11' * 32}},
                 'alternatives': {'engine': {'5-r8': {'version': '5-r8', 'hashes': '00' * 32}}}}
        world, changes = G.migration_world(baseline, {'elf_abi': audit})
        self.assertEqual(world, 'engine><Q1' + 'A' * 27 + '=\n')
        self.assertEqual(len(changes), 1)

    def test_legacy_consumer_is_checked_against_actual_post_upgrade_files(self):
        machine = {'needed': [], 'soname': 'libprobe.so.1', 'rpath': None,
                   'runpath': None, 'interpreter': None, 'class': 2, 'machine': 62}
        old = {'schema': 1, 'files': {'/usr/lib/libprobe.so.1': machine}, 'links': {}}
        app = {'schema': 1, 'files': {'/usr/bin/legacy-app': {**machine,
               'needed': ['libprobe.so.1'], 'soname': None}}, 'links': {}}
        baseline = {'elf': {'library': {'elf': old}, 'legacy-app': {'elf': app}}}
        new = {'schema': 1, 'version': '2-r1', 'files': {'/usr/lib/libprobe.so.2':
               {**machine, 'soname': 'libprobe.so.2'}}, 'links': {}}
        manifest = {'elf_abi': {'package_info': {'library': {'name': 'library', 'version': '2-r1'}},
                               'inventories': {'library': new}}}
        simulation = {'plan': {'changes': [{'name': 'library', 'before': '1-r1', 'after': '2-r1'}]}}
        with self.assertRaisesRegex(ValueError, 'legacy-app.*libprobe.so.1'):
            G.validate_elf_transition(baseline, manifest, simulation)
        fixed = {'schema': 1, 'version': '1-r2', 'files': {'/usr/bin/legacy-app':
                 {**machine, 'needed': ['libprobe.so.2'], 'soname': None}}, 'links': {}}
        manifest['elf_abi']['inventories']['legacy-app'] = fixed
        manifest['elf_abi']['package_info']['legacy-app'] = {'name': 'legacy-app', 'version': '1-r2'}
        simulation['plan']['changes'].append({'name': 'legacy-app', 'before': '1-r1', 'after': '1-r2'})
        self.assertEqual(G.validate_elf_transition(baseline, manifest, simulation)['elf_files'], 2)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.baseline = {'schema': 1, 'abi': OLD, 'release': 'old-g1', 'boot_id': 'boot',
            'hashes': {'installed': 'old'}, 'world': 'kernel\nkmod-nf-log6\n',
            'installed': 'P:kmod-nf-log6\nV:1-r1\nD:kmod-nf-log\n'
                         'F:usr/lib/apk/packages\nR:kmod-nf-log6.list\n\n'
                         'P:kmod-nf-log\nV:1-r1\n\n'}
        self.packages = []
        for name in ('kmod-nf-log', 'kmod-nf-log6'):
            self.packages += [
                {'name': name, 'version': '2-r1', 'depends': ['kernel=' + NEW, name + '-' + GEN + '=2-r1'] +
                 (['kmod-nf-log'] if name.endswith('log6') else [])},
                {'name': name + '-' + GEN, 'version': '2-r1', 'origin': 'kernel-generations',
                 'depends': ['linux-image-' + GEN + '=' + NEW]}]
        self.results = {}
        for name in ('userspace', 'kernel'):
            folder = self.root / 'public' / 'snapshots' / name
            folder.mkdir(parents=True)
            (folder / 'packages.adb').write_bytes(b'signed index fixture')
            (folder / 'probe.apk').write_bytes(b'immutable package fixture')
            self.results[name] = {'status': 'prepared', 'snapshot': str(folder),
                'alias': str(self.root / 'public' / ('abi' if name == 'userspace' else 'kernel-upgrades')),
                'previous': None}
        manifest = {'images': {'linux-image-' + GEN: NEW},
                    'packages': {str(i): {'info': p} for i, p in enumerate(self.packages)}}
        (Path(self.results['kernel']['snapshot']) / 'manifest.json').write_text(json.dumps(manifest))

    def check(self, packages=None, baseline=None):
        G.validate_transition(baseline or self.baseline, self.packages if packages is None else packages, NEW)

    def test_current_installed_module_omission_blocks_despite_new_config(self):
        packages = [p for p in self.packages if p['name'] != 'kmod-nf-log6']
        with self.assertRaisesRegex(ValueError, 'no target ABI tracker: kmod-nf-log6'):
            self.check(packages)

    def test_unknown_removed_module_requires_explicit_port(self):
        self.baseline['installed'] += 'P:kmod-unknown\nV:1-r1\n\n'
        with self.assertRaisesRegex(ValueError, 'kmod-unknown'):
            self.check()

    def test_missing_payload_blocks(self):
        with self.assertRaisesRegex(ValueError, 'generation payload'):
            self.check([p for p in self.packages if p['name'] != 'kmod-nf-log6-' + GEN])

    def test_matching_empty_compatibility_passes(self):
        self.check()

    def test_replacement_dependency_must_be_declared(self):
        self.packages[2]['depends'].remove('kmod-nf-log')
        with self.assertRaisesRegex(ValueError, 'compatibility dependency'):
            self.check()

    def test_empty_rule_cannot_hide_real_module_files(self):
        self.baseline['installed'] += ('P:kmod-nf-log6-old-owrt-g1\nV:1-r1\n'
                                      'F:usr/lib/modules/old\nR:real.ko\n\n')
        self.baseline['installed'] = self.baseline['installed'].replace(
            'D:kmod-nf-log\n', 'D:kmod-nf-log kmod-nf-log6-old-owrt-g1=1-r1\n')
        with self.assertRaisesRegex(ValueError, 'discard a real file'):
            self.check()

    def test_same_abi_does_not_require_generation_replacement(self):
        G.validate_transition({**self.baseline, 'abi': NEW}, [], NEW)

    def test_reports_all_old_tracker_locks_and_missing_modules_without_mutation(self):
        self.baseline['installed'] += 'P:kmod-unknown\nV:1-r1\n\n'
        self.baseline['installed'] = self.baseline['installed'].replace(
            'P:kmod-nf-log6\nV:1-r1\n', 'P:kmod-nf-log6\nV:1-r1\nC:Q1old\n')
        self.baseline['world'] += ('kmod-nf-log6@lan><Q1old\nkmod-nf-log=1-r1\n' +
                                   'kmod-nf-log6-old-owrt-g1><Q1protected\n')
        before = json.dumps(self.baseline, sort_keys=True)
        with self.assertRaises(ValueError) as failure:
            self.check()
        message = str(failure.exception)
        for expected in ('kmod-unknown', 'kmod-nf-log6@lan><Q1old', 'kmod-nf-log=1-r1'):
            self.assertIn(expected, message)
        self.assertNotIn('Q1protected', message)
        self.assertEqual(json.dumps(self.baseline, sort_keys=True), before)

    def test_kernel_version_lock_blocks_abi_transition_but_target_pin_is_allowed(self):
        self.baseline['installed'] += 'P:kernel\nV:' + OLD + '\n\n'
        self.packages.append({'name': 'kernel', 'version': NEW})
        self.baseline['world'] = 'kernel=' + OLD + '\n'
        with self.assertRaisesRegex(ValueError, 'world locks block'):
            self.check()
        self.baseline['world'] = 'kernel=' + NEW + '\n'
        self.check()

    def test_readiness_rejects_missing_tracker_before_staging(self):
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'remote', return_value=self.baseline):
            with self.assertRaisesRegex(ValueError, 'no target ABI tracker'):
                G.readiness(self.root, [], NEW)

    def test_changed_early_baseline_blocks_before_simulation(self):
        stale = {**self.baseline, 'hashes': {'installed': 'changed'}}
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=self.baseline), \
                patch.object(G, 'remote') as remote:
            with self.assertRaisesRegex(ValueError, 'changed during feed preparation'):
                G.preflight(self.root, 'http://host', **self.results, expected_baseline=stale)
            remote.assert_not_called()

    def test_readiness_baseline_accepts_added_elf_fingerprint_but_final_check_requires_it(self):
        full = {**self.baseline, 'hashes': {**self.baseline['hashes'], 'elf': 'same'}}
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=full), \
                patch.object(G, 'remote', return_value={'returncode': 0}):
            self.assertEqual(G.preflight(self.root, 'http://host', **self.results,
                             expected_baseline=self.baseline)['status'], 'passed')
        changed = {**full, 'hashes': {**full['hashes'], 'elf': 'changed'}}
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', side_effect=[full, changed]), \
                patch.object(G, 'remote', return_value={'returncode': 0}):
            with self.assertRaisesRegex(ValueError, 'baseline changed'):
                G.preflight(self.root, 'http://host', **self.results, expected_baseline=self.baseline)

    def test_fresh_router_simulation_and_bound_receipt(self):
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=self.baseline), \
                patch.object(G, 'remote', return_value={'returncode': 0}) as remote:
            receipt = G.preflight(self.root, 'http://host', self.results['userspace'], self.results['kernel'])
        self.assertEqual(receipt['status'], 'passed')
        self.assertNotIn('installed', receipt['baseline'])
        self.assertEqual(remote.call_count, 2)
        self.assertEqual(len(remote.call_args_list[0].args[2]['indexes']), 1)
        self.assertEqual(len(remote.call_args_list[1].args[2]['indexes']), 2)
        self.assertTrue(remote.call_args_list[1].args[2]['replace_managed'])

    def packaged_channel(self):
        manifest = {'images': {'linux-image-' + GEN: NEW, 'linux-image-6.18.55-46-openwrt': '6.18.55-r46'},
                    'packages': {str(i): {'info': p} for i, p in enumerate(self.packages)}}
        (Path(self.results['kernel']['snapshot']) / 'manifest.json').write_text(json.dumps(manifest))

    def test_legacy_router_takes_the_userspace_only_migration_step(self):
        self.packaged_channel()
        userspace = {**self.results['userspace'], 'kernel': self.baseline['abi']}
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=self.baseline), \
                patch.object(G, 'remote', return_value={'returncode': 0}) as remote:
            receipt = G.preflight(self.root, 'http://host', userspace, self.results['kernel'])
        self.assertEqual(receipt['migration_step'], 'userspace-only')
        self.assertEqual(remote.call_count, 1)
        request = remote.call_args_list[0].args[2]
        self.assertTrue(request['userspace_only'])
        self.assertEqual(len(request['indexes']), 2)

    def test_package_router_simulates_the_full_upgrade_with_userspace(self):
        self.packaged_channel()
        baseline = {**self.baseline, 'model': 'packages', 'abi': None}
        userspace = {**self.results['userspace'], 'kernel': NEW}
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=baseline), \
                patch.object(G, 'remote', return_value={'returncode': 0}) as remote:
            receipt = G.preflight(self.root, 'http://host', userspace, self.results['kernel'])
        self.assertNotIn('migration_step', receipt)
        self.assertEqual(remote.call_count, 1)
        request = remote.call_args_list[0].args[2]
        self.assertNotIn('userspace_only', request)
        self.assertEqual(len(request['indexes']), 2)

    def test_target_abi_userspace_failure_is_a_publication_blocker(self):
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=self.baseline), \
                patch.object(G, 'remote', side_effect=[{'returncode': 0},
                    {'returncode': 99, 'stderr': 'target library conflict'}]):
            with self.assertRaisesRegex(ValueError, 'target ABI userspace'):
                G.preflight(self.root, 'http://host', **self.results)

    def test_simulation_failure_blocks(self):
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=self.baseline), \
                patch.object(G, 'remote', return_value={'returncode': 99, 'stderr': 'missing dependency'}):
            with self.assertRaisesRegex(ValueError, 'Router rejects'):
                G.preflight(self.root, 'http://host', **self.results)

    def test_long_solver_error_preserves_root_conflict_and_final_blocker(self):
        error = 'ROOT: pinned tracker conflicts\n' + 'dependency details\n' * 1000 + 'FINAL BLOCKER'
        for first in (True, False):
            with self.subTest(first_simulation=first):
                responses = [{'returncode': 99, 'stderr': error}]
                if not first:
                    responses.insert(0, {'returncode': 0})
                with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                        patch.object(G, 'capture', return_value=self.baseline), \
                        patch.object(G, 'remote', side_effect=responses):
                    with self.assertRaises(ValueError) as failure:
                        G.preflight(self.root, 'http://host', **self.results)
                self.assertIn('ROOT: pinned tracker conflicts', str(failure.exception))
                self.assertIn('FINAL BLOCKER', str(failure.exception))
                self.assertLess(len(str(failure.exception)), 8500)

    def test_database_change_invalidates_receipt(self):
        changed = {**self.baseline, 'hashes': {'installed': 'changed'}}
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', side_effect=[self.baseline, changed]), \
                patch.object(G, 'remote', return_value={'returncode': 0}):
            with self.assertRaisesRegex(ValueError, 'baseline changed'):
                G.preflight(self.root, 'http://host', **self.results)

    def test_changed_prepared_apk_cannot_promote(self):
        with patch.object(G, 'policy', return_value=None):
            receipt = G.preflight(self.root, 'http://host', **self.results)
            (Path(self.results['kernel']['snapshot']) / 'probe.apk').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'changed after'):
                G.authorize(self.root, self.results['kernel'], receipt, 'kernel')

    def test_simulation_time_change_is_rejected_without_intermediate_rehash(self):
        def simulate(*args):
            (Path(self.results['kernel']['snapshot']) / 'probe.apk').write_bytes(b'changed')
            return {'returncode': 0}

        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', return_value=self.baseline), \
                patch.object(G, 'remote', side_effect=simulate), \
                patch.object(G, 'snapshot_hashes', wraps=G.snapshot_hashes) as hashes:
            receipt = G.preflight(self.root, 'http://host', **self.results)
            self.assertEqual(hashes.call_count, 2)
            with self.assertRaisesRegex(ValueError, 'changed after'):
                G.authorize(self.root, self.results['kernel'], receipt, 'kernel')

    def test_snapshot_rehashes_same_size_change_with_restored_mtime(self):
        snapshot = Path(self.results['userspace']['snapshot'])
        nested = snapshot / '.hidden/subdir'
        nested.mkdir(parents=True)
        package = nested / 'payload.apk'
        package.write_bytes(b'before')
        before = G.snapshot_hashes(snapshot)
        self.assertEqual(before, {str(p.relative_to(snapshot)): G.digest(p)
                                 for p in sorted(snapshot.rglob('*')) if p.is_file()})
        st = package.stat()
        package.write_bytes(b'after!')
        os.utime(package, ns=(st.st_atime_ns, st.st_mtime_ns))
        after = G.snapshot_hashes(snapshot)
        self.assertEqual(before.keys(), after.keys())
        self.assertNotEqual(before['.hidden/subdir/payload.apk'],
                            after['.hidden/subdir/payload.apk'])

    def test_production_cannot_use_receipt_without_router(self):
        with patch.object(G, 'policy', return_value=None):
            receipt = G.preflight(self.root, 'http://host', **self.results)
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}):
            with self.assertRaisesRegex(ValueError, 'lacks a router'):
                G.authorize(self.root, self.results['kernel'], receipt, 'kernel')

    def test_low_level_production_publication_requires_coordinator(self):
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}):
            with self.assertRaisesRegex(ValueError, 'coordinated staged'):
                G.require_coordinator(self.root)

    def test_unreachable_router_is_not_an_optional_check(self):
        with patch.object(G, 'policy', return_value={'ssh_target': 'router'}), \
                patch.object(G, 'capture', side_effect=ValueError('unreachable')):
            with self.assertRaisesRegex(ValueError, 'unreachable'):
                G.preflight(self.root, 'http://host', **self.results)

    def test_unsafe_ssh_target_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'SSH target'):
            G.remote('router; touch /tmp/unsafe', '', {})

    def test_migration_cycles_and_unknown_types_are_rejected(self):
        path = self.root / 'rules.json'
        for rules in ([{'from': 'kmod-a', 'to': ['kmod-a'], 'type': 'empty-compat', 'reason': 'bad'}],
                      [{'from': 'kmod-a', 'to': ['kmod-b'], 'type': 'drop', 'reason': 'bad'}],
                      [{'from': 'kmod-a', 'to': ['kmod-b'], 'type': 'empty-compat', 'reason': 'a'},
                       {'from': 'kmod-b', 'to': ['kmod-a'], 'type': 'empty-compat', 'reason': 'b'}]):
            path.write_text(json.dumps({'schema': 1, 'rules': rules}))
            with self.assertRaises(ValueError):
                G.MIGRATIONS.rules(path)


if __name__ == '__main__':
    unittest.main(verbosity=2)
