#!/usr/bin/env python3
"""Cut an APK transaction off in a disposable VM and check boot-time recovery.

Boots an exact image through scripts/tests/kernel-upgrade/vm-console.py (qcow2
over the immutable raw image, isolated user networking) and serves the build's
signed package feeds on a read-only ext4 NVMe disk. Never touches the physical router.

Scenarios, in one boot sequence:
  caller   apk runs inside a KillMode=mixed service (as LuCI runs it inside
           rpcd); stopping that service must not kill it; ordinary reboot is
           refused while it commits.
  power    a large transaction is hard-reset (QMP system_reset) partway
           through; apk-resume.service must finish it offline before
           openwrt-services.service starts.
"""
import argparse
import gzip
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import time

TREE = Path(__file__).resolve().parents[2]
CONSOLE = TREE / 'scripts/tests/kernel-upgrade/vm-console.py'
FEEDS = TREE / 'bin/systemd/packages/x86_64'
# Core packages whose interruption is not the subject of this test.
SKIP_PREFIXES = ('kmod-', 'linux-image-', 'linux-headers-', 'kernel', 'libc', 'glibc', 'apk-',
                 'busybox', 'base-files', 'systemd', 'procd', 'ubus', 'libubox', 'ld-',
                 'openwrt-kernel-upgrade', 'apk-transaction-guard', 'grub2')


