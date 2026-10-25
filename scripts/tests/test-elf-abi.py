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

    def test_inventory_mode_is_stable_across_umasks_and_rewrites(self):
        inventory = self.work / 'inventory.json'
        for mask in (0o002, 0o022, 0o077):
            previous = os.umask(mask)
            try:
                inventory.unlink(missing_ok=True)
                E.write_changed(inventory, '{}\n', mode=0o644)
                self.assertEqual(inventory.stat().st_mode & 0o777, 0o644)
                inventory.chmod(0o664)
                before = inventory.stat().st_mtime_ns
                E.write_changed(inventory, '{}\n', mode=0o644)
                self.assertEqual(inventory.stat().st_mode & 0o777, 0o644)
                self.assertEqual(inventory.stat().st_mtime_ns, before)
                E.write_changed(inventory, '{"changed":true}\n', mode=0o644)
                self.assertEqual(inventory.stat().st_mode & 0o777, 0o644)
            finally:
                os.umask(previous)

    def test_toolchain_bootstrap_with_empty_staging_root(self):
        toolchain = self.work / 'toolchain'
        library = self.library(toolchain, directory='lib')
        payload = self.work / 'payload'
        payload.mkdir()
        source = self.work / 'consumer.c'
        source.write_text('extern int probe(void); int consumer(void) { return probe(); }')
        subprocess.run(['cc', '-shared', '-nostdlib', '-fPIC', str(source),
                        str(library), '-o', str(payload / 'consumer.so')], check=True)
        command = ['python3', str(TREE / 'scripts/elf-abi.py'),
                   '--root', str(payload), '--package', 'libgcc1', '--version', '1-r1',
                   '--staging-root', str(self.work / 'empty-staging'),
                   '--depends-output', str(self.work / 'depends'),
                   '--provides-output', str(self.work / 'provides')]
        rejected = subprocess.run(command, capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('missing library', rejected.stderr)
        accepted = subprocess.run(command + ['--bootstrap-root', str(toolchain)],
                                  capture_output=True, text=True, umask=0o002)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertEqual((payload / 'usr/lib/apk/packages/libgcc1.elf.json').stat().st_mode & 0o777,
                         0o644)
        self.assertEqual((self.work / 'depends').read_text().strip(), 'so:libprobe.so.1')
        library.unlink()
        rejected = subprocess.run(command + ['--bootstrap-root', str(toolchain)],
                                  capture_output=True, text=True)
        self.assertNotEqual(rejected.returncode, 0)
        self.assertIn('missing library', rejected.stderr)

    def test_toolchain_bootstrap_absolute_link_stays_inside_sysroot(self):
        toolchain = self.work / 'toolchain'
        library = self.library(toolchain, directory='lib')
        library.rename(library.with_name('actual.so'))
        library.symlink_to('/lib/actual.so')
        consumer = {'files': {'/usr/lib/consumer.so': {
            **E.elf(library.with_name('actual.so')), 'needed': ['libprobe.so.1']}},
            'links': {}}
        bootstrap = E.staged_inventory(toolchain, consumer, merged_usr=False)
        deps, _ = E.contracts(consumer, 'libgcc1', {'@bootstrap': bootstrap})
        self.assertEqual(deps, ['so:libprobe.so.1'])
        bootstrap['files']['/usr/lib/actual.so']['machine'] = -1
        with self.assertRaisesRegex(ValueError, 'architecture mismatch'):
            E.contracts(consumer, 'libgcc1', {'@bootstrap': bootstrap})

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

    def test_sibling_packages_stage_libraries_before_both_elf_checks(self):
        source = (TREE / 'include/package-pack.mk').read_text()
        rules = source[source.index('define AddDependency'):source.index('# Format dependencies')]
        for dependency in ('library', 'virtual-library'):
            for order in (('app', 'library'), ('library', 'app')):
                for jobs in (1, 4):
                    with self.subTest(dependency=dependency, order=order, jobs=jobs):
                        work = self.work / (dependency + '-'.join(order) + str(jobs))
                        work.mkdir()
                        (work / 'Makefile').write_text(
                            '.DEFAULT_GOAL:=all\nCONFIG_USE_APK:=y\n'
                            'PKG_BUILD_DIR:=build\nPKG_INFO_DIR:=info\nSTAGING_DIR_ROOT:=root\n'
                            'PACK_app:=app.apk\nPACK_library:=library.apk\n'
                            + rules + '\n'
                            'define Register\n'
                            'IPKGS += $(1)\n'
                            'SIBLING_PROVIDES_library:=virtual-library\n'
                            f'IDEPEND += $(if $(filter app,$(1)),app:{dependency})\n'
                            '$(FixupDependencies)\n$(FixupReverseDependencies)\n'
                            'endef\n'
                            + ''.join('$(eval $(call Register,' + name + '))\n' for name in order)
                            + 'all: app.apk info/app.provides build/.pkgdir/app.installed\n'
                            'app.apk info/app.provides build/.pkgdir/app.installed:\n'
                            '\t@test -f root/stamp/.library_installed\n'
                            '\t@mkdir -p $(@D); touch $@\n'
                            'library.apk build/.pkgdir/library.installed:\n'
                            '\t@mkdir -p $(@D); touch $@\n'
                            'root/stamp/.library_installed: build/.pkgdir/library.installed\n'
                            '\t@mkdir -p $(@D); touch $@\n')
                        result = subprocess.run(['make', '-j' + str(jobs)], cwd=work,
                                                capture_output=True, text=True)
                        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
                        self.assertNotIn('Circular', result.stderr)

    def test_release_ledger_change_restages_provider_before_consumer(self):
        source = (TREE / 'include/package-pack.mk').read_text().splitlines()
        staged_rule = next(line.strip() for line in source
                           if line.strip().startswith('$(PKG_BUILD_DIR)/.pkgdir/$(1).installed:'))
        package_rule = next(line.strip() for line in source
                            if line.strip().startswith('$(PKG_INFO_DIR)/$(1).provides $$(PACK_$(1)):'))
        for relative in ('built', '.config', 'include/package-pack.mk', 'scripts/elf-abi.py',
                         'scripts/ucode-abi.py', 'configs/elf-abi-policy.json'):
            target = self.work / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            target.touch()
        ledger = self.work / 'configs/apk-elf-rebuilds.mk'
        ledger.write_text('1\n')
        self.work.joinpath('Makefile').write_text(
            'TOPDIR:=.\nINCLUDE_DIR:=include\nSCRIPT_DIR:=scripts\n'
            'CONFIG_USE_APK:=y\nSTAMP_BUILT:=built\nPKG_BUILD_DIR:=build\n'
            'PKG_INFO_DIR:=info\nPACK_library:=library.apk\n'
            'all: app\n'
            + staged_rule.replace('$(1)', 'library').replace('$$', '$') + '\n'
            '\t@mkdir -p $(@D); cp configs/apk-elf-rebuilds.mk $@\n'
            + package_rule.replace('$(1)', 'library').replace('$$', '$') + '\n'
            '\t@mkdir -p $(@D); touch $@\n'
            'root/version: build/.pkgdir/library.installed\n'
            '\t@mkdir -p $(@D); cp $< $@\n'
            'app: root/version library.apk\n\t@cp root/version app\n')
        for version in ('1', '2'):
            ledger.write_text(version + '\n')
            result = subprocess.run(['make', '-j3'], cwd=self.work, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual((self.work / 'app').read_text().strip(), version)

    def test_libc_version_stamp_uses_effective_package_version(self):
        source = (TREE / 'package/libs/toolchain/Makefile').read_text()
        recipes = source.split('define Package/libc/install\n')[1:]
        self.assertEqual(len(recipes), 2)  # Internal and external toolchains.
        mapping = next(line.strip() for line in (TREE / 'include/package.mk').read_text().splitlines()
                       if '$(eval VERSION:=$(or $(ELF_REBUILD_' in line)
        mapping = mapping.replace('$(1)', 'libc')
        for recipe in recipes:
            command = next(line.strip().rstrip('; \\') for line in recipe.split('endef', 1)[0].splitlines()
                           if 'libc.version' in line)
            (self.work / 'Makefile').write_text(
                'CONFIG_USE_APK:=y\nLIBC_VERSION:=2.43\nPKG_RELEASE:=5\n'
                'VERSION:=$(LIBC_VERSION)-r$(PKG_RELEASE)\n'
                'ELF_REBUILD_libc_2.43-r5:=2.43-r6\n'
                'STAGING_DIR:=' + str(self.work) + '\n' + mapping + '\n'
                'define Install\nall:\n\t' + command + '\nendef\n'
                '$(eval $(Install))\nVERSION:=unrelated-package-version\n')
            subprocess.run(['make', '-s'], cwd=self.work, check=True, capture_output=True)
            self.assertEqual((self.work / 'libc.version').read_text().strip(), '2.43-r6')

    def test_recipe_cannot_reuse_a_migration_output_version(self):
        source = (TREE / 'include/package.mk').read_text()
        helpers = source[source.index('elf_rebuild_upstream ='):
                         source.index('find_library_dependency_names =')]
        guard = next(line.strip() for line in source.splitlines()
                     if '$(call CheckElfRebuildVersion,$(1),$(VERSION))' in line)
        mapping = next(line.strip() for line in source.splitlines()
                       if '$(eval VERSION:=$(or $(ELF_REBUILD_' in line)
        cases = [
            ('libcups-runtime', '2.4.20-r1', '2.4.20-r2'),
            ('libcups-runtime', '2.4.20-r2', None),
            ('libcups-runtime', '2.4.20-r3', '2.4.20-r3'),
            ('libcups-runtime', '2.4.21-r2', '2.4.21-r2'),
            ('mtd', '29', '29-r2'),
            ('mtd', '29-r1', '29-r2'),
            ('mtd', '29-r2', None),
            ('mtd', '29-r3', '29-r3'),
            ('samba4-libs', '4.24.5-r2', '4.24.5-r4'),
            ('samba4-libs', '4.24.5-r3', '4.24.5-r4'),
            ('samba4-libs', '4.24.5-r4', None),
            ('boost-program_options', '1.92.0-r3', '1.92.0-r4'),
            ('boost-program_options', '1.92.0-r4', None),
            ('avahi-utils', '0.9_rc5-r2', '0.9_rc5-r3'),
            ('avahi-utils', '0.9_rc5-r3', None),
            ('probe_widget', '1.0-rc1-r2', None),
            ('probe', '1.0-rc1-r2', '1.0-rc1-r2'),
            ('chain', '1.0-r2', '1.0-r3'),
            ('chain', '1.0-r3', None),
        ]
        for name, version, expected in cases:
            with self.subTest(name=name, version=version):
                (self.work / 'Makefile').write_text(
                    'CONFIG_USE_APK:=y\n'
                    'include ' + str(TREE / 'configs/apk-elf-rebuilds.mk') + '\n'
                    'ELF_REBUILD_probe_widget_1.0-rc1-r1:=1.0-rc1-r2\n'
                    'ELF_REBUILD_chain_1.0-r1:=1.0-r2\n'
                    'ELF_REBUILD_chain_1.0-r2:=1.0-r3\n'
                    + helpers + '\nVERSION:=' + version + '\n'
                    + guard.replace('$(1)', name) + '\n'
                    + mapping.replace('$(1)', name) + '\n'
                    'all:\n\t@echo "$(VERSION)"\n')
                result = subprocess.run(['make', '-s'], cwd=self.work,
                                        capture_output=True, text=True)
                if expected is None:
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(name + ': recipe version ' + version + ' is reserved', result.stderr)
                    self.assertIn('PKG_RELEASE', result.stderr)
                else:
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(), expected)

    def test_glibc_companions_resolve_runtime_derived_versions_without_collision(self):
        source = (TREE / 'include/package.mk').read_text()
        helpers = source[source.index('elf_rebuild_upstream ='):
                         source.index('find_library_dependency_names =')]
        guard = next(line.strip() for line in source.splitlines()
                     if '$(call CheckElfRebuildVersion,$(1),$(VERSION))' in line)
        mapping = next(line.strip() for line in source.splitlines()
                       if '$(eval VERSION:=$(or $(ELF_REBUILD_' in line)
        for name in ('glibc-getent', 'glibc-distro-compat'):
            recipe = (TREE / 'package/custom' / name / 'Makefile').read_text()
            # Exercise the actual recipe expressions with a real libc.version,
            # not DUMP's <LIBC_VERSION>/<LIBC_RELEASE> metadata placeholders.
            version_rules = recipe.split('include $(TOPDIR)/rules.mk', 1)[1].split(
                'include $(INCLUDE_DIR)/package.mk', 1)[0]
            exact_dependency = next(line.strip() for line in recipe.splitlines()
                                    if line.strip().startswith('EXTRA_DEPENDS:='))
            for release in (5, 6, 7):
                with self.subTest(name=name, release=release):
                    runtime = '2.43-r' + str(release)
                    (self.work / 'libc.version').write_text(runtime + '\n')
                    (self.work / 'Makefile').write_text(
                        'CONFIG_USE_APK:=y\nLIBC_VERSION:=2.43\n'
                        'STAGING_DIR:=' + str(self.work) + '\n'
                        'include ' + str(TREE / 'configs/apk-elf-rebuilds.mk') + '\n'
                        + version_rules + '\n' + helpers
                        + '\nVERSION:=$(PKG_VERSION)-r$(PKG_RELEASE)\n'
                        + guard.replace('$(1)', name) + '\n'
                        + mapping.replace('$(1)', name) + '\n' + exact_dependency
                        + '\nall:\n\t@echo "$(VERSION)|$(EXTRA_DEPENDS)"\n')
                    result = subprocess.run(['make', '-s'], cwd=self.work,
                                            capture_output=True, text=True)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    self.assertEqual(result.stdout.strip(),
                                     '2.43_p3-r' + str(release) + '|libc (=' + runtime + ')')

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
