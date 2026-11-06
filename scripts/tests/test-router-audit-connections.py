#!/usr/bin/env python3
"""Source tests for router-audit connection collection: conntrack snapshot and daed connection events."""
import importlib.machinery
import importlib.util
import ipaddress
import json
import os
import pathlib
import socket
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch

sys.dont_write_bytecode = True
root = pathlib.Path(__file__).resolve().parents[2]
files = root / 'package/custom/router-audit/files'
loader = importlib.machinery.SourceFileLoader('router_audit_conn_test', str(files / 'router-audit'))
spec = importlib.util.spec_from_loader(loader.name, loader)
A = importlib.util.module_from_spec(spec)
loader.exec_module(A)

# Real /proc/net/nf_conntrack layout (accounting fields present, IPv6 fully expanded); addresses are
# documentation ranges. Router: LAN 192.0.2.1/24 + 2001:db8:2::1/64, WAN 203.0.113.7.
LINES = [
    'ipv4     2 tcp      6 431999 ESTABLISHED src=192.0.2.10 dst=93.184.216.34 sport=51000 dport=443 packets=10 bytes=900 '
    'src=93.184.216.34 dst=203.0.113.7 sport=443 dport=51000 packets=12 bytes=8000 [ASSURED] mark=0 zone=0 use=2',
    'ipv4     2 tcp      6 431999 ESTABLISHED src=192.0.2.10 dst=93.184.216.34 sport=51001 dport=443 packets=1 bytes=60 '
    'src=93.184.216.34 dst=203.0.113.7 sport=443 dport=51001 packets=1 bytes=60 [ASSURED] mark=0 zone=0 use=2',
    'ipv4     2 udp      17 25 src=192.0.2.11 dst=198.51.100.9 sport=4000 dport=3478 packets=1 bytes=100 [UNREPLIED] '
    'src=198.51.100.9 dst=203.0.113.7 sport=3478 dport=4000 packets=0 bytes=0 mark=0 zone=0 use=2',
    'ipv6     10 tcp      6 100 TIME_WAIT src=2001:0db8:0002:0000:0000:0000:0000:0010 dst=2001:0db8:00ff:0000:0000:0000:0000:0001 '
    'sport=40000 dport=443 packets=5 bytes=500 src=2001:0db8:00ff:0000:0000:0000:0000:0001 dst=2001:0db8:0002:0000:0000:0000:0000:0010 '
    'sport=443 dport=40000 packets=5 bytes=5000 [ASSURED] mark=0 zone=0 use=2',
    'ipv4     2 udp      17 20 src=192.0.2.10 dst=192.0.2.1 sport=5353 dport=53 packets=1 bytes=60 '
    'src=192.0.2.1 dst=192.0.2.10 sport=53 dport=5353 packets=1 bytes=90 mark=0 zone=0 use=2',
    'ipv4     2 tcp      6 300 ESTABLISHED src=198.51.100.50 dst=203.0.113.7 sport=60000 dport=8443 packets=3 bytes=200 '
    'src=192.0.2.20 dst=198.51.100.50 sport=443 dport=60000 packets=3 bytes=300 [ASSURED] mark=0 zone=0 use=2',
    'ipv4     2 tcp      6 300 ESTABLISHED src=203.0.113.7 dst=1.1.1.1 sport=41000 dport=443 packets=3 bytes=200 '
    'src=1.1.1.1 dst=203.0.113.7 sport=443 dport=41000 packets=3 bytes=300 [ASSURED] mark=0 zone=0 use=2',
    'ipv4     2 tcp      6 300 ESTABLISHED src=192.0.2.10 dst=192.0.2.30 sport=41000 dport=445 packets=3 bytes=200 '
    'src=192.0.2.30 dst=192.0.2.10 sport=445 dport=41000 packets=3 bytes=300 [ASSURED] mark=0 zone=0 use=2',
    'ipv4     2 udp      17 20 src=127.0.0.1 dst=127.0.0.1 sport=1 dport=2 packets=1 bytes=1 src=127.0.0.1 dst=127.0.0.1 sport=2 dport=1 packets=1 bytes=1 mark=0 zone=0 use=2',
    'ipv6     10 icmpv6   58 8 src=2001:0db8:0002:0000:0000:0000:0000:0010 dst=2001:0db8:00ff:0000:0000:0000:0000:0001 type=128 code=0 id=1 '
    'packets=1 bytes=64 src=2001:0db8:00ff:0000:0000:0000:0000:0001 dst=2001:0db8:0002:0000:0000:0000:0000:0010 type=129 code=0 id=1 packets=1 bytes=64 mark=0 zone=0 use=2',
    'garbage line',
]
SCOPES = ({ipaddress.ip_address(x) for x in ('192.0.2.1', '2001:db8:2::1', '203.0.113.7')},
          [ipaddress.ip_network('192.0.2.0/24'), ipaddress.ip_network('2001:db8:2::/64')])


