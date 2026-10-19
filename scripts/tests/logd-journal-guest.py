#!/usr/bin/env python3
"""Exercise unified logging ONLY inside a disposable OpenWrt VM.

Run with --disposable. Restarts logging and temporarily changes UCI logging.
--recovery checks the original procd path instead. --vacuum deletes journal
history and is intended only for a dedicated retention test VM.
Use --prepare-storage-failure, reboot, then --storage-recovery to exercise
runtime fallback and a live persistent mount/flush transition.
"""
import argparse
import json
import os
from pathlib import Path
import select
import signal
import socket
import struct
import subprocess
import tempfile
import time
import uuid


def run(*args, input=None):
    return subprocess.check_output(args, input=input, text=True, stderr=subprocess.STDOUT)


def wait_for(callback, description, seconds=15):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = callback()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError('Timed out: ' + description)


def entries():
    try:
        return json.loads(run('ubus', '-t', '2', 'call', 'log', 'read',
                              '{"stream":false,"lines":10000}')).get('log', [])
    except subprocess.CalledProcessError:
        return []


def find(marker):
    return [entry for entry in entries() if marker in entry['msg']]


def logd_pid():
    return subprocess.run(['pidof', 'logd'], text=True, capture_output=True).stdout.strip()


def journal(marker):
    # Filter decoded JSON as well, including binary MESSAGE fields.
    output = run('journalctl', '-b', '-o', 'json', '--no-pager', '-n', '1000')
    result = []
    for line in output.splitlines():
        if not line.startswith('{'):
            continue
        entry = json.loads(line)
        message = entry.get('MESSAGE', '')
        if isinstance(message, list):
            message = bytes(message).decode('utf-8', 'replace')
        if marker in message:
            result.append(entry)
    return result


def syslog(marker, priority=131, tag='logd-journal-test', pid=4242):
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
        sender.sendto(f'<{priority}>{tag}[{pid}]: {marker}'.encode(), '/dev/log')


def native(marker, payload=None, uid=None):
    message = marker.encode() if payload is None else payload
    packet = (b'PRIORITY=2\nSYSLOG_FACILITY=17\n'
              b'SYSLOG_IDENTIFIER=logd-journal-binary-test\nMESSAGE\n' +
              struct.pack('<Q', len(message)) + message + b'\n')
    if uid is not None:
        child = os.fork()
        if child:
            assert os.waitpid(child, 0)[1] == 0
            return
        os.setgroups([])
        os.setgid(uid)
        os.setuid(uid)
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sender:
        sender.sendto(packet, '/run/systemd/journal/socket')
    if uid is not None:
        os._exit(0)


def check_once(marker):
    result = wait_for(lambda: find(marker), marker)
    assert len(result) == 1, result
    stored = wait_for(lambda: journal(marker), 'journal ' + marker)
    assert len(stored) == 1, stored
    return result[0], stored[0]


def forwarder_ready(peer, probe, received=b''):
    deadline = time.monotonic() + 15
    while probe.encode() not in received and time.monotonic() < deadline:
        syslog(probe)
        if select.select([peer], [], [], 0.2)[0]:
            packet = peer.recv(65535)
            assert packet, 'forwarding connection closed'
            received += packet
    assert probe.encode() in received, 'forwarder did not become ready'
    return received


