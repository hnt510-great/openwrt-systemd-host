#!/usr/bin/python3
"""Explain router-audit findings with a local OpenAI-compatible model.

Talks only to POST <endpoint>/chat/completions (llama.cpp server, Ollama /v1, LM Studio,
vLLM). Answers are constrained with response_format json_schema, falling back to
json_object plus local validation when a server rejects schemas. Rule severity from the
analyzer stays authoritative; the model's assessment is reported beside it.

    explain.py DB --endpoint http://127.0.0.1:8080/v1 --model NAME [--window 1h]
               [--mode pipeline|agent] [--think off|on] [--budget 4000] [--out DIR]
"""
import argparse
import datetime as dt
import importlib.machinery
import importlib.util
import json
import pathlib
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request

HERE = pathlib.Path(__file__).resolve().parent
PROMPTS = HERE / 'prompts'


def _load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(HERE / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


A = _load('router_audit_analyze', 'analyze.py')
MAX_AGENT_CALLS = 6


class ModelError(Exception):
    pass


# ---------------------------------------------------------------- JSON handling

def parse_json(text):
    """Model reply -> object. Tolerates think blocks and code fences, nothing more."""
    if not isinstance(text, str):
        raise ValueError('empty reply')
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.S).strip()
    text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text).strip()
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end < start:
        raise ValueError('no JSON object in reply')
    return json.loads(text[start:end + 1])


def validate(value, schema, path='$'):
    """Validate the JSON-schema subset used by prompts/*.schema.json. Returns error strings."""
    errors = []
    kind = schema.get('type')
    if 'enum' in schema and value not in schema['enum']:
        return ['%s: %r not in %s' % (path, value, schema['enum'])]
    if kind == 'object':
        if not isinstance(value, dict):
            return ['%s: expected object' % path]
        for key in schema.get('required', []):
            if key not in value:
                errors.append('%s: missing %s' % (path, key))
        if schema.get('additionalProperties') is False:
            errors += ['%s: unexpected %s' % (path, k) for k in value if k not in schema.get('properties', {})]
        for key, sub in schema.get('properties', {}).items():
            if key in value:
                errors += validate(value[key], sub, '%s.%s' % (path, key))
    elif kind == 'array':
        if not isinstance(value, list):
            return ['%s: expected array' % path]
        if len(value) > schema.get('maxItems', len(value)):
            errors.append('%s: more than %d items' % (path, schema['maxItems']))
        for index, item in enumerate(value):
            errors += validate(item, schema.get('items', {}), '%s[%d]' % (path, index))
    elif kind == 'string':
        if not isinstance(value, str):
            return ['%s: expected string' % path]
        if len(value) > schema.get('maxLength', len(value)):
            errors.append('%s: longer than %d characters' % (path, schema['maxLength']))
    return errors


def prompt(name):
    return (PROMPTS / name).read_text()


def schema(name):
    return json.loads((PROMPTS / name).read_text())


# ---------------------------------------------------------------- model client

