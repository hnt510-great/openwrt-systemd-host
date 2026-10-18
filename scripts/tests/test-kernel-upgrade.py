#!/usr/bin/env python3
"""Exercise fail-closed activation and real signed APK payload splitting."""
import argparse
import gzip
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

TREE = Path(__file__).resolve().parents[2]


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


K = load('kernelctl', TREE / 'package/custom/openwrt-kernel-upgrade/files/kernelctl')
P = load('kernel_package', TREE / 'scripts/kernel-package.py')
F = load('kernel_feed', TREE / 'scripts/publish-kernel-upgrade-feed.py')
APK = TREE / 'staging_dir/host/bin/apk'
ABI = '6.18.55~' + 'a' * 32 + '-r1'
GEN = '6.18.55-owrt-' + 'a' * 32 + '-r1-g1'


class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ('boot/grub', 'etc/openwrt-kernel', 'usr/lib/modules/6.18.55',
                          'usr/lib/apk/db', 'proc/self', 'proc/1', 'run', 'tmp'):
            (self.root / directory).mkdir(parents=True)
        (self.root / 'boot/vmlinuz').write_bytes(b'ONLY KNOWN BOOTABLE KERNEL')
        (self.root / 'usr/lib/modules/6.18.55/nic.ko').write_bytes(b'original network driver')
        (self.root / 'proc/self/mountinfo').write_text('34 29 8:1 /boot /boot rw,noatime - vfat /dev/sda1 rw\n')
        (self.root / 'proc/1/comm').write_text('systemd\n')
        (self.root / 'proc/cmdline').write_text('root=PARTUUID=abcd-02 openwrt.init=systemd noinitrd')
        (self.root / 'proc/mounts').write_text('/dev/nvme0n1p1 /overlay ext4 rw 0 0\n')
        carrier = self.root / 'sys/class/net/br-lan/carrier'
        carrier.parent.mkdir(parents=True); carrier.write_text('1\n')
        self.environment = {'saved_entry': 'owrt-rescue'}
        self.calls = []
        self.running = '6.18.55'
        self.manager = K.KernelManager(self.root, self.run_command)
        self.modules = K.inventory(self.root / 'usr/lib/modules/6.18.55')
        self.original = K.sha256(self.root / 'boot/vmlinuz')
        self.baseline = {'interfaces': ['lan', 'wan'], 'overlay': ['/dev/nvme0n1p1'],
                         'default_route': True, 'kvm': False}
        self.state = {'schema': 1, 'rescue': 'legacy-6.18.55', 'known_good': 'legacy-6.18.55',
                      'previous_good': None, 'pending': None,
                      'bootargs': 'root=PARTUUID=abcd-02 rootwait console=ttyS0,115200n8',
                      'health': self.baseline, 'generations': {'legacy-6.18.55': {
                          'legacy': True, 'ready': True, 'release': '6.18.55', 'abi': ABI,
                          'kernel_sha256': self.original, 'modules': self.modules}}}
        self.manager.save(self.state)
        (self.manager.policy / 'protected').write_text('')
        self.database({'kernel': ABI, 'kmod-nic': '6.18.55-r1'})

    def run_command(self, args):
        self.calls.append(args)
        if args[:2] == ['uname', '-r']:
            return self.running
        if args[0] == 'blkid':
            return '1234-ABCD'
        if args[0] == 'grub-editenv':
            for item in args[3:]:
                key, value = item.split('=', 1)
                self.environment[key] = value
        if args[0] == 'ubus':
            return json.dumps({'interface': [{'interface': 'lan', 'up': True,
                                              'l3_device': 'br-lan', 'ipv4-address': [{'address': '192.0.2.1'}]},
                                              {'interface': 'wan', 'up': True}]})
        if args[0] == 'ip':
            return 'default via 192.0.2.1'
        return ''

    def database(self, packages):
        (self.root / 'usr/lib/apk/db/installed').write_text('\n\n'.join(
            f'P:{name}\nV:{version}\nC:Q1testchecksum' for name, version in packages.items()) + '\n\n')

    def candidate(self, generation=GEN, abi=ABI):
        metadata = self.root / 'usr/lib/openwrt-kernel' / generation
        (metadata / 'kmods').mkdir(parents=True)
        modules = self.root / 'usr/lib/modules' / generation
        modules.mkdir(parents=True)
        (modules / 'nic.ko').write_bytes(('network driver ' + generation).encode())
        (metadata / 'vmlinuz').write_bytes(('candidate ' + generation).encode())
        (metadata / 'config').write_text('CONFIG_BLK_DEV_INITRD=y\n')
        K.json_write(metadata / 'image.json', {
            'schema': 1, 'generation': generation, 'release': generation,
            'abi': abi, 'sequence': 1, 'package': 'linux-image-' + generation,
            'version': abi, 'files': {}, 'kernel_sha256': K.sha256(metadata / 'vmlinuz')})
        K.json_write(metadata / 'kmods/kmod-nic.json', {'name': 'kmod-nic',
            'release': generation, 'abi': abi,
            'files': {str((modules / 'nic.ko').relative_to(self.root)):
                      {'sha256': K.sha256(modules / 'nic.ko')}}})
        K.json_write(self.root / 'usr/share/openwrt-kernel/selected.json',
                     {'generation': generation, 'abi': abi, 'sequence': 1})
        self.database({'kernel': abi, 'kmod-nic': '6.18.55.1-r1',
                       'linux-image-' + generation: abi,
                       'kmod-nic-' + generation: '6.18.55.1-r1'})

    def activate(self):
        def bootstrap(name, path):
            K.atomic(path, gzip.compress(b'bootstrap for ' + name.encode(), mtime=0), 0o644)
        with patch.object(self.manager, 'bootstrap', side_effect=bootstrap):
            return self.manager.activate()

    def generation(self, name, known=False, previous=False):
        metadata = self.root / 'usr/lib/openwrt-kernel' / name
        (metadata / 'kmods').mkdir(parents=True, exist_ok=True)
        (metadata / 'config').write_text('CONFIG_BLK_DEV_INITRD=y\n')
        (metadata / 'vmlinuz').write_bytes(('kernel ' + name).encode())
        modules = self.root / 'usr/lib/modules' / name
        modules.mkdir(parents=True, exist_ok=True)
        (modules / 'nic.ko').write_bytes(('module ' + name).encode())
        boot = self.root / 'boot/kernels' / name
        boot.mkdir(parents=True, exist_ok=True)
        (boot / 'vmlinuz').write_bytes(('kernel ' + name).encode())
        (boot / 'initramfs.gz').write_bytes(('initramfs ' + name).encode())
        files = {str(path.relative_to(self.root)): {'sha256': K.sha256(path)}
                 for path in sorted(metadata.rglob('*')) if path.is_file()}
        files[str((modules / 'nic.ko').relative_to(self.root))] = {
            'sha256': K.sha256(modules / 'nic.ko')}
        state = self.manager.state()
        state['generations'][name] = {
            'legacy': False, 'ready': True, 'release': name, 'abi': ABI,
            'package': 'linux-image-' + name, 'version': ABI,
            'kernel_sha256': K.sha256(metadata / 'vmlinuz'),
            'files': files, 'boot_files': K.inventory(boot)}
        if known:
            state['known_good'] = name
            state['previous_good'] = name
        if previous:
            state['previous_good'] = name
        self.manager.save(state)
        return state

    def test_bad_boot_mount_refuses_without_writes(self):
        (self.root / 'proc/self/mountinfo').write_text('')
        with self.assertRaisesRegex(K.KernelError, 'not mounted'):
            self.manager.check()
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

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

    def test_wrong_abi_cannot_activate(self):
        self.candidate()
        manifest = self.root / 'usr/lib/openwrt-kernel' / GEN / 'kmods/kmod-nic.json'
        data = json.loads(manifest.read_text()); data['abi'] = ABI.replace('a', 'b')
        K.json_write(manifest, data)
        with self.assertRaisesRegex(K.KernelError, 'ABI'):
            self.activate()
        self.assertNotIn('next_entry', self.environment)

    def test_corrupt_module_cannot_activate(self):
        self.candidate()
        (self.root / 'usr/lib/modules' / GEN / 'nic.ko').write_bytes(b'wrong module')
        with self.assertRaisesRegex(K.KernelError, 'changed generation'):
            self.activate()
        self.assertNotIn('next_entry', self.environment)

    def test_missing_module_rejected_before_transaction(self):
        txn = self.root / 'run/txn'
        txn.write_text(f'-\t-\tlinux-image-{GEN}\t{ABI}\t0\n')
        before = (self.manager.policy / 'state.json').read_bytes()
        with self.assertRaisesRegex(K.KernelError, 'lacks matching payload'):
            self.manager.transaction('apk-pre', txn, '0', 'live', '0')
        self.assertEqual(before, (self.manager.policy / 'state.json').read_bytes())

    def test_failed_apk_transaction_never_arms_trial(self):
        txn = self.root / 'run/txn'
        txn.write_text(f'-\t-\tlinux-image-{GEN}\t{ABI}\t0\n')
        with self.assertRaisesRegex(K.KernelError, 'transaction failed'):
            self.manager.transaction('apk-post', txn, '1', 'live', '0')
        self.assertNotIn('next_entry', self.environment)

    def test_disabled_hooks_refused_even_for_simulation(self):
        txn = self.root / 'run/txn'
        txn.write_text(f'-\t-\tlinux-image-{GEN}\t{ABI}\t0\n')
        with self.assertRaisesRegex(K.KernelError, 'requires scripts'):
            self.manager.transaction('apk-pre', txn, '0', 'simulate', '1')

    def test_trial_keeps_original_and_only_promotes_after_health(self):
        self.candidate()
        state = self.activate()
        self.assertEqual(self.environment['saved_entry'], 'owrt-rescue')
        self.assertEqual(self.environment['next_entry'], 'owrt-' + GEN)
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)
        self.assertEqual(K.inventory(self.root / 'usr/lib/modules/6.18.55'), self.modules)
        self.running = GEN
        with patch.object(self.manager, 'health', side_effect=K.KernelError('LAN unhealthy')):
            with self.assertRaisesRegex(K.KernelError, 'LAN unhealthy'):
                self.manager.confirm(duration=0)
        self.assertEqual(self.environment['saved_entry'], 'owrt-rescue')
        self.manager.confirm(duration=0)
        self.assertEqual(self.environment['saved_entry'], 'owrt-' + GEN)
        self.assertIsNone(self.manager.state()['pending'])
        self.assertTrue((self.root / 'boot/kernels' / GEN / 'vmlinuz').exists())

    def test_protected_removal_refused(self):
        with self.assertRaisesRegex(K.KernelError, 'Refusing to remove'):
            self.manager.remove('legacy-6.18.55')

    def test_required_builtin_feature_cannot_disappear(self):
        self.candidate()
        state = self.manager.state()
        state['required_config'] = ['CONFIG_KVM']
        self.manager.save(state)
        with self.assertRaisesRegex(K.KernelError, 'CONFIG_KVM'):
            self.activate()
        self.assertNotIn('next_entry', self.environment)

    def test_interruption_before_grub_publish_is_retryable(self):
        self.candidate()
        original_atomic = K.atomic
        def interrupted(path, *args, **kwargs):
            if Path(path).name == 'openwrt.cfg':
                raise OSError('simulated power loss')
            return original_atomic(path, *args, **kwargs)
        with patch.object(K, 'atomic', side_effect=interrupted):
            with self.assertRaisesRegex(OSError, 'simulated power loss'):
                self.activate()
        self.assertEqual(self.environment['saved_entry'], 'owrt-rescue')
        self.assertNotIn('next_entry', self.environment)
        self.activate()
        self.assertEqual(self.environment['next_entry'], 'owrt-' + GEN)

    def test_cancel_trial_keeps_last_confirmed_kernel_as_default(self):
        self.candidate()
        self.activate()
        self.manager.rollback()
        self.assertEqual(self.environment['saved_entry'], 'owrt-rescue')
        self.assertIsNone(self.manager.state()['pending'])
        with self.assertRaisesRegex(K.KernelError, 'rejected'):
            self.activate()

    def test_firmware_snapshot_survives_shared_firmware_update(self):
        firmware = self.root / 'usr/lib/firmware'; firmware.mkdir()
        (firmware / 'nic.bin').write_bytes(b'known good firmware')
        destination = self.root / 'usr/lib/openwrt-kernel' / GEN
        destination.mkdir(parents=True)
        snapshot = self.manager.freeze_firmware(GEN)
        (firmware / 'nic.bin').write_bytes(b'replacement firmware')
        K.verify_files(self.root, snapshot)
        self.assertEqual((destination / 'firmware/nic.bin').read_bytes(), b'known good firmware')

    def test_space_failure_never_prunes_fallback(self):
        self.candidate()
        with patch('shutil.disk_usage', return_value=shutil._ntuple_diskusage(100, 99, 1)):
            with self.assertRaisesRegex(K.KernelError, 'Insufficient boot space'):
                self.activate()
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_retention_keeps_trial_and_fallback(self):
        first = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'
        fallback = '6.18.55-owrt-' + 'c' * 32 + '-r1-g3'
        extra = '6.18.55-owrt-' + 'd' * 32 + '-r1-g4'
        self.generation(first, known=True)
        self.generation(fallback, previous=True)
        self.generation(extra)
        self.running = first
        keep = self.manager.retain(self.manager.state(), candidate=GEN)
        self.assertEqual(keep[:2], [GEN, first])
        self.assertTrue((self.root / 'boot/kernels' / first).is_dir())
        self.assertFalse((self.root / 'boot/kernels' / fallback).exists())
        self.assertFalse((self.root / 'boot/kernels' / extra).exists())
        state = self.manager.state()
        self.assertFalse(state['generations'][fallback]['ready'])
        self.assertFalse(state['generations'][extra]['ready'])
        self.assertEqual(state['previous_good'], first)
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)
        cfg = (self.root / 'boot/grub/openwrt.cfg').read_text()
        self.assertIn(first, cfg)
        self.assertNotIn(fallback, cfg)
        self.assertNotIn(extra, cfg)

    def test_retention_sweeps_orphan_boot_directory(self):
        first = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'
        self.generation(first, known=True)
        self.running = first
        orphan = self.root / 'boot/kernels' / ('6.18.55-owrt-' + 'e' * 32 + '-r1-g5')
        orphan.mkdir(parents=True)
        (orphan / 'vmlinuz').write_bytes(b'orphan')
        self.manager.retain(self.manager.state())
        self.assertFalse(orphan.exists())
        self.assertTrue((self.root / 'boot/kernels' / first).is_dir())
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_activate_prunes_previous_good_before_space_check(self):
        first = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'
        fallback = '6.18.55-owrt-' + 'c' * 32 + '-r1-g3'
        self.generation(first, known=True)
        self.generation(fallback, previous=True)
        self.running = first
        self.candidate()
        with patch('shutil.disk_usage', return_value=shutil._ntuple_diskusage(100, 99, 1)):
            with self.assertRaisesRegex(K.KernelError, 'Insufficient boot space'):
                self.activate()
        self.assertTrue((self.root / 'boot/kernels' / first).is_dir())
        self.assertFalse((self.root / 'boot/kernels' / fallback).exists())
        self.assertFalse((self.root / 'boot/kernels' / GEN).exists())
        state = self.manager.state()
        self.assertFalse(state['generations'][fallback]['ready'])
        self.assertEqual(state['previous_good'], first)
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_rollback_prunes_rejected_trial(self):
        self.candidate()
        self.activate()
        self.assertTrue((self.root / 'boot/kernels' / GEN).is_dir())
        self.running = GEN
        self.manager.rollback()
        self.assertFalse((self.root / 'boot/kernels' / GEN).exists())
        state = self.manager.state()
        self.assertFalse(state['generations'][GEN]['ready'])
        self.assertTrue(state['generations'][GEN]['failed'])
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_running_generation_is_never_pruned(self):
        first = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'
        running = '6.18.55-owrt-' + 'c' * 32 + '-r1-g3'
        extra = '6.18.55-owrt-' + 'd' * 32 + '-r1-g4'
        self.generation(first, known=True)
        self.generation(running)
        self.generation(extra)
        self.running = running
        keep = self.manager.retain(self.manager.state())
        self.assertIn(running, keep)
        self.assertTrue((self.root / 'boot/kernels' / running).is_dir())
        self.assertTrue((self.root / 'boot/kernels' / first).is_dir())
        self.assertFalse((self.root / 'boot/kernels' / extra).exists())

    def test_confirmation_retains_new_and_old(self):
        first = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'
        self.generation(first, known=True)
        self.running = first
        self.candidate()
        self.activate()
        self.running = GEN
        self.manager.confirm(duration=0)
        state = self.manager.state()
        self.assertEqual(state['known_good'], GEN)
        self.assertEqual(state['previous_good'], first)
        remaining = {path.name for path in (self.root / 'boot/kernels').iterdir()
                     if path.is_dir()}
        self.assertEqual(remaining, {first, GEN})
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_retention_preserves_legacy_previous_good(self):
        first = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'
        extra = '6.18.55-owrt-' + 'd' * 32 + '-r1-g4'
        self.generation(first, known=True)
        self.generation(extra)
        state = self.manager.state()
        state['previous_good'] = state['rescue']
        self.manager.save(state)
        self.running = first
        self.manager.retain(self.manager.state())
        state = self.manager.state()
        self.assertEqual(state['previous_good'], state['rescue'])
        self.assertFalse(state['generations'][extra]['ready'])
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_simulation_never_prunes(self):
        first = '6.18.55-owrt-' + 'b' * 32 + '-r1-g2'
        fallback = '6.18.55-owrt-' + 'c' * 32 + '-r1-g3'
        extra = '6.18.55-owrt-' + 'd' * 32 + '-r1-g4'
        self.generation(first, known=True)
        self.generation(fallback, previous=True)
        self.generation(extra)
        self.running = first
        txn = self.root / 'run/txn'
        txn.write_text(f'kernel\t{ABI}\tkernel\t{ABI}\t1\n')
        self.manager.transaction('apk-pre', txn, '0', 'simulate', '0')
        self.assertTrue((self.root / 'boot/kernels' / extra).is_dir())
        self.assertEqual(self.manager.state()['previous_good'], fallback)
        self.manager.transaction('apk-pre', txn, '0', 'live', '0')
        self.assertFalse((self.root / 'boot/kernels' / extra).exists())
        self.assertEqual(self.manager.state()['previous_good'], fallback)

    def test_finish_remove_failure_keeps_withdrawn_without_payload(self):
        extra = '6.18.55-owrt-' + 'd' * 32 + '-r1-g4'
        self.generation(extra)
        self.manager.remove(extra)
        shutil.rmtree(self.root / 'boot/kernels' / extra)
        self.manager.finish_remove(extra, False)
        state = self.manager.state()
        self.assertFalse(state['generations'][extra]['ready'])
        cfg = (self.root / 'boot/grub/openwrt.cfg').read_text()
        self.assertNotIn(extra, cfg)

    def test_unrelated_userspace_transaction_does_not_need_boot_mount(self):
        (self.root / 'proc/self/mountinfo').write_text('')
        txn = self.root / 'run/txn'; txn.write_text('app\t1-r1\tapp\t1-r2\t0\n')
        self.manager.transaction('apk-pre', txn, '0', 'live', '0')

    def test_adoption_replaces_only_kernel_pin_and_enrolls_tracker(self):
        world = self.root / 'etc/apk/world'
        world.parent.mkdir(parents=True)
        world.write_text('base-files=1-r1\nkernel=' + ABI + '\nlibc=2.42-r1\nkmod-nic\n')
        state = self.manager.state()
        state['phase'] = 'adopting'
        with patch.object(self.manager, 'install_grub_modules'), \
                patch.object(self.manager, 'dispatcher'), patch.object(self.manager, 'prepare'):
            self.manager.finish_migrate(state)
        self.assertEqual(world.read_text(),
            'base-files=1-r1\nkernel\nlibc=2.42-r1\nkmod-nic\nlinux-image-openwrt\n')

    def test_additional_payload_to_confirmed_generation_is_protected(self):
        self.candidate()
        self.activate()
        self.running = GEN
        self.manager.confirm(duration=0)
        records = {name: entry['V'] for name, entry in self.manager.installed().items()}
        records['kmod-extra-' + GEN] = '1000.1.6.18.55-r1'
        self.database(records)
        with patch.object(self.manager, 'prepare') as prepare:
            self.manager.activate()
        self.assertIn('kmod-extra-' + GEN + '><Q1testchecksum',
                      (self.manager.policy / 'protected').read_text())
        prepare.assert_called_once()
        self.assertIsNone(self.manager.state()['pending'])

    def test_fresh_image_prepares_matching_autoload_before_adoption(self):
        self.candidate()
        (self.manager.policy / 'state.json').unlink()
        self.running = GEN
        rules = self.root / 'usr/lib/modules' / GEN / 'openwrt/modules.d'
        rules.mkdir(parents=True)
        (rules / '10-nic').write_text('nic\n')
        self.manager.prepare()
        self.assertEqual((self.root / 'run/openwrt-kernel/modules.d/10-nic').read_text(), 'nic\n')

    def test_withdrawn_generation_removal_preserves_rescue(self):
        self.candidate()
        self.activate()
        self.manager.rollback()
        packages = self.manager.remove(GEN)
        self.assertIn('linux-image-' + GEN, packages)
        self.assertFalse(self.manager.state()['generations'][GEN]['ready'])
        self.database({'kernel': ABI, 'kmod-nic': '1000.1.6.18.55-r1'})
        self.manager.finish_remove(GEN, True)
        self.assertFalse((self.root / 'boot/kernels' / GEN).exists())
        self.assertFalse((self.root / 'usr/lib/modules' / GEN).exists())
        self.assertFalse((self.root / 'usr/lib/openwrt-kernel' / GEN).exists())
        self.assertEqual(K.sha256(self.root / 'boot/vmlinuz'), self.original)

    def test_fresh_image_existing_generation_does_not_become_a_redundant_trial(self):
        self.candidate()
        metadata = self.root / 'usr/lib/openwrt-kernel' / GEN
        (metadata / 'vmlinuz').write_bytes((self.root / 'boot/vmlinuz').read_bytes())
        image = json.loads((metadata / 'image.json').read_text())
        image['kernel_sha256'] = self.original; K.json_write(metadata / 'image.json', image)
        state = self.manager.state(); rescue = state['generations'][state['rescue']]
        rescue['release'] = GEN
        modules = self.root / 'usr/lib/modules' / GEN
        (modules / 'modules.dep').write_text('original generated index')
        rescue['modules'] = K.inventory(modules); self.manager.save(state)
        (modules / 'modules.dep').write_text('updated generated index')
        rules = modules / 'openwrt/modules.d'; rules.mkdir(parents=True)
        (rules / '10-nic').write_text('nic\n')
        self.running = GEN
        state = self.manager.activate()
        self.assertIsNone(state['pending'])
        self.assertEqual(state['known_good'], state['rescue'])
        self.assertNotIn('modules.dep', state['generations'][state['rescue']]['modules'])
        self.assertEqual((self.root / 'run/openwrt-kernel/modules.d/10-nic').read_text(), 'nic\n')


