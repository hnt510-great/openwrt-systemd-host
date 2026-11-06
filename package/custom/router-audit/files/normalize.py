"""Shared router-audit parsers and schema 1.0 -> 1.1 record upgrade.

Standard library only. Installed on the router as /usr/libexec/router-audit-normalize.py
(loaded by the collector) and on Debian as /usr/share/router-audit/normalize.py (loaded
by analyze.py, explain.py and mcp_server.py). One implementation for both sides.
"""
import datetime as dt
import ipaddress
import re

SCHEMA = '1.1'
MEMORY_KEYS = ('MemTotal', 'MemAvailable', 'MemFree', 'Cached', 'SwapTotal', 'SwapFree',
               'Shmem', 'Slab', 'SReclaimable', 'Dirty', 'Committed_AS')
CPU_FIELDS = ('user', 'nice', 'system', 'idle', 'iowait', 'irq', 'softirq', 'steal')
LINK_FIELDS = ('ifname', 'operstate', 'mtu', 'master', 'link_type', 'stats64')
INTERNAL_CLIENTS = ('127.0.0.1', '::1')


def iso(value):
    """ISO-8601 UTC with Z from epoch seconds (int, float or numeric string) or a datetime."""
    if value is None or value == '':
        return None
    if isinstance(value, dt.datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=dt.timezone.utc)
    else:
        moment = dt.datetime.fromtimestamp(float(value), dt.timezone.utc)
    return moment.astimezone(dt.timezone.utc).isoformat().replace('+00:00', 'Z')


def iso_us(value):
    """ISO-8601 UTC from epoch microseconds (journal __REALTIME_TIMESTAMP)."""
    if value is None or value == '':
        return None
    return iso(int(value) / 1e6)


def iso_text(value):
    """Re-render an ISO string (with +00:00 or Z) as Z form; None when unparseable."""
    moment = parse_time(value)
    return iso(moment) if moment else None


def parse_time(value):
    if not isinstance(value, str) or not value:
        return None
    try:
        moment = dt.datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=dt.timezone.utc)


def client_addr(value):
    """Split a resolver client into (address, port). Ports change per query and must not
    identify a client. IPv4-mapped IPv6 is reduced to IPv4."""
    if not isinstance(value, str) or not value:
        return 'unknown', None
    text, port = value.strip(), None
    match = re.fullmatch(r'\[([^\]]+)\](?::(\d+))?', text)
    if match:
        text, port = match.group(1), match.group(2)
    elif text.count(':') == 1:
        host, _, tail = text.partition(':')
        if tail.isdigit():
            text, port = host, tail
    text = text.split('%', 1)[0]
    try:
        address = ipaddress.ip_address(text)
    except ValueError:
        return text, int(port) if port else None
    if address.version == 6 and address.ipv4_mapped:
        address = address.ipv4_mapped
    return str(address), int(port) if port else None


def is_internal(address):
    return address in INTERNAL_CLIENTS


def parse_cpu(line):
    """First /proc/stat line -> tick counters."""
    if isinstance(line, dict):
        return line
    words = (line or '').split()
    if not words or words[0] != 'cpu':
        return None
    values = [int(x) for x in words[1:1 + len(CPU_FIELDS)]]
    return dict(zip(CPU_FIELDS, values))


def parse_pressure(text):
    """One /proc/pressure/* file -> {some|full: {avg10, avg60, avg300, total}}."""
    if isinstance(text, dict) or text is None:
        return text
    result = {}
    for line in text.splitlines():
        words = line.split()
        if not words:
            continue
        values = {}
        for word in words[1:]:
            key, _, number = word.partition('=')
            try:
                values[key] = int(number) if key == 'total' else float(number)
            except ValueError:
                pass
        result[words[0]] = values
    return result


def select_memory(memory):
    return {k: memory[k] for k in MEMORY_KEYS if k in (memory or {})}


def parse_systemctl_show(text):
    """`systemctl show UNIT... -p ...` blocks -> list of property dicts."""
    if isinstance(text, list) or text is None:
        return text
    units, current = [], {}
    for line in text.splitlines() + ['']:
        if not line.strip():
            if current:
                units.append(current)
            current = {}
            continue
        key, sep, value = line.partition('=')
        if sep:
            current[key] = int(value) if key in ('NRestarts', 'ExecMainCode', 'ExecMainStatus') and value.lstrip('-').isdigit() else value
    return units


def parse_failed_units(text):
    if isinstance(text, list) or text is None:
        return text
    units = []
    for line in text.splitlines():
        words = line.split()
        if words and words[0] in ('●', '*'):
            words = words[1:]
        if words:
            units.append(words[0])
    return units


def parse_conntrack_stats(text):
    """/proc/net/stat/nf_conntrack (hex, one row per CPU) -> summed integer counters.
    `entries` is global (same on every row) so it is taken once, not summed."""
    if isinstance(text, dict) or text is None:
        return text
    lines = [l.split() for l in text.splitlines() if l.strip()]
    if len(lines) < 2:
        return None
    header, totals = lines[0], {}
    for row in lines[1:]:
        for key, value in zip(header, row):
            try:
                number = int(value, 16)
            except ValueError:
                continue
            totals[key] = number if key == 'entries' else totals.get(key, 0) + number
    return totals


def parse_conntrack(values):
    """{'count': '123\\n', 'max': ..., 'acct': ...} -> integers."""
    result = {}
    for key, value in (values or {}).items():
        try:
            result[key] = int(str(value).strip())
        except ValueError:
            result[key] = None
    return result


def parse_virsh_list(text):
    if isinstance(text, list) or text is None:
        return text
    domains = []
    for line in text.splitlines():
        words = line.split()
        if len(words) < 3 or words[0] == 'Id' or set(line.strip()) <= {'-'}:
            continue
        domains.append({'id': None if words[0] == '-' else words[0], 'name': words[1], 'state': ' '.join(words[2:])})
    return domains


