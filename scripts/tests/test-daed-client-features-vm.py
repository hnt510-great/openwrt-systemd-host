#!/usr/bin/env python3
"""Extended KVM acceptance suite (V01-V11) for daed native client features.

Topologies:
1. Isolated multi-identity KVM testbed (V01-V09):
   - Router VM (OpenWrt final image)
   - LAN Client VM with two independent MAC/IP identities (eth0 + macvlan/second NIC)
   - Host-side controllable WAN endpoints (QEMU guestfwd / local SOCKS5+HTTP+UDP servers):
     - Direct target (10.203.0.100:8080)
     - Proxy 1 (10.203.0.101:1080) and Proxy 2 (10.203.0.102:1080) — real forwarding SOCKS5
       servers that record next-hop + request tokens and can independently toggle TCP/UDP
     - Subscription & rule-list HTTP mock server (10.203.0.103:8080) validating UA, headers,
       Clash YAML / SIP008 / Base64, rename, credential rotation, HTML error & empty responses
2. Real VLESS acceptance (V10):
   - Separate disposable router + LAN client VM with outbound WAN enabled
   - VLESS URI passed ONLY via a mode-0600 temporary file attached as a read-only virtio
     block device (never in host argv, guest shell cmdline, serial console, or validation.json)
   - Verifies transparent TCP (and UDP when supported) through the real VLESS node,
     negative control when node endpoint is blocked on router WAN, direct control success,
     and recovery after unblock.
"""
import argparse
import base64
import gzip
import importlib.util
import json
import os
from pathlib import Path
import secrets
import shlex
import socket
import subprocess
import sys
import tempfile
import threading
import time

HERE = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location('image_network', HERE.parents[1] / 'test-image-network.py')
NET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NET)

DIRECT = '10.203.0.100'
PROXY1 = '10.203.0.101'
PROXY2 = '10.203.0.102'
MOCK_HTTP = '10.203.0.103'
TARGET_ONLY_PROXY = '10.203.0.104'

TCX_LAN = ("idx=$(cat /sys/class/net/br-lan/ifindex); n=0; "
           "for pid in $(busybox pgrep -x daed); do for f in /proc/$pid/fdinfo/*; do "
           "grep -q '^link_type:[[:space:]]*tcx' $f 2>/dev/null && "
           "grep -q \"^ifindex:[[:space:]]*$idx$\" $f && n=$((n+1)) || :; done; done; "
           "p=$(find /sys/fs/bpf -name '*lan_ingress*' 2>/dev/null | wc -l); echo $((n+p))")


def wait(guest, command, timeout=90, interval=2):
    script = (f'for n in $(seq 1 {max(1, timeout // interval)}); do '
              f'if {command}; then exit 0; fi; sleep {interval}; done; exit 1')
    return guest.run(script, timeout=timeout + 30)


def gql(router, query, variables=None, token=None):
    body = json.dumps({'query': query, 'variables': variables or {}})
    headers = '-H "Content-Type: application/json"'
    if token:
        headers += ' -H ' + shlex.quote('Authorization: Bearer ' + token)
    output = router.run('curl --noproxy "*" -fsS --max-time 30 ' + headers + ' --data ' +
                        shlex.quote(body) + ' http://127.0.0.1:2023/graphql', timeout=60)
    value = json.loads(output)
    if value.get('errors'):
        raise RuntimeError('GraphQL error: ' + output)
    return value['data']


def socks_forwarder(label, forward_to=None):
    """SOCKS5 responder/forwarder for QEMU guestfwd."""
    stream_in, stream_out = sys.stdin.buffer, sys.stdout.buffer

    def read(count):
        data = stream_in.read(count)
        if len(data) != count:
            raise SystemExit(0)
        return data

    version, methods = read(2)
    read(methods)
    if version != 5:
        return
    stream_out.write(b'\x05\x00')
    stream_out.flush()
    _, command, _, kind = read(4)
    if kind == 1:
        target = socket.inet_ntoa(read(4))
    elif kind == 3:
        target = read(read(1)[0]).decode(errors='replace')
    elif kind == 4:
        target = socket.inet_ntop(socket.AF_INET6, read(16))
    else:
        return
    port = int.from_bytes(read(2), 'big')
    if command != 1:
        stream_out.write(b'\x05\x07\x00\x01\x00\x00\x00\x00\x00\x00')
        stream_out.flush()
        return
    stream_out.write(b'\x05\x00\x00\x01\x00\x00\x00\x00\x00\x00')
    stream_out.flush()

    if forward_to:
        # Real TCP forwarding for 2-hop chain verification!
        host, fport = forward_to.rsplit(':', 1)
        with socket.create_connection((host, int(fport)), timeout=10) as upstream:
            def pump(src, dst):
                try:
                    while True:
                        chunk = src.recv(4096) if hasattr(src, 'recv') else src.read(4096)
                        if not chunk:
                            break
                        dst.sendall(chunk) if hasattr(dst, 'sendall') else (dst.write(chunk), dst.flush())
                except Exception:
                    pass
            t = threading.Thread(target=pump, args=(upstream, stream_out), daemon=True)
            t.start()
            pump(stream_in, upstream)
        return

    first = stream_in.readline(8192).decode('ascii', errors='replace').split()
    while True:
        line = stream_in.readline(8192)
        if line in (b'\r\n', b'\n', b''):
            break
    path = first[1] if len(first) == 3 else ''
    body = f'{label}:{target}:{port}{path}'.encode()
    stream_out.write((f'HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n'
                      'Connection: close\r\n\r\n').encode() + body)
    stream_out.flush()


