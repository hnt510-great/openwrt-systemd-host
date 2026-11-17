#!/usr/bin/env python3
"""Exercise the opt-in gate and service lifecycle without touching the host."""
import os
import pathlib
import subprocess
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/custom/router-audit/files'


class AuditConfig(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = pathlib.Path(self.temp.name)
        self.env = dict(os.environ, PATH=str(self.work) + os.pathsep + os.environ['PATH'])
        self.env['AUDIT_TEST_LOG'] = str(self.work / 'calls')
        self.script('uci', '#!/bin/sh\n[ "$*" = "-q get router-audit.main.enabled" ] || exit 2\n'
                    '[ "${AUDIT_TEST_VALUE+x}" ] || exit 1\nprintf "%s\\n" "$AUDIT_TEST_VALUE"\n')
        self.script('systemctl', '#!/bin/sh\nprintf "%s\\n" "$*" >> "$AUDIT_TEST_LOG"\n')
        self.gate = self.script('router-audit-enabled', (FILES / 'router-audit-enabled').read_text())

    def script(self, name, source):
        path = self.work / name
        path.write_text(source)
        path.chmod(0o755)
        return path

    def test_gate_fails_closed(self):
        for value in (None, '', '0', 'true', 'yes', '2', '1\n0', '1'):
            with self.subTest(value=value):
                env = self.env.copy()
                if value is not None:
                    env['AUDIT_TEST_VALUE'] = value
                result = subprocess.run(['sh', str(self.gate)], env=env, capture_output=True)
                self.assertEqual(result.returncode, 0 if value == '1' else 1)

    def lifecycle(self, source, command, value):
        source = source.replace('/usr/libexec/router-audit-enabled', str(self.gate))
        env = dict(self.env, AUDIT_TEST_VALUE=value)
        log = self.work / 'calls'
        log.write_text('')
        subprocess.run(['sh', '-c', source + '\n' + command], env=env, check=True)
        return log.read_text().splitlines()

    def test_start_reload_stop(self):
        source = (FILES / 'router-audit.init').read_text()
        for value in ('0', '1'):
            with self.subTest(value=value):
                self.assertEqual(self.lifecycle(source, 'start_service', value),
                                 [('--no-block start' if value == '1' else 'stop') + ' router-audit-collect.service'])
                self.assertEqual(self.lifecycle(source, 'reload_service', value),
                                 [('restart' if value == '1' else 'stop') + ' router-audit-collect.service'])
                self.assertEqual(self.lifecycle(source, 'stop_service', value),
                                 ['stop router-audit-collect.service'])

    def test_upgrade_stops_old_collector_unless_enabled(self):
        recipe = (FILES.parent / 'Makefile').read_text()
        source = recipe.split('systemctl daemon-reload\n', 1)[1].split('\nexit 0', 1)[0]
        for value in ('0', '1'):
            with self.subTest(value=value):
                self.assertEqual(self.lifecycle(source, '', value),
                                 ['enable router-audit-collect.service',
                                  ('restart' if value == '1' else 'stop') + ' router-audit-collect.service'])

    def test_producer_environments_follow_switch(self):
        for name, relative, expected in (
            ('daed', 'package/custom/daed/files/daed.init',
             ['env ROUTER_AUDIT_DNS=1', 'env ROUTER_AUDIT_CONN=1']),
            ('dnsmasq', 'package/network/services/dnsmasq/files/dnsmasq.init',
             ['env ROUTER_AUDIT_DNS=1']),
        ):
            source = (ROOT / relative).read_text()
            start = source.index('\tif [ -x /usr/libexec/router-audit-enabled ]')
            block = source[start:source.index('\n\tfi', start) + len('\n\tfi')]
            mocks = ('procd_append_param() { systemctl "$@"; }\n'
                     'procd_set_param() { systemctl "$@"; }\n'
                     'mkdir() { :; }\n')
            for value in ('0', '1'):
                with self.subTest(producer=name, value=value):
                    calls = self.lifecycle(mocks + block, 'true', value)
                    self.assertEqual(calls, expected if value == '1' else [])


if __name__ == '__main__':
    unittest.main()
