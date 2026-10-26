#!/usr/bin/env python3
"""Test staged target IME binaries over NLA RDP in an isolated bubblewrap namespace.

Requires Linux x86_64, bwrap, host FreeRDP 3 client libraries, GCC, and OpenSSL.
Build openwrt-desktop-ime first. Uses a temporary identity and network namespace.
"""
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
TESTS = ROOT / 'scripts/tests'
STAGING = ROOT / 'staging_dir/target-x86_64_glibc'
TARGET = STAGING / 'root-x86-systemd'
HOST_LIB = Path('/usr/lib/x86_64-linux-gnu')


def run(*args, **kwargs):
    return subprocess.run(*args, check=True, **kwargs)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'bin/validation/desktop-ime')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if os.getuid() < 1000:
        raise SystemExit('Run as an ordinary build user (uid >= 1000).')
    version = re.search(r'^CONFIG_GCC_VERSION="([^"]+)"', (ROOT / '.config').read_text(), re.M)[1]
    compiler = ROOT / f'staging_dir/toolchain-x86_64_gcc-{version}_glibc/bin/x86_64-openwrt-linux-gnu-gcc'
    env = dict(os.environ, STAGING_DIR=str(STAGING), PKG_CONFIG_LIBDIR=str(STAGING / 'usr/lib/pkgconfig'),
               PKG_CONFIG_SYSROOT_DIR=str(STAGING))
    with tempfile.TemporaryDirectory(prefix='openwrt-desktop-ime-') as directory:
        work = Path(directory)
        work.chmod(0o755)
        flags = subprocess.check_output(['pkg-config', '--cflags', '--libs', 'gtk+-3.0'], env=env, text=True).split()
        run([str(compiler), str(TESTS / 'desktop-ime-entry.c'), '-o', str(work / 'entry'), *flags,
             '-Wl,-rpath-link,' + str(STAGING / 'usr/lib')], env=env)
        run(['gcc', '-Wno-deprecated-declarations', '-I' + str(STAGING / 'usr/include/freerdp3'),
             '-I' + str(STAGING / 'usr/include/winpr3'), str(TESTS / 'desktop-ime-rdp.c'), '-o', str(work / 'rdp-full'),
             *[str(HOST_LIB / name) for name in ['libfreerdp-client3.so.3', 'libfreerdp3.so.3', 'libwinpr3.so.3']]])
        (work / 'bin').mkdir()
        # Staging roots have not yet had package alternatives installed.
        coreutils = sorted((ROOT / 'build_dir/target-x86_64_glibc').glob('coreutils-*/ipkg-install/usr/bin'))[-1]
        for name in ['mkdir', 'chmod', 'sleep', 'cat', 'cp', 'ln']:
            shutil.copy2(coreutils / name, work / 'bin' / name)
        (work / 'hostusr').mkdir()
        (work / 'passwd').write_text(f'root:x:0:0:root:/root:/bin/sh\nime:x:{os.getuid()}:{os.getgid()}:IME test:/tmp/home:/bin/sh\n')
        (work / 'group').write_text(f'root:x:0:\nime:x:{os.getgid()}:\n')
        with (work / 'cert.log').open('w') as log:
            run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-keyout', str(work / 'rdp.key'),
                 '-out', str(work / 'rdp.crt'), '-days', '1', '-subj', '/CN=localhost'], stdout=log, stderr=log)
        (work / 'entry-start').write_text('#!/bin/sh\nWAYLAND_DEBUG=1 exec /mnt/entry 2>/mnt/entry-wayland.log\n')
        (work / 'entry-start').chmod(0o755)
        (work / 'weston.ini').write_text('''[core]
shell=desktop-shell.so
idle-time=0
[input-method]
path=/usr/libexec/desktop-ime-session
[autolaunch]
path=/mnt/entry-start
watch=false
[output]
name=rdp-0
mode=800x600
[rdp]
address=127.0.0.1
port=33991
tls-key=/mnt/rdp.key
tls-cert=/mnt/rdp.crt
nla-ntlm-db=/mnt/test.sam
''')
        (work / 'run.sh').write_text('''#!/bin/sh
set -eu
export PATH=/mnt/bin:$PATH
mkdir -p /tmp/runtime /tmp/home
chmod 700 /tmp/runtime
export XDG_RUNTIME_DIR=/tmp/runtime HOME=/tmp/home XDG_CONFIG_HOME=/tmp/home/.config
export WAYLAND_DISPLAY=wayland-ime GTK_IM_MODULE=fcitx GTK_IM_MODULE_FILE=/usr/share/fcitx5-gtk/immodules.cache
printf '%s\\n' ime-test-only | winpr-hash -u ime --password-stdin -f sam > /mnt/test.sam
export DBUS_SESSION_BUS_ADDRESS=$(dbus-daemon --session --fork --print-address)
weston --debug --backends=rdp --renderer=pixman --width=800 --height=600 --socket=wayland-ime --config=/mnt/weston.ini > /mnt/weston.log 2>&1 &
weston_pid=$!
trap 'kill "$weston_pid" 2>/dev/null || :' EXIT
sleep 4
OPENSSL_MODULES=/mnt/hostusr/lib/x86_64-linux-gnu/ossl-modules /mnt/hostusr/lib/x86_64-linux-gnu/ld-linux-x86-64.so.2 --library-path /mnt/hostusr/lib/x86_64-linux-gnu /mnt/rdp-full > /mnt/rdp-client.log 2>&1
cp -r /tmp/home/.config/fcitx5 /mnt/runtime-profile
''')
        cmd = ['bwrap', '--unshare-all', '--die-with-parent', '--ro-bind', str(TARGET), '/', '--dev', '/dev',
               '--proc', '/proc', '--tmpfs', '/tmp', '--tmpfs', '/run', '--bind', str(work), '/mnt',
               '--ro-bind', '/usr', '/mnt/hostusr', '--ro-bind', str(work / 'passwd'), '/etc/passwd',
               '--ro-bind', str(work / 'group'), '/etc/group', '--clearenv', '--setenv', 'PATH',
               '/usr/sbin:/usr/bin:/sbin:/bin', '--setenv', 'USER', 'ime', '--setenv', 'LANG', 'C',
               '/bin/sh', '/mnt/run.sh']
        try:
            with (work / 'acceptance.log').open('w') as log:
                run(cmd, stdout=log, stderr=log, timeout=60)
            assert (work / 'state1').read_text().strip() == '2', 'Pinyin did not activate'
            assert (work / 'after-commit').read_text() == '你好', 'Pinyin commit mismatch'
            assert (work / 'state2').read_text().strip() == '1', 'Pinyin did not deactivate'
            assert (work / 'entry.txt').read_text() == '你好abc', 'English input mismatch'
            assert list(work.glob('wayland-screenshot-*.png')), 'Candidate screenshot missing'
            (output / 'result.json').write_text(json.dumps({'result': 'pass', 'text': '你好abc',
                'pinyin_state': 2, 'english_state': 1, 'environment': 'isolated target userspace on host kernel'},
                ensure_ascii=False, indent=2) + '\n')
        finally:
            # Retain evidence, never temporary private keys, SAM data, or credentials.
            for pattern in ['*.log', 'wayland-screenshot-*.png', 'entry.txt', 'after-commit', 'state1', 'state2']:
                for path in work.glob(pattern):
                    shutil.copy2(path, output / path.name)
    print(f'PASS: RDP Pinyin commit and English toggle; evidence: {output}')


if __name__ == '__main__':
    main()
