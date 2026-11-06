#!/usr/bin/env python3
"""Score a local OpenAI-compatible model on router-audit fixtures.

Skips (exit 0) without --endpoint. Never starts or installs a model server.

    python3 scripts/tests/router-audit-llm-eval.py --endpoint http://127.0.0.1:8080/v1 \
        --model NAME --fixtures DIR --out DIR [--sweep] [--tools] [--real DB]

Findings eval: explain.py on every fixture; scores valid JSON, category match, severity
within one level of the rule, the expected issue named in the summary, and nothing
invented for the quiet fixture. --sweep varies one setting at a time from the default
(budget 4000, text, thinking off, pipeline). --tools checks first tool choice for scripted
questions against the MCP tool schemas.
"""
import argparse
import importlib.machinery
import importlib.util
import json
import pathlib
import sys
import time
import urllib.request

sys.dont_write_bytecode = True
ROOT = pathlib.Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/custom/router-audit/files'


def load(name, path):
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


EX = load('router_audit_explain', FILES / 'explain.py')
AN = EX.A
FX = load('router_audit_fixtures', ROOT / 'scripts/tests/router-audit-fixtures.py')
DEFAULT = {'budget': 4000, 'format': 'llm', 'think': False, 'mode': 'pipeline'}
SWEEP = [('default', {}), ('budget-3k', {'budget': 3000}), ('budget-8k', {'budget': 8000}), ('budget-16k', {'budget': 16000}),
         ('llm-json', {'format': 'llm-json'}), ('agent', {'mode': 'agent'})]
# Thinking mode was measured on 2026-11-06 (no accuracy gain, 10-30x slower) and is no longer part of
# --sweep; run it explicitly with --only think-on.
OPTIONAL = [('think-on', {'think': True})]
QUESTIONS = [
    ('Is the internet connection stable right now?', [('router_topic', {'topic': 'wan'}), ('router_overview', {})]),
    ('Which device on my LAN is causing DNS errors?', [('router_topic', {'topic': 'clients'}), ('router_topic', {'topic': 'dns'})]),
    ('Explain finding F2 in detail.', [('router_finding', {'id': 'F2'})]),
    ('Were there any configuration changes in the last 24 hours?', [('router_topic', {'topic': 'changes', 'window': '24h'})]),
    ('Is the connection tracking table getting full?', [('router_topic', {'topic': 'conntrack'})]),
    ('Did any service crash or restart in the last hour?', [('router_topic', {'topic': 'services'}), ('router_overview', {})]),
    ('Do the logs show failed login attempts?', [('router_topic', {'topic': 'logs'})]),
    ('How busy are the CPU and memory?', [('router_topic', {'topic': 'system'})]),
    ('Give me an overall health report for the last 6 hours.', [('router_overview', {'window': '6h'})]),
    ('Which firewall rules see the most traffic?', [('router_topic', {'topic': 'firewall'})]),
]
LEVEL = {s: i for i, s in enumerate(AN.SEVERITIES)}


def models(endpoint):
    with urllib.request.urlopen(endpoint.rstrip('/') + '/models', timeout=10) as response:
        return [m.get('id') for m in json.loads(response.read()).get('data', [])]


def score(report, spec):
    findings = {f['id']: f for f in report['findings']}
    assessments = report['assessments']
    answered = [a for a in assessments if a.get('model')]
    summary = report.get('summary')
    top = [i['id'] for i in (summary or {}).get('top_issues', [])]
    expected = spec['expected']
    result = {
        'valid': (len(answered) + (summary is not None)) / (len(assessments) + 1),
        'category': sum(a['model']['category'] == a['category'] for a in answered) / len(answered) if answered else None,
        'severity': sum(abs(LEVEL[a['model']['severity']] - LEVEL[a['rule_severity']]) <= 1 for a in answered) / len(answered) if answered else None,
        'invented_ids': sum(i not in findings for i in top),
        'timed_out': float(bool(report.get('timed_out'))),
        'seconds': report['seconds'],
        'completion_tokens': sum(c.get('completion_tokens') or 0 for c in report['calls']),
        'prompt_tokens': sum(c.get('prompt_tokens') or 0 for c in report['calls']),
    }
    if expected:
        wanted = {e['category'] for e in expected}
        result['named_expected'] = float(any(findings.get(i, {}).get('category') in wanted for i in top))
        result['overall_ok'] = float(bool(summary) and summary['overall'] != 'ok')
    else:
        result['named_expected'] = None
        result['overall_ok'] = float(bool(summary) and summary['overall'] == 'ok' and not top)
    return result


