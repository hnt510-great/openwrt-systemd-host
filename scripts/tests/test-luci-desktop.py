#!/usr/bin/env python3
"""Run the actual luci.desktop ucode backend with a stub desktop-ctl CLI."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'package/custom/luci-app-desktop/root/usr/share/rpcd/ucode/luci.desktop'
UCODE = ROOT / 'staging_dir/hostpkg/bin/ucode'


class LuciDesktopBackendTest(unittest.TestCase):
    def setUp(self):
        if not UCODE.exists():
            self.skipTest('host ucode binary is not built')
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.calls = self.work / 'calls.json'
        fake = self.work / 'desktop-ctl'
        fake.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['DESKTOP_CALLS'], 'w') as f:
    json.dump(sys.argv[1:], f)
mode = os.environ.get('DESKTOP_MODE', '')
if mode == 'large':
    print('x' * 600000)
elif mode == 'invalid':
    print('{}')
elif mode == 'error':
    print(json.dumps(dict(schema_version=1, ok=False, error=dict(code=2, message='Unavailable'))))
    sys.exit(2)
else:
    print(json.dumps(dict(schema_version=1, ok=True, error=None)))
''')
        fake.chmod(0o755)
        source = SOURCE.read_text().replace('/usr/sbin/desktop-ctl', str(fake))
        self.source = source.replace("return { 'luci.desktop': {", "const methods = {").rsplit('} };', 1)[0] + '};\n'
        self.env = dict(os.environ, DESKTOP_CALLS=str(self.calls))

    def call(self, method, **args):
        script = self.work / 'run.uc'
        script.write_text(self.source + 'print(sprintf("%J", methods.' + method + '.call(' + json.dumps(dict(args=args)) + ')));\n')
        p = subprocess.run([str(UCODE), str(script)], env=self.env, capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 0, p.stderr)
        return json.loads(p.stdout)

    def test_valid_methods_and_argv(self):
        self.assertTrue(self.call('status')['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'status'])

        self.assertTrue(self.call('logs', lines=50)['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'logs', '--lines', '50'])

        for verb in ('start', 'stop', 'restart', 'reload'):
            self.assertTrue(self.call('action', verb=verb)['ok'])
            self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'action', verb])

        self.assertTrue(self.call('switch', session='plasma-wayland_1')['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'switch', '--session', 'plasma-wayland_1'])

        self.assertTrue(self.call('sync_boot')['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'sync-boot'])

        self.assertTrue(self.call('sync_sunshine')['ok'])
        self.assertEqual(json.loads(self.calls.read_text()), ['--json', 'sync-sunshine'])

    def test_rejects_injection_and_invalid_arguments(self):
        for verb in ('enable', 'disable', 'restart;id', '', None, 'start\n'):
            self.assertFalse(self.call('action', verb=verb)['ok'])
        for session in ('', '../gnome', 'gnome;id', '-bad', 'Upper', 'a' * 33, None):
            self.assertFalse(self.call('switch', session=session)['ok'])
        for lines in (0, -5, 201, '100'):
            self.assertFalse(self.call('logs', lines=lines)['ok'])
        self.assertFalse(self.calls.exists())

    def test_cap_invalid_and_error(self):
        for mode in ('large', 'invalid', 'error'):
            self.env['DESKTOP_MODE'] = mode
            data = self.call('status')
            self.assertFalse(data['ok'], mode)
            self.assertEqual(data['schema_version'], 1)
        self.assertEqual(data['error']['code'], 2)

    def test_acl_separates_read_and_write(self):
        acl = json.loads((SOURCE.parent.parent / 'acl.d/luci-app-desktop.json').read_text())['luci-app-desktop']
        self.assertEqual(acl['read']['ubus']['luci.desktop'], ['status', 'logs'])
        self.assertEqual(acl['write']['ubus']['luci.desktop'], ['action', 'switch', 'sync_boot', 'sync_sunshine'])
        self.assertNotIn('file', acl['read'])
        self.assertNotIn('file', acl['write'])


if __name__ == '__main__':
    unittest.main()
