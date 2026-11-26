#!/usr/bin/env python3
"""Host tests for optional installer components, preflight checks, TUI, and firstboot."""
import copy
import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
INSTALLER_DIR = ROOT / 'package/custom/openwrt-installer/files'
sys.path.insert(0, str(INSTALLER_DIR))


def load_module(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


core = load_module('core', INSTALLER_DIR / 'core.py')
apply = load_module('apply', INSTALLER_DIR / 'apply.py')
tui = load_module('tui', INSTALLER_DIR / 'tui.py')
builder = load_module('build_installer_components', ROOT / 'scripts/build-installer-components.py')

HASH = '$6$salt$' + 'a' * 86
CATALOG_CFG = json.loads((ROOT / 'configs/installer-components.json').read_text())


def sample_catalog(repo_index_sha256='0' * 64, base_sha256='1' * 64, repo_files=None):
    return {
        'format_version': 2,
        'version': 'SNAPSHOT',
        'kernel_release': '7.3.5-70-openwrt',
        'arch': 'x86_64',
        'base_package_count': 100,
        'base_packages_sha256': base_sha256,
        'repo_index_sha256': repo_index_sha256,
        'components': copy.deepcopy(CATALOG_CFG['components']),
        'repo_files': repo_files or {},
    }


def sample_answers(components=None, gnome_autostart=True):
    a = {
        'disk': '/dev/nvme0n1',
        'partitions': core.guided(400 * core.MIB),
        'network': {
            'wan_port': 'eth1',
            'lan_ports': ['eth0'],
            'lan': {'ipaddr': '192.168.1.1', 'netmask': '255.255.255.0', 'dhcp': True, 'start': 100, 'limit': 150},
            'wan': {'proto': 'dhcp'},
            'ipv6': True,
        },
        'firewall': {'masq': True, 'fullcone': False, 'lan_to_wan': True},
        'accounts': {
            'root_password_hash': HASH,
            'user': {'name': 'alice', 'password_hash': HASH, 'gnome_autostart': gnome_autostart},
        },
    }
    if components is not None:
        a['components'] = components
    return a


def sha256_bytes(data):
    return hashlib.sha256(data).hexdigest()


class InstallerComponentsTests(unittest.TestCase):
    def test_selection_defaults_and_empty(self):
        cat = sample_catalog()
        default_ids = [c['id'] for c in cat['components'] if c.get('default', True)]
        self.assertEqual(core.default_components(cat), default_ids)
        self.assertEqual(core.validate_components(None, cat), default_ids)
        self.assertEqual(core.validate_components([], cat), [])
        self.assertEqual(core.resolve_component_packages([], cat), [])

        # Omitted components in answers defaults to default components.
        a = core.validate_answers(sample_answers(components=None), catalog=cat)
        self.assertEqual(a['components'], default_ids)

        # Pure Plasma selection is valid and resolves Plasma packages without GNOME.
        self.assertEqual(core.validate_components(['plasma'], cat), ['plasma'])
        self.assertEqual(core.validate_components(['plasma', 'audio', 'ime', 'rdp', 'sunshine'], cat),
                         ['plasma', 'audio', 'ime', 'rdp', 'sunshine'])
        plasma_pkgs = core.resolve_component_packages(['plasma', 'audio', 'ime', 'rdp', 'virtualization'], cat)
        self.assertIn('openwrt-desktop-plasma-core', plasma_pkgs)
        self.assertIn('openwrt-desktop-plasma-rdp', plasma_pkgs)
        self.assertIn('openwrt-desktop-ime-plasma', plasma_pkgs)
        self.assertIn('plasma-pa', plasma_pkgs)
        self.assertIn('virt-manager', plasma_pkgs)
        self.assertNotIn('openwrt-desktop-core', plasma_pkgs)
        self.assertNotIn('openwrt-desktop-rdp', plasma_pkgs)

        # Empty components in answers is base-only and rejects gnome_autostart=True.
        with self.assertRaisesRegex(ValueError, 'GNOME autostart requires'):
            core.validate_answers(sample_answers(components=[], gnome_autostart=True), catalog=cat)
        a_base = core.validate_answers(sample_answers(components=[], gnome_autostart=False), catalog=cat)
        self.assertEqual(a_base['components'], [])

    def test_dependencies_and_unknown_components(self):
        cat = sample_catalog()
        with self.assertRaisesRegex(ValueError, 'Unknown component'):
            core.validate_components(['bogus'], cat)
        for bad in (['audio'], ['ime'], ['rdp'], ['flatpak'], ['appimage'], ['sunshine'], ['gnome', 'sunshine']):
            with self.subTest(bad=bad):
                with self.assertRaisesRegex(ValueError, 'requires:'):
                    core.validate_components(bad, cat)

        # Valid combinations.
        self.assertEqual(core.validate_components(['gnome'], cat), ['gnome'])
        self.assertEqual(core.validate_components(['gnome', 'audio', 'sunshine'], cat), ['gnome', 'audio', 'sunshine'])
        self.assertEqual(core.validate_components(['containers', 'virtualization'], cat), ['virtualization', 'containers'])

    def test_conditional_virt_manager(self):
        cat = sample_catalog()
        headless = core.resolve_component_packages(['virtualization', 'containers'], cat)
        self.assertIn('libvirt-daemon', headless)
        self.assertIn('qemu-x86_64-softmmu', headless)
        self.assertIn('podman', headless)
        self.assertNotIn('virt-manager', headless)
        self.assertNotIn('openwrt-desktop-core', headless)

        with_gnome = core.resolve_component_packages(['gnome', 'virtualization'], cat)
        self.assertIn('virt-manager', with_gnome)
        self.assertIn('openwrt-desktop-core', with_gnome)
        self.assertNotIn('openwrt-desktop-rdp', with_gnome)

    def test_overlay_space_calculation(self):
        self.assertEqual(core.min_overlay_mib(0), 2048)
        # 2000 MiB unpacked -> 2300 MiB with 15% overhead + 1024 MiB reserve = 3324 MiB
        need = core.min_overlay_mib(2000 * core.MIB)
        self.assertGreaterEqual(need, 3324)
        parts = core.guided(400 * core.MIB)
        # 4096 MiB disk cannot fit 512 boot + 1024 rom + 3324 overlay.
        with self.assertRaisesRegex(ValueError, 'Partition 3 requires at least'):
            core.layout(parts, 4096 * core.MIB, 400 * core.MIB, min_overlay=need)
        plan = core.layout(parts, 8192 * core.MIB, 400 * core.MIB, min_overlay=need)
        self.assertGreaterEqual(plan['partitions'][2]['size_mib'], need)

    def test_tui_components_preserves_selection_on_error(self):
        cat = sample_catalog()
        a = {'components': ['gnome', 'audio', 'sunshine']}
        calls = []

        def fake_dialog(kind, text, items=(), default=None):
            calls.append((kind, text, list(items)))
            if kind == 'checklist':
                # First submit: user unchecks gnome, leaving audio+sunshine -> invalid.
                # Second submit: user unchecks audio+sunshine too -> base-only valid.
                checklist_count = sum(1 for c in calls if c[0] == 'checklist')
                if checklist_count == 1:
                    return '"audio" "sunshine"'
                return ''
            return ''

        with patch.object(tui, 'dialog', side_effect=fake_dialog):
            tui.components(a, cat)
        self.assertEqual(a['components'], [])
        # Second checklist must NOT have silently re-checked gnome!
        second_checklist = [c[2] for c in calls if c[0] == 'checklist'][1]
        state = {second_checklist[i]: second_checklist[i + 2] for i in range(0, len(second_checklist), 3)}
        self.assertEqual(state['gnome'], 'OFF')
        self.assertEqual(state['audio'], 'ON')
        self.assertEqual(state['sunshine'], 'ON')

    def test_catalog_verification_and_preflight_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            payload = Path(tmp) / 'install'
            comp_dir = payload / 'components'
            repo_dir = comp_dir / 'repo'
            keys_dir = comp_dir / 'keys'
            repo_dir.mkdir(parents=True)
            keys_dir.mkdir(parents=True)

            index_path = repo_dir / 'packages.adb'
            index_path.write_bytes(b'fake-index')
            index_hash = sha256_bytes(b'fake-index')

            apk_path = repo_dir / 'openwrt-desktop-core-36.apk'
            apk_path.write_bytes(b'fake-apk')
            apk_hash = sha256_bytes(b'fake-apk')

            (keys_dir / 'public-key.pem').write_text('-----BEGIN PUBLIC KEY-----\nTEST\n-----END PUBLIC KEY-----\n')

            base_root = Path(tmp) / 'rom'
            (base_root / 'lib/apk/db').mkdir(parents=True)
            (base_root / 'etc/apk/keys').mkdir(parents=True)
            (base_root / 'lib/apk/db/installed').write_text('P:base-files\nV:1\nI:104857600\n\n')
            (base_root / 'etc/apk/arch').write_text('x86_64\n')
            (base_root / 'etc/apk/world').write_text('base-files\n')
            (base_root / 'etc/apk/keys/public-key.pem').write_text(
                '-----BEGIN PUBLIC KEY-----\nTRUSTED\n-----END PUBLIC KEY-----\n'
            )
            base_hash = apply.read_installed_digest(base_root)

            cat = sample_catalog(
                repo_index_sha256=index_hash,
                base_sha256=base_hash,
                repo_files={'openwrt-desktop-core-36.apk': {'name': 'openwrt-desktop-core', 'version': '36', 'size': 8, 'sha256': apk_hash}},
            )
            comp_json = comp_dir / 'components.json'
            comp_json.write_text(json.dumps(cat))
            manifest = {
                'format_version': 2,
                'version': 'SNAPSHOT',
                'kernel_release': '7.3.5-70-openwrt',
                'squashfs_size': 1024,
                'squashfs_sha256': '2' * 64,
                'root_partuuid': 'PARTUUID=00000000-02',
                'components_manifest': 'components/components.json',
                'components_sha256': sha256_bytes(comp_json.read_bytes()),
                'repo_index_sha256': index_hash,
            }

            # Valid load.
            loaded = apply.load_components_catalog(manifest, payload)
            self.assertEqual(loaded['format_version'], 2)

            # Unsupported format version.
            bad_fmt = dict(manifest, format_version=99)
            with self.assertRaisesRegex(ValueError, 'Unsupported installer payload format'):
                apply.load_components_catalog(bad_fmt, payload)

            # Version mismatch.
            bad_ver = dict(manifest, kernel_release='7.3.5-1-openwrt')
            with self.assertRaisesRegex(ValueError, 'does not match installer manifest'):
                apply.load_components_catalog(bad_ver, payload)

            # Private key embedded -> refused.
            priv = keys_dir / 'private-key.pem'
            priv.write_text('secret')
            with self.assertRaisesRegex(ValueError, 'private key'):
                apply.load_components_catalog(manifest, payload)
            priv.unlink()

            # Base root digest mismatch.
            bad_cat = dict(loaded, base_packages_sha256='f' * 64)
            with self.assertRaisesRegex(ValueError, 'Base rootfs package set'):
                apply.preflight_components(['gnome'], bad_cat, payload, base_root=base_root)

            # Realistic apk-tools 3.x simulate + query output.
            sim_out = '(1/1) Installing openwrt-desktop-core (36)\nOK: 228.0 MiB in 2 packages\n'
            query_out = json.dumps([{'name': 'openwrt-desktop-core', 'version': '36', 'installed-size': 128 * core.MIB}])
            recorded_cmds = []

            def fake_apk(*args, **kwargs):
                recorded_cmds.append(args)
                if 'query' in args:
                    return query_out
                return sim_out

            # Corrupt APK fails preflight before wipe.
            apk_path.write_bytes(b'corrupted!')
            with patch.object(apply, 'run', side_effect=fake_apk):
                with self.assertRaisesRegex(ValueError, 'Corrupt package'):
                    apply.preflight_components(['gnome'], loaded, payload, base_root=base_root)

            # Missing APK fails preflight before wipe.
            apk_path.unlink()
            with patch.object(apply, 'run', side_effect=fake_apk):
                with self.assertRaisesRegex(ValueError, 'missing from offline repository'):
                    apply.preflight_components(['gnome'], loaded, payload, base_root=base_root)

            # Restore APK -> preflight succeeds, uses /rom/etc/apk/keys (not /install/components/keys), and reads exact size.
            apk_path.write_bytes(b'fake-apk')
            recorded_cmds.clear()
            with patch.object(apply, 'run', side_effect=fake_apk):
                plan = apply.preflight_components(['gnome'], loaded, payload, base_root=base_root)
            self.assertEqual(plan['install_count'], 1)
            self.assertEqual(plan['installed_bytes'], 128 * core.MIB)
            self.assertEqual(plan['min_overlay_mib'], 2048)
            self.assertEqual(len(recorded_cmds), 2)
            expected_keys = str(base_root / 'etc/apk/keys')
            for cmd in recorded_cmds:
                idx = cmd.index('--keys-dir')
                self.assertEqual(cmd[idx + 1], expected_keys)

            # install_components also uses base_root/etc/apk/keys.
            recorded_cmds.clear()
            with patch.object(apply, 'run', side_effect=fake_apk):
                apply.install_components(Path(tmp) / 'target', plan, payload, base_root=base_root)
            self.assertEqual(len(recorded_cmds), 1)
            idx = recorded_cmds[0].index('--keys-dir')
            self.assertEqual(recorded_cmds[0][idx + 1], expected_keys)

            # Missing trusted base keys fails even if /install/components/keys has a key.
            shutil.rmtree(base_root / 'etc/apk/keys')
            with self.assertRaisesRegex(ValueError, 'Trusted base APK keys directory missing'):
                apply.preflight_components(['gnome'], loaded, payload, base_root=base_root)
            with self.assertRaisesRegex(ValueError, 'Trusted base APK keys directory missing'):
                apply.install_components(Path(tmp) / 'target', plan, payload, base_root=base_root)

    def test_parse_apk_simulate_real_apk3_ok_summary(self):
        # Real apk-tools 3.0.5 summary format (OK: <total> <unit> in <N> packages).
        out = '\n'.join([
            '(1/2) Installing libwinpr3 (3.33.1-r2)',
            '(2/2) Installing winpr-hash (3.33.1-r2)',
            'OK: 2830.5 MiB in 1381 packages',
        ])
        base_bytes = 1295915209  # 1235.88 MiB
        solved, delta = apply.parse_apk_simulate(out, base_installed_bytes=base_bytes)
        self.assertEqual(solved, [('libwinpr3', '3.33.1-r2'), ('winpr-hash', '3.33.1-r2')])
        # 2830.5 MiB - 1235.88 MiB ~= 1594.6 MiB -> min_overlay_mib == 2858 MiB.
        self.assertEqual(core.min_overlay_mib(delta), 2858)
        # 4.5 GiB disk gives 3070 MiB overlay with guided layout -> must be accepted.
        parts = core.guided(369 * core.MIB)
        plan = core.layout(parts, int(4.5 * 1024 * core.MIB), 369 * core.MIB, min_overlay=core.min_overlay_mib(delta))
        self.assertEqual(plan['partitions'][2]['size_mib'], 3070)

    def test_real_apk_iso_preflight_size_and_trusted_keys(self):
        apk = ROOT / 'staging_dir/host/bin/apk'
        unsquash = ROOT / 'staging_dir/host/bin/unsquashfs4'
        iso = ROOT / 'bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso'
        if not (apk.is_file() and unsquash.is_file() and iso.is_file() and shutil.which('xorriso') and shutil.which('openssl')):
            self.skipTest('Built installer ISO or host apk/unsquashfs4/xorriso/openssl not available')
        with tempfile.TemporaryDirectory(prefix='test-real-apk-iso-') as tmp:
            t = Path(tmp)
            subprocess.run(
                ['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', '/install', str(t / 'install')],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            manifest = json.loads((t / 'install/manifest.json').read_text())
            catalog = apply.load_components_catalog(manifest, t / 'install')
            with iso.open('rb') as f:
                mbr = f.read(512)
            part3_lba = struct.unpack_from('<I', mbr, 446 + 2 * 16 + 8)[0]
            sq_path = t / 'root.squashfs'
            with iso.open('rb') as f:
                f.seek(part3_lba * 512)
                sq_path.write_bytes(f.read(manifest['squashfs_size']))
            subprocess.run(
                [str(unsquash), '-d', str(t / 'rom'), str(sq_path), 'usr/lib/apk/db/installed', 'etc/apk'],
                check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

            # Real APK preflight for all 9 components must use exact installed-size (not compressed*3).
            plan = apply.preflight_components(None, catalog, t / 'install', base_root=t / 'rom', apk_bin=apk)
            compressed_total = sum(int(v['size']) for v in catalog['repo_files'].values())
            self.assertGreater(plan['install_count'], 0)
            self.assertLess(plan['installed_bytes'], compressed_total * 3)
            # 4.5 GiB disk (3070 MiB overlay) must pass with actual unpacked delta.
            parts = core.guided(manifest['squashfs_size'])
            disk_plan = core.layout(
                parts, int(4.5 * 1024 * core.MIB), manifest['squashfs_size'],
                min_overlay=plan['min_overlay_mib'],
            )
            self.assertEqual(disk_plan['partitions'][2]['size_mib'], 3070)

            # Self-signed tampered offline repo (re-signed with rogue key placed in /install/components/keys)
            # MUST be rejected because verification trusts /rom/etc/apk/keys, not /install/components/keys.
            rogue_sec = t / 'rogue-sec.pem'
            rogue_pub = t / 'rogue-pub.pem'
            subprocess.run(['openssl', 'ecparam', '-name', 'prime256v1', '-genkey', '-noout', '-out', str(rogue_sec)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            subprocess.run(['openssl', 'ec', '-in', str(rogue_sec), '-pubout', '-out', str(rogue_pub)],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            comp_keys = t / 'install/components/keys'
            for p in comp_keys.glob('*.pem'):
                p.unlink()
            shutil.copyfile(rogue_pub, comp_keys / 'public-key.pem')
            repo_dir = t / 'install/components/repo'
            apks = sorted(p.name for p in repo_dir.glob('*.apk'))
            subprocess.run(
                [str(apk), 'mkndx', '--root', str(comp_keys), '--keys-dir', str(comp_keys),
                 '--allow-untrusted', '--sign', str(rogue_sec), '--output', str(repo_dir / 'packages.adb'), *apks],
                cwd=repo_dir, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            with self.assertRaises(RuntimeError):
                apply.preflight_components(['rdp', 'gnome'], catalog, t / 'install', base_root=t / 'rom', apk_bin=apk)
            with self.assertRaises(RuntimeError):
                apply.install_components(t / 'target', plan, t / 'install', base_root=t / 'rom', apk_bin=apk)

    def test_build_entry_signing_and_catalog_guards(self):
        # Kconfig and Makefile must require CONFIG_SIGNED_PACKAGES for INSTALLER_ISO_IMAGES.
        cfg_images = (ROOT / 'config/Config-images.in').read_text()
        iso_block = cfg_images.split('config INSTALLER_ISO_IMAGES', 1)[1].split('config ', 1)[0]
        self.assertIn('SIGNED_PACKAGES', iso_block)

        img_mk = (ROOT / 'target/linux/x86/image/Makefile').read_text()
        self.assertIn('CONFIG_INSTALLER_ISO_IMAGES requires CONFIG_SIGNED_PACKAGES=y', img_mk)
        installer_recipe = img_mk.split('define Build/installer-iso', 1)[1].split('endef', 1)[0]
        self.assertNotIn('--allow-untrusted', installer_recipe)
        self.assertIn('--sign-key $(BUILD_KEY_APK_SEC)', installer_recipe)

        # Builder CLI must reject missing --sign-key and must not accept --allow-untrusted.
        res_nosign = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/build-installer-components.py'),
             '--config', str(ROOT / 'configs/installer-components.json'),
             '--apk', 'apk', '--package-dir', '/tmp', '--keys-dir', '/tmp', '--public-key', '/tmp/pub.pem',
             '--version', 'SNAPSHOT', '--kernel-release', '7.3.5-71-openwrt',
             '--base-files-version', '1', '--libc-version', '1', '--kernel-version', '1',
             '--base-root-out', '/tmp/r', '--components-out', '/tmp/c'],
            text=True, capture_output=True,
        )
        self.assertNotEqual(res_nosign.returncode, 0)
        self.assertIn('--sign-key', res_nosign.stderr)

        res_untrusted = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/build-installer-components.py'),
             '--config', str(ROOT / 'configs/installer-components.json'),
             '--apk', 'apk', '--package-dir', '/tmp', '--keys-dir', '/tmp',
             '--public-key', '/tmp/pub.pem', '--sign-key', '/tmp/sec.pem',
             '--version', 'SNAPSHOT', '--kernel-release', '7.3.5-71-openwrt',
             '--base-files-version', '1', '--libc-version', '1', '--kernel-version', '1',
             '--base-root-out', '/tmp/r', '--components-out', '/tmp/c', '--allow-untrusted'],
            text=True, capture_output=True,
        )
        self.assertNotEqual(res_untrusted.returncode, 0)
        self.assertIn('unrecognized arguments: --allow-untrusted', res_untrusted.stderr)

        # Pure-router package subset must fail catalog availability check clearly.
        router_cfg = (ROOT / 'configs/x86-64-systemd-router.config').read_text()
        router_pkgs = {
            line[len('CONFIG_PACKAGE_'):-2]
            for line in router_cfg.splitlines()
            if line.startswith('CONFIG_PACKAGE_') and (line.endswith('=y') or line.endswith('=m'))
        }
        with self.assertRaises(RuntimeError) as ctx:
            builder.check_catalog_availability(router_pkgs, CATALOG_CFG['base'], CATALOG_CFG['components'])
        msg = str(ctx.exception)
        self.assertIn('configs/x86-64-systemd-desktop.config', msg)
        self.assertIn('samba4-server', msg)
        self.assertIn('luci-app-passwall', msg)
        self.assertIn('router-audit', msg)
        self.assertIn("component 'gnome'", msg)

        # Complete package set passes catalog availability check.
        full_pkgs = set(CATALOG_CFG['base']['packages']) | set(CATALOG_CFG['base']['required_packages'])
        for c in CATALOG_CFG['components']:
            full_pkgs.update(c.get('packages', []))
            for cond in c.get('conditional_packages', []):
                full_pkgs.update(cond.get('packages', []))
        builder.check_catalog_availability(full_pkgs, CATALOG_CFG['base'], CATALOG_CFG['components'])

    def test_preflight_failure_never_wipes_disk(self):
        a = sample_answers(components=['audio'], gnome_autostart=False)
        manifest = {'format_version': 2, 'squashfs_size': 1024, 'squashfs_sha256': 'a' * 64}
        with patch.object(apply, 'prepare', side_effect=ValueError('preflight failed')), \
                patch.object(apply, 'run') as mocked_run:
            with self.assertRaisesRegex(ValueError, 'preflight failed'):
                apply.install(a, manifest, Path('/nonexistent'))
        mocked_run.assert_not_called()

    def test_firstboot_component_handling(self):
        fb_src = (INSTALLER_DIR / 'firstboot').read_text()
        for case, fb_data, expected_cmds, expect_unlinked, fail_cmd in [
            ('gnome_autostart_and_audio',
             {'name': 'alice', 'password_hash': HASH, 'gnome_autostart': True, 'components': ['gnome', 'audio']},
             [['id', 'alice'], ['useradd', '-m', '-G', 'sudo', 'alice'], ['usermod', '-p', HASH, 'alice'],
              ['uci', 'set', 'desktop.main.session=gnome'], ['uci', 'commit', 'desktop'],
              ['desktop-setup', 'alice'], ['desktop-audio-setup', 'alice']],
             True, None),
            ('plasma_autostart_and_audio',
             {'name': 'alice', 'password_hash': HASH, 'desktop_session': 'plasma', 'desktop_autostart': True,
              'components': ['plasma', 'audio']},
             [['id', 'alice'], ['useradd', '-m', '-G', 'sudo', 'alice'], ['usermod', '-p', HASH, 'alice'],
              ['uci', 'set', 'desktop.main.session=plasma'], ['uci', 'commit', 'desktop'],
              ['desktop-setup', 'alice'], ['desktop-audio-setup', 'alice']],
             True, None),
            ('gnome_no_autostart',
             {'name': 'alice', 'password_hash': HASH, 'gnome_autostart': False, 'components': ['gnome']},
             [['id', 'alice'], ['useradd', '-m', '-G', 'sudo', 'alice'], ['usermod', '-p', HASH, 'alice'],
              ['uci', 'set', 'desktop.main.session=gnome'], ['uci', 'commit', 'desktop'],
              ['desktop-setup', 'alice', '--no-autostart']],
             True, None),
            ('base_only',
             {'name': 'alice', 'password_hash': HASH, 'gnome_autostart': False, 'components': []},
             [['id', 'alice'], ['useradd', '-m', '-G', 'sudo', 'alice'], ['usermod', '-p', HASH, 'alice']],
             True, None),
            ('audio_failure_keeps_request',
             {'name': 'alice', 'password_hash': HASH, 'gnome_autostart': True, 'components': ['gnome', 'audio']},
             [['id', 'alice'], ['useradd', '-m', '-G', 'sudo', 'alice'], ['usermod', '-p', HASH, 'alice'],
              ['uci', 'set', 'desktop.main.session=gnome'], ['uci', 'commit', 'desktop'],
              ['desktop-setup', 'alice'], ['desktop-audio-setup', 'alice']],
             False, 'desktop-audio-setup'),
        ]:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as tmp:
                fb_path = Path(tmp) / 'firstboot.json'
                fb_path.write_text(json.dumps(fb_data))
                recorded = []

                def fake_run(cmd, **kwargs):
                    recorded.append(list(cmd))
                    if cmd[0] == 'id':
                        return subprocess.CompletedProcess(cmd, 1)
                    if fail_cmd and cmd[0] == fail_cmd:
                        raise subprocess.CalledProcessError(1, cmd)
                    return subprocess.CompletedProcess(cmd, 0)

                patched = fb_src.replace('/etc/openwrt-installer/firstboot.json', str(fb_path))
                ns = {}
                with patch.object(subprocess, 'run', side_effect=fake_run):
                    if fail_cmd:
                        with self.assertRaises(subprocess.CalledProcessError):
                            exec(compile(patched, 'firstboot', 'exec'), ns)
                    else:
                        exec(compile(patched, 'firstboot', 'exec'), ns)
                self.assertEqual(recorded, expected_cmds)
                self.assertEqual(not fb_path.exists(), expect_unlinked)

    def test_rdp_package_split_recipes(self):
        desktop_mk = (ROOT / 'package/custom/openwrt-desktop/Makefile').read_text()
        base_block = desktop_mk.split('define Package/openwrt-desktop-base\n', 1)[1].split('endef', 1)[0]
        core_block = desktop_mk.split('define Package/openwrt-desktop-core\n', 1)[1].split('endef', 1)[0]
        rdp_block = desktop_mk.split('define Package/openwrt-desktop-rdp\n', 1)[1].split('endef', 1)[0]
        meta_block = desktop_mk.split('define Package/openwrt-desktop\n', 1)[1].split('endef', 1)[0]
        self.assertNotIn('gnome-shell', base_block)
        self.assertNotIn('gnome-keyring', base_block)
        self.assertNotIn('gnome-remote-desktop', base_block)
        self.assertIn('+python3', base_block)
        self.assertIn('+openwrt-desktop-base', core_block)
        self.assertNotIn('gnome-remote-desktop', core_block)
        self.assertIn('+openwrt-desktop-core', rdp_block)
        self.assertIn('+gnome-remote-desktop', rdp_block)
        self.assertIn('+openwrt-desktop-core', meta_block)
        self.assertIn('+openwrt-desktop-rdp', meta_block)

        for pkg in ('luci-app-desktop', 'openwrt-desktop-audio', 'openwrt-appimage'):
            mk = (ROOT / 'package/custom' / pkg / 'Makefile').read_text()
            self.assertIn('+openwrt-desktop-base', mk)
            self.assertNotIn('+openwrt-desktop-core', mk)
            self.assertNotRegex(mk, r'\+openwrt-desktop(?:\s|$)')

        ime_mk = (ROOT / 'package/custom/openwrt-desktop-ime/Makefile').read_text()
        ime_base = ime_mk.split('define Package/openwrt-desktop-ime-base', 1)[1].split('endef', 1)[0]
        ime_gnome = ime_mk.split('define Package/openwrt-desktop-ime\n', 1)[1].split('endef', 1)[0]
        self.assertIn('+openwrt-desktop-base', ime_base)
        self.assertNotIn('gnome', ime_base)
        self.assertIn('+openwrt-desktop-ime-base', ime_gnome)
        self.assertIn('+openwrt-desktop-core', ime_gnome)
        self.assertIn('+gnome-shell-extension-kimpanel', ime_gnome)

        fp_mk = (ROOT / 'package/custom/openwrt-flatpak/Makefile').read_text()
        fp_base = fp_mk.split('define Package/openwrt-flatpak-base', 1)[1].split('endef', 1)[0]
        fp_gnome = fp_mk.split('define Package/openwrt-flatpak\n', 1)[1].split('endef', 1)[0]
        self.assertIn('+openwrt-desktop-base', fp_base)
        self.assertNotIn('gnome', fp_base)
        self.assertIn('+openwrt-flatpak-base', fp_gnome)
        self.assertIn('+openwrt-desktop-core', fp_gnome)
        self.assertIn('+xdg-desktop-portal-gtk', fp_gnome)
        self.assertIn('+xdg-desktop-portal-gnome', fp_gnome)

    def test_snapshot_kconfig_reconstruction_selects_all_ten_components(self):
        conf = ROOT / 'scripts/config/conf'
        if not conf.is_file():
            self.skipTest('host Kconfig conf binary not built')
        base = ROOT / 'configs/x86-64-systemd-desktop.config'
        plasma_pkgs = ROOT / 'configs/plasma-packages.config'
        plasma_full = ROOT / 'configs/plasma.config'
        iso_frag = ROOT / 'configs/installer-iso.config'
        with tempfile.TemporaryDirectory(prefix='test-kconfig-iso-') as td:
            td = Path(td)
            # 1. Documented 10-component ISO reconstruction path from desktop snapshot.
            iso_cfg = td / 'iso.config'
            merged = subprocess.check_output(
                [str(ROOT / 'scripts/kconfig.pl'), '+', 'm+', str(base), str(plasma_pkgs), str(iso_frag)],
                text=True,
            )
            iso_cfg.write_text(merged)
            env = {**os.environ, 'KCONFIG_CONFIG': str(iso_cfg), 'TOPDIR': str(ROOT)}
            subprocess.run(
                [str(conf), f'--defconfig={iso_cfg}', 'Config.in'],
                cwd=ROOT, env=env, check=True, capture_output=True, text=True,
            )
            resolved = iso_cfg.read_text()
            self.assertIn('CONFIG_BUILD_qt6base-gui_OPENGL_OPENGLES2=y\n', resolved)
            self.assertIn('CONFIG_BUILD_qt6base_SQL=y\n', resolved)
            self.assertIn('CONFIG_PACKAGE_kwin=m\n', resolved)
            self.assertIn('CONFIG_PACKAGE_krdp=m\n', resolved)
            missing = []
            for comp in CATALOG_CFG['components']:
                pkgs = list(comp.get('packages', []))
                for cond in comp.get('conditional_packages', []):
                    pkgs.extend(cond.get('packages', []))
                for pkg in pkgs:
                    if f'CONFIG_PACKAGE_{pkg}=y\n' not in resolved and f'CONFIG_PACKAGE_{pkg}=m\n' not in resolved:
                        missing.append((comp['id'], pkg))
            self.assertEqual(missing, [], f'Missing installer component packages after Kconfig: {missing}')

            # 2. Preinstalled Plasma fragment merged onto desktop snapshot.
            full_cfg = td / 'plasma.config'
            merged_full = subprocess.check_output(
                [str(ROOT / 'scripts/kconfig.pl'), '+', str(base), str(plasma_full)],
                text=True,
            )
            full_cfg.write_text(merged_full)
            env_full = {**os.environ, 'KCONFIG_CONFIG': str(full_cfg), 'TOPDIR': str(ROOT)}
            subprocess.run(
                [str(conf), f'--defconfig={full_cfg}', 'Config.in'],
                cwd=ROOT, env=env_full, check=True, capture_output=True, text=True,
            )
            resolved_full = full_cfg.read_text()
            for sym in (
                'CONFIG_BUILD_qt6base-gui_OPENGL_OPENGLES2=y',
                'CONFIG_BUILD_qt6base_SQL=y',
                'CONFIG_PACKAGE_openwrt-desktop-plasma=y',
                'CONFIG_PACKAGE_openwrt-desktop-plasma-core=y',
                'CONFIG_PACKAGE_openwrt-desktop-plasma-rdp=y',
                'CONFIG_PACKAGE_kwin=y',
                'CONFIG_PACKAGE_krdp=y',
            ):
                self.assertIn(sym + '\n', resolved_full)


if __name__ == '__main__':
    unittest.main()