class Conntrack(unittest.TestCase):
    def test_parse_line(self):
        e = A.parse_conntrack_line(LINES[0])
        self.assertEqual((e['family'], e['proto'], e['state'], e['flags']), ('ipv4', 'tcp', 'ESTABLISHED', ['ASSURED']))
        self.assertEqual((e['orig']['src'], e['orig']['dport'], e['reply']['dst'], e['reply']['bytes']), ('192.0.2.10', 443, '203.0.113.7', 8000))
        u = A.parse_conntrack_line(LINES[2])
        self.assertIsNone(u['state'])
        self.assertIn('UNREPLIED', u['flags'])
        v6 = A.parse_conntrack_line(LINES[3])
        self.assertEqual(v6['orig']['src'], '2001:db8:2::10', 'expanded IPv6 must be compressed')
        self.assertIsNone(A.parse_conntrack_line('garbage line'))
        self.assertIsNone(A.parse_conntrack_line('ipv4 2 tcp 6 1 ESTABLISHED src=not-an-ip dst=1.1.1.1 sport=1 dport=2'))

    def test_snapshot_groups_and_directions(self):
        result = A.connections('\n'.join(LINES), SCOPES)
        by = {(g['direction'], g['client'], g['dst'], g['dst_port']): g for g in result['groups']}
        laptop = by[('lan_out', '192.0.2.10', '93.184.216.34', 443)]
        self.assertEqual((laptop['entries'], laptop['assured'], laptop['bytes'], laptop['states']), (2, 2, 9020, {'ESTABLISHED': 2}))
        self.assertEqual(by[('lan_out', '192.0.2.11', '198.51.100.9', 3478)]['unreplied'], 1)
        self.assertIn(('lan_out', '2001:db8:2::10', '2001:db8:ff::1', 443), by)
        self.assertEqual(by[('inbound', '198.51.100.50', '203.0.113.7', 8443)]['dnat_to'], '192.0.2.20')
        self.assertIn(('router_out', '203.0.113.7', '1.1.1.1', 443), by)
        self.assertIn(('lan_local', '192.0.2.10', '192.0.2.30', 445), by)
        self.assertEqual(result['skipped'], {'dns_to_router': 1, 'loopback': 1, 'unparsed': 1})
        self.assertIsNone(by[('lan_out', '192.0.2.10', '93.184.216.34', 443)]['dnat_to'])
        self.assertFalse(result['truncated'])
        json.dumps(result)

    def test_limits(self):
        with patch.object(A, 'CONNTRACK_MAX_LINES', 3):
            self.assertTrue(A.connections('\n'.join(LINES), SCOPES)['truncated'])
        with patch.object(A, 'CONNTRACK_MAX_GROUPS', 1):
            result = A.connections('\n'.join(LINES), SCOPES)
            self.assertEqual(len(result['groups']), 1)
            self.assertTrue(result['truncated'])

    def test_module_registered(self):
        self.assertIn('connections', A.MODULES)
        self.assertIn('connections', A.capabilities()['implemented'])


