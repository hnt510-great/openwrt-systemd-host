#!/usr/bin/env python3
"""Source tests for router-audit; no router and no model needed. Hardware checks are recorded in docs."""
import http.server
import importlib.machinery
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
root = pathlib.Path(__file__).resolve().parents[2]
files = root / 'package/custom/router-audit/files'


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


A = load('router_audit', files / 'router-audit')
N = load('router_audit_normalize_test', files / 'normalize.py')
AN = load('router_audit_analyze_test', files / 'analyze.py')
EX = load('router_audit_explain_test', files / 'explain.py')
FX = load('router_audit_fixtures', root / 'scripts/tests/router-audit-fixtures.py')


class Collector(unittest.TestCase):
    def test_duration_bounds(self):
        self.assertEqual(A.parse_since('15m'), 900)
        for value in ['0m', '31d', '15m;id', '../../../etc/shadow']:
            with self.assertRaises(Exception):
                A.parse_since(value)

    def test_independent_failure(self):
        def fail():
            raise OSError('secret should not appear')
        with patch.dict(A.MODULES, {'fixture': fail, 'healthy': lambda: {'value': 1}}):
            r = A.envelope('fixture', 0, 10)
            self.assertEqual(r['status'], 'error')
            self.assertNotIn('secret', str(r))
            self.assertEqual(A.envelope('healthy', 0, 10)['status'], 'ok')
            self.assertEqual(A.envelope('healthy', 0, 10)['schema_version'], '1.1')

    def test_internal_queries_separate(self):
        rows = [{'source': 'dnsmasq', 'client': '127.0.0.1', 'qname': 'x.example', 'qtype': 1, 'rcode': 0},
                {'source': 'daed', 'client': '192.0.2.1:123', 'qname': 'x.example.', 'qtype': 1, 'rcode': 3}]
        out = A.dns_summary(rows)['clients']
        self.assertEqual(len(out), 2)
        self.assertTrue(out[0]['internal'])
        self.assertFalse(out[1]['internal'])
        self.assertEqual(out[1]['rcodes']['3'], 1)

    def test_daed_ports_group_into_one_client(self):
        rows = [{'source': 'daed', 'client': '192.0.2.1:%d' % port, 'qname': 'a.example.', 'qtype': 1, 'rcode': 0} for port in (1000, 2000, 3000)]
        rows.append({'source': 'daed', 'client': '127.0.0.1:5353', 'qname': 'a.example.', 'qtype': 1, 'rcode': 0})
        out = {c['client']: c for c in A.dns_summary(rows)['clients']}
        self.assertEqual(out['192.0.2.1']['queries'], 3)
        self.assertTrue(out['127.0.0.1']['internal'])

    def test_missing_source(self):
        self.assertIsNone(A.command(['/nonexistent/router-audit-fixture']))
        self.assertTrue(A.ERR)

    def test_iso_window(self):
        self.assertTrue(A.envelope('capabilities', 0, 10)['window']['start'].endswith('Z'))


