#!/usr/bin/env python3
"""Resolve the effective kernel series before evaluating package Kconfig."""
import importlib.util
from pathlib import Path
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('kernel_inputs', TREE / 'scripts/kernel-build-inputs.py')
K = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(K)


class KernelSelection(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='kernel-inputs-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.target = self.root / 'target/linux/x86'
        (self.target / '64').mkdir(parents=True)
        (self.target / 'Makefile').write_text('KERNEL_PATCHVER:=6.18\n')
        self.config = {'CONFIG_TARGET_BOARD': '"x86"', 'CONFIG_TARGET_SUBTARGET': '"64"'}

    def test_subtarget_overrides_parent(self):
        (self.target / '64/target.mk').write_text('KERNEL_PATCHVER:=7.3\n')
        self.assertEqual(K.kernel_patchver(self.root, self.config), '7.3')

    def test_parent_retained_for_other_subtargets(self):
        self.config['CONFIG_TARGET_SUBTARGET'] = '"legacy"'
        self.assertEqual(K.kernel_patchver(self.root, self.config), '6.18')

    def test_testing_kernel_override(self):
        (self.target / '64/target.mk').write_text('KERNEL_PATCHVER:=7.3\nKERNEL_TESTING_PATCHVER:=7.4\n')
        self.config['CONFIG_TESTING_KERNEL'] = 'y'
        self.assertEqual(K.kernel_patchver(self.root, self.config), '7.4')

    def test_command_line_takes_precedence(self):
        self.config['CONFIG_TESTING_KERNEL'] = 'y'
        self.assertEqual(K.kernel_patchver(self.root, self.config, ['KERNEL_PATCHVER=7.2']), '7.2')

    def test_command_line_testing_selection(self):
        (self.target / '64/target.mk').write_text('KERNEL_TESTING_PATCHVER:=7.4\n')
        self.assertEqual(K.kernel_patchver(self.root, self.config, ['CONFIG_TESTING_KERNEL=y']), '7.4')

    def test_unresolved_dynamic_selection_fails(self):
        (self.target / '64/target.mk').write_text('KERNEL_PATCHVER:=$(OTHER_VERSION)\n')
        with self.assertRaisesRegex(ValueError, 'Nonliteral'):
            K.kernel_patchver(self.root, self.config)

    def test_fallback_requires_unambiguous_staging_metadata(self):
        (self.target / 'Makefile').unlink()
        path = self.root / 'staging_dir/target-x86_64_glibc/kernel.version'
        path.parent.mkdir(parents=True)
        path.write_text('6.18.55~abc-r1\n')
        self.assertEqual(K.kernel_patchver(self.root, self.config), '6.18')


class NarrowedFingerprintTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='kernel-fp-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / 'tmp').mkdir(parents=True)
        (self.root / 'tmp/.packageinfo').write_text(
            'Source-Makefile: package/kernel/linux/Makefile\n'
            'Package: kmod-nic\n'
            'Version: 1000.85.1-r1\n'
            'Source: package/kernel/linux\n'
        )
        (self.root / 'package/kernel/linux').mkdir(parents=True)
        (self.root / 'package/kernel/linux/Makefile').write_text('# kernel\n')
        (self.root / 'target/linux/generic/pending-7.3').mkdir(parents=True)
        (self.root / 'target/linux/generic/pending-7.3/001-active.patch').write_text('active\n')
        (self.root / 'target/linux/generic/pending-6.18').mkdir(parents=True)
        (self.root / 'target/linux/generic/pending-6.18/001-inactive.patch').write_text('inactive\n')
        (self.root / 'target/linux/generic/kernel-7.3').write_text('LINUX_VERSION-7.3 = .5\n')
        (self.root / 'target/linux/generic/kernel-6.18').write_text('LINUX_VERSION-6.18 = .55\n')
        (self.root / 'target/linux/x86/64').mkdir(parents=True)
        (self.root / 'target/linux/x86/Makefile').write_text('KERNEL_PATCHVER:=6.18\n')
        (self.root / 'target/linux/x86/64/target.mk').write_text('KERNEL_PATCHVER:=7.3\n')
        (self.root / 'target/linux/x86/patches-7.3').mkdir(parents=True)
        (self.root / 'target/linux/x86/patches-7.3/001-x86.patch').write_text('x86-7.3\n')
        (self.root / 'target/linux/x86/patches-6.18').mkdir(parents=True)
        (self.root / 'target/linux/x86/patches-6.18/001-x86.patch').write_text('x86-6.18\n')
        (self.root / 'target/linux/x86/image').mkdir(parents=True)
        (self.root / 'target/linux/x86/image/Makefile').write_text('# iso recipe\n')
        (self.root / 'include').mkdir(parents=True)
        (self.root / 'include/kernel-version.mk').write_text('# ver\n')
        self.config = {
            'CONFIG_TARGET_BOARD': '"x86"',
            'CONFIG_TARGET_SUBTARGET': '"64"',
            'CONFIG_OPENWRT_KERNEL_UPGRADE': 'y',
            'CONFIG_OPENWRT_KERNEL_SEQUENCE': '85',
            'CONFIG_PACKAGE_kmod-nic': 'y',
            'CONFIG_INSTALLER_ISO_IMAGES': 'y',
        }
        (self.root / '.config').write_text(
            ''.join(f'{k}={v}\n' for k, v in sorted(self.config.items()))
        )

    def test_iso_recipe_and_inactive_series_changes_do_not_change_fingerprint(self):
        before = K.fingerprint(self.root, self.config)
        # Edit pure ISO recipe, inactive 6.18 patches/version, and GRUB/ISO config
        (self.root / 'target/linux/x86/image/Makefile').write_text('# updated iso recipe\n')
        (self.root / 'target/linux/generic/pending-6.18/001-inactive.patch').write_text('changed 6.18\n')
        (self.root / 'target/linux/x86/patches-6.18/001-x86.patch').write_text('changed x86 6.18\n')
        (self.root / 'target/linux/generic/kernel-6.18').write_text('LINUX_VERSION-6.18 = .56\n')
        cfg2 = {**self.config, 'CONFIG_GRUB_BOOTOPTS': '"split_lock_detect=off"'}
        after = K.fingerprint(self.root, cfg2)
        self.assertTrue(K.same_inputs(before, after))
        _, changes = K.diff_inputs(before, after)
        self.assertEqual(changes, [])

    def test_active_series_patch_and_kcflags_change_fingerprint_with_pinpointed_diff(self):
        before = K.fingerprint(self.root, self.config)
        (self.root / 'target/linux/x86/patches-7.3/001-x86.patch').write_text('modified active patch\n')
        after = K.fingerprint(self.root, self.config)
        self.assertFalse(K.same_inputs(before, after))
        groups, changes = K.diff_inputs(before, after)
        self.assertIn('kernel_patches', groups)
        self.assertTrue(any('kernel_patches: target/linux/x86/patches-7.3/001-x86.patch' in c for c in changes))

        after_flags = K.fingerprint(self.root, self.config, ('KCFLAGS=-O3',))
        self.assertFalse(K.same_inputs(after, after_flags))
        _, flag_changes = K.diff_inputs(after, after_flags)
        self.assertTrue(any(c.startswith('build_env: arguments') for c in flag_changes))

    def test_env_kernel_config_change_advances_fingerprint(self):
        before = K.fingerprint(self.root, self.config)
        (self.root / 'env').mkdir(parents=True)
        (self.root / 'env/kernel-config').write_text('CONFIG_FOO=y\n')
        after = K.fingerprint(self.root, self.config)
        self.assertFalse(K.same_inputs(before, after))
        _, changes = K.diff_inputs(before, after)
        self.assertTrue(any('kernel_config: env/kernel-config' in c for c in changes))


if __name__ == '__main__':
    unittest.main()
