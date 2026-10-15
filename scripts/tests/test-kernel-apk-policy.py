#!/usr/bin/env python3
"""Run the patched APK in disposable chroots; never use the host APK database."""
import hashlib
import os
from pathlib import Path
import subprocess
import re
import shutil
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
BUILDER = TREE / 'staging_dir/host/bin/apk'
APK = os.environ.get('KERNEL_POLICY_APK')


@unittest.skipUnless(APK, 'Set KERNEL_POLICY_APK to the isolated patched APK')
class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.addCleanup(self.cleanup)
        self.root = self.work / 'root'; self.root.mkdir()
        self.repo = self.work / 'repo'; self.repo.mkdir()
        self.key = self.work / 'private.pem'
        subprocess.run(['openssl', 'ecparam', '-name', 'prime256v1', '-genkey', '-noout', '-out', str(self.key)], check=True)
        subprocess.run(['openssl', 'ec', '-in', str(self.key), '-pubout', '-out', str(self.work / 'public.pem')],
                       check=True, capture_output=True)
        self.pkg('linux-image-generation-one', '1-r1', 'usr/share/kernel-one', b'old image')
        self.pkg('linux-image-openwrt', '1-r1', 'usr/share/tracker', b'one', 'linux-image-generation-one=1-r1')
        self.pkg('legacy-module', '1-r1', 'usr/lib/modules/legacy/driver.ko', b'legacy module')
        self.pkg('legacy-headers', '1-r1', 'usr/src/linux-headers-legacy/Makefile', b'legacy headers')
        self.index()
        self.apk('add', '--initdb', '--no-scripts', 'linux-image-openwrt', 'legacy-module', 'legacy-headers')
        subprocess.run(['sudo', '-n', 'chown', '-R', str(os.getuid()) + ':' + str(os.getgid()), str(self.root)], check=True)
        for name in ('run', 'usr/sbin', 'etc/openwrt-kernel'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        helper = self.work / 'helper.c'
        helper.write_text(r'''
#include <stdio.h>
#include <string.h>
#include <unistd.h>
int main(int argc, char **argv) {
 if (argc != 6) return 80;
 FILE *file = fopen("/run/policy-contract", "a");
 if (!file) { perror("policy contract"); return 81; }
 fprintf(file, "%s %s %s %s\n", argv[1], argv[3], argv[4], argv[5]);
 fclose(file);
 if (!strcmp(argv[1], "apk-pre") && (!access("/etc/openwrt-kernel/reject", F_OK) || !strcmp(argv[5], "1"))) return 82;
 if (!strcmp(argv[1], "apk-post") && strcmp(argv[3], "0")) return 83;
 return 0;
}
''')
        subprocess.run(['cc', '-static', str(helper), '-o', str(self.root / 'usr/sbin/kernelctl')], check=True)
        records = self.installed()
        package = records['linux-image-generation-one']
        (self.root / 'etc/openwrt-kernel/protected').write_text('linux-image-generation-one><' + package['C'] + '\n')
        (self.root / 'etc/openwrt-kernel/legacy-release').write_text('legacy\n')
        self.pkg('linux-image-generation-two', '1-r1', 'usr/share/kernel-two', b'new image')
        self.pkg('linux-image-openwrt', '1-r2', 'usr/share/tracker', b'two', 'linux-image-generation-two=1-r1')
        self.pkg('legacy-module', '1-r2', 'usr/share/legacy-tracker', b'no module ownership')
        self.pkg('legacy-headers', '1-r2', 'usr/share/headers-tracker', b'no header ownership')
        self.index()
        subprocess.run(['sudo', '-n', 'chown', '-R', 'root:root', str(self.root / 'lib/apk/db')], check=True)

    def cleanup(self):
        subprocess.run(['sudo', '-n', 'chown', '-R', str(os.getuid()) + ':' + str(os.getgid()), str(self.work)], check=True)
        self.temp.cleanup()

    def pkg(self, name, version, path, data, dependencies='', script=None):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            root = Path(temp)
            target = root / path; target.parent.mkdir(parents=True); target.write_bytes(data)
            args = [str(BUILDER), 'mkpkg', '--info', 'name:' + name, '--info', 'version:' + version,
                    '--info', 'arch:x86_64', '--info', 'depends:' + dependencies,
                    '--sign', str(self.key), '--files', str(root), '--output', str(self.repo / (name + '-' + version + '.apk'))]
            if script:
                args += ['--script', 'post-upgrade:' + str(script)]
            subprocess.run(args, check=True, capture_output=True)

    def index(self):
        subprocess.run([str(BUILDER), 'mkndx', '--keys-dir', str(self.work), '--sign-key', str(self.key), '--output',
                        str(self.repo / 'packages.adb'), *map(str, self.repo.glob('*.apk'))],
                       check=True, capture_output=True)

    def apk(self, *args, success=True):
        command = ['sudo', '-n', APK, '--root', str(self.root), '--keys-dir', str(self.work),
                   '--no-logfile', '--repositories-file', '/dev/null',
                   '--repository', str(self.repo / 'packages.adb'), '--no-cache', *args]
        result = subprocess.run(command, capture_output=True, text=True)
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def installed(self):
        result = {}
        for record in (self.root / 'lib/apk/db/installed').read_text().split('\n\n'):
            data = dict(line.split(':', 1) for line in record.splitlines()
                        if len(line) > 2 and line[1] == ':' and line[0] in 'PVC')
            if 'P' in data:
                result[data['P']] = data
        return result

    def test_upgrade_retains_previous_image_and_legacy_module_bytes(self):
        self.apk('upgrade')
        installed = self.installed()
        self.assertIn('linux-image-generation-one', installed)
        self.assertIn('linux-image-generation-two', installed)
        self.assertEqual((self.root / 'usr/lib/modules/legacy/driver.ko').read_bytes(), b'legacy module')
        self.assertEqual((self.root / 'usr/src/linux-headers-legacy/Makefile').read_bytes(), b'legacy headers')
        self.assertIn('apk-post 0 live 0', (self.root / 'run/policy-contract').read_text())

    def test_preflight_rejection_precedes_any_package_writes(self):
        (self.root / 'etc/openwrt-kernel/reject').touch()
        before = hashlib.sha256((self.root / 'lib/apk/db/installed').read_bytes()).hexdigest()
        self.apk('upgrade', success=False)
        self.assertFalse((self.root / 'usr/share/kernel-two').exists())
        self.assertEqual(before, hashlib.sha256((self.root / 'lib/apk/db/installed').read_bytes()).hexdigest())

    def test_no_scripts_cannot_skip_kernel_policy(self):
        self.apk('upgrade', '--no-scripts', success=False)
        self.assertFalse((self.root / 'usr/share/kernel-two').exists())

    def test_simulation_keeps_package_database_and_files(self):
        before = (self.root / 'lib/apk/db/installed').read_bytes()
        self.apk('upgrade', '--simulate')
        self.assertEqual(before, (self.root / 'lib/apk/db/installed').read_bytes())
        self.assertFalse((self.root / 'usr/share/kernel-two').exists())

    def preupgrade_probe(self):
        self.pkg('preupgrade-probe', '1-r1', 'usr/share/preupgrade-probe', b'old tool')
        self.index()
        self.apk('add', 'preupgrade-probe')
        self.pkg('preupgrade-probe', '1-r2', 'usr/share/preupgrade-probe', b'new tool')
        self.index()

    def test_preupgrade_defers_enrolled_image_until_complete_module_transaction(self):
        # Migration enrolls a rolling image in world before it is installed.
        # With the same config ABI, a minimal self-upgrade can add its image
        # while retaining old logical modules, unlike the full upgrade.
        self.apk('del', 'linux-image-openwrt')
        self.pkg('kmod-probe', '1-r1', 'usr/share/kmod-probe', b'old module tracker')
        self.index()
        self.apk('add', 'kmod-probe')
        self.preupgrade_probe()
        self.pkg('kmod-probe-generation-two', '1-r1', 'usr/share/module-two', b'new module',
                 'linux-image-generation-two=1-r1')
        self.pkg('kmod-probe', '1-r2', 'usr/share/kmod-probe', b'new module tracker',
                 'kmod-probe-generation-two=1-r1')
        self.index()
        subprocess.run(['sudo', '-n', 'tee', '-a', str(self.root / 'etc/apk/world')],
                       input='linux-image-openwrt\n', text=True, capture_output=True, check=True)
        before = (self.root / 'lib/apk/db/installed').read_bytes()
        contract = self.root / 'run/policy-contract'
        contract.unlink(missing_ok=True)
        result = self.apk('upgrade', '--preupgrade-only', '--simulate',
                          '--preupgrade-depends', 'preupgrade-probe')
        self.assertIn('Deferring preupgrade', result.stdout + result.stderr)
        self.assertFalse(contract.exists())
        self.assertEqual(before, (self.root / 'lib/apk/db/installed').read_bytes())
        self.assertFalse((self.root / 'usr/share/kernel-two').exists())
        # Omit --root inside the chroot so ordinary upgrade really exercises
        # its automatic preupgrade phase, rather than the offline-root path.
        result = self.chroot_apk('upgrade', '--preupgrade-depends', 'preupgrade-probe')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Deferring preupgrade', result.stdout + result.stderr)
        self.assertIn('kmod-probe-generation-two', self.installed())
        self.assertIn('linux-image-generation-one', self.installed())
        self.assertIn('apk-post 0 live 0', contract.read_text())

    def test_support_only_preupgrade_keeps_normal_policy_checks(self):
        self.preupgrade_probe()
        contract = self.root / 'run/policy-contract'
        contract.unlink(missing_ok=True)
        result = self.apk('upgrade', '--preupgrade-only', '--preupgrade-depends', 'preupgrade-probe')
        self.assertNotIn('Deferring preupgrade', result.stdout + result.stderr)
        self.assertEqual(self.installed()['preupgrade-probe']['V'], '1-r2')
        self.assertNotIn('linux-image-generation-two', self.installed())
        self.assertIn('apk-pre 0 live 0', contract.read_text())

    def test_protected_image_survives_explicit_delete(self):
        self.apk('del', 'linux-image-generation-one')
        self.assertIn('linux-image-generation-one', self.installed())

    def test_package_script_failure_reaches_activation_policy(self):
        source = self.work / 'fail.c'; source.write_text('int main(void) { return 1; }\n')
        binary = self.work / 'fail'
        subprocess.run(['cc', '-static', str(source), '-o', str(binary)], check=True)
        self.pkg('legacy-module', '1-r3', 'usr/share/legacy-tracker', b'failed script', script=binary)
        self.index()
        self.apk('upgrade', success=False)
        trace = (self.root / 'run/policy-contract').read_text()
        self.assertRegex(trace, r'apk-post [1-9][0-9]* live 0')
        self.assertEqual((self.root / 'usr/share/kernel-one').read_bytes(), b'old image')

    def test_root_slash_cannot_bypass_live_adoption_guard(self):
        (self.root / 'etc/openwrt-kernel/protected').unlink()
        before = (self.root / 'lib/apk/db/installed').read_bytes()
        result = self.chroot_apk('--root', '/', 'add', '--simulate', 'linux-image-generation-two')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('Run kernelctl migrate', result.stdout + result.stderr)
        self.assertEqual(before, (self.root / 'lib/apk/db/installed').read_bytes())

    def chroot_apk(self, *args):
        binary = self.root / 'usr/bin/apk'; binary.parent.mkdir(parents=True)
        shutil.copy2(APK, binary)
        libraries = subprocess.check_output(['ldd', APK], text=True)
        for name in re.findall(r'(?:=>\s*)?(/[^\s()]+)', libraries):
            target = self.root / name.lstrip('/')
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(Path(name).resolve(), target)
            if Path(name).name.startswith('libapk.so'):
                library = self.root / 'usr/lib' / Path(name).name
                library.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(name).resolve(), library)
        shutil.copytree(self.repo, self.root / 'repo')
        (self.root / 'keys').mkdir()
        shutil.copy2(self.work / 'public.pem', self.root / 'keys/public.pem')
        return subprocess.run(['sudo', '-n', 'chroot', str(self.root), '/usr/bin/apk',
            '--repositories-file', '/dev/null', '--keys-dir', '/keys',
            '--repository', '/repo/packages.adb', '--no-logfile', *args],
            capture_output=True, text=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)
