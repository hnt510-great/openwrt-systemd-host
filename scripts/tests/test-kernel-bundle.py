#!/usr/bin/env python3
"""Stage kernel/kmod/header payloads and build distribution-style kernel packages."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
APK = TREE / 'staging_dir/host/bin/apk'
FAKEROOT = TREE / 'staging_dir/host/bin/fakeroot'
RELEASE = '7.3.1-46-openwrt'
VERSION = '7.3.1-r46'


@unittest.skipUnless(APK.is_file() and FAKEROOT.is_file(), 'Requires the host apk and fakeroot tools')
class KernelBundleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.stage = self.work / 'stage' / RELEASE
        self.linux = self.work / 'linux'
        (self.linux / 'include/config').mkdir(parents=True)
        (self.linux / 'include/config/kernel.release').write_text(RELEASE + '\n')
        (self.linux / 'arch/x86/boot').mkdir(parents=True)
        (self.linux / 'arch/x86/boot/bzImage').write_bytes(b'kernel image')
        (self.linux / '.config').write_text('CONFIG_X86_64=y\n')
        (self.linux / 'System.map').write_text('ffffffff81000000 T _text\n')
        self.key = self.work / 'key.pem'
        subprocess.run(['openssl', 'ecparam', '-name', 'prime256v1', '-genkey', '-noout',
                        '-out', str(self.key)], check=True)
        self.config = self.work / '.config'
        self.config.write_text('CONFIG_PACKAGE_kmod-alpha=y\nCONFIG_PACKAGE_kmod-beta=m\n'
                               'CONFIG_PACKAGE_kmod-meta=y\nCONFIG_PACKAGE_kernel-dev-headers=y\n'
                               '# CONFIG_PACKAGE_kmod-unused is not set\n')

    def idir(self, name, files):
        root = self.work / 'idir' / name
        for path, data in files.items():
            target = root / path
            target.parent.mkdir(parents=True, exist_ok=True)
            if isinstance(data, tuple):
                target.symlink_to(data[0])
            else:
                target.write_bytes(data)
        lists = root / 'usr/lib/apk/packages'
        lists.mkdir(parents=True, exist_ok=True)
        (lists / (name + '.list')).write_text('stale\n')
        return root

    def stage_package(self, name, root, success=True):
        result = subprocess.run(['python3', str(TREE / 'scripts/kernel-package.py'), '--root', str(root),
                                 '--name', name, '--release', RELEASE, '--stage', str(self.stage),
                                 '--linux', str(self.linux)], capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def module(self, name, release=RELEASE):
        return b'\x7fELF' + b'\0' * 8 + b'vermagic=' + release.encode() + b' SMP preempt mod_unload \0' + name.encode()

    def stage_all(self):
        kernel = self.idir('kernel', {f'usr/lib/modules/{RELEASE}/modules.builtin': b'kernel/fs/ext4.ko\n',
                                      f'usr/lib/modules/{RELEASE}/modules.order': b'alpha.ko\n'})
        alpha = self.idir('kmod-alpha', {f'usr/lib/modules/{RELEASE}/alpha.ko': self.module('alpha'),
                                         'etc/modules.d/30-alpha': b'alpha\n',
                                         'etc/modprobe.d/alpha.conf': b'options alpha x=1\n'})
        beta = self.idir('kmod-beta', {f'usr/lib/modules/{RELEASE}/beta.ko': self.module('beta')})
        meta = self.idir('kmod-meta', {})
        headers = self.idir('kernel-dev-headers', {
            f'usr/src/linux-headers-{RELEASE}/Makefile': b'headers',
            f'usr/lib/modules/{RELEASE}/build': (f'../../../usr/src/linux-headers-{RELEASE}',),
            'usr/src/linux': (f'linux-headers-{RELEASE}',)})
        for name, root in (('kernel', kernel), ('kmod-alpha', alpha), ('kmod-beta', beta),
                           ('kmod-meta', meta), ('kernel-dev-headers', headers)):
            self.stage_package(name, root)
        return kernel, alpha, headers

    def bundle(self, success=True):
        result = subprocess.run(['python3', str(TREE / 'scripts/kernel-bundle.py'), '--stage', str(self.stage),
                                 '--config', str(self.config), '--output', str(self.work / 'out'),
                                 '--apk', str(APK), '--fakeroot', str(FAKEROOT), '--release', RELEASE,
                                 '--version', VERSION, '--sequence', '46', '--key', str(self.key)],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode == 0, success, result.stdout + result.stderr)
        return result

    def dump(self, name):
        path = self.work / 'out' / name
        data = subprocess.check_output([str(APK), 'adbdump', '--format', 'json', str(path)], text=True)
        return json.loads(data)

    def files(self, package):
        return {(d['name'] + '/' + f['name']) for d in package.get('paths', [])
                for f in d.get('files', [])}

    def test_kmods_keep_configuration_and_stage_modules(self):
        kernel, alpha, headers = self.stage_all()
        self.assertFalse((alpha / 'usr/lib/modules' / RELEASE).exists())
        self.assertTrue((alpha / 'etc/modules.d/30-alpha').is_file())
        self.assertTrue((alpha / 'etc/modprobe.d/alpha.conf').is_file())
        self.assertEqual((alpha / 'usr/lib/apk/packages/kmod-alpha.list').read_text(),
                         '/etc/modprobe.d/alpha.conf\n/etc/modules.d/30-alpha\n'
                         '/usr/lib/apk/packages/kmod-alpha.list\n')
        # The virtual kernel package keeps its (now empty) modules directory.
        self.assertTrue((kernel / 'usr/lib/modules').is_dir())
        self.assertFalse((kernel / 'usr/lib/modules' / RELEASE).exists())
        self.assertTrue((self.stage / 'kmods/kmod-alpha/usr/lib/modules' / RELEASE / 'alpha.ko').is_file())
        self.assertTrue((self.stage / 'kmods/kmod-meta').is_dir())
        self.assertEqual((self.stage / 'kernel/vmlinuz').read_bytes(), b'kernel image')
        self.assertTrue((headers / 'usr/src/linux').is_symlink())
        self.assertTrue((self.stage / 'headers/usr/src' / ('linux-headers-' + RELEASE) / 'Makefile').is_file())

    def test_restaging_replaces_a_kmod(self):
        self.stage_all()
        again = self.idir('kmod-alpha-again', {f'usr/lib/modules/{RELEASE}/alpha2.ko': self.module('alpha2')})
        self.stage_package('kmod-alpha', again)
        modules = self.stage / 'kmods/kmod-alpha/usr/lib/modules' / RELEASE
        self.assertEqual(sorted(p.name for p in modules.iterdir()), ['alpha2.ko'])

    def test_module_from_another_release_is_refused(self):
        root = self.idir('kmod-alpha', {f'usr/lib/modules/{RELEASE}/alpha.ko': self.module('alpha', '7.3.1-45-openwrt')})
        result = self.stage_package('kmod-alpha', root, success=False)
        self.assertIn('differs from kernel release', result.stderr)

    def test_bundle_builds_image_headers_and_meta(self):
        self.stage_all()
        self.bundle()
        image = self.dump(f'linux-image-{RELEASE}-{VERSION}.apk')
        self.assertEqual(image['info']['version'], VERSION)
        self.assertEqual(image['info']['origin'], 'kernel-packages')
        self.assertEqual(image['info'].get('depends'), ['openwrt-kernel-upgrade'])
        files = self.files(image)
        for path in (f'usr/lib/modules/{RELEASE}/alpha.ko', f'usr/lib/modules/{RELEASE}/beta.ko',
                     f'usr/lib/modules/{RELEASE}/modules.builtin',
                     f'usr/lib/openwrt-kernel/{RELEASE}/vmlinuz', f'usr/lib/openwrt-kernel/{RELEASE}/config',
                     f'usr/lib/openwrt-kernel/{RELEASE}/System.map',
                     f'usr/lib/openwrt-kernel/{RELEASE}/image.json'):
            self.assertIn(path, files)
        headers = self.dump(f'linux-headers-{RELEASE}-{VERSION}.apk')
        self.assertIn(f'usr/src/linux-headers-{RELEASE}/Makefile', self.files(headers))
        meta = self.dump(f'linux-image-openwrt-{VERSION}.apk')
        self.assertEqual(set(meta['info']['depends']), {f'linux-image-{RELEASE}={VERSION}',
                                                        'openwrt-kernel-upgrade', 'openwrt-kernel-policy>=3.0.5-r17'})
        self.assertEqual(self.files(meta), set())
        # The metapackage sorts above the previous rolling tracker 1-r45.
        order = subprocess.check_output([str(APK), 'version', '-t', '1-r45', VERSION], text=True).strip()
        self.assertEqual(order, '<')

    def test_bundle_is_reproducible_and_immutable(self):
        self.stage_all()
        self.bundle()
        path = self.work / 'out' / f'linux-image-{RELEASE}-{VERSION}.apk'
        before = path.read_bytes()
        self.bundle()
        self.assertEqual(before, path.read_bytes())
        (self.stage / 'kernel/vmlinuz').write_bytes(b'different kernel image')
        result = self.bundle(success=False)
        self.assertIn('Immutable kernel package changed', result.stderr)
        self.assertEqual(before, path.read_bytes())

    def test_unpacked_selected_kmod_is_refused(self):
        self.stage_all()
        self.config.write_text(self.config.read_text() + 'CONFIG_PACKAGE_kmod-gamma=y\n')
        result = self.bundle(success=False)
        self.assertIn('kmod-gamma', result.stderr)

    def test_conflicting_module_files_are_refused(self):
        self.stage_all()
        other = self.idir('kmod-beta', {f'usr/lib/modules/{RELEASE}/alpha.ko': self.module('different')})
        self.stage_package('kmod-beta', other)
        result = self.bundle(success=False)
        self.assertIn('Conflicting staged file', result.stderr)

    def test_deselected_kmod_is_not_bundled(self):
        self.stage_all()
        self.config.write_text(self.config.read_text().replace('CONFIG_PACKAGE_kmod-beta=m\n', ''))
        self.bundle()
        files = self.files(self.dump(f'linux-image-{RELEASE}-{VERSION}.apk'))
        self.assertNotIn(f'usr/lib/modules/{RELEASE}/beta.ko', files)


if __name__ == '__main__':
    unittest.main(verbosity=2)
