#!/usr/bin/env python3
"""Build synthetic router-audit puller databases with one injected fault each.

Each database holds a baseline period (default 7 days, coarse samples, the oldest days in
schema 1.0 to exercise the upgrade path) followed by a one-hour test window sampled every
minute in schema 1.1. A `quiet` fixture has no fault: nothing may be reported for it.

    python3 scripts/tests/router-audit-fixtures.py --out DIR [--days 7]

writes DIR/<fixture>.sqlite and DIR/manifest.json (expected categories and severities).
"""
import argparse
import base64
import datetime as dt
import json
import pathlib
import random
import sqlite3

END = dt.datetime(2026, 11, 6, 3, 0, tzinfo=dt.timezone.utc)
HOST = 'f1x7ure0host0000000a'
CLIENTS = [('192.0.2.10', 'aa:00:00:00:00:10', 'laptop'), ('192.0.2.11', 'aa:00:00:00:00:11', 'phone'),
           ('192.0.2.12', 'aa:00:00:00:00:12', 'tv'), ('192.0.2.50', 'aa:00:00:00:00:50', 'iot-cam'),
           ('192.0.2.60', 'aa:00:00:00:00:60', 'lab-vm')]
IPV6 = {'2001:db8::10': 'aa:00:00:00:00:10'}
DOMAINS = ['example.com', 'www.example.org', 'cdn.example.net', 'api.example.com', 'news.example.cn',
           'mail.example.co.uk', 'time.example.net', 'updates.example.org']
MANIFEST = {
    'quiet': {'expected': [], 'description': 'normal operation, no fault'},
    'wan_flap': {'expected': [{'category': 'wan', 'severity': 'critical'}],
                 'description': 'WAN interface down and all probes failing for 5 minutes'},
    'conntrack_full': {'expected': [{'category': 'conntrack', 'severity': 'warning'}],
                       'description': 'conntrack table at 90% for the last 30 minutes'},
    'nxdomain_storm': {'expected': [{'category': 'dns', 'severity': 'warning'}],
                       'description': 'one LAN client gets mostly NXDOMAIN answers'},
    'random_names': {'expected': [{'category': 'security', 'severity': 'warning'}],
                     'description': 'one LAN client queries many random-looking names'},
    'failed_unit': {'expected': [{'category': 'services', 'severity': 'warning'}],
                    'description': 'a service restarts repeatedly and ends failed'},
    'memory_pressure': {'expected': [{'category': 'memory', 'severity': 'critical'}],
                        'description': 'available memory 6%, memory pressure stalls and an OOM kill'},
}


def iso(moment):
    return moment.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


class Router:
    def __init__(self, fault, seed):
        self.fault, self.rng = fault, random.Random(seed)
        self.boot, self.boot_start = 'boot-a', END - dt.timedelta(days=30)
        self.cpu = {'user': 0, 'nice': 0, 'system': 0, 'idle': 0, 'iowait': 0, 'irq': 0, 'softirq': 0, 'steal': 0}
        self.links = {n: {'rx': 0, 'tx': 0} for n in ('eth0', 'br-lan', 'wg0')}
        self.nft = {'!fw4: Accept traffic from lan to wan IPv4/IPv6': [0, 0], '!fw4: Handle wan IPv4/IPv6 input traffic': [0, 0]}
        self.restarts = 0
        self.seq = 0
        self.last = None
        self.revision = 40

    def reboot(self, moment):
        self.boot, self.boot_start = 'boot-b', moment
        for k in self.cpu:
            self.cpu[k] = 0
        for v in self.links.values():
            v['rx'] = v['tx'] = 0
        for v in self.nft.values():
            v[0] = v[1] = 0
        self.restarts = 0

    def advance(self, moment):
        seconds = 60 if self.last is None else (moment - self.last).total_seconds()
        self.last = moment
        busy = min(95, max(1, self.rng.gauss(8, 2)))
        ticks = seconds * 100 * 4
        self.cpu['user'] += int(ticks * busy / 100 * 0.6)
        self.cpu['system'] += int(ticks * busy / 100 * 0.3)
        self.cpu['softirq'] += int(ticks * busy / 100 * 0.1)
        self.cpu['idle'] += int(ticks * (100 - busy) / 100)
        for name, rate in (('eth0', 2e6), ('br-lan', 2.2e6), ('wg0', 1e4)):
            self.links[name]['rx'] += int(seconds * rate / 8 * self.rng.uniform(0.7, 1.3))
            self.links[name]['tx'] += int(seconds * rate / 16 * self.rng.uniform(0.7, 1.3))
        for v in self.nft.values():
            packets = int(seconds * self.rng.uniform(50, 150))
            v[0] += packets
            v[1] += packets * 800


