#!/usr/bin/env python3
"""Exercise publication and failure isolation using real signed APK fixtures."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
APK = TREE / 'staging_dir/host/bin/apk'
PUBLISHER = TREE / 'scripts/publish-lan-apk-feeds.py'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PublisherTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        kernels = list((TREE / 'bin/systemd/targets/x86/64-glibc/packages').glob('kernel-*.apk'))
        if not APK.exists() or len(kernels) != 1:
            raise unittest.SkipTest('Build apk/host and one native-systemd kernel APK first')
        cls.kernel_apk = kernels[0]
        cls.kernel = json.loads(subprocess.check_output(
            [str(APK), 'adbdump', '--format', 'json', str(cls.kernel_apk)]))['info']['version']

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='lan-feed-test-')
        self.root = Path(self.temporary.name)
        self.source = self.root / 'build'
        self.destination = self.root / 'server'
        self.target = self.source / 'bin/systemd/targets/x86/64-glibc/packages'
        self.base = self.source / 'bin/systemd/packages/x86_64/base'
        self.upstream = self.source / 'bin/systemd/packages/x86_64/packages'
        for directory in (self.target, self.base, self.upstream):
            directory.mkdir(parents=True)
        shutil.copyfile(self.kernel_apk, self.target / self.kernel_apk.name)
        self.make_package('feed-probe', '1.0-r1', 'initial')
        self.make_package('feed-kernel-probe', '1.0-r1', 'initial', depends='kernel=' + self.kernel)
        self.make_package('upstream-probe', '1.0-r1', 'initial', custom=False)
        self.command = ['python3', str(PUBLISHER), '--kernel', self.kernel,
                        '--source-root', str(self.source), '--destination', str(self.destination),
                        '--base-url', 'http://127.0.0.1:8088']
        initial = self.publish(incremental=False)
        self.before = Path(initial['snapshot'])
        self.alias = self.destination / 'public/abi' / self.kernel

    def tearDown(self):
        self.temporary.cleanup()

    def make_package(self, name, version, content, *, custom=True, signed=True, depends='libc',
                     provides=''):
        payload = self.root / ('payload-' + name)
        file = payload / 'usr/share/feed-test' / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(content + '\n')
        package = (self.base if custom else self.upstream) / f'{name}-{version}.apk'
        origin = 'feeds/base/custom/feed-test' if custom else 'feeds/packages/utils/feed-test'
        command = [str(APK), 'mkpkg', '--info', 'name:' + name, '--info', 'version:' + version,
                   '--info', 'arch:x86_64', '--info', 'license:MIT', '--info', 'origin:' + origin,
                   '--info', 'description:Disposable publishing test', '--info', 'depends:' + depends,
                   '--files', str(payload), '--output', str(package)]
        if signed:
            command += ['--sign-key', str(TREE / 'private-key.pem')]
        if provides:
            command += ['--info', 'provides:' + provides]
        subprocess.run(command, check=True, capture_output=True)
        return package

    def publish(self, *, incremental=True, dry_run=False):
        command = self.command + (['--incremental'] if incremental else [])
        if dry_run:
            command += ['--dry-run']
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return json.loads(result.stdout)

    def assert_failed_publication(self, expected=None):
        before = self.alias.resolve()
        snapshots = set((self.destination / 'public/snapshots').iterdir())
        result = subprocess.run(self.command + ['--incremental'], capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        if expected:
            self.assertIn(expected, result.stdout + result.stderr)
        self.assertEqual(self.alias.resolve(), before)
        self.assertEqual(set((self.destination / 'public/snapshots').iterdir()), snapshots)

    def test_detect_kernel_without_override(self):
        self.command = self.command[:2] + self.command[4:]
        self.assertEqual(self.publish()['kernel'], self.kernel)

    def test_detect_metadata_when_kernel_apk_was_cleaned(self):
        version = self.source / 'staging_dir/target-x86_64_glibc/kernel.version'
        version.parent.mkdir(parents=True)
        version.write_text(self.kernel + '\n')
        (self.target / self.kernel_apk.name).unlink()
        self.command = self.command[:2] + self.command[4:]
        self.assertEqual(self.publish()['status'], 'unchanged')

    def test_detect_new_abi_keeps_old_router_alias_unchanged(self):
        new_kernel = '6.18.55~11111111111111111111111111111111-r1'
        (self.target / self.kernel_apk.name).unlink()
        package = self.make_package('kernel', new_kernel, 'new kernel', custom=False)
        shutil.move(str(package), self.target / package.name)
        self.make_package('feed-kernel-probe', '1.0-r1', 'new ABI', depends='kernel=' + new_kernel)
        self.command = self.command[:2] + self.command[4:]
        result = self.publish()
        self.assertEqual(result['kernel'], new_kernel)
        self.assertEqual(self.alias.resolve(), self.before)
        self.assertTrue((self.destination / 'public/abi' / new_kernel).is_dir())

    def test_detect_rejects_stale_metadata(self):
        version = self.source / 'staging_dir/target-x86_64_glibc/kernel.version'
        version.parent.mkdir(parents=True)
        version.write_text('6.18.55~wrong-r1\n')
        self.command = self.command[:2] + self.command[4:]
        self.assert_failed_publication('does not match kernel APK')

    def test_detect_missing_metadata_and_apk_fails_closed(self):
        (self.target / self.kernel_apk.name).unlink()
        self.command = self.command[:2] + self.command[4:]
        self.assert_failed_publication('Cannot detect build kernel ABI')

    def test_unchanged_is_noop(self):
        snapshots = set((self.destination / 'public/snapshots').iterdir())
        result = self.publish()
        self.assertEqual(result['status'], 'unchanged')
        self.assertEqual(result['affected_repositories'], [])
        self.assertEqual(self.alias.resolve(), self.before)
        self.assertEqual(set((self.destination / 'public/snapshots').iterdir()), snapshots)

    def test_upgrade_retains_old_packages_and_reuses_other_indexes(self):
        (self.base / 'feed-probe-1.0-r1.apk').unlink()
        (self.target / self.kernel_apk.name).unlink()
        new = self.make_package('feed-probe', '1.0-r2', 'upgraded')
        result = self.publish()
        after = Path(result['snapshot'])
        self.assertEqual(result['affected_repositories'], ['base', 'custom'])
        self.assertEqual(len(result['changed_packages']), 1)
        for repository in ('base', 'custom'):
            self.assertTrue((after / repository / 'feed-probe-1.0-r1.apk').exists())
            self.assertEqual(digest(after / repository / new.name), digest(new))
            self.assertNotEqual(digest(after / repository / 'packages.adb'),
                                digest(self.before / repository / 'packages.adb'))
        for repository in ('target', 'packages'):
            self.assertEqual((after / repository / 'packages.adb').stat().st_ino,
                             (self.before / repository / 'packages.adb').stat().st_ino)

    def test_same_version_rebuild_keeps_previous_snapshot_immutable(self):
        filename = 'feed-probe-1.0-r1.apk'
        old_apk = digest(self.before / 'base' / filename)
        old_indexes = {name: digest(self.before / name / 'packages.adb')
                       for name in ('base', 'custom')}
        new = self.make_package('feed-probe', '1.0-r1', 'different payload, same version')
        result = self.publish()
        after = Path(result['snapshot'])
        self.assertEqual(result['same_version_rebuilds'], ['base/' + filename])
        for repository in ('base', 'custom'):
            self.assertEqual(digest(after / repository / filename), digest(new))
            self.assertEqual(digest(self.before / repository / filename), old_apk)
            self.assertEqual(digest(self.before / repository / 'packages.adb'), old_indexes[repository])

    def test_ucode_abi_mismatch_does_not_switch_feed(self):
        self.make_package('ucode', '2-r1', 'new interpreter', provides='ucode-abi=222')
        self.make_package('ucode-mod-probe', '1-r1', 'stale plugin',
                          depends='ucode-abi=111 libucode111')
        self.assert_failed_publication('incompatible lock')

    def test_incremental_abi_upgrade_checks_retained_consumers(self):
        self.make_package('ucode', '1-r1', 'old interpreter', provides='ucode-abi=111')
        plugin = self.make_package('ucode-mod-probe', '1-r1', 'old plugin',
                                   depends='ucode-abi=111 libucode111')
        self.publish()
        plugin.unlink()
        self.make_package('ucode', '2-r1', 'new interpreter', provides='ucode-abi=222')
        self.assert_failed_publication('incompatible lock')
        self.make_package('ucode-mod-probe', '1-r2', 'new plugin',
                          depends='ucode-abi=222 libucode222')
        self.assertEqual(self.publish()['ucode_abi']['abi'], '222')

    def test_same_version_ucode_rebuild_is_rejected(self):
        self.make_package('ucode', '1-r1', 'original', provides='ucode-abi=111')
        self.publish()
        self.make_package('ucode', '1-r1', 'different bytes', provides='ucode-abi=111')
        self.assert_failed_publication('bump PKG_RELEASE')

    def test_same_version_ucode_library_rebuild_is_rejected(self):
        self.make_package('ucode', '1-r1', 'interpreter', provides='ucode-abi=111')
        self.make_package('libucode111', '1-r1', 'original runtime library')
        self.publish()
        self.make_package('libucode111', '1-r1', 'changed runtime library')
        self.assert_failed_publication('bump PKG_RELEASE')

    def test_dry_run_does_not_switch_or_retain_a_snapshot(self):
        self.make_package('feed-probe', '1.0-r2', 'preview')
        snapshots = set((self.destination / 'public/snapshots').iterdir())
        result = self.publish(dry_run=True)
        self.assertEqual(result['status'], 'dry-run')
        self.assertEqual(result['affected_repositories'], ['base', 'custom'])
        self.assertEqual(self.alias.resolve(), self.before)
        self.assertEqual(set((self.destination / 'public/snapshots').iterdir()), snapshots)

    def test_wrong_kernel_abi_is_rejected(self):
        self.make_package('kmod-feed-probe', '1.0-r1', 'bad ABI',
                          depends='kernel=6.18.55~00000000000000000000000000000000-r1')
        self.assert_failed_publication('Kernel ABI mismatch')

    def test_existing_kernel_dependent_package_is_immutable(self):
        self.make_package('feed-kernel-probe', '1.0-r1', 'changed protected package',
                          depends='kernel=' + self.kernel)
        self.assert_failed_publication('Existing ABI package changed or disappeared')

    def test_unsigned_package_is_rejected(self):
        self.make_package('unsigned-probe', '1.0-r1', 'no signature', signed=False)
        self.assert_failed_publication()

    def test_conflicting_custom_copies_are_rejected(self):
        package = self.make_package('feed-probe', '1.0-r1', 'conflicting copy')
        shutil.copyfile(package, self.upstream / package.name)
        shutil.copyfile(self.before / 'base' / package.name, package)
        self.assert_failed_publication('Conflicting custom APKs')


if __name__ == '__main__':
    unittest.main(verbosity=2)