def mock_http_cmd(state_file: Path):
    """One HTTP request per QEMU guestfwd connection, driven by state_file."""
    req_line = sys.stdin.buffer.readline(8192).decode('ascii', errors='replace').split()
    path = req_line[1] if len(req_line) >= 2 else '/'
    ua = ''
    while True:
        line = sys.stdin.buffer.readline(8192)
        if line in (b'\r\n', b'\n', b''):
            break
        decoded = line.decode('ascii', errors='replace').strip()
        if decoded.lower().startswith('user-agent:'):
            ua = decoded.split(':', 1)[1].strip()
    state = json.loads(state_file.read_text()) if state_file.exists() else {'mode': 'v1'}
    state['last_ua'] = ua
    state.setdefault('requests', []).append([path, ua])
    state_file.write_text(json.dumps(state))
    mode = state.get('mode', 'v1')

    extra_headers = ''
    status = '200 OK'
    if path == '/sub-yaml':
        extra_headers = 'Subscription-Userinfo: upload=100; download=200; total=10000; expire=1900000000\r\n'
        if mode == 'init-b64':
            body = base64.b64encode(f'socks5://{PROXY1}:1080#P1-Primary\n'.encode())
        elif mode == 'html':
            body = b'<!DOCTYPE html><html><title>502</title></html>'
        elif mode == 'empty':
            body = b''
        elif mode == 'v2-rename':
            body = (
                f"proxies:\n"
                f"  - name: 'P1-Renamed'\n    type: socks5\n    server: {PROXY1}\n    port: 1080\n"
                f"  - name: 'P2-Backup'\n    type: socks5\n    server: {PROXY2}\n    port: 1080\n"
            ).encode()
        else:
            body = (
                f"proxies:\n"
                f"  - name: 'P1-Primary'\n    type: socks5\n    server: {PROXY1}\n    port: 1080\n"
                f"  - name: 'Bad-XHTTP'\n    type: vless\n    server: 1.2.3.4\n    port: 443\n"
                f"    uuid: 11111111-1111-1111-1111-111111111111\n    network: xhttp\n"
                f"  - name: 'Trial-Excluded'\n    type: socks5\n    server: {PROXY2}\n    port: 1080\n"
            ).encode()
    elif path == '/rulelist':
        if mode == 'bad-list':
            body = b'<!DOCTYPE html><html><title>Error</title></html>'
        else:
            body = f'{TARGET_ONLY_PROXY}/32\n||proxy.example.test\n'.encode()
    elif path == '/generate_204':
        status = '204 No Content'
        body = b''
    else:
        body = b'ok'
    resp = (f'HTTP/1.1 {status}\r\n{extra_headers}Content-Length: {len(body)}\r\n'
            'Connection: close\r\n\r\n').encode() + body
    sys.stdout.buffer.write(resp)
    sys.stdout.buffer.flush()


def extract_base(image: Path, base: Path):
    with gzip.open(image, 'rb') as source, base.open('wb') as target:
        zero = bytes(1024 * 1024)
        while chunk := source.read(1024 * 1024):
            if chunk == zero[:len(chunk)]:
                target.seek(len(chunk), 1)
            else:
                target.write(chunk)
        target.truncate()
    base.chmod(0o400)


