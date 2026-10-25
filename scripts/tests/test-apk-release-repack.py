#!/usr/bin/env python3
"""Verify audited release repackaging with real signed native and data APKs."""
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
APK = TREE / 'staging_dir/host/bin/apk'
FAKEROOT = APK.with_name('fakeroot')
spec = importlib.util.spec_from_file_location('repack_elf', TREE / 'scripts/elf-abi.py')
ELF = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ELF)


class ReleaseRepackTests(unittest.TestCase):
    def setUp(self):
        if not APK.exists() or not FAKEROOT.exists() or not shutil.which('cc'):
            self.skipTest('Requires apk/host, fakeroot and cc')
        self.temp = tempfile.TemporaryDirectory(prefix='apk-release-repack-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.records = {}
        library_root = self.work / 'payloads/libprobe1'
        library = library_root / 'usr/lib/libprobe.so.1'
        library.parent.mkdir(parents=True)
        source = self.work / 'probe.c'
        source.write_text('int probe(void) { return 42; }\n')
        subprocess.run(['cc', '-shared', '-nostdlib', '-fPIC', str(source),
                        '-Wl,-soname,libprobe.so.1', '-o', str(library)], check=True)
        inventory = {**ELF.inspect(library_root), 'package': 'libprobe1', 'version': '1-r2'}
        stamp = library_root / 'usr/lib/apk/packages/libprobe1.elf.json'
        ELF.write_changed(stamp, json.dumps(inventory) + '\n', mode=0o644)
        self.package('libprobe1', library_root, provides='libprobe=1-r2 so:libprobe.so.1=0')
        data_root = self.work / 'payloads/probe-data'
        data = data_root / 'usr/share/probe/data'
        data.parent.mkdir(parents=True)
        data.write_text('preserve contents and permissions\n')
        data.chmod(0o640)
        self.package('probe-data', data_root, depends='libprobe1=1-r2')
        idroot = self.work / 'idroot'
        (idroot / 'etc').mkdir(parents=True)
        (idroot / 'etc/passwd').write_text('root:x:0:0::/:/bin/false\n')
        (idroot / 'etc/group').write_text('root:x:0:\n')
        self.plan = {'records': self.records, 'workspace': str(self.work),
                     'output': str(self.work / 'output'), 'idroot': str(idroot),
                     'users': {'root': 0}, 'groups': {'root': 0}}

    def package(self, name, root, provides='', depends=''):
        package = self.work / (name + '-1-r2.apk')
        script = self.work / 'post-install'
        script.write_text('#!/bin/sh\nexit 0\n')
        subprocess.run([str(FAKEROOT), str(APK), 'mkpkg', '--files', str(root),
                        '--output', str(package), '--sign-key', str(TREE / 'private-key.pem'),
                        '--info', 'name:' + name, '--info', 'version:1-r2',
                        '--info', 'arch:x86_64', '--info', 'provides:' + provides,
                        '--info', 'depends:' + depends, '--script', 'post-install:' + str(script)],
                       check=True, capture_output=True, env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})
        metadata = json.loads(subprocess.check_output(
            [str(APK), 'adbdump', '--format', 'json', str(package)]))
        self.records[name] = {'root': str(root), 'repository': 'base',
                              'info': metadata['info'], 'metadata': metadata,
                              'elf': {**ELF.inspect(root), 'package': name, 'version': '1-r3'}}

    def repack(self, *names):
        plan = self.work / 'plan.json'
        plan.write_text(json.dumps(self.plan))
        return subprocess.run([str(FAKEROOT), 'python3', str(TREE / 'scripts/migrate-elf-abi.py'),
                               '--plan', str(plan), '--worker', *names], capture_output=True, text=True)

    def test_native_and_data_releases_preserve_payloads_and_update_contracts(self):
        result = self.repack('libprobe1', 'probe-data')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for name in self.records:
            package = self.work / 'output/base' / (name + '-1-r3.apk')
            subprocess.run([str(APK), 'verify', '--keys-dir', str(TREE), str(package)],
                           check=True, capture_output=True)
            metadata = json.loads(subprocess.check_output(
                [str(APK), 'adbdump', '--format', 'json', str(package)]))
            self.assertEqual(metadata['scripts'], self.records[name]['metadata']['scripts'])
            root = self.work / 'verified' / name
            root.mkdir(parents=True)
            subprocess.run([str(APK), 'extract', '--keys-dir', str(TREE), '--no-chown',
                            '--destination', str(root), str(package)], check=True, capture_output=True)
            stamp = root / 'usr/lib/apk/packages' / (name + '.elf.json')
            if name == 'libprobe1':
                self.assertEqual(json.loads(stamp.read_text())['version'], '1-r3')
                self.assertIn('libprobe=1-r3', metadata['info']['provides'])
                self.assertNotIn('libprobe=1-r2', metadata['info']['provides'])
                original = Path(self.records[name]['root']) / 'usr/lib/libprobe.so.1'
                self.assertEqual((root / 'usr/lib/libprobe.so.1').read_bytes(), original.read_bytes())
            else:
                self.assertFalse(stamp.exists())
                self.assertIn('libprobe1=1-r3', metadata['info']['depends'])
                self.assertEqual((root / 'usr/share/probe/data').stat().st_mode & 0o777, 0o640)

    def test_stale_existing_inventory_is_rejected(self):
        stamp = Path(self.records['libprobe1']['root']) / 'usr/lib/apk/packages/libprobe1.elf.json'
        data = json.loads(stamp.read_text())
        data['version'] = '1-r1'
        stamp.write_text(json.dumps(data))
        result = self.repack('libprobe1')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('existing ELF inventory is stale', result.stderr)


if __name__ == '__main__':
    unittest.main(verbosity=2)
