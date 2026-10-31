#!/usr/bin/env python3
"""Run the netifd wait-online helper against scripted ubus interface dumps."""
import configparser
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


TREE = Path(__file__).resolve().parents[2]
PACKAGE = TREE / 'package/system/systemd-openwrt'
HELPER = PACKAGE / 'files/openwrt-network-wait-online'
STAGING_LIB = TREE / 'staging_dir/target-x86_64_glibc/usr/lib'


def find_jsonfilter():
    # The helper's filter expressions are only meaningful with the real tool.
    for path in sorted(TREE.glob('build_dir/target-*/jsonfilter-*/.pkgdir/jsonfilter/usr/bin/jsonfilter')):
        if os.access(path, os.X_OK):
            return path
    return None


JSONFILTER = find_jsonfilter()


def interface(name, up, available=True, autostart=True, dynamic=False, proto='static'):
    return {'interface': name, 'up': up, 'pending': not up, 'available': available,
            'autostart': autostart, 'dynamic': dynamic, 'proto': proto}


@unittest.skipIf(JSONFILTER is None, 'build package/utils/jsonfilter first')
class WaitOnlineTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='wait-online-test-')
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        (self.root / 'bin').mkdir()
        (self.root / 'states').mkdir()
        self.write_executable('bin/ubus', '''#!/bin/sh
[ "$*" = '-t 5 call network.interface dump' ] || exit 9
count=$(cat "$TEST_ROOT/calls" 2>/dev/null || echo 0)
count=$((count + 1))
echo "$count" > "$TEST_ROOT/calls"
state=$TEST_ROOT/states/$count
[ -e "$state" ] || state=$TEST_ROOT/states/$(ls "$TEST_ROOT/states" | sort -n | tail -n 1)
case "$(cat "$state")" in
absent) echo 'Command failed: Not found' >&2; exit 4 ;;
esac
cat "$state"
''')
        self.write_executable('bin/jsonfilter', '#!/bin/sh\nexec "$JSONFILTER_BIN" "$@"\n')
        self.env = {**os.environ, 'PATH': str(self.root / 'bin') + ':' + os.environ['PATH'],
                    'TEST_ROOT': str(self.root), 'JSONFILTER_BIN': str(JSONFILTER),
                    'LD_LIBRARY_PATH': str(STAGING_LIB)}

    def write_executable(self, name, text):
        path = self.root / name
        path.write_text(text)
        path.chmod(0o755)

    def states(self, *states):
        for number, state in enumerate(states, 1):
            text = state if isinstance(state, str) else json.dumps({'interface': state})
            (self.root / 'states' / str(number)).write_text(text)

    def run_helper(self, *args, timeout=30):
        return subprocess.run(['sh', str(HELPER), *args], env=self.env, capture_output=True,
                              text=True, timeout=timeout)

    def calls(self):
        return int((self.root / 'calls').read_text())

    def test_waits_for_netifd_configuration_and_interfaces(self):
        self.states('absent', [], [interface('loopback', True), interface('lan', False),
                                    interface('wan', False)],
                    [interface('loopback', True), interface('lan', True), interface('wan', False)],
                    [interface('loopback', True), interface('lan', True), interface('wan', True)])
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan wan')
        self.assertEqual(self.calls(), 5)

    def test_ignores_absent_devices_dynamic_and_manual_interfaces(self):
        self.states([interface('loopback', True), interface('lan', True),
                     interface('modem', False, available=False),
                     interface('wan_6', False, dynamic=True),
                     interface('guest', False, autostart=False)])
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan')
        self.assertEqual(self.calls(), 1)

    def test_upstream_outage_does_not_hold_local_networks(self):
        # The router's PPPoE and WireGuard links stay down; LAN services must not wait.
        self.states([interface('loopback', True), interface('lan', False),
                     interface('wan', False, proto='pppoe'),
                     interface('WIREGUARD', False, proto='wireguard')],
                    [interface('loopback', True), interface('lan', True),
                     interface('wan', False, proto='pppoe'),
                     interface('WIREGUARD', False, proto='wireguard')])
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan')
        self.assertEqual(self.calls(), 2)

    def test_upstream_alone_cannot_complete_before_the_lan_device_exists(self):
        self.states([interface('loopback', True), interface('lan', False, available=False),
                     interface('wan', True, proto='pppoe'),
                     interface('WIREGUARD', True, proto='wireguard')],
                    [interface('loopback', True), interface('lan', False),
                     interface('wan', True, proto='pppoe'),
                     interface('WIREGUARD', True, proto='wireguard')],
                    [interface('loopback', True), interface('lan', True),
                     interface('wan', True, proto='pppoe'),
                     interface('WIREGUARD', True, proto='wireguard')])
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan')
        self.assertEqual(self.calls(), 3)

    def test_without_local_networks_waits_for_every_present_interface(self):
        self.states([interface('loopback', True), interface('lan', False, proto='dhcp'),
                     interface('wan', True, proto='dhcp'),
                     interface('modem', False, available=False, proto='qmi')],
                    [interface('loopback', True), interface('lan', True, proto='dhcp'),
                     interface('wan', True, proto='dhcp'),
                     interface('modem', False, available=False, proto='qmi')])
        result = self.run_helper()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan wan')
        self.assertEqual(self.calls(), 2)

    def test_loopback_alone_is_not_online(self):
        self.states([interface('loopback', True)])
        result = self.run_helper('--timeout', '2')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Timed out after 2s waiting for: interfaces', result.stderr)

    def test_timeout_names_interfaces_still_down(self):
        self.states([interface('loopback', True), interface('lan', True), interface('guest', False)])
        result = self.run_helper('--timeout=2')
        self.assertEqual(result.returncode, 1)
        self.assertIn('Timed out after 2s waiting for: guest', result.stderr)
        self.assertGreaterEqual(self.calls(), 2)

    def test_named_upstream_interface_is_waited_for(self):
        self.states([interface('loopback', True), interface('lan', True),
                     interface('wan', False, proto='pppoe')],
                    [interface('loopback', True), interface('lan', True),
                     interface('wan', True, proto='pppoe')])
        result = self.run_helper('--interface', 'lan', '--interface', 'wan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan wan')
        self.assertEqual(self.calls(), 2)

    def test_named_interfaces_override_the_default_selection(self):
        self.states([interface('loopback', True), interface('lan', False), interface('wan', False)],
                    [interface('loopback', True), interface('lan', True), interface('wan', False)])
        result = self.run_helper('--interface', 'lan')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan')
        self.assertEqual(self.calls(), 2)

    def test_named_interface_is_waited_for_before_its_device_appears(self):
        self.states([interface('loopback', True), interface('lan', True)],
                    [interface('loopback', True), interface('lan', True),
                     interface('modem', False, available=False)],
                    [interface('loopback', True), interface('lan', True), interface('modem', True)])
        result = self.run_helper('-i', 'lan', '-i', 'modem')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan modem')
        self.assertEqual(self.calls(), 3)

    def test_any_accepts_one_selected_interface(self):
        self.states([interface('loopback', True), interface('lan', True), interface('wan', False)])
        result = self.run_helper('--any')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), 'Network is online: lan')

    def test_rejects_invalid_arguments(self):
        self.states([interface('lan', True)])
        for args in (['--timeout', 'soon'], ['--timeout'], ['-i', 'lan;reboot'], ['--bogus']):
            result = self.run_helper(*args)
            self.assertEqual(result.returncode, 2, args)
            self.assertIn('Usage:', result.stderr)
        self.assertFalse((self.root / 'calls').exists())


