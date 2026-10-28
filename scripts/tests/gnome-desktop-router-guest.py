#!/usr/bin/env python3
"""Check DHCP, DNS and routed NAT inside a disposable Q35 GNOME guest.

Creates two guest network namespaces and a temporary netifd WAN interface.
The existing firewall configuration is restored in finally; no host network,
physical WAN, existing interface configuration or external server is used.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time

assert os.getuid() == 0
assert 'Q35' in Path('/sys/class/dmi/id/product_name').read_text(), 'Disposable Q35 guest required'
work = Path(tempfile.mkdtemp(prefix='gnome-router-test-'))
firewall = Path('/etc/config/firewall')
original = firewall.read_bytes()
dhcp_config = Path('/etc/config/dhcp')
original_dhcp = dhcp_config.read_bytes()
processes = []
created_namespaces = []
created_links = []
dynamic_created = []
firewall_changed = False
dhcp_changed = False
result = {}


def run(*args, check=True, data=None, timeout=30):
    p = subprocess.run(args, input=data, text=True, capture_output=True, timeout=timeout)
    if check and p.returncode:
        raise RuntimeError(f'{args[0:3]}: {p.stderr[-1200:]} {p.stdout[-400:]}')
    return p


def ns(name, *args, **kwargs):
    return run('ip', 'netns', 'exec', name, *args, **kwargs)


def start(name, *args):
    log = (work / (name + '.log')).open('w')
    p = subprocess.Popen(args, stdout=log, stderr=log)
    processes.append((p, log))
    return p


try:
    assert not run('uci', 'changes', 'firewall').stdout.strip(), 'Pending firewall edits exist'
    assert not run('uci', 'changes', 'dhcp').stdout.strip(), 'Pending DHCP edits exist'
    assert run('uci', '-q', 'get', 'dhcp.gnome_validation_record', check=False).returncode != 0
    for name in ['gnome_validation_lan', 'gnome_validation_wan']:
        assert not run('ubus', 'list', 'network.interface.' + name, check=False).stdout.strip()
    assert run('uci', '-q', 'get', 'dhcp.gnome_validation_pool', check=False).returncode != 0
    for name in ['gnome_validation_lan', 'gnome_validation_zone', 'gnome_validation_forward']:
        assert run('uci', '-q', 'get', 'firewall.' + name, check=False).returncode != 0
    for name in ['gnome-lan-test', 'gnome-wan-test']:
        assert not Path('/run/netns', name).exists(), 'Fixture already exists'
        run('ip', 'netns', 'add', name)
        created_namespaces.append(name)
        ns(name, 'ip', 'link', 'set', 'lo', 'up')
    for root, peer, namespace in [('gnvl0', 'gnvlp0', 'gnome-lan-test'),
                                   ('gnvw0', 'gnvwp0', 'gnome-wan-test')]:
        assert not Path('/sys/class/net', root).exists()
        run('ip', 'link', 'add', root, 'type', 'veth', 'peer', 'name', peer)
        created_links.append(root)
        run('ip', 'link', 'set', peer, 'netns', namespace)
        run('ip', 'link', 'set', root, 'up')
        ns(namespace, 'ip', 'link', 'set', peer, 'up')
    # A separate virtual LAN avoids the image overlay's client-specific DNS
    # policies and slirp's DHCP server on br-lan. Existing LAN/WAN stay intact.
    run('ubus', 'call', 'network', 'add_dynamic', json.dumps({
        'name': 'gnome_validation_lan', 'proto': 'static', 'device': 'gnvl0',
        'ipaddr': ['192.168.250.1/24']}))
    dynamic_created.append('gnome_validation_lan')
    dhcp_changed = True
    for value in ['gnome_validation_pool=dhcp',
                  'gnome_validation_pool.interface=gnome_validation_lan',
                  'gnome_validation_pool.dhcpv4=server',
                  'gnome_validation_pool.start=100', 'gnome_validation_pool.limit=10',
                  'gnome_validation_pool.leasetime=5m', 'gnome_validation_pool.force=1',
                  'gnome_validation_record=domain',
                  'gnome_validation_record.name=gnome-validation.test',
                  'gnome_validation_record.ip=192.168.250.1', '@dnsmasq[0].port=1053']:
        run('uci', 'set', 'dhcp.' + value)
    run('uci', 'commit', 'dhcp')
    firewall_changed = True
    for value in ['gnome_validation_lan=zone', 'gnome_validation_lan.name=gnomelan',
                  'gnome_validation_lan.network=gnome_validation_lan',
                  'gnome_validation_lan.input=ACCEPT', 'gnome_validation_lan.output=ACCEPT',
                  'gnome_validation_lan.forward=ACCEPT']:
        run('uci', 'set', 'firewall.' + value)
    run('uci', 'commit', 'firewall')
    run('fw4', 'reload')
    run('/etc/init.d/dnsmasq', 'reload')
    time.sleep(2)
    hook = work / 'dhcp-hook'
    hook.write_text('''#!/usr/bin/python3
import ipaddress,json,os,subprocess,sys
from pathlib import Path
if sys.argv[1] not in ['bound','renew']: raise SystemExit(0)
e=os.environ
prefix=ipaddress.IPv4Network('0.0.0.0/'+e['subnet']).prefixlen
subprocess.run(['ip','addr','replace',e['ip']+'/'+str(prefix),'dev',e['interface']],check=True)
subprocess.run(['ip','route','replace','default','via',e['router'].split()[0]],check=True)
Path(__file__).with_name('dhcp.json').write_text(json.dumps({k:e.get(k) for k in ['ip','subnet','router','serverid']}))
''')
    hook.chmod(0o700)
    ns('gnome-lan-test', 'udhcpc', '-f', '-q', '-n', '-t', '4', '-T', '2',
       '-i', 'gnvlp0', '-s', str(hook), timeout=20)
    result['lan_dhcp'] = json.loads((work / 'dhcp.json').read_text())
    assert result['lan_dhcp']['serverid'] == '192.168.250.1', result['lan_dhcp']
    # The preserved overlay redirects port 53 through its proxy DNS policy.
    # Exercise the actual procd dnsmasq backend on a temporary fixture port,
    # rather than changing those interception rules or querying the Internet.
    dns = ns('gnome-lan-test', 'python3', '-c', """import socket,struct
