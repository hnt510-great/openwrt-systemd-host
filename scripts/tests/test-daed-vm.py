#!/usr/bin/env python3
"""Boot an exact image as router plus LAN client under KVM and exercise daed.

The router's WAN is a restricted QEMU user network. Two private endpoints sit
behind it: a direct HTTP target (10.203.0.100:8080) and a fake SOCKS5 node
(10.203.0.101:1080) that answers every CONNECT itself. 10.203.0.102 has no
endpoint at all, so a client can only reach it through dae's proxy route.
Guest disks are disposable; the physical router is never touched.
"""
import argparse
import gzip
import importlib.util
import json
from pathlib import Path
import secrets
import shlex
import socket
import sys
import tempfile
import time

HERE = Path(__file__).resolve()
SPEC = importlib.util.spec_from_file_location('image_network', HERE.parents[1] / 'test-image-network.py')
NET = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(NET)

DIRECT = '10.203.0.100'
SOCKS = '10.203.0.101'
PROXIED = '10.203.0.102'
DAED_SYSLOG = ('{ journalctl -q -t daed -n 20 --no-pager 2>/dev/null; '
               'logread -e daed 2>/dev/null; } | tail -n 20; true')
# dae attaches with tcx BPF links on Linux 6.6+, which tc does not list. Count
# the daemon's tcx links on br-lan from fdinfo, plus any pinned in bpffs.
TCX_LAN = ("idx=$(cat /sys/class/net/br-lan/ifindex); n=0; "
           "for pid in $(busybox pgrep -x daed); do for f in /proc/$pid/fdinfo/*; do "
           "grep -q '^link_type:[[:space:]]*tcx' $f 2>/dev/null && "
           "grep -q \"^ifindex:[[:space:]]*$idx$\" $f && n=$((n+1)) || :; done; done; "
           "p=$(find /sys/fs/bpf -name '*lan_ingress*' 2>/dev/null | wc -l); echo $((n+p))")
REQUIRED = {
    'kernel-btf', 'kernel-config', 'daed-installed', 'daed-disabled-by-default',
    'passwall-interlock', 'dashboard-lan', 'daed-configured', 'default-lan-interface', 'tc-hooks',
    'route-direct', 'route-proxy', 'dns-through-dae', 'flow-offloading',
    'passwall-reload-stops-daed', 'stop-cleanup', 'restart', 'wan-dashboard-closed',
    'send-redirects-off', 'luci-acl-read', 'luci-log', 'luci-acl-denies-other-exec',
    'luci-toggle', 'luci-restart', 'luci-view-served', 'procd-init', 'procd-daed-autostart', 'procd-routes',
    'procd-stop-cleanup',
}


def socks_response(token):
    """One SOCKS5 CONNECT per guestfwd connection, answered by this process."""
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
    first = stream_in.readline(8192).decode('ascii', errors='replace').split()
    while True:
        line = stream_in.readline(8192)
        if line in (b'\r\n', b'\n', b''):
            break
    path = first[1] if len(first) == 3 else ''
    body = (f'proxied:{target}:{port}{path}').encode()
    if path != '/' + token and not path.startswith('/check'):
        body = b'proxied:unknown'
    stream_out.write((f'HTTP/1.1 200 OK\r\nContent-Length: {len(body)}\r\n'
                      'Connection: close\r\n\r\n').encode() + body)
    stream_out.flush()


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