EVENT = {'source': 'daed', 'source_epoch': '42-1', 'source_seq': 7, 'event_time': '2026-11-06T06:00:00.123+00:00', 'network': 'tcp',
         'client': '::ffff:192.0.2.10', 'client_port': 51000, 'mac': 'aa:00:00:00:00:10', 'dst': '93.184.216.34', 'dst_port': 443,
         'domain': 'example.com', 'dial_target': 'example.com:443', 'outbound': 'proxy', 'dialer': 'node-a', 'failed': False, 'producer_dropped': 0}


class ConnEvents(unittest.TestCase):
    def test_validation(self):
        e = A.conn_event(json.dumps(EVENT))
        self.assertEqual(e['client'], '192.0.2.10', 'IPv4-mapped addresses are reduced to IPv4')
        self.assertEqual(e['event_time'], '2026-11-06T06:00:00.123000Z')
        for bad in [dict(EVENT, source='dnsmasq'), dict(EVENT, network='icmp'), dict(EVENT, client='x'), dict(EVENT, dst_port='443'),
                    dict(EVENT, domain='a' * 301), dict(EVENT, failed='no')]:
            self.assertIsNone(A.conn_event(json.dumps(bad)), bad)
        self.assertNotIn('unexpected', A.conn_event(json.dumps(dict(EVENT, unexpected='x'))))
        self.assertNotIn('process', A.conn_event(json.dumps(dict(EVENT, process=''))))

    def test_flows(self):
        events = [A.conn_event(json.dumps(dict(EVENT, source_seq=i, client_port=50000 + i))) for i in range(3)]
        events.append(A.conn_event(json.dumps(dict(EVENT, network='udp', dst_port=443, domain='', dial_target='93.184.216.34:443'))))
        events.append(A.conn_event(json.dumps(dict(EVENT, failed=True, producer_dropped=4))))
        out = A.conn_flows(events)
        self.assertEqual(out['events'], 5)
        counts = sorted((f['network'], f['failed'], f['count']) for f in out['flows'])
        self.assertEqual(counts, [('tcp', False, 3), ('tcp', True, 1), ('udp', False, 1)])
        self.assertEqual(out['producer_dropped'], {'42-1': 4})
        self.assertNotIn('domain', next(f for f in out['flows'] if f['network'] == 'udp'))

    def test_receiver_checks_credentials(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, 'conn.sock')
            A.CONN_QUEUE.clear()
            stranger = {os.getuid() + 1}
            with patch.object(A, 'CONN_SOCK', path), patch.object(A, 'CONN_UIDS', stranger):
                threading.Thread(target=A.conn_receive, daemon=True).start()
                for _ in range(200):
                    if os.path.exists(path):
                        break
                    time.sleep(0.01)
                with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as s:
                    s.sendto(json.dumps(dict(EVENT, source_seq=1)).encode(), path)  # sender uid not allowed
                    time.sleep(0.2)
                    self.assertEqual(len(A.CONN_QUEUE), 0, 'datagrams from other UIDs are ignored')
                    A.CONN_UIDS = {os.getuid()}
                    s.sendto(json.dumps(EVENT).encode(), path)
                    s.sendto(b'not json', path)
                    s.sendto(json.dumps(dict(EVENT, source='other')).encode(), path)
                for _ in range(200):
                    if A.CONN_QUEUE:
                        break
                    time.sleep(0.01)
                time.sleep(0.1)
                self.assertEqual([e['source_seq'] for e in A.CONN_QUEUE], [7])
            A.CONN_QUEUE.clear()

    def test_production_uid_is_root_only(self):
        self.assertEqual(A.CONN_UIDS, {0})


if __name__ == '__main__':
    unittest.main()
