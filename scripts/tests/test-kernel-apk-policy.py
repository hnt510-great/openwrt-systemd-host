#!/usr/bin/env python3
"""Run the patched APK in disposable chroots; never use the host APK database."""
import hashlib
import json
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

    def abi_generation(self, sequence, abi):
        generation = abi.replace('~', '-owrt-') + '-g' + str(sequence)
        image = 'linux-image-' + generation
        module = 'kmod-abi-probe-' + generation
        headers = 'kernel-dev-headers-' + generation
        version = '1000.' + str(sequence) + '.6.18.55-r1'
        if not (self.repo / ('kernel-' + abi + '.apk')).exists():
            self.pkg('kernel', abi, 'usr/share/abi', abi.encode())
        self.pkg(image, abi, 'usr/share/images/' + generation, b'kernel image')
        self.pkg(module, version, 'usr/lib/modules/' + generation + '/probe.ko',
                 b'matching module', image + '=' + abi)
        self.pkg(headers, version, 'usr/src/linux-headers-' + generation + '/Makefile',
                 b'matching headers', image + '=' + abi)
        self.pkg('kmod-abi-probe', version, 'usr/share/probe-tracker', str(sequence).encode(),
                 'kernel=' + abi + ' ' + module + '=' + version)
        self.pkg('kernel-dev-headers', version, 'usr/share/abi-headers-tracker', str(sequence).encode(),
                 'kernel=' + abi + ' ' + headers + '=' + version)
        self.pkg('linux-image-openwrt', '1-r' + str(sequence), 'usr/share/tracker', str(sequence).encode(),
                 'kernel=' + abi + ' ' + image + '=' + abi)
        self.index()
        return image, module, headers

    def installed_abi_generation(self):
        abi = '6.18.55~' + 'a' * 32 + '-r1'
        payloads = self.abi_generation(10, abi)
        self.pkg('userspace-probe', '1-r1', 'usr/share/userspace-probe', b'old userspace')
        self.index()
        self.apk('add', '--upgrade', 'linux-image-openwrt', 'kmod-abi-probe', 'kernel-dev-headers', 'userspace-probe')
        self.pkg('userspace-probe', '1-r2', 'usr/share/userspace-probe', b'new userspace')
        return abi, payloads

    def test_same_abi_sequence_upgrade_keeps_kernel_modules_headers_and_updates_userspace(self):
        abi, old = self.installed_abi_generation()
        new = self.abi_generation(11, abi)
        before = self.installed()
        world = (self.root / 'etc/apk/world').read_bytes()
        database = (self.root / 'lib/apk/db/installed').read_bytes()
        result = self.apk('upgrade', '--simulate')
        self.assertIn('Keeping installed kernel generation: ABI unchanged.', result.stdout + result.stderr)
        self.assertEqual(database, (self.root / 'lib/apk/db/installed').read_bytes())
        result = self.apk('upgrade')
        self.assertIn('Keeping installed kernel generation: ABI unchanged.', result.stdout + result.stderr)
        after = self.installed()
        for name in ('kernel', 'linux-image-openwrt', 'kmod-abi-probe', 'kernel-dev-headers', *old):
            self.assertEqual(before[name], after[name])
        for name in new:
            self.assertNotIn(name, after)
        self.assertEqual(after['userspace-probe']['V'], '1-r2')
        self.assertEqual(world, (self.root / 'etc/apk/world').read_bytes())
        transaction = subprocess.check_output(
            ['sudo', '-n', 'cat', str(self.root / 'run/openwrt-kernel-apk.txn')], text=True)
        for line in transaction.splitlines():
            old_name, old_version, new_name, new_version, reinstall = line.split('\t')
            if old_name == 'kernel' or old_name.startswith(('linux-image-', 'kmod-', 'kernel-dev-headers')):
                self.assertEqual((old_name, old_version, '0'), (new_name, new_version, reinstall))
        # No permanent tracker pins may block the next real ABI transition,
        # including one whose hash sorts below the installed hash.
        next_abi = abi.replace('a' * 32, '0' * 32)
        next_payloads = self.abi_generation(12, next_abi)
        self.apk('upgrade')
        after = self.installed()
        self.assertEqual(after['kernel']['V'], next_abi)
        self.assertEqual(after['linux-image-openwrt']['V'], '1-r12')
        for name in next_payloads:
            self.assertIn(name, after)

    def test_explicit_same_abi_image_with_matching_generation_is_allowed(self):
        abi, old = self.installed_abi_generation()
        protected = self.root / 'etc/openwrt-kernel/protected'
        records = self.installed()
        protected.write_text(protected.read_text() + ''.join(
            name + '><' + records[name]['C'] + '\n' for name in old))
        new = self.abi_generation(11, abi)
        version = '1000.11.6.18.55-r1'
        self.apk('add', new[0] + '=' + abi, 'linux-image-openwrt=1-r11',
                 'kmod-abi-probe=' + version, 'kernel-dev-headers=' + version)
        after = self.installed()
        for name in (*old, *new):
            self.assertIn(name, after)
        self.assertEqual(after['linux-image-openwrt']['V'], '1-r11')
        self.assertEqual(after['kmod-abi-probe']['V'], version)
        self.assertEqual(after['kernel-dev-headers']['V'], version)

    def test_explicit_local_same_abi_image_preserves_protected_generation(self):
        abi, old = self.installed_abi_generation()
        protected = self.root / 'etc/openwrt-kernel/protected'
        records = self.installed()
        protected.write_text(protected.read_text() + ''.join(
            name + '><' + records[name]['C'] + '\n' for name in old))
        new = self.abi_generation(11, abi)
        version = '1000.11.6.18.55-r1'
        (self.root / 'var/cache/apk').mkdir(parents=True, exist_ok=True)
        self.apk('--cache', '--cache-packages', 'add', str(self.repo / (new[0] + '-' + abi + '.apk')),
                 'linux-image-openwrt=1-r11', 'kmod-abi-probe=' + version,
                 'kernel-dev-headers=' + version)
        for name in (*old, *new):
            self.assertIn(name, self.installed())
        self.assertEqual(self.installed()['linux-image-openwrt']['V'], '1-r11')

    def test_old_retained_image_pin_does_not_enable_same_abi_upgrade(self):
        abi, _ = self.installed_abi_generation()
        retained = self.abi_generation(9, abi)
        self.apk('add', retained[0] + '=' + abi)
        new = self.abi_generation(11, abi)
        self.apk('upgrade')
        after = self.installed()
        self.assertEqual(after['linux-image-openwrt']['V'], '1-r10')
        for name in new:
            self.assertNotIn(name, after)

    def test_same_abi_targeted_upgrade_also_keeps_installed_generation(self):
        abi, old = self.installed_abi_generation()
        new = self.abi_generation(11, abi)
        self.apk('upgrade', 'linux-image-openwrt')
        self.assertEqual(self.installed()['linux-image-openwrt']['V'], '1-r10')
        for name in old:
            self.assertIn(name, self.installed())
        for name in new:
            self.assertNotIn(name, self.installed())

    def test_same_abi_targeted_module_upgrade_keeps_installed_generation(self):
        abi, _ = self.installed_abi_generation()
        new = self.abi_generation(11, abi)
        self.apk('upgrade', 'kmod-abi-probe')
        self.assertEqual(self.installed()['kmod-abi-probe']['V'], '1000.10.6.18.55-r1')
        for name in new:
            self.assertNotIn(name, self.installed())

    def test_new_module_cannot_introduce_same_abi_generation(self):
        abi, _ = self.installed_abi_generation()
        for sequence in (10, 11, 12):
            image, _, _ = self.abi_generation(sequence, abi)
            generation = image.removeprefix('linux-image-')
            payload = 'kmod-new-probe-' + generation
            version = '1000.' + str(sequence) + '.6.18.55-r1'
            self.pkg(payload, version, 'usr/lib/modules/' + generation + '/new.ko',
                     b'new driver', image + '=' + abi)
            self.pkg('kmod-new-probe', version, 'usr/share/new-probe-tracker', str(sequence).encode(),
                     'kernel=' + abi + ' ' + payload + '=' + version)
        self.index()
        before = (self.root / 'lib/apk/db/installed').read_bytes()
        self.apk('add', 'kmod-new-probe', success=False)
        self.assertEqual(before, (self.root / 'lib/apk/db/installed').read_bytes())
        self.apk('add', 'kmod-new-probe=1000.10.6.18.55-r1')
        after = self.installed()
        self.assertEqual(after['linux-image-openwrt']['V'], '1-r10')
        self.assertEqual(after['kmod-new-probe']['V'], '1000.10.6.18.55-r1')
        self.assertFalse(any(name.startswith('linux-image-') and name.endswith(('-g11', '-g12'))
                             for name in after))

    def test_same_abi_policy_preserves_explicit_world_constraints(self):
        abi, _ = self.installed_abi_generation()
        self.abi_generation(11, abi)
        world_path = self.root / 'etc/apk/world'
        world = world_path.read_text().replace('linux-image-openwrt\n', 'linux-image-openwrt=1-r11\n')
        subprocess.run(['sudo', '-n', 'tee', str(world_path)], input=world,
                       text=True, capture_output=True, check=True)
        database = (self.root / 'lib/apk/db/installed').read_bytes()
        self.apk('upgrade', success=False)
        self.assertEqual(database, (self.root / 'lib/apk/db/installed').read_bytes())
        self.assertEqual(world_path.read_text(), world)

    def obsolete_module_transition(self):
        abi, _ = self.installed_abi_generation()
        self.pkg('kmod-obsolete', '1-r1', 'usr/share/obsolete', b'old tracker', 'kernel=' + abi)
        self.index()
        self.apk('add', 'kmod-obsolete')
        self.abi_generation(11, abi.replace('a' * 32, 'b' * 32))
        self.pkg('userspace-probe', '1-r2', 'usr/share/userspace-probe', b'new userspace')
        self.index()
        return abi

    def test_missing_compatibility_blocks_full_upgrade_with_json_report(self):
        self.obsolete_module_transition()
        world = (self.root / 'etc/apk/world').read_bytes()
        database = (self.root / 'lib/apk/db/installed').read_bytes()
        plan = self.work / 'plan.json'
        self.apk('upgrade', '--simulate', '--plan-json', str(plan), success=False)
        report = json.loads(subprocess.check_output(['sudo', '-n', 'cat', str(plan)], text=True))
        self.assertEqual(report['status'], 'blocked')
        self.assertEqual(report['blockers'], ['unsatisfied-package-migration-or-dependency'])
        self.assertEqual(database, (self.root / 'lib/apk/db/installed').read_bytes())
        self.assertEqual(world, (self.root / 'etc/apk/world').read_bytes())

    def test_userspace_only_retains_kernel_identity_and_world(self):
        abi = self.obsolete_module_transition()
        before = self.installed()
        world = (self.root / 'etc/apk/world').read_bytes()
        plan = self.work / 'plan.json'
        self.apk('upgrade', '--userspace-only', '--simulate', '--plan-json', str(plan))
        report = json.loads(subprocess.check_output(['sudo', '-n', 'cat', str(plan)], text=True))
        self.assertEqual(report['schema'], 1)
        self.assertEqual(report['mode'], 'userspace-only')
        self.assertEqual(report['status'], 'passed')
        self.assertEqual(report['kernel']['before']['abi'], abi)
        self.assertEqual(report['kernel']['after']['abi'], abi)
        self.assertEqual(report['inputs']['world_sha256'], hashlib.sha256(world).hexdigest())
        self.assertEqual(report['indexes'][0]['sha256'],
                         hashlib.sha256((self.repo / 'packages.adb').read_bytes()).hexdigest())
        self.apk('upgrade', '--userspace-only')
        after = self.installed()
        self.assertEqual(after['userspace-probe']['V'], '1-r2')
        for name in before:
            if name == 'kernel' or name.startswith(('kmod-', 'linux-image-', 'kernel-dev-headers')):
                self.assertEqual(before[name], after[name])
        self.assertEqual(world, (self.root / 'etc/apk/world').read_bytes())

    def test_compatibility_tracker_allows_abi_transition(self):
        self.obsolete_module_transition()
        abi = '6.18.55~' + 'b' * 32 + '-r1'
        self.pkg('kmod-obsolete', '1-r2', 'usr/share/obsolete', b'compatibility tracker', 'kernel=' + abi)
        self.index()
        self.apk('upgrade')
        self.assertEqual(self.installed()['kernel']['V'], abi)
        self.assertEqual(self.installed()['kmod-obsolete']['V'], '1-r2')

    def test_userspace_only_rejects_world_reset_and_targeted_upgrade(self):
        before = (self.root / 'etc/apk/world').read_bytes()
        for args in (('--available',), ('--prune',), ('--preupgrade-only',), ('legacy-module',)):
            self.apk('upgrade', '--userspace-only', *args, success=False)
        self.assertEqual(before, (self.root / 'etc/apk/world').read_bytes())

    def test_explicit_kernel_version_pin_is_not_reset_by_full_upgrade_intent(self):
        abi = self.obsolete_module_transition()
        self.apk('add', 'kernel=' + abi)
        world = (self.root / 'etc/apk/world').read_bytes()
        self.apk('upgrade')
        self.assertEqual(self.installed()['kernel']['V'], abi)
        self.assertEqual(self.installed()['userspace-probe']['V'], '1-r2')
        self.assertEqual(world, (self.root / 'etc/apk/world').read_bytes())

    def test_full_preflight_prevents_early_support_upgrade(self):
        self.obsolete_module_transition()
        self.preupgrade_probe()
        before = (self.root / 'lib/apk/db/installed').read_bytes()
        result = self.chroot_apk('upgrade', '--preupgrade-depends', 'preupgrade-probe')
        self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(before, (self.root / 'lib/apk/db/installed').read_bytes())
        self.assertEqual(self.installed()['preupgrade-probe']['V'], '1-r1')

    def test_corrupt_local_payload_blocks_before_any_package_write(self):
        self.pkg('payload-probe', '1-r1', 'usr/share/payload-probe', b'old')
        self.index()
        self.apk('add', 'payload-probe')
        self.pkg('payload-probe', '1-r2', 'usr/share/payload-probe', b'new')
        self.index()
        payload = self.repo / 'payload-probe-1-r2.apk'
        data = payload.read_bytes()
        # Truncate signed content; a final-byte flip may only alter padding.
        payload.write_bytes(data[:len(data) // 2])
        before = (self.root / 'lib/apk/db/installed').read_bytes()
        plan = self.work / 'plan.json'
        self.apk('upgrade', '--plan-json', str(plan), success=False)
        report = json.loads(subprocess.check_output(['sudo', '-n', 'cat', str(plan)], text=True))
        self.assertEqual(report['blockers'], ['payload-verification-failed'])
        self.assertEqual(before, (self.root / 'lib/apk/db/installed').read_bytes())
        self.assertEqual((self.root / 'usr/share/payload-probe').read_bytes(), b'old')

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
        self.assertIn('apk-pre 0 simulate 0', contract.read_text())
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

    def test_delete_keeps_protected_orphan_generation(self):
        self.apk('upgrade')
        world = self.root / 'etc/apk/world'
        subprocess.run(['sudo', '-n', 'chown', str(os.getuid()), str(world)], check=True)
        world.write_text(''.join(line + '\n' for line in world.read_text().splitlines()
                                 if not line.startswith('linux-image-generation-one')))
        self.assertNotIn('linux-image-generation-one', world.read_text())
        self.apk('del', 'legacy-headers')
        self.assertNotIn('legacy-headers', self.installed())
        self.assertIn('linux-image-generation-one', self.installed())
        self.assertEqual((self.root / 'usr/share/kernel-one').read_bytes(), b'old image')

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
