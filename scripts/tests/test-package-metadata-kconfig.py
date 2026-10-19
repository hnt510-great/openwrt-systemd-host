#!/usr/bin/env python3
"""Exercise propagated constraints through the metadata generator and Kconfig."""
import itertools
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


TREE = Path(__file__).resolve().parents[2]
GENERATOR = TREE / 'scripts/package-metadata.pl'
CONF = TREE / 'scripts/config/conf'


class PackageMetadataKconfigTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix='package-metadata-kconfig-')
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / 'package').mkdir()

    def generate(self, packages):
        metadata = []
        for name, depends, extra in packages:
            metadata.append(
                f'Source-Makefile: package/{name}/Makefile\n'
                f'Package: {name}\nCategory: Test\nTitle: {name}\n'
                f'Depends: {depends}\n{extra}\n'
                'Description: Fixture package\n@@\n')
        source = self.root / 'metadata'
        source.write_text('\n'.join(metadata))
        result = subprocess.run(
            ['perl', str(GENERATOR), 'config', str(source)],
            cwd=self.root, text=True, capture_output=True, check=True)
        return result.stdout

    def configure(self, generated, symbols, settings):
        if not CONF.exists():
            self.skipTest('build scripts/config/conf first')
        (self.root / 'Config.in').write_text(
            'config MODULES\n\tbool\n\tmodules\n\tdefault y\n'
            + symbols + '\n' + generated)
        (self.root / 'input').write_text(''.join(
            f'CONFIG_{key}={value}\n' for key, value in settings.items()))
        environment = os.environ.copy()
        environment['KCONFIG_CONFIG'] = str(self.root / 'output')
        result = subprocess.run(
            [str(CONF), '--fatalrecursive', '--defconfig=input', '-w',
             str(self.root / 'output'), 'Config.in'],
            cwd=self.root, env=environment, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        values = {}
        for line in (self.root / 'output').read_text().splitlines():
            if line.startswith('CONFIG_'):
                key, value = line[7:].split('=', 1)
                values[key] = value
            elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
                values[line[9:-11]] = 'n'
        return values

    def test_nested_guards_do_not_create_package_option_cycles(self):
        # The first feature models dnsmasq/fwknop; the nested condition models
        # gensio's IPv6/SCTP option. All feature options depend on the consumer.
        generated = self.generate([
            ('consumer', '+FEATURE:bridge +(IPV6&&SCTP):sctp',
             'Config:\nconfig FEATURE\n\tbool "Feature"\n'
             '\tdepends on PACKAGE_consumer\n'
             'config SCTP\n\tbool "SCTP"\n'
             '\tdepends on PACKAGE_consumer && IPV6\n@@'),
            ('bridge', '+!LINUX_6_12:legacy +LINUX_6_12:modern', ''),
            ('legacy', '@!LINUX_6_12', ''),
            ('modern', '@LINUX_6_12', ''),
            ('sctp', '@IPV6 +LINUX_6_12:modern', ''),
        ])
        symbols = ('config LINUX_6_12\n\tbool "Old kernel"\n'
                   'config IPV6\n\tbool "IPv6"\n')
        for old, ipv6, feature, sctp in itertools.product('ny', repeat=4):
            with self.subTest(old=old, ipv6=ipv6, feature=feature, sctp=sctp):
                values = self.configure(generated, symbols, {
                    'PACKAGE_consumer': 'y', 'LINUX_6_12': old,
                    'IPV6': ipv6, 'FEATURE': feature, 'SCTP': sctp,
                })
                self.assertEqual(values['PACKAGE_consumer'], 'y')
                self.assertEqual(values.get('PACKAGE_bridge', 'n'), feature)
                self.assertEqual(values.get('PACKAGE_sctp', 'n'),
                                 'y' if ipv6 == sctp == 'y' else 'n')
                self.assertEqual(values.get('PACKAGE_legacy', 'n'),
                                 'y' if feature == 'y' and old == 'n' else 'n')
                self.assertEqual(values.get('PACKAGE_modern', 'n'),
                                 'y' if old == 'y' and (feature == 'y' or ipv6 == sctp == 'y') else 'n')

    def test_required_constraints_and_disjunctions_are_retained(self):
        for condition in ['FEATURE', '(IPV6||FEATURE)',
                          '(IPV6&&FEATURE)||OTHER', '!(IPV6&&FEATURE)',
                          'IPV6_EXTRA']:
            generated = self.generate([
                ('consumer', f'+{condition}:library', ''),
                ('library', '@IPV6', ''),
            ])
            symbols = ''.join(f'config {name}\n\tbool "{name}"\n'
                              for name in ['IPV6', 'FEATURE', 'OTHER', 'IPV6_EXTRA'])
            with self.subTest(condition=condition):
                self.assertIn(f'depends on !({condition}) || IPV6', generated)
                values = self.configure(generated, symbols, {
                    'PACKAGE_consumer': 'y', 'IPV6': 'n', 'FEATURE': 'y',
                    'OTHER': 'y', 'IPV6_EXTRA': 'y',
                })
                self.assertEqual(values.get('PACKAGE_consumer', 'n'), 'n')

    def test_virtual_provider_tristate_fallback_and_constraints(self):
        generated = self.generate([
            ('consumer', '+virtual', ''),
            ('fallback', '+IPV6:library',
             'Provides: virtual\nDefault-Variant: 1\nConflicts: alternative'),
            ('alternative', '', 'Provides: virtual'),
            ('library', '@IPV6', ''),
        ])
        symbols = 'config IPV6\n\tbool "IPv6"\n'
        for consumer, alternative, ipv6 in itertools.product('nmy', 'nmy', 'ny'):
            with self.subTest(consumer=consumer, alternative=alternative, ipv6=ipv6):
                values = self.configure(generated, symbols, {
                    'PACKAGE_consumer': consumer,
                    'PACKAGE_alternative': alternative, 'IPV6': ipv6,
                })
                self.assertEqual(values.get('PACKAGE_consumer', 'n'), consumer)
                expected = consumer if 'nmy'.index(alternative) < 'nmy'.index(consumer) else 'n'
                self.assertEqual(values.get('PACKAGE_fallback', 'n'), expected)
                self.assertEqual(values.get('PACKAGE_library', 'n'),
                                 expected if ipv6 == 'y' else 'n')

    def test_tristate_guards_retain_module_limits(self):
        generated = self.generate([
            ('consumer', '+FEATURE:bridge', ''),
            ('bridge', '+GATE:library', ''),
            ('library', '@GATE', ''),
        ])
        symbols = ('config FEATURE\n\tbool "Feature"\n'
                   'config GATE\n\ttristate "Gate"\n')
        for feature, gate in itertools.product('ny', 'nmy'):
            with self.subTest(feature=feature, gate=gate):
                values = self.configure(generated, symbols, {
                    'PACKAGE_consumer': 'y', 'FEATURE': feature, 'GATE': gate,
                })
                expected = 'm' if feature == 'y' and gate == 'm' else 'y'
                self.assertEqual(values['PACKAGE_consumer'], expected)


if __name__ == '__main__':
    unittest.main()
