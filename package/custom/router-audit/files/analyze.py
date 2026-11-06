#!/usr/bin/python3
"""Deterministic router-audit analysis for the puller's SQLite database.

All arithmetic happens here: counter rates, 7-day baselines, thresholds, identity
resolution and ranking. The `llm` renderers turn the result into short text with the
verdicts already attached, so a small local model only has to explain and prioritise.

The source database is opened read-only. Per-minute samples extracted from it are cached
in a sidecar database (default: DB + '.derived') so baselines do not re-parse every batch.
Standard library only.
"""
import argparse
import collections
import datetime as dt
import importlib.machinery
import importlib.util
import json
import math
import pathlib
import re
import sqlite3
import statistics
import sys

HERE = pathlib.Path(__file__).resolve().parent


def _load(name, filename):
    loader = importlib.machinery.SourceFileLoader(name, str(HERE / filename))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


N = _load('router_audit_normalize', 'normalize.py')

DERIVED_VERSION = '3'
SEVERITIES = ('info', 'warning', 'critical')
CATEGORIES = ('system', 'memory', 'wan', 'network', 'dns', 'conntrack', 'services',
              'firewall', 'security', 'coverage')
TOPICS = ('system', 'wan', 'dns', 'clients', 'conntrack', 'services', 'firewall', 'changes', 'logs')
WINDOWS = {'15m': 0.25, '1h': 1.0, '6h': 6.0, '24h': 24.0}
BASELINE_DAYS = 7
MIN_BASELINE = 30
MIN_BASELINE_SPAN = 86400  # a baseline needs at least a day of history
DERIVED_MODULES = ('system', 'network', 'firewall', 'services', 'dns_queries', 'dns_minute')
WINDOW_MODULES = ('system', 'network', 'firewall', 'services', 'identity', 'events', 'changes',
                  'dns_queries', 'dns_minute', 'virtualization')
MULTI_SUFFIXES = {'com.cn', 'net.cn', 'org.cn', 'gov.cn', 'edu.cn', 'co.uk', 'org.uk', 'ac.uk',
                  'co.jp', 'ne.jp', 'or.jp', 'com.au', 'net.au', 'org.au', 'com.hk', 'com.tw',
                  'com.sg', 'co.kr', 'com.br', 'co.nz', 'co.in'}
NOT_MEASURED = {
    'dns': 'Client DoH/DoT/DoQ and application DNS caches are not observed; dnsmasq reports '
           'sent responses only, not every attempted query.',
    'network': 'Flow offload, notrack and transparent-proxy paths can bypass counters.',
    'wan': 'Probes are TCP 443 and one UDP DNS query per minute; no ICMP loss or HTTPS health.',
    'services': 'Container runtime health is not collected; only process presence.',
    'security': 'Only typed journal signatures are exported; raw log messages are not.',
    'conntrack': 'Conntrack totals only; no per-client connection accounting.',
}

# Metrics that get a 7-day baseline verdict. agg: how the window is summarised.
# floor: minimum distance from the median before anything is called high/unusual.
BASELINE_METRICS = {
    'cpu_pct': {'label': 'CPU busy', 'unit': '%', 'agg': 'mean', 'floor': 15.0, 'category': 'system'},
    'load1': {'label': 'load average (1 min)', 'unit': '', 'agg': 'mean', 'floor': 1.5, 'category': 'system'},
    'psi_memory': {'label': 'memory pressure avg60', 'unit': '', 'agg': 'max', 'floor': 5.0, 'category': 'memory'},
    'psi_io': {'label': 'I/O pressure avg60', 'unit': '', 'agg': 'max', 'floor': 10.0, 'category': 'system'},
    'conntrack_pct': {'label': 'conntrack table use', 'unit': '%', 'agg': 'max', 'floor': 15.0, 'category': 'conntrack'},
    'dns_qpm': {'label': 'DNS queries per minute (LAN clients)', 'unit': '/min', 'agg': 'mean', 'floor': 60.0, 'category': 'dns'},
    'dns_nx_pct': {'label': 'DNS NXDOMAIN share', 'unit': '%', 'agg': 'mean', 'floor': 10.0, 'category': 'dns'},
}


# ---------------------------------------------------------------- small helpers

def epoch(value):
    moment = N.parse_time(value)
    return moment.timestamp() if moment else None


def percentile(values, fraction):
    ordered = sorted(values)
    if not ordered:
        return None
    index = max(0, min(len(ordered) - 1, math.ceil(fraction * len(ordered)) - 1))
    return ordered[index]


def registrable(name):
    labels = [x for x in (name or '').lower().rstrip('.').split('.') if x]
    if len(labels) <= 2:
        return '.'.join(labels) or '(root)'
    if '.'.join(labels[-2:]) in MULTI_SUFFIXES:
        return '.'.join(labels[-3:])
    return '.'.join(labels[-2:])


def entropy(label):
    if not label:
        return 0.0
    counts = collections.Counter(label)
    return -sum((n / len(label)) * math.log2(n / len(label)) for n in counts.values())


def high_entropy(qname):
    label = max((qname or '').rstrip('.').split('.'), key=len)
    return len(label) >= 24 and entropy(label) >= 4.0


def num(value, digits=0):
    if value is None:
        return 'unknown'
    if digits == 0:
        return f'{round(value):,}'
    return f'{value:,.{digits}f}'


def bits(value):
    if value is None:
        return 'unknown'
    for unit, size in (('Gbit/s', 1e9), ('Mbit/s', 1e6), ('kbit/s', 1e3)):
        if value >= size:
            return f'{value / size:.1f} {unit}'
    return f'{value:.0f} bit/s'


def pct(part, whole):
    return 100.0 * part / whole if whole else None


# ---------------------------------------------------------------- extraction

def extract(record):
    """One normalized record -> (samples [(key, value)], dns_rows, domains)."""
    module, d = record.get('module'), record.get('data') or {}
    samples, dns_rows, domains = [], [], set()
    add = lambda key, value: samples.append((key, float(value))) if isinstance(value, (int, float)) and not isinstance(value, bool) else None
    if module == 'system':
        cpu = d.get('cpu') or {}
        if cpu:
            busy = sum(cpu.get(k, 0) for k in ('user', 'nice', 'system', 'irq', 'softirq', 'steal'))
            add('cpu.busy', busy)
            add('cpu.total', busy + cpu.get('idle', 0) + cpu.get('iowait', 0))
        memory = d.get('memory') or {}
        if memory.get('MemTotal'):
            add('mem.avail_pct', pct(memory.get('MemAvailable', 0), memory['MemTotal']))
        load = d.get('load') or []
        if load:
            add('load1', load[0])
        for kind in ('cpu', 'memory', 'io'):
            some = ((d.get('pressure') or {}).get(kind) or {}).get('some') or {}
            add('psi.' + kind, some.get('avg60'))
        temps = [t.get('celsius') for t in d.get('temperature') or [] if isinstance(t.get('celsius'), (int, float))]
        if temps:
            add('temp.max', max(temps))
        for disk in d.get('disks') or []:
            if disk.get('total'):
                add('disk.%s.free_pct' % disk.get('path'), pct(disk.get('available', 0), disk['total']))
    elif module == 'network':
        for link in d.get('links') or []:
            name, stats = link.get('ifname'), link.get('stats64') or {}
            rx, tx = stats.get('rx') or {}, stats.get('tx') or {}
            if not name:
                continue
            add('if.%s.rx_bytes' % name, rx.get('bytes'))
            add('if.%s.tx_bytes' % name, tx.get('bytes'))
            add('if.%s.errors' % name, (rx.get('errors') or 0) + (tx.get('errors') or 0))
            add('if.%s.rx_drops' % name, rx.get('dropped'))
            add('if.%s.tx_drops' % name, tx.get('dropped'))
        for iface in d.get('interfaces') or []:
            if iface.get('interface'):
                add('iface.%s.up' % iface['interface'], 1 if iface.get('up') else 0)
        for probe in d.get('probes') or []:
            target = '%s/%s' % (probe.get('kind'), probe.get('target'))
            add('probe.%s.ok' % target, 1 if probe.get('ok') else 0)
            if probe.get('ok'):
                add('probe.%s.ms' % target, probe.get('elapsed_ms'))
    elif module == 'firewall':
        ct = d.get('conntrack') or {}
        if isinstance(ct.get('count'), int):
            add('ct.count', ct['count'])
            if ct.get('max'):
                add('ct.max', ct['max'])
                add('ct.pct', pct(ct['count'], ct['max']))
        for key in ('insert_failed', 'drop', 'early_drop'):
            add('ct.' + key, (d.get('conntrack_stats') or {}).get(key))
        for rule in d.get('rules') or []:
            if not rule.get('counters'):
                continue
            name = '%s/%s/%s/%s' % (rule.get('family'), rule.get('table'), rule.get('chain'),
                                    rule.get('comment') or '#%s' % rule.get('handle'))
            add('nft.%s.packets' % name, sum(c.get('packets', 0) for c in rule['counters']))
            add('nft.%s.bytes' % name, sum(c.get('bytes', 0) for c in rule['counters']))
        for iface, fields in (d.get('wireguard') or {}).items():
            for row in fields.get('transfer') or []:
                values = row.get('values') or []
                if len(values) >= 2 and all(str(v).isdigit() for v in values[:2]):
                    add('wg.%s.%s.rx' % (iface, row.get('peer', '')[:8]), int(values[0]))
                    add('wg.%s.%s.tx' % (iface, row.get('peer', '')[:8]), int(values[1]))
    elif module == 'services':
        for unit in d.get('systemd') or []:
            if unit.get('Id'):
                add('restarts.%s' % unit['Id'], unit.get('NRestarts'))
        for inst in d.get('procd') or []:
            add('respawn.%s/%s' % (inst.get('service'), inst.get('instance')), inst.get('respawn_count'))
    elif module == 'dns_minute':
        clients = [c for c in d.get('clients') or [] if not c.get('internal')]
        queries = sum(c.get('queries', 0) for c in clients)
        add('dns.queries', queries)
        add('dns.nxdomain', sum((c.get('rcodes') or {}).get('3', 0) for c in clients))
        add('dns.servfail', sum((c.get('rcodes') or {}).get('2', 0) for c in clients))
        add('dns.receiver_dropped', (d.get('receiver') or {}).get('dropped'))
    elif module == 'dns_queries':
        per = {}
        for event in d.get('events') or []:
            client = event.get('client') or 'unknown'
            if N.is_internal(client):
                continue
            row = per.setdefault(client, [0, 0, 0, 0])
            row[0] += 1
            row[1] += event.get('rcode') == 3
            row[2] += event.get('rcode') == 2
            row[3] += bool(event.get('failed'))
            domains.add(registrable(event.get('qname')))
        dns_rows = [(client, *row) for client, row in per.items()]
        producers = {}
        for event in d.get('events') or []:
            if isinstance(event.get('producer_dropped'), int):
                key = '%s/%s' % (event.get('source'), event.get('source_epoch'))
                producers[key] = max(producers.get(key, 0), event['producer_dropped'])
        for key, value in producers.items():
            add('dns.producer_dropped.%s' % key, value)
    return samples, dns_rows, domains


