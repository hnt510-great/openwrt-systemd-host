#!/usr/bin/env python3
"""Distribution-style kernel packages: adoption, boot counting, retention and channel."""
import argparse
from contextlib import contextmanager
import fcntl
import gzip
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

TREE = Path(__file__).resolve().parents[2]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


KERNELCTL = TREE / 'package/custom/openwrt-kernel-upgrade/files/kernelctl'
K = load('kernelctl', KERNELCTL)
B = load('kernel_bundle', TREE / 'scripts/kernel-bundle.py')
F = load('kernel_feed', TREE / 'scripts/publish-kernel-upgrade-feed.py')
APK = TREE / 'staging_dir/host/bin/apk'
ABI = '6.18.55~' + 'a' * 32 + '-r1'
GEN = '6.18.55-owrt-' + 'a' * 32 + '-r1-g45'
FAKEROOT = TREE / 'staging_dir/host/bin/fakeroot'


def release(number):
    return f'6.18.55-{number}-openwrt'


class RecipeTests(unittest.TestCase):
    def test_logging_compatibility_default_survives_configuration_free_scan(self):
        # Package scanning does not load .config. Its conditional default must
        # reach Kconfig rather than being evaluated by Make during the scan.
        output = subprocess.check_output([
            'make', '-s', '-C', str(TREE / 'package/kernel/linux'),
            'TOPDIR=' + str(TREE), 'DUMP=1', 'dumpinfo'], text=True)
        recipe = next(block for block in output.split('@@')
                      if block.lstrip().startswith('Package: kmod-nf-log6\n'))
        self.assertIn('\nDefault: y if OPENWRT_KERNEL_UPGRADE\n', recipe)
        self.assertIn('\nHidden: 1\n', recipe)
        self.assertIn('\nDepends: +kmod-nf-log\n', recipe)
        self.assertNotIn('\nKernel-Config:', recipe)

    def test_new_compatibility_rule_builds_for_an_unnormalized_configuration(self):
        output = subprocess.check_output([
            'make', '-s', '-C', str(TREE / 'package/kernel/linux'),
            'TOPDIR=' + str(TREE), 'DUMP=1', 'CONFIG_OPENWRT_KERNEL_UPGRADE=y',
            '--eval=compatibility-selection:; @echo COMPAT_SELECTION=$(CONFIG_PACKAGE_kmod-nf-log6)',
            'compatibility-selection'], text=True)
        self.assertIn('COMPAT_SELECTION=m', output)


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('boot/grub', 'etc/openwrt-kernel', 'etc/apk', 'usr/lib/modules',
                          'usr/lib/apk/db', 'lib/apk/db', 'proc/self', 'proc/1', 'run', 'tmp',
                          'usr/libexec'):
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        (self.root / 'lib/apk/db/lock').touch()
        (self.root / 'usr/libexec/openwrt-kernel-init').write_text('#!/bin/sh\n')
        (self.root / 'boot/vmlinuz').write_bytes(b'ONLY KNOWN BOOTABLE KERNEL')
        (self.root / 'proc/self/mountinfo').write_text('34 29 8:1 /boot /boot rw,noatime - vfat /dev/sda1 rw\n')
        (self.root / 'proc/1/comm').write_text('systemd\n')
        (self.root / 'proc/cmdline').write_text('root=PARTUUID=abcd-02 openwrt.init=systemd noinitrd')
        (self.root / 'proc/mounts').write_text('/dev/nvme0n1p1 /overlay ext4 rw 0 0\n')
        (self.root / 'proc/config.gz').write_bytes(gzip.compress(b'CONFIG_BLK_DEV_INITRD=y\n'))
        carrier = self.root / 'sys/class/net/br-lan/carrier'
        carrier.parent.mkdir(parents=True); carrier.write_text('1\n')
        support = self.root / 'usr/share/openwrt-kernel'
        (support / 'grub/x86_64-efi').mkdir(parents=True)
        (support / 'grub/x86_64-efi/loadenv.mod').write_bytes(b'grub module')
        for capability in ('apk-policy', 'kmodloader-policy'):
            (support / capability).write_text('1\n')
        (self.root / 'boot/grub/grub.cfg').write_text(
            "serial --unit=0\nmenuentry 'OpenWrt' {\n linux /boot/vmlinuz root=PARTUUID=abcd-02\n}\n")
        (self.root / 'etc/apk/world').write_text('kernel=' + ABI + '\nkmod-nic\nlinux-image-openwrt=1-r45\n')
        self.environment = {}
        self.calls = []
        self.packages = {'kernel': ABI, 'kmod-nic': '1000.1.6.18.55-r1'}
        self.lan_up = True
        self.running = release(1)
        self.manager = K.KernelManager(self.root, self.run_command)
        self.original = K.sha256(self.root / 'boot/vmlinuz')
        self.package(1, image=b'ONLY KNOWN BOOTABLE KERNEL')

    def run_command(self, args):
        self.calls.append(args)
        if args[:2] == ['uname', '-r']:
            return self.running
        if args[0] == 'blkid':
            return '1234-ABCD'
        if args[0] == 'grub-editenv':
            if args[2] == 'set':
                for item in args[3:]:
                    key, value = item.split('=', 1)
                    self.environment[key] = value
            elif args[2] == 'unset':
                for key in args[3:]:
                    self.environment.pop(key, None)
            elif args[2] == 'list':
                return '\n'.join(f'{k}={v}' for k, v in self.environment.items())
            return ''
        if args[0] == 'ubus':
            return json.dumps({'interface': [
                {'interface': 'lan', 'up': self.lan_up, 'proto': 'static', 'l3_device': 'br-lan',
                 'ipv4-address': [{'address': '192.0.2.1'}]},
                {'interface': 'wan', 'up': False, 'proto': 'dhcp'}]})
        if args[0] == 'apk' and 'del' in args:
            for name in args[args.index('del') + 1:]:
                self.packages.pop(name, None)
            self.database()
        return ''

    def database(self):
        (self.root / 'usr/lib/apk/db/installed').write_text('\n\n'.join(
            f'P:{name}\nV:{version}\nC:Q1{name}' for name, version in self.packages.items()) + '\n\n')

    def package(self, number, image=None, installed=True):
        """An installed linux-image-<release> as kernel-bundle.py lays it out."""
        name = release(number)
        metadata = self.root / 'usr/lib/openwrt-kernel' / name
        modules = self.root / 'usr/lib/modules' / name
        metadata.mkdir(parents=True, exist_ok=True)
        modules.mkdir(parents=True, exist_ok=True)
        (metadata / 'vmlinuz').write_bytes(image or ('kernel ' + name).encode())
        (metadata / 'config').write_text('CONFIG_BLK_DEV_INITRD=y\n')
        (modules / 'nic.ko').write_bytes(('module ' + name).encode())
        (modules / 'modules.builtin').write_text('')
        files = {str(p.relative_to(self.root)): {'sha256': K.sha256(p)}
                 for p in [metadata / 'vmlinuz', metadata / 'config', modules / 'nic.ko', modules / 'modules.builtin']}
        K.json_write(metadata / 'image.json', {
            'schema': 2, 'release': name, 'version': f'6.18.55-r{number}', 'sequence': number,
            'package': 'linux-image-' + name, 'kernel_sha256': K.sha256(metadata / 'vmlinuz'),
            'files': files})
        if installed:
            self.packages['linux-image-' + name] = f'6.18.55-r{number}'
            self.database()
        return name

    def bootstrap(self, name, path):
        K.atomic(path, gzip.compress(b'bootstrap for ' + name.encode(), mtime=0), 0o644)

    def adopt(self):
        with patch.object(self.manager, 'bootstrap', side_effect=self.bootstrap):
            return self.manager.migrate()

    def install(self, number, errors='0', simulation='live'):
        name = self.package(number)
        txn = self.root / 'run/txn'
        txn.write_text(f'-\t-\tlinux-image-{name}\t6.18.55-r{number}\t0\n'
                       f'linux-image-openwrt\t6.18.55-r{number - 1}\tlinux-image-openwrt\t6.18.55-r{number}\t0\n')
        with patch.object(self.manager, 'bootstrap', side_effect=self.bootstrap):
            self.manager.transaction('apk-pre', txn, '0', simulation, '0')
            self.manager.transaction('apk-post', txn, errors, simulation, '0')
        return name

    def boot(self, name, healthy=True):
        """Boot a kernel and run the boot assessment."""
        self.running = name
        self.lan_up = healthy
        self.manager.prepare()
        return self.manager.assess(timeout=0)

    # -- adoption --------------------------------------------------------------

    def test_adoption_makes_the_image_kernel_rescue_and_follows_the_newest_kernel(self):
        state = self.adopt()
        self.assertEqual(state['schema'], 2)
        self.assertEqual((state['rescue'], state['default'], state['known_good']), (release(1),) * 3)
        self.assertEqual(self.environment['saved_entry'], 'owrt-rescue')
        self.assertEqual((self.root / 'etc/apk/world').read_text(), 'kernel\nkmod-nic\nlinux-image-openwrt\n')
        self.assertIn('linux-image-' + release(1) + '><Q1linux-image-' + release(1),
                      (self.manager.policy / 'protected').read_text())
        grub = (self.root / 'boot/grub/grub.cfg').read_text()
        self.assertTrue(grub.startswith('serial --unit=0\n'))
        self.assertLess(grub.index("--id=owrt-rescue {"), grub.index('source $prefix/openwrt.cfg'))
        self.assertIn('if [ "$boot_left" = 0 ]; then set default=$fallback_entry', grub)
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_adoption_requires_the_running_kernel_package(self):
        self.running = '6.18.55-9-openwrt'
        with self.assertRaisesRegex(K.KernelError, 'not an installed kernel package'):
            self.adopt()
        self.assertFalse((self.manager.policy / 'state.json').exists())

    def test_bad_boot_mount_refuses_without_writes(self):
        self.adopt()
        (self.root / 'proc/self/mountinfo').write_text('')
        with self.assertRaisesRegex(K.KernelError, 'not mounted'):
            self.manager.check()

    # -- installing kernels ------------------------------------------------------

    def test_new_kernel_package_becomes_the_counted_default(self):
        self.adopt()
        name = self.install(2)
        state = self.manager.state()
        self.assertEqual((state['default'], state['counting'], state['fallback']), (name, name, release(1)))
        self.assertEqual(self.environment['saved_entry'], 'owrt-' + name)
        self.assertEqual(self.environment['boot_left'], '3')
        self.assertEqual(self.environment['fallback_entry'], 'owrt-rescue')
        boot = self.root / 'boot/kernels' / name
        self.assertEqual((boot / 'vmlinuz').read_bytes(), b'kernel ' + name.encode())
        self.assertTrue((boot / 'initramfs.gz').is_file())
        self.assertIn(['depmod', '-a', name], self.calls)
        menu = (self.root / 'boot/grub/openwrt.cfg').read_text()
        self.assertIn(f"--id=owrt-{name} {{\n linux /boot/kernels/{name}/vmlinuz root=PARTUUID=abcd-02 openwrt.init=systemd", menu)
        self.assertIn(f"--id=owrt-{name}-procd", menu)
        self.assertNotIn('firmware_class.path', menu)
        protected = (self.manager.policy / 'protected').read_text()
        self.assertIn('linux-image-' + name + '>', protected)
        self.assertIn('linux-image-' + release(1) + '>', protected)
        self.manager.check()

    def test_simulation_and_failed_transactions_change_no_boot_entries(self):
        self.adopt()
        self.install(2, simulation='simulate')
        self.assertFalse((self.root / 'boot/kernels').exists())
        self.assertNotIn('boot_left', self.environment)
        with self.assertRaisesRegex(K.KernelError, 'transaction failed'):
            self.install(3, errors='1')
        self.assertFalse((self.root / 'boot/kernels').exists())
        self.assertEqual(self.manager.state()['default'], release(1))

    def test_changed_kernel_package_files_are_refused(self):
        self.adopt()
        self.package(2)
        (self.root / 'usr/lib/modules' / release(2) / 'nic.ko').write_bytes(b'changed')
        txn = self.root / 'run/txn'
        txn.write_text(f'-\t-\tlinux-image-{release(2)}\t6.18.55-r2\t0\n')
        with patch.object(self.manager, 'bootstrap', side_effect=self.bootstrap):
            with self.assertRaisesRegex(K.KernelError, 'changed kernel file'):
                self.manager.transaction('apk-post', txn, '0', 'live', '0')
        self.assertNotIn('boot_left', self.environment)

    def test_scripts_are_required_for_kernel_transactions(self):
        self.adopt()
        self.package(2)
        txn = self.root / 'run/txn'
        txn.write_text(f'-\t-\tlinux-image-{release(2)}\t6.18.55-r2\t0\n')
        with self.assertRaisesRegex(K.KernelError, 'requires scripts'):
            self.manager.transaction('apk-pre', txn, '0', 'live', '1')

    def test_userspace_and_kmod_configuration_changes_are_not_kernel_transactions(self):
        self.adopt()
        before = (self.manager.policy / 'state.json').read_bytes()
        txn = self.root / 'run/txn'
        txn.write_text('kmod-nic\t1000.1.6.18.55-r1\tkmod-nic\t1000.2.6.18.55-r1\t0\n'
                       'busybox\t1-r1\tbusybox\t1-r2\t0\n')
        self.manager.transaction('apk-pre', txn, '0', 'live', '1')
        self.manager.transaction('apk-post', txn, '0', 'live', '1')
        self.assertEqual(before, (self.manager.policy / 'state.json').read_bytes())

    # -- boot counting -----------------------------------------------------------

    def test_prepare_arms_the_counting_reboot_only_for_the_counted_kernel(self):
        self.adopt()
        name = self.install(2)
        dropin = self.root / K.COUNTING_DROPIN.lstrip('/')
        self.running = release(1)
        self.manager.prepare()
        self.assertFalse(dropin.exists())
        self.running = name
        self.manager.prepare()
        self.assertIn('FailureAction=reboot', dropin.read_text())
        self.assertIn('JobTimeoutAction=reboot', dropin.read_text())

    def test_healthy_counted_boot_is_blessed(self):
        self.adopt()
        name = self.install(2)
        state = self.boot(name)
        self.assertEqual((state['known_good'], state['default'], state['counting']), (name, name, None))
        self.assertNotIn('boot_left', self.environment)
        self.assertNotIn('fallback_entry', self.environment)
        self.assertEqual(self.environment['saved_entry'], 'owrt-' + name)
        self.assertFalse((self.root / K.COUNTING_DROPIN.lstrip('/')).exists())

    def test_unhealthy_counted_boot_fails_so_the_unit_reboots(self):
        self.adopt()
        name = self.install(2)
        with self.assertRaisesRegex(K.KernelError, 'LAN'):
            self.boot(name, healthy=False)
        state = self.manager.state()
        self.assertEqual((state['counting'], state['known_good']), (name, release(1)))
        self.assertEqual(self.environment['boot_left'], '3')

    def test_wan_outage_does_not_fail_a_counted_boot(self):
        self.adopt()
        name = self.install(2)
        # The baseline holds only static local interfaces; WAN (dhcp) is down.
        self.assertEqual(self.manager.state()['health']['interfaces'], ['lan'])
        self.assertEqual(self.boot(name)['known_good'], name)

    def test_exhausted_attempts_restore_the_fallback_as_default(self):
        self.adopt()
        name = self.install(2)
        self.environment['boot_left'] = '0'
        state = self.boot(release(1))
        self.assertTrue(state['kernels'][name]['bad'])
        self.assertEqual((state['default'], state['counting']), (release(1), None))
        self.assertEqual(self.environment['saved_entry'], 'owrt-rescue')
        self.assertNotIn('boot_left', self.environment)
        self.assertIn(f"'OpenWrt {name} (failed boot)'", (self.root / 'boot/grub/openwrt.cfg').read_text())

    def test_menu_choice_during_counting_is_not_a_failure(self):
        self.adopt()
        name = self.install(2)
        self.environment['boot_left'] = '2'
        state = self.boot(release(1))
        self.assertEqual((state['counting'], state['default']), (name, name))
        self.assertFalse(state['kernels'][name].get('bad'))

    def test_set_default_and_rollback(self):
        self.adopt()
        two = self.install(2)
        self.boot(two)
        three = self.install(3)
        state = self.manager.rollback()
        self.assertTrue(state['kernels'][three]['bad'])
        self.assertEqual((state['default'], self.environment['saved_entry']), (two, 'owrt-' + two))
        state = self.manager.set_default(three)
        self.assertFalse(state['kernels'][three]['bad'])
        self.assertEqual((state['default'], state['counting']), (three, None))
        self.assertEqual(self.environment['saved_entry'], 'owrt-' + three)
        with self.assertRaisesRegex(K.KernelError, 'Unknown kernel'):
            self.manager.set_default('6.18.55-99-openwrt')

    def test_booted_set_default_kernel_becomes_known_good(self):
        self.adopt()
        two = self.install(2)
        self.environment['boot_left'] = '0'
        self.boot(release(1))
        self.manager.set_default(two)
        state = self.boot(two)
        self.assertEqual((state['known_good'], state['default'], state['counting']), (two, two, None))

    # -- retention and removal ---------------------------------------------------

    def test_retention_keeps_default_and_fallback_besides_rescue(self):
        self.adopt()
        for number in (2, 3, 4):
            self.boot(self.install(number))
        five = self.install(5)
        # Pending 5 with the running 4 as fallback: 3 is withdrawn immediately.
        state = self.manager.state()
        self.assertEqual(self.manager.retention(state), [five, release(4)])
        self.assertEqual(sorted(self.manager.prunable(state)), [release(2), release(3)])
        self.assertFalse((self.root / 'boot/kernels' / release(3)).exists())
        self.assertTrue((self.root / 'boot/kernels' / release(4)).exists())
        self.assertTrue((self.root / 'run/openwrt-kernel-prune').exists())
        self.boot(five)
        self.manager.prune()
        self.assertIn(['apk', '--wait', '10', '--no-network', 'del', 'linux-image-' + release(2)], self.calls)
        state = self.manager.state()
        self.assertEqual(sorted(state['kernels']), sorted([release(1), release(4), five]))
        protected = (self.manager.policy / 'protected').read_text()
        self.assertNotIn('linux-image-' + release(3), protected)
        self.assertFalse((self.manager.policy / 'pruning.json').exists())
        menu = (self.root / 'boot/grub/openwrt.cfg').read_text()
        self.assertNotIn(release(3), menu)
        self.assertIn(release(4), menu)

    def test_apk_cannot_remove_held_or_unplanned_kernels(self):
        self.adopt()
        two = self.install(2)
        self.boot(two)
        self.install(3)
        self.boot(release(3))
        self.install(4)
        txn = self.root / 'run/txn'
        for name in (release(1), release(4), release(3)):
            txn.write_text(f'linux-image-{name}\t6.18.55-r1\t-\t-\t0\n')
            with self.assertRaisesRegex(K.KernelError, 'Refusing to remove'):
                self.manager.transaction('apk-pre', txn, '0', 'live', '0')
        txn.write_text(f'linux-image-{two}\t6.18.55-r2\t-\t-\t0\n')
        with self.assertRaisesRegex(K.KernelError, 'kernelctl remove'):
            self.manager.transaction('apk-pre', txn, '0', 'live', '0')
        packages = self.manager.remove(two)
        self.assertEqual(packages, ['linux-image-' + two])
        self.manager.transaction('apk-pre', txn, '0', 'live', '0')

    def test_remove_refuses_the_kernel_the_metapackage_requires(self):
        self.adopt()
        two = self.install(2)
        self.boot(two)
        three = self.install(3)
        self.boot(three)
        self.packages['linux-image-openwrt'] = '6.18.55-r3'
        self.database()
        records = self.manager.installed()
        db = (self.root / 'usr/lib/apk/db/installed')
        db.write_text(db.read_text().replace('P:linux-image-openwrt\nV:6.18.55-r3\n',
                      'P:linux-image-openwrt\nV:6.18.55-r3\nD:linux-image-' + three + '=6.18.55-r3\n'))
        self.manager.set_default(two)
        self.boot(two)
        with self.assertRaisesRegex(K.KernelError, 'newest kernel'):
            self.manager.remove(three)
        self.assertIn(three, self.manager.state()['kernels'])

    def test_remove_keeps_state_when_apk_keeps_the_package(self):
        self.adopt()
        two = self.install(2)
        self.boot(two)
        self.boot(self.install(3))
        self.boot(self.install(4))
        packages = self.manager.remove(two)
        self.assertEqual(packages, ['linux-image-' + two])
        self.manager.finish_remove(two, True)  # apk "succeeded" but kept it
        self.assertIn(two, self.manager.state()['kernels'])
        self.assertTrue((self.root / 'usr/lib/openwrt-kernel' / two / 'image.json').is_file())
        self.manager.forget(self.manager.state(), two)  # even a forced forget keeps package files
        self.assertTrue((self.root / 'usr/lib/openwrt-kernel' / two / 'image.json').is_file())
        self.assertIn('linux-image-' + two, (self.manager.policy / 'protected').read_text())

    def test_remove_refuses_the_running_default_and_rescue_kernels(self):
        self.adopt()
        two = self.install(2)
        for name in (release(1), two):
            with self.assertRaisesRegex(K.KernelError, 'Refusing to remove'):
                self.manager.remove(name)

    # -- schema-1 generations ----------------------------------------------------

    def legacy_state(self):
        """A router adopted with the previous per-generation model, running g45."""
        modules = self.root / 'usr/lib/modules/6.18.55'
        modules.mkdir(parents=True, exist_ok=True)
        (modules / 'nic.ko').write_bytes(b'original network driver')
        rescue_copy = self.root / 'usr/lib/openwrt-kernel/legacy-6.18.55'
        (rescue_copy / 'modules.d').mkdir(parents=True)
        (rescue_copy / 'modules.d/30-nic').write_text('nic\n')
        boot = self.root / 'boot/kernels' / GEN
        boot.mkdir(parents=True)
        (boot / 'vmlinuz').write_bytes(b'kernel g45')
        (boot / 'initramfs.gz').write_bytes(b'initramfs g45')
        autoload = self.root / 'usr/lib/modules' / GEN / 'openwrt/modules.d'
        autoload.mkdir(parents=True)
        (autoload / '30-nic').write_text('nic\n')
        firmware = self.root / 'usr/lib/openwrt-kernel' / GEN / 'firmware'
        firmware.mkdir(parents=True)
        state = {'schema': 1, 'phase': 'ready', 'rescue': 'legacy-6.18.55', 'known_good': GEN,
                 'previous_good': 'legacy-6.18.55', 'pending': None,
                 'bootargs': 'root=PARTUUID=abcd-02', 'required_config': [],
                 'health': {'interfaces': ['lan', 'wan', 'wan6'], 'overlay': ['/dev/nvme0n1p1'],
                            'lan_addresses': ['192.0.2.1'], 'default_route': True, 'kvm': False},
                 'generations': {
                     'legacy-6.18.55': {'legacy': True, 'ready': True, 'release': '6.18.55', 'abi': ABI,
                                        'kernel_sha256': self.original,
                                        'modules': K.inventory(modules)},
                     GEN: {'legacy': False, 'ready': True, 'release': GEN, 'abi': ABI,
                           'kernel_sha256': K.sha256(boot / 'vmlinuz'), 'files': {},
                           'boot_files': K.inventory(boot)}}}
        K.json_write(self.manager.policy / 'state.json', state)
        self.packages = {'kernel': ABI, 'kmod-nic': '1000.45.6.18.55-r1',
                         'linux-image-' + GEN: ABI, 'kmod-nic-' + GEN: '1000.45.6.18.55-r1',
                         'linux-image-openwrt': '1-r45'}
        self.database()
        (self.root / 'boot/grub/grub.cfg.rescue').write_text('serial --unit=0\n')
        self.running = GEN

    def test_schema1_state_converts_to_legacy_kernels(self):
        self.legacy_state()
        state = self.manager.state()
        self.assertEqual(json.loads((self.manager.policy / 'state.json').read_text())['schema'], 2)
        self.assertEqual(state['kernels'][GEN]['kind'], 'legacy-generation')
        self.assertEqual(state['kernels']['legacy-6.18.55']['kind'], 'legacy-rescue')
        self.assertEqual((state['default'], state['known_good'], state['fallback']),
                         (GEN, GEN, 'legacy-6.18.55'))
        # Only the static local interface survives; the DHCP WANs never count.
        self.assertEqual(state['health'], {'interfaces': ['lan'], 'overlay': ['/dev/nvme0n1p1'],
                                           'lan_addresses': ['192.0.2.1']})
        self.manager.check()
        menu = self.manager.grub_config(state)
        self.assertIn(f'linux /boot/kernels/{GEN}/vmlinuz root=PARTUUID=abcd-02 '
                      f'firmware_class.path=/usr/lib/openwrt-kernel/{GEN}/firmware openwrt.init=systemd', menu)
        self.manager.prepare()
        link = self.root / 'run/openwrt-kernel/modules.d/30-nic'
        self.assertEqual(link.resolve(), (self.root / 'usr/lib/modules' / GEN / 'openwrt/modules.d/30-nic').resolve())

    def test_legacy_router_installs_its_first_kernel_package_with_g45_fallback(self):
        self.legacy_state()
        name = self.install(46)
        state = self.manager.state()
        self.assertEqual((state['default'], state['fallback'], state['counting']), (name, GEN, name))
        self.assertEqual(self.environment['fallback_entry'], 'owrt-' + GEN)
        protected = (self.manager.policy / 'protected').read_text()
        self.assertIn('kmod-nic-' + GEN + '>', protected)
        self.assertIn('linux-image-' + GEN + '>', protected)
        # The package kernel uses the standard /etc autoload rules.
        self.running = GEN
        self.manager.prepare()
        self.assertTrue((self.root / 'run/openwrt-kernel/modules.d').is_dir())
        self.running = name
        self.manager.prepare()
        self.assertFalse((self.root / 'run/openwrt-kernel/modules.d').exists())
        state = self.manager.assess(timeout=0)
        self.assertEqual(state['known_good'], name)
        # g45 stays as the fallback until two newer kernels exist.
        self.assertIn(GEN, self.manager.retention(state))
        self.assertEqual(self.manager.kernel_packages(state, GEN),
                         sorted(['kmod-nic-' + GEN, 'linux-image-' + GEN]))

    def test_router_prunes_the_extra_legacy_generation_only(self):
        self.legacy_state()
        g43 = GEN.replace('-g45', '-g43')
        state = json.loads((self.manager.policy / 'state.json').read_text())
        boot = self.root / 'boot/kernels' / g43
        boot.mkdir(parents=True)
        (boot / 'vmlinuz').write_bytes(b'kernel g43')
        state['generations'][g43] = {'legacy': False, 'ready': True, 'release': g43, 'abi': ABI,
                                     'kernel_sha256': K.sha256(boot / 'vmlinuz'), 'files': {},
                                     'boot_files': K.inventory(boot)}
        state['previous_good'] = g43
        K.json_write(self.manager.policy / 'state.json', state)
        self.packages.update({'linux-image-' + g43: ABI, 'kmod-nic-' + g43: '1000.43.6.18.55-r1'})
        self.database()
        self.assertEqual(self.manager.state()['fallback'], g43)
        name = self.install(47)
        state = self.manager.assess(timeout=0) if self.running == name else self.boot(name)
        self.assertEqual((state['default'], state['fallback']), (name, GEN))
        self.assertEqual(self.manager.prunable(state), [g43])
        self.assertFalse((self.root / 'boot/kernels' / g43).exists())
        self.assertEqual(self.manager.kernel_packages(state, g43),
                         sorted(['kmod-nic-' + g43, 'linux-image-' + g43]))

    # -- health and helpers ------------------------------------------------------

    def test_health_requires_every_systemd_service(self):
        original = self.manager.command
        def failed_service(*args):
            if args == ('systemctl', 'is-active', 'openwrt-services'):
                raise K.KernelError('openwrt-services failed')
            return original(*args)
        with patch.object(self.manager, 'command', side_effect=failed_service):
            with self.assertRaisesRegex(K.KernelError, 'openwrt-services failed'):
                self.manager.health()

    def test_ram_overlay_cannot_qualify_as_persistent(self):
        (self.root / 'proc/mounts').write_text('tmpfs /overlay tmpfs rw 0 0\n')
        with self.assertRaisesRegex(K.KernelError, 'Persistent overlay'):
            self.manager.health()

    def test_health_selects_the_installed_ssh_supervisor(self):
        self.manager.health()
        self.assertIn(['/etc/init.d/sshd', 'status'], self.calls)
        self.calls.clear()
        unit = self.root / 'usr/lib/systemd/system/sshd.service'
        unit.parent.mkdir(parents=True)
        unit.touch()
        self.manager.health()
        self.assertIn(['systemctl', 'is-active', 'sshd.service'], self.calls)
        self.assertNotIn(['/etc/init.d/sshd', 'status'], self.calls)

    def test_initramfs_archive_roundtrips_with_standard_cpio(self):
        archive_root = self.root / 'archive'; archive_root.mkdir()
        (archive_root / 'init').write_bytes(b'#!/bin/sh\n')
        (archive_root / 'init').chmod(0o755)
        (archive_root / 'init-link').symlink_to('/init')
        output = self.root / 'extracted'; output.mkdir()
        subprocess.run(['cpio', '-idm', '--quiet', '--no-absolute-filenames'],
                       input=K.cpio_archive(archive_root), cwd=output, check=True)
        self.assertEqual((output / 'init').read_bytes(), b'#!/bin/sh\n')
        self.assertEqual(os.readlink(output / 'init-link'), '/init')
        self.assertEqual((output / 'init').stat().st_mode & 0o777, 0o755)

    def test_bootstrap_failure_reboots_for_the_boot_counter(self):
        init = (TREE / 'package/custom/openwrt-kernel-upgrade/files/init').read_text()
        self.assertIn('echo b >/proc/sysrq-trigger', init)

    def test_release_sequence_orders_both_naming_schemes(self):
        self.assertEqual(K.sequence(release(46)), 46)
        self.assertEqual(K.sequence(GEN), 45)
        self.assertEqual(K.sequence('legacy-6.18.55'), 0)


