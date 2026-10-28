#!/usr/bin/env python3
"""Check source-version advancement across feed updates and migration releases."""
from pathlib import Path
import os
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
APK = TREE / 'staging_dir/host/bin/apk'


class SourceVersionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='apk-source-versions-')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)

    def make(self, text):
        (self.work / 'Makefile').write_text(text)
        return subprocess.check_output(['make', '-s'], cwd=self.work, text=True).strip()

    def test_recipe_releases_clear_allocated_identities(self):
        source = (TREE / 'include/package.mk').read_text()
        helpers = source[source.index('elf_rebuild_upstream ='):
                         source.index('find_library_dependency_names =')]
        for name, recipe, previous in (
                ('nginx-ssl', 'feeds/packages/net/nginx', '1.30.5-r3'),
                ('nginx-ssl-util', 'feeds/packages/net/nginx-util', '1.7-r4'),
                ('ffmpeg', 'feeds/packages/multimedia/ffmpeg', '9.0.1-r7'),
                ('libffmpeg', 'feeds/packages/multimedia/ffmpeg', '9.0.1-r6'),
                ('gst1-mod-gio', 'feeds/packages/multimedia/gst1-plugins-base', '1.28.7-r3'),
                ('glib2-build-tools', 'package/custom/glib2-build-tools', '1-r3'),
                ('intel-gpu-tools', 'package/custom/intel-gpu-tools', '2.6-r3'),
                ('libvirt', 'package/custom/libvirt', '12.8.0-r7'),
                ('libvirt-daemon', 'package/custom/libvirt', '12.8.0-r7'),
                ('native-libs-dev', 'package/custom/native-libs-dev', '1-r3'),
                ('wireplumber', 'package/custom/wireplumber', '0.5.18-r3'),
                ('libinput', 'feeds/packages/libs/libinput', '1.31.3-r4'),
                ('libwacom', 'feeds/packages/libs/libwacom', '2.19.1-r3'),
                ('qemu-x86_64-softmmu', 'feeds/packages/utils/qemu', '11.1.2-r4'),
                ('usbutils', 'feeds/packages/utils/usbutils', '020-r3')):
            with self.subTest(name=name):
                fields = '\n'.join(line for line in
                                   (TREE / recipe / 'Makefile').read_text().splitlines()
                                   if line.startswith(('PKG_VERSION:=', 'PKG_RELEASE:=')))
                # Exercise the real guard and mapping, for both the current
                # recipe and a future upstream release increment.
                for increment in (0, 1):
                    version = self.make(
                        'include ' + str(TREE / 'configs/apk-elf-rebuilds.mk') + '\n'
                        + fields + '\n' + helpers + '\n'
                        'VERSION:=$(PKG_VERSION)-r$(shell expr $(PKG_RELEASE) + '
                        + str(increment) + ')\n'
                        '$(call CheckElfRebuildVersion,' + name + ',$(VERSION))\n'
                        'VERSION:=$(or $(ELF_REBUILD_' + name + '_$(VERSION)),$(VERSION))\n'
                        'all:\n\t@echo "$(VERSION)"\n')
                    order = subprocess.check_output([str(APK), 'version', '-t', previous, version],
                                                    text=True).strip()
                    self.assertEqual(order, '<', (name, previous, version))
                    previous = version

    def commit(self, timestamp):
        subprocess.run(['git', 'add', 'code.lua', 'po'], cwd=self.work, check=True,
                       capture_output=True)
        env = dict(os.environ, GIT_AUTHOR_DATE=timestamp, GIT_COMMITTER_DATE=timestamp)
        subprocess.run(['git', '-c', 'user.name=Version Test',
                        '-c', 'user.email=version@example.invalid', 'commit', '-qm', 'update'],
                       cwd=self.work, env=env, check=True, capture_output=True)

    def passwall_versions(self):
        luci = (TREE / 'feeds/luci/luci.mk').read_text()
        recipe = (TREE / 'feeds/passwall_luci/luci-app-passwall/Makefile').read_text()
        # Evaluate the recipe's version declarations with the real LuCI
        # findrev, defaults, and package VERSION expression.
        declarations = '\n'.join(line for line in recipe.splitlines()
                                 if line.startswith(('PKG_VERSION', 'PKG_RELEASE', 'PKG_PO_VERSION')))
        findrev = luci[luci.index('define findrev\n'):luci.index('\nPKG_NAME?=')]
        defaults = luci[luci.index('ifeq ($(origin PKG_PO_VERSION),undefined)'):
                        luci.index('ifeq ($(origin PKG_GITBRANCH),undefined)')]
        expression = next(line.strip() for line in luci.splitlines()
                          if line.strip().startswith('VERSION:=$(if $(PKG_VERSION)'))
        return self.make(declarations + '\n' + findrev + '\n' + defaults + '\n'
                         + expression + '\nall:\n\t@echo "$(VERSION)|$(PKG_PO_VERSION)"\n').split('|')

    def test_passwall_code_and_translation_commits_advance_independently(self):
        subprocess.run(['git', 'init', '-q'], cwd=self.work, check=True)
        (self.work / 'po').mkdir()
        (self.work / 'code.lua').write_text('initial\n')
        (self.work / 'po/zh-cn.po').write_text('initial\n')
        self.commit('2026-10-24T00:00:00Z')
        first = self.passwall_versions()
        self.assertEqual(first, self.passwall_versions())
        for old, new in zip(('26.10.22-r2', '26.10.22'), first):
            self.assertEqual(subprocess.check_output([str(APK), 'version', '-t', old, new],
                                                    text=True).strip(), '<')
        (self.work / 'code.lua').write_text('updated\n')
        self.commit('2026-10-25T00:00:00Z')
        code = self.passwall_versions()
        self.assertNotEqual(code[0], first[0])
        self.assertEqual(code[1], first[1])
        (self.work / 'po/zh-cn.po').write_text('updated\n')
        self.commit('2026-10-26T00:00:00Z')
        translated = self.passwall_versions()
        self.assertEqual(translated[0], code[0])
        self.assertNotEqual(translated[1], code[1])
        self.assertEqual(translated, self.passwall_versions())


if __name__ == '__main__':
    unittest.main()