class Normalize(unittest.TestCase):
    def test_client_addr(self):
        cases = {'192.0.2.1:123': ('192.0.2.1', 123), '[2001:db8::1]:53': ('2001:db8::1', 53), '::ffff:192.0.2.1': ('192.0.2.1', None),
                 '2001:db8::5': ('2001:db8::5', None), '127.0.0.1': ('127.0.0.1', None), '[::1]:40000': ('::1', 40000),
                 'fe80::1%br-lan': ('fe80::1', None), '': ('unknown', None), None: ('unknown', None)}
        for value, expected in cases.items():
            self.assertEqual(N.client_addr(value), expected, value)
        self.assertTrue(N.is_internal(N.client_addr('[::1]:9')[0]))

    def test_parsers(self):
        self.assertEqual(N.parse_cpu('cpu  10 1 5 100 2 0 3 0 0 0')['idle'], 100)
        psi = N.parse_pressure('some avg10=0.10 avg60=2.50 avg300=0.00 total=77\nfull avg10=0.00 avg60=0.00 avg300=0.00 total=5\n')
        self.assertEqual(psi['some']['avg60'], 2.5)
        self.assertEqual(psi['full']['total'], 5)
        units = N.parse_systemctl_show('Id=a.service\nActiveState=active\nNRestarts=2\n\nId=b.service\nActiveState=failed\nNRestarts=0\n')
        self.assertEqual([u['Id'] for u in units], ['a.service', 'b.service'])
        self.assertEqual(units[0]['NRestarts'], 2)
        self.assertEqual(N.parse_failed_units('● x.service loaded failed failed X\ny.service loaded failed failed Y\n'), ['x.service', 'y.service'])
        stats = N.parse_conntrack_stats('entries  insert_failed drop\n000000e2 00000001 00000002\n000000e2 00000003 00000000\n')
        self.assertEqual(stats, {'entries': 0xe2, 'insert_failed': 4, 'drop': 2})
        self.assertEqual(N.parse_conntrack({'count': '12\n', 'max': '100\n', 'acct': None})['count'], 12)
        rules = N.firewall_rules({'nftables': [
            {'rule': {'family': 'inet', 'table': 'fw4', 'chain': 'input', 'handle': 1, 'comment': '!fw4: x', 'expr': [{'counter': {'packets': 1, 'bytes': 2}}]}},
            {'rule': {'family': 'inet', 'table': 'fw4', 'chain': 'input', 'handle': 2, 'expr': [{'accept': None}]}},
            {'rule': {'family': 'inet', 'table': 'fw4', 'chain': 'input', 'handle': 3, 'comment': 'only comment', 'expr': []}}]})
        self.assertEqual([(r['handle'], r['comment']) for r in rules], [(1, '!fw4: x'), (3, 'only comment')])
        self.assertEqual(N.parse_virsh_list(' Id   Name   State\n----------------------\n 1    vm1    running\n -    vm2    shut off\n'),
                         [{'id': '1', 'name': 'vm1', 'state': 'running'}, {'id': None, 'name': 'vm2', 'state': 'shut off'}])
        self.assertEqual(N.parse_ps('  1000  4242 conmon\n')[0]['pid'], 4242)
        self.assertEqual([l['ifname'] for l in N.trim_links([{'ifname': 'lo'}, {'ifname': 'eth0', 'address': 'aa'}])], ['eth0'])

    def test_iso(self):
        self.assertEqual(N.iso(0), '1970-01-01T00:00:00Z')
        self.assertEqual(N.iso('1700000000'), '2023-11-14T22:13:20Z')
        self.assertEqual(N.iso_us('1700000000500000'), '2023-11-14T22:13:20.500000Z')
        self.assertEqual(N.iso_text('2023-11-14T22:13:20+00:00'), '2023-11-14T22:13:20Z')
        self.assertIsNone(N.iso(None))

    def test_upgrade(self):
        record = {'schema_version': '1.0', 'module': 'system', 'collected_at': '2026-01-01T00:00:00Z',
                  'window': {'start': '2026-01-01T00:00:00+00:00', 'end': '2026-01-01T00:02:00Z'},
                  'data': {'memory_bytes': {'MemTotal': 100, 'MemAvailable': 50, 'VmallocTotal': 9}, 'cpu_ticks': 'cpu  1 2 3 4 5 6 7 8 0 0',
                           'pressure': {'memory': 'some avg10=0.00 avg60=1.00 avg300=0.00 total=1\n'}}}
        up = N.upgrade(record)
        self.assertEqual(up['schema_version'], '1.1')
        self.assertEqual(up['upgraded_from'], '1.0')
        self.assertEqual(up['data']['memory'], {'MemTotal': 100, 'MemAvailable': 50})
        self.assertEqual(up['data']['cpu']['steal'], 8)
        self.assertEqual(up['data']['pressure']['memory']['some']['avg60'], 1.0)
        self.assertEqual(up['window']['start'], '2026-01-01T00:00:00Z')
        self.assertEqual(record['schema_version'], '1.0', 'upgrade must not mutate its input')
        dns = N.upgrade({'schema_version': '1.0', 'module': 'dns_queries', 'data': {'events': [{'client': '192.0.2.9:5000', 'event_time': '2026-01-01T00:00:00+00:00'}]}})
        self.assertEqual(dns['data']['events'][0]['client'], '192.0.2.9')
        self.assertEqual(dns['data']['events'][0]['client_port'], 5000)
        minute = N.upgrade({'schema_version': '1.0', 'module': 'dns_minute', 'data': {'clients': [
            {'source': 'daed', 'client': '192.0.2.9:1', 'queries': 2, 'rcodes': {'0': 2}, 'qtypes': {'1': 2}, 'unique_domains': 2, 'length_max': 5},
            {'source': 'daed', 'client': '192.0.2.9:2', 'queries': 1, 'rcodes': {'3': 1}, 'qtypes': {'1': 1}, 'unique_domains': 1, 'length_max': 9}]}})
        self.assertEqual(minute['data']['clients'], [{'source': 'daed', 'client': '192.0.2.9', 'internal': False, 'queries': 3,
                                                      'rcodes': {'0': 2, '3': 1}, 'qtypes': {'1': 3}, 'unique_domains': 2, 'length_max': 9}])
        events = N.upgrade({'schema_version': '1.0', 'module': 'events', 'data': {'events': [{'event_time_us': '1700000000000000', 'kind': 'oom'}]}})
        self.assertEqual(events['data']['events'][0]['event_time'], '2023-11-14T22:13:20Z')
        current = {'schema_version': '1.1', 'module': 'system', 'data': {}}
        self.assertIs(N.upgrade(current), current)