class PackageTests(unittest.TestCase):
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

    def split(self, name, version, generation=GEN, sequence=1, module_release=None):
        root = self.work / (name + '-g' + str(sequence))
        (root / 'usr/lib/modules' / generation).mkdir(parents=True)
        (root / 'usr/lib/apk/packages').mkdir(parents=True, exist_ok=True)
        config = self.work / 'linux/.config'; config.parent.mkdir(exist_ok=True)
        (config.parent / 'include/config').mkdir(parents=True, exist_ok=True)
        (config.parent / 'include/config/kernel.release').write_text(generation)
        config.write_text('CONFIG_BLK_DEV_INITRD=y\n')
        kernel = self.work / 'bzImage'; kernel.write_bytes(b'kernel image fixture')
        if name == 'kernel':
            (root / 'usr/lib/modules' / generation / 'modules.builtin').write_text('kernel/kvm.ko\n')
        else:
            (root / 'usr/lib/modules' / generation / 'nic.ko').write_bytes(
                b'module fixture\x00vermagic=' + (module_release or generation).encode() + b' SMP\x00')
            (root / 'etc/modules.d').mkdir(parents=True)
            (root / 'etc/modules.d/10-nic').write_text('nic\n')
        P.split(argparse.Namespace(root=root, name=name, version=version, abi=ABI,
            generation=generation, sequence=sequence, depends='kernel (=' + ABI + ')',
            kernel=kernel, config=config, apk=str(APK), output=self.output, key=str(self.key)))
        return root

    def test_signed_image_and_module_payloads_coinstall_without_global_provides(self):
        root = self.split('kernel', ABI)
        wrapper = self.split('kmod-nic', '6.18.55.1-r1')
        self.assertFalse((root / 'usr/lib/modules' / GEN).exists())
        self.assertFalse((wrapper / 'etc/modules.d').exists())
        files = sorted(self.output.glob('*.apk'))
        self.assertEqual(len(files), 3)
        subprocess.run([str(APK), 'verify', '--keys-dir', str(self.work), *map(str, files)], check=True)
        metadata = [json.loads(subprocess.check_output([str(APK), 'adbdump', '--format', 'json', str(p)]))['info']
                    for p in files]
        module = next(m for m in metadata if m['name'].startswith('kmod-'))
        self.assertEqual(module['depends'], ['linux-image-' + GEN + '=' + ABI])
        self.assertNotIn('kernel', module.get('provides', []))
        for package in files:
            data = json.loads(subprocess.check_output([str(APK), 'adbdump', '--format', 'json', str(package)]))
            for directory in data['paths']:
                for entry in [directory, *directory.get('files', [])]:
                    acl = entry.get('acl', {})
                    self.assertEqual(acl.get('user', 'root'), 'root')
                    self.assertEqual(acl.get('group', 'root'), 'root')
                    self.assertFalse(acl.get('mode', 0) & 0o022)

    def test_same_linux_version_payloads_install_together(self):
        second = GEN[:-1] + '2'
        self.split('kernel', ABI)
        self.split('kmod-nic', '1000.1.6.18.55-r1')
        self.split('kernel', ABI, second, 2)
        self.split('kmod-nic', '1000.2.6.18.55-r1', second, 2)
        index = self.output / 'packages.adb'
        subprocess.run([str(APK), 'mkndx', '--keys-dir', str(self.work), '--sign-key', str(self.key),
                        '--output', str(index), *map(str, self.output.glob('*.apk'))], check=True)
        root = self.work / 'installed'
        root.mkdir()
        result = subprocess.run([str(APK), '--root', str(root), '--keys-dir', str(self.work),
                        '--repositories-file', '/dev/null', '--repository', str(index),
                        '--no-logfile', 'add', '--initdb', '--usermode', '--no-scripts',
                        'linux-image-' + GEN, 'linux-image-' + second,
                        'kmod-nic-' + GEN, 'kmod-nic-' + second], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        for release in (GEN, second):
            self.assertEqual((root / 'usr/lib/modules' / release / 'nic.ko').read_bytes(),
                             b'module fixture\x00vermagic=' + release.encode() + b' SMP\x00')

    def test_tracking_epoch_is_newer_than_legacy_external_module_version(self):
        comparison = subprocess.check_output([str(APK), 'version', '--test',
            '6.18.55.7.2-r5', '1000.1.6.18.55.7.2-r5'], text=True).strip()
        self.assertEqual(comparison, '<')

    def test_wrong_compiled_module_release_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Compiled module release'):
            self.split('kmod-nic', '1000.1.6.18.55-r1', module_release='6.18.55')
        self.assertFalse(list(self.output.glob('kmod-*.apk')))

    def test_release_bump_cannot_replace_payload_within_same_generation(self):
        self.split('kmod-nic', '1000.1.6.18.55-r1')
        with self.assertRaisesRegex(ValueError, 'Immutable generation version'):
            self.split('kmod-nic', '1000.1.6.18.55-r2')

    def test_publisher_rejects_writable_payload_before_publishing(self):
        self.split('kernel', ABI)
        root = self.work / 'unsafe'; root.mkdir(); root.chmod(0o777)
        (root / 'unsafe').write_bytes(b'fixture')
        output = self.output / ('kmod-unsafe-' + GEN + '-1-r1.apk')
        subprocess.run([str(APK), 'mkpkg', '--info', 'name:kmod-unsafe-' + GEN,
            '--info', 'version:1-r1', '--info', 'arch:x86_64',
            '--info', 'origin:kernel-generations', '--info', 'depends:linux-image-' + GEN + '=' + ABI,
            '--files', str(root), '--sign', str(self.key), '--output', str(output)], check=True)
        destination = self.work / 'publications'
        with self.assertRaisesRegex(ValueError, 'Unsafe kernel payload'):
            F.publish(self.output, destination, APK, self.key, self.work)
        self.assertFalse((destination / 'public/kernel-upgrades').exists())

    def test_ordinary_upgrade_accepts_new_generation_with_lower_sorting_abi(self):
        second = GEN.replace('a' * 32, '0' * 32)[:-1] + '2'
        second_abi = ABI.replace('a' * 32, '0' * 32)
        def packages(generation, abi, sequence):
            root = self.work / ('payload-' + str(sequence)); root.mkdir()
            image = 'linux-image-' + generation
            module = 'kmod-nic-' + generation
            version = f'1000.{sequence}.6.18.55-r1'
            for name, ver, deps in [('kernel', abi, []), (image, abi, []),
                    (module, version, [image + '=' + abi]),
                    ('kmod-nic', version, ['kernel=' + abi, module + '=' + version]),
                    ('linux-image-openwrt', f'1-r{sequence}', ['kernel=' + abi, image + '=' + abi])]:
                P.package(str(APK), str(self.key), root, self.output, name, ver, deps, 'fixture', '')
            return image, module
        index = self.output / 'packages.adb'
        def index_packages():
            subprocess.run([str(APK), 'mkndx', '--keys-dir', str(self.work), '--sign-key', str(self.key),
                            '--output', str(index), *map(str, self.output.glob('*.apk'))], check=True)
        old = packages(GEN, ABI, 1)
        index_packages()
        root = self.work / 'installed'; root.mkdir()
        command = [str(APK), '--root', str(root), '--keys-dir', str(self.work),
                   '--repositories-file', '/dev/null', '--repository', str(index),
                   '--no-logfile', '--no-cache', '--no-scripts']
        subprocess.run(command + ['add', '--initdb', '--usermode', 'kernel',
                       'kmod-nic', 'linux-image-openwrt', *old], check=True)
        packages(second, second_abi, 2)
        index_packages()
        result = subprocess.run(command + ['upgrade'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        database = (root / 'lib/apk/db/installed').read_text()
        self.assertIn('P:kernel\nV:' + second_abi, database)
        self.assertIn('P:linux-image-openwrt\nV:1-r2', database)
        self.assertIn('P:' + old[0] + '\n', database)

    def test_channel_publication_retains_old_snapshot_and_rejects_bad_abi(self):
        self.split('kernel', ABI)
        self.split('kmod-nic', '1000.1.6.18.55-r1')
        destination = self.work / 'publications'
        result = F.publish(self.output, destination, APK, self.key, self.work)
        self.assertEqual(result['images'], 1)
        active = destination / 'public/kernel-upgrades'
        previous = active.resolve()
        before = (active / 'packages.adb').read_bytes()
        badroot = self.work / 'bad'; badroot.mkdir()
        P.package(str(APK), str(self.key), badroot, self.output, 'kmod-bad-' + GEN, '1-r1',
                  ['linux-image-' + GEN + '=' + ABI.replace('a', 'b')], 'bad fixture', 'openwrt:test')
        with self.assertRaisesRegex(ValueError, 'ABI mismatch'):
            F.publish(self.output, destination, APK, self.key, self.work)
        self.assertEqual(active.resolve(), previous)
        self.assertEqual(before, (active / 'packages.adb').read_bytes())


if __name__ == '__main__':
    unittest.main(verbosity=2)