def mean(values):
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def eval_findings(args, fixtures, manifest, label, settings, out):
    rows = {}
    existing = {name: out / ('%s-%s.json' % (label, name)) for name in manifest}
    started = any(p.exists() for p in existing.values())
    for name, spec in manifest.items():
        if args.resume and existing[name].exists():
            report = json.loads(existing[name].read_text())
            rows[name] = score(report, spec)
            print('  %-16s %s (resumed)' % (name, json.dumps(rows[name])), flush=True)
            continue
        if args.resume and started:
            rows[name] = {'skipped': 'run was stopped before this fixture'}
            print('  %-16s skipped (stopped run)' % name, flush=True)
            continue
        with AN.Analysis(fixtures / ('%s.sqlite' % name)) as analysis:
            client = EX.Client(args.endpoint, args.model, args.timeout, settings['think'], args.extra_system,
                               time_budget=args.fixture_timeout, think_tokens=args.think_tokens)
            try:
                report = EX.run(analysis, client, settings['mode'], settings['budget'], settings['format'], args.max_findings)
            except EX.ModelError as error:
                rows[name] = {'error': str(error)}
                continue
        existing[name].write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        rows[name] = score(report, spec)
        print('  %-16s %s' % (name, json.dumps(rows[name])), flush=True)
    keys = ('valid', 'category', 'severity', 'named_expected', 'overall_ok', 'timed_out', 'invented_ids', 'seconds', 'completion_tokens', 'prompt_tokens')
    scored = [r for r in rows.values() if 'valid' in r]
    totals = {k: mean([r.get(k) for r in scored]) if k not in ('invented_ids', 'seconds', 'completion_tokens', 'prompt_tokens')
              else sum(r.get(k) or 0 for r in scored) for k in keys}
    totals['fixtures_scored'] = len(scored)
    return {'label': label, 'settings': settings, 'fixtures': rows, 'totals': totals}


def eval_tools(args, fixtures):
    mcp = EX.McpClient(fixtures / 'failed_unit.sqlite')
    tools = mcp.openai_tools()
    mcp.close()
    client = EX.Client(args.endpoint, args.model, args.timeout, False, args.extra_system, time_budget=args.fixture_timeout * 2)
    rows = []
    for question, accepted in QUESTIONS:
        messages = [client.system(EX.prompt('agent.txt')), {'role': 'user', 'content': question}]
        try:
            message = client.chat(messages, tools=tools, max_tokens=300, label='tool')
        except EX.ModelError as error:
            rows.append({'question': question, 'ok': False, 'error': str(error)})
            continue
        calls = message.get('tool_calls') or []
        call = calls[0]['function'] if calls else None
        try:
            arguments = json.loads(call.get('arguments') or '{}') if call else None
        except ValueError:
            arguments = None
        ok = bool(call) and isinstance(arguments, dict) and any(
            call.get('name') == name and all(arguments.get(k) == v for k, v in want.items()) for name, want in accepted)
        rows.append({'question': question, 'ok': ok, 'tool': call.get('name') if call else None, 'arguments': arguments})
        print('  %-5s %s -> %s %s' % ('ok' if ok else 'MISS', question, rows[-1]['tool'], json.dumps(arguments)), flush=True)
    return {'accuracy': sum(r['ok'] for r in rows) / len(rows), 'questions': rows,
            'seconds': round(sum(c['seconds'] for c in client.calls), 1)}


