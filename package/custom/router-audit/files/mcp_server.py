#!/usr/bin/python3
"""Minimal read-only MCP server (stdio, newline-delimited JSON-RPC 2.0) for router-audit.

Three tools with flat enum parameters, sized for small local models. Each returns the
analyzer's pre-computed `llm` text for the requested window. Standard library only.

    python3 mcp_server.py --database router-audit.sqlite [--budget 3000] [--end ISO]
"""
import argparse
import importlib.machinery
import importlib.util
import json
import pathlib
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(HERE / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


A = _load('router_audit_analyze', 'analyze.py')
PROTOCOLS = ('2025-06-18', '2025-03-26', '2024-11-05')
WINDOW = {'type': 'string', 'enum': ['1h', '6h', '24h'], 'description': 'Time window ending now. Default 1h.'}
TOOLS = [
    {'name': 'router_overview',
     'description': 'General health check: overall state and numbered findings (F1, F2, ...). For a question about one area, use router_topic instead.',
     'inputSchema': {'type': 'object', 'properties': {'window': WINDOW}, 'additionalProperties': False}},
    {'name': 'router_finding',
     'description': 'Facts, surrounding context and blind spots for one finding ID listed by router_overview for the same window. Example: {"id": "F1"}.',
     'inputSchema': {'type': 'object', 'properties': {'id': {'type': 'string', 'pattern': '^F[1-9][0-9]?$', 'description': 'Finding ID such as F1'},
                                                      'window': WINDOW}, 'required': ['id'], 'additionalProperties': False}},
    {'name': 'router_topic',
     'description': 'Answer a question about one area. Pick the topic: system = CPU, memory, load, disk, temperature; wan = internet link and probes; '
                    'dns = DNS totals; clients = which LAN device does what; conntrack = connection tracking table; services = crashes, restarts, failed units; '
                    'firewall = rule traffic; changes = configuration (UCI) changes; logs = journal events such as failed logins. Example: {"topic": "changes", "window": "24h"}.',
     'inputSchema': {'type': 'object', 'properties': {'topic': {'type': 'string', 'enum': list(A.TOPICS),
                                                                'description': 'area to inspect'},
                                                      'window': WINDOW}, 'required': ['topic'], 'additionalProperties': False}},
]


class ToolError(Exception):
    pass


class Server:
    def __init__(self, database, budget=3000, end=None, cache='auto', ttl=60):
        self.database, self.budget, self.end, self.cache, self.ttl = database, budget, end, cache, ttl
        self._analyses = {}

    def analysis(self, window):
        hit = self._analyses.get(window)
        if hit and time.monotonic() - hit[0] < self.ttl:
            return hit[1]
        if hit:
            hit[1].close()
        an = A.Analysis(self.database, A.WINDOWS[window], end=self.end, cache=self.cache)
        self._analyses[window] = (time.monotonic(), an)
        return an

    def call(self, name, args):
        if not isinstance(args, dict):
            raise ToolError('arguments must be an object')
        tool = next((t for t in TOOLS if t['name'] == name), None)
        if tool is None:
            raise KeyError(name)
        schema = tool['inputSchema']
        unknown = set(args) - set(schema['properties'])
        if unknown:
            raise ToolError('unknown argument(s): %s' % ', '.join(sorted(unknown)))
        for key in schema.get('required', []):
            if key not in args:
                raise ToolError('missing required argument: %s' % key)
        window = args.get('window', '1h')
        if window not in WINDOW['enum']:
            raise ToolError('window must be one of %s' % ', '.join(WINDOW['enum']))
        an = self.analysis(window)
        if name == 'router_overview':
            return A.overview(an, self.budget)
        if name == 'router_finding':
            fid = args['id']
            if not isinstance(fid, str) or not re.fullmatch(r'F[1-9][0-9]?', fid):
                raise ToolError('id must look like F1')
            finding = an.finding(fid)
            if finding is None:
                ids = ', '.join(f['id'] for f in an.findings()) or 'none'
                raise ToolError('no finding %s in window %s; available: %s' % (fid, window, ids))
            return A.finding_text(an, finding, self.budget)
        topic = args['topic']
        if topic not in A.TOPICS:
            raise ToolError('topic must be one of %s' % ', '.join(A.TOPICS))
        return A.topic_text(an, topic, self.budget)

    def handle(self, message):
        """One JSON-RPC message -> response dict, or None for notifications."""
        if not isinstance(message, dict) or message.get('jsonrpc') != '2.0' or 'method' not in message:
            return {'jsonrpc': '2.0', 'id': message.get('id') if isinstance(message, dict) else None,
                    'error': {'code': -32600, 'message': 'Invalid Request'}}
        method, params, mid = message['method'], message.get('params') or {}, message.get('id')
        if mid is None:
            return None  # notification (e.g. notifications/initialized)
        try:
            if method == 'initialize':
                requested = params.get('protocolVersion')
                result = {'protocolVersion': requested if requested in PROTOCOLS else PROTOCOLS[0],
                          'capabilities': {'tools': {'listChanged': False}},
                          'serverInfo': {'name': 'router-audit', 'version': '1.1'},
                          'instructions': 'Read-only router telemetry. Start with router_overview; finding IDs are only valid for the same window.'}
            elif method == 'ping':
                result = {}
            elif method == 'tools/list':
                result = {'tools': TOOLS}
            elif method == 'tools/call':
                try:
                    text = self.call(params.get('name'), params.get('arguments') or {})
                    result = {'content': [{'type': 'text', 'text': text}], 'isError': False}
                except ToolError as error:
                    result = {'content': [{'type': 'text', 'text': 'Error: %s' % error}], 'isError': True}
                except KeyError:
                    return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32602, 'message': 'Unknown tool: %s' % params.get('name')}}
            else:
                return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32601, 'message': 'Method not found'}}
        except SystemExit as error:
            return {'jsonrpc': '2.0', 'id': mid, 'error': {'code': -32603, 'message': str(error)}}
        return {'jsonrpc': '2.0', 'id': mid, 'result': result}

    def serve(self, stdin=sys.stdin, stdout=sys.stdout):
        for line in stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Parse error'}}
            else:
                response = self.handle(message)
            if response is not None:
                stdout.write(json.dumps(response, ensure_ascii=False) + '\n')
                stdout.flush()


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--database', required=True)
    p.add_argument('--budget', type=int, default=3000, help='token budget per tool result (chars/4 estimate)')
    p.add_argument('--end', help='fixed ISO-8601 window end (default: newest record)')
    p.add_argument('--cache', default='auto')
    a = p.parse_args()
    end = A.N.parse_time(a.end) if a.end else None
    Server(a.database, a.budget, end, a.cache).serve()


if __name__ == '__main__':
    main()
