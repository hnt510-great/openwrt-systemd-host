#!/usr/bin/env python3
"""Verify ELF ABI detection and real APK solver rejection of mixed runtimes."""
import importlib.util
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
APK = TREE / 'staging_dir/host/bin/apk'
spec = importlib.util.spec_from_file_location('ucode_abi', TREE / 'scripts/ucode-abi.py')
ABI = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ABI)


class UcodeAbiTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('cc') or not shutil.which('readelf') or not APK.exists():
            self.skipTest('Requires native cc/readelf and built apk/host')
        self.temp = tempfile.TemporaryDirectory(prefix='ucode-abi-test-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / 'payload'
        self.root.mkdir()

    def consumer(self, abi='111'):
        source = self.work / 'probe.c'
        source.write_text('int probe(void) { return 0; }\n')
        library = self.work / f'libucode.so.{abi}'
        subprocess.run(['cc', '-shared', '-fPIC', str(source), '-Wl,-soname,' + library.name,
                        '-o', str(library)], check=True, capture_output=True)
        consumer = self.root / 'usr/sbin/netifd'
        consumer.parent.mkdir(parents=True)
        source.write_text('extern int probe(void); int main(void) { return probe(); }\n')
        subprocess.run(['cc', str(source), str(library), '-o', str(consumer)],
                       check=True, capture_output=True)
        return consumer

    def package(self, name, version, *, depends='', provides=''):
        payload = self.work / ('files-' + name)
        payload.mkdir(exist_ok=True)
        (payload / name).write_text(version)
        package = self.work / f'{name}-{version}.apk'
        args = [str(APK), 'mkpkg', '--info', 'name:' + name, '--info', 'version:' + version,
                '--info', 'arch:x86_64', '--info', 'description:ABI solver fixture',
                '--info', 'license:MIT', '--files', str(payload), '--output', str(package),
                '--sign-key', str(TREE / 'private-key.pem')]
        for key, value in [('depends', depends), ('provides', provides)]:
            if value:
                args += ['--info', key + ':' + value]
        subprocess.run(args, check=True, capture_output=True)
        return package

    def test_embedded_runtime_gets_library_and_shared_abi_lock(self):
        self.consumer()
        self.assertEqual(ABI.requirements(self.root, 'netifd', '111'),
                         ['libucode111', 'ucode-abi=111'])

    def test_stale_elf_rejected_even_when_package_metadata_claims_current(self):
        self.consumer('111')
        with self.assertRaisesRegex(ValueError, 'ELF uses libucode ABI'):
            ABI.requirements(self.root, 'netifd', '222')

    def test_c_module_without_dt_needed_is_locked(self):
        module = self.root / 'usr/lib/ucode/plugin.so'
        module.parent.mkdir(parents=True)
        source = self.work / 'module.c'
        source.write_text('extern void uc_module_init(void); void probe(void) { uc_module_init(); }')
        subprocess.run(['cc', '-shared', '-fPIC', str(source), '-o', str(module)],
                       check=True, capture_output=True)
        self.assertEqual(ABI.requirements(self.root, 'ucode-mod-test', '222'),
                         ['libucode222', 'ucode-abi=222'])

    def test_interpreter_does_not_depend_on_its_own_virtual_provider(self):
        self.consumer()
        self.assertEqual(ABI.requirements(self.root, 'ucode', '111'), [])

    def test_unrelated_files_and_soname_literals_do_not_create_dependencies(self):
        (self.root / 'text').write_text('libucode.so.111')
        source = self.work / 'literal.c'
        source.write_text('const char *x="libucode.so.111"; int main(void) { return 0; }')
        subprocess.run(['cc', str(source), '-o', str(self.root / 'binary')],
                       check=True, capture_output=True)
        self.assertEqual(ABI.requirements(self.root, 'unrelated', ''), [])

    def test_solver_rejects_partial_abi_upgrade_and_accepts_coordinated_upgrade(self):
        old = self.package('ucode', '1-r1', provides='ucode-abi=111')
        consumer = self.package('netifd', '1-r1', depends='ucode-abi=111')
        new = self.package('ucode', '2-r1', provides='ucode-abi=222')
        fixed = self.package('netifd', '1-r2', depends='ucode-abi=222')
        root = self.work / 'apk-root'
        root.mkdir()
        common = [str(APK), '--root', str(root), '--keys-dir', str(TREE),
                  '--repositories-file', '/dev/null', '--no-network', '--no-scripts',
                  '--no-logfile', '--no-interactive', '--force-non-repository']
        installed = subprocess.run(common + ['add', '--initdb', '--usermode', str(old), str(consumer)],
                                   text=True, capture_output=True)
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        rejected = subprocess.run(common + ['add', '--simulate', str(new)],
                                  text=True, capture_output=True)
        self.assertNotEqual(rejected.returncode, 0, rejected.stdout + rejected.stderr)
        self.assertIn('ucode-abi', rejected.stdout + rejected.stderr)
        accepted = subprocess.run(common + ['add', '--simulate', str(new), str(fixed)],
                                  text=True, capture_output=True)
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
