#!/usr/bin/env python3
"""Run the actual ucode backend against isolated accounts and a fake executor."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
APP = ROOT / 'package/custom/luci-app-podman'
UCODE = ROOT / 'staging_dir/hostpkg/bin/ucode'


class BackendTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='podman-rpc-test-')
        self.work = Path(self.temp.name)
        self.log = self.work / 'argv.jsonl'
        self.env = dict(os.environ, PODMAN_TEST_LOG=str(self.log))
        for name, contents in {
            'passwd': 'alice:x:1000:1000::/home/alice:/bin/sh\nbob:x:1001:1001::/home/bob:/bin/sh\nroot:x:0:0::/root:/bin/sh\nunmapped:x:1002:1002::/home/unmapped:/bin/sh\n',
            'subuid': 'alice:100000:65536\n1001:200000:65536\n',
            'subgid': 'alice:300000:65536\nbob:400000:65536\n',
        }.items():
            (self.work / name).write_text(contents)
        self.executor = self.work / 'exec'
        self.executor.write_text('''#!/usr/bin/env python3
import json, os, sys
with open(os.environ['PODMAN_TEST_LOG'], 'a') as f:
    f.write(json.dumps(sys.argv[1:]) + '\\n')
if os.environ.get('PODMAN_TEST_FAIL'):
    print('rootless runtime unavailable'); sys.exit(125)
if 'logs' in sys.argv:
    print('<script>literal log</script>')
elif 'info' in sys.argv:
    print('{"host":{"security":{"rootless":true}}}')
else:
    print('[]')
''')
        self.executor.chmod(0o755)
        worker = self.work / 'worker'
        worker.write_text((APP / 'root/usr/libexec/podman-luci-job').read_text()
                          .replace('/usr/libexec/podman-luci-exec', str(self.executor)))
        worker.chmod(0o755)
        self.source = (APP / 'root/usr/share/rpcd/ucode/luci.podman').read_text()
        self.source = self.source.replace("import { cursor } from 'uci';", '''
function cursor() { return { get: () => [ 'alice' ], unload: () => null }; }
''')
        for f in ['passwd', 'subuid', 'subgid']:
            self.source = self.source.replace('/etc/' + f, str(self.work / f))
        self.source = self.source.replace('/tmp/luci-podman-', str(self.work / 'job-'))
        self.source = self.source.replace('const JOB_UID = 0;', f'const JOB_UID = {os.getuid()};')
        self.source = self.source.replace('/usr/libexec/podman-luci-exec', str(self.executor))
        self.source = self.source.replace('/usr/libexec/podman-luci-job', str(worker))

    def tearDown(self):
        self.temp.cleanup()

    def call(self, method, **args):
        script = self.work / 'run.uc'
        script.write_text(self.source.rsplit("return { 'luci.podman': methods };", 1)[0] +
                          f'print(sprintf("%J", methods.{method}.call({json.dumps({"args": args})})));')
        result = subprocess.run([str(UCODE), str(script)], env=self.env, check=True,
                                capture_output=True, text=True, timeout=10)
        return json.loads(result.stdout)

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def action(self, resource, action, id='', **options):
        return self.call('action', user='alice', resource=resource, action=action,
                         id=id, options=json.dumps(options))

    def complete(self, result):
        self.assertTrue(result['success'], result)
        for _ in range(30):
            status = self.call('job', user='alice', job=result['job'])
            self.assertTrue(status['success'], status)
            if status['done']:
                self.assertEqual(status['code'], 0, status)
                return status
            time.sleep(0.05)
        self.fail('operation did not complete')

    def test_account_mapping_and_allowlist(self):
        users = self.call('accounts')['accounts']
        self.assertEqual([u['user'] for u in users], ['alice', 'bob'])
        self.assertEqual([u['allowed'] for u in users], [True, False])
        for user in ['bob', 'root', 'unmapped', "alice'; id", 'alice\n']:
            self.assertFalse(self.call('list', user=user, resource='info')['success'])
        self.assertEqual(self.calls(), [])

    def test_read_commands_and_failure(self):
        self.assertTrue(self.call('list', user='alice', resource='info')['data']['host']['security']['rootless'])
        self.assertEqual(self.call('list', user='alice', resource='containers')['data'], [])
        self.assertIn('<script>', self.call('detail', user='alice', resource='container', id='abc', logs=True)['data'])
        self.env['PODMAN_TEST_FAIL'] = '1'
        self.assertIn('runtime unavailable', self.call('list', user='alice', resource='info')['error'])

    def test_identifier_and_action_rejection(self):
        for ident in ['--all', 'name;touch /tmp/injected', 'abc\n', '../root']:
            self.assertFalse(self.action('container', 'rm', ident)['success'])
        for action in ['reset', 'prune', 'exec', 'kill']:
            self.assertFalse(self.action('container', action, 'abc')['success'])
        self.assertFalse(self.call('detail', user='alice', resource='container', id='--all', logs=False)['success'])
        self.assertFalse(self.call('job', user='alice', job='../abc')['success'])
        self.assertEqual(self.calls(), [])

    def test_background_mutations_and_argv_quoting(self):
        hostile = "SECRET='quoted'; $(touch /tmp/podman-injected) `id`"
        self.complete(self.action('container', 'create', name='test', image='docker.io/library/alpine:3.23',
                                  env=[hostile], command=['sh', '-c', 'echo "hello world"'], ports=['8080:80/tcp'],
                                  volumes=['data:/data:ro'], restart='no'))
        args = self.calls()[0]
        self.assertEqual(args[:5], ['alice', 'create', '--pull=never', '--name', 'test'])
        self.assertEqual(args[args.index('--env') + 1], hostile)
        self.assertEqual(args[-3:], ['sh', '-c', 'echo "hello world"'])
        self.complete(self.action('container', 'stop', 'abc'))
        self.assertEqual(self.calls()[-1], ['alice', 'container', 'stop', '--time=10', 'abc'])
        self.complete(self.action('pod', 'restart', 'test'))
        self.assertEqual(self.calls()[-1], ['alice', 'pod', 'restart', 'test'])

    def test_create_network_volume_pod_and_pull(self):
        for kind in ['network', 'volume', 'pod']:
            self.complete(self.action(kind, 'create', name='test'))
            expected = (['alice', 'pod', 'create', '--name', 'test', '--infra=false', '--share=']
                        if kind == 'pod' else ['alice', kind, 'create', 'test'])
            self.assertEqual(self.calls()[-1], expected)
        self.complete(self.action('pod', 'create', name='infra', infra_image='docker.io/library/alpine:3.23', infra_command='/bin/sleep 600'))
        self.assertEqual(self.calls()[-1], ['alice', 'pod', 'create', '--name', 'infra', '--infra-image',
                                           'docker.io/library/alpine:3.23', '--infra-command', '/bin/sleep 600'])
        self.complete(self.action('image', 'pull', image='docker.io/library/alpine:3.23'))
        self.assertEqual(self.calls()[-1], ['alice', 'pull', 'docker.io/library/alpine:3.23'])
        self.assertFalse(self.action('image', 'pull', image='alpine')['success'])

    def test_invalid_create_options(self):
        for overrides in [{'name': '--all'}, {'image': '--privileged'}, {'env': ['BAD']},
                          {'ports': ['--net=host']}, {'volumes': ['/etc']},
                          {'network': '--privileged'}, {'command': 'shell string'},
                          {'command': ['bad\x00argument']}, {'restart': '--privileged'}]:
            options = {'name': 'test', 'image': 'docker.io/library/alpine:3.23'} | overrides
            self.assertFalse(self.action('container', 'create', **options)['success'], overrides)
        self.assertEqual(self.calls(), [])

    def test_job_directory_symlink_rejected(self):
        (self.work / 'job-ABCDEF').symlink_to(self.work, target_is_directory=True)
        (self.work / 'owner').write_text('alice')
        (self.work / 'output').write_text('must not be returned')
        result = self.call('job', user='alice', job='ABCDEF')
        self.assertFalse(result['success'])


if __name__ == '__main__':
    unittest.main()