def configure_daed(router, token):
    password = secrets.token_urlsafe(18) + 'a1'  # daed requires letters and digits
    gql(router, 'mutation($u:String!,$p:String!){createUser(username:$u,password:$p)}',
        {'u': 'admin', 'p': password})
    auth = gql(router, 'query($u:String!,$p:String!){token(username:$u,password:$p)}',
               {'u': 'admin', 'p': password})['token']
    nodes = gql(router, 'mutation($a:[ImportArgument!]!){importNodes(rollbackError:true,args:$a)'
                '{link error node{id}}}',
                {'a': [{'link': f'socks5://{SOCKS}:1080', 'tag': 'fake-socks'}]}, auth)['importNodes']
    if nodes[0]['error']:
        raise RuntimeError('Node import failed: ' + json.dumps(nodes))
    group = gql(router, 'mutation{createGroup(name:"proxy",policy:fixed,policyParams:[{val:"0"}]){id}}',
                token=auth)['createGroup']['id']
    gql(router, 'mutation($g:ID!,$n:[ID!]!){groupAddNodes(id:$g,nodeIDs:$n)}',
        {'g': group, 'n': [nodes[0]['node']['id']]}, auth)
    # Created like the dashboard's first-run setup, whose lanInterface is
    # empty on this router; the package default (patch 004) must fill it.
    config = gql(router, 'mutation($g:globalInput){createConfig(name:"vm",global:$g){id}}', {'g': {
        'lanInterface': [], 'wanInterface': [], 'logLevel': 'info',
        'tcpCheckUrl': [f'http://{PROXIED}:8080/check', PROXIED],
        'udpCheckDns': [f'{PROXIED}:53'], 'checkInterval': '30s',
        'dialMode': 'ip', 'autoConfigKernelParameter': True}}, auth)['createConfig']['id']
    routing = gql(router, 'mutation($r:String){createRouting(name:"vm",routing:$r){id}}', {
        'r': f'dip({PROXIED}/32) -> proxy\nfallback: direct\n'}, auth)['createRouting']['id']
    dns = gql(router, 'mutation($d:String){createDns(name:"vm",dns:$d){id}}', {
        'd': 'upstream {\n}\nrouting {\n request {\n  fallback: asis\n }\n'
             ' response {\n  fallback: accept\n }\n}\n'}, auth)['createDns']['id']
    for kind, ident in (('Config', config), ('Routing', routing), ('Dns', dns)):
        gql(router, f'mutation($i:ID!){{select{kind}(id:$i)}}', {'i': ident}, auth)
    configs = gql(router, 'query{configs{id global{lanInterface}}}', token=auth)['configs']
    lan = next(c['global']['lanInterface'] for c in configs if c['id'] == config)
    gql(router, 'mutation{run(dry:false)}', token=auth)
    return auth, lan


def ubus(client, session, obj, method, arguments, check=True):
    """JSON-RPC to the router's /ubus from the LAN client; returns (code, data)."""
    body = json.dumps({'jsonrpc': '2.0', 'id': 1, 'method': 'call',
                       'params': [session, obj, method, arguments]})
    output = client.run('curl --noproxy "*" -fsS --max-time 30 -H "Content-Type: application/json" --data ' +
                        shlex.quote(body) + ' http://192.0.2.1/ubus', timeout=60)
    value = json.loads(output)
    result = value.get('result') or [value.get('error', {}).get('code', -1)]
    if check and result[0] != 0:
        raise RuntimeError(f'ubus {obj}.{method} failed: {output}')
    return result[0], (result[1] if len(result) > 1 else {})


def wait(guest, command, timeout=90, interval=2):
    script = (f'for n in $(seq 1 {max(1, timeout // interval)}); do '
              f'if {command}; then exit 0; fi; sleep {interval}; done; exit 1')
    return guest.run(script, timeout=timeout + 30)


