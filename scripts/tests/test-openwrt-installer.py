#!/usr/bin/env python3
"""Host acceptance for installer planning, actual GPT and UCI serialization."""
import copy
import importlib.machinery
import importlib.util
import itertools
import json
import os
import pty
import fcntl
import select
import struct
import sys
import termios
import time
from pathlib import Path
import shutil
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
loader = importlib.machinery.SourceFileLoader('installer_core', str(ROOT / 'package/custom/openwrt-installer/files/core.py'))
spec = importlib.util.spec_from_loader(loader.name, loader)
core = importlib.util.module_from_spec(spec); loader.exec_module(core)
HASH = '$6$salt$' + 'a' * 86


def answers():
    return {'disk': '/dev/nvme0n1', 'partitions': core.guided(730 * core.MIB),
            'network': {'wan_port': 'eth1', 'lan_ports': ['eth0', 'eth2'],
                        'lan': {'ipaddr': '192.168.1.1', 'netmask': '255.255.255.0', 'dhcp': True, 'start': 100, 'limit': 150},
                        'wan': {'proto': 'dhcp'}, 'ipv6': True},
            'firewall': {'masq': True, 'fullcone': False, 'lan_to_wan': True},
            'accounts': {'root_password_hash': HASH, 'user': {'name': 'alice', 'password_hash': HASH, 'gnome_autostart': True}}}


