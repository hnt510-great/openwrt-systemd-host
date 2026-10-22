#!/usr/bin/env python3
"""Live replacement, ownership, queue and RPC checks in a disposable VM only."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import shlex
import subprocess
import re
import tarfile
import time


def run(*args, ok=(0,), timeout=90):
    p = subprocess.run(args, text=True, capture_output=True, timeout=timeout)
    if p.returncode not in ok:
        raise AssertionError(f'{args}: {p.returncode}\n{p.stdout}\n{p.stderr}')
    return p


def wait(test, label, timeout=90):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        if test():
            return
        time.sleep(.2)
    raise AssertionError('Timeout: ' + label)


def report():
    return json.loads(run('needrestart', '--json', ok=(0, 2)).stdout)


def subject(data, name):
    return next((s for s in data['services'] if s['name'] == name), None)


def replace(source, destination):
    tmp = destination.with_suffix('.new')
    shutil.copy2(source, tmp)
    tmp.replace(destination)


def container_checks(root, network_backend='slirp4netns'):
    image = 'localhost/needrestart-fixture:latest'
    image_root = root / 'image-root'
    for directory in ('bin', 'tmp', 'proc', 'sys', 'dev', 'etc', 'root'):
        (image_root / directory).mkdir(parents=True, exist_ok=True)
    (image_root / 'tmp').chmod(0o1777)
    binary = shutil.which('sleep')
    shutil.copy2(binary, image_root / 'bin/sleep')
    for name in set(re.findall(r'/[^\s()]+', run('ldd', binary).stdout)):
        source = Path(name)
        if source.is_file():
            dest = image_root / name.lstrip('/')
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    (image_root / 'etc/passwd').write_text('root:x:0:0:root:/root:/bin/sleep\n')
    (image_root / 'etc/group').write_text('root:x:0:\n')
    archive = root / 'container.tar'

    def tar(version):
        (image_root / 'etc/fixture-version').write_text(version)
        with tarfile.open(archive, 'w') as f:
            for p in image_root.iterdir():
                f.add(p, arcname=p.name)
        archive.chmod(0o644)

    user = 'needrestart-test'
    if subprocess.run(['id', user], capture_output=True).returncode:
        run('useradd', '-m', '-s', '/bin/sh', user)
    run('podman-rootless-setup', user)
    uid = int(run('id', '-u', user).stdout)
    wait(lambda: Path(f'/run/user/{uid}/bus').exists(), 'rootless user manager')

    def as_user(*args, **kwargs):
        command = ['env', 'HOME=/home/' + user, f'XDG_RUNTIME_DIR=/run/user/{uid}',
                   f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', *args]
        return run('su', '-s', '/bin/sh', user, '-c', shlex.join(command), **kwargs)

    tar('one')
    for invoke in (run, as_user):
        invoke('podman', 'import', str(archive), image)
    container_ids = []
    split_unit = 'needrestart-split-fixture-' + str(os.getpid())
    try:
        for label, invoke in [('rootful', run), ('rootless', as_user),
                              ('rootless-split', as_user)]:
            directory = root / label
            directory.mkdir()
            shutil.copy2(binary, directory / 'worker')
            argv = ['podman', 'run', '-d', '--name', 'needrestart-' + label,
                    '--network=none', '-v', str(directory) + ':/fixtures:ro']
            if label == 'rootless-split':
                argv[argv.index('--network=none')] = '--network=' + network_backend
                argv += ['--cgroups=split']
                as_user('systemd-run', '--user', '--collect', '--unit=' + split_unit,
                        '--property=Type=oneshot', '--property=RemainAfterExit=yes',
                        '--property=Delegate=yes', '/usr/bin/' + argv[0],
                        *argv[1:], image, '/fixtures/worker', '600')
                wait(lambda: as_user('podman', 'container', 'exists',
                                     'needrestart-' + label, ok=(0, 1)).returncode == 0,
                     'rootless split container')
                result = as_user('podman', 'inspect', '--format', '{{.Id}}',
                                 'needrestart-' + label)
                pid = as_user('podman', 'inspect', '--format', '{{.State.Pid}}',
                              'needrestart-' + label).stdout.strip()
                assert '/libpod-payload-' in Path(f'/proc/{pid}/cgroup').read_text()
                helpers = []
                for proc in Path('/proc').iterdir():
                    try:
                        if (proc.name.isdecimal() and
                            (proc / 'comm').read_text().strip() in
                            ('slirp4netns', 'pasta', 'passt', 'pasta.avx2', 'passt.avx2') and
                            '/' + split_unit + '.service/runtime' in (proc / 'cgroup').read_text()):
                            helpers.append(proc.name)
                    except OSError:
                        pass
                assert helpers, 'split container did not exercise the sandboxed network helper'
            else:
                result = invoke(*argv, image, '/fixtures/worker', '600')
            container_ids.append(result.stdout.strip())
        first = report()
        assert not first['warnings'], first['warnings']
        # Probe children can exit while the next probe is waiting. Exercise
        # repeated untraced scans to catch false denials after SIGCHLD/EINTR.
        for _ in range(5):
            repeated = report()
            assert not repeated['warnings'], repeated['warnings']
        for cid in container_ids:
            c = next(c for c in first['containers'] if c['id'] == cid)
            assert c['image_status'] == 'current', c
        tar('two')
        run('podman', 'import', str(archive), image)
        second = report()
        rootful = next(c for c in second['containers'] if c['id'] == container_ids[0])
        rootless = next(c for c in second['containers'] if c['id'] == container_ids[1])
        assert rootful['image_status'] == 'changed', rootful
        assert rootless['image_status'] == 'current', rootless
        assert rootless['uid'] == uid
        for label in ('rootful', 'rootless', 'rootless-split'):
            replace(shutil.which('true'), root / label / 'worker')
        stale = report()
        for cid in container_ids:
            found = subject(stale, cid)
            assert found and found['kind'] == 'container', (cid, stale)
            assert any(f['path'] == '/fixtures/worker' for p in found['processes'] for f in p['files'])
        print('PASS: rootful/rootless stale container code, local-image changes and separate user stores', flush=True)
    finally:
        run('podman', 'rm', '-f', 'needrestart-rootful', ok=(0, 1))
        as_user('podman', 'rm', '-f', 'needrestart-rootless', ok=(0, 1))
        as_user('podman', 'rm', '-f', 'needrestart-rootless-split', ok=(0, 1))
        as_user('systemctl', '--user', 'stop', split_unit + '.service', ok=(0, 5))


def browser_checks():
    user = 'needrestart-test'
    uid = int(run('id', '-u', user).stdout)
    unit = 'needrestart-firefox-' + str(os.getpid())
    profile = '/tmp/' + unit

    def as_user(*args, **kwargs):
        argv = ['env', 'HOME=/home/' + user, f'XDG_RUNTIME_DIR=/run/user/{uid}',
                f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', *args]
        return run('su', '-s', '/bin/sh', user, '-c', shlex.join(argv), **kwargs)

    def children():
        result = []
        for proc in Path('/proc').iterdir():
            try:
                if (proc.name.isdecimal() and '/' + unit + '.service' in
                    (proc / 'cgroup').read_text() and
                    re.fullmatch(r'/proc/[0-9]+/fdinfo', os.readlink(proc / 'root'))):
                    result.append(int(proc.name))
            except OSError:
                pass
        return result

    as_user('mkdir', '-m', '700', profile)
    try:
        as_user('systemd-run', '--user', '--collect', '--unit=' + unit,
                '/usr/bin/firefox-esr', '--headless', '--no-remote', '--profile', profile,
                'data:text/html,<title>needrestart fixture</title>Browser sandbox fixture')
        wait(lambda: len(children()) > 0, 'real Firefox proc-fdinfo sandbox children', timeout=50)
        for _ in range(3):
            pids = children()
            r = report()
            assert r['complete'] and not r['warnings'], r
            assert not any(s['kind'] == 'isolated' and
                           any(p['pid'] in pids for p in s['processes']) for s in r['services'])
        print('PASS: real sandboxed Firefox children inspected without disabling sandboxing', flush=True)
    finally:
        as_user('systemctl', '--user', 'stop', unit + '.service', ok=(0, 5))
        shutil.rmtree(profile, ignore_errors=True)


def flatpak_checks(root, fixtures):
    user = 'needrestart-test'
    uid = int(run('id', '-u', user).stdout)
    app = 'org.openwrt.NeedrestartTest'
    runtime = 'org.openwrt.NeedrestartRuntime'
    repo = root / 'flatpak-repo'
    build = root / 'flatpak-app'
    platform = root / 'flatpak-runtime'
    remote = 'needrestart-fixture'
    for p in (build / 'files/bin', build / 'export', platform / 'usr/share', platform / 'files'):
        p.mkdir(parents=True)
    shutil.copy2(fixtures / 'flatpak-worker', build / 'files/bin/probe')
    (build / 'metadata').write_text(f'[Application]\nname={app}\n'
        f'runtime={runtime}/x86_64/1.0\nsdk={runtime}/x86_64/1.0\ncommand=probe\n')
    (platform / 'metadata').write_text(f'[Runtime]\nname={runtime}\n')
    (platform / 'usr/share/fixture').write_text('minimal offline runtime\n')

    def as_user(*args, **kwargs):
        argv = ['env', 'HOME=/home/' + user, f'XDG_RUNTIME_DIR=/run/user/{uid}',
                f'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/{uid}/bus', *args]
        return run('su', '-s', '/bin/sh', user, '-c', shlex.join(argv), **kwargs)

    def exported():
        run('flatpak', 'build-export', '--arch=x86_64', str(repo), str(build), 'stable')

    def application(r):
        return next((a for a in r.get('applications', []) if a['name'] == app), None)

    run('flatpak', 'build-export', '--runtime', '--arch=x86_64', str(repo), str(platform), '1.0')
    exported()
    as_user('flatpak', 'remote-add', '--user', '--no-gpg-verify', remote, repo.as_uri())
    try:
        for ref in (f'runtime/{runtime}/x86_64/1.0', f'app/{app}/x86_64/stable'):
            as_user('flatpak', 'install', '--user', '--assumeyes', '--no-deps', remote, ref)
        as_user('systemd-run', '--user', '--collect', '--unit=needrestart-flatpak-fixture',
                '/usr/bin/flatpak', 'run', '--user', app)
        wait(lambda: application(report()) is not None, 'real Flatpak instance', timeout=50)
        current = report()
        assert current['complete'] and not current['warnings'], current
        assert application(current)['deployment_status'] == 'current', current
        (build / 'files/share').mkdir(exist_ok=True)
        (build / 'files/share/version').write_text('new local deployment\n')
        exported()
        as_user('flatpak', 'update', '--user', '--assumeyes', '--no-deps', app)
        changed = report()
        assert changed['complete'] and not changed['warnings'], changed
        assert application(changed)['deployment_status'] == 'changed', changed
        s = subject(changed, app)
        assert s and s['kind'] == 'flatpak' and 'Close and relaunch' in s['recommended_action'], changed
        print('PASS: real offline Flatpak identity, current deployment and update/relaunch advice', flush=True)
    finally:
        as_user('flatpak', 'kill', app, ok=(0, 1))
        as_user('systemctl', '--user', 'stop', 'needrestart-flatpak-fixture.service', ok=(0, 5))
        as_user('flatpak', 'uninstall', '--user', '--assumeyes', app, runtime, ok=(0, 1))
        as_user('flatpak', 'remote-delete', '--user', '--force', remote, ok=(0, 1))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--disposable-vm', action='store_true', required=True)
    parser.add_argument('--fixtures', type=Path, required=True,
                        help='Directory containing cross-built dl-worker, libprobe-v1.so and libprobe-v2.so')
    parser.add_argument('--containers', action='store_true', help='Also exercise rootful/rootless Podman')
    parser.add_argument('--network-backend', choices=('slirp4netns', 'pasta'),
                        default='slirp4netns', help='Split-container network helper to validate')
    parser.add_argument('--browser', action='store_true',
                        help='Also validate real Firefox proc-fdinfo sandbox children (requires --containers)')
    parser.add_argument('--flatpak', action='store_true',
                        help='Build and exercise an offline Flatpak (requires --containers)')
    args = parser.parse_args()
    assert os.geteuid() == 0 and Path('/run/systemd/system').is_dir()
    root = Path('/tmp/needrestart-live')
    root.mkdir(exist_ok=False)
    init = Path('/etc/init.d/needrestart-fixture')
    try:
        native = root / 'native'
        procd = root / 'procd'
        library = root / 'libprobe.so'
        for file in (native, procd):
            shutil.copy2(shutil.which('sleep'), file)
        with native.open('r+b') as file:
            file.truncate(300 * 1024 * 1024)
        shutil.copy2(args.fixtures / 'libprobe-v1.so', library)
        run('systemd-run', '--collect', '--unit=needrestart-native', '--', str(native), '600')
        run('systemd-run', '--collect', '--unit=needrestart-library', '--', str(args.fixtures / 'dl-worker'), str(library))
        init.write_text('''#!/bin/sh /etc/rc.common
USE_PROCD=1
start_service() {
    procd_open_instance main
    procd_set_param command /tmp/needrestart-live/procd 600
    procd_close_instance
}
''')
        init.chmod(0o755)
        run(str(init), 'start')
        time.sleep(1)
        initial = report()
        assert not subject(initial, 'needrestart-native.service')
        assert not subject(initial, 'needrestart-library.service')
        assert not subject(initial, 'needrestart-fixture')
        replace(native, native)
        identical = report()
        assert not subject(identical, 'needrestart-native.service'), identical
        print('PASS: identical replacement of a 300 MiB executable is not outdated', flush=True)
        with native.open('r+b') as file:
            file.seek(290 * 1024 * 1024)
            file.write(b'changed-code-near-end')
        late_change = report()
        assert subject(late_change, 'needrestart-native.service'), late_change
        run('systemctl', 'restart', 'needrestart-native.service')
        print('PASS: a difference near the end of a 300 MiB executable is detected', flush=True)
        state_file = Path('/etc/openwrt-kernel/state.json')
        original_state = state_file.read_bytes()
        try:
            large_state = json.loads(original_state)
            large_state['needrestart_test_padding'] = 'x' * (5 * 1024 * 1024)
            state_file.write_text(json.dumps(large_state))
            large_report = report()
            assert large_report['kernel']['status'] == initial['kernel']['status']
            assert not any('Kernel' in w for w in large_report['warnings'])
            print('PASS: kernel inventory larger than 4 MiB remains assessed', flush=True)
        finally:
            state_file.write_bytes(original_state)
        replace(shutil.which('true'), native)
        replace(shutil.which('true'), procd)
        replace(args.fixtures / 'libprobe-v2.so', library)
        stale = report()
        for name in ('needrestart-native.service', 'needrestart-library.service', 'needrestart-fixture'):
            found = subject(stale, name)
            assert found, (name, stale)
            assert any(f['reason'] == 'replaced' for p in found['processes'] for f in p['files'])
        assert subject(stale, 'needrestart-fixture')['kind'] == 'procd'
        assert subject(stale, 'needrestart-native.service')['kind'] == 'systemd'
        print('PASS: live executable/library replacement and native/procd ownership', flush=True)
        run('systemctl', 'restart', 'needrestart-native.service', 'needrestart-library.service')
        run(str(init), 'restart')
        refreshed = report()
        for name in ('needrestart-native.service', 'needrestart-library.service', 'needrestart-fixture'):
            assert not subject(refreshed, name), (name, refreshed)
        print('PASS: findings clear after manual owner-controlled restarts', flush=True)
        run('systemctl', 'start', 'openwrt-needrestart.path')
        pending = Path('/run/openwrt-needrestart/pending')
        cached = Path('/run/openwrt-needrestart/report.json')
        stamp = cached.stat().st_mtime_ns
        with Path('/lib/apk/db/lock').open() as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            run('/lib/apk/commit_hooks.d/90-needrestart', 'post-commit')
            assert pending.exists()
            time.sleep(1)
            assert cached.stat().st_mtime_ns == stamp, 'worker scanned before APK finished'
        wait(lambda: not pending.exists() and cached.stat().st_mtime_ns != stamp, 'post-APK scan')
        assert not Path('/run/openwrt-needrestart/running').exists()
        print('PASS: APK hook queues, waits for transaction lock release, publishes and acknowledges', flush=True)
        rpc = json.loads(run('ubus', 'call', 'luci.needrestart', 'status', '{}').stdout)
        assert rpc['report']['schema_version'] == 1
        assert not rpc.get('running') and not rpc.get('pending'), rpc
        assert json.loads(run('ubus', 'call', 'luci.needrestart', 'scan', '{}').stdout)['success']
        wait(lambda: not pending.exists(), 'RPC scan')
        print('PASS: LuCI RPC status and read-only scan queue', flush=True)
        if args.containers:
            container_checks(root, args.network_backend)
        if args.browser:
            assert args.containers, '--browser requires the prepared rootless test account'
            browser_checks()
        if args.flatpak:
            assert args.containers, '--flatpak requires the prepared rootless test account'
            flatpak_checks(root, args.fixtures)
        print(json.dumps({'coverage': refreshed['scan_status'], 'warnings': refreshed['warnings'],
                          'kernel': refreshed['kernel']['status']}, indent=2), flush=True)
    finally:
        for unit in ('needrestart-native.service', 'needrestart-library.service'):
            run('systemctl', 'stop', unit, ok=(0, 5))
        if init.exists():
            run(str(init), 'stop', ok=(0, 1))
            init.unlink()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == '__main__':
    main()
