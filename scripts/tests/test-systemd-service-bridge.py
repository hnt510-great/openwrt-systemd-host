#!/usr/bin/env python3
"""Exercise the real bridge binary and IPC against an isolated fake root.

The BRIDGE_TEST binary alone enables the explicit --test-root option and a
file-backed procd snapshot. Production builds contain neither override.
"""
import json
import os
from pathlib import Path
import shutil
import shlex
import socket
import subprocess
import tempfile
import threading
import time
import unittest


TREE = Path(__file__).resolve().parents[2]
SOURCE = TREE / 'package/system/systemd-openwrt-services'


class BridgeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='owb-build-')
        toolchains = sorted((TREE / 'staging_dir').glob('toolchain-x86_64_gcc-*_glibc'))
        if not toolchains:
            raise unittest.SkipTest('Build the x86_64/glibc toolchain first')
        cls.toolchain = toolchains[-1]
        cls.staging = TREE / 'staging_dir/target-x86_64_glibc'
        cls.binary = Path(cls.build.name) / 'bridge'
        compiler = cls.toolchain / 'bin/x86_64-openwrt-linux-gcc'
        subprocess.run([
            str(compiler), '-O2', '-g', '-Wall', '-Wextra', '-Werror',
            '-DBRIDGE_TEST', '-I', str(cls.staging / 'usr/include'),
            str(SOURCE / 'src/service-bridge.c'), '-L', str(cls.staging / 'usr/lib'),
            '-Wl,-rpath-link,' + str(cls.staging / 'usr/lib'),
            '-lubus', '-lubox', '-lblobmsg_json', '-ljson-c', '-lsystemd',
            '-o', str(cls.binary),
        ], check=True, env={**os.environ, 'STAGING_DIR': str(cls.staging)})
        cls.runner = [
            str(cls.toolchain / 'lib/ld-linux-x86-64.so.2'),
            '--library-path', ':'.join(map(str, [
                cls.staging / 'usr/lib', cls.toolchain / 'lib',
            ])), str(cls.binary),
        ]

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='owb-')
        self.root = Path(self.directory.name)
        for directory in ['etc/init.d', 'etc/rc.d', 'usr/bin', 'usr/sbin',
                          'usr/share/openwrt-service-bridge', 'run', 'proc']:
            (self.root / directory).mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / 'files/service-kinds',
                        self.root / 'usr/share/openwrt-service-bridge/service-kinds')
        self.set_snapshot({})
        self.make_script('sample')
        self.executable('usr/bin/systemctl', '''#!/bin/sh
printf '%s\\n' "$*" >> "$(dirname "$0")/../../native-actions"
''')
        self.executable('usr/sbin/nft', '''#!/bin/sh
if test -f "$(dirname "$0")/../../firewall-active"; then
    echo '{"nftables":[{"table":{"family":"inet","name":"fw4"}}]}'
else
    echo '{"nftables":[]}'
fi
''')
        self.log = open(self.root / 'daemon.log', 'w')
        self.daemon = subprocess.Popen(self.command('daemon'), stdout=self.log, stderr=self.log)
        self.wait_for(lambda: (self.root / 'run/openwrt-service-bridge/control').exists())

    def tearDown(self):
        self.daemon.terminate()
        self.daemon.wait(timeout=5)
        self.log.close()
        self.directory.cleanup()

    def command(self, *args):
        return [*self.runner, '--test-root', str(self.root), *args]

    def call(self, *args):
        return subprocess.run(self.command('systemctl', *args), text=True,
                              capture_output=True, timeout=15)

    def executable(self, name, text):
        p = self.root / name
        p.write_text(text)
        p.chmod(0o755)

    def make_script(self, name, procd=True):
        # Python is only a fixture interpreter; the installed bridge is C.
        header = 'USE_PROCD=1\n' if procd else ''
        self.executable('etc/init.d/' + name, '''#!/usr/bin/python3
START=20
STOP=90
''' + header + '''
import fcntl, json, os, pathlib, sys, time
root = pathlib.Path(__file__).parents[2]
name = pathlib.Path(__file__).name
action = sys.argv[1]
with open(root / 'fixture.lock', 'a') as lock:
    fcntl.flock(lock, fcntl.LOCK_EX)
    with open(root / 'actions', 'a') as log:
        log.write(name + ':' + action + '\\n')
    if (root / ('fail-' + name)).exists():
        sys.exit(9)
    if (root / 'slow').exists():
        time.sleep(0.2)
    if action in ('enable', 'disable'):
        for key in ('S20', 'K90'):
            link = root / 'etc/rc.d' / (key + name)
            link.unlink(missing_ok=True)
            if action == 'enable':
                link.symlink_to('../init.d/' + name)
    elif action in ('start', 'restart', 'stop'):
        data = json.loads((root / 'ubus.json').read_text())
        if action == 'stop':
            data.pop(name, None)
        else:
            data[name] = {'instances': {'main': {'running': True, 'pid': 123}}}
        tmp = root / 'ubus.json.new'
        tmp.write_text(json.dumps(data))
        tmp.replace(root / 'ubus.json')
''')

    def set_snapshot(self, value):
        p = self.root / 'ubus.json.new'
        p.write_text(json.dumps(value))
        p.replace(self.root / 'ubus.json')

    def request(self, **value):
        with socket.socket(socket.AF_UNIX, socket.SOCK_SEQPACKET) as client:
            client.settimeout(5)
            client.connect(str(self.root / 'run/openwrt-service-bridge/control'))
            client.send(json.dumps(value).encode())
            return json.loads(client.recv(8192))

    @staticmethod
    def wait_for(predicate, timeout=8):
        deadline = time.monotonic() + timeout
        while not predicate():
            if time.monotonic() > deadline:
                raise AssertionError('Timed out waiting for bridge state')
            time.sleep(0.03)

    def actions(self):
        p = self.root / 'actions'
        return p.read_text().splitlines() if p.exists() else []

    def test_hint(self):
        result = self.call('hint', 'sample')
        self.assertEqual(result.returncode, 0)
        self.assertIn('systemctl restart openwrt@sample', result.stdout)
        self.make_script('network')
        self.set_snapshot({'network': {'instances': {'main': {
            'command': ['/sbin/netifd'], 'running': True}}}})
        result = self.call('hint', 'netifd', 'stop')
        self.assertEqual(result.returncode, 0)
        self.assertIn("supervised by OpenWrt service 'network'", result.stdout)
        self.assertIn('systemctl stop openwrt@network', result.stdout)
        self.assertEqual(self.call('hint', 'unmatched').stdout, '')
        self.assertFalse((self.root / 'actions').exists())
        self.assertFalse((self.root / 'native-actions').exists())
        self.assertEqual(self.call('hint', '../network').returncode, 2)

    def test_actions_keep_custom_restart_and_do_not_repeat_during_reconcile(self):
        for action in ['start', 'restart', 'reload', 'stop']:
            result = self.call(action, 'openwrt@sample.service')
            self.assertEqual(result.returncode, 0, result.stderr)
        time.sleep(2.3)
        self.assertEqual(self.actions(), [
            'sample:start', 'sample:restart', 'sample:reload', 'sample:stop'])

    def test_enable_disable_and_now_share_rc_links(self):
        self.assertEqual(self.call('is-enabled', 'openwrt@sample').returncode, 1)
        self.assertEqual(self.call('enable', '--now', 'openwrt@sample').returncode, 0)
        self.assertEqual(self.call('is-enabled', 'openwrt@sample').stdout.strip(), 'enabled')
        self.assertEqual(self.call('is-active', 'openwrt@sample').stdout.strip(), 'active')
        self.assertEqual(self.call('disable', 'openwrt@sample').returncode, 0)
        self.assertEqual(self.call('is-active', 'openwrt@sample').returncode, 0)
        self.assertEqual(self.call('disable', '--now', 'openwrt@sample').returncode, 0)
        self.assertEqual(self.call('is-active', 'openwrt@sample').stdout.strip(), 'inactive')

    def test_live_procd_partial_respawn_permanent_failure_and_recovery(self):
        scenarios = [
            ({'a': {'running': True}, 'b': {'running': True}}, 'active', '2/2', 0),
            ({'a': {'running': True}, 'b': {'running': False}}, 'active', '1/2', 0),
            ({'a': {'running': False, 'respawn': {'timeout': 5}}}, 'activating', 'respawn', 3),
            ({'a': {'running': False, 'respawn': {'timeout': 1},
                    'systemd_unit': 'openwrt-sample@a.service',
                    'systemd_state': 'activating', 'exit_code': 137}}, 'activating', 'respawn', 3),
            ({'a': {'running': False, 'respawn': {'timeout': 1},
                    'systemd_state': 'failed', 'exit_code': 137}}, 'failed', 'instance failure', 3),
            ({'a': {'running': False, 'respawn': {'timeout': 1},
                    'systemd_unit': 'openwrt-sample@a.service',
                    'exit_code': 137}}, 'failed', 'instance failure', 3),
            ({'a': {'running': False, 'respawn': {'timeout': 1},
                    'systemd_unit': 'openwrt-sample@a.service',
                    'exit_code': 0}}, 'inactive', 'exited successfully', 3),
            ({'a': {'running': False, 'exit_code': 1}}, 'failed', '0/1', 3),
            ({'a': {'running': True}}, 'active', '1/1', 0),
        ]
        for instances, state, detail, code in scenarios:
            with self.subTest(state=state, detail=detail):
                self.set_snapshot({'sample': {'instances': instances}})
                result = self.call('status', 'openwrt@sample.service')
                self.assertEqual(result.returncode, code, result.stderr)
                self.assertIn(state, result.stdout)
                self.assertIn(detail, result.stdout)
        self.assertEqual(self.actions(), [])

    def test_successful_exit_is_not_a_failed_daemon_or_failed_setup_task(self):
        self.set_snapshot({'sample': {'instances': {'main': {'running': False, 'exit_code': 0}}}})
        result = self.call('status', 'openwrt@sample')
        self.assertEqual(result.returncode, 3)
        self.assertIn('inactive', result.stdout)
        self.assertIn('exited successfully', result.stdout)
        self.make_script('urandom_seed')
        self.set_snapshot({'urandom_seed': {'instances': {'seed': {'running': False, 'exit_code': 0}}}})
        result = self.call('status', 'openwrt@urandom_seed')
        self.assertEqual(result.returncode, 0)
        self.assertIn('setup completed successfully', result.stdout)
        self.set_snapshot({'urandom_seed': {'instances': {'seed': {'running': False, 'exit_code': 1}}}})
        self.assertEqual(self.call('status', 'openwrt@urandom_seed').returncode, 3)

    def test_bus_outage_is_unknown_then_recovers(self):
        (self.root / 'ubus.json').unlink()
        result = self.call('status', 'openwrt@sample')
        self.assertEqual(result.returncode, 4)
        self.assertIn('unavailable', result.stdout)
        self.set_snapshot({'sample': {}})
        result = self.call('status', 'openwrt@sample')
        self.assertEqual(result.returncode, 0)
        self.assertIn('configured with no instances', result.stdout)

    def test_setup_completion_is_not_claimed_to_be_a_running_daemon(self):
        self.make_script('sysctl', procd=False)
        self.assertEqual(self.call('status', 'openwrt@sysctl').returncode, 4)
        subprocess.run(self.command('notify', 'sysctl', 'boot', '0'), check=True)
        self.wait_for(lambda: 'completed' in self.call('status', 'openwrt@sysctl').stdout)
        self.assertIn('no daemon expected', self.call('status', 'openwrt@sysctl').stdout)
        subprocess.run(self.command('notify', 'sysctl', 'enable', '0'), check=True)
        self.assertIn('completed', self.call('status', 'openwrt@sysctl').stdout)

    def test_legacy_and_firewall_checks(self):
        for name in ['passwall', 'passwall_server', 'firewall', 'zram']:
            self.make_script(name, procd=False)
        (self.root / 'proc/123').mkdir()
        (self.root / 'proc/123/cmdline').write_bytes(
            b'/tmp/etc/passwall/bin/xray\0run\0-c\0/tmp/etc/passwall/global.json\0')
        self.assertEqual(self.call('is-active', 'openwrt@passwall').returncode, 0)
        self.assertEqual(self.call('is-active', 'openwrt@passwall_server').returncode, 3)
        self.assertEqual(self.call('is-active', 'openwrt@firewall').returncode, 3)
        (self.root / 'firewall-active').touch()
        self.assertEqual(self.call('is-active', 'openwrt@firewall').returncode, 0)
        self.executable('usr/sbin/nft', '#!/bin/sh\nexit 1\n')
        self.assertEqual(self.call('is-active', 'openwrt@firewall').returncode, 4)
        (self.root / 'proc/swaps').write_text('Filename Type Size Used Priority\n/dev/zram0 partition 100 0 1\n')
        self.assertEqual(self.call('is-active', 'openwrt@zram').returncode, 0)

    def test_unknown_legacy_never_reports_success_as_health(self):
        self.make_script('third-party', procd=False)
        self.assertEqual(self.call('start', 'openwrt@third-party').returncode, 0)
        # A legacy script may still register dynamically with procd.
        self.set_snapshot({})
        result = self.call('status', 'openwrt@third-party')
        self.assertEqual(result.returncode, 4)
        self.assertIn('no health adapter', result.stdout)

    def test_failures_retain_script_exit_status(self):
        (self.root / 'fail-sample').touch()
        self.assertEqual(self.call('restart', 'openwrt@sample').returncode, 9)
        self.assertEqual(self.call('status', 'openwrt@sample').returncode, 3)
        self.assertIn('failed', self.call('status', 'openwrt@sample').stdout)

    def test_invalid_names_and_unavailable_bridge_never_run_an_action(self):
        for name in ['../sample', 'sample/../../x', 'sample;touch-x', 'sample%2f', 'sample\nx']:
            result = self.request(action='start', name=name)
            self.assertNotEqual(result['code'], 0)
        self.assertEqual(self.actions(), [])
        self.daemon.terminate()
        self.daemon.wait(timeout=5)
        result = self.call('start', 'openwrt@sample')
        self.assertEqual(result.returncode, 4)
        self.assertEqual(self.actions(), [])

    def test_native_ssh_is_excluded_from_bridge(self):
        self.make_script('sshd')
        for action in ('start', 'stop', 'restart', 'reload', 'enable', 'disable', 'status'):
            result = self.call(action, 'openwrt@sshd')
            self.assertEqual(result.returncode, 4)
            self.assertIn('sshd.service', result.stderr + result.stdout)
        self.assertEqual(self.actions(), [])

    def test_concurrent_actions_are_serialized(self):
        (self.root / 'slow').touch()
        a = subprocess.Popen(self.command('systemctl', 'restart', 'openwrt@sample'))
        b = subprocess.Popen(self.command('systemctl', 'reload', 'openwrt@sample'))
        self.assertEqual(a.wait(timeout=5), 0)
        self.assertEqual(b.wait(timeout=5), 0)
        self.assertCountEqual(self.actions(), ['sample:restart', 'sample:reload'])

    def test_obsolete_proxy_commands_are_rejected_without_actions(self):
        for command in [('generate', str(self.root)), ('proxy', 'sample')]:
            done = subprocess.run(self.command(*command), timeout=5)
            self.assertEqual(done.returncode, 2)
        self.assertEqual(self.actions(), [])
        self.assertFalse((self.root / 'native-actions').exists())

    def test_installed_image_has_adapter_coverage(self):
        root = TREE / 'build_dir/target-x86_64_glibc/root-x86-systemd'
        if not (root / 'etc/init.d').is_dir():
            self.skipTest('No staged image available')
        kinds = dict(line.split() for line in (SOURCE / 'files/service-kinds').read_text().splitlines()
                     if line.strip() and not line.startswith('#'))
        missing = [p.name for p in (root / 'etc/init.d').iterdir()
                   if p.is_file() and p.name not in ('dbus', 'sshd', 'umount')
                   and 'USE_PROCD=' not in p.read_text()
                   and p.name not in kinds]
        self.assertEqual(missing, [])

    def test_missing_stop_link_matches_original_enablement(self):
        self.call('enable', 'openwrt@sample')
        (self.root / 'etc/rc.d/K90sample').unlink()
        self.assertEqual(self.call('is-enabled', 'openwrt@sample').returncode, 1)

    def test_second_daemon_cannot_replace_live_socket(self):
        second = subprocess.run(self.command('daemon'), timeout=5)
        self.assertNotEqual(second.returncode, 0)
        self.assertEqual(self.call('status', 'openwrt@sample').returncode, 3)

    def test_invalid_later_argument_cannot_partially_execute(self):
        self.assertEqual(self.call('start', 'openwrt@sample', 'openwrt@../x').returncode, 2)
        self.assertEqual(self.actions(), [])

    def test_bridge_restart_preserves_receipts_and_never_restarts_services(self):
        self.make_script('sysctl', procd=False)
        subprocess.run(self.command('notify', 'sysctl', 'boot', '0'), check=True)
        self.wait_for(lambda: self.call('status', 'openwrt@sysctl').returncode == 0)
        self.call('start', 'openwrt@sample')
        self.daemon.terminate()
        self.daemon.wait(timeout=5)
        self.daemon = subprocess.Popen(self.command('daemon'), stdout=self.log, stderr=self.log)
        self.wait_for(lambda: self.call('status', 'openwrt@sample').returncode == 0)
        self.assertEqual(self.call('status', 'openwrt@sysctl').returncode, 0)
        self.assertEqual(self.actions(), ['sample:start'])

    def test_rc_common_observes_legacy_rc_symlink_and_preserves_exit_code(self):
        self.make_script('sysctl', procd=False)
        link = self.root / 'etc/rc.d/S20sysctl'
        link.symlink_to('../init.d/sysctl')
        helper = self.root / 'notify-helper'
        self.executable('notify-helper', '#!/bin/sh\nexec ' +
                        shlex.join(self.command()) + ' "$@"\n')
        original = (TREE / 'package/base-files/files/etc/rc.common').read_text()
        hook = original[original.index('rc_status=$?'):]
        hook = hook.replace('/run/openwrt-service-bridge/control',
                            str(self.root / 'run/openwrt-service-bridge/control'))
        hook = hook.replace('/usr/libexec/openwrt-service-bridge', str(helper))
        env = {**os.environ, 'initscript': str(link), 'action': 'boot', 'IPKG_INSTROOT': ''}
        done = subprocess.run(['sh', '-c', 'true\n' + hook], env=env)
        self.assertEqual(done.returncode, 0)
        self.wait_for(lambda: self.call('status', 'openwrt@sysctl').returncode == 0)
        env['action'] = 'start'
        done = subprocess.run(['sh', '-c', '(exit 7)\n' + hook], env=env)
        self.assertEqual(done.returncode, 7)
        self.wait_for(lambda: self.call('status', 'openwrt@sysctl').returncode == 3)

    def test_script_removal_prunes_receipts_without_stopping_workloads(self):
        self.make_script('sysctl', procd=False)
        subprocess.run(self.command('notify', 'sysctl', 'boot', '0'), check=True)
        receipt = self.root / 'run/openwrt-service-bridge/receipts/sysctl'
        self.wait_for(receipt.exists)
        (self.root / 'etc/init.d/sysctl').unlink()
        subprocess.run(self.command('refresh'), check=True)
        self.wait_for(lambda: not receipt.exists())
        self.assertFalse((self.root / 'native-actions').exists())
        self.assertFalse((self.root / 'run/openwrt-service-bridge/states').exists())

    def test_installed_scripts_are_discovered_without_manager_reload(self):
        self.make_script('new-service')
        self.assertEqual(self.call('start', 'openwrt@new-service').returncode, 0)
        self.assertEqual(self.actions(), ['new-service:start'])
        self.assertFalse((self.root / 'native-actions').exists())

    def test_placement_metadata_is_additive_and_does_not_replace_health(self):
        self.set_snapshot({'sample': {'instances': {
            'main': {'running': True, 'systemd_scope': 'openwrt-test.scope',
                     'systemd_placement': 'inherited'}}}})
        status = self.call('status', 'openwrt@sample')
        self.assertEqual(status.returncode, 0)
        self.assertIn('Cgroup main: inherited openwrt-test.scope', status.stdout)
        self.assertIn('1/1 instances running', status.stdout)

    def test_units_mode_placement_names_the_transient_service(self):
        self.set_snapshot({'sample': {'instances': {
            'main': {'running': True, 'systemd_unit': 'openwrt-sample@main.service',
                     'systemd_placement': 'unit'}}}})
        status = self.call('status', 'openwrt@sample')
        self.assertEqual(status.returncode, 0)
        self.assertIn('Cgroup main: unit openwrt-sample@main.service', status.stdout)
        self.assertIn('1/1 instances running', status.stdout)

    def test_status_traffic_does_not_create_manager_jobs(self):
        stop = threading.Event()
        failures = []

        def traffic():
            while not stop.is_set():
                try:
                    self.request(action='status', name='sample')
                except Exception as error:
                    failures.append(error)
                    return
                stop.wait(0.015)

        thread = threading.Thread(target=traffic)
        thread.start()
        try:
            self.make_script('busy-service')
            self.assertEqual(self.call('start', 'openwrt@busy-service').returncode, 0)
            self.assertEqual(failures, [])
            self.assertFalse((self.root / 'native-actions').exists())
        finally:
            stop.set()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
