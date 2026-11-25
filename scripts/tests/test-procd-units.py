#!/usr/bin/env python3
"""Host checks for procd units mode packaging and hotplug wiring.

Runtime behaviour (transient units, triggers, respawn, udev forwarding) is
covered by scripts/tests/procd-units-guest.sh inside a disposable VM.
"""

import fnmatch
import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROCD = ROOT / 'package/system/procd'
SYSTEMD_OPENWRT = ROOT / 'package/system/systemd-openwrt'
HARDWARE = ROOT / 'package/system/hardware-support'
FORWARDER = '/usr/libexec/openwrt-udev-forward'


def commands(node):
    """Yield every json_script command name in a rule tree."""
    if isinstance(node, list):
        if node and isinstance(node[0], str):
            yield node[0]
        for child in node:
            yield from commands(child)
    elif isinstance(node, dict):
        for child in node.values():
            yield from commands(child)


def parse_udev_rules(path):
    rules = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        keys = re.findall(r'([A-Z]+(?:\{[^}]*\})?)\s*(==|!=|\+=|:=|=)\s*"([^"]*)"', line)
        rules.append(keys)
    return rules


def forwards(rules, event, dirs):
    """Count forwarder RUN entries a udev event would collect."""
    count = 0
    for rule in rules:
        matched = True
        runs = 0
        for key, op, value in rule:
            if key == 'RUN':
                runs += value == FORWARDER
                continue
            if key == 'TEST':
                path = value.replace('$env{SUBSYSTEM}', event.get('SUBSYSTEM', ''))
                result = path in dirs
            elif key.startswith('ENV{'):
                actual = event.get(key[4:-1], '')
                result = fnmatch.fnmatch(actual, value) if value != '?*' else bool(actual)
            else:
                actual = event.get(key, '')
                result = any(fnmatch.fnmatch(actual, alt) for alt in value.split('|'))
            if (op == '==') != result:
                matched = False
                break
        if matched:
            count += runs
    return count


