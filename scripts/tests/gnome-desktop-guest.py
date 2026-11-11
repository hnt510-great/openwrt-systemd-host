#!/usr/bin/env python3
"""Record runtime session evidence inside the disposable GNOME guest.

Run as root after provisioning the test account. This checks session and
listener prerequisites; client input, media and clipboard acceptance are
separate tests.
"""
import argparse
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--user', required=True)
    parser.add_argument('--lan-address', required=True)
    parser.add_argument('--rdp-port', type=int, default=3389)
    parser.add_argument('--sunshine-port', type=int, default=48989)
    args = parser.parse_args()
    account = pwd.getpwnam(args.user)
    if os.getuid() != 0 or account.pw_uid < 1000:
        raise SystemExit('Run as root with an ordinary test account')
    env = dict(os.environ, HOME=account.pw_dir, USER=account.pw_name,
               XDG_RUNTIME_DIR=f'/run/user/{account.pw_uid}',
               DBUS_SESSION_BUS_ADDRESS=f'unix:path=/run/user/{account.pw_uid}/bus')
    identity = dict(user=account.pw_uid, group=account.pw_gid,
                    extra_groups=os.getgrouplist(account.pw_name, account.pw_gid), env=env)
    failures = []

    def run(command, user=False):
        result = subprocess.run(command, capture_output=True, text=True, timeout=20,
                                **(identity if user else {}))
        if result.returncode:
            failures.append(f'{command[0]} {command[1]} failed ({result.returncode})')
        return result.stdout.strip()

    def properties(command, user=False):
        return dict(line.split('=', 1) for line in run(command, user).splitlines() if '=' in line)

    sessions = []
    for line in run(['loginctl', 'list-sessions', '--no-legend', '--no-pager']).splitlines():
        session = properties(['loginctl', 'show-session', line.split()[0],
                              *[arg for name in ['Id', 'User', 'Name', 'Type', 'Class',
                                                 'Active', 'Seat', 'VTNr', 'Service', 'Leader']
                                for arg in ['-p', name]]])
        if session.get('User') == str(account.pw_uid):
            sessions.append(session)
    desktop_sessions = [s for s in sessions if s.get('Service') == 'openwrt-desktop']
    if len(desktop_sessions) != 1 or desktop_sessions[0].get('Type') != 'wayland':
        failures.append('Expected one PAM/logind Wayland desktop session')
    system_units = {}
    for unit in ['openwrt-procd.service', 'systemd-logind.service',
                 'systemd-udevd.service', 'openwrt-desktop.service',
                 'accounts-daemon.service', 'upower.service', 'colord.service',
                 'rtkit-daemon.service']:
        state = properties(['systemctl', 'show', unit, '-p', 'LoadState,ActiveState,MainPID'])
        system_units[unit] = state
        if state.get('LoadState') != 'loaded':
            failures.append(f'{unit} is missing from the runtime image')
        if unit.startswith(('openwrt-', 'systemd-')) and state.get('ActiveState') != 'active':
            failures.append(f'{unit} is not active')
    units = {}
    for unit in ['org.gnome.Shell@user.service', 'gnome-remote-desktop.service',
                 'sunshine.service', 'openwrt-fcitx5.service']:
        state = properties(['systemctl', '--user', 'show', unit,
                            '-p', 'ActiveState,SubState,MainPID'], user=True)
        units[unit] = state
        if state.get('ActiveState') != 'active':
            failures.append(f'{unit} is not active')
        pid = int(state.get('MainPID', '0'))
        if pid and Path(f'/proc/{pid}').stat().st_uid != account.pw_uid:
            failures.append(f'{unit} is not owned by the desktop user')
    kms_mode = subprocess.run(['uci', '-q', 'get', 'desktop.main.kms_scheduling'],
                              capture_output=True, text=True).stdout.strip() or 'high-priority'
    kms_threads = []
    shell_pid = int(units['org.gnome.Shell@user.service'].get('MainPID', '0'))
    for task in Path(f'/proc/{shell_pid}/task').glob('*') if shell_pid else []:
        try:
            if (task / 'comm').read_text().strip() != 'KMS thread':
                continue
            fields = (task / 'stat').read_text().rsplit(')', 1)[1].split()
            tid = int(task.name)
            kms_threads.append(dict(tid=tid, nice=int(fields[16]), policy=int(fields[38]),
                                    rtprio=int(fields[37])))
        except (OSError, ValueError, IndexError):
            continue
    if len(kms_threads) != 1:
        failures.append('Expected one gnome-shell KMS thread')
    for thread in kms_threads:
        realtime = thread['policy'] in (os.SCHED_FIFO, os.SCHED_RR)
        if kms_mode == 'realtime' and not realtime:
            failures.append('KMS thread is not realtime with kms_scheduling=realtime')
        if kms_mode == 'high-priority' and (realtime or thread['nice'] >= 0):
            failures.append('KMS thread was not raised to a negative nice level by RealtimeKit')
    journal = run(['journalctl', '-b', f'_UID={account.pw_uid}', '-o', 'cat', '--no-pager'])
    if kms_mode != 'normal' and "Failed to make thread 'KMS thread'" in journal:
        failures.append('gnome-shell could not raise the KMS thread priority')
    locked = run(['gdbus', 'call', '--session', '--dest', 'org.freedesktop.secrets',
                  '--object-path', '/org/freedesktop/secrets/aliases/default', '--method',
                  'org.freedesktop.DBus.Properties.Get',
                  'org.freedesktop.Secret.Collection', 'Locked'], user=True)
    if locked != '(<false>,)':
        failures.append('Login keyring is unavailable or locked')
    monitors = run(['gdbus', 'call', '--session', '--dest', 'org.gnome.Mutter.DisplayConfig',
                    '--object-path', '/org/gnome/Mutter/DisplayConfig', '--method',
                    'org.gnome.Mutter.DisplayConfig.GetCurrentState'], user=True)
    listeners = run(['ss', '-ltnH']).splitlines()
    bindings = [line.split()[3] for line in listeners]
    for port in [args.rdp_port, args.sunshine_port]:
        endpoint = f'{args.lan_address}:{port}'
        actual = [binding for binding in bindings if binding.rsplit(':', 1)[-1] == str(port)]
        if actual != [endpoint]:
            failures.append(f'Port {port} must listen only on {endpoint}')
    result = dict(user=args.user, uid=account.pw_uid, sessions=sessions, units=units,
                  system_units=system_units, kms_scheduling=kms_mode, kms_threads=kms_threads,
                  keyring_locked=locked, monitor_state=monitors, tcp_bindings=bindings,
                  meminfo=Path('/proc/meminfo').read_text(), failures=failures)
    print(json.dumps(result, indent=2))
    return bool(failures)


if __name__ == '__main__':
    sys.exit(main())