def storage_test(prepare):
    target = Path('/var/log/journal').resolve()
    unit = run('systemd-escape', '--path', '--suffix=mount', str(target)).strip()
    override = Path('/etc/systemd/system') / (unit + '.d') / 'logd-journal-test.conf'
    failure = '[Mount]\nWhat=/proc/logd-journal-test-missing\n'
    mounted = subprocess.run(['mountpoint', '-q', str(target)]).returncode == 0
    if prepare:
        assert mounted, 'persistent journal must be working before the failure test'
        override.parent.mkdir(parents=True, exist_ok=True)
        with override.open('x') as output:
            output.write(failure)
        run('journalctl', '--sync')
        print('Reboot this disposable VM, then run --disposable --storage-recovery')
        return
    assert not mounted and override.read_text() == failure
    marker = 'runtime-fallback-' + uuid.uuid4().hex
    syslog(marker)
    wait_for(lambda: find(marker), marker)
    assert len(find(marker)) == 1
    assert marker in run('journalctl', '--directory=/run/log/journal', '-b',
                         '-t', 'logd-journal-test', '--no-pager')
    print('PASS: runtime logging after persistent mount failure')
    override.unlink()
    run('systemctl', 'daemon-reload')
    run('systemctl', 'reset-failed', unit, 'systemd-journal-flush.service')
    run('systemctl', 'start', unit, 'systemd-journal-flush.service')
    run('journalctl', '--sync')
    assert marker in run('journalctl', '--directory=/srv/journal', '-b',
                         '-t', 'logd-journal-test', '--no-pager')
    post = 'post-flush-' + uuid.uuid4().hex
    syslog(post)
    check_once(post)
    assert len(find(marker)) == 1, 'mount transition replayed history'
    print('PASS: persistent mount/flush resumes ingestion without replay')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable', action='store_true', required=True)
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument('--recovery', action='store_true')
    modes.add_argument('--prepare-storage-failure', action='store_true')
    modes.add_argument('--storage-recovery', action='store_true')
    parser.add_argument('--vacuum', action='store_true')
    args = parser.parse_args()
    assert os.geteuid() == 0 and Path('/etc/openwrt-systemd').is_file()
    mode = Path('/proc/1/comm').read_text().strip()
    token = 'journal-' + uuid.uuid4().hex
    marker = lambda name: token + '-' + name
    if args.recovery:
        assert mode == 'procd'
        assert '-J' not in Path('/proc/' + run('pidof', 'logd').strip() + '/cmdline').read_text().split('\0')
        syslog(marker('recovery'))
        wait_for(lambda: find(marker('recovery')), 'recovery syslog')
        run('ubus', 'call', 'system', 'board')
        print('PASS: stock logd syslog/ubus in procd recovery')
        return
    assert mode == 'systemd'
    if args.prepare_storage_failure or args.storage_recovery:
        storage_test(args.prepare_storage_failure)
        return
    assert os.readlink('/dev/log') == '/run/systemd/journal/dev-log'
    run('systemctl', 'is-active', 'systemd-journald-dev-log.socket')
    pid = run('pidof', 'logd').strip()
    assert '-J' in Path('/proc/' + pid + '/cmdline').read_text().split('\0')
    status = Path('/proc/' + pid + '/status').read_text()
    assert 'Uid:\t514\t514\t514\t514' in status, status
    groups = next(line for line in status.splitlines() if line.startswith('Groups:'))
    assert '190' in groups.split(), groups
    assert not any(os.readlink(fd) == '/proc/kmsg' for fd in Path('/proc/' + pid + '/fd').iterdir())
    syslog(marker('syslog'))
    legacy, stored = check_once(marker('syslog'))
    assert legacy['priority'] == 131 and legacy['source'] == 1, legacy
    assert legacy['time'] == int(stored['__REALTIME_TIMESTAMP']) // 1000, (legacy, stored)
    assert stored['SYSLOG_PID'] == '4242' and stored['_PID'] == str(os.getpid()), stored
    regex = '^journal-(?:[0-9a-f]{32})-syslog$'
    matched = run('journalctl', '-b', '-t', 'logd-journal-test', '--grep', regex,
                  '-o', 'cat', '--no-pager')
    assert marker('syslog') in matched
    print('PASS: journalctl PCRE2 regular-expression filtering')

    run('systemd-cat', '-t', 'logd-journal-native-test', '-p', 'warning', input=marker('stdout') + '\n')
    legacy, _ = check_once(marker('stdout'))
    assert legacy['priority'] & 7 == 4, legacy
    with open('/dev/kmsg', 'w') as output:
        output.write('<6>' + marker('kernel') + '\n')
    legacy, stored = check_once(marker('kernel'))
    assert legacy['source'] == 0 and stored['_TRANSPORT'] == 'kernel', (legacy, stored)

    run('ubus', 'call', 'log', 'write', json.dumps({'event': '<149>logd-journal-ubus: ' + marker('ubus')}))
    legacy, _ = check_once(marker('ubus'))
    assert legacy['priority'] == 149, legacy
    native(marker('binary'), marker('binary').encode() + b'\nline\x00tail')
    legacy, _ = check_once(marker('binary'))
    assert legacy['priority'] == 138 and ' line tail' in legacy['msg'], legacy
    native(marker('long'), marker('long').encode() + b'x' * 2048)
    legacy, stored = check_once(marker('long'))
    assert len(legacy['msg'].encode()) == 1023 and len(stored['MESSAGE']) > 2048, (legacy, stored)
    for index in range(256):
        syslog(marker('burst-') + str(index))
    wait_for(lambda: len(find(marker('burst-'))) == 256, 'batched journal ingestion')
    assert len(journal(marker('burst-'))) == 256
    native(marker('private'), uid=12345)
    private = wait_for(lambda: journal(marker('private')), 'private user journal')
    assert private[0]['_UID'] == '12345', private
    time.sleep(0.5)
    assert not find(marker('private')), 'private user journal exposed through logd'
    print('PASS: syslog/native/kernel/ubus mapping, timestamps, truncation, batching and user isolation')

    # Stop only compatibility logging; journald must retain and later seed its records.
    run('/etc/init.d/log', 'stop')
    syslog(marker('catchup'))
    wait_for(lambda: journal(marker('catchup')), 'logging while logd stopped')
    run('/etc/init.d/log', 'start')
    check_once(marker('catchup'))
    run('systemctl', 'restart', 'systemd-journald')
    syslog(marker('restart'))
    check_once(marker('restart'))
    run('journalctl', '--rotate')
    syslog(marker('rotate'))
    check_once(marker('rotate'))
    if args.vacuum:
        run('journalctl', '--rotate', '--vacuum-size=1')
        syslog(marker('vacuum'))
        check_once(marker('vacuum'))
    print('PASS: catch-up, journald restart and journal file changes')

    # Preserve exact UCI file bytes; never use a global uci revert/commit.
    system = Path('/etc/config/system')
    original = system.read_bytes()
    with tempfile.TemporaryDirectory(prefix='logd-journal-') as directory:
        logfile = Path(directory) / 'messages'
        try:
            for protocol in ('udp', 'tcp'):
                socktype = socket.SOCK_DGRAM if protocol == 'udp' else socket.SOCK_STREAM
                with socket.socket(socket.AF_INET, socktype) as receiver:
                    receiver.bind(('127.0.0.1', 0))
                    receiver.settimeout(15)
                    if protocol == 'tcp':
                        receiver.listen(1)
                    for option, value in {
                        'log_file': str(logfile), 'log_remote': '1', 'log_ip': '127.0.0.1',
                        'log_port': str(receiver.getsockname()[1]), 'log_proto': protocol,
                    }.items():
                        run('uci', 'set', 'system.@system[0].' + option + '=' + value)
                    run('uci', 'commit', 'system')
                    run('/etc/init.d/log', 'restart')
                    wait_for(entries, 'log object after UCI restart')
                    peer = receiver.accept()[0] if protocol == 'tcp' else receiver
                    try:
                        # Forwarding is best effort while its connection is starting.
                        # Establish an observed barrier rather than assuming a delay.
                        received = forwarder_ready(peer, marker('ready-' + protocol))
                        current = marker('remote-' + protocol)
                        syslog(current)
                        check_once(current)
                        deadline = time.monotonic() + 15
                        while current.encode() not in received and time.monotonic() < deadline:
                            if select.select([peer], [], [], 0.2)[0]:
                                received += peer.recv(65535)
                        assert received.count(current.encode()) == 1, received
                        assert marker('catchup').encode() not in received, received
                        wait_for(lambda: logfile.exists() and current in logfile.read_text(), 'file forwarding')
                        assert logfile.read_text().count(current) == 1
                        assert marker('catchup') not in logfile.read_text(), 'history replayed to file logger'
                        # Keep forwarders alive while procd respawns only logd.
                        previous_pid = run('pidof', 'logd').strip()
                        os.kill(int(previous_pid), signal.SIGTERM)
                        wait_for(lambda: (current_pid := logd_pid()) and current_pid != previous_pid,
                                 'procd respawn', seconds=15)
                        wait_for(entries, 'log object after respawn')
                        received = forwarder_ready(peer, marker('ready-resumed-' + protocol), received)
                        resumed = marker('resumed-' + protocol)
                        syslog(resumed)
                        check_once(resumed)
                        deadline = time.monotonic() + 15
                        while resumed.encode() not in received and time.monotonic() < deadline:
                            if select.select([peer], [], [], 0.2)[0]:
                                received += peer.recv(65535)
                        assert received.count(resumed.encode()) == 1, (protocol, received)
                        assert received.count(current.encode()) == 1, 'history replayed after respawn'
                        wait_for(lambda: resumed in logfile.read_text(), 'file logger after respawn')
                        assert logfile.read_text().count(current) == 1
                    finally:
                        if peer is not receiver:
                            peer.close()
            print('PASS: UCI file/UDP/TCP forwarding and logd respawn without history replay')
            run('uci', 'set', 'system.@system[0].log_buffer_size=1')
            run('uci', 'commit', 'system')
            run('/etc/init.d/log', 'restart')
            wait_for(entries, '1 KiB compatibility buffer')
            pid = run('pidof', 'logd').strip()
            native(marker('tiny-large'), marker('tiny-large').encode() + b'x' * 2048)
            wait_for(lambda: journal(marker('tiny-large')), 'full message in journal with tiny ring')
            time.sleep(0.5)
            assert run('pidof', 'logd').strip() == pid, 'oversized record crashed tiny ring'
            assert not find(marker('tiny-large'))
            syslog(marker('tiny-seed'))
            check_once(marker('tiny-seed'))
            run('/etc/init.d/log', 'restart')
            wait_for(lambda: find(marker('tiny-seed')), 'seeding a small buffer after restart')
            print('PASS: bounded 1 KiB ring and startup seeding')
        finally:
            system.write_bytes(original)
            run('/etc/init.d/log', 'restart')


if __name__ == '__main__':
    main()
