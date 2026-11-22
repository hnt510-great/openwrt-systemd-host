#!/usr/bin/env python3
"""Verify native-systemd pure-router Kconfig isolation and app decoupling."""
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest


TREE = Path(__file__).resolve().parents[2]
KCONFIG_TREE = Path(os.environ.get('OPENWRT_KCONFIG_TREE', str(TREE))).resolve()


def parse_config(text):
    values = {}
    for line in text.splitlines():
        if line.startswith('CONFIG_') and '=' in line:
            key, value = line[7:].split('=', 1)
            values[key] = value
        elif line.startswith('# CONFIG_') and line.endswith(' is not set'):
            values[line[9:-11]] = 'n'
    return values


class SystemdRouterDecouplingTests(unittest.TestCase):
    def normalize(self, base_config, overrides=()):
        conf = KCONFIG_TREE / 'scripts/config/conf'
        kconfig_pl = KCONFIG_TREE / 'scripts/kconfig.pl'
        if not conf.exists() or not (KCONFIG_TREE / 'tmp/.config-package.in').exists():
            self.skipTest('Kconfig metadata or scripts/config/conf is missing in ' + str(KCONFIG_TREE))
        with tempfile.TemporaryDirectory(prefix='router-decoupling-kconfig-') as temporary:
            temp = Path(temporary)
            seed = temp / 'seed.config'
            output = temp / 'out.config'
            current = temp / 'step0.config'
            current.write_text(base_config.read_text())
            for index, item in enumerate(overrides, start=1):
                if isinstance(item, Path):
                    frag = item
                else:
                    frag = temp / f'frag{index}.config'
                    frag.write_text(item)
                merged = temp / f'step{index}.config'
                res = subprocess.run(
                    ['perl', str(kconfig_pl), '+', str(current), str(frag)],
                    cwd=KCONFIG_TREE, text=True, capture_output=True, check=True)
                merged.write_text(res.stdout)
                current = merged
            seed.write_text(current.read_text())
            env = os.environ.copy()
            env['KCONFIG_CONFIG'] = str(output)
            env['TOPDIR'] = str(KCONFIG_TREE)
            result = subprocess.run(
                [str(conf), '--fatalrecursive', '--defconfig=' + str(seed),
                 '-w', str(output), 'Config.in'],
                cwd=KCONFIG_TREE, env=env, text=True, capture_output=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            return parse_config(output.read_text())

    def assertSelected(self, config, names):
        missing = [name for name in names if config.get(name) != 'y']
        self.assertEqual(missing, [], f'Expected =y symbols missing: {missing}')

    def assertUnselected(self, config, names):
        present = [name for name in names if config.get(name) == 'y']
        self.assertEqual(present, [], f'Unexpected =y symbols present: {present}')

    def test_xdg_desktop_portal_recipe_decoupled_from_flatpak_runtime(self):
        recipe = (TREE / 'package/custom/xdg-desktop-portal/Makefile').read_text()
        flatpak = (TREE / 'package/custom/flatpak/Makefile').read_text()
        flatpak_ver = re.search(r'^PKG_VERSION:=(\S+)$', flatpak, re.M).group(1)
        flatpak_hash = re.search(r'^PKG_HASH:=(\S+)$', flatpak, re.M).group(1)

        depends = re.search(r'^\s*DEPENDS:=([^\n]+)$', recipe, re.M).group(1)
        self.assertNotIn('+flatpak', depends)
        self.assertIn('+bubblewrap', depends)
        self.assertIn('FLATPAK_INTERFACES_VERSION:=' + flatpak_ver, recipe)
        self.assertIn('FLATPAK_INTERFACES_HASH:=' + flatpak_hash, recipe)
        self.assertIn('define Download/flatpak-interfaces', recipe)
        self.assertIn('$(eval $(call Download,flatpak-interfaces))', recipe)
        self.assertIn('-Dflatpak-interfaces=enabled', recipe)
        self.assertIn('-Dflatpak-interfaces-dir=$(FLATPAK_INTERFACES_DIR)', recipe)
        self.assertIn('org.freedesktop.portal.Flatpak.xml', recipe)

        # Avoid reserved ELF migration outputs in configs/apk-elf-rebuilds.mk.
        version = re.search(r'^PKG_VERSION:=(\S+)$', recipe, re.M).group(1)
        release = int(re.search(r'^PKG_RELEASE:=(\d+)$', recipe, re.M).group(1))
        ledger = (TREE / 'configs/apk-elf-rebuilds.mk').read_text()
        reserved = [
            int(match.group(1))
            for match in re.finditer(
                r'^ELF_REBUILD_xdg-desktop-portal_' + re.escape(version) + r'-r\d+:='
                + re.escape(version) + r'-r(\d+)$',
                ledger, re.M,
            )
        ]
        if reserved:
            self.assertGreater(release, max(reserved))

    def test_virt_manager_recipe_and_setup_decoupled_from_desktop(self):
        recipe = (TREE / 'package/custom/virt-manager/Makefile').read_text()
        block = re.search(r'define Package/virt-manager\n(.*?)endef', recipe, re.S).group(1)
        self.assertNotIn('+openwrt-desktop', block)
        for dep in ('+libvirt-daemon', '+shadow-groupadd', '+shadow-gpasswd', '+shadow-usermod'):
            self.assertIn(dep, block)

        setup = TREE / 'package/custom/virt-manager/files/virt-manager-setup'
        text = setup.read_text()
        self.assertNotIn('desktop-common.sh', text)
        syntax = subprocess.run(['sh', '-n', str(setup)], text=True, capture_output=True)
        self.assertEqual(syntax.returncode, 0, syntax.stderr)

    def test_virt_manager_validate_user_semantics(self):
        setup = (TREE / 'package/custom/virt-manager/files/virt-manager-setup').read_text()
        helper_match = re.search(
            r'(virt_manager_error\(\) \{.*?virt_manager_validate_user\(\) \{.*?\n\})',
            setup, re.S,
        )
        self.assertIsNotNone(helper_match)
        helper = helper_match.group(1)

        with tempfile.TemporaryDirectory(prefix='virt-manager-validate-') as temporary:
            temp = Path(temporary)
            home = temp / 'home-alice'
            home.mkdir()
            good_shell = temp / 'sh-ok'
            good_shell.write_text('#!/bin/sh\n')
            good_shell.chmod(0o755)
            noexec_shell = temp / 'sh-noexec'
            noexec_shell.write_text('#!/bin/sh\n')
            noexec_shell.chmod(0o644)
            nologin = temp / 'nologin'
            nologin.write_text('#!/bin/sh\n')
            nologin.chmod(0o755)

            passwd = temp / 'passwd'
            shadow = temp / 'shadow'
            passwd.write_text('\n'.join([
                f'root:x:0:0:root:/root:{good_shell}',
                f'svc:x:999:999:svc:{home}:{good_shell}',
                f'rootgrp:x:1001:0:rootgrp:{home}:{good_shell}',
                f'relhome:x:1002:1002:rel:relative/home:{good_shell}',
                f'nohome:x:1003:1003:nohome:{temp}/missing:{good_shell}',
                f'badsh:x:1004:1004:badsh:{home}:{noexec_shell}',
                f'nologinuser:x:1005:1005:nl:{home}:{nologin}',
                f'locked:x:1006:1006:locked:{home}:{good_shell}',
                f'emptyhash:x:1007:1007:empty:{home}:{good_shell}',
                f'starhash:x:1008:1008:star:{home}:{good_shell}',
                f'alice:x:1000:1000:alice:{home}:{good_shell}',
            ]) + '\n')
            shadow.write_text('\n'.join([
                'root:$6$hash:19000:0:99999:7:::',
                'svc:$6$hash:19000:0:99999:7:::',
                'rootgrp:$6$hash:19000:0:99999:7:::',
                'relhome:$6$hash:19000:0:99999:7:::',
                'nohome:$6$hash:19000:0:99999:7:::',
                'badsh:$6$hash:19000:0:99999:7:::',
                'nologinuser:$6$hash:19000:0:99999:7:::',
                'locked:!$6$hash:19000:0:99999:7:::',
                'emptyhash::19000:0:99999:7:::',
                'starhash:*:19000:0:99999:7:::',
                'alice:$6$hash:19000:0:99999:7:::',
            ]) + '\n')

            patched = helper.replace('/etc/passwd', str(passwd)).replace('/etc/shadow', str(shadow))
            script = temp / 'check.sh'
            script.write_text('#!/bin/sh\nset -eu\n' + patched + '\nvirt_manager_validate_user "$1"\n')

            ok = subprocess.run(['sh', str(script), 'alice'], text=True, capture_output=True)
            self.assertEqual(ok.returncode, 0, ok.stderr)

            for bad_user in ('', '-alice', 'bad name', 'missing', 'root', 'svc',
                             'rootgrp', 'relhome', 'nohome', 'badsh',
                             'nologinuser', 'locked', 'emptyhash', 'starhash'):
                with self.subTest(user=bad_user):
                    res = subprocess.run(['sh', str(script), bad_user], text=True, capture_output=True)
                    self.assertNotEqual(res.returncode, 0, f'Expected failure for {bad_user!r}')

    def test_pure_router_config_kconfig_isolation(self):
        cfg = self.normalize(TREE / 'configs/x86-64-systemd-router.config')
        self.assertSelected(cfg, [
            'TARGET_x86_64', 'USE_GLIBC', 'USE_APK', 'OPENWRT_SYSTEMD',
            'OPENWRT_SYSTEMD_SERVICE_BRIDGE', 'OPENWRT_KERNEL_UPGRADE',
            'SIGNED_PACKAGES', 'TARGET_ROOTFS_SQUASHFS', 'GRUB_EFI_IMAGES',
            'PACKAGE_systemd-openwrt', 'PACKAGE_systemd-openwrt-services',
            'PACKAGE_openwrt-kernel-upgrade', 'PACKAGE_procd', 'PACKAGE_ubus',
            'PACKAGE_netifd', 'PACKAGE_firewall4', 'PACKAGE_dnsmasq-full',
            'PACKAGE_odhcp6c', 'PACKAGE_odhcpd-ipv6only', 'PACKAGE_ppp',
            'PACKAGE_ppp-mod-pppoe', 'PACKAGE_luci', 'PACKAGE_luci-i18n-base-zh-cn',
            'PACKAGE_openssh-server-pam', 'PACKAGE_openssh-keygen', 'PACKAGE_sudo',
            'PACKAGE_shadow-groupadd', 'PACKAGE_shadow-useradd', 'PACKAGE_shadow-usermod',
            'PACKAGE_kmod', 'PACKAGE_kmod-nvme', 'PACKAGE_kmod-r8169',
            'PACKAGE_kmod-igc', 'PACKAGE_kmod-igb', 'PACKAGE_kmod-e1000e',
            'PACKAGE_kmod-e1000',
        ])
        self.assertUnselected(cfg, [
            'TARGET_PREINIT_DISABLE_FAILSAFE', 'INSTALLER_ISO_IMAGES', 'ISO_IMAGES',
            'PACKAGE_video-support', 'PACKAGE_dnsmasq', 'PACKAGE_dropbear',
            'PACKAGE_openwrt-desktop', 'PACKAGE_gnome-shell', 'PACKAGE_flatpak',
            'PACKAGE_openwrt-flatpak', 'PACKAGE_xdg-desktop-portal',
            'PACKAGE_podman', 'PACKAGE_openwrt-podman-rootless', 'PACKAGE_luci-app-podman',
            'PACKAGE_distrobox', 'PACKAGE_samba4-server', 'PACKAGE_luci-app-samba4',
            'PACKAGE_wsdd2', 'PACKAGE_avahi-dbus-daemon',
            'PACKAGE_libvirt-daemon', 'PACKAGE_qemu-x86_64-softmmu',
            'PACKAGE_virt-manager', 'PACKAGE_luci-app-qemu', 'PACKAGE_openwrt-installer',
        ])

    def test_busybox_pam_default_dependency(self):
        recipe = (TREE / 'package/utils/busybox/Makefile').read_text()
        self.assertIn('BUSYBOX_DEFAULT_PAM:libpam', recipe)
        self.assertIn('+(BUSYBOX_CONFIG_PAM||BUSYBOX_DEFAULT_PAM):libpam', recipe)

    def test_gnome_without_flatpak_kconfig(self):
        cfg = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            [TREE / 'configs/gnome-desktop-core.config'],
        )
        self.assertSelected(cfg, [
            'PACKAGE_openwrt-desktop', 'PACKAGE_gnome-shell',
            'PACKAGE_gnome-remote-desktop', 'PACKAGE_xdg-desktop-portal-gnome',
            'PACKAGE_xdg-desktop-portal', 'PACKAGE_bubblewrap',
            'PACKAGE_libgst1pbutils',
        ])
        self.assertUnselected(cfg, [
            'PACKAGE_flatpak', 'PACKAGE_openwrt-flatpak',
            'PACKAGE_podman', 'PACKAGE_distrobox', 'PACKAGE_samba4-server',
            'PACKAGE_libvirt-daemon', 'PACKAGE_virt-manager',
        ])

    def test_gnome_with_flatpak_kconfig(self):
        cfg = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            [
                TREE / 'configs/gnome-desktop-core.config',
                'CONFIG_PACKAGE_openwrt-flatpak=y\n',
            ],
        )
        self.assertSelected(cfg, [
            'PACKAGE_openwrt-desktop', 'PACKAGE_openwrt-flatpak',
            'PACKAGE_flatpak', 'PACKAGE_xdg-desktop-portal',
            'PACKAGE_xdg-desktop-portal-gnome', 'PACKAGE_xdg-desktop-portal-gtk',
        ])
        self.assertUnselected(cfg, [
            'PACKAGE_podman', 'PACKAGE_distrobox', 'PACKAGE_samba4-server',
            'PACKAGE_libvirt-daemon', 'PACKAGE_virt-manager',
        ])

    def test_podman_without_distrobox_kconfig(self):
        cfg = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            [TREE / 'configs/podman.config'],
        )
        self.assertSelected(cfg, [
            'PACKAGE_podman', 'PACKAGE_openwrt-podman-rootless',
            'PACKAGE_luci-app-podman', 'PACKAGE_luci-i18n-podman-zh-cn',
        ])
        self.assertUnselected(cfg, [
            'PACKAGE_distrobox', 'PACKAGE_openwrt-desktop', 'PACKAGE_flatpak',
            'PACKAGE_samba4-server', 'PACKAGE_libvirt-daemon', 'PACKAGE_virt-manager',
        ])

    def test_distrobox_kconfig(self):
        cfg = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            [TREE / 'configs/distrobox.config'],
        )
        self.assertSelected(cfg, [
            'PACKAGE_distrobox', 'PACKAGE_openwrt-podman-rootless', 'PACKAGE_podman',
        ])
        self.assertUnselected(cfg, [
            'PACKAGE_openwrt-desktop', 'PACKAGE_flatpak',
            'PACKAGE_samba4-server', 'PACKAGE_libvirt-daemon', 'PACKAGE_virt-manager',
        ])

    def test_samba_with_and_without_discovery_kconfig(self):
        no_disc = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            [
                'CONFIG_PACKAGE_samba4-server=y\n'
                'CONFIG_PACKAGE_luci-app-samba4=y\n'
                '# CONFIG_SAMBA4_SERVER_WSDD2 is not set\n'
                '# CONFIG_SAMBA4_SERVER_AVAHI is not set\n'
            ],
        )
        self.assertSelected(no_disc, [
            'PACKAGE_samba4-server', 'PACKAGE_luci-app-samba4',
            'PACKAGE_luci-i18n-samba4-zh-cn',
        ])
        self.assertUnselected(no_disc, [
            'PACKAGE_wsdd2', 'PACKAGE_avahi-dbus-daemon',
            'PACKAGE_openwrt-desktop', 'PACKAGE_podman', 'PACKAGE_libvirt-daemon',
        ])

        with_disc = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            [TREE / 'configs/samba4.config'],
        )
        self.assertSelected(with_disc, [
            'PACKAGE_samba4-server', 'PACKAGE_luci-app-samba4',
            'PACKAGE_luci-i18n-samba4-zh-cn', 'PACKAGE_wsdd2',
            'PACKAGE_avahi-dbus-daemon',
        ])
        self.assertUnselected(with_disc, [
            'PACKAGE_openwrt-desktop', 'PACKAGE_podman', 'PACKAGE_libvirt-daemon',
        ])

    def test_headless_virtualization_and_virt_manager_kconfig(self):
        headless = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            [TREE / 'configs/virt-headless.config'],
        )
        self.assertSelected(headless, [
            'PACKAGE_libvirt-daemon', 'PACKAGE_virsh', 'PACKAGE_virt-install',
            'PACKAGE_qemu-x86_64-softmmu', 'PACKAGE_luci-app-qemu',
        ])
        self.assertUnselected(headless, [
            'PACKAGE_virt-manager', 'PACKAGE_openwrt-desktop',
            'PACKAGE_gnome-shell', 'PACKAGE_flatpak',
            'PACKAGE_podman', 'PACKAGE_samba4-server',
        ])

        vm_gui = self.normalize(
            TREE / 'configs/x86-64-systemd-router.config',
            ['CONFIG_PACKAGE_virt-manager=y'],
        )
        self.assertSelected(vm_gui, [
            'PACKAGE_virt-manager', 'PACKAGE_libvirt-daemon',
            'PACKAGE_shadow-groupadd', 'PACKAGE_shadow-gpasswd', 'PACKAGE_shadow-usermod',
        ])
        self.assertUnselected(vm_gui, [
            'PACKAGE_openwrt-desktop', 'PACKAGE_gnome-shell', 'PACKAGE_flatpak',
        ])

    def test_full_desktop_config_retains_existing_features(self):
        cfg = self.normalize(TREE / 'configs/x86-64-systemd-desktop.config')
        self.assertSelected(cfg, [
            'OPENWRT_SYSTEMD', 'USE_GLIBC', 'USE_APK', 'INSTALLER_ISO_IMAGES',
            'PACKAGE_openwrt-desktop', 'PACKAGE_gnome-remote-desktop',
            'PACKAGE_openwrt-flatpak', 'PACKAGE_flatpak',
            'PACKAGE_xdg-desktop-portal', 'PACKAGE_xdg-desktop-portal-gnome',
            'PACKAGE_podman', 'PACKAGE_openwrt-podman-rootless',
            'PACKAGE_luci-app-podman', 'PACKAGE_distrobox',
            'PACKAGE_samba4-server', 'PACKAGE_luci-app-samba4',
            'PACKAGE_wsdd2', 'PACKAGE_avahi-dbus-daemon',
            'PACKAGE_libvirt-daemon', 'PACKAGE_virt-manager', 'PACKAGE_luci-app-qemu',
        ])


if __name__ == '__main__':
    unittest.main()
