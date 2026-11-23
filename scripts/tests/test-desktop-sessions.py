#!/usr/bin/env python3
"""Test pluggable desktop sessions, active-session stop/switch, and desktop-ctl."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
FILES = ROOT / 'package/custom/openwrt-desktop/files'


def load_desktop_ctl():
    path = FILES / 'desktop-ctl'
    loader = importlib.machinery.SourceFileLoader('desktop_ctl_mod', str(path))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class DesktopSessionPluginsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.bin = self.path / 'bin'
        self.bin.mkdir()
        self.sessions_dir = self.path / 'sessions.d'
        self.sessions_dir.mkdir()
        self.run_dir = self.path / 'run-desktop'
        self.run_dir.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        HOME=str(self.path))

    def tool(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)
        return path

    def write_common(self, extra=''):
        src = (FILES / 'desktop-common.sh').read_text()
        src = src.replace(
            'DESKTOP_SESSIONS_DIR=/usr/libexec/openwrt-desktop/sessions.d',
            f'DESKTOP_SESSIONS_DIR={self.sessions_dir}')
        src = src.replace(
            'DESKTOP_SESSION_REQUIRE_ROOT=1',
            'DESKTOP_SESSION_REQUIRE_ROOT=0')
        path = self.path / 'desktop-common.sh'
        path.write_text(src + '\n' + extra)
        return path

    def write_dummy_plugin(self, exec_path, stop_record):
        (self.sessions_dir / 'dummy').write_text(
            'SESSION_ID="dummy"\n'
            'SESSION_TITLE="Dummy Wayland"\n'
            'SESSION_DESCRIPTION="Mock session for switcher tests"\n'
            f'SESSION_EXEC="{exec_path}"\n'
            'SESSION_SUPPORTS_RDP="0"\n'
            'SESSION_SUPPORTS_KMS_SCHEDULING="0"\n'
            'SESSION_UNSET_VARS="KDE_FULL_SESSION KDE_SESSION_VERSION"\n'
            'desktop_session_check() { [ -x "$SESSION_EXEC" ]; }\n'
            'desktop_session_exec() {\n'
            '\texport XDG_CURRENT_DESKTOP=DUMMY XDG_SESSION_DESKTOP=dummy DESKTOP_SESSION=dummy\n'
            '\texport XDG_SESSION_TYPE=wayland KDE_FULL_SESSION=true\n'
            '\tsystemctl --user import-environment XDG_CURRENT_DESKTOP XDG_SESSION_DESKTOP DESKTOP_SESSION XDG_SESSION_TYPE KDE_FULL_SESSION\n'
            '\texec "$SESSION_EXEC" --dummy\n'
            '}\n'
            f'desktop_session_stop() {{ printf "stopped-dummy\\n" >> "{stop_record}"; }}\n'
        )

    def test_session_switch_stops_old_active_session_and_cleans_env(self):
        gnome_bin = self.tool('gnome-session', 'exit 0')
        dummy_bin = self.tool(
            'dummy-session',
            "/usr/bin/python3 -c 'import json,os,sys; "
            'json.dump([sys.argv[1:], dict(os.environ)], open(os.environ["OUT"], "w"))\' "$@"')
        stop_log = self.path / 'stop.log'
        (self.sessions_dir / 'gnome').write_text(
            (FILES / 'sessions.d/gnome').read_text().replace('/usr/bin/gnome-session', str(gnome_bin)))
        self.write_dummy_plugin(dummy_bin, stop_log)

        common = self.write_common(
            'desktop_error() { printf "%s\\n" "$*" >&2; return 1; }\n'
            'desktop_validate_user() { DESKTOP_USER_UID=1000 DESKTOP_USER_HOME=/home/alice DESKTOP_USER_SHELL=/bin/sh; }\n'
            'desktop_lan_address() { echo 192.0.2.1; }\n'
            'desktop_select_output() { echo HDMI-A-1; }\n'
        )
        secret = self.path / '1000.keyring-passphrase.cred'
        secret.write_text('sealed')
        secret.chmod(0o600)

        user_stop = self.path / 'desktop-user-stop'
        user_stop.write_text(
            (FILES / 'desktop-user-stop').read_text().replace('/usr/libexec/desktop-common.sh', str(common)))
        user_stop.chmod(0o755)

        systemctl_log = self.path / 'systemctl.log'
        self.tool('logger', ':')
        self.tool('chown', ':')
        self.tool('stat', 'echo 0:600')
        self.tool('id', 'echo 1000')
        self.tool('loginctl', 'exit 0')
        self.tool('su', 'shift; shift; shift; cmd="$1"; sh -c "$cmd"')
        self.tool('uci', 'case "$*" in *desktop.main.user*) echo alice;; *desktop.main.session*) echo gnome;; *) exit 1;; esac')
        self.tool('systemctl', f'printf "%s\\n" "$*" >> "{systemctl_log}"; [ "$1" = is-active ] && exit 3 || exit 0')
        self.tool('systemd-run', f'printf "%s\\n" "$@" > "{self.path / "systemd-run.args"}"')

        init_src = (FILES / 'desktop.init').read_text()
        init_src = init_src.replace('/usr/libexec/desktop-common.sh', str(common))
        init_src = init_src.replace('/run/openwrt-desktop', str(self.run_dir))
        init_src = init_src.replace('"/etc/desktop/gnome/$DESKTOP_USER_UID.keyring-passphrase"', f'"{self.path / "1000.keyring-passphrase"}"')
        init_src = init_src.replace('/usr/libexec/desktop-user-stop', str(user_stop))
        init_src = init_src.replace('/dev/tty0', str(self.path / 'no-tty0'))
        init_file = self.path / 'desktop.init'
        init_file.write_text(init_src)

        harness = self.path / 'harness.sh'
        harness.write_text(
            'config_load() { :; }\n'
            'config_get_bool() { eval "$1=1"; }\n'
            'config_get() {\n'
            '\tcase "$3" in\n'
            '\t\tuser) eval "$1=alice" ;;\n'
            '\t\tsession) eval "$1=\\${TARGET_SESSION:-gnome}" ;;\n'
            '\t\t*) eval "$1=\\$4" ;;\n'
            '\tesac\n'
            '}\n'
            '. "$1"\n'
            '"$2"\n'
        )

        # Start dummy session -> active.env records dummy
        res = subprocess.run(['sh', str(harness), str(init_file), 'start_service'],
                             env=dict(self.env, TARGET_SESSION='dummy'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        active = (self.run_dir / 'active.env').read_text()
        self.assertIn('ACTIVE_SESSION=dummy\n', active)
        self.assertIn('--setenv=OPENWRT_DESKTOP_SESSION=dummy',
                      (self.path / 'systemd-run.args').read_text().splitlines())

        # Now UCI says 'gnome', but stop_service must stop the OLD active session ('dummy')!
        res = subprocess.run(['sh', str(harness), str(init_file), 'stop_service'],
                             env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('stopped-dummy', stop_log.read_text())
        self.assertFalse((self.run_dir / 'active.env').exists())

        # Verify desktop-session clears KDE_FULL_SESSION / MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY
        # collected across all plugins in sessions.d/
        bus = socket.socket(socket.AF_UNIX)
        self.addCleanup(bus.close)
        bus.bind(str(self.path / 'bus'))
        keyring = self.tool('keyring', ':')
        user_setup = self.tool('user-setup', ':')
        sess_src = (FILES / 'desktop-session').read_text()
        sess_src = sess_src.replace('/usr/libexec/desktop-common.sh', str(common))
        sess_src = sess_src.replace('/usr/libexec/desktop-keyring-unlock', str(keyring))
        sess_src = sess_src.replace('/usr/libexec/desktop-user-setup', str(user_setup))
        sess_file = self.path / 'desktop-session'
        sess_file.write_text(sess_src)
        systemctl_log.unlink(missing_ok=True)
        out = self.path / 'dummy-out.json'
        res = subprocess.run(
            ['sh', str(sess_file)],
            env=dict(self.env, XDG_RUNTIME_DIR=str(self.path),
                     OPENWRT_DESKTOP_SESSION='dummy', OUT=str(out),
                     MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY='realtime',
                     KDE_SESSION_VERSION='6'),
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        args, env_after = json.loads(out.read_text())
        self.assertEqual(args, ['--dummy'])
        self.assertEqual(env_after['XDG_CURRENT_DESKTOP'], 'DUMMY')
        self.assertNotIn('MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY', env_after)
        self.assertNotIn('KDE_SESSION_VERSION', env_after)
        unset_lines = [line for line in systemctl_log.read_text().splitlines()
                       if line.startswith('--user unset-environment ')]
        self.assertEqual(len(unset_lines), 1)
        self.assertIn('MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY', unset_lines[0])
        self.assertIn('KDE_FULL_SESSION', unset_lines[0])
        self.assertIn('KDE_SESSION_VERSION', unset_lines[0])

    def test_rejects_symlinks_and_invalid_ids(self):
        real = self.path / 'evil'
        real.write_text('SESSION_ID="evil"\n')
        (self.sessions_dir / 'evil').symlink_to(real)
        common = self.write_common('desktop_error() { printf "%s\\n" "$*" >&2; return 1; }\n')
        for bad in ('evil', '../gnome', 'bad;id', '-dash', 'a' * 33, ''):
            res = subprocess.run(
                ['sh', '-c', '. "$1"; desktop_load_session "$2"', 't', str(common), bad],
                capture_output=True, text=True)
            self.assertNotEqual(res.returncode, 0, bad)

    def test_desktop_ctl_status_drift_and_preflight(self):
        mod = load_desktop_ctl()
        mod.SESSIONS_DIR = self.sessions_dir
        mod.RUN_DIR = self.run_dir
        mod.SECRET_DIR = self.path / 'secrets'
        mod.SECRET_DIR.mkdir()
        mod.TLS_DIR = self.path / 'tls'
        mod.TLS_DIR.mkdir()
        mod.DRM_DIR = self.path / 'drm'
        mod.DRM_DIR.mkdir()
        mod.PASSWD_FILE = self.path / 'passwd'
        mod.REQUIRE_ROOT_PLUGIN = False

        gnome_bin = self.tool('gnome-session', 'exit 0')
        (self.sessions_dir / 'gnome').write_text(
            (FILES / 'sessions.d/gnome').read_text().replace('/usr/bin/gnome-session', str(gnome_bin)))
        (self.sessions_dir / 'plasma').write_text(
            'SESSION_ID="plasma"\nSESSION_TITLE="KDE Plasma"\n'
            'SESSION_EXEC="/nonexistent/startplasma-wayland"\n'
            'SESSION_SUPPORTS_RDP="0"\nSESSION_SUPPORTS_KMS_SCHEDULING="0"\n')
        # Symlink should be ignored
        (self.sessions_dir / 'link').symlink_to(self.sessions_dir / 'gnome')

        (mod.DRM_DIR / 'card0-HDMI-A-1').mkdir()
        (mod.DRM_DIR / 'card0-HDMI-A-1/status').write_text('connected\n')
        (mod.DRM_DIR / 'card0-DP-1').mkdir()
        (mod.DRM_DIR / 'card0-DP-1/status').write_text('disconnected\n')

        mod.PASSWD_FILE.write_text(f'alice:x:1000:1000::/home/alice:/bin/sh\n')
        cred = mod.SECRET_DIR / '1000.keyring-passphrase.cred'
        cred.write_text('SUPER_SECRET_BYTES_NEVER_LEAK')
        cred.chmod(0o600)
        (mod.TLS_DIR / 'alice.crt').write_text('cert')
        (mod.TLS_DIR / 'alice.key').write_text('key')
        (self.run_dir / '1000.env').write_text('OPENWRT_DESKTOP_LAN_ADDRESS=192.0.2.1\n')
        (self.run_dir / 'active.env').write_text(
            'ACTIVE_SESSION=gnome\nACTIVE_USER=alice\nACTIVE_KMS_SCHEDULING=high-priority\n'
            'ACTIVE_OUTPUT=auto\nACTIVE_MODE=preferred\n')

        uci_values = {
            'desktop.main.enabled': '1',
            'desktop.main.user': 'alice',
            'desktop.main.session': 'gnome',
            'desktop.main.kms_scheduling': 'realtime',
            'desktop.main.output': 'auto',
            'desktop.main.mode': 'preferred',
            'desktop.main.rdp_enabled': '1',
            'desktop.main.rdp_port': '3389',
        }
        init_calls = []

        def fake_run(argv, **kwargs):
            if argv[0] == 'uci' and argv[1] == '-q' and argv[2] == 'get':
                val = uci_values.get(argv[3], '')
                return subprocess.CompletedProcess(argv, 0 if val else 1, val + '\n' if val else '', '')
            if argv[0] == 'systemctl' and argv[1] == 'show':
                return subprocess.CompletedProcess(
                    argv, 0,
                    'ActiveState=active\nSubState=running\nMainPID=4242\nNRestarts=0\nActiveEnterTimestamp=Mon\n', '')
            if argv[0] == mod.INIT_SCRIPT:
                if argv[1] != 'enabled':
                    init_calls.append(argv[1])
                return subprocess.CompletedProcess(argv, 0, '', '')
            return subprocess.CompletedProcess(argv, 1, '', '')

        mod.run_cmd = fake_run
        st = mod.get_status()
        self.assertTrue(st['ok'])
        self.assertEqual(st['provisioned']['keyring_credential'], 'tpm2')
        self.assertNotIn('SUPER_SECRET_BYTES_NEVER_LEAK', json.dumps(st))
        self.assertEqual(st['outputs'], ['HDMI-A-1'])
        self.assertEqual([s['id'] for s in st['sessions']], ['gnome', 'plasma'])
        self.assertTrue(st['sessions'][0]['available'])
        self.assertFalse(st['sessions'][1]['available'])
        self.assertTrue(st['restart_required'])
        self.assertEqual(st['drifted_keys'], ['kms_scheduling'])

        # Switching to unavailable plasma must fail WITHOUT calling /etc/init.d/desktop
        res = mod.do_switch('plasma')
        self.assertFalse(res['ok'])
        self.assertEqual(init_calls, [])

        # If configured session is unavailable, restart must be rejected before stopping active session
        uci_values['desktop.main.session'] = 'plasma'
        res = mod.do_action('restart')
        self.assertFalse(res['ok'])
        self.assertEqual(init_calls, [])


if __name__ == '__main__':
    unittest.main()