def parse_ps(text):
    if isinstance(text, list) or text is None:
        return text
    rows = []
    for line in text.splitlines():
        words = line.split(None, 2)
        if len(words) == 3 and words[0].isdigit() and words[1].isdigit():
            rows.append({'uid': int(words[0]), 'pid': int(words[1]), 'comm': words[2]})
    return rows


def firewall_rules(raw):
    """`nft -j list ruleset` -> rules with counters and fw4 comments. Rules that have
    neither a counter nor a comment carry no information and are dropped."""
    rules = []
    for item in (raw or {}).get('nftables', []):
        rule = item.get('rule')
        if not rule:
            continue
        counters = [x['counter'] for x in rule.get('expr', []) if isinstance(x, dict) and 'counter' in x]
        comment = rule.get('comment')
        if not counters and not comment:
            continue
        entry = {k: rule.get(k) for k in ('family', 'table', 'chain', 'handle')}
        entry['comment'] = comment
        entry['counters'] = counters
        rules.append(entry)
    return rules


def trim_links(links):
    return [{k: l[k] for k in LINK_FIELDS if k in l} for l in (links or []) if l.get('ifname') != 'lo']


def normalize_dns_event(event):
    event = dict(event)
    if event.get('event_time_epoch') is not None and not event.get('event_time'):
        event['event_time'] = iso(event.pop('event_time_epoch'))
    elif event.get('event_time'):
        event['event_time'] = iso_text(event['event_time']) or event['event_time']
    address, port = client_addr(event.get('client'))
    if port is not None or 'client_port' not in event:
        event['client_port'] = port
    event['client'] = address
    return event


def merge_dns_clients(clients):
    """Re-group 1.0 dns_minute client groups whose key included the source port."""
    merged = {}
    for group in clients or []:
        address, _ = client_addr(group.get('client'))
        key = (group.get('source'), address)
        target = merged.setdefault(key, {'source': key[0], 'client': address, 'internal': is_internal(address),
                                         'queries': 0, 'rcodes': {}, 'qtypes': {}, 'unique_domains': 0, 'length_max': 0})
        target['queries'] += group.get('queries', 0)
        for field in ('rcodes', 'qtypes'):
            for k, v in (group.get(field) or {}).items():
                target[field][k] = target[field].get(k, 0) + v
        # Unique names cannot be merged exactly from per-port sets; the maximum is a lower bound.
        target['unique_domains'] = max(target['unique_domains'], group.get('unique_domains', 0))
        target['length_max'] = max(target['length_max'], group.get('length_max', 0))
    return list(merged.values())


def upgrade(record):
    """Return a schema 1.1 copy of a 1.0 record. 1.1 records are returned unchanged."""
    if not isinstance(record, dict) or record.get('schema_version') != '1.0':
        return record
    r = dict(record)
    d = dict(r.get('data') or {})
    module = r.get('module')
    window = r.get('window')
    if isinstance(window, dict):
        r['window'] = {k: iso_text(v) or v for k, v in window.items()}
    if r.get('collected_at'):
        r['collected_at'] = iso_text(r['collected_at']) or r['collected_at']
    if module == 'system':
        if 'memory_bytes' in d:
            d['memory'] = select_memory(d.pop('memory_bytes'))
        if 'cpu_ticks' in d:
            d['cpu'] = parse_cpu(d.pop('cpu_ticks'))
        if isinstance(d.get('pressure'), dict):
            d['pressure'] = {k: parse_pressure(v) for k, v in d['pressure'].items()}
    elif module == 'services':
        d['systemd'] = parse_systemctl_show(d.get('systemd'))
        d['failed'] = parse_failed_units(d.get('failed'))
    elif module == 'firewall':
        d['rules'] = [dict(x, comment=x.get('comment')) for x in d.get('rules', []) if x.get('counters') or x.get('comment')]
        d['conntrack'] = parse_conntrack(d.get('conntrack'))
        d['conntrack_stats'] = parse_conntrack_stats(d.get('conntrack_stats'))
    elif module == 'network':
        d['links'] = trim_links(d.get('links'))
    elif module == 'virtualization':
        d['domains'] = parse_virsh_list(d.get('domains'))
        d['container_monitors'] = parse_ps(d.get('container_monitors'))
        if isinstance(d.get('libvirt_state'), str):
            d['libvirt_state'] = d['libvirt_state'].strip()
    elif module == 'identity':
        leases = []
        for lease in d.get('dhcp4') or []:
            lease = dict(lease)
            if 'expires_epoch' in lease:
                epoch = lease.pop('expires_epoch')
                lease['expires'] = iso(epoch) if str(epoch).isdigit() and int(epoch) > 0 else None
            leases.append(lease)
        d['dhcp4'] = leases
    elif module in ('events', 'incidents'):
        events = []
        for event in d.get('events', []):
            event = dict(event)
            if 'event_time_us' in event:
                event['event_time'] = iso_us(event.pop('event_time_us'))
            event.setdefault('detail', None)
            events.append(event)
        d['events'] = events
    elif module == 'changes':
        d['revisions'] = [dict(x, event_time=iso(x['event_time']) if isinstance(x.get('event_time'), (int, float)) else x.get('event_time'))
                          for x in d.get('revisions', [])]
    elif module == 'dns_queries':
        d['events'] = [normalize_dns_event(e) for e in d.get('events', [])]
    elif module == 'dns_minute':
        d['clients'] = merge_dns_clients(d.get('clients'))
    r['data'] = d
    r['schema_version'] = SCHEMA
    r['upgraded_from'] = '1.0'
    return r