class UnitTests(unittest.TestCase):
    def test_unit_orders_before_network_online_without_waiting_for_rc_scripts(self):
        unit = configparser.ConfigParser(strict=False, interpolation=None)
        unit.optionxform = str
        unit.read(PACKAGE / 'files/openwrt-network-wait-online.service')
        self.assertIn('network-online.target', unit['Unit']['Before'].split())
        self.assertIn('openwrt-procd.service', unit['Unit']['After'].split())
        # rc scripts may synchronously start units ordered after network-online.target.
        self.assertNotIn('openwrt-services.service', unit['Unit']['After'].split())
        self.assertEqual(unit['Install']['WantedBy'], 'network-online.target')
        self.assertEqual(unit['Service']['ExecStart'], '/usr/libexec/openwrt-network-wait-online')

    def test_package_installs_and_enables_the_unit(self):
        makefile = (PACKAGE / 'Makefile').read_text()
        self.assertIn('./files/openwrt-network-wait-online $(1)/usr/libexec/', makefile)
        self.assertIn('$(1)/etc/systemd/system/network-online.target.wants/', makefile)
        # User managers cannot pull in system targets; boot must activate it.
        self.assertIn('/usr/lib/systemd/system/network-online.target $(1)/etc/systemd/system/multi-user.target.wants/',
                      makefile)
        self.assertIn('+jsonfilter', makefile)


if __name__ == '__main__':
    unittest.main()