_FIXTURES = {}


def fixture_dir():
    """Build the synthetic databases once per test run (2 baseline days keep it fast)."""
    if not _FIXTURES:
        _FIXTURES['tmp'] = tempfile.TemporaryDirectory()
        _FIXTURES['dir'] = FX.build_all(_FIXTURES['tmp'].name, days=2, step=900, legacy_days=1)
        _FIXTURES['analyses'] = {}
    return _FIXTURES['dir']


class FixtureBase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = fixture_dir()
        cls.manifest = json.loads((cls.dir / 'manifest.json').read_text())['fixtures']

    def analysis(self, name):
        cache = _FIXTURES['analyses']
        if name not in cache:
            cache[name] = AN.Analysis(self.dir / ('%s.sqlite' % name), tz=AN.dt.timezone.utc)
        return cache[name]


class Fixtures(FixtureBase):
    def test_each_fault_is_found(self):
        for name, spec in self.manifest.items():
            found = self.analysis(name).findings()
            if not spec['expected']:
                self.assertEqual(found, [], name)
            for want in spec['expected']:
                match = [f for f in found if f['category'] == want['category']]
                self.assertTrue(match, '%s: no %s finding in %s' % (name, want['category'], [f['key'] for f in found]))
                self.assertEqual(max(match, key=lambda f: AN.SEVERITIES.index(f['severity']))['severity'], want['severity'], name)

    def test_quiet_state(self):
        an = self.analysis('quiet')
        state = an.state()
        self.assertEqual(state['samples'], 60)
        self.assertEqual(state['dns']['clients'], 6, 'daed ports must not create extra clients')
        self.assertTrue(all(b['verdict'] == 'normal' for b in state['baselines'].values()), state['baselines'])
        cpu = [v for _, v in an.cpu_series(an.base0, an.e1)]
        self.assertTrue(cpu and all(0 <= v <= 100 for v in cpu), 'reboot/counter reset must not produce bogus rates')

    def test_benign_patterns_not_reported(self):
        an = self.analysis('quiet')
        laptop = next(c for c in an.dns_clients() if c['client'] == '192.0.2.10')
        self.assertGreater(laptop['reverse_nx'], 30, 'fixture must contain failing PTR lookups')
        self.assertLess(laptop['error_pct'], 20)
        self.assertEqual(an.findings(), [], 'clean one-shot exits and PTR NXDOMAIN are not findings')

    def test_short_history_has_no_baseline(self):
        an = self.analysis('quiet')
        with AN.Analysis(self.dir / 'quiet.sqlite', hours=1, end=AN.dt.datetime.fromtimestamp(an.e1 - 2 * 86400 + 4 * 3600, AN.dt.timezone.utc),
                         tz=AN.dt.timezone.utc) as early:
            b = early.baseline('cpu_pct')
        self.assertEqual(b['verdict'], 'no baseline')
        self.assertIn('needs 24h', early.baseline_text(b))

    def test_names_and_domains(self):
        an = self.analysis('nxdomain_storm')
        finding = an.findings()[0]
        self.assertIn('iot-cam (192.0.2.50)', finding['title'])
        self.assertEqual(an.name('2001:db8::10'), 'laptop (2001:db8::10)')
        self.assertEqual(AN.registrable('a.b.example.co.uk.'), 'example.co.uk')
        self.assertEqual(AN.registrable('x.y.example.com'), 'example.com')
        self.assertTrue(AN.high_entropy('mfrggzdfmztwq2lknnwg23tpobyxe43uov3ho6dzpi.t.example.net'))
        self.assertFalse(AN.high_entropy('www.example.com'))

    def test_render_budgets(self):
        an = self.analysis('memory_pressure')
        for budget in (500, 3000, 8000):
            text = AN.overview(an, budget)
            self.assertLessEqual(len(text), budget * 4)
            for f in an.findings():
                self.assertLessEqual(len(AN.finding_text(an, f, budget)), budget * 4)
        self.assertIn('[truncated:', AN.overview(an, 300))
        self.assertIn('series (10-minute', AN.finding_text(an, an.finding('memory_pressure'), 8000))
        self.assertNotIn('series (10-minute', AN.finding_text(an, an.finding('memory_pressure'), 4000))
        json.loads(AN.overview(an, 4000, 'llm-json'))
        for topic in AN.TOPICS:
            self.assertTrue(AN.topic_text(an, topic, 3000).startswith('TOPIC '))
        for text in [AN.overview(an)] + [AN.finding_text(an, f) for f in an.findings()]:
            self.assertNotIn('boot-', text)
            self.assertNotIn(FX.HOST, text)
        self.assertTrue(json.dumps(an.to_json(), default=str))

    def test_derived_cache_incremental(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = pathlib.Path(tmp) / 'r.sqlite'
            db.write_bytes((self.dir / 'quiet.sqlite').read_bytes())
            def processed():
                with AN.Analysis(db) as an:
                    return an.derived.db.execute('SELECT count(*) FROM processed').fetchone()[0]
            before = processed()
            self.assertEqual(processed(), before)
            src = AN.sqlite3.connect(str(db))
            row = src.execute("SELECT id, time, module, payload FROM batches WHERE module='system' ORDER BY time DESC LIMIT 1").fetchone()
            with src:
                src.execute('INSERT INTO batches VALUES(?,?,?,?)', (row[0] + 'x', row[1], row[2], row[3]))
            src.close()
            self.assertEqual(processed(), before + 1)


class FakeModel:
    """Local stand-in for an OpenAI-compatible server with scripted replies."""

    def __init__(self, replies):
        self.replies, self.requests = list(replies), []
        model = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                model.requests.append(body)
                status, reply = model.replies.pop(0) if model.replies else (500, {'error': 'no reply scripted'})
                if callable(reply):
                    reply = reply(body)
                data = json.dumps(reply).encode()
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Content-Length', str(len(data)))
                self.end_headers()
                self.wfile.write(data)
                self.close_connection = True

            def log_message(self, *args):
                pass

        self.server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.endpoint = 'http://127.0.0.1:%d/v1' % self.server.server_address[1]

    def close(self):
        self.server.shutdown()
        self.server.server_close()


def content(obj):
    return (200, {'choices': [{'message': {'role': 'assistant', 'content': obj if isinstance(obj, str) else json.dumps(obj)}}],
                  'usage': {'prompt_tokens': 10, 'completion_tokens': 5}, 'timings': {'prompt_per_second': 100.0, 'predicted_per_second': 20.0}})


GOOD = {'id': 'F1', 'severity': 'warning', 'category': 'dns', 'explanation': 'x', 'likely_causes': ['a'], 'next_checks': ['b'], 'confidence': 'low'}
SUMMARY = {'overall': 'attention', 'summary': 's', 'top_issues': [{'id': 'F1', 'why': 'w'}]}


class Explain(FixtureBase):
    def run_with(self, replies, **kw):
        model = FakeModel(replies)
        try:
            client = EX.Client(model.endpoint, 'fake', timeout=10)
            report = EX.run(self.analysis('nxdomain_storm'), client, max_findings=1, **kw)
        finally:
            model.close()
        return report, model

    def test_valid_answers(self):
        report, model = self.run_with([content(GOOD), content(SUMMARY)])
        self.assertEqual(report['assessments'][0]['model'], GOOD)
        self.assertEqual(report['summary'], SUMMARY)
        first = model.requests[0]
        self.assertEqual(first['response_format']['type'], 'json_schema')
        self.assertFalse(first['chat_template_kwargs']['enable_thinking'])
        self.assertEqual([m['role'] for m in first['messages']], ['system', 'user', 'assistant', 'user'])
        self.assertIn('FINDING F1', first['messages'][-1]['content'])
        self.assertEqual(report['calls'][0]['generation_tps'], 20.0)
        self.assertIn('Overall: attention', EX.markdown(report))

    def test_retry_then_valid(self):
        report, model = self.run_with([content('<think>hmm</think>not json'), content(GOOD), content(SUMMARY)])
        self.assertEqual(report['assessments'][0]['model'], GOOD)
        self.assertIn('invalid', model.requests[1]['messages'][-1]['content'])

    def test_invalid_twice_is_model_error(self):
        bad = dict(GOOD, severity='extreme')
        report, _ = self.run_with([content(bad), content(bad), content(SUMMARY)])
        self.assertIsNone(report['assessments'][0]['model'])
        self.assertTrue(report['assessments'][0]['error'].startswith('model_error'))
        self.assertEqual(report['summary'], SUMMARY)

    def test_json_object_fallback(self):
        report, model = self.run_with([(400, {'error': 'json_schema unsupported'}), content('```json\n%s\n```' % json.dumps(GOOD)), content(SUMMARY)])
        self.assertEqual(report['assessments'][0]['model'], GOOD)
        self.assertEqual(model.requests[1]['response_format'], {'type': 'json_object'})
        self.assertIn('must match this JSON schema', model.requests[1]['messages'][0]['content'])
        self.assertEqual(report['settings']['schema_mode'], 'json_object')

    def test_finding_fields_pinned(self):
        finding = self.analysis('conntrack_full').findings()[0]
        schema = EX.finding_schema(finding)
        self.assertEqual(schema['properties']['category']['enum'], ['conntrack'])
        self.assertTrue(EX.validate(dict(GOOD, id=finding['id'], category='network'), schema))
        self.assertEqual(EX.validate(dict(GOOD, id=finding['id'], category='conntrack'), schema), [])

    def test_summary_ids_restricted(self):
        schema = EX.summary_schema(self.analysis('failed_unit'))
        self.assertEqual(schema['properties']['top_issues']['maxItems'], 2)
        self.assertEqual(schema['properties']['top_issues']['items']['properties']['id']['enum'], ['F1', 'F2'])
        padded = {'overall': 'attention', 'summary': 's', 'top_issues': [{'id': 'F1', 'why': 'w'}, {'id': 'none', 'why': 'filler'}]}
        self.assertTrue(EX.validate(padded, schema))
        self.assertEqual(EX.summary_schema(self.analysis('quiet'))['properties']['top_issues']['maxItems'], 0)

    def test_time_budget(self):
        def slow(body):
            time.sleep(2)
            return content(GOOD)[1]
        model = FakeModel([(200, slow)] * 3)
        try:
            client = EX.Client(model.endpoint, 'fake', timeout=10, time_budget=1.5)
            report = EX.run(self.analysis('nxdomain_storm'), client, max_findings=1)
        finally:
            model.close()
        self.assertTrue(report['timed_out'])
        self.assertIsNone(report['summary'])
        self.assertLess(report['seconds'], 4)

    def test_think_tokens_capped(self):
        model = FakeModel([content(GOOD), content(SUMMARY)])
        try:
            client = EX.Client(model.endpoint, 'fake', timeout=10, think=True, think_tokens=1000)
            EX.run(self.analysis('nxdomain_storm'), client, max_findings=1)
        finally:
            model.close()
        self.assertEqual(model.requests[0]['max_tokens'], 1700)
        self.assertTrue(model.requests[0]['chat_template_kwargs']['enable_thinking'])

    def test_parse_and_validate(self):
        self.assertEqual(EX.parse_json('<think>x</think>\n```json\n{"a": 1}\n```'), {'a': 1})
        schema = EX.schema('finding.schema.json')
        self.assertEqual(EX.validate(GOOD, schema), [])
        self.assertTrue(EX.validate(dict(GOOD, extra=1), schema))
        self.assertTrue(EX.validate(dict(GOOD, likely_causes=['a'] * 4), schema))
        self.assertTrue(EX.validate(dict(GOOD, explanation='x' * 1000), schema))

    def test_agent_mode(self):
        def tool_call(body):
            self.assertTrue(body['tools'])
            return {'choices': [{'message': {'role': 'assistant', 'content': '', 'tool_calls': [
                {'id': 'c1', 'type': 'function', 'function': {'name': 'router_topic', 'arguments': '{"topic": "clients"}'}}]}}]}

        def after_tool(body):
            self.assertEqual(body['messages'][-1]['role'], 'tool')
            self.assertIn('TOPIC CLIENTS', body['messages'][-1]['content'])
            return content('iot-cam has DNS errors')[1]
        report, model = self.run_with([(200, tool_call), (200, after_tool), content(SUMMARY)], mode='agent')
        self.assertEqual(report['summary'], SUMMARY)
        self.assertEqual(report['agent_trace'][0]['tool'], 'router_topic')
        self.assertNotIn('tools', model.requests[-1])


class Mcp(FixtureBase):
    def test_stdio_protocol(self):
        db = self.dir / 'failed_unit.sqlite'
        messages = [
            {'jsonrpc': '2.0', 'id': 1, 'method': 'initialize', 'params': {'protocolVersion': '2025-06-18', 'capabilities': {}}},
            {'jsonrpc': '2.0', 'method': 'notifications/initialized'},
            {'jsonrpc': '2.0', 'id': 2, 'method': 'tools/list'},
            {'jsonrpc': '2.0', 'id': 3, 'method': 'tools/call', 'params': {'name': 'router_overview', 'arguments': {}}},
            {'jsonrpc': '2.0', 'id': 4, 'method': 'tools/call', 'params': {'name': 'router_finding', 'arguments': {'id': 'F1'}}},
            {'jsonrpc': '2.0', 'id': 5, 'method': 'tools/call', 'params': {'name': 'router_topic', 'arguments': {'topic': 'services', 'window': '6h'}}},
            {'jsonrpc': '2.0', 'id': 6, 'method': 'tools/call', 'params': {'name': 'router_topic', 'arguments': {'topic': 'everything'}}},
            {'jsonrpc': '2.0', 'id': 7, 'method': 'tools/call', 'params': {'name': 'router_finding', 'arguments': {'id': 'F99'}}},
            {'jsonrpc': '2.0', 'id': 8, 'method': 'tools/call', 'params': {'name': 'shell', 'arguments': {}}},
            {'jsonrpc': '2.0', 'id': 9, 'method': 'tools/call', 'params': {'name': 'router_overview', 'arguments': {'window': '9999h'}}},
            {'jsonrpc': '2.0', 'id': 10, 'method': 'ping'},
            {'jsonrpc': '2.0', 'id': 11, 'method': 'resources/list'},
        ]
        result = subprocess.run([sys.executable, '-I', str(files / 'mcp_server.py'), '--database', str(db)],
                                input=''.join(json.dumps(m) + '\n' for m in messages) + 'not json\n',
                                capture_output=True, text=True, timeout=60)
        self.assertEqual(result.returncode, 0, result.stderr)
        replies = {r['id']: r for r in map(json.loads, result.stdout.splitlines())}
        self.assertEqual(replies[1]['result']['protocolVersion'], '2025-06-18')
        self.assertEqual([t['name'] for t in replies[2]['result']['tools']], ['router_overview', 'router_finding', 'router_topic'])
        self.assertIn('ROUTER OVERVIEW', replies[3]['result']['content'][0]['text'])
        self.assertIn('FINDING F1', replies[4]['result']['content'][0]['text'])
        self.assertIn('TOPIC SERVICES', replies[5]['result']['content'][0]['text'])
        for bad in (6, 7, 9):
            self.assertTrue(replies[bad]['result']['isError'], replies[bad])
        self.assertEqual(replies[8]['error']['code'], -32602)
        self.assertEqual(replies[10]['result'], {})
        self.assertEqual(replies[11]['error']['code'], -32601)
        self.assertEqual(replies[None]['error']['code'], -32700)
        self.assertEqual(len(replies), 12, 'notifications get no reply')


if __name__ == '__main__':
    try:
        unittest.main()
    finally:
        if _FIXTURES:
            for an in _FIXTURES['analyses'].values():
                an.close()
            _FIXTURES['tmp'].cleanup()