class Client:
    def __init__(self, endpoint, model, timeout=180, think=False, extra_system='', seed=42, temperature=0.2,
                 time_budget=None, think_tokens=2048):
        self.url = endpoint.rstrip('/') + '/chat/completions'
        self.model, self.timeout, self.think = model, timeout, think
        # Whole-run wall-clock budget: no new request starts after it, and a running one is cut off.
        self.deadline = time.monotonic() + time_budget if time_budget else None
        self.think_tokens = think_tokens
        self.extra_system, self.seed, self.temperature = extra_system, seed, temperature
        self.schema_mode = 'json_schema'
        self.calls = []

    def system(self, text):
        return {'role': 'system', 'content': text + ('\n' + self.extra_system if self.extra_system else '')}

    def remaining(self):
        return None if self.deadline is None else self.deadline - time.monotonic()

    def _post(self, payload):
        timeout = self.timeout
        left = self.remaining()
        if left is not None:
            if left <= 1:
                raise ModelError('time budget exceeded')
            timeout = min(timeout, left)
        request = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read())

    def chat(self, messages, response_schema=None, tools=None, max_tokens=700, label=''):
        payload = {'model': self.model, 'messages': messages, 'temperature': self.temperature, 'seed': self.seed,
                   'max_tokens': max_tokens + (self.think_tokens if self.think else 0),
                   'chat_template_kwargs': {'enable_thinking': bool(self.think)}}
        if tools:
            payload['tools'] = tools
        if response_schema is not None:
            if self.schema_mode == 'json_schema':
                payload['response_format'] = {'type': 'json_schema', 'json_schema': {'name': 'answer', 'strict': True, 'schema': response_schema}}
            else:
                # Server without schema support: describe the schema in the prompt instead.
                payload['response_format'] = {'type': 'json_object'}
                payload['messages'] = [dict(messages[0], content=messages[0]['content'] + '\nThe JSON object must match this JSON schema:\n'
                                            + json.dumps(response_schema))] + messages[1:]
        started = time.monotonic()
        try:
            reply = self._post(payload)
        except urllib.error.HTTPError as error:
            body = error.read().decode(errors='replace')[:300]
            error.close()
            if response_schema is not None and self.schema_mode == 'json_schema' and error.code in (400, 422, 500, 501):
                self.schema_mode = 'json_object'
                return self.chat(messages, response_schema, tools, max_tokens, label)
            raise ModelError('HTTP %d: %s' % (error.code, body))
        except TimeoutError:
            raise ModelError('request timed out')
        except (urllib.error.URLError, OSError) as error:
            if isinstance(getattr(error, 'reason', None), TimeoutError):
                raise ModelError('request timed out')
            raise ModelError('endpoint unreachable: %s' % error)
        elapsed = time.monotonic() - started
        usage = reply.get('usage') or {}
        timings = reply.get('timings') or {}
        self.calls.append({'label': label, 'seconds': round(elapsed, 2), 'prompt_tokens': usage.get('prompt_tokens'),
                           'completion_tokens': usage.get('completion_tokens'),
                           'prompt_tps': timings.get('prompt_per_second'), 'generation_tps': timings.get('predicted_per_second'),
                           'schema_mode': self.schema_mode if response_schema is not None else None})
        try:
            return reply['choices'][0]['message']
        except (KeyError, IndexError, TypeError):
            raise ModelError('malformed reply')

    def structured(self, messages, response_schema, max_tokens=700, label=''):
        """Schema-constrained answer with one corrective retry; ModelError when still invalid."""
        problem = None
        for attempt in range(2):
            message = self.chat(messages, response_schema, max_tokens=max_tokens, label=label + ('' if attempt == 0 else ':retry'))
            text = message.get('content') or ''
            try:
                value = parse_json(text)
                errors = validate(value, response_schema)
            except ValueError as error:
                value, errors = None, [str(error)]
            if not errors:
                return value
            problem = '; '.join(errors)[:300]
            messages = messages + [{'role': 'assistant', 'content': text[:2000]},
                                   {'role': 'user', 'content': 'That reply was invalid (%s). Reply again with only the corrected JSON object.' % problem}]
        raise ModelError('invalid answer: %s' % problem)


# ---------------------------------------------------------------- MCP client (agent mode)

class McpClient:
    def __init__(self, database, end=None, budget=3000, cache='auto'):
        command = [sys.executable, '-I', str(HERE / 'mcp_server.py'), '--database', str(database), '--budget', str(budget), '--cache', cache]
        if end:
            command += ['--end', A.N.iso(end)]
        self.process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.next_id = 0
        self.request('initialize', {'protocolVersion': '2025-06-18', 'capabilities': {}, 'clientInfo': {'name': 'router-audit-explain', 'version': '1.1'}})
        self.process.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
        self.process.stdin.flush()
        self.tools = self.request('tools/list', {})['tools']

    def request(self, method, params):
        self.next_id += 1
        self.process.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': self.next_id, 'method': method, 'params': params}) + '\n')
        self.process.stdin.flush()
        response = json.loads(self.process.stdout.readline())
        if 'error' in response:
            raise ModelError('MCP %s: %s' % (method, response['error'].get('message')))
        return response['result']

    def call(self, name, arguments):
        try:
            result = self.request('tools/call', {'name': name, 'arguments': arguments})
        except ModelError as error:
            return 'Error: %s' % error, True
        return '\n'.join(c.get('text', '') for c in result.get('content', [])), result.get('isError', False)

    def openai_tools(self):
        return [{'type': 'function', 'function': {'name': t['name'], 'description': t['description'], 'parameters': t['inputSchema']}}
                for t in self.tools]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=10)
        self.process.stdout.close()


# ---------------------------------------------------------------- runs

def finding_schema(finding):
    """Answer schema for one finding: id and category are copied fields, so they are pinned to
    the finding's own values (small models otherwise relabel e.g. conntrack as network)."""
    value = schema('finding.schema.json')
    value['properties']['id'] = {'type': 'string', 'enum': [finding['id']]}
    value['properties']['category'] = {'type': 'string', 'enum': [finding['category']]}
    return value