def minute_of(moment):
    return int((moment - (END - dt.timedelta(hours=1))).total_seconds() // 60)


def build(path, fault='quiet', days=7, step=600, seed=1, legacy_days=3):
    path = pathlib.Path(path)
    if path.exists():
        path.unlink()
    db = sqlite3.connect(str(path))
    db.executescript('CREATE TABLE batches(id TEXT PRIMARY KEY, time TEXT, module TEXT, payload TEXT);'
                     'CREATE TABLE state(host TEXT PRIMARY KEY, cursor TEXT);')
    router = Router(fault, seed)
    test_start = END - dt.timedelta(hours=1)
    times, moment = [], END - dt.timedelta(days=days) - dt.timedelta(hours=1)
    while moment < test_start:
        times.append(moment)
        moment += dt.timedelta(seconds=step)
    times += [test_start + dt.timedelta(minutes=m + 1) for m in range(60)]
    reboot_at = END - dt.timedelta(days=days / 2)
    rows = []
    for moment in times:
        if router.boot == 'boot-a' and moment >= reboot_at:
            router.reboot(moment)
        router.advance(moment)
        legacy = moment < END - dt.timedelta(days=days) + dt.timedelta(days=legacy_days) and legacy_days > 0
        in_test = moment > test_start
        for record in records(router, moment, legacy, minute_of(moment) if in_test else None, step if not in_test else 60):
            rows.append((HOST + ':' + record['module'] + ':' + record['collected_at'], record['collected_at'], record['module'],
                         json.dumps(record, separators=(',', ':'))))
    with db:
        db.executemany('INSERT INTO batches VALUES(?,?,?,?)', rows)
    db.close()
    return path


def envelope(module, moment, data, router, legacy, offset_ms=0):
    collected = moment + dt.timedelta(milliseconds=offset_ms)
    stamp = collected.isoformat() if legacy and module not in ('dns_minute', 'dns_queries') else iso(collected)
    record = {'schema_version': '1.0' if legacy else '1.1', 'host_id': HOST, 'boot_id': router.boot,
              'collected_at': iso(collected), 'module': module, 'status': 'ok', 'data': data, 'errors': []}
    if module not in ('dns_minute', 'dns_queries'):
        start = moment - dt.timedelta(minutes=2)
        record['window'] = {'start': start.isoformat() if legacy else iso(start), 'end': stamp if legacy else iso(collected)}
    return record


def records(router, moment, legacy, minute, step):
    f, rng = router.fault, router.rng
    test = minute is not None
    out = []
    # system
    avail = 0.69
    psi_mem = rng.uniform(0, 0.4)
    if test and f == 'memory_pressure' and minute >= 30:
        avail, psi_mem = 0.06, 25.0
    total = 8 * 1024 ** 3
    memory = {'MemTotal': total, 'MemAvailable': int(total * avail), 'MemFree': int(total * avail / 3), 'Cached': total // 3,
              'SwapTotal': 8 * 1024 ** 3, 'SwapFree': 8 * 1024 ** 3 - 50 * 1024 ** 2, 'Shmem': 300 * 1024 ** 2, 'Slab': 500 * 1024 ** 2,
              'SReclaimable': 400 * 1024 ** 2, 'Dirty': 1024 ** 2, 'Committed_AS': 6 * 1024 ** 3, 'VmallocTotal': 2 ** 45}
    pressure = {'cpu': {'some': {'avg10': 0.5, 'avg60': round(rng.uniform(0, 1), 2), 'avg300': 0.4, 'total': 1000}},
                'memory': {'some': {'avg10': psi_mem, 'avg60': round(psi_mem, 2), 'avg300': psi_mem / 2, 'total': 10},
                           'full': {'avg10': 0.0, 'avg60': 0.0, 'avg300': 0.0, 'total': 5}},
                'io': {'some': {'avg10': 0.1, 'avg60': round(rng.uniform(0, 1), 2), 'avg300': 0.1, 'total': 100},
                       'full': {'avg10': 0.0, 'avg60': 0.0, 'avg300': 0.0, 'total': 50}}}
    cpu = dict(router.cpu)
    system = {'load': [round(rng.uniform(0.1, 0.5), 2), 0.3, 0.3], 'uptime_seconds': (moment - router.boot_start).total_seconds(),
              'temperature': [{'sensor': 'x86_pkg_temp', 'celsius': round(rng.uniform(44, 50), 1)}],
              'disks': [{'path': '/', 'total': 100 * 1024 ** 3, 'available': 63 * 1024 ** 3}, {'path': '/srv', 'total': 100 * 1024 ** 3, 'available': 63 * 1024 ** 3}],
              'kernel': '7.3.1-51-openwrt'}
    if legacy:
        system['memory_bytes'] = memory
        system['cpu_ticks'] = 'cpu  ' + ' '.join(str(cpu[k]) for k in ('user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal')) + ' 0 0'
        system['pressure'] = {k: '\n'.join('%s %s' % (kind, ' '.join('%s=%s' % kv for kv in vals.items())) for kind, vals in v.items()) + '\n'
                              for k, v in pressure.items()}
    else:
        system.update(memory={k: v for k, v in memory.items() if k != 'VmallocTotal'}, cpu=cpu, pressure=pressure, cpu_count=4)
    out.append(envelope('system', moment, system, router, legacy, 1))
    # network
    wan_down = test and f == 'wan_flap' and 20 <= minute <= 24
    links = [{'ifname': name, 'operstate': 'UP', 'mtu': 1500, 'link_type': 'ether',
              'stats64': {'rx': {'bytes': v['rx'], 'packets': v['rx'] // 800, 'errors': 0, 'dropped': 0},
                          'tx': {'bytes': v['tx'], 'packets': v['tx'] // 800, 'errors': 0, 'dropped': 0}}}
             for name, v in router.links.items()]
    if legacy:
        links.insert(0, {'ifname': 'lo', 'operstate': 'UNKNOWN', 'stats64': {'rx': {'bytes': 1}, 'tx': {'bytes': 1}}, 'address': '00:00:00:00:00:00'})
    interfaces = [{'interface': 'lan', 'up': True, 'uptime': 50000, 'l3_device': 'br-lan', 'proto': 'static', 'ipv4-address': [{'address': '192.0.2.1', 'mask': 24}]},
                  {'interface': 'wan', 'up': not wan_down, 'uptime': 0 if wan_down else 40000, 'l3_device': 'eth0', 'proto': 'dhcp',
                   'ipv4-address': [] if wan_down else [{'address': '203.0.113.7', 'mask': 24}]},
                  {'interface': 'wan6', 'up': not wan_down, 'uptime': 0 if wan_down else 40000, 'l3_device': 'eth0', 'proto': 'dhcpv6',
                   'ipv6-address': [] if wan_down else [{'address': '2001:db8:1::7', 'mask': 64}]}]
    probes = [{'target': t, 'kind': k, 'ok': not wan_down, 'elapsed_ms': 2000.0 if wan_down else round(rng.uniform(8, 20), 1), 'path': 'system_default'}
              for t, k in (('1.1.1.1', 'tcp443'), ('2606:4700:4700::1111', 'tcp443'), ('223.5.5.5', 'dns'))]
    out.append(envelope('network', moment, {'interfaces': interfaces, 'links': links, 'routes': {}, 'probes': probes, 'rules': {}}, router, legacy, 2))
    # firewall
    ct_max = 65536
    count = int(ct_max * rng.uniform(0.04, 0.06))
    if test and f == 'conntrack_full' and minute >= 30:
        count = int(ct_max * 0.90)
    stats = {'entries': count, 'clashres': 0, 'found': 0, 'new': 0, 'invalid': 1200, 'ignore': 0, 'delete': 0, 'chainlength': 0,
             'insert': 0, 'insert_failed': 0, 'drop': 0, 'early_drop': 0, 'icmp_error': 0, 'expect_new': 0, 'expect_create': 0,
             'expect_delete': 0, 'search_restart': 40}
    rules = [{'family': 'inet', 'table': 'fw4', 'chain': 'forward_lan' if i == 0 else 'input_wan', 'handle': 600 + i,
              **({} if legacy else {'comment': name}), 'counters': [{'packets': v[0], 'bytes': v[1]}]}
             for i, (name, v) in enumerate(router.nft.items())]
    if legacy:
        rules.append({'family': 'inet', 'table': 'fw4', 'chain': 'input', 'handle': 650, 'counters': []})
        header = ' '.join(stats)
        rows = [' '.join('%08x' % ((v if k == 'entries' else v // 4)) for k, v in stats.items()) for _ in range(4)]
        firewall = {'rules': rules, 'conntrack': {'count': '%d\n' % count, 'max': '%d\n' % ct_max, 'acct': '0\n'},
                    'conntrack_stats': header + '\n' + '\n'.join(rows) + '\n'}
    else:
        firewall = {'rules': rules, 'conntrack': {'count': count, 'max': ct_max, 'acct': 0}, 'conntrack_stats': stats}
    firewall.update(wireguard={'wg0': {'latest-handshakes': [], 'transfer': [{'peer': 'peerhash0001', 'values': [str(router.links['wg0']['rx']), str(router.links['wg0']['tx'])]}]}},
                    nlbwmon=None, coverage='fixture')
    out.append(envelope('firewall', moment, firewall, router, legacy, 3))
    # services
    failed_unit = 'openwrt-ddns@instance1.service'
    if test and f == 'failed_unit' and 10 <= minute <= 15:
        router.restarts += 1
    units = [{'Id': 'openwrt-dnsmasq@cfg01411c.service', 'ActiveState': 'active', 'SubState': 'running', 'NRestarts': 0, 'ExecMainCode': 0, 'ExecMainStatus': 0},
             {'Id': failed_unit, 'ActiveState': 'failed' if test and f == 'failed_unit' and minute >= 15 else 'active',
              'SubState': 'failed' if test and f == 'failed_unit' and minute >= 15 else 'running', 'NRestarts': router.restarts,
              'ExecMainCode': 1, 'ExecMainStatus': 1 if test and f == 'failed_unit' and minute >= 15 else 0},
             {'Id': 'sshd.service', 'ActiveState': 'active', 'SubState': 'running', 'NRestarts': 0, 'ExecMainCode': 0, 'ExecMainStatus': 0},
             # one-shot instance that exited cleanly: must not be reported
             {'Id': 'openwrt-urandom_seed@urandom_seed.service', 'ActiveState': 'inactive', 'SubState': 'dead', 'NRestarts': 0, 'ExecMainCode': 0, 'ExecMainStatus': 0}]
    failed = [failed_unit] if test and f == 'failed_unit' and minute >= 15 else []
    procd = [{'service': 'dnsmasq', 'instance': 'cfg01411c', 'running': True, 'systemd_unit': units[0]['Id'], 'respawn_count': 0},
             {'service': 'ddns', 'instance': 'instance1', 'running': not failed, 'systemd_unit': failed_unit, 'respawn_count': 0},
             {'service': 'urandom_seed', 'instance': 'urandom_seed', 'running': False, 'systemd_unit': 'openwrt-urandom_seed@urandom_seed.service'}]
    if legacy:
        services = {'procd': procd, 'systemd': '\n\n'.join('\n'.join('%s=%s' % kv for kv in u.items()) for u in units) + '\n',
                    'failed': ''.join('● %s loaded failed failed X\n' % u for u in failed)}
    else:
        services = {'procd': procd, 'systemd': units, 'failed': failed}
    out.append(envelope('services', moment, services, router, legacy, 4))
    # identity (hourly, and at the start of the test window)
    if moment.minute == 0 or (test and minute == 1):
        leases = [{'mac': mac, 'ip': ip, 'hostname': name, ('expires_epoch' if legacy else 'expires'):
                   (str(int(moment.timestamp()) + 43200) if legacy else iso(moment + dt.timedelta(hours=12)))} for ip, mac, name in CLIENTS]
        neighbours = [{'dst': ip, 'dev': 'br-lan', 'lladdr': mac, 'state': ['REACHABLE']} for ip, mac in IPV6.items()]
        out.append(envelope('identity', moment, {'dhcp4': leases, 'dhcp6': {'device': {}}, 'neighbors': neighbours, 'coverage': 'fixture'}, router, legacy, 5))
    # journal events
    events = []

    def event(kind, detail, unit=None, source=None, address=None, second=0):
        stamp = moment - dt.timedelta(seconds=30 - second)
        router.seq += 1
        e = {'event_id': '%032x' % router.seq, 'time_quality': 'journal_ingest', 'kind': kind, 'unit': unit, 'source': source,
             'source_address': address}
        if legacy:
            e['event_time_us'] = str(int(stamp.timestamp() * 1e6))
        else:
            e.update(event_time=iso(stamp), detail=detail)
        events.append(e)
    if test and f == 'wan_flap' and minute == 20:
        event('wan_down', 'link is down', 'openwrt-netifd.service', 'netifd')
    if test and f == 'wan_flap' and minute == 25:
        event('wan_up', 'is now up', 'openwrt-netifd.service', 'netifd')
    if test and f == 'failed_unit' and 10 <= minute <= 15:
        event('service_failure', 'Main process exited', failed_unit, 'systemd')
    if test and f == 'memory_pressure' and minute == 40:
        event('oom', 'Killed process', None, 'kernel')
    out.append(envelope('events', moment, {'events': events, 'coverage': 'fixture', 'scan_limit': 1000, 'possible_truncation': False}, router, legacy, 6))
    # UCI change once a day in the baseline, never in the quiet test window
    revisions = []
    if not test and moment.hour == 2 and moment.minute < step / 60:
        router.revision += 1
        stamp = moment - dt.timedelta(seconds=40)
        revisions.append({'event_id': '%040x' % router.revision, 'event_time': int(stamp.timestamp()) if legacy else iso(stamp),
                          'revision': str(router.revision), 'source': 'luci', 'configs': ['dhcp'], 'diff_available': True,
                          'changes': [{'config': 'dhcp', 'section': 'lan', 'option': 'leasetime', 'values': 'redacted'}]})
    out.append(envelope('changes', moment, {'revisions': revisions, 'coverage': 'fixture'}, router, legacy, 7))
    # DNS: one minute of observations per sample
    dns = []
    normal = [(ip, 8) for ip, _, _ in CLIENTS[:3]] + [('2001:db8::10', 3), ('192.0.2.50', 2), ('192.0.2.60', 2)]
    for client, count in normal:
        for _ in range(max(1, int(rng.gauss(count, 1)))):
            nx = rng.random() < 0.03
            dns.append((client, rng.choice(DOMAINS), 3 if nx else 0))
    # reverse lookups for unnamed addresses normally fail; must not count as DNS errors
    for _ in range(4):
        dns.append(('192.0.2.10', '%x.0.8.b.d.0.1.0.0.2.ip6.arpa' % rng.randrange(16), 3))
    if test and f == 'nxdomain_storm':
        for _ in range(12):
            dns.append(('192.0.2.50', 'cam%04d.badupdate.example' % rng.randrange(10000), 3 if rng.random() < 0.7 else 0))
    if test and f == 'random_names':
        for _ in range(6):
            label = base64.b32encode(rng.randbytes(20)).decode().lower().rstrip('=')
            dns.append(('192.0.2.60', '%s.t.tunnel-example.net' % label, 0))
    events_out, groups = [], {}
    for index, (client, qname, rcode) in enumerate(dns):
        router.seq += 1
        port = rng.randrange(20000, 65000)
        stamp = moment - dt.timedelta(seconds=59) + dt.timedelta(seconds=index * 50 / max(len(dns), 1))
        e = {'source': 'daed', 'source_epoch': '4242-1', 'source_seq': router.seq, 'event_time': iso(stamp),
             'client': ('[%s]:%d' % (client, port) if ':' in client else '%s:%d' % (client, port)) if legacy else client,
             'qname': qname + '.', 'qtype': 1, 'rcode': rcode, 'cache': rng.random() < 0.3, 'duration_ms': round(rng.uniform(1, 40), 2),
             'failed': False, 'producer_dropped': 0}
        if not legacy:
            e['client_port'] = port
        events_out.append(e)
        key = e['client']
        g = groups.setdefault(key, {'source': 'daed', 'client': key, 'internal': False, 'queries': 0, 'rcodes': {}, 'qtypes': {'1': 0},
                                    'unique_domains': 0, 'length_max': 0, '_names': set()})
        g['queries'] += 1
        g['rcodes'][str(rcode)] = g['rcodes'].get(str(rcode), 0) + 1
        g['qtypes']['1'] += 1
        g['_names'].add(qname)
        g['length_max'] = max(g['length_max'], len(qname) + 1)
        # daed forwards upstream to dnsmasq over loopback: internal duplicate
        if rng.random() < 0.7:
            router.seq += 1
            events_out.append({'source': 'dnsmasq', 'source_epoch': '1700000000-99', 'source_seq': router.seq, 'event_time': iso(stamp),
                               'client': '127.0.0.1', **({} if legacy else {'client_port': None}), 'qname': qname, 'qtype': 1, 'rcode': rcode,
                               'duration_ms': None, 'cache': None, 'producer_dropped': 0})
    internal = sum(1 for e in events_out if e['source'] == 'dnsmasq')
    clients = [dict({k: v for k, v in g.items() if k != '_names'}, unique_domains=len(g['_names'])) for g in groups.values()]
    if internal:
        clients.append({'source': 'dnsmasq', 'client': '127.0.0.1', 'internal': True, 'queries': internal, 'rcodes': {'0': internal},
                        'qtypes': {'1': internal}, 'unique_domains': 0, 'length_max': 0})
    receiver = {'received': router.seq, 'dropped': 0}
    out.append(envelope('dns_minute', moment, {'clients': clients, 'coverage': 'fixture', 'receiver': receiver}, router, legacy, 8))
    out.append(envelope('dns_queries', moment, {'events': events_out, 'receiver': receiver, 'coverage': 'fixture'}, router, legacy, 9))
    return out


def build_all(out, days=7, step=600, legacy_days=3):
    out = pathlib.Path(out)
    out.mkdir(parents=True, exist_ok=True)
    for index, fault in enumerate(MANIFEST):
        build(out / ('%s.sqlite' % fault), fault, days=days, step=step, seed=index + 1, legacy_days=legacy_days)
    (out / 'manifest.json').write_text(json.dumps({'end': iso(END), 'fixtures': MANIFEST}, indent=2) + '\n')
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument('--out', required=True)
    p.add_argument('--days', type=int, default=7)
    p.add_argument('--step', type=int, default=600, help='baseline sample spacing in seconds')
    a = p.parse_args()
    print(build_all(a.out, a.days, a.step))


if __name__ == '__main__':
    main()
