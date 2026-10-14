#!/usr/bin/env python3
"""Check the journal RPC command boundary using the real ucode runtime."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'package/custom/luci-app-systemd-journal/root/usr/share/rpcd/ucode/luci.journal'
UCODE = ROOT / 'staging_dir/hostpkg/bin/ucode'


class JournalTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='luci-journal-test-')
        self.work = Path(self.temp.name)
        self.calls = self.work / 'calls.json'
        fake = self.work / 'journalctl'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys, time
with open(os.environ['JOURNAL_TEST_CALLS'], 'w') as f:
    json.dump(sys.argv[1:], f)
mode = os.environ.get('JOURNAL_TEST_MODE', '')
if mode == 'hang':
    time.sleep(20)
if mode == 'failure':
    print('No journal boot found')
    sys.exit(1)
if mode == 'large':
    print('x' * 400000)
else:
    print('2026-10-15T00:00:00+08:00 router example[42]: <script>unsafe HTML</script>')
''')
        fake.chmod(0o755)
        self.source = SOURCE.read_text().replace('/usr/bin/journalctl', str(fake))
        self.env = dict(os.environ, JOURNAL_TEST_CALLS=str(self.calls))

    def tearDown(self):
        self.temp.cleanup()

    def call(self, **overrides):
        args = dict(boot='current', unit='', priority='all', lines=300)
        args.update(overrides)
        source = self.source.rsplit("return { 'luci.journal': methods };", 1)[0]
        script = self.work / 'run.uc'
        script.write_text(source + 'print(sprintf("%J", methods.read.call(' +
                          json.dumps({'args': args}) + ')));\n')
        result = subprocess.run([str(UCODE), str(script)], env=self.env,
                                capture_output=True, text=True, check=True, timeout=8)
        return json.loads(result.stdout)

    def test_fixed_read_only_command(self):
        result = self.call(unit='example@instance.service', priority='3', lines=100)
        self.assertTrue(result['success'])
        self.assertIn('<script>', result['log'])
        self.assertEqual(json.loads(self.calls.read_text()), [
            '--no-pager', '--quiet', '--output=short-iso', '--lines=100',
            '--boot=0', '--unit=example@instance.service', '--priority=3'])
        self.assertFalse(result['truncated'])

    def test_rpc_schema_uses_typed_examples(self):
        source = self.source.rsplit("return { 'luci.journal': methods };", 1)[0]
        script = self.work / 'schema.uc'
        script.write_text(source + 'print(sprintf("%J", methods.read.args));\n')
        result = subprocess.check_output([str(UCODE), str(script)], text=True)
        schema = json.loads(result)
        self.assertIsInstance(schema['lines'], int)
        for name in ['boot', 'unit', 'priority']:
            self.assertIsInstance(schema[name], str)

    def test_boots(self):
        self.assertTrue(self.call(boot='previous')['success'])
        self.assertIn('--boot=-1', json.loads(self.calls.read_text()))
        self.assertTrue(self.call(boot='all')['success'])
        self.assertFalse(any(arg.startswith('--boot') for arg in json.loads(self.calls.read_text())))

    def test_reject_unbounded_or_hostile_arguments(self):
        for args in [dict(unit='x; reboot'), dict(unit='$(touch /tmp/injected)'),
                     dict(unit='example.service\n'), dict(unit='*'), dict(unit='a' * 257),
                     dict(unit=None), dict(boot='--vacuum-size=1'), dict(priority='8'),
                     dict(lines=0), dict(lines=1001), dict(lines='100')]:
            self.assertFalse(self.call(**args)['success'], args)
        self.assertFalse(self.calls.exists())

    def test_output_bound(self):
        self.env['JOURNAL_TEST_MODE'] = 'large'
        result = self.call()
        self.assertTrue(result['success'])
        self.assertTrue(result['truncated'])
        self.assertEqual(len(result['log']), 262144)

    def test_failure_is_visible(self):
        self.env['JOURNAL_TEST_MODE'] = 'failure'
        result = self.call()
        self.assertFalse(result['success'])
        self.assertIn('No journal boot', result['error'])

    def test_timeout(self):
        self.env['JOURNAL_TEST_MODE'] = 'hang'
        result = self.call()
        self.assertFalse(result['success'])
        self.assertIn('timed out', result['error'])


if __name__ == '__main__':
    unittest.main()
