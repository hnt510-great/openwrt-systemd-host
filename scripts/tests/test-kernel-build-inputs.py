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


if __name__ == '__main__':
    unittest.main()