class ProcdUnitsTest(unittest.TestCase):
    def test_patch_precedes_systemd_only_changes(self):
        patches = sorted(p.name for p in (PROCD / 'patches').glob('*.patch'))
        units_patch = '130-systemd-transient-units.patch'
        self.assertLess(patches.index(units_patch), patches.index('140-systemd-no-firmware.patch'))
        text = (PROCD / 'patches' / units_patch).read_text()
        for needle in ('StartTransientUnit', '"procd.udev"', '--systemd=units',
                       'hotplug_units', 'udevadm'):
            self.assertIn(needle, text)

    def test_systemd_instance_guard_packaged(self):
        systemd = ROOT / 'package/system/systemd'
        self.assertTrue((systemd / 'patches/002-openwrt-procd-instance-jobs.patch').is_file())
        release = re.search(r'^PKG_RELEASE:=(\d+)$',
                            (systemd / 'Makefile').read_text(), re.M)
        self.assertGreaterEqual(int(release[1]), 12)

    def test_units_rules_leave_device_nodes_to_udev(self):
        rules = json.loads((PROCD / 'files/hotplug-systemd.json').read_text())
        used = set(commands(rules))
        self.assertFalse(used & {'makedev', 'rm', 'include', 'start-console'})
        self.assertTrue({'exec', 'button', 'load-firmware'} <= used)
        stock = json.loads((PROCD / 'files/hotplug.json').read_text())
        self.assertTrue({'makedev', 'include'} <= set(commands(stock)))

    def test_each_event_is_forwarded_at_most_once(self):
        rules = parse_udev_rules(PROCD / 'files/90-openwrt-hotplug.rules')
        dirs = {'/etc/hotplug.d/block', '/etc/hotplug.d/net', '/etc/hotplug.d/'}
        cases = [
            ({'SUBSYSTEM': 'block', 'ACTION': 'add'}, 1),
            ({'SUBSYSTEM': 'net', 'ACTION': 'remove'}, 1),
            ({'SUBSYSTEM': 'input', 'ACTION': 'add'}, 0),
            ({'SUBSYSTEM': 'usb-serial', 'ACTION': 'add'}, 1),
            ({'SUBSYSTEM': 'firmware', 'FIRMWARE': 'x.bin'}, 1),
            ({'SUBSYSTEM': 'block', 'FIRMWARE': 'x.bin'}, 1),
        ]
        for event, expected in cases:
            with self.subTest(event=event):
                self.assertEqual(forwards(rules, event, dirs), expected)

    def test_package_installs_units_mode_files(self):
        makefile = (PROCD / 'Makefile').read_text()
        block = makefile.split('ifeq ($(CONFIG_OPENWRT_SYSTEMD),)', 1)[1].split('endif', 1)[0]
        legacy, native = block.split('\nelse\n', 1)
        self.assertIn('usr/sbin/upgraded', legacy)
        self.assertNotIn('usr/sbin/upgraded', native)
        for name in ('openwrt-udev-forward', '90-openwrt-hotplug.rules', 'hotplug-systemd.json'):
            self.assertIn(name, native)
        self.assertNotIn('hotplug*.json', makefile)

    def test_systemd_owns_watchdog_and_procd_runs_units(self):
        unit = (SYSTEMD_OPENWRT / 'files/openwrt-procd.service').read_text()
        self.assertIn('ExecStart=/sbin/procd --systemd=units -S', unit)
        self.assertIn('After=openwrt-ubusd.service systemd-udevd.service', unit)
        conf = (SYSTEMD_OPENWRT / 'files/system.conf').read_text()
        self.assertRegex(conf, r'(?m)^RuntimeWatchdogSec=30s$')
        makefile = (SYSTEMD_OPENWRT / 'Makefile').read_text()
        self.assertIn('+systemd-udev', makefile)
        self.assertNotIn('systemd-udevd.service systemd-udevd-control.socket', makefile)

    def test_udev_rules_use_groups_their_package_allocates(self):
        makefile = (HARDWARE / 'Makefile').read_text()
        packages = re.findall(r'define Package/(\w+)-support\n(.*?)endef', makefile, re.S)
        groups = {name: set(re.findall(r':([\w-]+)=\d+', body)) for name, body in packages}
        for path in sorted((HARDWARE / 'files/udev').glob('60-openwrt-*.rules')):
            topic = path.stem[len('60-openwrt-'):]
            with self.subTest(rule=path.name):
                self.assertTrue(list(HARDWARE.glob(f'files/*-{topic}.json')))
                used = set(re.findall(r'GROUP="([^"]+)"', path.read_text())) - {'root'}
                self.assertTrue(used <= groups[topic], used - groups[topic])

    def test_udev_defaults_are_not_tightened(self):
        names = {p.name for p in (HARDWARE / 'files/udev').glob('*.rules')}
        self.assertNotIn('60-openwrt-kvm.rules', names)
        self.assertNotIn('60-openwrt-accel.rules', names)
        for path in (HARDWARE / 'files/udev').glob('*.rules'):
            self.assertNotRegex(path.read_text(), r'KERNEL=="(kvm|renderD\*)"[^\n]*MODE')

    def test_libvirt_daemon_owns_kvm_and_render_udev_rules(self):
        libvirt = ROOT / 'package/custom/libvirt'
        rule = libvirt / 'files/65-libvirt-devices.rules'
        self.assertTrue(rule.is_file())
        text = rule.read_text()
        self.assertIn('KERNEL=="kvm", GROUP="kvm", MODE="0660", OPTIONS+="static_node=kvm"', text)
        self.assertIn('SUBSYSTEM=="drm", KERNEL=="renderD*", GROUP="render", MODE="0660"', text)
        self.assertNotIn('vhost-vsock', text)
        self.assertFalse((libvirt / 'files/libvirt-render.hotplug').exists())
        makefile = (libvirt / 'Makefile').read_text()
        self.assertIn('65-libvirt-devices.rules', makefile)
        self.assertNotIn('zz-libvirt-render\n', makefile)
        self.assertIn('define Package/libvirt-daemon/postinst', makefile)
        self.assertIn('define Package/libvirt-daemon/postrm', makefile)
        prepare = (libvirt / 'files/libvirt-openwrt-prepare').read_text()
        self.assertNotIn('/dev/kvm', prepare)
        self.assertNotIn('renderD', prepare)

    def test_virtio_console_helper_omits_duplicate_symlink_on_native_systemd(self):
        qemu_mk = ROOT / 'feeds/packages/utils/qemu/Makefile'
        if not qemu_mk.is_file():
            self.skipTest('packages feed qemu recipe unavailable')
        text = qemu_mk.read_text()
        install = text.split('define Package/virtio-console-helper/install', 1)[1].split('endef', 1)[0]
        self.assertIn('$(INSTALL_DIR) $(1)/etc/hotplug.d/virtio-ports', install)
        self.assertIn('ifeq ($(CONFIG_OPENWRT_SYSTEMD),)', install)
        self.assertIn('00-virtio-ports.hotplug', install)
        self.assertIn('CONFIG_OPENWRT_SYSTEMD', text.split('PKG_CONFIG_DEPENDS +=', 1)[1].splitlines()[0])
        ga_install = text.split('define Package/qemu-ga/install', 1)[1].split('endef', 1)[0]
        self.assertIn('10-qemu-ga.hotplug', ga_install)

    @unittest.skipUnless(shutil.which('udevadm'), 'udevadm not available')
    def test_udev_rules_parse(self):
        files = [str(p) for p in (HARDWARE / 'files/udev').glob('*.rules')]
        files.append(str(PROCD / 'files/90-openwrt-hotplug.rules'))
        files.append(str(ROOT / 'package/custom/libvirt/files/65-libvirt-devices.rules'))
        result = subprocess.run(['udevadm', 'verify', '--no-style', *files],
                                capture_output=True, text=True)
        if result.returncode != 0 and 'Unknown verb' in result.stderr:
            self.skipTest('udevadm verify not supported')
        problems = [line for line in (result.stdout + result.stderr).splitlines()
                    if '.rules:' in line and 'Unknown group' not in line
                    and 'rules check failed' not in line]
        self.assertEqual(problems, [])


if __name__ == '__main__':
    unittest.main()
