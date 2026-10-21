#!/usr/bin/env python3
"""Run the real ucode RPC backend against isolated report/queue fixtures."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
SOURCE = TREE / 'package/custom/luci-app-needrestart/root/usr/share/rpcd/ucode/luci.needrestart'
UCODE = TREE / 'staging_dir/hostpkg/bin/ucode'


class BackendTests(unittest.TestCase):
    def setUp(self):
        if not UCODE.exists():
            self.skipTest('Host ucode interpreter required')
        self.directory = tempfile.TemporaryDirectory(prefix='needrestart-rpc-')
        self.root = Path(self.directory.name)
        self.boot = self.root / 'boot'
        self.boot.write_text('test-boot\n')
        self.command = self.root / 'needrestart'
        self.command.write_text('#!/bin/sh\nprintf "%s\\n" "$@" > "' + str(self.root / 'argv') + '"\n')
        self.command.chmod(0o755)
        self.source = SOURCE.read_text().replace("'/run/openwrt-needrestart/'", repr(str(self.root) + '/'))
        self.source = self.source.replace('/proc/sys/kernel/random/boot_id', str(self.boot))
        self.source = self.source.replace('/usr/sbin/needrestart', str(self.command))
        self.source = self.source.replace("return { 'luci.needrestart': {", "const methods = { 'luci.needrestart': {")

    def tearDown(self):
        if hasattr(self, 'directory'):
            self.directory.cleanup()

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(value))

    def call(self, method='status', args=None):
        script = self.root / 'run.uc'
        script.write_text(self.source + '\nprint(sprintf("%J", methods["luci.needrestart"].' +
                          method + '.call(' + json.dumps({'args': args or {}}) + ')));\n')
        p = subprocess.run([str(UCODE), str(script)], capture_output=True, text=True, timeout=10)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_missing_report(self):
        self.assertIsNone(self.call()['report'])

    def test_report_and_stale_boot(self):
        self.write('report.json', {'schema_version': 1, 'boot_id': 'test-boot', 'complete': True})
        self.assertTrue(self.call()['report']['complete'])
        self.boot.write_text('new-boot\n')
        self.assertEqual(self.call()['report']['scan_status'], 'stale')

    def test_bad_version_or_json_is_visible(self):
        self.write('report.json', {'schema_version': 5})
        self.assertIsNone(self.call()['report'])
        self.assertTrue(self.call()['error'])
        (self.root / 'report.json').write_text('{broken')
        self.assertTrue(self.call()['error'])

    def test_scan_error_and_pending(self):
        self.write('error.json', {'error': 'APK busy'})
        self.write('pending', {})
        r = self.call()
        self.assertEqual(r['error'], 'APK busy')
        self.assertTrue(r['pending'])

    def test_running_identity_and_dead_worker(self):
        pid = os.getpid()
        fields = Path(f'/proc/{pid}/stat').read_text().rsplit(') ', 1)[1].split()
        self.write('running', {'pid': pid, 'start_time': int(fields[19])})
        self.assertTrue(self.call()['running'])
        self.write('running', {'pid': pid, 'start_time': 1})
        r = self.call()
        self.assertFalse(r['running'])
        self.assertIn('exited', r['error'])

    def test_queue_ignores_caller_command_arguments(self):
        self.assertTrue(self.call('scan', {'command': 'reboot', 'path': '/etc/shadow'})['success'])
        self.assertEqual((self.root / 'argv').read_text(), '--queue\n')

    def test_queue_failure_visible(self):
        self.command.write_text('#!/bin/sh\nexit 1\n')
        self.assertFalse(self.call('scan')['success'])


if __name__ == '__main__':
    unittest.main()