def summary_schema(analysis):
    """Summary schema narrowed to this window: top_issues may only name real finding IDs, and
    no more entries than there are findings (small models otherwise pad the list)."""
    value = schema('summary.schema.json')
    ids = [f['id'] for f in analysis.findings()]
    issues = value['properties']['top_issues']
    issues['maxItems'] = min(issues.get('maxItems', 3), len(ids))
    if ids:
        issues['items']['properties']['id'] = {'type': 'string', 'enum': ids}
    return value


def example_messages():
    block, answer = prompt('example.txt').split('=== ANSWER ===')
    return [{'role': 'user', 'content': block.strip()}, {'role': 'assistant', 'content': answer.strip()}]


def explain_finding(client, analysis, finding, budget, fmt):
    messages = [client.system(prompt('system.txt'))] + example_messages() + [
        {'role': 'user', 'content': A.finding_text(analysis, finding, budget, fmt)}]
    return client.structured(messages, finding_schema(finding), label=finding['id'])


def summarize(client, analysis, assessments, budget, fmt):
    text = A.overview(analysis, budget, fmt)
    if assessments:
        text += '\n\nPER-FINDING ASSESSMENTS\n' + '\n'.join(
            '%s rule severity %s, model severity %s, confidence %s: %s' % (
                a['id'], a['rule_severity'], (a.get('model') or {}).get('severity', 'n/a'),
                (a.get('model') or {}).get('confidence', 'n/a'), (a.get('model') or {}).get('explanation', a.get('error') or ''))
            for a in assessments)
    messages = [client.system(prompt('summary.txt')), {'role': 'user', 'content': text}]
    return client.structured(messages, summary_schema(analysis), max_tokens=600, label='summary')


def agent_summary(client, analysis, budget, fmt, cache='auto'):
    mcp = McpClient(analysis.database, analysis.end, budget, cache)
    trace = []
    try:
        tools = mcp.openai_tools()
        messages = [client.system(prompt('agent.txt')),
                    {'role': 'user', 'content': A.overview(analysis, budget, fmt) + '\n\nInvestigate what matters, using tools if useful.'}]
        for _ in range(MAX_AGENT_CALLS + 1):
            message = client.chat(messages, tools=tools, max_tokens=500, label='agent')
            calls = message.get('tool_calls') or []
            if not calls or len(trace) >= MAX_AGENT_CALLS:
                if message.get('content'):
                    messages.append({'role': 'assistant', 'content': message['content']})
                break
            messages.append({'role': 'assistant', 'content': message.get('content') or '', 'tool_calls': calls})
            for call in calls:
                name = call.get('function', {}).get('name')
                try:
                    arguments = json.loads(call.get('function', {}).get('arguments') or '{}')
                except ValueError:
                    arguments = None
                if len(trace) >= MAX_AGENT_CALLS:
                    text, failed = 'Error: tool call limit reached', True
                elif arguments is None:
                    text, failed = 'Error: arguments were not valid JSON', True
                else:
                    text, failed = mcp.call(name, arguments)
                trace.append({'tool': name, 'arguments': arguments, 'error': failed, 'chars': len(text)})
                messages.append({'role': 'tool', 'tool_call_id': call.get('id') or name, 'content': text})
        messages.append({'role': 'user', 'content': prompt('summary.txt') + '\nGive the final answer now.'})
        return client.structured(messages, summary_schema(analysis), max_tokens=600, label='agent-final'), trace
    finally:
        mcp.close()


def run(analysis, client, mode='pipeline', budget=4000, fmt='llm', max_findings=8, cache='auto'):
    started = time.monotonic()
    findings = analysis.findings()
    assessments = []
    if mode == 'pipeline':
        for finding in findings[:max_findings]:
            entry = {'id': finding['id'], 'key': finding['key'], 'category': finding['category'],
                     'rule_severity': finding['severity'], 'title': finding['title'], 'model': None, 'error': None}
            if client.remaining() is not None and client.remaining() <= 1:
                entry['error'] = 'skipped: time budget exceeded'
            else:
                try:
                    entry['model'] = explain_finding(client, analysis, finding, budget, fmt)
                except ModelError as error:
                    entry['error'] = 'model_error: %s' % error
            assessments.append(entry)
    trace = None
    try:
        if mode == 'agent':
            summary, trace = agent_summary(client, analysis, budget, fmt, cache)
        else:
            summary = summarize(client, analysis, assessments, budget, fmt)
        summary_error = None
    except ModelError as error:
        summary, summary_error = None, 'model_error: %s' % error
    return {
        'kind': 'router-audit-explanation', 'generated_at': A.N.iso(dt.datetime.now(dt.timezone.utc)),
        'window': {'start': A.N.iso(analysis.start), 'end': A.N.iso(analysis.end), 'hours': analysis.hours},
        'settings': {'model': client.model, 'endpoint': client.url, 'mode': mode, 'think': client.think, 'budget': budget,
                     'format': fmt, 'schema_mode': client.schema_mode, 'max_findings': max_findings},
        'findings': [{k: v for k, v in f.items() if k in ('id', 'key', 'category', 'severity', 'title')} for f in findings],
        'assessments': assessments, 'summary': summary, 'summary_error': summary_error, 'agent_trace': trace,
        'calls': client.calls, 'seconds': round(time.monotonic() - started, 1),
        'timed_out': any('time budget' in (a.get('error') or '') or 'timed out' in (a.get('error') or '') for a in assessments)
                     or bool(summary_error and ('time budget' in summary_error or 'timed out' in summary_error)),
    }