class VM:
    def __init__(self, raw, out):
        self.out = out
        # vm-console attaches out/extroot.qcow2 as an NVMe disk and only creates
        # it when missing; pre-build it as an ext4 copy of the signed feeds
        # (this kernel has no virtio 9p transport).
        out.mkdir(parents=True, exist_ok=True)
        disk = out / 'feeds.raw'
        subprocess.run(['truncate', '-s', '2G', str(disk)], check=True)
        subprocess.run(['mkfs.ext4', '-q', '-L', 'apkfeeds', '-d', str(FEEDS), str(disk)], check=True)
        subprocess.run(['qemu-img', 'convert', '-f', 'raw', '-O', 'qcow2', str(disk), str(out / 'extroot.qcow2')],
                       check=True)
        disk.unlink()
        self.process = subprocess.Popen(
            [sys.executable, str(CONSOLE), '--raw', str(raw), '--out', str(out)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
        self.reply()

    def reply(self):
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('VM console exited; see ' + str(self.out / 'serial.log'))
        return json.loads(line)

    def send(self, request):
        self.process.stdin.write(json.dumps(request) + '\n')
        self.process.stdin.flush()
        return self.reply()

    def run(self, command, timeout=120, check=True):
        result = self.send({'command': command, 'timeout': timeout})
        output = result['output'].replace('\r', '')
        if check and result['status'] != 0:
            raise RuntimeError(f'{command!r} failed ({result["status"]}):\n{output}')
        return result['status'], output

    def qmp(self, command):
        with socket.socket(socket.AF_UNIX) as sock:
            sock.connect(str(self.out / 'qmp.sock'))
            stream = sock.makefile('rw')
            json.loads(stream.readline())
            for request in ({'execute': 'qmp_capabilities'}, {'execute': command}):
                stream.write(json.dumps(request) + '\n')
                stream.flush()
                while True:
                    answer = json.loads(stream.readline())
                    if 'return' in answer or 'error' in answer:
                        break
            return answer

    def close(self):
        try:
            self.send({'quit': True})
        except Exception:
            pass
        self.process.wait(timeout=60)


def packages(manifest, count):
    sizes = {}
    for path in FEEDS.glob('*/*.apk'):
        sizes[path.name] = path.stat().st_size
    chosen = []
    for line in manifest.read_text().splitlines():
        name, _, version = line.partition(' - ')
        if name.startswith(SKIP_PREFIXES):
            continue
        size = sizes.get(f'{name}-{version}.apk')
        if size:
            chosen.append((size, name))
    chosen.sort(reverse=True)
    names = [name for _, name in chosen[:count]]
    if 'rpcd' not in names:
        names.append('rpcd')
    return names


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--image', type=Path, required=True, help='exact *-combined-efi.img.gz')
    parser.add_argument('--work-dir', type=Path, required=True, help='new empty directory')
    parser.add_argument('--count', type=int, default=80, help='packages to reinstall in the power-cut transaction')
    args = parser.parse_args()
    if args.work_dir.exists() and any(args.work_dir.iterdir()):
        parser.error('--work-dir must be new or empty')
    args.work_dir.mkdir(parents=True, exist_ok=True)
    raw = args.work_dir / 'image.raw'
    with gzip.open(args.image, 'rb') as source, raw.open('wb') as target:
        shutil.copyfileobj(source, target)
    raw.chmod(0o444)
    manifest = args.image.parent / 'openwrt-x86-64-generic.manifest'
    names = packages(manifest, args.count)
    results = {'image': str(args.image), 'packages': names, 'checks': {}}

    def check(name, passed, detail=''):
        results['checks'][name] = {'pass': bool(passed), 'detail': detail}
        print(('PASS ' if passed else 'FAIL ') + name + (': ' + detail if detail else ''), flush=True)

    vm = VM(raw, args.work_dir / 'vm')
    try:
        vm.run('mkdir -p /mnt/feeds && mount -o ro /dev/nvme0n1 /mnt/feeds')
        vm.run('for f in /mnt/feeds/*/packages.adb; do echo "$f"; done > /root/feeds.list; cat /root/feeds.list')
        apk = 'apk --repositories-file /root/feeds.list --no-network --no-cache --no-progress'
        _, version = vm.run('apk --version; ls /usr/lib/apk/commit_hooks.d/; systemctl is-enabled apk-resume.service')
        check('image carries apk r18 and the guard', '00-transaction-scope' in version and 'enabled' in version, version.strip())

        # --- caller: a KillMode=mixed service stops while its apk commits ------
        vm.run(f"systemd-run --unit=fake-rpcd -p KillMode=mixed -p TimeoutStopSec=5s /bin/sh -c "
               f"'{apk} add --force-reinstall firefox-esr-bin rpcd >/root/caller.log 2>&1; "
               f"echo exit=$? >>/root/caller.log'")
        apk_pid = ''
        for _ in range(300):
            status, out = vm.run('ls /lib/apk/db/transaction/journal 2>/dev/null && pgrep -x apk', check=False)
            if status == 0:
                apk_pid = out.split()[-1]
                break
            time.sleep(0.2)
        _, cgroup = vm.run(f'cat /proc/{apk_pid}/cgroup; COLUMNS=400 systemd-inhibit --list --no-pager --no-legend', check=False)
        check('apk moved into its own scope', f'apk-transaction-{apk_pid}.scope' in cgroup, cgroup.strip())
        check('shutdown block inhibitor held', 'Package transaction in progress' in cgroup)
        status, refused = vm.run('systemctl reboot 2>&1', check=False)
        check('systemctl reboot refused while committing', status != 0, refused.strip())
        vm.run('systemctl stop fake-rpcd', check=False)
        for _ in range(1200):
            if vm.run('pgrep -x apk >/dev/null', check=False)[0] != 0:
                break
            time.sleep(0.5)
        _, log = vm.run('cat /root/caller.log; ls /lib/apk/db/transaction 2>&1; apk-resume --status', check=False)
        check('apk survived its caller service stopping', 'OK:' in log and 'No interrupted' in log, log.strip()[-600:])

        # --- power: hard reset partway through a large transaction ------------
        audit = 'apk audit --system --packages -q 2>/dev/null | sort'
        _, before = vm.run(audit, timeout=900, check=False)
        command = f'{apk} add --force-reinstall {" ".join(names)}'
        vm.run(f"( {command} >/root/power.log 2>&1 & )")
        total, done = len(names), 0
        deadline = time.monotonic() + 900
        while time.monotonic() < deadline:
            _, out = vm.run("grep -c 'Reinstalling\\|Installing' /root/power.log; "
                            "test -f /lib/apk/db/transaction/journal && echo journal", check=False)
            lines = out.split()
            done = int(lines[0]) if lines and lines[0].isdigit() else 0
            if 'journal' in lines and done >= total // 3:
                break
            time.sleep(0.5)
        _, journal = vm.run('grep -c ^change /lib/apk/db/transaction/journal; '
                            'grep -E "^(payloads|attempt)" /lib/apk/db/transaction/journal', check=False)
        check('cut point reached with a journal', done >= total // 3 and 'payloads 1' in journal,
              f'{done}/{total} packages started; {journal.split()}')
        print(json.dumps(vm.qmp('system_reset')), flush=True)
        vm.send({'reconnect': True, 'timeout': 1800})
        state = ''
        for _ in range(360):
            _, state = vm.run('systemctl is-active apk-resume.service', check=False)
            if state.strip() not in ('activating', ''):
                break
            time.sleep(5)
        _, show = vm.run('systemctl show -p Result -p ExecMainStatus apk-resume.service')
        check('apk-resume.service succeeded', 'Result=success' in show and 'ExecMainStatus=0' in show, show.strip())
        _, resume_done = vm.run('systemctl show --value -p ExecMainExitTimestampMonotonic apk-resume.service')
        _, services_start = vm.run('systemctl show --value -p InactiveExitTimestampMonotonic openwrt-services.service')
        resume_done, services_start = int(resume_done.strip() or 0), int(services_start.strip() or 0)
        check('resume finished before openwrt-services started',
              resume_done and services_start and resume_done <= services_start,
              f'resume exited at {resume_done}us, services started at {services_start}us')
        _, log = vm.run('journalctl -b -u apk-resume.service --no-pager | tail -n 20', check=False)
        check('resume ran offline from the journal', 'offline from the journal' in log, log.strip()[-800:])
        status, status_out = vm.run('apk-resume --status', check=False)
        _, listing = vm.run('ls /lib/apk/db/transaction 2>&1', check=False)
        check('no journal remains', status == 0 and 'No such file' in listing, (status_out + listing).strip())
        _, after = vm.run(audit, timeout=900, check=False)
        problems = sorted((set(after.split()) - set(before.split())) & set(names))
        check('reinstalled packages match their installed checksums', not problems, ' '.join(problems))
        vm.run('mkdir -p /mnt/feeds && (mountpoint -q /mnt/feeds || mount -o ro /dev/nvme0n1 /mnt/feeds)')
        status, simulate = vm.run('apk --repositories-file /root/feeds.list --no-network --no-cache fix --simulate', check=False)
        check('apk fix finds nothing broken', status == 0 and 'Reinstalling' not in simulate, simulate.strip()[-400:])
        status, ok = vm.run('systemctl is-system-running; systemctl --failed --no-legend --no-pager', check=False)
        results['system_state'] = ok.strip()
        print(ok, flush=True)
    finally:
        vm.close()
        (args.work_dir / 'validation.json').write_text(json.dumps(results, indent=2) + '\n')
    failed = [name for name, check_result in results['checks'].items() if not check_result['pass']]
    print('FAILED: ' + ', '.join(failed) if failed else 'All checks passed', flush=True)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