class Derived:
    """Sidecar cache of extracted samples. Incremental: each source batch is read once."""

    SCHEMA = '''
    CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
    CREATE TABLE IF NOT EXISTS processed(id TEXT PRIMARY KEY, t REAL);
    CREATE TABLE IF NOT EXISTS samples(t REAL, boot TEXT, key TEXT, value REAL);
    CREATE INDEX IF NOT EXISTS samples_key_t ON samples(key, t);
    CREATE TABLE IF NOT EXISTS dns_min(t REAL, client TEXT, queries INT, nxdomain INT, servfail INT, failed INT);
    CREATE INDEX IF NOT EXISTS dns_min_t ON dns_min(t);
    CREATE TABLE IF NOT EXISTS domains(domain TEXT PRIMARY KEY, first_seen REAL, last_seen REAL);
    '''

    def __init__(self, source, path=None, since=None):
        source_uri = pathlib.Path(source).resolve().as_uri() + '?mode=ro'
        if path is None:
            self.db = sqlite3.connect(':memory:')
        else:
            self.db = sqlite3.connect(str(path))
        self.db.execute('ATTACH DATABASE ? AS src', (source_uri,))
        self.db.executescript(self.SCHEMA)
        version = self.db.execute("SELECT value FROM meta WHERE key='version'").fetchone()
        if not version or version[0] != DERIVED_VERSION:
            for table in ('processed', 'samples', 'dns_min', 'domains'):
                self.db.execute('DELETE FROM ' + table)
            self.db.execute("INSERT OR REPLACE INTO meta VALUES('version', ?)", (DERIVED_VERSION,))
        self.update(since)

    def update(self, since=None):
        placeholders = ','.join('?' * len(DERIVED_MODULES))
        query = ('SELECT b.id, b.payload FROM src.batches b LEFT JOIN processed p ON p.id = b.id '
                 'WHERE p.id IS NULL AND b.module IN (%s)' % placeholders)
        args = list(DERIVED_MODULES)
        if since is not None:
            query += ' AND b.time >= ?'
            args.append(N.iso(since))
        cursor = self.db.execute(query, args)
        while True:
            rows = cursor.fetchmany(2000)
            if not rows:
                break
            samples, dns_rows, processed, domains = [], [], [], {}
            for batch_id, payload in rows:
                try:
                    record = N.upgrade(json.loads(payload))
                except ValueError:
                    continue
                t = epoch(record.get('collected_at'))
                if t is None:
                    continue
                values, dns, names = extract(record)
                boot = record.get('boot_id') or ''
                samples += [(t, boot, k, v) for k, v in values]
                dns_rows += [(t, *row) for row in dns]
                for name in names:
                    first, last = domains.get(name, (t, t))
                    domains[name] = (min(first, t), max(last, t))
                processed.append((batch_id, t))
            with self.db:
                self.db.executemany('INSERT INTO samples VALUES(?,?,?,?)', samples)
                self.db.executemany('INSERT INTO dns_min VALUES(?,?,?,?,?,?)', dns_rows)
                self.db.executemany('INSERT OR IGNORE INTO processed VALUES(?,?)', processed)
                self.db.executemany('INSERT INTO domains VALUES(?,?,?) ON CONFLICT(domain) DO UPDATE SET '
                                    'first_seen=min(first_seen, excluded.first_seen), last_seen=max(last_seen, excluded.last_seen)',
                                    [(k, *v) for k, v in domains.items()])
        cutoff = dt.datetime.now(dt.timezone.utc).timestamp() - 32 * 86400
        with self.db:
            for table in ('samples', 'dns_min', 'processed'):
                self.db.execute('DELETE FROM %s WHERE t < ?' % table, (cutoff,))

    def series(self, key, start, end):
        return self.db.execute('SELECT t, boot, value FROM samples WHERE key=? AND t>=? AND t<=? ORDER BY t',
                               (key, start, end)).fetchall()

    def keys(self, prefix, start, end):
        pattern = prefix.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_') + '%'
        return sorted(r[0] for r in self.db.execute("SELECT DISTINCT key FROM samples WHERE key LIKE ? ESCAPE '\\' AND t>=? AND t<=?",
                                                     (pattern, start, end)))


def rates(rows, per=1.0):
    """Counter rows [(t, boot, value)] -> [(t, delta/second*per)]. Reset on boot change or decrease."""
    out = []
    for (t0, b0, v0), (t1, b1, v1) in zip(rows, rows[1:]):
        if b0 == b1 and v1 >= v0 and t1 > t0:
            out.append((t1, (v1 - v0) / (t1 - t0) * per))
    return out


def deltas(rows):
    """Counter rows -> [(t, increment)] with the same reset rules (for event counts)."""
    out = []
    for (t0, b0, v0), (t1, b1, v1) in zip(rows, rows[1:]):
        if b0 == b1 and v1 >= v0:
            out.append((t1, v1 - v0))
    return out


# ---------------------------------------------------------------- analysis

