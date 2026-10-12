#!/usr/bin/env python3
"""Exercise the real ucode parser and command boundary with a fake virsh."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'package/custom/luci-app-qemu/root/usr/share/rpcd/ucode/luci.qemu'
UCODE = ROOT / 'staging_dir/hostpkg/bin/ucode'
UUID = '11111111-2222-3333-4444-555555555555'
NAME = "guest 'quoted' $(touch /tmp/luci-qemu-injected) <script>"


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luci-qemu-test-')
        self.work = Path(self.temp.name)
        self.log = self.work / 'calls.jsonl'
        fake = self.work / 'virsh'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ['QEMU_TEST_LOG'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
args = sys.argv[1:]
if os.environ.get('QEMU_TEST_HANG'):
    time.sleep(20)
if os.environ.get('QEMU_TEST_FAIL'):
    print('error: cannot connect to libvirt')
    sys.exit(1)
if 'list' in args:
    if not os.environ.get('QEMU_TEST_EMPTY'):
        print(os.environ['QEMU_TEST_UUID'] + ' ' + os.environ['QEMU_TEST_NAME'])
elif 'domstats' in args:
    print("Domain: '" + os.environ['QEMU_TEST_NAME'] + "'")
    print("""  state.state=1
  cpu.time=5000000000
  vcpu.current=2
  balloon.current=262144
  balloon.rss=32768
  net.0.rx.bytes=0
  net.1.rx.bytes=4096
  net.0.tx.bytes=512
  block.0.rd.bytes=1024
  block.1.rd.bytes=2048
  block.0.path=/a/path=999
  block.0.name=vda""")
else:
    print('request accepted')
''')
        fake.chmod(0o755)
        self.source = SOURCE.read_text().replace('/usr/bin/virsh', str(fake))
        self.env = dict(os.environ, QEMU_TEST_LOG=str(self.log),
                        QEMU_TEST_UUID=UUID, QEMU_TEST_NAME=NAME)

    def tearDown(self):
        self.temp.cleanup()

    def call(self, method, args=None):
        request = json.dumps({'args': args or {}})
        script = self.work / 'run.uc'
        source = self.source.rsplit("return { 'luci.qemu': methods };", 1)[0]
        script.write_text(source + f'print(sprintf("%J", methods.{method}.call({request})));\n')
        proc = subprocess.run([str(UCODE), str(script)], env=self.env,
                              check=True, capture_output=True, text=True, timeout=10)
        return json.loads(proc.stdout)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def test_stats_and_hostile_name(self):
        result = self.call('status')
        self.assertTrue(result['success'])
        vm = result['domains'][0]
        self.assertEqual((vm['uuid'], vm['name']), (UUID, NAME))
        self.assertEqual(vm['disk_read'], 3072)
        self.assertEqual(vm['net_rx'], 4096)
        self.assertIsNone(vm['disk_write'])
        self.assertEqual(vm['rss_kib'], 32768)
        self.assertGreater(result['timestamp'], 0)
        self.assertEqual(len(self.calls()), 2)
        self.assertTrue(all('--readonly' in call for call in self.calls()))

    def test_empty_list(self):
        self.env['QEMU_TEST_EMPTY'] = '1'
        self.assertEqual(self.call('status')['domains'], [])
        self.assertEqual(len(self.calls()), 1)

    def test_daemon_failure(self):
        self.env['QEMU_TEST_FAIL'] = '1'
        self.assertFalse(self.call('status')['success'])
        self.assertIn('cannot connect', self.call('action', {'uuid': UUID, 'action': 'start'})['error'])

    def test_actions_use_fixed_uri_and_uuid(self):
        for action in ['start', 'shutdown', 'reboot']:
            self.assertTrue(self.call('action', {'uuid': UUID, 'action': action})['success'])
        self.assertEqual(self.calls(), [
            ['--connect', 'qemu:///system', action, UUID]
            for action in ['start', 'shutdown', 'reboot']
        ])

    def test_stuck_client_is_bounded(self):
        self.env['QEMU_TEST_HANG'] = '1'
        result = self.call('status')
        self.assertFalse(result['success'])
        self.assertEqual(result['code'], 124)
        self.assertIn('timed out', result['error'])

    def test_reject_injection_and_unrequested_commands(self):
        for uuid in [UUID + '\n', UUID + ';touch /tmp/luci-qemu-injected', '--help', '', None]:
            self.assertFalse(self.call('action', {'uuid': uuid, 'action': 'start'})['success'])
        for action in ['destroy', 'reset', 'undefine', 'start;reboot', '', None]:
            self.assertFalse(self.call('action', {'uuid': UUID, 'action': action})['success'])
        self.assertEqual(self.calls(), [])


if __name__ == '__main__':
    unittest.main()
