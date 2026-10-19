#!/usr/bin/env python3
"""Exercise real cgroup placement; run only in an explicitly disposable VM."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def run(*args, check=True, timeout=90):
    result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
    if check and result.returncode:
        raise AssertionError(f'{args}: {result.returncode}\n{result.stdout}\n{result.stderr}')
    return result


def wait(test, description, timeout=20):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if test():
            return
        time.sleep(0.1)
    raise AssertionError('Timed out: ' + description)


def instances():
    data = json.loads(run('ubus', 'call', 'service', 'list',
                          '{"name":"cgroup-smoke","verbose":true}').stdout)
    return data.get('cgroup-smoke', {}).get('instances', {})


def alive(pid):
    p = Path(f'/proc/{pid}/stat')
    try:
        return p.read_text().split(') ')[1][0] != 'Z'
    except FileNotFoundError:
        return False


def membership(pid):
    return Path(f'/proc/{pid}/cgroup').read_text().strip().split('::', 1)[1]


def managed(instance='main'):
    data = instances().get(instance, {})
    if not data.get('running') or data.get('systemd_placement') != 'managed':
        return False
    group = run('systemctl', 'show', data['systemd_scope'], '-p', 'ControlGroup',
                '--value').stdout.strip()
    assert membership(data['pid']) == group, (data, group, membership(data['pid']))
    assert '/openwrt-cgroup\\x2dsmoke.slice/' in group, group
    return data


def write(path, text):
    p = Path(path)
    p.write_text(text)
    p.chmod(0o755)


def fixture():
    write('/usr/libexec/cgroup-supervised-test.py', '''#!/usr/bin/python3
import os, time
pid = os.fork()
if not pid:
    while True: time.sleep(3600)
open('/tmp/cgroup-worker-' + str(os.getpid()), 'w').write(str(pid))
while True: time.sleep(3600)
''')
    write('/etc/init.d/cgroup-smoke', '''#!/bin/sh /etc/rc.common
START=98
STOP=10
USE_PROCD=1
start_service() {
    procd_open_instance main
    procd_set_param command /usr/bin/python3 /usr/libexec/cgroup-supervised-test.py
    procd_set_param respawn 3600 1 0
    procd_set_param term_timeout 1
    procd_close_instance
    if [ -e /tmp/cgroup-extra ]; then
        procd_open_instance extra
        procd_set_param command /bin/sleep 3600
        procd_close_instance
    fi
}
reload_service() { echo reload >> /tmp/cgroup-reloads; }
service_triggers() { procd_add_reload_trigger cgroup_smoke; }
''')
    write('/tmp/cgroup-legacy-launch.py', '''#!/usr/bin/python3
import os, sys
pid = os.fork()
if pid: sys.exit(0)
os.setsid()
pid = os.fork()
if pid: os._exit(0)
open('/tmp/cgroup-legacy.pid', 'w').write(str(os.getpid()))
os.execl('/bin/sleep', 'sleep', '3600')
''')
    write('/etc/init.d/cgroup-legacy', '''#!/bin/sh /etc/rc.common
START=98
STOP=10
EXTRA_COMMANDS="terminate"
start() { /usr/bin/python3 /tmp/cgroup-legacy-launch.py; }
stop() { :; }
terminate() { kill "$(cat /tmp/cgroup-legacy.pid)"; }
restart() {
    echo custom >> /tmp/cgroup-legacy-restarts
    terminate
    start
}
''')
    write('/etc/init.d/cgroup-bare', '''#!/bin/sh
START=98
case "$1" in
    start|boot) /bin/sleep 3600 & echo $! > /tmp/cgroup-bare.pid ;;
    stop|shutdown) kill "$(cat /tmp/cgroup-bare.pid)" ;;
    *) exit 2 ;;
esac
''')


def normal():
    assert not Path('/sys/fs/cgroup/services').exists(), 'procd wrote a host-root services cgroup'
    assert not Path('/sys/fs/cgroup/containers').exists(), 'ujail wrote a host-root containers cgroup'
    assert not Path('/usr/lib/systemd/system-generators/openwrt-services-generator').exists()
    assert not run('pgrep', '-f', 'openwrt-service-bridge proxy', check=False).stdout.strip()
    fixture()
    run('/etc/init.d/cgroup-smoke', 'enable')
    run('/etc/init.d/cgroup-smoke', 'start')
    wait(managed, 'initial placement')
    first = managed()
    worker_file = Path('/tmp/cgroup-worker-' + str(first['pid']))
    wait(worker_file.exists, 'worker created')
    worker = int(worker_file.read_text())
    assert membership(worker) == membership(first['pid'])
    Path('/tmp/cgroup-extra').touch()
    run('/etc/init.d/cgroup-smoke', 'start')
    wait(lambda: managed('extra'), 'dynamic instance added')
    assert managed()['pid'] == first['pid'], 'unchanged instance restarted'
    extra = managed('extra')
    Path('/tmp/cgroup-extra').unlink()
    run('/etc/init.d/cgroup-smoke', 'start')
    wait(lambda: 'extra' not in instances(), 'dynamic instance removed')
    wait(lambda: not alive(extra['pid']), 'removed instance dead')
    for _ in range(6):
        old = managed()
        worker_file = Path('/tmp/cgroup-worker-' + str(old['pid']))
        wait(worker_file.exists, 'worker before respawn')
        worker = int(worker_file.read_text())
        os.kill(old['pid'], signal.SIGKILL)
        wait(lambda: managed() and managed()['pid'] != old['pid'], 'procd respawn')
        assert managed()['systemd_scope'] != old['systemd_scope']
        wait(lambda: not alive(worker), 'old worker removed before replacement')
        wait(lambda: run('systemctl', 'show', old['systemd_scope'], '-p',
                         'ControlGroup', '--value', check=False).stdout.strip() == '',
             'old scope collected')
    run('ubus', 'call', 'service', 'event',
        '{"type":"config.change","data":{"package":"cgroup_smoke"}}')
    wait(lambda: Path('/tmp/cgroup-reloads').exists(), 'UCI reload trigger')
    before = managed()
    run('systemctl', 'restart', 'openwrt-service-bridge')
    assert managed()['pid'] == before['pid'], 'bridge restart changed daemon PID'
    run('systemctl', 'daemon-reload')
    run('systemctl', 'daemon-reexec')
    assert managed()['pid'] == before['pid']
    run('systemctl', 'start', 'openwrt@cgroup-legacy')
    wait(lambda: Path('/tmp/cgroup-legacy.pid').exists(), 'double-forked daemon')
    pid = int(Path('/tmp/cgroup-legacy.pid').read_text())
    group = membership(pid)
    assert '/openwrt-cgroup\\x2dlegacy.slice/' in group, group
    run('/etc/init.d/cgroup-legacy', 'stop')
    assert alive(pid), 'generic cleanup overrode the original legacy stop handler'
    assert membership(pid) == group
    run('systemctl', 'restart', 'openwrt@cgroup-legacy')
    wait(lambda: int(Path('/tmp/cgroup-legacy.pid').read_text()) != pid, 'legacy restart')
    assert Path('/tmp/cgroup-legacy-restarts').read_text().splitlines() == ['custom']
    wait(lambda: not alive(pid), 'legacy handler stopped old daemon')
    run('/etc/init.d/cgroup-legacy', 'terminate')
    run('systemctl', 'start', 'openwrt@cgroup-bare')
    pid = int(Path('/tmp/cgroup-bare.pid').read_text())
    assert '/openwrt-cgroup\\x2dbare.slice/' in membership(pid)
    run('systemctl', 'stop', 'openwrt@cgroup-bare')
    wait(lambda: not alive(pid), 'bare script stop')
    Path('/etc/rc.d/S98cgroup-bare').symlink_to('../init.d/cgroup-bare')
    Path('/etc/rc.d/K10cgroup-bare').symlink_to('../init.d/cgroup-bare')
    # Apply limits to a real service slice and demonstrate fork refusal.
    run('/usr/libexec/openwrt-cgroup', 'exec', 'cgroup-limit', '/bin/true')
    slice_name = r'openwrt-cgroup\x2dlimit.slice'
    run('systemctl', 'set-property', '--runtime', slice_name, 'TasksMax=8', 'MemoryMax=64M', 'MemorySwapMax=0')
    code = '''import os, time
children=[]
try:
    for i in range(64):
        pid=os.fork()
        if not pid:
            time.sleep(10); os._exit(0)
        children.append(pid)
except BlockingIOError:
    print('limited', len(children))
finally:
    for pid in children: os.kill(pid, 9)
    for pid in children: os.waitpid(pid, 0)
assert 0 < len(children) < 8, len(children)
'''
    assert 'limited' in run('/usr/libexec/openwrt-cgroup', 'exec', 'cgroup-limit',
                            '/usr/bin/python3', '-c', code).stdout
    killed = run('/usr/libexec/openwrt-cgroup', 'exec', 'cgroup-limit', '/usr/bin/python3',
                 '-c', 'x=bytearray(128*1024*1024); '
                 'exec("for i in range(0,len(x),4096): x[i]=1")', check=False)
    assert killed.returncode in (-signal.SIGKILL, 128 + signal.SIGKILL), killed
    write('/usr/libexec/cgroup-detached-test.py', 'import os,time\n'
          'from pathlib import Path\npid=os.fork()\nif pid:\n time.sleep(.2)\n os._exit(0)\n'
          'Path("/tmp/cgroup-detached.pid").write_text(str(os.getpid()))\ntime.sleep(600)\n')
    detached = {'name': 'cgroup-detached', 'instances': {'main': {
        'command': ['/usr/bin/python3', '/usr/libexec/cgroup-detached-test.py']}}}
    run('ubus', 'call', 'service', 'set', json.dumps(detached))
    pid_file = Path('/tmp/cgroup-detached.pid')
    wait(pid_file.exists, 'daemonizing child recorded')
    pid = int(pid_file.read_text())
    time.sleep(0.5)
    assert alive(pid), 'normal non-respawn parent exit killed a daemonized child'
    assert '/openwrt-cgroup\\x2ddetached.slice/' in membership(pid)
    run('ubus', 'call', 'service', 'set', json.dumps(detached))
    wait(lambda: int(pid_file.read_text()) != pid, 'detached execution replaced')
    wait(lambda: not alive(pid), 'old detached worker drained before replacement')
    pid = int(pid_file.read_text())
    run('ubus', 'call', 'service', 'delete', '{"name":"cgroup-detached"}')
    wait(lambda: not alive(pid), 'explicit deletion stops detached worker')
    Path('/tmp/cgroup-unavailable-socket').touch()
    degraded = run('unshare', '--mount', '--propagation', 'private', '/bin/sh', '-c',
                   'mount --bind /tmp/cgroup-unavailable-socket /run/systemd/private; '
                   'exec /usr/libexec/openwrt-cgroup exec cgroup-failure /bin/true')
    assert 'inherited cgroup placement' in degraded.stderr, degraded
    assert not Path('/sys/fs/cgroup/services').exists()
    assert not Path('/sys/fs/cgroup/containers').exists()
    print('PASS: actual placement, dynamic instances, six respawns with worker cleanup, '
          'legacy double-fork/custom restart, bridge isolation, reexec, live memory/task limits, '
          'availability-first manager failure')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable', action='store_true', required=True)
    parser.add_argument('--after-reboot', action='store_true')
    parser.add_argument('--recovery', action='store_true')
    args = parser.parse_args()
    if args.recovery:
        assert Path('/proc/1/comm').read_text().strip() == 'procd'
        run('/etc/init.d/cgroup-smoke', 'start')
        wait(lambda: instances().get('main', {}).get('running'), 'recovery start')
        assert 'systemd_scope' not in instances()['main']
        run('/etc/init.d/cgroup-smoke', 'stop')
        print('PASS: recovery retains original procd placement and supervision')
    elif args.after_reboot:
        assert Path('/proc/1/comm').read_text().strip() == 'systemd'
        wait(managed, 'enabled daemon after reboot')
        wait(lambda: Path('/tmp/cgroup-bare.pid').exists(), 'bare boot script launched')
        pid = int(Path('/tmp/cgroup-bare.pid').read_text())
        assert alive(pid) and '/openwrt-cgroup\\x2dbare.slice/' in membership(pid)
        print('PASS: enabled procd instance and bare init script have real scopes after reboot')
    else:
        assert Path('/proc/1/comm').read_text().strip() == 'systemd'
        normal()


if __name__ == '__main__':
    main()