@unittest.skipUnless(APK.exists() and FAKEROOT.exists(), 'Build apk/host first')
class ChannelTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.output = self.work / 'packages'; self.output.mkdir()
        self.key = self.work / 'private.pem'
        subprocess.run(['openssl', 'ecparam', '-name', 'prime256v1', '-genkey',
                        '-noout', '-out', str(self.key)], check=True, capture_output=True)
        subprocess.run(['openssl', 'ec', '-in', str(self.key), '-pubout',
                        '-out', str(self.work / 'public.pem')], check=True, capture_output=True)

    def make(self, name, version, depends=()):
        root = self.work / 'files' / (name + version)
        root.mkdir(parents=True)
        (root / 'probe').write_text(name + version)
        B.package(APK, FAKEROOT, self.key, root, self.output, name, version, list(depends), 'fixture', '')

    def legacy(self, sequence):
        generation = GEN.rsplit('-g', 1)[0] + f'-g{sequence}'
        image = 'linux-image-' + generation
        self.make(image, ABI)
        self.make('linux-image-openwrt', f'1-r{sequence}', [image + '=' + ABI, 'kernel=' + ABI])
        self.make('kmod-nic-' + generation, f'1000.{sequence}.6.18.55-r1', [image + '=' + ABI])

    def build(self, number):
        name = release(number)
        version = f'6.18.55-r{number}'
        self.make('linux-image-' + name, version, ['openwrt-kernel-upgrade'])
        self.make('linux-headers-' + name, version)
        self.make('linux-image-openwrt', version, ['linux-image-' + name + '=' + version])

    def test_channel_keeps_three_newest_builds_across_both_schemes(self):
        destination = self.work / 'publications'
        active = destination / 'public/kernel-upgrades'
        self.legacy(8)
        self.assertEqual(F.publish(self.output, destination, APK, self.key, self.work)['images'], 1)
        for number, images in ((9, 2), (10, 3), (11, 3)):
            self.build(number)
            self.assertEqual(F.publish(self.output, destination, APK, self.key, self.work)['images'], images)
        manifest = json.loads((active / 'manifest.json').read_text())
        self.assertEqual(sorted(manifest['images']), ['linux-image-' + release(n) for n in (10, 11, 9)])
        names = {entry['info']['name'] + '=' + entry['info']['version'] for entry in manifest['packages'].values()}
        self.assertFalse(any('-g8' in name or '1-r8' in name for name in names))
        self.assertIn('linux-headers-' + release(9) + '=6.18.55-r9', names)
        self.assertEqual(manifest['sequence'], 11)
        subprocess.run([str(APK), 'verify', '--keys-dir', str(self.work), str(active / 'packages.adb')],
                       check=True, capture_output=True)
        self.assertEqual(F.publish(self.output, destination, APK, self.key, self.work)['status'], 'unchanged')

    def test_headers_need_their_image(self):
        self.build(9)
        self.make('linux-headers-' + release(12), '6.18.55-r12')
        with self.assertRaisesRegex(ValueError, 'headers without their image'):
            F.publish(self.output, self.work / 'publications', APK, self.key, self.work)

    def test_image_version_must_match_its_release(self):
        self.make('linux-image-' + release(9), '6.18.55-r8', ['openwrt-kernel-upgrade'])
        self.make('linux-image-openwrt', '6.18.55-r8', ['linux-image-' + release(9) + '=6.18.55-r8'])
        with self.assertRaisesRegex(ValueError, 'Image version and release disagree'):
            F.publish(self.output, self.work / 'publications', APK, self.key, self.work)

    def test_retention_uses_apk_order_for_support_package_versions(self):
        packages = {f'grub2-{version}.apk': {'info': {'name': 'grub2', 'version': version}}
                    for version in ('1-r7', '1-r8', '1-r9', '1-r10')}
        retained, _ = F.retained_packages(packages, {}, {}, APK)
        self.assertEqual(set(retained), {'grub2-1-r8.apk', 'grub2-1-r9.apk', 'grub2-1-r10.apk'})


if __name__ == '__main__':
    unittest.main(verbosity=2)
