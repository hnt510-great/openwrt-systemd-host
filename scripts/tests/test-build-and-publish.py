#!/usr/bin/env python3
"""Signed generation publication, legacy retention and failure isolation."""
import argparse
import importlib.util
import json
import os
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


B = load('build_publish_test', 'build-and-publish.py')
P = load('package_fixture', 'kernel-bundle.py')
APK = TREE / 'staging_dir/host/bin/apk'
FAKEROOT = TREE / 'staging_dir/host/bin/fakeroot'
ABI = '6.18.55~' + 'a' * 32 + '-r1'


class BuildPublicationTests(unittest.TestCase):
    def setUp(self):
        if not APK.exists():
            self.skipTest('Build apk/host first')
        self.temp = tempfile.TemporaryDirectory(prefix='build-publication-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.tree = self.root / 'tree'
        self.server = self.root / 'server'
        self.target = self.tree / 'bin/systemd/targets/x86/64-glibc/packages'
        self.base = self.tree / 'bin/systemd/packages/x86_64/base'
        self.release = (self.tree / 'build_dir/target-x86_64_glibc/linux-x86_64/'
                        'linux-6.18.55/include/config/kernel.release')
        self.target.mkdir(parents=True)
        self.base.mkdir(parents=True)
        self.release.parent.mkdir(parents=True)
        version = self.tree / 'staging_dir/target-x86_64_glibc/kernel.version'
        version.parent.mkdir(parents=True)
        version.write_text(ABI + '\n')
        metadata = self.tree / 'tmp/.packageinfo'
        metadata.parent.mkdir()
        metadata.write_text('Source-Makefile: package/kernel/nic/Makefile\n'
                            'Package: kmod-nic\nKernel-Config: CONFIG_NIC\n'
                            'Source-Makefile: package/custom/kernel-dev-headers/Makefile\n'
                            'Package: kernel-dev-headers\n')
        for name in ('package/kernel/nic', 'package/custom/kernel-dev-headers'):
            path = self.tree / name / 'Makefile'
            path.parent.mkdir(parents=True)
            path.write_text('PKG_RELEASE:=1\n# CONFIG_PACKAGE_NIC_DEBUG\n')
        self.make_package('kernel', ABI, content='ORIGINAL kernel stub')
        self.make_package('user-probe', '1-r1')
        self.data = {'destination': self.server, 'base_url': 'http://127.0.0.1:8088'}
        (self.tree / 'configs').mkdir()
        (self.tree / 'configs/lan-apk-feeds.json').write_text(json.dumps(
            {'destination': str(self.server), 'base_url': self.data['base_url']}))
        initial = B.LAN.publish(argparse.Namespace(source_root=self.tree, kernel=ABI,
            destination=self.server, base_url=self.data['base_url'], incremental=True,
            dry_run=False, kernel_upgrade_view=False))
        self.old = Path(initial['snapshot'])
        self.old_stub = (self.old / 'target' / ('kernel-' + ABI + '.apk')).read_bytes()
        self.make_package('kernel', ABI, content='NEW parallel kernel stub')
        self.generation(1)
        # Simulate previous/future experimental output left in bin/. It must
        # never be selected merely because its version sorts higher: an old
        # per-generation payload set and a newer kernel package build.
        other = '6.18.55-owrt-' + 'b' * 32 + '-r1-g99'
        other_abi = ABI.replace('a' * 32, 'b' * 32)
        self.make_package('linux-image-' + other, other_abi)
        self.make_package('linux-image-openwrt', '1-r98',
                          ['linux-image-' + other + '=' + other_abi, 'kernel=' + other_abi])
        self.make_package('kmod-nic-' + other, '1000.98.6.18.55-r1', ['linux-image-' + other + '=' + other_abi])
        self.make_package('linux-image-6.18.55-99-openwrt', '6.18.55-r99')
        self.make_package('linux-image-openwrt', '6.18.55-r99', ['linux-image-6.18.55-99-openwrt=6.18.55-r99'])

    def make_package(self, name, version, depends=(), content=None, signed=True, files=None):
        root = self.root / 'package-files'
        if root.exists():
            shutil.rmtree(root)
        root.mkdir()
        file = root / 'probe'
        file.write_text(content or name + ' ' + version)
        for relative, data in (files or {}).items():
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
        folder = self.target if name == 'kernel' or name.startswith(
            ('kmod-', 'linux-image-', 'linux-headers-', 'kernel-dev-headers')) else self.base
        package = folder / (name + '-' + version + '.apk')
        package.unlink(missing_ok=True)
        P.package(APK, FAKEROOT, TREE / 'private-key.pem' if signed else None,
                  root, folder, name, version, list(depends), 'signed fixture', '')
        return package

    def generation(self, sequence, abi=ABI):
        name = '6.18.55-' + str(sequence) + '-openwrt'
        version = '6.18.55-r' + str(sequence)
        image = 'linux-image-' + name
        self.release.write_text(name + '\n')
        (self.tree / '.config').write_text(
            'CONFIG_OPENWRT_KERNEL_UPGRADE=y\nCONFIG_OPENWRT_KERNEL_SEQUENCE=' + str(sequence) +
            '\nCONFIG_PACKAGE_kmod-nic=y\nCONFIG_PACKAGE_kernel-dev-headers=y\nKEEP_ME=yes\n')
        linux = self.release.parents[2]
        binary = linux / 'arch/x86/boot/bzImage'
        binary.parent.mkdir(parents=True, exist_ok=True)
        state = B.state_path(self.tree)
        timestamp = json.loads(state.read_text())['timestamp'] if state.exists() else 'fixture timestamp'
        boot_header = bytearray(0x300)
        boot_header[0x202:0x206] = b'HdrS'
        boot_header[0x20e:0x210] = (0x100).to_bytes(2, 'little')
        binary.write_bytes(boot_header + (name + ' (fixture) #0 SMP ' + timestamp).encode() + b'\0')
        (linux / '.config').write_text('CONFIG_FIXTURE=y\n')
        self.make_package(image, version, ['openwrt-kernel-upgrade'], files={
            'usr/lib/openwrt-kernel/' + name + '/vmlinuz': binary.read_bytes(),
            'usr/lib/openwrt-kernel/' + name + '/config': (linux / '.config').read_bytes(),
            'usr/lib/modules/' + name + '/nic.ko': b'module'})
        self.make_package('linux-headers-' + name, version)
        self.make_package('linux-image-openwrt', version, [image + '=' + version])
        self.make_package('kernel-dev-headers', f'1000.{sequence}.6.18.55-r1',
                          ['linux-headers-' + name + '=' + version])
        self.make_package('kmod-nic', f'1000.{sequence}.6.18.55-r1', ['linux-image-openwrt'])
        return name

    def aliases(self):
        return {name: p.resolve() if p.exists() else None for name, p in (
            ('userspace', self.server / 'public/abi' / ABI),
            ('kernel', self.server / 'public/kernel-upgrades'))}

    def test_complete_signed_publication_preserves_legacy_same_abi(self):
        result = B.publish(self.tree, self.data)
        self.assertEqual(result['kernel']['images'], 1)
        self.assertEqual((self.old / 'target' / ('kernel-' + ABI + '.apk')).read_bytes(), self.old_stub)
        active = self.server / 'public/abi' / ABI
        self.assertEqual(len(json.loads((active / 'manifest.json').read_text())['kernel_packages']), 1)
        self.assertEqual((active / 'target' / ('kernel-' + ABI + '.apk')).read_bytes(), self.old_stub)
        channel = self.server / 'public/kernel-upgrades'
        self.assertNotEqual((channel / ('kernel-' + ABI + '.apk')).read_bytes(), self.old_stub)
        manifest = json.loads((channel / 'manifest.json').read_text())
        self.assertEqual(manifest['sequence'], 1)
        self.assertFalse(any('-g99' in p for p in manifest['packages']))
        self.assertFalse(any('1-r99' in p for p in manifest['packages']))
        for index in (active / 'target/packages.adb', channel / 'packages.adb'):
            subprocess.run([str(APK), 'verify', '--keys-dir', str(TREE), str(index)],
                           check=True, capture_output=True)

    def test_new_generation_retains_previous_payload_and_collects_old_snapshot(self):
        B.publish(self.tree, self.data)
        previous = self.aliases()['kernel']
        original = {p.name: p.read_bytes() for p in previous.glob('*.apk')}
        self.generation(2)
        result = B.publish(self.tree, self.data)
        self.assertEqual(result['kernel']['images'], 2)
        self.assertFalse(previous.exists())
        active = self.server / 'public/kernel-upgrades'
        for filename, content in original.items():
            self.assertEqual((active / filename).read_bytes(), content)
        current = json.loads((self.server / 'public/kernel-upgrades/manifest.json').read_text())
        self.assertEqual(current['sequence'], 2)
        self.assertTrue(any(p.startswith('linux-image-6.18.55-1-openwrt-') for p in current['packages']))

    def test_unchanged_publication_does_not_create_snapshots(self):
        B.publish(self.tree, self.data)
        before = self.aliases()
        result = B.publish(self.tree, self.data)
        self.assertEqual(result['userspace']['status'], 'unchanged')
        self.assertEqual(result['kernel']['status'], 'unchanged')
        self.assertEqual(self.aliases(), before)

    def test_duplicate_kernel_packages_still_require_identical_bytes(self):
        name = 'linux-image-openwrt'
        version = '6.18.55-r1'
        package = self.target / (name + '-' + version + '.apk')
        shutil.copyfile(package, self.base / package.name)
        B.publish(self.tree, self.data)
        before = self.aliases()
        self.make_package(name, version, ['linux-image-6.18.55-1-openwrt=' + version],
                          content='different signed meta with the same identity')
        with self.assertRaisesRegex(ValueError, 'Conflicting kernel package copies'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)
    def test_new_lower_sorting_abi_preserves_old_router_view(self):
        B.publish(self.tree, self.data)
        original_alias = (self.server / 'public/abi' / ABI).resolve()
        new_abi = ABI.replace('a' * 32, '0' * 32)
        self.generation(2, new_abi)
        self.make_package('kernel', new_abi)
        version = self.tree / 'staging_dir/target-x86_64_glibc/kernel.version'
        version.write_text(new_abi + '\n')
        result = B.publish(self.tree, self.data)
        self.assertEqual(result['userspace']['kernel'], new_abi)
        self.assertEqual(result['kernel']['images'], 2)
        self.assertEqual((self.server / 'public/abi' / ABI).resolve(), original_alias)
        self.assertTrue((self.server / 'public/abi' / new_abi / 'target/packages.adb').exists())

    def test_missing_kernel_image_does_not_publish_either_view(self):
        for p in self.target.glob('linux-image-6.18.55-1-openwrt-*.apk'):
            p.unlink()
        before = self.aliases()
        with self.assertRaisesRegex(ValueError, 'Missing matching kernel package: linux-image-6.18.55-1-openwrt'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)

    def test_missing_kmod_configuration_does_not_publish_either_view(self):
        (self.target / 'kmod-nic-1000.1.6.18.55-r1.apk').unlink()
        before = self.aliases()
        with self.assertRaisesRegex(ValueError, 'Missing kmod configuration package for this kernel build: kmod-nic'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)

    def test_kmods_are_userspace_and_kernel_packages_are_channel_only(self):
        B.publish(self.tree, self.data)
        userspace = self.server / 'public/current/target'
        names = {p.name for p in userspace.glob('*.apk')}
        self.assertIn('kmod-nic-1000.1.6.18.55-r1.apk', names)
        self.assertFalse(any(n.startswith(('linux-image-', 'linux-headers-')) or '-owrt-' in n for n in names))
        channel = {p.name for p in (self.server / 'public/kernel-upgrades').glob('*.apk')}
        for name in ('linux-image-6.18.55-1-openwrt-6.18.55-r1.apk', 'linux-headers-6.18.55-1-openwrt-6.18.55-r1.apk',
                     'linux-image-openwrt-6.18.55-r1.apk', 'kernel-dev-headers-1000.1.6.18.55-r1.apk'):
            self.assertIn(name, channel)
        self.assertFalse(any('-r99' in n or '-g99' in n or '1-r98' in n for n in channel))
        self.assertEqual((self.server / 'public/current').resolve(),
                         (self.server / 'public/abi' / ABI).resolve())
    def test_unsigned_userspace_does_not_publish_either_view(self):
        self.make_package('user-probe', '1-r2', signed=False)
        before = self.aliases()
        with self.assertRaises(subprocess.CalledProcessError):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)

    def test_router_rejection_discards_stages_and_preserves_both_views(self):
        B.publish(self.tree, self.data)
        self.generation(2)
        before = self.aliases()
        with patch.object(B.GUARD, 'preflight', side_effect=ValueError('Router rejects prepared release')):
            with self.assertRaisesRegex(ValueError, 'Router rejects'):
                B.publish(self.tree, self.data)
        self.assertEqual(before, self.aliases())
        self.assertEqual(len(list((self.server / 'public/kernel-snapshots').iterdir())), 1)

    def test_prepared_payload_change_is_rejected_before_either_pointer(self):
        B.publish(self.tree, self.data)
        self.generation(2)
        before = self.aliases()
        original = B.GUARD.preflight
        def mutate(*args, **kwargs):
            receipt = original(*args, **kwargs)
            root = Path(args[3]['snapshot'])
            next(root.glob('*.apk')).write_bytes(b'changed after validation')
            return receipt
        with patch.object(B.GUARD, 'preflight', side_effect=mutate):
            with self.assertRaisesRegex(ValueError, 'changed after'):
                B.publish(self.tree, self.data)
        self.assertEqual(before, self.aliases())

    def test_bin_change_after_validation_does_not_change_published_snapshot(self):
        probe = self.base / 'user-probe-1-r1.apk'
        expected = probe.read_bytes()
        original = B.GUARD.preflight
        def mutate(*args, **kwargs):
            receipt = original(*args, **kwargs)
            probe.write_bytes(b'concurrent build wrote a different APK')
            return receipt
        with patch.object(B.GUARD, 'preflight', side_effect=mutate):
            result = B.publish(self.tree, self.data)
        self.assertEqual((Path(result['userspace']['snapshot']) / 'base' / probe.name).read_bytes(), expected)

    def test_second_pointer_failure_rolls_back_first_pointer(self):
        B.publish(self.tree, self.data)
        self.generation(2)
        before = self.aliases()
        with patch.object(B.KERNEL, 'promote', side_effect=OSError('rename failed')):
            with self.assertRaisesRegex(OSError, 'rename failed'):
                B.publish(self.tree, self.data)
        self.assertEqual(before, self.aliases())

    def test_post_commit_gc_scan_failure_keeps_both_new_views(self):
        B.publish(self.tree, self.data)
        self.generation(2)
        self.make_package('user-probe', '2-r1')
        before = self.aliases()
        original = Path.iterdir
        def fail_gc(path):
            if path == self.server / 'public/kernel-snapshots':
                raise OSError('post-commit GC scan failed')
            return original(path)
        with patch.object(Path, 'iterdir', fail_gc):
            result = B.publish(self.tree, self.data)
        self.assertEqual(result['kernel']['status'], 'published')
        self.assertIn('post-commit GC scan failed', result['kernel']['cleanup_warnings'][0])
        self.assertNotEqual(before['userspace'], self.aliases()['userspace'])
        self.assertNotEqual(before['kernel'], self.aliases()['kernel'])

    def test_unchanged_kernel_check_failure_rolls_back_new_userspace(self):
        B.publish(self.tree, self.data)
        self.make_package('user-probe', '2-r1')
        before = self.aliases()
        with patch.object(B.KERNEL, 'promote', side_effect=ValueError('kernel validation failed')):
            with self.assertRaisesRegex(ValueError, 'kernel validation failed'):
                B.publish(self.tree, self.data)
        self.assertEqual(before, self.aliases())

    def test_changed_published_image_does_not_publish_userspace(self):
        B.publish(self.tree, self.data)
        self.make_package('linux-image-6.18.55-1-openwrt', '6.18.55-r1', ['openwrt-kernel-upgrade'],
                          content='CHANGED')
        self.make_package('user-probe', '1-r2')
        before = self.aliases()
        with self.assertRaisesRegex(ValueError, 'Published kernel channel package changed'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)
    def test_changed_support_requires_release_bump_and_preserves_old_blob(self):
        name = 'apk-mbedtls'
        self.make_package(name, '3.0.5-r7', content='published policy tool')
        B.publish(self.tree, self.data)
        active = self.server / 'public/kernel-upgrades'
        previous = (active / (name + '-3.0.5-r7.apk')).read_bytes()
        self.make_package(name, '3.0.5-r7', content='rebuilt policy tool')
        before = self.aliases()
        with self.assertRaisesRegex(ValueError, 'bump.*PKG_RELEASE'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)
        # A real package rebuild removes its superseded local output; the
        # immutable historical copy remains in the published snapshot.
        (self.base / (name + '-3.0.5-r7.apk')).unlink()
        self.make_package(name, '3.0.5-r8', content='rebuilt policy tool')
        B.publish(self.tree, self.data)
        self.assertEqual((active / (name + '-3.0.5-r7.apk')).read_bytes(), previous)
        self.assertTrue((active / (name + '-3.0.5-r8.apk')).exists())

    def test_make_normalizes_package_permissions_under_group_writable_shell(self):
        makefile = self.tree / 'umask-probe.mk'
        makefile.write_text('all:\n\tmkdir -p umask-probe\n\tprintf probe > umask-probe/file\n')
        previous = os.umask(0o002)
        try:
            B.run_make(self.tree, ['-f', str(makefile)])
        finally:
            os.umask(previous)
        self.assertEqual((self.tree / 'umask-probe').stat().st_mode & 0o777, 0o755)
        self.assertEqual((self.tree / 'umask-probe/file').stat().st_mode & 0o777, 0o644)

    def test_meta_for_another_image_does_not_publish_either_view(self):
        self.make_package('linux-image-openwrt', '6.18.55-r1', ['linux-image-6.18.55-1-openwrt=6.18.55-r7'])
        before = self.aliases()
        with self.assertRaisesRegex(ValueError, 'Missing matching kernel package: linux-image-openwrt'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)
    def test_dry_run_changes_neither_alias(self):
        self.make_package('user-probe', '1-r2')
        before = self.aliases()
        result = B.publish(self.tree, self.data, dry_run=True)
        self.assertEqual(result['kernel']['status'], 'dry-run')
        self.assertEqual(result['userspace']['status'], 'dry-run')
        self.assertEqual(self.aliases(), before)

    def test_cli_progress_keeps_json_stdout_and_can_be_disabled(self):
        before = self.aliases()
        command = ['python3', str(TREE / 'scripts/build-and-publish.py'),
                   '--source-root', str(self.tree), '--destination', str(self.server),
                   '--base-url', self.data['base_url'], '--dry-run']
        for options in ([], ['--no-progress']):
            with self.subTest(options=options):
                result = subprocess.run(command + options, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(json.loads(result.stdout)['kernel']['status'], 'dry-run')
                self.assertEqual(self.aliases(), before)
                if options:
                    self.assertEqual(result.stderr, '')
                else:
                    self.assertIn('Read and stage APKs', result.stderr)
                    self.assertIn('[100%] Dry run complete', result.stderr)
                    self.assertNotIn('\x1b', result.stderr)

    def test_failed_publication_does_not_report_complete(self):
        events = []
        def progress(percent, phase, detail=''):
            events.append((percent, phase))
        before = self.aliases()
        with patch.object(B.GUARD, 'preflight', side_effect=ValueError('rejected')):
            with self.assertRaisesRegex(ValueError, 'rejected'):
                B.publish(self.tree, self.data, dry_run=True, progress=progress)
        self.assertEqual(self.aliases(), before)
        self.assertTrue(events)
        self.assertTrue(all(percent < 100 for percent, _ in events))

    def test_router_readiness_failure_precedes_feed_staging(self):
        before = self.aliases()
        with patch.object(B.GUARD, 'readiness', side_effect=ValueError('world locks block')), \
                patch.object(B.LAN, 'publish') as lan, patch.object(B.KERNEL, 'publish') as kernel:
            with self.assertRaisesRegex(ValueError, 'world locks block'):
                B.publish(self.tree, self.data, dry_run=True)
            lan.assert_not_called()
            kernel.assert_not_called()
        self.assertEqual(self.aliases(), before)

    def migration_fixture(self):
        (self.tree / 'configs/apk-elf-rebuilds.mk').write_text(
            'ELF_DEP_legacy-app_1-r1:=legacy-app=1-r2\n')
        with (self.tree / 'tmp/.packageinfo').open('a') as metadata:
            metadata.write('Source-Makefile: package/custom/legacy-app/Makefile\n'
                           'Package: legacy-app\nVersion: 1-r1\n')
        self.make_package('legacy-app', '1-r1')

    def test_full_build_includes_unselected_retained_migration_without_config_edit(self):
        self.migration_fixture()
        config = (self.tree / '.config').read_bytes()
        with patch.object(B, 'run_make') as make, patch.object(B, 'prepare_sequence'), \
                patch.object(B, 'state_path', return_value=self.root / 'absent-state'), \
                patch.object(B, 'configuration', return_value={'CONFIG_OPENWRT_KERNEL_UPGRADE': 'n'}):
            B.build(self.tree, ['-j3'], publish_after=False)
        self.assertIn('CONFIG_PACKAGE_legacy-app=m', make.call_args.args[1])
        self.assertEqual((self.tree / '.config').read_bytes(), config)

    def test_migration_build_options_respect_explicit_selection_and_existing_rebuild(self):
        self.migration_fixture()
        self.assertEqual(B.retained_migration_options(self.tree, []), ['CONFIG_PACKAGE_legacy-app=m'])
        self.assertEqual(B.retained_migration_options(self.tree, ['CONFIG_PACKAGE_legacy-app=n']), [])
        self.make_package('legacy-app', '1-r2')
        self.assertEqual(B.retained_migration_options(self.tree, []), [])
        (self.base / 'legacy-app-1-r2.apk').unlink()
        self.make_package('legacy-app', '1-r3')
        self.assertEqual(B.retained_migration_options(self.tree, []), [])

    def test_retained_published_migration_is_built_even_without_local_apk(self):
        self.migration_fixture()
        package = self.base / 'legacy-app-1-r1.apk'
        shutil.copyfile(package, self.old / 'base' / package.name)
        package.unlink()
        self.assertEqual(B.retained_migration_options(self.tree, [], self.server),
                         ['CONFIG_PACKAGE_legacy-app=m'])

    def test_sequence_advances_without_changing_other_config(self):
        B.publish(self.tree, self.data)
        path = self.tree / '.config'
        before = path.read_text()
        self.assertEqual(B.prepare_sequence(self.tree, self.server), 2)
        self.assertEqual(path.read_text(), before.replace('SEQUENCE=1', 'SEQUENCE=2'))
        self.assertEqual(B.prepare_sequence(self.tree, self.server), 2)

    def test_full_retry_skips_an_unpublished_generation(self):
        self.assertEqual(B.prepare_sequence(self.tree, self.server), 2)
        self.assertIn('SEQUENCE=2\n', (self.tree / '.config').read_text())

    def test_userspace_source_config_and_metadata_keep_sequence(self):
        first = B.prepare_sequence(self.tree, self.server)
        path = self.tree / 'package/custom/user-probe/Makefile'
        path.parent.mkdir(parents=True); path.write_text('PKG_RELEASE:=2\n')
        config = self.tree / '.config'
        config.write_text(config.read_text() + 'CONFIG_PACKAGE_user-probe=y\nCONFIG_USER_SETTING="changed"\n')
        metadata = self.tree / 'tmp/.packageinfo'
        metadata.write_text(metadata.read_text() + 'Source-Makefile: package/custom/user-probe/Makefile\n'
                            'Package: user-probe\nVersion: 2-r1\n')
        self.assertEqual(B.prepare_sequence(self.tree, self.server), first)

    def test_kernel_config_change_with_same_abi_advances_sequence(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        path = self.tree / '.config'
        path.write_text(path.read_text() + 'CONFIG_KERNEL_PRINTK_TIME=y\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_module_source_change_without_vermagic_change_advances(self):
        source = self.tree / 'package/kernel/nic/driver.c'
        source.write_text('original module\n')
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        source.write_text('fixed module, same kernel ABI\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_migration_registry_change_requires_a_new_kernel_generation(self):
        path = self.tree / 'configs/apk-migrations.json'
        path.write_text('{"schema": 1, "rules": []}\n')
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        path.write_text(json.dumps({'schema': 1, 'rules': [{'from': 'kmod-old',
            'to': ['kmod-nic'], 'type': 'empty-compat', 'reason': 'driver merged'}]}) + '\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_kernel_patch_change_advances(self):
        path = self.tree / 'target/linux/generic/pending/100-fix.patch'
        path.parent.mkdir(parents=True); path.write_text('old patch\n')
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        path.write_text('new patch\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_selected_module_option_change_advances(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        path = self.tree / '.config'
        path.write_text(path.read_text() + 'CONFIG_PACKAGE_NIC_DEBUG=y\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_effective_module_version_change_advances(self):
        metadata = self.tree / 'tmp/.packageinfo'
        metadata.write_text(metadata.read_text().replace('Package: kmod-nic\n',
                            'Package: kmod-nic\nVersion: 1000.1.6.18.55-r1\n'))
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        metadata.write_text(metadata.read_text().replace('6.18.55-r1', '6.18.55-r2'))
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_sequence_inside_metadata_is_not_an_input_change(self):
        metadata = self.tree / 'tmp/.packageinfo'
        metadata.write_text(metadata.read_text().replace('Package: kmod-nic\n',
                            'Package: kmod-nic\nVersion: 1000.1.6.18.55-r1\n'))
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        metadata.write_text(metadata.read_text().replace('1000.1.', f'1000.{first}.'))
        self.assertEqual(B.prepare_sequence(self.tree, self.server), first)

    def test_userspace_kernel_request_change_advances(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        path = self.tree / '.config'
        path.write_text(path.read_text() + 'CONFIG_PACKAGE_special-service=y\n')
        metadata = self.tree / 'tmp/.packageinfo'
        metadata.write_text(metadata.read_text() + 'Source-Makefile: package/custom/special/Makefile\n'
                            'Package: special-service\nKernel-Config: CONFIG_SPECIAL_SERVICE=y\n')
        source = self.tree / 'package/custom/special/Makefile'
        source.parent.mkdir(parents=True); source.write_text('# service requires a kernel feature\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_feed_symlink_module_source_change_advances(self):
        feed = self.root / 'feed'; feed.mkdir()
        (feed / 'Makefile').write_text('PKG_RELEASE:=1\n')
        driver = feed / 'driver.c'; driver.write_text('old driver\n')
        provider = self.tree / 'package/kernel/nic'
        shutil.rmtree(provider); provider.symlink_to(feed, target_is_directory=True)
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        driver.write_text('new driver\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_build_tool_change_advances(self):
        path = self.tree / 'staging_dir/host/bin/apk'
        path.parent.mkdir(parents=True); path.write_bytes(b'old tool')
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        path.write_bytes(b'new tool')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_same_inputs_retry_reuses_partial_generation(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        self.assertEqual(B.prepare_sequence(self.tree, self.server), first)

    def test_timestamp_stays_pinned_across_userspace_commit_epochs(self):
        with patch.dict('os.environ', {'SOURCE_DATE_EPOCH': '1000000000'}):
            first = B.prepare_sequence(self.tree, self.server)
        state = json.loads(B.state_path(self.tree).read_text())
        self.generation(first)
        with patch.dict('os.environ', {'SOURCE_DATE_EPOCH': '2000000000'}):
            self.assertEqual(B.prepare_sequence(self.tree, self.server), first)
        self.assertEqual(json.loads(B.state_path(self.tree).read_text())['timestamp'], state['timestamp'])

    def test_changed_compiled_image_with_same_inputs_advances_sequence(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        image = next(self.target.glob(f'linux-image-*-{first}-openwrt-*.apk'))
        original = image.read_bytes()
        (self.release.parents[2] / 'arch/x86/boot/bzImage').write_text('different build timestamp')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)
        self.assertEqual(image.read_bytes(), original)

    def test_changed_generated_kernel_config_advances_sequence(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        (self.release.parents[2] / '.config').write_text('CONFIG_FIXTURE=n\n')
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_recorded_timestamp_must_match_existing_image(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        state = json.loads(B.state_path(self.tree).read_text())
        state['timestamp'] = '2000-01-01 00:00:00 +0000'
        B.save_state(self.tree, state)
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_unrelated_cached_kernel_build_does_not_advance_sequence(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        cached = self.release.parents[3] / 'linux-6.18.54/include/config/kernel.release'
        cached.parent.mkdir(parents=True)
        cached.write_text('unrelated cached kernel\n')
        self.assertEqual(B.prepare_sequence(self.tree, self.server), first)

    def test_missing_compiled_image_with_existing_payload_advances_sequence(self):
        first = B.prepare_sequence(self.tree, self.server)
        self.generation(first)
        (self.release.parents[2] / 'arch/x86/boot/bzImage').unlink()
        self.assertGreater(B.prepare_sequence(self.tree, self.server), first)

    def test_manual_sequence_increase_is_honored(self):
        first = B.prepare_sequence(self.tree, self.server)
        path = self.tree / '.config'
        path.write_text(path.read_text().replace(f'SEQUENCE={first}', 'SEQUENCE=7'))
        self.assertEqual(B.prepare_sequence(self.tree, self.server), 7)

    def test_changing_make_kernel_flags_advances(self):
        first = B.prepare_sequence(self.tree, self.server, ['-j16', 'V=s'])
        self.generation(first)
        self.assertGreater(B.prepare_sequence(self.tree, self.server, ['KCFLAGS=-O3']), first)

    def test_source_change_during_make_prevents_publication(self):
        source = self.tree / 'package/kernel/nic/driver.c'
        source.write_text('old\n')
        def make(tree, arguments):
            if arguments != ['prepare-tmpinfo']:
                source.write_text('edited during build\n')
        with patch.object(B, 'run_make', side_effect=make):
            with patch.object(B, 'publish') as publish:
                with self.assertRaisesRegex(ValueError, 'changed during build'):
                    B.build(self.tree, ['-j16'])
                publish.assert_not_called()

    def test_repeated_full_build_with_userspace_change_keeps_kernel_channel(self):
        timestamps = []
        def make(tree, arguments):
            if arguments == ['prepare-tmpinfo']:
                return
            timestamps.append(next(a for a in arguments if a.startswith('KBUILD_BUILD_TIMESTAMP=')))
            self.generation(int(B.configuration(tree)['CONFIG_OPENWRT_KERNEL_SEQUENCE']))
        with patch.object(B, 'run_make', side_effect=make):
            first = B.build(self.tree, ['-j16'])
            before = self.aliases()
            self.make_package('user-probe', '1-r2')
            second = B.build(self.tree, ['-j16'])
        self.assertEqual(first['generation'], second['generation'])
        self.assertEqual(self.aliases()['kernel'], before['kernel'])
        self.assertNotEqual(self.aliases()['userspace'], before['userspace'])
        self.assertEqual(second['kernel']['status'], 'unchanged')
        self.assertEqual(timestamps[0], timestamps[1])

    def test_failed_full_build_resumes_same_sequence_and_timestamp(self):
        timestamps, sequences = [], []
        fail = True
        def make(tree, arguments):
            if arguments == ['prepare-tmpinfo']:
                return
            timestamps.append(next(a for a in arguments if a.startswith('KBUILD_BUILD_TIMESTAMP=')))
            sequence = int(B.configuration(tree)['CONFIG_OPENWRT_KERNEL_SEQUENCE'])
            sequences.append(sequence)
            self.generation(sequence)
            if fail:
                raise subprocess.CalledProcessError(2, 'make')
        with patch.object(B, 'run_make', side_effect=make):
            with self.assertRaises(subprocess.CalledProcessError):
                B.build(self.tree, ['-j16'])
            self.assertIsNone(self.aliases()['kernel'])
            fail = False
            B.build(self.tree, ['-j16'])
        self.assertEqual(sequences[0], sequences[1])
        self.assertEqual(timestamps[0], timestamps[1])

    def test_failed_make_forwards_arguments_and_does_not_publish(self):
        def make(tree, arguments):
            if arguments != ['prepare-tmpinfo']:
                raise subprocess.CalledProcessError(2, 'make')
        with patch.object(B, 'run_make', side_effect=make) as run:
            with patch.object(B, 'publish') as publish:
                with self.assertRaises(subprocess.CalledProcessError):
                    B.build(self.tree, ['-j16', 'V=s'])
                self.assertEqual(run.call_args_list[0].args, (self.tree, ['prepare-tmpinfo']))
                arguments = run.call_args_list[1].args[1]
                self.assertEqual(arguments[:2], ['-j16', 'V=s'])
                self.assertTrue(arguments[2].startswith('KBUILD_BUILD_TIMESTAMP='))
                publish.assert_not_called()

    def test_successful_full_build_advances_sequence_and_publishes_after_make(self):
        B.publish(self.tree, self.data)
        events = []
        def make(tree, arguments):
            if arguments == ['prepare-tmpinfo']:
                return
            events.append('make')
            self.assertIn('SEQUENCE=2\n', (self.tree / '.config').read_text())
        def publish(*args, **kwargs):
            events.append('publish')
        with patch.object(B, 'run_make', side_effect=make):
            with patch.object(B, 'publish', side_effect=publish):
                B.build(self.tree, ['-j16', 'V=s'])
        self.assertEqual(events, ['make', 'publish'])

    def test_package_only_build_keeps_sequence(self):
        B.publish(self.tree, self.data)
        with patch.object(B, 'run_make'):
            with patch.object(B, 'publish'):
                B.build(self.tree, ['-j16', 'package/custom/example/compile'])
        self.assertIn('SEQUENCE=1\n', (self.tree / '.config').read_text())

    def test_build_only_never_publishes_before_external_validation(self):
        with patch.object(B, 'run_make'), patch.object(B, 'publish') as publish:
            result = B.build(self.tree, ['-j8', 'V=s'], publish_after=False)
        self.assertEqual(result['status'], 'built')
        publish.assert_not_called()

    def test_make_preview_is_rejected_without_changing_config(self):
        before = (self.tree / '.config').read_bytes()
        with self.assertRaisesRegex(ValueError, 'preview/touch'):
            B.build(self.tree, ['--dry-run', '-j16'])
        self.assertEqual((self.tree / '.config').read_bytes(), before)

    def test_sequence_overflow_fails_without_changing_config(self):
        B.publish(self.tree, self.data)
        manifest = self.server / 'public/kernel-upgrades/manifest.json'
        data = json.loads(manifest.read_text()); data['sequence'] = 999999
        manifest.write_text(json.dumps(data))
        before = (self.tree / '.config').read_bytes()
        with self.assertRaisesRegex(ValueError, 'exhausted'):
            B.prepare_sequence(self.tree, self.server)
        self.assertEqual((self.tree / '.config').read_bytes(), before)

    def test_unsigned_kernel_does_not_publish_userspace(self):
        self.make_package('linux-image-6.18.55-1-openwrt', '6.18.55-r1', ['openwrt-kernel-upgrade'],
                          signed=False)
        self.make_package('user-probe', '1-r2')
        before = self.aliases()
        with self.assertRaises(subprocess.CalledProcessError):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)

    def test_republishing_an_older_generation_is_rejected(self):
        B.publish(self.tree, self.data)
        self.generation(2)
        B.publish(self.tree, self.data)
        self.release.write_text('6.18.55-1-openwrt\n')
        path = self.tree / '.config'
        path.write_text(path.read_text().replace('SEQUENCE=2', 'SEQUENCE=1'))
        before = self.aliases()
        with self.assertRaisesRegex(ValueError, 'stale kernel generation'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)

    def test_stale_compiled_generation_is_rejected(self):
        (self.tree / '.config').write_text((self.tree / '.config').read_text().replace('SEQUENCE=1', 'SEQUENCE=2'))
        before = self.aliases()
        with self.assertRaisesRegex(ValueError, 'Compiled kernel release'):
            B.publish(self.tree, self.data)
        self.assertEqual(self.aliases(), before)

    def test_new_abi_has_signed_empty_target_view(self):
        other = ABI.replace('a' * 32, 'c' * 32)
        # A new ABI needs userspace views even when it has no ABI-local APKs;
        # the independent channel supplies its kernel assets later.
        args = argparse.Namespace(source_root=self.tree, kernel=other, destination=self.server,
            base_url=self.data['base_url'], incremental=True, dry_run=False, kernel_upgrade_view=True)
        result = B.LAN.publish(args)
        target = Path(result['snapshot']) / 'target/packages.adb'
        data = json.loads(subprocess.check_output([str(APK), 'adbdump', '--format', 'json', str(target)]))
        # Only the kernel-independent kmod configuration packages remain.
        self.assertEqual({p['name'] for p in data.get('packages', [])}, {'kmod-nic'})
        self.assertTrue((self.server / 'public/abi' / ABI).exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