def test_daed(image, work):
    work.mkdir(parents=True, exist_ok=False)
    work.chmod(0o700)
    image = image.resolve()
    digest = NET.sha256(image)
    receipt = {'schema': 1, 'image': str(image), 'image_sha256': digest,
               'checks': {}, 'status': 'running', 'started_at': time.time()}
    result = work / 'validation.json'
    result.write_text(json.dumps(receipt, indent=2))
    token = secrets.token_hex(24)
    base = work / 'base.img'
    guests = []
    checks = receipt['checks']
    try:
        # Sparse extraction, as in test-image-network.py.
        with gzip.open(image, 'rb') as source, base.open('wb') as target:
            zero = bytes(1024 * 1024)
            while chunk := source.read(1024 * 1024):
                if chunk == zero[:len(chunk)]:
                    target.seek(len(chunk), 1)
                else:
                    target.write(chunk)
            target.truncate()
        base.chmod(0o400)
        with tempfile.TemporaryDirectory(prefix='owrt-daed-') as temporary:
            runtime = Path(temporary)
            listener = socket.socket()
            listener.bind(('127.0.0.1', 0))
            lan_port = listener.getsockname()[1]
            listener.close()
            responder = shlex.join([sys.executable, str(HERE.parents[1] / 'test-image-network.py'),
                                    '--wan-response', token])
            socks = shlex.join([sys.executable, str(HERE), '--socks-response', token])
            wan = ('user,id=wan,net=10.203.0.0/24,host=10.203.0.2,dns=10.203.0.3,ipv6=off,restrict=on,'
                   f'guestfwd=tcp:{DIRECT}:8080-cmd:{responder},'
                   f'guestfwd=tcp:{SOCKS}:1080-cmd:{socks}')
            router_net = [
                '-netdev', f'socket,id=lan,listen=127.0.0.1:{lan_port}',
                '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ed:01:01',
                '-netdev', wan, '-device', 'virtio-net-pci,netdev=wan,mac=52:54:00:ed:01:02']
            client_net = [
                '-netdev', f'socket,id=lan,connect=127.0.0.1:{lan_port}',
                '-device', 'virtio-net-pci,netdev=lan,mac=52:54:00:ed:02:01']
            router = NET.Guest('router', work, runtime, base, router_net, 2048)
            guests.append(router)
            # Keep kernel printk off the serial console that carries framed output.
            router.run('dmesg -n 1')
            receipt['router_init'] = router.run('cat /proc/1/comm')
            receipt['guest_kernel'] = router.run('uname -r')

            checks['kernel-btf'] = router.run('test -s /sys/kernel/btf/vmlinux && '
                                              'stat -c %s /sys/kernel/btf/vmlinux').isdigit()
            config = router.run("zcat /proc/config.gz | grep -E '^CONFIG_(DEBUG_INFO_BTF|BPF_STREAM_PARSER|"
                                "NETKIT|NET_CLS_BPF|NET_SCH_INGRESS|NET_CLS_ACT|BPF_SYSCALL|BPF_JIT|"
                                "KPROBE_EVENTS|BPF_EVENTS|CGROUP_BPF)='")
            receipt['kernel_config'] = config.splitlines()
            checks['kernel-config'] = all(f'CONFIG_{name}=' in config for name in (
                'DEBUG_INFO_BTF', 'BPF_STREAM_PARSER', 'NETKIT', 'NET_CLS_BPF', 'NET_SCH_INGRESS'))
            receipt['daed_version'] = router.run('daed --version')
            checks['daed-installed'] = '2.' in receipt['daed_version']
            router.run('test -L /usr/share/dae/geoip.dat && test -s /usr/share/dae/geoip.dat && '
                       'test -s /usr/share/dae/geosite.dat')
            checks['daed-disabled-by-default'] = router.run(
                'uci get daed.config.enabled; ! busybox pgrep -x daed >/dev/null && echo idle') == '0\nidle'

            NET.disable_external_integrations(router)
            router.run(NET.network_config())
            router.run("for n in $(seq 1 40); do ubus call network.interface.wan status | grep -q '\"up\": true' "
                       "&& ip -4 addr show dev br-lan | grep -q '192.0.2.1/24' && exit 0; sleep 2; done; exit 1",
                       timeout=100)
            router.run("uci set dhcp.lan.interface=lan; uci set dhcp.lan.ignore=0; uci set dhcp.lan.start=100; "
                       "uci set dhcp.lan.limit=20; uci add_list dhcp.@dnsmasq[0].address='/scheduler.test/"
                       f"{DIRECT}'; uci commit dhcp; /etc/init.d/dnsmasq restart; /etc/init.d/firewall restart")
            receipt['flow_offloading'] = router.run("uci -q get firewall.@defaults[0].flow_offloading || echo 0")
            if receipt['flow_offloading'] != '1':
                router.run("uci set firewall.@defaults[0].flow_offloading=1; uci commit firewall; fw4 reload")
            checks['flow-offloading'] = 'flowtable' in router.run('nft list ruleset | grep -m1 flowtable')

            # Interlock: with Passwall enabled in UCI, enabling daed must not start it.
            router.run('uci -q set passwall.@global[0].enabled=1 && uci commit passwall')
            router.run('uci set daed.config.enabled=1; uci commit daed; /etc/init.d/daed restart || :')
            time.sleep(3)
            interlock = router.run('busybox pgrep -x daed >/dev/null && echo running || echo stopped; ' +
                                   DAED_SYSLOG)
            checks['passwall-interlock'] = interlock.startswith('stopped') and 'Passwall is enabled' in interlock
            router.run('uci set passwall.@global[0].enabled=0; uci commit passwall; /etc/init.d/daed start')
            wait(router, 'curl --noproxy "*" -fsS --max-time 3 -H "Content-Type: application/json" '
                         "--data '{\"query\":\"{healthCheck}\"}' http://127.0.0.1:2023/graphql >/dev/null", 60)

            client = NET.Guest('client', work, runtime, base, client_net, 1536)
            guests.append(client)
            client.run('dmesg -n 1')
            NET.disable_external_integrations(client)
            client.run('for s in daed passwall passwall_server dnsmasq odhcpd firewall; do '
                       '[ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
            client.run(NET.network_config(client=True))
            client.run("for n in $(seq 1 40); do ip -4 route | grep -q 'default via 192.0.2.1' && exit 0; "
                       "sleep 2; done; exit 1", timeout=100)
            client.run("printf 'nameserver 192.0.2.1\\n' > /tmp/daed-resolv.conf; "
                       "ln -sf /tmp/daed-resolv.conf /etc/resolv.conf")
            # Baseline before dae takes over: direct works, the proxy-only address does not.
            assert client.run(f'curl -4 --noproxy "*" -fsS --max-time 15 http://{DIRECT}:8080/{token}') == token
            client.run(f'! curl -4 --noproxy "*" -fsS --max-time 5 http://{PROXIED}:8080/{token}')
            html = client.run('curl --noproxy "*" -fsS --max-time 15 http://192.0.2.1:2023/')
            checks['dashboard-lan'] = '<html' in html.lower()
            checks['wan-dashboard-closed'] = 'reject' in router.run(
                "nft list chain inet fw4 input_wan | tail -n 3")

            _, receipt['config_lan_interface'] = configure_daed(router, token)
            checks['daed-configured'] = True
            checks['default-lan-interface'] = receipt['config_lan_interface'] == ['br-lan']
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)
            receipt['tcx_links_br_lan'] = int(router.run(TCX_LAN))
            hooks = router.run('ip -d link show dae0; tc qdisc show dev br-lan')
            receipt['dae0'] = hooks.splitlines()
            checks['tc-hooks'] = receipt['tcx_links_br_lan'] > 0 and 'dae0' in hooks
            receipt['dae0_type'] = 'netkit' if 'netkit' in hooks else 'veth' if 'veth' in hooks else 'unknown'

            for _ in range(3):
                assert client.run(f'curl -4 --noproxy "*" -fsS --max-time 15 '
                                  f'http://{DIRECT}:8080/{token}') == token
            checks['route-direct'] = True
            proxied = client.run(f'for n in $(seq 1 30); do curl -4 --noproxy "*" -fsS --max-time 10 '
                                 f'http://{PROXIED}:8080/{token} && exit 0; sleep 2; done; exit 1', timeout=150)
            checks['route-proxy'] = proxied == f'proxied:{PROXIED}:8080/{token}'
            dns = client.run('nslookup -type=A scheduler.test 192.0.2.1')
            checks['dns-through-dae'] = DIRECT in dns
            # Backported dae e3fee8f: conf/all must be cleared, not only br-lan.
            checks['send-redirects-off'] = router.run(
                'cat /proc/sys/net/ipv4/conf/all/send_redirects /proc/sys/net/ipv4/conf/br-lan/send_redirects'
            ).split() == ['0', '0']
            receipt['daed_log'] = router.run('tail -n 40 /var/log/daed/daed.log').splitlines()

            # Turning Passwall on later reloads daed through the procd trigger and stops it.
            router.run('uci set passwall.@global[0].enabled=1; uci commit passwall; '
                       'ubus call service event \'{"type":"config.change","data":{"package":"passwall"}}\'')
            stopped = wait(router, '! busybox pgrep -x daed >/dev/null', 30)
            checks['passwall-reload-stops-daed'] = stopped == ''
            router.run('uci set passwall.@global[0].enabled=0; uci commit passwall')
            leftovers = router.run(TCX_LAN + '; ip link show dae0 2>/dev/null | wc -l')
            client.run(f'! curl -4 --noproxy "*" -fsS --max-time 5 http://{PROXIED}:8080/{token}')
            assert client.run(f'curl -4 --noproxy "*" -fsS --max-time 15 http://{DIRECT}:8080/{token}') == token
            checks['stop-cleanup'] = leftovers.split() == ['0', '0']

            # The selected configuration is persistent: a plain start resumes proxying.
            router.run('/etc/init.d/daed start')
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)
            proxied = client.run(f'for n in $(seq 1 30); do curl -4 --noproxy "*" -fsS --max-time 10 '
                                 f'http://{PROXIED}:8080/{token} && exit 0; sleep 2; done; exit 1', timeout=150)
            checks['restart'] = proxied == f'proxied:{PROXIED}:8080/{token}'

            # LuCI: a non-root rpcd login holding only luci-base (which every LuCI
            # user needs) and luci-app-daed, driven from the LAN client the way
            # the browser view does; saves use uci apply like LuCI.
            ui_password = secrets.token_urlsafe(18)
            router.run(f"hash=$(uhttpd -m {shlex.quote(ui_password)}); test -n \"$hash\"; "
                       "uci -q delete rpcd.daedui || :; uci set rpcd.daedui=login; "
                       "uci set rpcd.daedui.username=daedui; "
                       "uci set rpcd.daedui.password=\"$hash\"; "
                       "for g in luci-base luci-app-daed; do uci add_list rpcd.daedui.read=$g; "
                       "uci add_list rpcd.daedui.write=$g; done; uci commit rpcd; /etc/init.d/rpcd reload")
            time.sleep(2)
            session = ubus(client, '0' * 32, 'session', 'login',
                           {'username': 'daedui', 'password': ui_password})[1]['ubus_rpc_session']
            checks['luci-acl-read'] = ubus(client, session, 'uci', 'get',
                                           {'config': 'daed', 'section': 'config'})[1]['values']['enabled'] == '1'
            log = ubus(client, session, 'file', 'exec', {'command': '/usr/bin/tail',
                       'params': ['-n', '200', '/var/log/daed/daed.log']})[1]
            checks['luci-log'] = log.get('code') == 0 and 'Bind to LAN' in log.get('stdout', '')
            denied = ubus(client, session, 'file', 'exec', {'command': '/bin/sh', 'params': ['-c', 'id']},
                          check=False)[0]
            checks['luci-acl-denies-other-exec'] = denied != 0
            # Disable then enable through rpcd uci set/commit (LuCI save & apply).
            ubus(client, session, 'uci', 'set', {'config': 'daed', 'section': 'config', 'values': {'enabled': '0'}})
            ubus(client, session, 'uci', 'apply', {'rollback': False})
            wait(router, '! busybox pgrep -x daed >/dev/null', 60)
            ubus(client, session, 'uci', 'set', {'config': 'daed', 'section': 'config', 'values': {'enabled': '1'}})
            ubus(client, session, 'uci', 'apply', {'rollback': False})
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)
            proxied = client.run(f'for n in $(seq 1 30); do curl -4 --noproxy "*" -fsS --max-time 10 '
                                 f'http://{PROXIED}:8080/{token} && exit 0; sleep 2; done; exit 1', timeout=150)
            checks['luci-toggle'] = proxied == f'proxied:{PROXIED}:8080/{token}'
            restart = ubus(client, session, 'file', 'exec', {'command': '/etc/init.d/daed', 'params': ['restart']})[1]
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 90)
            checks['luci-restart'] = restart.get('code') == 0
            view_js = client.run('curl --noproxy "*" -fsS --max-time 15 '
                                 'http://192.0.2.1/luci-static/resources/view/daed/settings.js')
            menu = router.run('cat /usr/share/luci/menu.d/luci-app-daed.json')
            checks['luci-view-served'] = 'dashboardURL' in view_js and 'admin/services/daed' in menu

            # procd recovery boot: daed is an rc service, so the same enabled
            # configuration must come up when procd is PID 1. Make GRUB's
            # "procd recovery" entry the default on this disposable disk and
            # power-cycle both guests on their persistent overlays.
            # kernelctl owns grub.cfg; use its one-shot next_entry, like a trial boot.
            grub = router.run('cat /boot/grub/grub.cfg')
            entry = 'owrt-rescue-procd'
            if f'--id={entry} ' not in grub:
                raise AssertionError('No procd recovery GRUB entry: ' + grub)
            router.run(f'grub-editenv /boot/grub/grubenv set next_entry={entry}; '
                       'grub-editenv /boot/grub/grubenv list; sync')
            receipt['grub_next_entry'] = entry
            client.close()
            router.close()
            guests.clear()
            router = NET.Guest('router', work, runtime, base, router_net, 2048)
            guests.append(router)
            router.run('dmesg -n 1')
            receipt['recovery_cmdline'] = router.run('cat /proc/cmdline')
            checks['procd-init'] = (router.run('cat /proc/1/comm') == 'procd' and
                                    'openwrt.init=procd' in receipt['recovery_cmdline'])
            wait(router, f'[ "$({TCX_LAN})" -gt 0 ]', 120)
            checks['procd-daed-autostart'] = int(router.run(TCX_LAN)) > 0
            client = NET.Guest('client', work, runtime, base, client_net, 1536)
            guests.append(client)
            client.run('dmesg -n 1')
            client.run('for s in daed passwall passwall_server dnsmasq odhcpd firewall; do '
                       '[ ! -x /etc/init.d/$s ] || /etc/init.d/$s stop; done; true')
            client.run("for n in $(seq 1 40); do ip -4 route | grep -q 'default via 192.0.2.1' && exit 0; "
                       "sleep 2; done; exit 1", timeout=100)
            client.run("printf 'nameserver 192.0.2.1\\n' > /tmp/daed-resolv.conf; "
                       "ln -sf /tmp/daed-resolv.conf /etc/resolv.conf")
            assert client.run(f'curl -4 --noproxy "*" -fsS --max-time 15 http://{DIRECT}:8080/{token}') == token
            proxied = client.run(f'for n in $(seq 1 30); do curl -4 --noproxy "*" -fsS --max-time 10 '
                                 f'http://{PROXIED}:8080/{token} && exit 0; sleep 2; done; exit 1', timeout=150)
            checks['procd-routes'] = proxied == f'proxied:{PROXIED}:8080/{token}'
            router.run('/etc/init.d/daed stop')
            wait(router, '! busybox pgrep -x daed >/dev/null', 30)
            leftovers = router.run(TCX_LAN + '; ip link show dae0 2>/dev/null | wc -l')
            client.run(f'! curl -4 --noproxy "*" -fsS --max-time 5 http://{PROXIED}:8080/{token}')
            checks['procd-stop-cleanup'] = leftovers.split() == ['0', '0']

            missing = REQUIRED - set(checks)
            failed = [name for name, value in checks.items() if not value]
            if missing or failed:
                raise AssertionError(f'missing={sorted(missing)} failed={failed}')
            assert NET.sha256(image) == digest, 'Image changed during validation'
            receipt['status'] = 'passed'
    except BaseException as error:
        receipt.update(status='failed', error=str(error))
        for guest in guests:
            try:
                guest.run(DAED_SYSLOG + '; tail -n 80 /var/log/daed/daed.log 2>/dev/null || :; ' +
                          TCX_LAN + '; ip -br link; ip -4 route; '
                          'journalctl -b -n 60 --no-pager || :', timeout=20)
            except Exception:
                pass
        raise
    finally:
        for guest in reversed(guests):
            guest.close()
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
    parser.add_argument('--socks-response', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.socks_response:
        socks_response(args.socks_response)
    elif not args.image or not args.work_dir:
        parser.error('--image and --work-dir are required')
    else:
        print(json.dumps(test_daed(args.image, args.work_dir.resolve()), indent=2))