class Installer(unittest.TestCase):
    def test_layout(self):
        for fs in core.FILESYSTEMS:
            parts = core.guided(730 * core.MIB, fs)
            parts.append({'role': 'data', 'fs': 'unformatted', 'size_mib': 512})
            plan = core.layout(parts, 8 * 1024 * core.MIB, 730 * core.MIB)
            self.assertEqual(plan['disk_guid'][-2:], '00')
            self.assertEqual(plan['bios_uuid'][-2:], '80')
            self.assertEqual(plan['partitions'][1]['uuid'][-2:], '02')
            for p in plan['partitions']:
                self.assertEqual(p['start'] % 2048, 0)
            self.assertIn('128 : start=34, size=2014', core.sfdisk_script('/dev/nvme0n1', plan))
        self.assertEqual(core.partition('/dev/nvme0n1', 128), '/dev/nvme0n1p128')
        self.assertEqual(core.partition('/dev/sda', 3), '/dev/sda3')

    def test_invalid_layout(self):
        for index, size in ((0, 63), (1, 729), (2, 2047)):
            p = core.guided(730 * core.MIB); p[index]['size_mib'] = size
            with self.assertRaises(ValueError):
                core.layout(p, 8 * 1024 * core.MIB, 730 * core.MIB)
        with self.assertRaises(ValueError):
            core.layout(core.guided(730 * core.MIB), 2048 * core.MIB, 730 * core.MIB)
        p = core.guided(730 * core.MIB); p.append({'role': 'data', 'size_mib': None, 'fs': 'xfs'})
        with self.assertRaises(ValueError):
            core.layout(p, 8 * 1024 * core.MIB, 730 * core.MIB)

    @unittest.skipUnless(shutil.which('sfdisk'), 'host sfdisk absent')
    def test_real_gpt_128(self):
        with tempfile.TemporaryDirectory() as tmp:
            disk = Path(tmp) / 'disk.img'
            with disk.open('wb') as f:
                f.truncate(5 * 1024**3)
            plan = core.layout(core.guided(1), disk.stat().st_size, 1)
            subprocess.run(['sfdisk', str(disk)], input=core.sfdisk_script(str(disk), plan), text=True, check=True, capture_output=True)
            data = json.loads(subprocess.check_output(['sfdisk', '--json', str(disk)]))['partitiontable']
            self.assertEqual([p['node'].removeprefix(str(disk)) for p in data['partitions']], ['1', '2', '3', '128'])
            self.assertEqual(data['partitions'][-1]['start'], 34)

    def test_validation_and_redaction(self):
        a = answers(); self.assertEqual(core.validate_answers(a), a)
        for mutate in (lambda a: a['network']['lan'].update(start=200),
                       lambda a: a['network'].update(lan_ports=['eth1']),
                       lambda a: a['accounts']['user'].update(name='root'),
                       lambda a: a['accounts'].update(root_password_hash='plaintext')):
            a = answers(); mutate(a)
            with self.assertRaises(ValueError): core.validate_answers(a)
        a = answers(); a['network']['wan'] = {'proto': 'pppoe', 'username': 'name', 'password': 'secret'}
        self.assertNotIn('secret', core.summary(a)); self.assertNotIn(HASH, core.summary(a))
        plan = core.layout(a['partitions'], 8 * 1024 * core.MIB, 730 * core.MIB)
        display = core.display_summary(a, plan)
        self.assertNotIn('secret', display); self.assertNotIn(HASH, display)
        self.assertIn('192.168.1.1', display); self.assertIn('User: alice', display)
        self.assertIn(str(plan['partitions'][2]['size_mib']) + ' MiB ext4', display)
        with self.assertRaises(ValueError): core.validate_answers(a, ['alice'])

    def test_uci_matrix(self):
        uci = Path(os.environ.get('INSTALLER_TEST_UCI', str(ROOT / 'staging_dir/host/bin/uci')))
        dhcp = ROOT / 'package/network/services/dnsmasq/files/dhcp.conf'
        for proto, ipv6, masq, fullcone, forward in itertools.product(('dhcp', 'pppoe', 'static', 'none'), (True, False), (True, False), (True, False), (True, False)):
            a = answers(); a['network']['wan'] = {'proto': proto}; a['network']['ipv6'] = ipv6
            a['firewall'] = dict(masq=masq, fullcone=fullcone, lan_to_wan=forward)
            if proto == 'pppoe': a['network']['wan'].update(username="user'name", password="p'a ss")
            if proto == 'static': a['network']['wan'].update(ipaddr='10.0.2.20', netmask='255.255.255.0', gateway='10.0.2.2', dns=['1.1.1.1'])
            core.validate_answers(a)
            batch = core.network_batch(a, 'fd00:1234:5678::/48')
            self.assertEqual('network.wan6=' in batch, ipv6 and proto in ('dhcp', 'static'))
            if not uci.exists(): continue
            with tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp); (config / 'network').touch()
                (config / 'firewall').write_text("config defaults\n option input 'REJECT'\nconfig zone\n option name 'lan'\nconfig zone\n option name 'wan'\nconfig forwarding\n option src 'lan'\n option dest 'wan'\n"); shutil.copyfile(dhcp, config / 'dhcp')
                def run(*args, input=None):
                    return subprocess.run([str(uci), '-c', tmp, *args], input=input, text=True, capture_output=True, check=True).stdout
                run('batch', input=batch)
                policy = core.policy_batch(a, run('-X', 'show', 'firewall'))
                run('batch', input=policy)
                network = run('show', 'network'); firewall = run('show', 'firewall')
                self.assertIn("network.lan.ipaddr='192.168.1.1'", network)
                self.assertIn(".masq='" + str(int(masq)) + "'", firewall)
                self.assertIn(".fullcone='" + str(2 if masq and fullcone else 0) + "'", firewall)
                self.assertEqual(".src='lan'" in firewall, forward)
                if proto == 'pppoe': self.assertEqual(run('get', 'network.wan.password').strip(), "p'a ss")

    def test_ipv6_policy_survives_odhcpd_firstboot(self):
        uci = Path(os.environ.get('INSTALLER_TEST_UCI', str(ROOT / 'staging_dir/host/bin/uci')))
        if not uci.exists(): self.skipTest('host UCI absent')
        defaults = (ROOT / 'package/network/services/odhcpd/files/odhcpd.defaults').read_text()
        for ipv6, dhcp in itertools.product((False, True), repeat=2):
            with tempfile.TemporaryDirectory() as tmp:
                config = Path(tmp)
                shutil.copyfile(ROOT / 'package/network/services/dnsmasq/files/dhcp.conf', config / 'dhcp')
                (config / 'network').touch()
                (config / 'firewall').write_text("config defaults\nconfig zone\n option name 'wan'\n")
                def run(*args, input=None):
                    return subprocess.run([str(uci), '-c', tmp, *args], input=input, text=True, capture_output=True, check=True).stdout
                a = answers(); a['network']['ipv6'] = ipv6; a['network']['lan']['dhcp'] = dhcp
                run('batch', input=core.network_batch(a))
                run('batch', input=core.policy_batch(a, run('-X', 'show', 'firewall')))
                # Execute the real firstboot script with a static board and an isolated UCI directory.
                body = defaults.replace('. /usr/share/libubox/jshn.sh', '').replace('/etc/config/dhcp', str(config / 'dhcp'))
                prefix = 'uci() { ' + shlex.quote(str(uci)) + ' -c ' + shlex.quote(tmp) + ' "$@"; }\n'
                prefix += 'json_load() { :; }; json_select() { :; }; json_get_vars() { protocol=static; };\n'
                subprocess.run(['/bin/sh', '-c', prefix + 'firstboot() {\n' + body + '\n}\nfirstboot'], check=True, capture_output=True)
                expected = 'server' if ipv6 else 'disabled'
                self.assertEqual(run('get', 'dhcp.lan.ra').strip(), expected)
                self.assertEqual(run('get', 'dhcp.lan.dhcpv6').strip(), expected)
                self.assertEqual(run('get', 'dhcp.lan.ignore').strip(), str(int(not dhcp)))
                self.assertEqual(run('get', 'dhcp.odhcpd.maindhcp').strip(), '0')

    @unittest.skipUnless(shutil.which('whiptail'), 'host whiptail absent')
    def test_escape_and_cursor_keys(self):
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', 25, 80, 0, 0))
        code = """import sys
sys.path.insert(0, sys.argv[1])
import tui
print('SELECTED=' + tui.menu('Navigation probe', [('one', 'First'), ('two', 'Second')]), flush=True)
try:
    tui.menu('Escape probe', [('one', 'First')])
except tui.Back:
    print('ESCAPE_BACK_OK', flush=True)
assert tui.dialog('passwordbox', 'Whitespace probe') == ' spaced secret '
print('PASSWORD_SPACE_OK', flush=True)
"""
        process = subprocess.Popen([sys.executable, '-c', code, str(ROOT / 'package/custom/openwrt-installer/files')],
                                   stdin=slave, stdout=slave, stderr=slave,
                                   env=dict(os.environ, TERM='linux'))
        os.close(slave)
        data = b''; selected = escaped = password_sent = False
        deadline = time.monotonic() + 10
        try:
            while time.monotonic() < deadline:
                if not select.select([master], [], [], .1)[0]: continue
                try: chunk = os.read(master, 65536)
                except OSError: break
                data += chunk
                if not selected and b'Navigation probe' in data:
                    os.write(master, b'\x1b[B\r'); selected = True
                if not escaped and b'Escape probe' in data:
                    os.write(master, b'\x1b'); escaped = True
                if not password_sent and b'Whitespace probe' in data:
                    os.write(master, b' spaced secret \r'); password_sent = True
                if b'PASSWORD_SPACE_OK' in data: break
            self.assertIn(b'SELECTED=two', data)
            self.assertIn(b'ESCAPE_BACK_OK', data)
            self.assertIn(b'PASSWORD_SPACE_OK', data)
            self.assertEqual(process.wait(timeout=2), 0)
        finally:
            if process.poll() is None: process.kill(); process.wait()
            os.close(master)

    def test_grub(self):
        text = 'search -l kernel -s root\n' + '\n'.join('linux root=PARTUUID=old ' + x for x in ('normal', 'failsafe', 'procd'))
        result = core.rewrite_grub(text, 'PARTUUID=old', 'new', 'ABCD-1234')
        self.assertEqual(result.count('PARTUUID=new'), 3)
        self.assertIn('search --fs-uuid --set=root ABCD-1234', result)

    def test_discovery(self):
        data = {'blockdevices': [dict(name=n, path='/dev/'+n, type=t, ro=ro, size=8*1024**3) for n, t, ro in [('sda', 'disk', False), ('sdb', 'disk', False), ('sdc', 'disk', True), ('loop0', 'disk', False), ('sr0', 'rom', False)]]}
        data['blockdevices'].append(dict(name='nbd0', path='/dev/nbd0', type='disk', ro=False, size=0))
        self.assertEqual([d['name'] for d in core.disks(data, ['/dev/sda'])], ['sdb'])
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)
            for name in ('eth0', 'wlan0', 'lo'):
                d = p/name; d.mkdir(); (d/'address').write_text('aa:bb'); (d/'carrier').write_text('1')
                if name != 'lo': (d/'device').mkdir()
                if name == 'wlan0': (d/'wireless').mkdir()
            driver = p / 'e1000'; driver.mkdir()
            (p / 'eth0/device/driver').symlink_to(driver)
            interfaces = core.nics(tmp)
            self.assertEqual([n['name'] for n in interfaces], ['eth0'])
            self.assertEqual((interfaces[0]['mac'], interfaces[0]['carrier'], interfaces[0]['driver']), ('aa:bb', '1', 'e1000'))


if __name__ == '__main__':
    unittest.main()