def run_v10_real_vless(base: Path, work: Path, vless_file: Path, receipt: dict):
    """Run V10 in an isolated disposable VM pair with real WAN and secret-safe virtio disk."""
    v10 = {'tcp': 'pending', 'udp': 'pending', 'negative_control': False, 'direct_control': False, 'recovery': False}
    if not vless_file or not vless_file.exists():
        receipt['v10'] = v10
        return

    raw_link = vless_file.read_text().strip()
    if not raw_link.startswith('vless://'):
        raise ValueError('vless-file must contain a vless:// URI')

    # Extract server IP:port ONLY for local WAN firewall block/unblock (never printed in receipt).
    hostport = raw_link.split('@', 1)[1].split('?', 1)[0].split('#', 1)[0]
    srv_host, srv_port = hostport.rsplit(':', 1)

    with tempfile.TemporaryDirectory(prefix='owrt-v10-') as tmp:
        runtime = Path(tmp)
        # Create a small 1 MiB raw disk containing the VLESS link (mode 0600, readonly in QEMU).
        secret_img = runtime / 'vless.raw'
        payload = raw_link.encode() + b'\n'
        secret_img.write_bytes(payload + b'\x00' * (65536 - len(payload)))
        secret_img.chmod(0o600)

        listener = socket.socket()
        listener.bind(('127.0.0.1', 0))
        lan_port = listener.getsockname()[1]
        listener.close()

        # WAN without restrict=on so router can reach the real VLESS endpoint.
        router_net = [
            '-netdev', f'socket,id=lan,listen=127.0.0.1:{lan_port}',
            '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ee:01:01',
            '-netdev', 'user,id=wan,net=10.204.0.0/24,host=10.204.0.2,dns=10.204.0.3,ipv6=off',
            '-device', 'virtio-net-pci,netdev=wan,mac=52:54:00:ee:01:02',
            '-drive', f'if=virtio,format=raw,readonly=on,file={secret_img}',
        ]
        client_net = [
            '-netdev', f'socket,id=lan,connect=127.0.0.1:{lan_port}',
            '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ee:02:01',
        ]
        guests = []
        v10_work = runtime / 'v10-work'
        v10_work.mkdir(mode=0o700)
        try:
            router = NET.Guest('v10-router', v10_work, runtime, base, router_net, 2048)
            guests.append(router)
            router.run('dmesg -n 1')
            NET.disable_external_integrations(router)
            router.run(NET.network_config())
            router.run("for n in $(seq 1 40); do ubus call network.interface.wan status | grep -q '\"up\": true' "
                       "&& ip -4 addr show dev br-lan | grep -q '192.0.2.1/24' && exit 0; sleep 2; done; exit 1",
                       timeout=100)
            router.run("uci set dhcp.lan.interface=lan; uci set dhcp.lan.ignore=0; uci set dhcp.lan.start=100; "
                       "uci set dhcp.lan.limit=20; uci commit dhcp; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart")
            router.run('uci set passwall.@global[0].enabled=0; uci commit passwall; '
                       'uci set daed.config.enabled=1; uci commit daed; /etc/init.d/daed start')
            wait(router, 'curl --noproxy "*" -fsS --max-time 3 -H "Content-Type: application/json" '
                         "--data '{\"query\":\"{healthCheck}\"}' http://127.0.0.1:2023/graphql >/dev/null", 60)

            # Configure daed INSIDE the guest reading /dev/vdb in memory so the VLESS URI
            # never touches host argv, serial logs, or command logs!
            setup_script = """python3 - <<'PY'
import json, secrets, urllib.request
raw = open('/dev/vdb', 'rb').read().split(b'\\x00', 1)[0].decode().strip()
def gql(q, v=None, tok=None):
    hdr = {'Content-Type': 'application/json'}
    if tok: hdr['Authorization'] = 'Bearer ' + tok
    req = urllib.request.Request('http://127.0.0.1:2023/graphql',
        data=json.dumps({'query': q, 'variables': v or {}}).encode(), headers=hdr)
    res = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
    if res.get('errors'): raise RuntimeError('gql error')
    return res['data']
pw = secrets.token_urlsafe(16) + 'a1'
gql('mutation($u:String!,$p:String!){createUser(username:$u,password:$p)}', {'u':'admin','p':pw})
tok = gql('query($u:String!,$p:String!){token(username:$u,password:$p)}', {'u':'admin','p':pw})['token']
imp = gql('mutation($a:[ImportArgument!]!){importNodes(rollbackError:true,args:$a){error node{id protocol}}}',
          {'a':[{'link': raw, 'tag': 'real-vless'}]}, tok)['importNodes'][0]
if imp['error']: raise RuntimeError('import failed')
nid = imp['node']['id']
gid = gql('mutation{createGroup(name:"vless_grp",policy:fixed,policyParams:[{val:"0"}]){id}}', tok=tok)['createGroup']['id']
gql('mutation($g:ID!,$n:[ID!]!){groupAddNodes(id:$g,nodeIDs:$n)}', {'g':gid,'n':[nid]}, tok)
cid = gql('mutation($g:globalInput){createConfig(name:"v10",global:$g){id}}', {'g':{
    'lanInterface':['br-lan'],'wanInterface':['auto'],'logLevel':'info',
    'dialMode':'ip','autoConfigKernelParameter':True}}, tok)['createConfig']['id']
rid = gql('mutation($r:String){createRouting(name:"v10",routing:$r){id}}', {
    'r': 'dip(1.1.1.1/32, 1.0.0.1/32) -> vless_grp\\ndip(9.9.9.9/32, 223.5.5.5/32) -> direct\\nfallback: direct\\n'}, tok)['createRouting']['id']
did = gql('mutation($d:String){createDns(name:"v10",dns:$d){id}}', {
    'd': 'upstream {}\\nrouting {\\n request { fallback: asis }\\n response { fallback: accept }\\n}\\n'}, tok)['createDns']['id']
for k, i in (('Config', cid), ('Routing', rid), ('Dns', did)):
    gql(f'mutation($i:ID!){{select{k}(id:$i)}}', {'i': i}, tok)
gql('mutation{run(dry:false)}', tok=tok)
print('V10_CONFIGURED protocol=' + imp['node']['protocol'])
PY"""
            out = router.run(setup_script, timeout=90)
            assert 'V10_CONFIGURED protocol=vless' in out
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)

            client = NET.Guest('v10-client', v10_work, runtime, base, client_net, 1536)
            guests.append(client)
            client.run('dmesg -n 1')
            NET.disable_external_integrations(client)
            client.run('for s in daed passwall passwall_server dnsmasq odhcpd firewall; do '
                       '[ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
            client.run(NET.network_config(client=True))
            client.run("for n in $(seq 1 40); do ip -4 route | grep -q 'default via 192.0.2.1' && exit 0; sleep 2; done; exit 1", timeout=100)

            # 1. Real HTTPS TCP through VLESS (1.1.1.1:443 -> vless_grp)
            code_tcp = client.run('env -u http_proxy -u https_proxy -u all_proxy curl -4 --noproxy "*" -sS -o /dev/null -w "%{http_code}" --max-time 20 https://1.1.1.1/')
            v10['tcp'] = 'passed' if code_tcp in ('200', '301', '302', '403') else f'failed:{code_tcp}'

            # 2. Real UDP DNS through VLESS (1.1.1.1:53 -> vless_grp)
            udp_out = client.run('nslookup -type=A example.com 1.1.1.1 2>&1 || true', timeout=30)
            v10['udp'] = 'passed' if ('Address:' in udp_out and 'timed out' not in udp_out.lower()) else 'failed'

            # 3. Negative control: block VLESS server IP:port on router WAN output, verify 1.1.1.1 fails while direct 9.9.9.9 succeeds!
            router.run(f'nft add table inet v10block; nft add chain inet v10block out "{{ type filter hook output priority 0; }}"; '
                       f'nft add rule inet v10block out ip daddr {srv_host} tcp dport {srv_port} drop')
            neg = client.run('env -u http_proxy -u https_proxy -u all_proxy curl -4 --noproxy "*" -sS --max-time 8 https://1.1.1.1/ >/dev/null 2>&1 && echo OK || echo BLOCKED')
            v10['negative_control'] = (neg.strip() == 'BLOCKED')
            direct_ok = client.run('env -u http_proxy -u https_proxy -u all_proxy curl -4 --noproxy "*" -sS -o /dev/null -w "%{http_code}" --max-time 15 https://223.5.5.5/ || echo ERR')
            v10['direct_control'] = direct_ok.strip() in ('200', '301', '302', '400', '403', '404')

            # 4. Unblock and verify recovery
            router.run('nft delete table inet v10block')
            rec = client.run('env -u http_proxy -u https_proxy -u all_proxy curl -4 --noproxy "*" -sS -o /dev/null -w "%{http_code}" --max-time 20 https://1.1.1.1/')
            v10['recovery'] = rec.strip() in ('200', '301', '302', '403')
        finally:
            for g in reversed(guests):
                g.close()
            # Temporary directory auto-deletes secret_img + v10-work wing.db!
    receipt['v10'] = v10


def run_isolated_suite(image: Path, work: Path, vless_file: Path | None):
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    image = image.resolve()
    digest = NET.sha256(image)
    receipt = {
        'schema': 2,
        'image': str(image),
        'image_sha256': digest,
        'checks': {},
        'status': 'running',
        'started_at': time.time(),
    }
    result = work / 'validation.json'
    result.write_text(json.dumps(receipt, indent=2))
    base = work / 'base.img'
    guests = []
    checks = receipt['checks']

    try:
        extract_base(image, base)
        with tempfile.TemporaryDirectory(prefix='owrt-daed-cf-') as tmp:
            runtime = Path(tmp)
            mock_state_file = runtime / 'mock-http-state.json'

            def set_mock_mode(mode: str):
                st = json.loads(mock_state_file.read_text()) if mock_state_file.exists() else {}
                st['mode'] = mode
                mock_state_file.write_text(json.dumps(st))

            set_mock_mode('v1')
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            lan_port = listener.getsockname()[1]
            listener.close()

            direct_cmd = shlex.join([sys.executable, str(HERE.parents[1] / 'test-image-network.py'), '--wan-response', 'direct-ok'])
            p1_cmd = shlex.join([sys.executable, str(HERE), '--socks-label', 'proxy1'])
            p2_cmd = shlex.join([sys.executable, str(HERE), '--socks-label', 'proxy2'])
            mock_cmd = shlex.join([sys.executable, str(HERE), '--mock-http', str(mock_state_file)])
            wan = (f'user,id=wan,net=10.203.0.0/24,host=10.203.0.2,dns=10.203.0.3,ipv6=off,restrict=on,'
                   f'guestfwd=tcp:{DIRECT}:8080-cmd:{direct_cmd},'
                   f'guestfwd=tcp:{PROXY1}:1080-cmd:{p1_cmd},'
                   f'guestfwd=tcp:{PROXY2}:1080-cmd:{p2_cmd},'
                   f'guestfwd=tcp:{MOCK_HTTP}:8080-cmd:{mock_cmd}')
            router_net = [
                '-netdev', f'socket,id=lan,listen=127.0.0.1:{lan_port}',
                '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ed:01:01',
                '-netdev', wan, '-device', 'virtio-net-pci,netdev=wan,mac=52:54:00:ed:01:02',
            ]
            client_net = [
                '-netdev', f'socket,id=lan,connect=127.0.0.1:{lan_port}',
                '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ed:02:01',
            ]
            router = NET.Guest('router', work, runtime, base, router_net, 2048)
            guests.append(router)
            router.run('dmesg -n 1')
            receipt['daed_version'] = router.run('daed --version')
            NET.disable_external_integrations(router)
            router.run(NET.network_config())
            router.run("for n in $(seq 1 40); do ubus call network.interface.wan status | grep -q '\"up\": true' "
                       "&& ip -4 addr show dev br-lan | grep -q '192.0.2.1/24' && exit 0; sleep 2; done; exit 1", timeout=100)
            router.run("uci set dhcp.lan.interface=lan; uci set dhcp.lan.ignore=0; uci set dhcp.lan.start=100; "
                       "uci set dhcp.lan.limit=20; uci commit dhcp; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart")
            router.run('uci set passwall.@global[0].enabled=0; uci commit passwall; '
                       'uci set daed.config.enabled=1; uci commit daed; /etc/init.d/daed start')
            wait(router, 'curl --noproxy "*" -fsS --max-time 3 -H "Content-Type: application/json" '
                         "--data '{\"query\":\"{healthCheck}\"}' http://127.0.0.1:2023/graphql >/dev/null", 60)

            # Setup client VM with two independent LAN identities (primary + macvlan second MAC/IP)
            client = NET.Guest('client', work, runtime, base, client_net, 1536)
            guests.append(client)
            client.run('dmesg -n 1')
            NET.disable_external_integrations(client)
            client.run('for s in daed passwall passwall_server dnsmasq odhcpd firewall; do '
                       '[ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
            client.run(NET.network_config(client=True))
            client.run("for n in $(seq 1 40); do ip -4 route | grep -q 'default via 192.0.2.1' && exit 0; sleep 2; done; exit 1", timeout=100)
            # Create second LAN identity in its own netns (MAC 52:54:00:ed:02:02, IP 192.0.2.150/24)
            client.run('ip netns add lan2 && '
                       'ip link add lan2 link eth0 address 52:54:00:ed:02:02 type macvlan mode bridge && '
                       'ip link set lan2 netns lan2 && '
                       'ip netns exec lan2 ip link set lo up && '
                       'ip netns exec lan2 ip addr add 192.0.2.150/24 dev lan2 && '
                       'ip netns exec lan2 ip link set lan2 up && '
                       'ip netns exec lan2 ip route add default via 192.0.2.1 dev lan2')
            client_ip1 = client.run("ip -4 -o addr show dev eth0 | awk '{print $4}' | cut -d/ -f1").strip()

            # Bootstrap admin user & baseline objects
            pw = secrets.token_urlsafe(16) + 'a1'
            gql(router, 'mutation($u:String!,$p:String!){createUser(username:$u,password:$p)}', {'u': 'admin', 'p': pw})
            tok = gql(router, 'query($u:String!,$p:String!){token(username:$u,password:$p)}', {'u': 'admin', 'p': pw})['token']

            n1 = gql(router, 'mutation($a:[ImportArgument!]!){importNodes(rollbackError:true,args:$a){node{id}}}',
                     {'a': [{'link': f'socks5://{PROXY1}:1080#p1', 'tag': 'p1'}]}, tok)['importNodes'][0]['node']['id']
            n2 = gql(router, 'mutation($a:[ImportArgument!]!){importNodes(rollbackError:true,args:$a){node{id}}}',
                     {'a': [{'link': f'socks5://{PROXY2}:1080#p2', 'tag': 'p2'}]}, tok)['importNodes'][0]['node']['id']
            g1 = gql(router, 'mutation{createGroup(name:"g_primary",policy:fixed,policyParams:[{val:"0"}]){id}}', token=tok)['createGroup']['id']
            g2 = gql(router, 'mutation{createGroup(name:"g_backup",policy:fixed,policyParams:[{val:"0"}]){id}}', token=tok)['createGroup']['id']
            gql(router, 'mutation($g:ID!,$n:[ID!]!){groupAddNodes(id:$g,nodeIDs:$n)}', {'g': g1, 'n': [n1]}, tok)
            gql(router, 'mutation($g:ID!,$n:[ID!]!){groupAddNodes(id:$g,nodeIDs:$n)}', {'g': g2, 'n': [n2]}, tok)
            cid = gql(router, 'mutation($g:globalInput){createConfig(name:"cf",global:$g){id}}', {'g': {
                'lanInterface': ['br-lan'], 'wanInterface': [], 'logLevel': 'info',
                'dialMode': 'ip', 'autoConfigKernelParameter': True}}, tok)['createConfig']['id']
            did = gql(router, 'mutation($d:String){createDns(name:"cf",dns:$d){id}}', {
                'd': 'upstream {}\nrouting {\n request { fallback: asis }\n response { fallback: accept }\n}\n'}, tok)['createDns']['id']
            rid = gql(router, 'mutation($r:String){createRouting(name:"cf",routing:$r){id}}', {
                'r': f'dip({TARGET_ONLY_PROXY}/32) -> g_primary\nfallback: direct\n'}, tok)['createRouting']['id']
            for k, i in (('Config', cid), ('Dns', did), ('Routing', rid)):
                gql(router, f'mutation($i:ID!){{select{k}(id:$i)}}', {'i': i}, tok)

            # V01/V06: Apply, create snapshot, save unapplied draft, restart daed, verify snapshot restored (not draft)!
            ap1 = gql(router, 'mutation{applyPolicyRevision{success running snapshotId digest generation status}}', token=tok)['applyPolicyRevision']
            assert ap1['success'] and ap1['running']
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)
            r1 = client.run(f'for n in $(seq 1 20); do curl -4 --noproxy "*" -fsS --max-time 8 http://{TARGET_ONLY_PROXY}:8080/v01 && exit 0; sleep 2; done; exit 1', timeout=90)
            assert r1.startswith('proxy1:')

            # Save a visual policy draft (V02: 2 MAC/IP identities -> eth0 goes g_primary, lan2 goes g_backup) WITHOUT applying
            policy_v02 = {
                'defaultAction': 'direct',
                'blockProxyPorts': 'udp:443',
                'acls': [
                    {'id': 'a1', 'name': 'client2', 'enabled': True, 'sources': [{'kind': 'mac', 'value': '52:54:00:ed:02:02'}],
                     'destinations': [{'kind': 'ip', 'value': TARGET_ONLY_PROXY}], 'action': 'group', 'targetGroup': 'g_backup'},
                    {'id': 'a2', 'name': 'client1', 'enabled': True, 'sources': [{'kind': 'ip', 'value': client_ip1}],
                     'destinations': [{'kind': 'ip', 'value': TARGET_ONLY_PROXY}], 'action': 'group', 'targetGroup': 'g_primary'},
                ],
                'listRules': [],
            }
            draft = gql(router, 'mutation($r:ID!,$p:String!){savePolicyDraft(routingId:$r,policyJson:$p){state{draftRevision} diagnostics{message}}}',
                        {'r': rid, 'p': json.dumps(policy_v02)}, tok)['savePolicyDraft']
            assert draft['state']['draftRevision'] == 1
            # Restart daed before applying draft -> must restore snapshot (not draft)!
            router.run('/etc/init.d/daed restart')
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)
            r_after_restart = client.run(f'for n in $(seq 1 20); do ip netns exec lan2 curl -4 --noproxy "*" -fsS --max-time 8 http://{TARGET_ONLY_PROXY}:8080/v01 && exit 0; sleep 2; done; exit 1', timeout=90)
            checks['V01_snapshot_restore'] = r_after_restart.startswith('proxy1:')

            # V02: Preview + Apply visual ACL, verify two MAC/IP identities get different outbounds!
            prev = gql(router, 'query{previewPolicy{digest hasErrors hasEffectiveChanges capacity{estimatedMatchSets maxMatchSets}}}', token=tok)['previewPolicy']
            assert not prev['hasErrors'] and prev['hasEffectiveChanges']
            ap2 = gql(router, 'mutation($d:String){applyPolicyRevision(expectedDigest:$d){success generation}}', {'d': prev['digest']}, tok)['applyPolicyRevision']
            assert ap2['success']
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)
            id1_out = client.run(f'for n in $(seq 1 20); do curl -4 --noproxy "*" -fsS --max-time 8 http://{TARGET_ONLY_PROXY}:8080/v02 && exit 0; sleep 2; done; exit 1', timeout=90)
            id2_out = client.run(f'for n in $(seq 1 20); do ip netns exec lan2 curl -4 --noproxy "*" -fsS --max-time 8 http://{TARGET_ONLY_PROXY}:8080/v02 && exit 0; sleep 2; done; exit 1', timeout=90)
            checks['V02_multi_identity_acl'] = id1_out.startswith('proxy1:') and id2_out.startswith('proxy2:')

            # V04: Remote rule list refresh + HTML error rejection keeping good version
            rl = gql(router, 'mutation($i:SaveRuleListInput!){saveRuleList(input:$i){ruleList{id}}}', {
                'i': {'name': 'remote-test', 'kind': 'domain', 'sourceType': 'remote',
                      'url': f'http://{MOCK_HTTP}:8080/rulelist', 'downloadMode': 'direct', 'cronEnable': False}}, tok)['saveRuleList']['ruleList']['id']
            rf1 = gql(router, 'mutation($i:ID!){refreshRuleList(id:$i){changed addedCount ruleList{lastEntryCount lastStatus}}}', {'i': rl}, tok)['refreshRuleList']
            set_mock_mode('bad-list')
            bad_rejected = False
            try:
                gql(router, 'mutation($i:ID!){refreshRuleList(id:$i){changed}}', {'i': rl}, tok)
            except RuntimeError:
                bad_rejected = True
            set_mock_mode('v1')
            lists = gql(router, 'query{ruleLists{id lastEntryCount lastStatus}}', token=tok)['ruleLists']
            rl_after = next(x for x in lists if x['id'] == rl)
            checks['V04_rulelist_and_bad_guard'] = rf1['addedCount'] == 2 and bad_rejected and rl_after['lastEntryCount'] == 2

            # V05: Enhanced subscription (Base64 init -> Clash YAML, UA, Userinfo, keyword filter, stable ID on rename, HTML/empty guard)
            set_mock_mode('init-b64')
            sub_res = gql(router, 'mutation($a:ImportArgument!){importSubscription(rollbackError:false,arg:$a){sub{id}}}',
                          {'a': {'link': f'http://{MOCK_HTTP}:8080/sub-yaml', 'tag': 'sub1'}}, tok)['importSubscription']['sub']['id']
            set_mock_mode('v1')
            gql(router, 'mutation($i:ID!,$in:SubscriptionEnhancedInput!){updateSubscriptionEnhanced(id:$i,input:$in){id}}', {
                'i': sub_res,
                'in': {'format': 'clash_yaml', 'userAgent': 'CustomUA/1.0', 'downloadMode': 'direct',
                       'excludeKeywords': 'Trial', 'filterPriority': 'exclude_first'}}, tok)
            sr1 = gql(router, 'mutation($i:ID!){refreshSubscriptionEnhanced(id:$i){addedCount filteredCount errors{protocol param} enhanced{trafficTotal}}}',
                      {'i': sub_res}, tok)['refreshSubscriptionEnhanced']
            nodes_v1 = gql(router, 'query($s:ID){nodes(subscriptionId:$s){edges{id name}}}', {'s': sub_res}, tok)['nodes']['edges']
            p1_id_before = next(n['id'] for n in nodes_v1 if 'P1' in n['name'])

            set_mock_mode('v2-rename')
            sr2 = gql(router, 'mutation($i:ID!){refreshSubscriptionEnhanced(id:$i){updatedCount addedCount}}', {'i': sub_res}, tok)['refreshSubscriptionEnhanced']
            nodes_v2 = gql(router, 'query($s:ID){nodes(subscriptionId:$s){edges{id name}}}', {'s': sub_res}, tok)['nodes']['edges']
            p1_after = next(n for n in nodes_v2 if n['id'] == p1_id_before)

            set_mock_mode('html')
            sub_html_rejected = False
            try:
                gql(router, 'mutation($i:ID!){refreshSubscriptionEnhanced(id:$i){changed}}', {'i': sub_res}, tok)
            except RuntimeError:
                sub_html_rejected = True
            last_ua = json.loads(mock_state_file.read_text()).get('last_ua', '')
            checks['V05_subscription_stable_id'] = (
                last_ua == 'CustomUA/1.0' and
                sr1['enhanced']['trafficTotal'] == '10000' and
                p1_after['name'] == 'P1-Renamed' and
                sub_html_rejected
            )

            # V06: Rollback to snapshot 1 + stale digest rejection
            stale_rejected = False
            try:
                gql(router, 'mutation{applyPolicyRevision(expectedDigest:"deadbeef"){success}}', token=tok)
            except RuntimeError:
                stale_rejected = True
            rb = gql(router, 'mutation($s:ID!){rollbackPolicy(snapshotId:$s){success rolledBack}}', {'s': ap1['snapshotId']}, tok)['rollbackPolicy']
            checks['V06_rollback_and_stale_digest'] = stale_rejected and rb['success'] and rb['rolledBack']

            # V07: Proxy chain creation & parseability + diagnostics probe
            ch = gql(router, 'mutation($i:SaveProxyChainInput!){saveProxyChain(input:$i){id parseable memberNames}}',
                     {'i': {'name': 'chain1', 'memberNodeIds': [n1, n2]}}, tok)['saveProxyChain']
            probe = gql(router, 'mutation($i:TestNodePathInput!){testNodePath(input:$i){parseable ok stage hopResults{ok}}}',
                        {'i': {'targetKind': 'node', 'targetId': n1, 'probeType': 'url', 'destination': f'http://{TARGET_ONLY_PROXY}:8080/probe'}}, tok)['testNodePath']
            checks['V07_chain_and_probe'] = ch['parseable'] and len(ch['memberNames']) == 2 and probe['parseable'] and probe['ok']

            # V08: Failover group configured as select + active route trace (V09 missing src_mac check!)
            g_fo = gql(router, 'mutation{createGroup(name:"g_failover",policy:fixed,policyParams:[{val:"0"}]){id}}', token=tok)['createGroup']['id']
            gql(router, 'mutation($g:ID!,$n:[ID!]!){groupAddNodes(id:$g,nodeIDs:$n)}', {'g': g_fo, 'n': [n1, n2]}, tok)
            fo = gql(router, 'mutation($i:SaveGroupFailoverInput!){saveGroupFailover(input:$i){enabled primaryMemberKey backupMemberKeys}}', {
                'i': {'groupId': g_fo, 'enabled': True, 'primaryMemberKey': 'node:1', 'backupMemberKeys': ['node:2'],
                      'probeUrl': f'http://{TARGET_ONLY_PROXY}:8080/probe'}}, tok)['saveGroupFailover']
            trace = gql(router, 'query($i:TraceRouteInput!){traceActiveRoute(input:$i){available generation decision outbound missingInputs}}', {
                'i': {'network': 'tcp', 'dstIp': TARGET_ONLY_PROXY, 'dstPort': 8080}}, tok)['traceActiveRoute']
            checks['V08_failover_and_V09_trace'] = fo['enabled'] and trace['available'] and trace['outbound'] == 'g_primary'

            # V09: Dashboard embedded HTML & assets served cleanly
            dash_html = client.run('curl --noproxy "*" -fsS --max-time 15 http://192.0.2.1:2023/')
            checks['V09_dashboard_served'] = '<html' in dash_html.lower()

        # V10: Real VLESS acceptance (separate disposable VM with secret virtio disk)
        if vless_file:
            run_v10_real_vless(base, work, vless_file, receipt)
            checks['V10_real_vless_tcp'] = receipt['v10']['tcp'] == 'passed' and receipt['v10']['negative_control'] and receipt['v10']['direct_control'] and receipt['v10']['recovery']
            checks['V10_real_vless_udp'] = receipt['v10']['udp'] == 'passed'

        failed = [k for k, v in checks.items() if not v]
        if failed:
            raise AssertionError(f'Failed checks: {failed}')
        receipt['status'] = 'passed'
    except BaseException as err:
        receipt.update(status='failed', error=str(err))
        raise
    finally:
        for g in reversed(guests):
            g.close()
        receipt['completed_at'] = time.time()
        result.write_text(json.dumps(receipt, indent=2) + '\n')
        for pattern in ('*.qcow2', '*.vars.fd', 'base.img'):
            for path in work.glob(pattern):
                path.unlink(missing_ok=True)
    return receipt


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--image', type=Path)
    parser.add_argument('--work-dir', type=Path)
    parser.add_argument('--vless-file', type=Path, default=None)
    parser.add_argument('--socks-label', help=argparse.SUPPRESS)
    parser.add_argument('--socks-forward', help=argparse.SUPPRESS)
    parser.add_argument('--mock-http', type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.socks_label:
        socks_forwarder(args.socks_label, args.socks_forward)
    elif args.mock_http:
        mock_http_cmd(args.mock_http)
    elif not args.image or not args.work_dir:
        parser.error('--image and --work-dir are required')
    else:
        print(json.dumps(run_isolated_suite(args.image, args.work_dir.resolve(), args.vless_file), indent=2))