def markdown(report):
    s = report['settings']
    lines = ['# Router audit explanation', '',
             'Window %s to %s · model `%s` · mode %s · thinking %s · budget %d' % (
                 report['window']['start'], report['window']['end'], s['model'], s['mode'], 'on' if s['think'] else 'off', s['budget']), '']
    summary = report.get('summary')
    if summary:
        lines += ['**Overall: %s.** %s' % (summary['overall'], summary['summary']), '']
        for issue in summary['top_issues']:
            lines.append('- **%s** — %s' % (issue['id'], issue['why']))
        lines.append('')
    elif report.get('summary_error'):
        lines += ['Summary unavailable: %s' % report['summary_error'], '']
    for a in report['assessments']:
        lines.append('## %s %s — rule severity %s' % (a['id'], a['title'], a['rule_severity']))
        m = a.get('model')
        if not m:
            lines += ['', a.get('error') or 'no answer', '']
            continue
        lines += ['', 'Model: %s, confidence %s. %s' % (m['severity'], m['confidence'], m['explanation']), '']
        lines += ['Likely causes:'] + ['- %s' % x for x in m['likely_causes']] + ['', 'Checks:'] + ['- `%s`' % x for x in m['next_checks']] + ['']
    if report.get('agent_trace'):
        lines += ['Tool calls: ' + ', '.join('%s(%s)' % (t['tool'], json.dumps(t['arguments'])) for t in report['agent_trace']), '']
    lines.append('%d model calls, %.1f s total.' % (len(report['calls']), report['seconds']))
    return '\n'.join(lines) + '\n'


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('database')
    p.add_argument('--endpoint', default='http://127.0.0.1:8080/v1')
    p.add_argument('--model', default='local')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--hours', type=float)
    group.add_argument('--window', choices=sorted(A.WINDOWS))
    p.add_argument('--end', help='ISO-8601 window end (default: newest record)')
    p.add_argument('--mode', choices=['pipeline', 'agent'], default='pipeline')
    p.add_argument('--think', choices=['off', 'on'], default='off')
    p.add_argument('--budget', type=int, default=4000)
    p.add_argument('--format', choices=['llm', 'llm-json'], default='llm')
    p.add_argument('--max-findings', type=int, default=8)
    p.add_argument('--extra-system', default='', help='text appended to every system prompt')
    p.add_argument('--timeout', type=int, default=180, help='seconds per model request')
    p.add_argument('--time-budget', type=int, default=600, help='seconds for the whole run; 0 = unlimited')
    p.add_argument('--think-tokens', type=int, default=2048, help='extra output tokens allowed for reasoning when --think on')
    p.add_argument('--cache', default='auto')
    p.add_argument('--out', help='directory for report.json and report.md')
    a = p.parse_args()
    if not 500 <= a.budget <= 64000:
        p.error('budget must be 500..64000')
    hours = A.WINDOWS[a.window] if a.window else (a.hours or 1.0)
    end = A.N.parse_time(a.end) if a.end else None
    analysis = A.Analysis(a.database, hours, end=end, cache=a.cache)
    client = Client(a.endpoint, a.model, a.timeout, a.think == 'on', a.extra_system,
                    time_budget=a.time_budget or None, think_tokens=a.think_tokens)
    with analysis:
        report = run(analysis, client, a.mode, a.budget, a.format, a.max_findings, a.cache)
    text = markdown(report)
    if a.out:
        out = pathlib.Path(a.out)
        out.mkdir(parents=True, exist_ok=True)
        (out / 'report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n')
        (out / 'report.md').write_text(text)
    print(text, end='')
    sys.exit(0 if report['summary'] is not None else 1)


if __name__ == '__main__':
    main()
