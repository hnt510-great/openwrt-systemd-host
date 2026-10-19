#!/usr/bin/env python3
"""Disposable-VM Passwall/Podman traffic and cgroup regression tests."""
import argparse
import base64
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import signal
import subprocess
import tarfile
import time


def run(*args, check=True, timeout=120):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise AssertionError(f'{args}: {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def wait(test, description, timeout=30):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if test():
            return
        time.sleep(0.3)
    raise AssertionError('Timed out: ' + description)


def uci(key, value):
    run('uci', 'set', key + '=' + value)


def cg(pid):
    return Path(f'/proc/{pid}/cgroup').read_text().strip().split('::', 1)[1]


def processes(prefix):
    result = []
    for p in Path('/proc').glob('[0-9]*/cmdline'):
        try:
            command = p.read_bytes().replace(b'\0', b' ')
            if prefix.encode() in command and b'xray' in command:
                result.append(int(p.parent.name))
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            pass
    return result


def traffic(port):
    return run('curl', '--noproxy', '', '--socks5-hostname', f'127.0.0.1:{port}',
               '--max-time', '5', '-fsS', 'http://203.0.113.2:18080/probe',
               check=False)


def passwall():
    server = {
        'log': {'access': '/tmp/cgroup-proxy-access.log', 'loglevel': 'warning'},
        'inbounds': [{'listen': '127.0.0.1', 'port': 19080, 'protocol': 'socks',
                      'settings': {'auth': 'noauth', 'udp': True}}],
        'outbounds': [{'protocol': 'freedom', 'streamSettings': {'sockopt': {'mark': 255}}}],
    }
    uci('passwall_server.global.enable', '1')
    uci('passwall_server.global.start_delay', '0')
    uci('passwall_server.cgroup_test', 'server')
    for key, value in {'enable': '1', 'type': 'Xray', 'custom': '1',
                       'remarks': 'Disposable cgroup test', 'port': '19080',
                       'firewall_allow': '0',
                       'config_str': base64.b64encode(json.dumps(server).encode()).decode()}.items():
        uci('passwall_server.cgroup_test.' + key, value)
    run('/etc/init.d/passwall_server', 'restart')
    wait(lambda: traffic(19080).returncode == 0, 'Passwall Server proxy traffic')
    for pid in processes('/tmp/etc/passwall_server/'):
        assert '/openwrt-passwall_server.slice/' in cg(pid), (pid, cg(pid))
    uci('passwall.cgroup_test', 'nodes')
    for key, value in {'type': 'Xray', 'protocol': 'socks', 'address': '127.0.0.1',
                       'port': '19080', 'remarks': 'Disposable cgroup test'}.items():
        uci('passwall.cgroup_test.' + key, value)
    for key, value in {'enabled': '1', 'node': 'cgroup_test', 'node_socks_port': '19180',
                       'dns_shunt': 'dnsmasq', 'dns_mode': 'udp',
                       'remote_dns': '127.0.0.1#53', 'direct_dns': '127.0.0.1#53',
                       'use_direct_list': '0', 'use_proxy_list': '0', 'use_block_list': '0',
                       'use_gfw_list': '0', 'chn_list': '0', 'dns_redirect': '0',
                       'udp_proxy_mode': 'disable'}.items():
        uci('passwall.@global[0].' + key, value)
    uci('passwall.@global_delay[0].start_delay', '0')
    uci('passwall.@global_delay[0].start_daemon', '1')
    run('/etc/init.d/passwall', 'restart')
    wait(lambda: traffic(19180).stdout.strip() == 'cgroup-traffic-ok',
         'Passwall client to server to controlled backend')
    clients = processes('/tmp/etc/passwall/')
    assert clients, 'no live client daemon'
    for pid in clients:
        assert '/openwrt-passwall.slice/' in cg(pid), (pid, cg(pid))
    assert '203.0.113.2:18080' in Path('/tmp/cgroup-proxy-access.log').read_text()
    old = clients[0]
    os.kill(old, signal.SIGKILL)
    wait(lambda: processes('/tmp/etc/passwall/') and old not in processes('/tmp/etc/passwall/'),
         'original Passwall monitor restarted its daemon', timeout=80)
    wait(lambda: traffic(19180).returncode == 0, 'traffic after monitor restart')
    for pid in processes('/tmp/etc/passwall/'):
        assert '/openwrt-passwall.slice/' in cg(pid), (pid, cg(pid))
    a = subprocess.Popen(['systemctl', 'restart', 'openwrt@passwall'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    b = subprocess.Popen(['/etc/init.d/passwall', 'restart'],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    assert a.wait(timeout=120) == 0 and b.wait(timeout=120) == 0
    wait(lambda: traffic(19180).returncode == 0, 'traffic after concurrent restarts')
    run('fw4', 'check')
    run('/etc/init.d/firewall', 'restart')
    wait(lambda: traffic(19180).returncode == 0, 'traffic after original firewall restart')
    run('nft', 'list', 'table', 'inet', 'fw4')
    run('nslookup', 'localhost', '127.0.0.1')
    print('PASS: Passwall and Server controlled traffic, daemon membership, original monitor, '
          'restart locks, firewall restart and DNS', flush=True)


def container_image():
    root = Path('/tmp/cgroup-container-root')
    for path in ['usr/bin', 'bin', 'tmp', 'proc', 'sys', 'dev', 'etc']:
        (root / path).mkdir(parents=True, exist_ok=True)
    (root / 'tmp').chmod(0o1777)
    # This image uses coreutils and networking applet alternatives; copy the
    # selected executables rather than assuming BusyBox includes each applet.
    for name in ['sh', 'sleep', 'wget', 'nslookup', 'cat', 'true']:
        binary = shutil.which(name)
        assert binary, name
        files = {binary}
        for line in run('ldd', binary).stdout.splitlines():
            match = re.search(r'=>\s+(/\S+)|^\s*(/\S+)', line)
            if match:
                files.add(match.group(1) or match.group(2))
        for source in files:
            dest = root / source.lstrip('/')
            dest.parent.mkdir(parents=True, exist_ok=True)
            if dest.is_symlink():
                dest.unlink()
            shutil.copyfile(source, dest)
            dest.chmod(0o755)
        dest = root / 'bin' / name
        if dest.is_symlink():
            dest.unlink()
        if dest != root / binary.lstrip('/'):
            shutil.copyfile(binary, dest)
            dest.chmod(0o755)
    (root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sh\n')
    (root / 'etc/group').write_text('root:x:0:\n')
    with tarfile.open('/tmp/cgroup-container.tar', 'w') as archive:
        for p in root.iterdir():
            archive.add(p, arcname=p.name)
    return 'localhost/cgroup-fixture:latest'


def oci_jail():
    bundle = Path('/tmp/cgroup-oci-bundle')
    bundle.mkdir(exist_ok=True)
    config = {
        'ociVersion': '1.2.0',
        'root': {'path': '/tmp/cgroup-container-root', 'readonly': False},
        'process': {'terminal': False, 'user': {'uid': 0, 'gid': 0},
                    'args': ['/bin/sleep', '600'], 'cwd': '/', 'env': ['PATH=/bin:/usr/bin']},
        'hostname': 'cgroup-test',
        'mounts': [{'destination': '/proc', 'type': 'proc', 'source': 'proc',
                    'options': ['nosuid', 'noexec', 'nodev']}],
        'linux': {'namespaces': [{'type': n} for n in ['mount', 'uts', 'ipc', 'pid']],
                  'cgroupsPath': 'fixture',
                  'resources': {'memory': {'limit': 33554432}, 'pids': {'limit': 16}}},
    }
    (bundle / 'config.json').write_text(json.dumps(config))
    data = {'name': 'cgroup-oci', 'instances': {'main': {
        'bundle': str(bundle), 'term_timeout': 1,
        'jail': {'name': 'cgroup-oci', 'procfs': True, 'sysfs': True, 'requirejail': True, 'immediately': True}}}}
    run('ubus', 'call', 'service', 'set', json.dumps(data))

    def instance():
        value = json.loads(run('ubus', 'call', 'service', 'list',
                               '{"name":"cgroup-oci","verbose":true}').stdout)
        return value.get('cgroup-oci', {}).get('instances', {}).get('main', {})

    wait(lambda: instance().get('systemd_placement') == 'managed', 'delegated jail registration')
    scope = instance()['systemd_scope']
    path = run('systemctl', 'show', scope, '-p', 'ControlGroup', '--value').stdout.strip()
    group = Path('/sys/fs/cgroup' + path)
    payload = group / 'payload/fixture'
    wait(lambda: (payload / 'memory.max').exists(), 'jail payload cgroup')
    assert (payload / 'memory.max').read_text().strip() == '33554432'
    assert (payload / 'pids.max').read_text().strip() == '16'
    assert not (group / 'cgroup.procs').read_text().strip(), 'process in an inner domain node'
    assert '/supervisor' in cg(instance()['pid'])
    assert not Path('/sys/fs/cgroup/containers').exists()
    run('ubus', 'call', 'service', 'delete', '{"name":"cgroup-oci"}')
    wait(lambda: not group.exists(), 'jail subtree and scope cleanup')
    config['linux']['cgroupsPath'] = '/not-delegated'
    (bundle / 'config.json').write_text(json.dumps(config))
    run('ubus', 'call', 'service', 'set', json.dumps(data))
    wait(lambda: instance().get('exit_code', 0) != 0, 'outside-delegation path rejected')
    assert not Path('/sys/fs/cgroup/not-delegated').exists()
    run('ubus', 'call', 'service', 'delete', '{"name":"cgroup-oci"}')
    print('PASS: OCI jail delegation, real memory/task controls, empty inner node, '
          'bounded paths and complete subtree cleanup', flush=True)


def podman():
    image = container_image()
    oci_jail()
    # Permit only the controlled backend across the disposable test interfaces.
    run('nft', 'insert', 'rule', 'inet', 'fw4', 'forward', 'ip', 'daddr',
        '203.0.113.2', 'tcp', 'dport', '18080', 'counter', 'accept')
    run('nft', 'insert', 'rule', 'inet', 'fw4', 'forward', 'ip', 'saddr',
        '203.0.113.2', 'ct', 'state', 'established,related', 'counter', 'accept')
    run('podman', 'import', '/tmp/cgroup-container.tar', image)
    assert run('podman', 'info', '--format', '{{.Host.CgroupManager}}').stdout.strip() == 'systemd'
    # Launch from an OpenWrt scope, as an init-script caller would. Podman
    # must still place its container in its independent manager-owned scope.
    run('/usr/libexec/openwrt-cgroup', 'exec', 'cgroup-podman', '/usr/bin/podman',
        'run', '-d', '--name', 'cgroup-rootful', '--network=none',
        '--memory=64m', '--pids-limit=16', image, '/bin/sleep', '600')
    pid = int(run('podman', 'inspect', 'cgroup-rootful', '--format', '{{.State.Pid}}').stdout)
    assert 'libpod' in cg(pid) and 'openwrt.slice' not in cg(pid), cg(pid)
    limits = Path('/sys/fs/cgroup' + cg(pid))
    assert (limits / 'memory.max').read_text().strip() == '67108864'
    assert (limits / 'pids.max').read_text().strip() == '16'
    run('podman', 'run', '--rm', image, '/bin/wget', '-qO-',
        'http://203.0.113.2:18080/probe')
    user = 'cgroup-test'
    if run('id', user, check=False).returncode:
        run('useradd', '-m', '-s', '/bin/sh', user)
    run('podman-rootless-setup', user)
    uid = int(run('id', '-u', user).stdout)
    wait(lambda: Path(f'/run/user/{uid}/bus').exists(), 'rootless user manager')

    def as_user(*args, **kwargs):
        cmd = ['env', 'HOME=/home/' + user, f'XDG_RUNTIME_DIR=/run/user/{uid}',
               f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', *args]
        return run('su', '-s', '/bin/sh', user, '-c', shlex.join(cmd), **kwargs)

    assert as_user('podman', 'info', '--format', '{{.Host.CgroupManager}}').stdout.strip() == 'systemd'
    mapping = as_user('podman', 'unshare', 'cat', '/proc/self/uid_map').stdout
    assert any(int(line.split()[2]) >= 65536 for line in mapping.splitlines())
    as_user('podman', 'import', '/tmp/cgroup-container.tar', image)
    as_user('podman', 'run', '-d', '--name', 'cgroup-rootless', '--network=none',
            '--memory=64m', '--pids-limit=16', image, '/bin/sleep', '600')
    pid = int(as_user('podman', 'inspect', 'cgroup-rootless', '--format', '{{.State.Pid}}').stdout)
    assert f'/user-{uid}.slice/' in cg(pid) and 'libpod' in cg(pid), cg(pid)
    limits = Path('/sys/fs/cgroup' + cg(pid))
    assert (limits / 'memory.max').read_text().strip() == '67108864'
    assert (limits / 'pids.max').read_text().strip() == '16'
    as_user('podman', 'run', '--rm', image, '/bin/wget', '-qO-',
            'http://203.0.113.2:18080/probe')
    as_user('podman', 'rm', '-f', 'cgroup-rootless')
    run('podman', 'rm', '-f', 'cgroup-rootful')
    print('PASS: offline rootful/rootless containers, subordinate IDs, independent systemd '
          'cgroups, requested limits and container networking', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable', action='store_true', required=True)
    parser.add_argument('--podman-only', action='store_true')
    args = parser.parse_args()
    assert Path('/proc/1/comm').read_text().strip() == 'systemd'
    # Lua UCI consumers require rpcd's live API.
    assert run('ubus', 'list', 'uci').stdout.strip() == 'uci', 'rpcd UCI API unavailable'
    run('ip', 'netns', 'add', 'cgroup-backend')
    run('ip', 'link', 'add', 'cgb-host', 'type', 'veth', 'peer', 'name', 'cgb-guest')
    run('ip', 'link', 'set', 'cgb-guest', 'netns', 'cgroup-backend')
    run('ip', 'addr', 'add', '203.0.113.1/24', 'dev', 'cgb-host')
    run('ip', 'link', 'set', 'cgb-host', 'up')
    run('ip', '-n', 'cgroup-backend', 'addr', 'add', '203.0.113.2/24', 'dev', 'cgb-guest')
    run('ip', '-n', 'cgroup-backend', 'link', 'set', 'cgb-guest', 'up')
    run('ip', '-n', 'cgroup-backend', 'link', 'set', 'lo', 'up')
    run('ip', '-n', 'cgroup-backend', 'route', 'add', 'default', 'via', '203.0.113.1')
    Path('/tmp/cgroup-www').mkdir(exist_ok=True)
    Path('/tmp/cgroup-www/probe').write_text('cgroup-traffic-ok\n')
    server = subprocess.Popen(['ip', 'netns', 'exec', 'cgroup-backend', 'python3', '-m',
                               'http.server', '18080', '--bind', '203.0.113.2',
                               '--directory', '/tmp/cgroup-www'],
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        wait(lambda: run('curl', '--noproxy', '*', '-fsS', '--max-time', '2',
                         'http://203.0.113.2:18080/probe', check=False).returncode == 0,
             'controlled HTTP backend')
        if not args.podman_only:
            passwall()
        podman()
    finally:
        server.terminate()
        server.wait(timeout=10)
        run('ip', 'link', 'del', 'cgb-host', check=False)
        run('ip', 'netns', 'del', 'cgroup-backend', check=False)


if __name__ == '__main__':
    main()
