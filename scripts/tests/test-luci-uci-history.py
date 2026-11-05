#!/usr/bin/env python3
"""Run the actual ucode backend with a stub CLI, preserving the command boundary."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'package/custom/luci-app-uci-history/root/usr/share/rpcd/ucode/luci.uci-history'
UCODE = ROOT / 'staging_dir/hostpkg/bin/ucode'


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.calls = self.work / 'calls.json'
        fake = self.work / 'cli'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['HISTORY_CALLS'], 'w') as f:
    json.dump(sys.argv[1:], f)
mode = os.environ.get('HISTORY_MODE', '')
if mode == 'large':
    print('x' * 1100000)
elif mode == 'invalid':
    print('{}')
elif mode == 'error':
    print(json.dumps(dict(schema_version=1, ok=False, error=dict(code=3, message='Conflict'))))
    sys.exit(3)
else:
    print(json.dumps(dict(schema_version=1, ok=True, error=None)))
''')
        fake.chmod(0o755)
        source = SOURCE.read_text().replace('/usr/sbin/uci-history', str(fake))
        self.source = source.replace("return { 'luci.uci-history': {", "const methods = {").rsplit('} };', 1)[0] + '};\n'
        self.env = dict(os.environ, HISTORY_CALLS=str(self.calls))

    def call(self, method, **args):
        script = self.work / 'run.uc'
        script.write_text(self.source + 'print(sprintf("%J", methods.' + method + '.call(' + json.dumps(dict(args=args)) + ')));\n')
        p = subprocess.run([str(UCODE), str(script)], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_fixed_methods_and_argv(self):
        for method in ('status', 'log'):
            self.assertTrue(self.call(method)['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'log', '--limit', '100'])
        self.assertTrue(self.call('diff', revision='12', format='unified', config='network')['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'diff', '12', '--format', 'unified', '--config', 'network'])
        self.assertTrue(self.call('restore', revision='12', configs=['network', 'dhcp'], timeout=90, dry_run=True)['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'restore', '12', '--config', 'network', '--config', 'dhcp', '--timeout', '90', '--dry-run'])
        for method in ('confirm', 'abort'):
            self.assertTrue(self.call(method, id='a' * 32)['ok'])
            self.assertEqual(json.loads(self.calls.read_text()), ['--json', method, '--id', 'a' * 32])

    def test_reject_injection_and_empty_restore(self):
        for revision in ('1;reboot', '1\n', '-1', '$(id)', '1' * 17, None):
            self.assertFalse(self.call('diff', revision=revision, format='uci', config='')['ok'])
        for configs in ([], ['network;id'], ['network\n'], ['--show-secrets'], 'network', [None], ['a'] * 129):
            self.assertFalse(self.call('restore', revision='1', configs=configs, timeout=90, dry_run=False)['ok'])
        for timeout in (0, 86401, '90'):
            self.assertFalse(self.call('restore', revision='1', configs=['network'], timeout=timeout, dry_run=False)['ok'])
        self.assertFalse(self.call('confirm', id='bad')['ok'])
        self.assertFalse(self.calls.exists())

    def test_cap_invalid_and_failure(self):
        for mode in ('large', 'invalid', 'error'):
            self.env['HISTORY_MODE'] = mode
            data = self.call('status')
            self.assertFalse(data['ok'], mode)
            self.assertEqual(data['schema_version'], 1)
        self.assertEqual(data['error']['code'], 3)

    def test_acl_separates_write(self):
        acl = json.loads((SOURCE.parent.parent / 'acl.d/luci-app-uci-history.json').read_text())['luci-app-uci-history']
        self.assertEqual(acl['read']['ubus']['luci.uci-history'], ['status', 'log', 'diff'])
        self.assertEqual(acl['write']['ubus']['luci.uci-history'], ['restore', 'confirm', 'abort'])


if __name__ == '__main__':
    unittest.main()