name=b''.join(bytes([len(x)])+x.encode() for x in 'gnome-validation.test'.split('.'))+b'\\0'
query=struct.pack('!6H',1234,256,1,0,0,0)+name+struct.pack('!HH',1,1)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);s.settimeout(5)
s.sendto(query,('192.168.250.1',1053));data,_=s.recvfrom(4096)
ident,flags,questions,answers,_,_=struct.unpack('!6H',data[:12])
assert ident==1234 and flags&15==0 and answers>0
assert socket.inet_aton('192.168.250.1') in data
print('192.168.250.1')
""")
    result['lan_dns_backend_port'] = 1053
    result['lan_dns'] = True
    ns('gnome-wan-test', 'ip', 'addr', 'add', '192.168.251.1/24', 'dev', 'gnvwp0')
    start('wan-dhcp', 'ip', 'netns', 'exec', 'gnome-wan-test', 'dnsmasq',
          '--keep-in-foreground', '--conf-file=/dev/null', '--port=0', '--no-resolv',
          '--no-hosts', '--bind-interfaces', '--interface=gnvwp0',
          '--dhcp-range=192.168.251.2,192.168.251.5,255.255.255.0,5m',
          '--dhcp-option=option:router,192.168.251.1',
          '--dhcp-leasefile=' + str(work / 'wan.leases'), '--pid-file=' + str(work / 'wan.pid'))
    server = work / 'http-server.py'
    server.write_text('''from http.server import BaseHTTPRequestHandler,HTTPServer
class Handler(BaseHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):
  self.send_response(200);self.end_headers();self.wfile.write(self.client_address[0].encode())
HTTPServer(('192.168.251.1',18080),Handler).serve_forever()
''')
    start('wan-http', 'ip', 'netns', 'exec', 'gnome-wan-test', 'python3', str(server))
    run('ubus', 'call', 'network', 'add_dynamic', json.dumps({
        'name': 'gnome_validation_wan', 'proto': 'dhcp', 'device': 'gnvw0',
        'peerdns': False, 'defaultroute': False}))
    dynamic_created.append('gnome_validation_wan')
    deadline = time.monotonic() + 25
    while True:
        p = run('ubus', 'call', 'network.interface.gnome_validation_wan', 'status')
        status = json.loads(p.stdout)
        if status.get('up') and status.get('ipv4-address'):
            break
        if time.monotonic() > deadline:
            raise RuntimeError('netifd test WAN did not acquire a DHCP lease')
        time.sleep(.25)
    result['wan_dhcp'] = status['ipv4-address']
    firewall_changed = True
    for value in ['gnome_validation_zone=zone',
                  'gnome_validation_zone.name=gnomeval',
                  'gnome_validation_zone.network=gnome_validation_wan',
                  'gnome_validation_zone.input=REJECT',
                  'gnome_validation_zone.output=ACCEPT',
                  'gnome_validation_zone.forward=REJECT',
                  'gnome_validation_zone.masq=1',
                  'gnome_validation_forward=forwarding',
                  'gnome_validation_forward.src=gnomelan',
                  'gnome_validation_forward.dest=gnomeval']:
        run('uci', 'set', 'firewall.' + value)
    run('uci', 'commit', 'firewall')
    run('fw4', 'check')
    run('fw4', 'reload')
    p = ns('gnome-lan-test', 'python3', '-c',
           "import urllib.request;print(urllib.request.urlopen('http://192.168.251.1:18080',timeout=5).read().decode())")
    observed = p.stdout.strip()
    assert observed == status['ipv4-address'][0]['address'], observed
    result['lan_to_wan_nat_source'] = observed
    run('systemctl', 'is-active', 'openwrt-procd.service', 'systemd-logind.service',
        'systemd-udevd.service', 'sshd.service')
    run('ubus', 'call', 'system', 'board')
    result['native_router_services'] = True
    print(json.dumps(result, indent=2))
finally:
    if dhcp_changed:
        dhcp_config.write_bytes(original_dhcp)
        run('uci', '-q', 'revert', 'dhcp', check=False)
        run('/etc/init.d/dnsmasq', 'reload', check=False)
    if firewall_changed:
        firewall.write_bytes(original)
        run('uci', '-q', 'revert', 'firewall', check=False)
        run('fw4', 'reload', check=False)
    for name in reversed(dynamic_created):
        run('ubus', 'call', 'network.interface.' + name, 'remove', check=False)
    for p, log in reversed(processes):
        p.terminate()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            p.kill();p.wait()
        log.close()
    for name in created_namespaces:
        run('ip', 'netns', 'delete', name, check=False)
    for name in created_links:
        run('ip', 'link', 'delete', name, check=False)
    shutil.rmtree(work)