def markdown(results):
    lines = ['# router-audit LLM eval: `%s`' % results['model'], '', 'Endpoint %s, %s.' % (results['endpoint'], results['date']), '',
             '| Run | Fixtures | Valid JSON | Category | Severity ±1 | Expected named | Overall right | Timed out | Invented IDs | Seconds | Output tokens |',
             '|---|---|---|---|---|---|---|---|---|---|---|']
    fmt = lambda v: '—' if v is None else ('%.0f%%' % (v * 100) if isinstance(v, float) and v <= 1 else ('%g' % round(v, 1)))
    for run in results['runs']:
        t = run['totals']
        lines.append('| %s | %d | %s | %s | %s | %s | %s | %s | %d | %.0f | %d |' % (
            run['label'], t['fixtures_scored'], fmt(t['valid']), fmt(t['category']), fmt(t['severity']), fmt(t['named_expected']),
            fmt(t['overall_ok']), fmt(t['timed_out']), t['invented_ids'], t['seconds'], t['completion_tokens']))
    if results.get('tools'):
        lines += ['', 'Tool choice: %.0f%% of %d questions (%.0f s).' % (results['tools']['accuracy'] * 100, len(results['tools']['questions']),
                                                                         results['tools']['seconds'])]
        lines += ['- %s %s → %s %s' % ('ok' if r['ok'] else 'MISS', r['question'], r.get('tool'), json.dumps(r.get('arguments')))
                  for r in results['tools']['questions']]
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--endpoint')
    p.add_argument('--model', default='local')
    p.add_argument('--fixtures', help='fixture directory (built with 7 baseline days when missing)')
    p.add_argument('--out', required='--endpoint' in sys.argv)
    p.add_argument('--sweep', action='store_true')
    p.add_argument('--tools', action='store_true')
    p.add_argument('--real', help='also explain this real puller database with the default settings')
    p.add_argument('--max-findings', type=int, default=8)
    p.add_argument('--timeout', type=int, default=120, help='seconds per model request')
    p.add_argument('--fixture-timeout', type=int, default=300, help='seconds per fixture run (all its requests)')
    p.add_argument('--think-tokens', type=int, default=2048)
    p.add_argument('--resume', action='store_true', help='reuse finished per-fixture reports; a stopped run is not continued')
    p.add_argument('--only', help='comma-separated sweep labels to run')
    p.add_argument('--extra-system', default='')
    args = p.parse_args()
    if not args.endpoint:
        print('skipped: no --endpoint given')
        return
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    fixtures = pathlib.Path(args.fixtures) if args.fixtures else out / 'fixtures'
    if not (fixtures / 'manifest.json').exists():
        FX.build_all(fixtures)
    manifest = json.loads((fixtures / 'manifest.json').read_text())['fixtures']
    results = {'model': args.model, 'endpoint': args.endpoint, 'served_models': models(args.endpoint),
               'date': time.strftime('%Y-%m-%d %H:%M %Z'), 'runs': []}
    selected = SWEEP if args.sweep else SWEEP[:1]
    if args.only:
        wanted = set(args.only.split(','))
        selected = [s for s in SWEEP + OPTIONAL if s[0] in wanted]
    for label, change in selected:
        settings = dict(DEFAULT, **change)
        print('%s %s' % (label, json.dumps(settings)), flush=True)
        results['runs'].append(eval_findings(args, fixtures, manifest, label, settings, out))
    if args.tools:
        print('tools', flush=True)
        results['tools'] = eval_tools(args, fixtures)
    if args.real:
        with AN.Analysis(args.real) as analysis:
            client = EX.Client(args.endpoint, args.model, args.timeout, False, args.extra_system, time_budget=args.fixture_timeout)
            report = EX.run(analysis, client, 'pipeline', DEFAULT['budget'], DEFAULT['format'], args.max_findings)
        (out / 'real-report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        (out / 'real-report.md').write_text(EX.markdown(report))
        results['real'] = {'findings': len(report['findings']), 'seconds': report['seconds'], 'summary': report['summary']}
    (out / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
    (out / 'results.md').write_text(markdown(results))
    print(markdown(results))


if __name__ == '__main__':
    main()