class Analysis:
    def __init__(self, database, hours=1.0, end=None, cache='auto', tz=None, now=None):
        self.database = str(database)
        self.hours = float(hours)
        last = sqlite3.connect(pathlib.Path(database).resolve().as_uri() + '?mode=ro', uri=True)
        try:
            newest = last.execute('SELECT max(time) FROM batches').fetchone()[0]
        except sqlite3.DatabaseError as error:
            raise SystemExit('not a router-audit database: %s' % error)
        self.end = end or N.parse_time(newest) or dt.datetime.now(dt.timezone.utc)
        self.now = now or self.end
        self.start = self.end - dt.timedelta(hours=self.hours)
        self.tz = tz or dt.datetime.now().astimezone().tzinfo
        self.e0, self.e1 = self.start.timestamp(), self.end.timestamp()
        self.base0 = self.e0 - BASELINE_DAYS * 86400
        cache_path = None if cache in (None, 'none') else (self.database + '.derived' if cache == 'auto' else cache)
        self.derived = Derived(database, cache_path, since=None if cache_path else self.base0 - 3600)
        self.records = collections.defaultdict(list)
        placeholders = ','.join('?' * len(WINDOW_MODULES))
        # Identity and changes may be older than a short window; read a little further back.
        lookback = N.iso(self.e0 - 3600)
        for (payload,) in last.execute('SELECT payload FROM batches WHERE time >= ? AND time <= ? AND module IN (%s) ORDER BY time' % placeholders,
                                       [lookback, N.iso(self.e1 + 1), *WINDOW_MODULES]):
            try:
                record = N.upgrade(json.loads(payload))
            except ValueError:
                continue
            t = epoch(record.get('collected_at'))
            if t is None:
                continue
            record['_t'] = t
            self.records[record['module']].append(record)
        last.close()
        self._identity = self._build_identity()
        self._findings = None

    def close(self):
        self.derived.db.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- record access
    def window(self, module):
        return [r for r in self.records.get(module, []) if self.e0 <= r['_t'] <= self.e1]

    def latest(self, module):
        rows = self.records.get(module) or []
        return rows[-1] if rows else None

    # -- time
    def local(self, t):
        moment = dt.datetime.fromtimestamp(t, dt.timezone.utc).astimezone(self.tz)
        return moment.strftime('%m-%d %H:%M' if self.hours > 12 else '%H:%M')

    def ago(self, t):
        minutes = max(0, round((self.now.timestamp() - t) / 60))
        if minutes < 90:
            return '%d min ago' % minutes
        return '%dh %02dm ago' % (minutes // 60, minutes % 60)

    def when(self, t):
        return '%s (%s)' % (self.local(t), self.ago(t))

    def window_label(self):
        offset = dt.datetime.fromtimestamp(self.e1, self.tz).strftime('%z')
        return '%s to %s, last %s, times UTC%s:%s' % (self.local(self.e0), self.local(self.e1),
                                                       '%gh' % self.hours if self.hours >= 1 else '%dm' % (self.hours * 60),
                                                       offset[:3], offset[3:])

    # -- identity
    def _build_identity(self):
        by_ip, by_mac = {}, {}
        records = self.records.get('identity') or []
        for record in records:
            d = record.get('data') or {}
            for lease in d.get('dhcp4') or []:
                name = lease.get('hostname')
                if name and name != '*':
                    by_ip[lease.get('ip')] = name
                    by_mac[(lease.get('mac') or '').lower()] = name
            for device in ((d.get('dhcp6') or {}).get('device') or {}).values():
                for lease in device.get('leases') or []:
                    name = lease.get('hostname')
                    if not name or name == '*':
                        continue
                    for address in lease.get('ipv6-addr') or lease.get('ipv6_addr') or []:
                        if isinstance(address, dict) and address.get('address'):
                            by_ip[address['address']] = name
            for neighbour in d.get('neighbors') or []:
                mac = (neighbour.get('lladdr') or '').lower()
                if mac in by_mac and neighbour.get('dst'):
                    by_ip.setdefault(neighbour['dst'], by_mac[mac])
        return by_ip

    def name(self, address):
        host = self._identity.get(address)
        return '%s (%s)' % (host, address) if host else address

    # -- series helpers
    def gauge(self, key, start=None, end=None):
        return [(t, v) for t, _, v in self.derived.series(key, self.e0 if start is None else start, self.e1 if end is None else end)]

    def counter_rate(self, key, per=1.0, start=None, end=None):
        # Include one sample before the window so the first in-window delta exists.
        s = self.e0 if start is None else start
        return [(t, v) for t, v in rates(self.derived.series(key, s - 900, self.e1 if end is None else end), per) if t >= s]

    def counter_increase(self, key):
        return sum(v for t, v in deltas(self.derived.series(key, self.e0 - 900, self.e1)) if t >= self.e0)

    def cpu_series(self, start, end):
        busy = self.derived.series('cpu.busy', start - 900, end)
        total = self.derived.series('cpu.total', start - 900, end)
        rb, rt = dict((t, v) for t, v in rates(busy)), dict((t, v) for t, v in rates(total))
        return [(t, 100.0 * rb[t] / rt[t]) for t in sorted(rb) if t >= start and rt.get(t)]

    def metric_series(self, metric, start, end):
        if metric == 'cpu_pct':
            return self.cpu_series(start, end)
        if metric == 'load1':
            return self.gauge('load1', start, end)
        if metric == 'psi_memory':
            return self.gauge('psi.memory', start, end)
        if metric == 'psi_io':
            return self.gauge('psi.io', start, end)
        if metric == 'conntrack_pct':
            return self.gauge('ct.pct', start, end)
        if metric == 'dns_qpm':
            return self.gauge('dns.queries', start, end)
        if metric == 'dns_nx_pct':
            q = dict(self.gauge('dns.queries', start, end))
            nx = dict(self.gauge('dns.nxdomain', start, end))
            return [(t, 100.0 * nx.get(t, 0) / q[t]) for t in sorted(q) if q[t] >= 10]
        raise KeyError(metric)

    @staticmethod
    def aggregate(values, agg):
        if not values:
            return None
        return max(values) if agg == 'max' else statistics.fmean(values)

    def baseline(self, metric):
        spec = BASELINE_METRICS[metric]
        current = self.aggregate([v for _, v in self.metric_series(metric, self.e0, self.e1)], spec['agg'])
        history = self.metric_series(metric, self.base0, self.e0 - 1)
        span = (self.e0 - history[0][0]) if history else 0
        hour = dt.datetime.fromtimestamp(self.e1, self.tz).hour
        same = [v for t, v in history if (dt.datetime.fromtimestamp(t, self.tz).hour - hour) % 24 in (0, 1, 23)]
        values, scope = (same, 'same hour ±1, previous 7 days') if len(same) >= MIN_BASELINE else ([v for _, v in history], 'previous 7 days')
        result = {'metric': metric, 'label': spec['label'], 'unit': spec['unit'], 'value': current,
                  'aggregate': spec['agg'], 'baseline_n': len(values), 'scope': scope,
                  'median': None, 'p95': None, 'verdict': 'unknown'}
        if current is None:
            result['verdict'] = 'no data'
            return result
        if len(values) < MIN_BASELINE or span < MIN_BASELINE_SPAN:
            result['verdict'] = 'no baseline'
            result['history_hours'] = round(span / 3600, 1)
            return result
        median, p95 = statistics.median(values), percentile(values, 0.95)
        result.update(median=median, p95=p95)
        excess = current - median
        if current > max(p95, 3 * median) and excess > spec['floor']:
            result['verdict'] = 'unusual'
        elif current > p95 and excess > spec['floor'] / 2:
            result['verdict'] = 'high'
        else:
            result['verdict'] = 'normal'
        return result

    def baseline_text(self, b):
        unit = b['unit']
        fmt = lambda v: 'unknown' if v is None else ('%.1f%s' % (v, unit) if abs(v) < 100 else '%s%s' % (num(v), unit))
        if b['verdict'] == 'no baseline':
            return '%s: %s — no baseline yet (%sh of history, needs 24h)' % (b['label'], fmt(b['value']), b.get('history_hours', 0))
        if b['verdict'] == 'no data':
            return '%s: no data' % b['label']
        return '%s: %s (%s over window) — %s (median %s, p95 %s, %s)' % (
            b['label'], fmt(b['value']), b['aggregate'], b['verdict'].upper() if b['verdict'] != 'normal' else 'normal',
            fmt(b['median']), fmt(b['p95']), b['scope'])

    # -- DNS
    def dns_clients(self):
        events = [e for r in self.window('dns_queries') for e in (r.get('data') or {}).get('events') or []
                  if not N.is_internal(e.get('client') or '')]
        known_before = set(r[0] for r in self.derived.db.execute('SELECT domain FROM domains WHERE first_seen < ?', (self.base0 + 0,)))
        new_domains = set(r[0] for r in self.derived.db.execute(
            'SELECT domain FROM domains WHERE first_seen >= ? AND first_seen <= ?', (self.e0, self.e1)))
        has_history = bool(known_before) or bool(self.derived.db.execute('SELECT 1 FROM dns_min WHERE t < ? LIMIT 1', (self.e0,)).fetchone())
        clients = {}
        for e in events:
            c = clients.setdefault(e.get('client') or 'unknown', {
                'client': e.get('client') or 'unknown', 'queries': 0, 'answered': 0, 'nxdomain': 0, 'servfail': 0,
                'failed': 0, 'reverse': 0, 'reverse_nx': 0, 'sources': set(), 'domains': collections.Counter(), 'nx_domains': collections.Counter(),
                'entropy_names': set(), 'first': e.get('event_time'), 'last': e.get('event_time')})
            c['queries'] += 1
            c['sources'].add(e.get('source'))
            rcode = e.get('rcode')
            if (e.get('qname') or '').lower().rstrip('.').endswith('.arpa'):
                # PTR lookups for unnamed addresses normally return NXDOMAIN; keep them out of error ratios.
                c['reverse'] += 1
                c['reverse_nx'] += rcode == 3
                continue
            if rcode is not None:
                c['answered'] += 1
            c['nxdomain'] += rcode == 3
            c['servfail'] += rcode == 2
            c['failed'] += bool(e.get('failed'))
            domain = registrable(e.get('qname'))
            c['domains'][domain] += 1
            if rcode == 3:
                c['nx_domains'][domain] += 1
            if high_entropy(e.get('qname')):
                c['entropy_names'].add((e.get('qname') or '').lower())
        result = []
        for c in clients.values():
            c['sources'] = sorted(x for x in c['sources'] if x)
            c['unique_domains'] = len(c['domains'])
            c['new_domains'] = sorted(d for d in c['domains'] if d in new_domains) if has_history else None
            c['error_pct'] = pct(c['nxdomain'] + c['servfail'], c['answered'])
            result.append(c)
        return sorted(result, key=lambda c: -c['queries'])

    # -- findings
    def findings(self):
        if self._findings is None:
            found = []
            for rule in (self._rule_memory, self._rule_wan, self._rule_probes, self._rule_conntrack,
                         self._rule_interfaces, self._rule_services, self._rule_dns, self._rule_journal,
                         self._rule_baselines, self._rule_coverage):
                found += rule()
            found.sort(key=lambda f: (-SEVERITIES.index(f['severity']), CATEGORIES.index(f['category']), f['key']))
            for index, finding in enumerate(found, 1):
                finding['id'] = 'F%d' % index
            self._findings = found
        return self._findings

    def finding(self, fid):
        for f in self.findings():
            if f['id'] == fid or f['key'] == fid:
                return f
        return None

    def _finding(self, key, category, severity, title, rule, facts, t=None, metric=None, units=()):
        return {'key': key, 'category': category, 'severity': severity, 'title': title, 'rule': rule,
                'facts': facts, 'time': t, 'metric': metric, 'units': list(units),
                'evidence': None}

    def _rule_memory(self):
        out = []
        avail = self.gauge('mem.avail_pct')
        if avail:
            t, low = min(avail, key=lambda x: x[1])
            if low < 10:
                out.append(self._finding('memory_low', 'memory', 'critical' if low < 5 else 'warning',
                                         'Low available memory', 'available memory below 10% (critical below 5%)',
                                         ['lowest available memory: %.1f%% at %s' % (low, self.when(t)),
                                          'latest available memory: %.1f%%' % avail[-1][1]], t))
        psi = self.gauge('psi.memory')
        if psi:
            t, high = max(psi, key=lambda x: x[1])
            if high > 10:
                out.append(self._finding('memory_pressure', 'memory', 'warning', 'Memory pressure stalls',
                                         'memory pressure avg60 above 10 (tasks stalled waiting for memory)',
                                         ['highest memory pressure avg60: %.1f at %s' % (high, self.when(t)),
                                          'latest: %.1f' % psi[-1][1]], t, metric='psi_memory'))
        return out

    def _wan_names(self):
        return sorted(set(k.split('.')[1] for k in self.derived.keys('iface.', self.e0 - 900, self.e1)
                          if re.match(r'wan', k.split('.')[1])))

    def _rule_wan(self):
        facts, first, severity = [], None, None
        for name in self._wan_names():
            rows = self.gauge('iface.%s.up' % name)
            down = [t for t, v in rows if v == 0]
            if down:
                facts.append('interface %s reported down in %d of %d samples, first at %s' % (name, len(down), len(rows), self.when(down[0])))
                first = min(first or down[0], down[0])
                severity = 'critical'
        events = [e for r in self.window('events') for e in (r['data'].get('events') or [])]
        downs = [e for e in self._dedupe(events) if e.get('kind') == 'wan_down']
        ups = [e for e in self._dedupe(events) if e.get('kind') == 'wan_up']
        if downs:
            ts = [epoch(e.get('event_time')) for e in downs if e.get('event_time')]
            facts.append('journal: %d link-down events (%s), %d link-up events' % (
                len(downs), ', '.join(sorted(set(e.get('detail') or e.get('kind') for e in downs)))[:120], len(ups)))
            if ts:
                first = min(first or min(ts), min(ts))
            severity = severity or 'warning'
        lost = self._connectivity_lost()
        if lost:
            facts.append('all probes failed together in %d samples, longest run %d minutes, first at %s' % (
                lost['samples'], lost['longest'], self.when(lost['first'])))
            first = min(first or lost['first'], lost['first'])
            severity = 'critical' if lost['longest'] >= 3 else (severity or 'warning')
        if not facts:
            return []
        return [self._finding('wan_instability', 'wan', severity, 'WAN connectivity interrupted',
                              'WAN interface down, link-down journal events, or all probes failing at once', facts, first)]

    def _probe_rows(self):
        samples = collections.defaultdict(dict)
        for key in self.derived.keys('probe.', self.e0, self.e1):
            if key.endswith('.ok'):
                for t, v in self.gauge(key):
                    samples[round(t)][key[6:-3]] = v
        return samples

    def _connectivity_lost(self):
        samples = self._probe_rows()
        if not samples:
            return None
        bad = [t for t in sorted(samples) if len(samples[t]) >= 2 and all(v == 0 for v in samples[t].values())]
        if not bad:
            return None
        longest, run, previous = 1, 1, bad[0]
        for t in bad[1:]:
            run = run + 1 if t - previous <= 150 else 1
            longest, previous = max(longest, run), t
        return {'samples': len(bad), 'longest': longest, 'first': bad[0]}

    def _rule_probes(self):
        out = []
        if self._connectivity_lost():
            return out  # covered by the WAN finding
        for key in self.derived.keys('probe.', self.e0, self.e1):
            if not key.endswith('.ok'):
                continue
            rows = self.gauge(key)
            failed = [t for t, v in rows if v == 0]
            if len(failed) >= 2:
                target = key[6:-3]
                out.append(self._finding('probe_failed:%s' % target, 'network', 'warning' if len(failed) >= 5 else 'info',
                                         'Probe failures to %s' % target, 'a connectivity probe failed 2 or more times',
                                         ['%d of %d probes failed, first at %s, last at %s' % (len(failed), len(rows), self.when(failed[0]), self.when(failed[-1]))],
                                         failed[0]))
        return out

    def _rule_conntrack(self):
        out = []
        use = self.gauge('ct.pct')
        if use:
            t, high = max(use, key=lambda x: x[1])
            if high >= 80:
                counts = self.gauge('ct.count')
                limit = self.gauge('ct.max')
                out.append(self._finding('conntrack_full', 'conntrack', 'critical' if high >= 95 else 'warning',
                                         'Connection tracking table nearly full', 'conntrack use at or above 80% of max (critical at 95%)',
                                         ['peak use %.0f%% at %s (%s of %s entries)' % (high, self.when(t), num(dict(counts).get(t)), num(dict(limit).get(t))),
                                          'latest use %.0f%%' % use[-1][1]], t, metric='conntrack_pct'))
        lost = {k: self.counter_increase('ct.' + k) for k in ('insert_failed', 'drop', 'early_drop')}
        if any(lost.values()):
            rows = self.counter_rate('ct.insert_failed', 60) + self.counter_rate('ct.drop', 60)
            t = min((t for t, v in rows if v > 0), default=None)
            out.append(self._finding('conntrack_drops', 'conntrack', 'warning', 'Connections dropped by conntrack',
                                     'conntrack insert_failed, drop or early_drop increased',
                                     ['increase in window: insert_failed %s, drop %s, early_drop %s' % (
                                         num(lost['insert_failed']), num(lost['drop']), num(lost['early_drop']))], t))
        return out

    def _rule_interfaces(self):
        out = []
        for key in self.derived.keys('if.', self.e0, self.e1):
            name, _, field = key[3:].rpartition('.')
            if field not in ('errors', 'rx_drops', 'tx_drops'):
                continue
            series = self.counter_rate(key, 60)
            if not series:
                continue
            total = self.counter_increase(key)
            mean = statistics.fmean(v for _, v in series)
            if total >= 100 and mean >= 5:
                t = next(t for t, v in series if v > 0)
                label = {'errors': 'errors', 'rx_drops': 'receive drops', 'tx_drops': 'transmit drops'}[field]
                facts = ['%s %s in window (average %.1f/min), first at %s' % (num(total), label, mean, self.when(t))]
                if field == 'rx_drops':
                    facts.append('Linux also counts received frames for protocols nothing handles (for example LLDP or '
                                 'unknown VLAN tags) as receive drops, so this is not necessarily packet loss')
                out.append(self._finding('iface_%s:%s' % (field, name), 'network', 'info' if field == 'rx_drops' else 'warning',
                                         'Packet %s on %s' % (label, name), 'interface %s average 5/min or more and 100+ in window' % label,
                                         facts, t))
        return out

    def _rule_services(self):
        out = []
        latest = self.latest('services')
        if latest:
            for unit in (latest['data'].get('failed') or []):
                out.append(self._finding('unit_failed:%s' % unit, 'services', 'warning', 'Failed systemd unit %s' % unit,
                                         'systemd lists the unit as failed', ['%s is in failed state at %s' % (unit, self.when(latest['_t']))],
                                         latest['_t'], units=[unit]))
            failed = set(latest['data'].get('failed') or [])
            units = {u.get('Id'): u for u in latest['data'].get('systemd') or []}
            for inst in latest['data'].get('procd') or []:
                unit = units.get(inst.get('systemd_unit')) or {}
                # One-shot instances (urandom_seed, acme, ...) exit cleanly: inactive with status 0 is fine.
                clean = unit.get('ActiveState') == 'inactive' and unit.get('ExecMainStatus') in (0, None)
                if inst.get('running') is False and inst.get('systemd_unit') not in failed and not clean:
                    name = '%s/%s' % (inst.get('service'), inst.get('instance'))
                    out.append(self._finding('procd_stopped:%s' % name, 'services', 'warning', 'Service instance %s not running' % name,
                                             'an enabled procd instance is not running',
                                             ['%s not running at %s; systemd unit %s is %s/%s with exit status %s' % (
                                                 name, self.when(latest['_t']), inst.get('systemd_unit') or 'none', unit.get('ActiveState', '?'),
                                                 unit.get('SubState', '?'), unit.get('ExecMainStatus', '?'))],
                                             latest['_t'], units=[inst.get('systemd_unit')] if inst.get('systemd_unit') else []))
        for key in self.derived.keys('restarts.', self.e0, self.e1) + self.derived.keys('respawn.', self.e0, self.e1):
            increase = self.counter_increase(key)
            if increase > 0:
                kind, _, unit = key.partition('.')
                rows = deltas(self.derived.series(key, self.e0 - 900, self.e1))
                t = next((t for t, v in rows if v > 0 and t >= self.e0), None)
                out.append(self._finding('restarts:%s' % unit, 'services', 'warning' if increase >= 3 else 'info',
                                         'Service %s restarted' % unit, 'systemd NRestarts or procd respawn count increased',
                                         ['%s %d time(s) in window, first at %s' % ('restarted' if kind == 'restarts' else 'respawned', increase,
                                                                                     self.when(t) if t else 'unknown')], t, units=[unit]))
        return out

    def _rule_dns(self):
        out = []
        for c in self.dns_clients():
            who = self.name(c['client'])
            if c['answered'] >= 30 and (c['error_pct'] or 0) > 20:
                top = ', '.join('%s (%d)' % kv for kv in c['nx_domains'].most_common(5))
                out.append(self._finding('dns_errors:%s' % c['client'], 'dns', 'warning', 'High DNS error ratio for %s' % who,
                                         'NXDOMAIN+SERVFAIL above 20% with at least 30 answered queries',
                                         ['client: %s' % who, 'answered forward queries: %s; reverse (PTR) lookups excluded: %s' % (
                                             num(c['answered']), num(c['reverse'])),
                                          'NXDOMAIN: %s (%.0f%%), SERVFAIL: %s' % (num(c['nxdomain']), pct(c['nxdomain'], c['answered']), num(c['servfail'])),
                                          'top NXDOMAIN domains: %s' % (top or 'none')],
                                         epoch(c['first']), metric=None))
                out[-1]['client'] = c['client']
            if len(c['entropy_names']) > 20:
                sample = sorted(c['entropy_names'])[:3]
                out.append(self._finding('dns_random_names:%s' % c['client'], 'security', 'warning',
                                         'Many random-looking DNS names from %s' % who,
                                         'more than 20 unique names with a long high-entropy label (possible DGA, tunnelling or tracker IDs)',
                                         ['client: %s' % who, 'unique random-looking names: %d of %d queries' % (len(c['entropy_names']), c['queries']),
                                          'registrable domains involved: %s' % ', '.join(sorted(set(registrable(n) for n in c['entropy_names'])))[:200],
                                          'examples: %s' % ', '.join(sample)], epoch(c['first'])))
                out[-1]['client'] = c['client']
        return out

    @staticmethod
    def _dedupe(events):
        seen, out = set(), []
        for e in events:
            key = e.get('event_id') or json.dumps(e, sort_keys=True)
            if key not in seen:
                seen.add(key)
                out.append(e)
        return out

    def journal_events(self, start=None, end=None):
        s, e = (self.e0 if start is None else start), (self.e1 if end is None else end)
        rows = []
        for record in self.records.get('events') or []:
            for event in record['data'].get('events') or []:
                t = epoch(event.get('event_time'))
                if t is not None and s <= t <= e:
                    rows.append(dict(event, _t=t))
        return sorted(self._dedupe(rows), key=lambda x: x['_t'])

    def _rule_journal(self):
        out, events = [], self.journal_events()
        by_kind = collections.defaultdict(list)
        for e in events:
            by_kind[e.get('kind')].append(e)
        if by_kind.get('oom'):
            rows = by_kind['oom']
            out.append(self._finding('oom', 'memory', 'critical', 'Out-of-memory kills', 'kernel OOM killer signature in the journal',
                                     ['%d OOM events, first at %s' % (len(rows), self.when(rows[0]['_t'])),
                                      'units: %s' % (', '.join(sorted(set(e.get('unit') or 'kernel' for e in rows))))], rows[0]['_t']))
        if by_kind.get('kernel_warning'):
            rows = by_kind['kernel_warning']
            out.append(self._finding('kernel_warning', 'system', 'warning', 'Kernel warnings', 'kernel call trace, watchdog or hardware error signature',
                                     ['%d events (%s), first at %s' % (len(rows), ', '.join(sorted(set(e.get('detail') or '?' for e in rows)))[:120],
                                                                       self.when(rows[0]['_t']))], rows[0]['_t']))
        failures = by_kind.get('auth_failure') or []
        if len(failures) >= 5:
            sources = collections.Counter(e.get('source_address') or 'unknown' for e in failures)
            out.append(self._finding('auth_failures', 'security', 'warning' if len(failures) < 50 else 'critical',
                                     'Repeated authentication failures', '5 or more failed logins in the window (critical at 50)',
                                     ['%d failures, first at %s, last at %s' % (len(failures), self.when(failures[0]['_t']), self.when(failures[-1]['_t'])),
                                      'sources: %s' % ', '.join('%s (%d)' % (self.name(a), n) for a, n in sources.most_common(5)),
                                      'services: %s' % ', '.join(sorted(set(e.get('source') or '?' for e in failures)))], failures[0]['_t']))
        return out

    def _rule_baselines(self):
        out = []
        for metric, spec in BASELINE_METRICS.items():
            b = self.baseline(metric)
            if b['verdict'] == 'unusual':
                series = self.metric_series(metric, self.e0, self.e1)
                t = max(series, key=lambda x: x[1])[0] if series else None
                out.append(self._finding('unusual:%s' % metric, spec['category'], 'info', 'Unusual %s' % spec['label'],
                                         'window value above both the 7-day p95 and 3x the median', [self.baseline_text(b)], t, metric=metric))
        return out

    def _rule_coverage(self):
        out = []
        times = sorted(r['_t'] for r in self.window('system'))
        expected = self.hours * 60
        if expected >= 10:
            gaps = [(a, b) for a, b in zip([self.e0] + times, times + [self.e1]) if b - a > 300]
            if gaps or len(times) < expected * 0.8:
                out.append(self._finding('coverage_gap', 'coverage', 'info', 'Missing samples',
                                         'more than 5 minutes without a system sample, or under 80% of expected samples',
                                         ['%d of about %d expected minute samples' % (len(times), round(expected))] +
                                         (['%d gaps over 5 minutes, about %d minutes missing in total; longest %s to %s' % (
                                             len(gaps), sum(b - a - 60 for a, b in gaps) // 60,
                                             *(self.local(x) for x in max(gaps, key=lambda g: g[1] - g[0])))] if gaps else []),
                                         gaps[0][0] if gaps else None))
        dropped = self.counter_increase('dns.receiver_dropped')
        producer = sum(self.counter_increase(k) for k in self.derived.keys('dns.producer_dropped.', self.e0, self.e1))
        if dropped or producer:
            out.append(self._finding('dns_drops', 'coverage', 'warning', 'DNS observations dropped',
                                     'collector or resolver dropped DNS metadata (DNS itself is unaffected)',
                                     ['collector queue drops: %s, resolver socket drops: %s' % (num(dropped), num(producer))], None))
        if any((r['data'] or {}).get('possible_truncation') for r in self.window('events')):
            out.append(self._finding('journal_truncated', 'coverage', 'info', 'Journal scan truncated',
                                     'a minute had 1000+ journal records; typed events may be missing',
                                     ['some journal scans hit the 1000-record limit'], None))
        return out

    # -- context for one finding
    def context(self, finding, top=5):
        lines = []
        t = finding.get('time')
        if t:
            nearby = [e for e in self.journal_events(t - 300, t + 300)
                      if e.get('kind') != 'auth_success' or finding['category'] == 'security']
            for e in nearby[:top]:
                lines.append(self.event_text(e))
            for name in self._wan_names() if finding['category'] == 'network' else []:
                rows = self.gauge('iface.%s.up' % name, t - 300, t + 300)
                if rows:
                    lines.append('interface %s around %s: %s' % (name, self.local(t), 'down at some point' if any(v == 0 for _, v in rows) else 'up'))
            for rev in self.changes(t - 1800, t + 300)[:3]:
                lines.append('config change %s: revision %s by %s, configs %s' % (
                    self.local(rev['_t']), rev.get('revision') or '?', rev.get('source') or '?', ' '.join(rev.get('configs') or []) or '?'))
        if finding.get('units'):
            wanted = set(finding['units'])
            for e in self.journal_events():
                if e.get('unit') in wanted:
                    lines.append(self.event_text(e))
                    if len(lines) >= top * 2:
                        break
        if finding.get('metric') in BASELINE_METRICS:
            lines.append('baseline: ' + self.baseline_text(self.baseline(finding['metric'])))
        if finding['category'] == 'dns' and finding.get('client'):
            history = self.derived.db.execute('SELECT sum(queries), sum(nxdomain), count(DISTINCT CAST(t/3600 AS INT)) FROM dns_min WHERE client=? AND t>=? AND t<?',
                                              (finding['client'], self.base0, self.e0)).fetchone()
            now = self.derived.db.execute('SELECT sum(queries), sum(nxdomain) FROM dns_min WHERE client=? AND t>=? AND t<=?',
                                          (finding['client'], self.e0, self.e1)).fetchone()
            if now and now[0]:
                lines.append('this client, this window: about %s queries/hour, NXDOMAIN %.0f%%' % (num(now[0] / self.hours), pct(now[1], now[0])))
            if history and history[0]:
                hours = max(history[2], 1)
                lines.append('this client, previous 7 days: about %s queries/hour in hours with traffic, NXDOMAIN %.0f%%' % (
                    num(history[0] / hours), pct(history[1], history[0])))
            else:
                lines.append('this client, previous 7 days: no DNS history')
        return list(dict.fromkeys(lines))

    def event_text(self, e):
        return 'journal %s: %s %s%s%s' % (self.local(e['_t']), e.get('kind'), e.get('unit') or e.get('source') or '',
                                          ' (%s)' % e['detail'] if e.get('detail') else '',
                                          ' from %s' % self.name(e['source_address']) if e.get('source_address') else '')

    def changes(self, start=None, end=None):
        s, e = (self.e0 if start is None else start), (self.e1 if end is None else end)
        rows, seen = [], set()
        for record in self.records.get('changes') or []:
            for rev in record['data'].get('revisions') or []:
                t = epoch(rev.get('event_time'))
                if t is None or not s <= t <= e or rev.get('event_id') in seen:
                    continue
                seen.add(rev.get('event_id'))
                rows.append(dict(rev, _t=t))
        return sorted(rows, key=lambda r: r['_t'])

    # -- state summary
    def state(self):
        s = {}
        system = self.latest('system')
        if system:
            d = system['data']
            memory = d.get('memory') or {}
            s['memory_available_pct'] = pct(memory.get('MemAvailable', 0), memory.get('MemTotal')) if memory.get('MemTotal') else None
            s['memory_total_bytes'] = memory.get('MemTotal')
            s['swap_used_bytes'] = (memory.get('SwapTotal') or 0) - (memory.get('SwapFree') or 0)
            s['load'] = d.get('load')
            s['cpu_count'] = d.get('cpu_count')
            s['uptime_seconds'] = d.get('uptime_seconds')
            s['pressure_avg60'] = {k: ((v or {}).get('some') or {}).get('avg60') for k, v in (d.get('pressure') or {}).items()}
            temps = [t.get('celsius') for t in d.get('temperature') or [] if isinstance(t.get('celsius'), (int, float))]
            s['temperature_max_c'] = max(temps) if temps else None
            s['disks_free_pct'] = {x.get('path'): pct(x.get('available', 0), x.get('total')) for x in d.get('disks') or [] if x.get('total')}
            s['kernel'] = d.get('kernel')
        cpu = [v for _, v in self.cpu_series(self.e0, self.e1)]
        s['cpu_pct_mean'] = statistics.fmean(cpu) if cpu else None
        s['cpu_pct_max'] = max(cpu) if cpu else None
        network = self.latest('network')
        s['wan'] = []
        if network:
            for iface in network['data'].get('interfaces') or []:
                if re.match(r'wan', iface.get('interface') or ''):
                    s['wan'].append({'interface': iface['interface'], 'up': bool(iface.get('up')), 'uptime_seconds': iface.get('uptime'),
                                     'proto': iface.get('proto'), 'device': iface.get('l3_device') or iface.get('device'),
                                     'ipv4': bool(iface.get('ipv4-address')), 'ipv6': bool(iface.get('ipv6-address') or iface.get('ipv6-prefix'))})
        probes = {}
        for key in self.derived.keys('probe.', self.e0, self.e1):
            target, _, field = key[6:].rpartition('.')
            rows = [v for _, v in self.gauge(key)]
            entry = probes.setdefault(target, {'target': target})
            if field == 'ok':
                entry['ok'], entry['total'] = int(sum(rows)), len(rows)
            elif field == 'ms' and rows:
                entry['median_ms'] = statistics.median(rows)
        s['probes'] = sorted(probes.values(), key=lambda p: p['target'])
        ct = self.gauge('ct.pct')
        s['conntrack_pct'] = ct[-1][1] if ct else None
        s['conntrack_count'] = (self.gauge('ct.count') or [(0, None)])[-1][1]
        s['conntrack_max'] = (self.gauge('ct.max') or [(0, None)])[-1][1]
        services = self.latest('services')
        s['failed_units'] = (services['data'].get('failed') or []) if services else None
        s['services_running'] = sum(1 for i in (services['data'].get('procd') or []) if i.get('running')) if services else None
        s['services_total'] = len(services['data'].get('procd') or []) if services else None
        clients = self.dns_clients()
        total = sum(c['queries'] for c in clients)
        answered = sum(c['answered'] for c in clients)
        s['dns'] = {'queries': total, 'clients': len(clients),
                    'nxdomain_pct': pct(sum(c['nxdomain'] for c in clients), answered),
                    'servfail_pct': pct(sum(c['servfail'] for c in clients), answered)}
        s['samples'] = len(self.window('system'))
        s['baselines'] = {m: self.baseline(m) for m in BASELINE_METRICS}
        return s

    def traffic(self, top=5):
        rows = []
        for key in self.derived.keys('if.', self.e0, self.e1):
            name, _, field = key[3:].rpartition('.')
            if field != 'rx_bytes':
                continue
            rx = [v for _, v in self.counter_rate(key, 8)]
            tx = [v for _, v in self.counter_rate('if.%s.tx_bytes' % name, 8)]
            if rx or tx:
                rows.append({'ifname': name, 'rx_bps_mean': statistics.fmean(rx) if rx else None, 'rx_bps_max': max(rx) if rx else None,
                             'tx_bps_mean': statistics.fmean(tx) if tx else None, 'tx_bps_max': max(tx) if tx else None})
        return sorted(rows, key=lambda r: -((r['rx_bps_mean'] or 0) + (r['tx_bps_mean'] or 0)))[:top]

    def firewall_top(self, top=5):
        rows = []
        for key in self.derived.keys('nft.', self.e0, self.e1):
            if not key.endswith('.packets'):
                continue
            name = key[4:-8]
            packets = [v for _, v in self.counter_rate(key)]
            byte_rate = [v for _, v in self.counter_rate('nft.%s.bytes' % name, 8)]
            if packets and max(packets) > 0:
                rows.append({'rule': name, 'pps_mean': statistics.fmean(packets), 'bps_mean': statistics.fmean(byte_rate) if byte_rate else None})
        return sorted(rows, key=lambda r: -r['pps_mean'])[:top]

    def to_json(self, top=10):
        clients = self.dns_clients()
        return {
            'schema_version': '1.1', 'kind': 'router-audit-analysis',
            'window': {'start': N.iso(self.start), 'end': N.iso(self.end), 'hours': self.hours},
            'state': self.state(),
            'findings': [dict(f, context=self.context(f), time=N.iso(f['time']) if f['time'] else None) for f in self.findings()],
            'dns_clients': [{k: (dict(v.most_common(top)) if isinstance(v, collections.Counter) else sorted(v)[:top] if isinstance(v, set) else v)
                             for k, v in dict(c, name=self.name(c['client'])).items()} for c in clients[:top * 2]],
            'traffic': self.traffic(top), 'firewall_top': self.firewall_top(top),
            'changes': [{k: v for k, v in r.items() if k != '_t'} for r in self.changes()],
            'events': [{k: v for k, v in e.items() if k != '_t'} for e in self.journal_events()][-top * 5:],
            'not_measured': NOT_MEASURED,
        }


# ---------------------------------------------------------------- LLM renderers

def detail_level(budget):
    """Token budget -> (top-N list length, include short series)."""
    if budget >= 12000:
        return 20, True
    if budget >= 8000:
        return 10, True
    return 5, False


def clip(lines, budget):
    """Hard limit on characters (chars/4 token estimate) with an explicit truncation line."""
    limit, out, used = budget * 4, [], 0
    for index, line in enumerate(lines):
        if used + len(line) + 1 > limit - 40:
            out.append('[truncated: %d more lines]' % (len(lines) - index))
            break
        out.append(line)
        used += len(line) + 1
    return '\n'.join(out)


def _threshold(value, warn, text, higher_bad=True, fmt='%.0f%%'):
    if value is None:
        return 'unknown'
    bad = value >= warn if higher_bad else value < warn
    return '%s — %s (%s)' % (fmt % value, 'WARN' if bad else 'OK', text)


def overview_lines(a, budget=4000):
    top, _ = detail_level(budget)
    s, findings = a.state(), a.findings()
    counts = collections.Counter(f['severity'] for f in findings)
    lines = ['ROUTER OVERVIEW', 'window: %s' % a.window_label(),
             'findings: %d (%s)' % (len(findings), ', '.join('%d %s' % (counts[k], k) for k in reversed(SEVERITIES) if counts[k]) or 'none'),
             'data: %d minute samples in window' % s['samples'], '', 'STATE']
    lines.append('memory available: %s' % _threshold(s.get('memory_available_pct'), 10, 'warn below 10%', higher_bad=False))
    b = s['baselines']['cpu_pct']
    lines.append('cpu busy: mean %s, max %s — %s' % ('unknown' if s['cpu_pct_mean'] is None else '%.0f%%' % s['cpu_pct_mean'],
                                                    'unknown' if s['cpu_pct_max'] is None else '%.0f%%' % s['cpu_pct_max'], b['verdict']))
    if s.get('load'):
        lines.append('load average: %s%s' % (' / '.join('%.2f' % x for x in s['load']), ' (%s CPUs)' % s['cpu_count'] if s.get('cpu_count') else ''))
    psi = s.get('pressure_avg60') or {}
    if psi:
        lines.append('pressure avg60: cpu %s, memory %s, io %s — %s' % (
            *('?' if psi.get(k) is None else '%.1f' % psi[k] for k in ('cpu', 'memory', 'io')),
            'WARN' if (psi.get('memory') or 0) > 10 else 'OK (warn memory above 10)'))
    if s.get('temperature_max_c') is not None:
        lines.append('temperature max: %.0f °C' % s['temperature_max_c'])
    for path, free in (s.get('disks_free_pct') or {}).items():
        lines.append('disk %s free: %s' % (path, _threshold(free, 10, 'warn below 10%', higher_bad=False)))
    for w in s['wan']:
        lines.append('wan interface %s: %s, %s, uptime %s, IPv4 %s, IPv6 %s' % (
            w['interface'], 'UP' if w['up'] else 'DOWN', w.get('proto') or '?',
            '%dh %02dm' % divmod((w.get('uptime_seconds') or 0) // 60, 60) if w.get('uptime_seconds') else 'unknown',
            'yes' if w['ipv4'] else 'no', 'yes' if w['ipv6'] else 'no'))
    for p in s['probes']:
        lines.append('probe %s: %s/%s ok%s' % (p['target'], p.get('ok', 0), p.get('total', 0),
                                              ', median %.0f ms' % p['median_ms'] if p.get('median_ms') is not None else ''))
    lines.append('conntrack: %s' % (_threshold(s['conntrack_pct'], 80, 'warn at 80%') + (' (%s of %s)' % (num(s['conntrack_count']), num(s['conntrack_max'])) if s['conntrack_max'] else '')
                                    if s['conntrack_pct'] is not None else 'unknown'))
    lines.append('services: %s of %s procd instances running; failed systemd units: %s' % (
        s['services_running'] if s['services_running'] is not None else '?', s['services_total'] if s['services_total'] is not None else '?',
        ', '.join(s['failed_units']) if s['failed_units'] else 'none'))
    dns = s['dns']
    lines.append('dns: %s queries from %d LAN clients, NXDOMAIN %s, SERVFAIL %s' % (
        num(dns['queries']), dns['clients'], 'unknown' if dns['nxdomain_pct'] is None else '%.0f%%' % dns['nxdomain_pct'],
        'unknown' if dns['servfail_pct'] is None else '%.0f%%' % dns['servfail_pct']))
    lines += ['', 'FINDINGS (rule-assigned severity)']
    if not findings:
        lines.append('none — no rule fired in this window')
    for f in findings[:max(top * 2, 10)]:
        lines.append('%s %s %s: %s%s' % (f['id'], f['severity'], f['category'], f['title'], ' at %s' % a.local(f['time']) if f['time'] else ''))
    if len(findings) > max(top * 2, 10):
        lines.append('[%d more findings]' % (len(findings) - max(top * 2, 10)))
    changes = a.changes()
    lines += ['', 'CONFIG CHANGES IN WINDOW']
    lines += ['%s revision %s by %s: %s' % (a.local(r['_t']), r.get('revision') or '?', r.get('source') or '?', ' '.join(r.get('configs') or []) or '?')
              for r in changes[-top:]] or ['none']
    lines += ['', 'BASELINES (previous 7 days)']
    lines += [a.baseline_text(b) for b in s['baselines'].values() if b['verdict'] != 'no data']
    return lines


def finding_lines(a, finding, budget=4000):
    top, series = detail_level(budget)
    lines = ['FINDING %s (%s, %s): %s' % (finding['id'], finding['severity'], finding['category'], finding['title']),
             'window: %s' % a.window_label(), 'rule: %s' % finding['rule'], 'facts:']
    lines += ['- ' + x for x in finding['facts']]
    context = a.context(finding, top)
    lines.append('context:')
    lines += ['- ' + x for x in context] or ['- none recorded around this time']
    if series and finding.get('metric') in BASELINE_METRICS:
        rows = a.metric_series(finding['metric'], a.e0, a.e1)
        buckets = collections.OrderedDict()
        for t, v in rows:
            buckets.setdefault(int(t // 600), []).append(v)
        lines.append('series (10-minute %s): %s' % (BASELINE_METRICS[finding['metric']]['agg'], ', '.join(
            '%s %.1f' % (a.local(k * 600), Analysis.aggregate(v, BASELINE_METRICS[finding['metric']]['agg'])) for k, v in buckets.items())))
    if finding['category'] in NOT_MEASURED:
        lines.append('not measured: %s' % NOT_MEASURED[finding['category']])
    return lines


def topic_lines(a, topic, budget=4000):
    top, _ = detail_level(budget)
    s = a.state()
    related = [f for f in a.findings() if f['category'] == topic or (topic == 'logs' and f['category'] == 'security')
               or (topic == 'clients' and f['category'] in ('dns', 'security'))]
    lines = ['TOPIC %s' % topic.upper(), 'window: %s' % a.window_label()]
    if topic == 'system':
        lines += [x for x in overview_lines(a, budget) if x.split(':')[0] in ('memory available', 'cpu busy', 'load average', 'pressure avg60', 'temperature max')
                  or x.startswith('disk ')]
        lines += [a.baseline_text(s['baselines'][m]) for m in ('cpu_pct', 'load1', 'psi_memory', 'psi_io')]
        lines.append('kernel: %s, uptime %s' % (s.get('kernel') or '?', '%dd %dh' % divmod(int((s.get('uptime_seconds') or 0) // 3600), 24)))
    elif topic == 'wan':
        lines += [x for x in overview_lines(a, budget) if x.startswith(('wan interface ', 'probe '))]
        for e in [e for e in a.journal_events() if e.get('kind') in ('wan_down', 'wan_up')][-top:]:
            lines.append(a.event_text(e))
        for t in a.traffic(top):
            lines.append('interface %s: rx mean %s (max %s), tx mean %s (max %s)' % (t['ifname'], bits(t['rx_bps_mean']), bits(t['rx_bps_max']),
                                                                                 bits(t['tx_bps_mean']), bits(t['tx_bps_max'])))
    elif topic == 'dns':
        dns = s['dns']
        lines.append('total: %s queries from %d LAN clients, NXDOMAIN %s' % (num(dns['queries']), dns['clients'],
                                                                           'unknown' if dns['nxdomain_pct'] is None else '%.0f%%' % dns['nxdomain_pct']))
        lines += [a.baseline_text(s['baselines'][m]) for m in ('dns_qpm', 'dns_nx_pct')]
        domains = collections.Counter()
        for c in a.dns_clients():
            domains.update(c['domains'])
        lines.append('top domains: %s' % ', '.join('%s (%d)' % kv for kv in domains.most_common(top)))
        lines.append('not measured: %s' % NOT_MEASURED['dns'])
    elif topic == 'clients':
        for c in a.dns_clients()[:top * 2]:
            lines.append('%s: %s DNS queries, errors %s, %d domains%s, random-looking names %d, top %s' % (
                a.name(c['client']), num(c['queries']), 'unknown' if c['error_pct'] is None else '%.0f%%' % c['error_pct'],
                c['unique_domains'], '' if c['new_domains'] is None else ' (%d new this window)' % len(c['new_domains']),
                len(c['entropy_names']), ', '.join(d for d, _ in c['domains'].most_common(3))))
    elif topic == 'conntrack':
        lines += [x for x in overview_lines(a, budget) if x.startswith('conntrack:')]
        lines.append(a.baseline_text(s['baselines']['conntrack_pct']))
        lines.append('increase in window: insert_failed %s, drop %s, early_drop %s' % tuple(num(a.counter_increase('ct.' + k)) for k in ('insert_failed', 'drop', 'early_drop')))
    elif topic == 'services':
        latest = a.latest('services')
        lines += [x for x in overview_lines(a, budget) if x.startswith('services')]
        if latest:
            for inst in [i for i in latest['data'].get('procd') or [] if not i.get('running') or i.get('respawn_count')][:top]:
                lines.append('%s/%s: running %s, respawns %s' % (inst.get('service'), inst.get('instance'), inst.get('running'), inst.get('respawn_count', 0)))
            restarted = [u for u in latest['data'].get('systemd') or [] if u.get('NRestarts')]
            for unit in restarted[:top]:
                lines.append('%s: %s/%s, NRestarts %s total' % (unit.get('Id'), unit.get('ActiveState'), unit.get('SubState'), unit.get('NRestarts')))
        lines.append('not measured: %s' % NOT_MEASURED['services'])
    elif topic == 'firewall':
        for r in a.firewall_top(top):
            lines.append('rule %s: %.1f packets/s, %s' % (r['rule'], r['pps_mean'], bits(r['bps_mean'])))
        lines.append('not measured: %s' % NOT_MEASURED['network'])
    elif topic == 'changes':
        lines += ['%s revision %s by %s: %s; %s' % (a.local(r['_t']), r.get('revision') or '?', r.get('source') or '?', ' '.join(r.get('configs') or []) or '?',
                                                   '; '.join('%s.%s.%s %s' % (c['config'], c['section'], c['option'],
                                                                              'redacted' if c.get('values') == 'redacted' else '%s -> %s' % (c.get('old'), c.get('new')))
                                                             for c in (r.get('changes') or [])[:top]) or 'no option detail')
                  for r in a.changes()[-top * 2:]] or ['no UCI changes in window']
    elif topic == 'logs':
        events = a.journal_events()
        counts = collections.Counter(e.get('kind') for e in events)
        lines.append('typed journal events: %s' % (', '.join('%s %d' % kv for kv in counts.most_common()) or 'none'))
        for e in events[-top * 2:]:
            lines.append(a.event_text(e)[len('journal '):])
        lines.append('not measured: %s' % NOT_MEASURED['security'])
    else:
        raise ValueError('unknown topic')
    lines.append('related findings: %s' % (', '.join('%s %s: %s' % (f['id'], f['severity'], f['title']) for f in related) or 'none'))
    return lines


def render(lines, budget, fmt):
    if fmt == 'llm-json':
        sections, current = {}, None
        for line in lines:
            if not line:
                continue
            if line.isupper() or line.endswith(':') and not line.startswith('- '):
                current = line.rstrip(':')
                sections.setdefault(current, [])
            else:
                sections.setdefault(current or 'header', []).append(line.lstrip('- '))
        text = json.dumps(sections, ensure_ascii=False, separators=(',', ':'))
        return text if len(text) <= budget * 4 else clip([text[:budget * 4 - 60]], budget) + '"]}'
    return clip(lines, budget)


def overview(a, budget=4000, fmt='llm'):
    return render(overview_lines(a, budget), budget, fmt)


def finding_text(a, finding, budget=4000, fmt='llm'):
    return render(finding_lines(a, finding, budget), budget, fmt)


def topic_text(a, topic, budget=4000, fmt='llm'):
    return render(topic_lines(a, topic, budget), budget, fmt)


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('database')
    group = p.add_mutually_exclusive_group()
    group.add_argument('--hours', type=float, default=1.0)
    group.add_argument('--window', choices=sorted(WINDOWS))
    p.add_argument('--end', help='ISO-8601 window end (default: newest record)')
    p.add_argument('--format', choices=['json', 'llm', 'llm-json'], default='json')
    p.add_argument('--budget', type=int, default=4000, help='LLM view token budget (chars/4 estimate)')
    p.add_argument('--finding', help='render one finding (F1, F2, ... or its key)')
    p.add_argument('--topic', choices=TOPICS)
    p.add_argument('--cache', default='auto', help="derived sample cache path, 'auto' (DB.derived) or 'none'")
    a = p.parse_args(argv)
    if not 500 <= a.budget <= 64000:
        p.error('budget must be 500..64000')
    hours = WINDOWS[a.window] if a.window else a.hours
    if not 0 < hours <= 24 * 7:
        p.error('window must be within 7 days')
    end = N.parse_time(a.end) if a.end else None
    if a.end and not end:
        p.error('invalid --end')
    an = Analysis(a.database, hours, end=end, cache=a.cache)
    with an:
        _print(an, a, p)


def _print(an, a, p):
    if a.finding:
        f = an.finding(a.finding)
        if not f:
            p.error('no such finding in this window')
        print(json.dumps(dict(f, context=an.context(f)), indent=2, default=str) if a.format == 'json' else finding_text(an, f, a.budget, a.format))
    elif a.topic:
        print(topic_text(an, a.topic, a.budget, 'llm' if a.format == 'json' else a.format))
    elif a.format == 'json':
        print(json.dumps(an.to_json(), indent=2, default=str))
    else:
        print(overview(an, a.budget, a.format))
        for f in an.findings():
            print()
            print(finding_text(an, f, a.budget, a.format))


if __name__ == '__main__':
    main()
