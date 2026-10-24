#!/usr/bin/env python3
"""Exercise real ELF payloads and the APK solver's SONAME contracts."""
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
spec = importlib.util.spec_from_file_location('elf_abi_test', TREE / 'scripts/elf-abi.py')
E = importlib.util.module_from_spec(spec)
spec.loader.exec_module(E)


class ElfAbiTests(unittest.TestCase):
    def setUp(self):
        if not shutil.which('cc') or not APK.exists():
            self.skipTest('Requires cc and apk/host')
        self.temp = tempfile.TemporaryDirectory(prefix='elf-abi-test-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def library(self, root, soname='libprobe.so.1', directory='usr/lib'):
        source = self.work / 'lib.c'
        source.write_text('int probe(void) { return 0; }\n')
        target = root / directory / soname
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(['cc', '-shared', '-fPIC', str(source), '-Wl,-soname,' + soname,
                        '-o', str(target)], check=True, capture_output=True)
        return target

    def app(self, root, library, rpath=None):
        source = self.work / 'app.c'
        source.write_text('extern int probe(void); int main(void) { return probe(); }\n')
        target = root / 'usr/bin/app'
        target.parent.mkdir(parents=True, exist_ok=True)
        args = ['cc', str(source), str(library), '-o', str(target)]
        if rpath:
            args += ['-Wl,-rpath,' + rpath]
        subprocess.run(args, check=True, capture_output=True)
        return target

    def test_public_library_and_external_dependency(self):
        lib = self.library(self.work / 'lib')
        self.app(self.work / 'app', lib)
        inventory = E.inspect(self.work / 'app')
        deps, _ = E.contracts(inventory, 'app')
        self.assertIn('so:libprobe.so.1', deps)
        self.assertEqual(E.public_provides(E.inspect(self.work / 'lib')), ['so:libprobe.so.1=0'])

    def test_origin_private_library_is_not_a_global_provider(self):
        root = self.work / 'private'
        lib = self.library(root, directory='usr/lib/app')
        self.app(root, lib, '$ORIGIN/../lib/app')
        deps, provides = E.contracts(E.inspect(root), 'app')
        self.assertNotIn('so:libprobe.so.1', deps)
        self.assertEqual(provides, [])

    def test_unreachable_private_library_cannot_satisfy_dependency(self):
        root = self.work / 'private'
        lib = self.library(root, directory='usr/lib/another-app')
        self.app(root, lib)
        deps, _ = E.contracts(E.inspect(root), 'app')
        self.assertIn('so:libprobe.so.1', deps)

    def test_cross_package_private_library_pins_owner_version(self):
        root = self.work / 'private'
        lib = self.library(root, directory='usr/lib/app')
        inventory = E.inspect(root)
        inventory['version'] = '1-r7'
        self.app(self.work / 'app', lib, '/usr/lib/app')
        # Add real libc/loader context for the host-linked fixture.
        app = E.inspect(self.work / 'app')
        system = {'files': {}, 'links': {}}
        for needed in app['files']['/usr/bin/app']['needed']:
            if needed != 'libprobe.so.1':
                system['files']['/usr/lib/' + needed] = dict(app['files']['/usr/bin/app'], needed=[], interpreter=None)
        system['files'][E.canonical(app['files']['/usr/bin/app']['interpreter'])] = dict(app['files']['/usr/bin/app'], needed=[], interpreter=None)
        context = {'library': inventory, '@system': system}
        deps, _ = E.contracts(app, 'app', context)
        self.assertIn('library=1-r7', deps)

    def test_absolute_symlink_is_resolved_inside_payload(self):
        root = self.work / 'link'
        lib = self.library(root, 'libprobe.so.1.0')
        (lib.parent / 'libprobe.so.1.0').rename(lib.parent / 'actual')
        lib.symlink_to('/usr/lib/actual')
        inventory = E.inspect(root)
        self.assertIn('so:libprobe.so.1.0=0', E.public_provides(inventory))

    def test_strings_and_relocatable_objects_do_not_create_dependencies(self):
        root = self.work / 'data'
        root.mkdir()
        (root / 'text').write_text('libprobe.so.1')
        source = self.work / 'data.c'
        source.write_text('const char *s="libprobe.so.1";')
        subprocess.run(['cc', '-c', str(source), '-o', str(root / 'object.o')], check=True)
        self.assertEqual(E.inspect(root)['files'], {})

    def test_corrupt_elf_is_rejected(self):
        bad = self.work / 'bad'
        bad.write_bytes(b'\x7fELFbad')
        with self.assertRaisesRegex(ValueError, 'invalid ELF'):
            E.elf(bad)

    def test_stamp_is_stable_until_sonames_change(self):
        stamp = self.work / 'stamp'
        E.write_changed(stamp, 'one\n')
        before = stamp.stat().st_mtime_ns
        E.write_changed(stamp, 'one\n')
        self.assertEqual(stamp.stat().st_mtime_ns, before)
        E.write_changed(stamp, 'two\n')
        self.assertEqual(stamp.read_text(), 'two\n')

    def test_actual_make_dependency_rule_rebuilds_after_soname_change(self):
        pkginfo = self.work / 'staged/pkginfo'
        pkginfo.mkdir(parents=True)
        stamp = pkginfo / 'library.sonames'
        E.write_changed(stamp, 'so:libprobe.so.1=0\n')
        source = (TREE / 'include/package.mk').read_text()
        rules = source[source.index('find_library_dependency_names ='):source.index('# External modules')]
        makefile = self.work / 'Makefile'
        makefile.write_text('STAGING_DIR:=' + str(self.work / 'staged') + '\n'
                            'BUILD_PACKAGES:=app\nPackage/app/depends:=library\n' + rules +
                            '\nall: built\nbuilt: $(call find_library_dependencies,app)\n'
                            '\t@echo rebuild >> events\n\t@touch built\n')
        run = lambda: subprocess.run(['make', '-s'], cwd=self.work, check=True, capture_output=True)
        run()
        E.write_changed(stamp, 'so:libprobe.so.1=0\n')
        run()
        self.assertEqual((self.work / 'events').read_text().splitlines(), ['rebuild'])
        E.write_changed(stamp, 'so:libprobe.so.2=0\n')
        run()
        self.assertEqual((self.work / 'events').read_text().splitlines(), ['rebuild', 'rebuild'])

    def test_make_dependency_migration_preserves_package_separators(self):
        source = (TREE / 'include/package-pack.mk').read_text()
        assignment = next(line.strip() for line in source.splitlines()
                          if 'ELF_DEP_$$(subst' in line)
        assignment = assignment.replace('$$', '$').replace('$(1)', 'probe')
        helpers = '\n'.join(line for line in source.splitlines()
                            if line.startswith(('_addsep=', '_cleansep=', 'mergelist=')))
        (self.work / 'Makefile').write_text(
            'empty:=\nspace:=$(empty) $(empty)\ncomma:=,\nparen_left:=(\nparen_right:=)\n'
            + helpers + '\nELF_DEP_pinned_1.0-r1:=pinned=1.0-r2\n'
            'Package/probe/DEPENDS:=libc, libpthread, pinned (= 1.0-r1)\n'
            + assignment + '\nall:\n'
            '\t@echo "$(subst $(comma),$(space),$(subst $(space),,$(Package/probe/DEPENDS)))"\n')
        result = subprocess.check_output(['make', '-s'], cwd=self.work, text=True)
        self.assertEqual(result.split(), ['libc', 'libpthread', 'pinned=1.0-r2'])

    def test_inherited_rpath_reaches_private_transitive_library(self):
        root = self.work / 'inherited'
        lib = self.library(root, directory='usr/lib/private')
        source = self.work / 'middle.c'
        source.write_text('extern int probe(void); int middle(void) { return probe(); }')
        middle = root / 'usr/lib/private/libmiddle.so.1'
        subprocess.run(['cc', '-shared', '-nostdlib', '-fPIC', str(source), str(lib),
                        '-Wl,-soname,libmiddle.so.1', '-o', str(middle)], check=True)
        source.write_text('extern int middle(void); int main(void) { return middle(); }')
        target = root / 'usr/bin/app'
        target.parent.mkdir(parents=True)
        subprocess.run(['cc', str(source), str(middle), '-Wl,--disable-new-dtags',
                        '-Wl,-rpath,/usr/lib/private', '-Wl,-rpath-link,' + str(lib.parent),
                        '-o', str(target)], check=True)
        deps, _ = E.contracts(E.inspect(root), 'app')
        self.assertNotIn('so:libprobe.so.1', deps)
        self.assertNotIn('so:libmiddle.so.1', deps)
        # A direct RUNPATH suppresses ancestor RPATH for this lookup.
        source.write_text('extern int probe(void); int middle(void) { return probe(); }')
        subprocess.run(['cc', '-shared', '-nostdlib', '-fPIC', str(source), str(lib),
                        '-Wl,-soname,libmiddle.so.1', '-Wl,-rpath,/usr/lib/unrelated',
                        '-o', str(middle)], check=True)
        deps, _ = E.contracts(E.inspect(root), 'app')
        self.assertIn('so:libprobe.so.1', deps)

    def test_32_bit_elf_is_parsed_without_running_a_target_loader(self):
        source = self.work / 'elf32.c'
        source.write_text('int probe(void) { return 0; }')
        target = self.work / 'elf32.so'
        result = subprocess.run(['cc', '-m32', '-shared', '-nostdlib', '-fPIC', str(source),
                                 '-Wl,-soname,libprobe32.so.1', '-o', str(target)], capture_output=True)
        if result.returncode:
            self.skipTest('Host linker lacks 32-bit ELF output')
        inventory = E.elf(target)
        self.assertEqual(inventory['class'], 1)
        self.assertEqual(inventory['soname'], 'libprobe32.so.1')

    def test_missing_metadata_and_unavailable_soname_are_rejected(self):
        root = self.work / 'provider'
        self.library(root)
        inventory = E.inspect(root)
        record = {'version': '1-r1', 'elf': inventory, 'depends': [], 'provides': []}
        system = {'files': {}, 'links': {}}
        for needed in inventory['files']['/usr/lib/libprobe.so.1']['needed']:
            system['files']['/usr/lib/' + needed] = dict(inventory['files']['/usr/lib/libprobe.so.1'], needed=[])
        records = {'library': record, 'system': {'elf': system}}
        with self.assertRaisesRegex(ValueError, 'missing ELF metadata'):
            E.validate(records)
        consumer = {'files': {'/usr/bin/missing': dict(inventory['files']['/usr/lib/libprobe.so.1'],
                    needed=['libabsent.so.9'], interpreter=None)}, 'links': {}}
        with self.assertRaisesRegex(ValueError, 'libabsent.so.9'):
            E.validate({'old-unmanaged-app': {'elf': consumer}}, require_metadata=False)

    def package(self, name, version, depends='', provides=''):
        root = self.work / (name + '-' + version)
        root.mkdir()
        (root / name).write_text(version)
        output = self.work / (root.name + '.apk')
        args = [str(APK), 'mkpkg', '--info', 'name:' + name, '--info', 'version:' + version,
                '--info', 'arch:x86_64', '--info', 'description:ELF ABI fixture',
                '--info', 'license:MIT', '--files', str(root), '--output', str(output),
                '--sign-key', str(TREE / 'private-key.pem')]
        for key, value in [('depends', depends), ('provides', provides)]:
            if value:
                args += ['--info', key + ':' + value]
        subprocess.run(args, check=True, capture_output=True)
        return str(output)

    def test_real_solver_blocks_partial_upgrade_and_library_removal(self):
        old = self.package('probe-lib', '1-r1', provides='so:libprobe.so.1=0')
        app = self.package('probe-app', '1-r1', depends='so:libprobe.so.1')
        new = self.package('probe-lib', '2-r1', provides='so:libprobe.so.2=0')
        fixed = self.package('probe-app', '1-r2', depends='so:libprobe.so.2')
        root = self.work / 'db'
        root.mkdir()
        common = [str(APK), '--root', str(root), '--keys-dir', str(TREE),
                  '--repositories-file', '/dev/null', '--no-network', '--no-scripts',
                  '--no-logfile', '--no-interactive', '--force-non-repository']
        run = lambda args: subprocess.run(common + args, capture_output=True, text=True)
        installed = run(['add', '--initdb', '--usermode', old, app])
        self.assertEqual(installed.returncode, 0, installed.stdout + installed.stderr)
        rejected = run(['add', '--simulate', new])
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('so:libprobe.so.1', rejected.stdout + rejected.stderr)
        accepted = run(['add', '--simulate', new, fixed])
        self.assertEqual(accepted.returncode, 0, accepted.stdout + accepted.stderr)
        # apk del may remove dependent applications; it must not leave a broken app.
        removed = run(['del', '--simulate', 'probe-lib'])
        self.assertTrue(removed.returncode or 'probe-app' in removed.stdout + removed.stderr)

    def test_publisher_checks_retained_consumers_and_exact_payload_metadata(self):
        spec = importlib.util.spec_from_file_location('elf_publisher_test', TREE / 'scripts/publish-lan-apk-feeds.py')
        publisher = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(publisher)
        payload = self.work / 'payload'
        repository = payload / 'base'
        repository.mkdir(parents=True)
        infos = []

        def build(name, version, soname, library=None, metadata=True):
            root = self.work / (name + '-' + version)
            directory = root / ('usr/lib' if library is None else 'usr/bin')
            directory.mkdir(parents=True)
            source = self.work / 'probe.c'
            source.write_text('int probe(void) { return 0; }' if library is None else
                              'extern int probe(void); int use(void) { return probe(); }')
            target = directory / (soname if library is None else name)
            args = ['cc', '-shared', '-nostdlib', '-fPIC', str(source), '-o', str(target)]
            args += ['-Wl,-soname,' + soname] if library is None else [str(library)]
            subprocess.run(args, check=True, capture_output=True)
            inventory = E.inspect(root)
            inventory.update(package=name, version=version)
            dependencies, provides = E.contracts(inventory, name)
            if metadata:
                output = root / 'usr/lib/apk/packages' / (name + '.elf.json')
                output.parent.mkdir(parents=True)
                output.write_text(json.dumps(inventory))
            package = repository / (name + '-' + version + '.apk')
            args = [str(APK), 'mkpkg', '--files', str(root), '--output', str(package),
                    '--sign-key', str(TREE / 'private-key.pem')]
            info = {'name': name, 'version': version, 'arch': 'x86_64', 'license': 'MIT',
                    'description': 'ELF publication fixture', 'depends': dependencies, 'provides': provides}
            for key, value in info.items():
                args += ['--info', key + ':' + (' '.join(value) if isinstance(value, list) else value)]
            subprocess.run(args, check=True, capture_output=True)
            infos.append(info)
            return target

        counter = 0

        def check():
            nonlocal counter
            counter += 1
            work = self.work / ('check-' + str(counter))
            return publisher.validate_elf_abi(APK, TREE, payload, {'base': {'packages': infos}}, work)

        old = build('library', '1-r1', 'libprobe.so.1')
        build('application', '1-r1', 'unused', old)
        self.assertEqual(check()['elf_files'], 2)
        new = build('library', '2-r1', 'libprobe.so.2')
        with self.assertRaisesRegex(ValueError, 'application.*libprobe.so.1'):
            check()
        build('application', '1-r2', 'unused', new)
        self.assertEqual(check()['elf_files'], 2)
        build('unmigrated', '1-r1', 'liblegacy.so.1', metadata=False)
        with self.assertRaisesRegex(ValueError, 'missing/stale ELF inventory'):
            check()


if __name__ == '__main__':
    unittest.main(verbosity=2)
