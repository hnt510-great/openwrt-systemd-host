#!/usr/bin/env python3
"""Test pluggable desktop sessions, active-session stop/switch, and desktop-ctl."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
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
        self.assertIn('--property=ExecStopPost=-' + str(user_stop) + ' dummy',
                      (self.path / 'systemd-run.args').read_text().splitlines())

        # Now UCI says 'gnome', but stop_service must stop the OLD active session ('dummy')!
        res = subprocess.run(['sh', str(harness), str(init_file), 'stop_service'],
                             env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('stopped-dummy', stop_log.read_text())
        self.assertFalse((self.run_dir / 'active.env').exists())
        self.assertTrue((self.run_dir / 'manual-stop').exists())

        # DRM hotplug delegates to locked `autostart` (skipping when udev already handled it)
        hotplug_calls = self.path / 'hotplug.log'
        fake_init = self.tool('fake-desktop-init', f'printf "%s\\n" "$*" >> "{hotplug_calls}"')
        self.tool('uci', 'case "$*" in *desktop.main.enabled*) echo 1;; *desktop.main.user*) echo alice;; *desktop.main.session*) echo gnome;; *) exit 1;; esac')
        hotplug = self.path / '95-desktop'
        hotplug.write_text(
            (FILES / 'desktop.hotplug').read_text()
            .replace('/etc/init.d/desktop', str(fake_init)))
        res = subprocess.run(['sh', str(hotplug)], env=dict(self.env, ACTION='change', OPENWRT_UDEV_HANDLED_DESKTOP='1'), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse(hotplug_calls.exists())
        res = subprocess.run(['sh', str(hotplug)], env=dict(self.env, ACTION='change'), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(hotplug_calls.read_text().strip(), 'autostart')

        # Locked autostart inside desktop.init must respect manual-stop and never clear it
        (self.path / 'systemd-run.args').unlink(missing_ok=True)
        res = subprocess.run(['sh', str(harness), str(init_file), 'start_service'],
                             env=dict(self.env, TARGET_SESSION='dummy', DESKTOP_AUTOSTART='1'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse((self.path / 'systemd-run.args').exists())
        self.assertTrue((self.run_dir / 'manual-stop').exists())

        # Explicit start clears manual-stop so subsequent autostart works
        res = subprocess.run(['sh', str(harness), str(init_file), 'start_service'],
                             env=dict(self.env, TARGET_SESSION='dummy'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse((self.run_dir / 'manual-stop').exists())
        (self.path / 'systemd-run.args').unlink(missing_ok=True)
        res = subprocess.run(['sh', str(harness), str(init_file), 'start_service'],
                             env=dict(self.env, TARGET_SESSION='dummy', DESKTOP_AUTOSTART='1'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertTrue((self.path / 'systemd-run.args').exists())

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
                     KDE_SESSION_VERSION='6',
                     XAUTHORITY='/tmp/stale-xauth',
                     XDG_SESSION_ID='c101', XDG_SEAT='seat0', XDG_VTNR='7'),
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        args, env_after = json.loads(out.read_text())
        self.assertEqual(args, ['--dummy'])
        self.assertEqual(env_after['XDG_CURRENT_DESKTOP'], 'DUMMY')
        self.assertNotIn('MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY', env_after)
        self.assertNotIn('KDE_SESSION_VERSION', env_after)
        self.assertNotIn('XAUTHORITY', env_after)
        self.assertEqual(env_after['XDG_SESSION_ID'], 'c101')
        self.assertEqual(env_after['XDG_SEAT'], 'seat0')
        self.assertEqual(env_after['XDG_VTNR'], '7')
        systemctl_lines = systemctl_log.read_text().splitlines()
        unset_lines = [line for line in systemctl_lines
                       if line.startswith('--user unset-environment ')]
        self.assertEqual(len(unset_lines), 1)
        self.assertIn('MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY', unset_lines[0])
        self.assertIn('KDE_FULL_SESSION', unset_lines[0])
        self.assertIn('KDE_SESSION_VERSION', unset_lines[0])
        self.assertIn('XAUTHORITY', unset_lines[0])
        self.assertIn('XDG_SESSION_ID', unset_lines[0])
        self.assertIn('XDG_SEAT', unset_lines[0])
        self.assertIn('XDG_VTNR', unset_lines[0])
        seat_import_idx = next(
            (i for i, l in enumerate(systemctl_lines)
             if l == '--user import-environment XDG_SESSION_ID XDG_SEAT XDG_VTNR'),
            None)
        unset_idx = systemctl_lines.index(unset_lines[0])
        self.assertIsNotNone(seat_import_idx)
        self.assertGreater(seat_import_idx, unset_idx)

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

    def test_no_credential_backend_and_session_resolution_rules(self):
        mod = load_desktop_ctl()
        mod.SESSIONS_DIR = self.sessions_dir
        mod.SYSTEMD_USER_DIR = self.path / 'systemd-user'
        mod.SYSTEMD_USER_DIR.mkdir()
        mod.RUN_DIR = self.run_dir
        mod.SECRET_DIR = self.path / 'secrets-empty'
        mod.SECRET_DIR.mkdir()
        mod.TLS_DIR = self.path / 'tls-empty'
        mod.TLS_DIR.mkdir()
        mod.DRM_DIR = self.path / 'drm'
        mod.DRM_DIR.mkdir()
        mod.PASSWD_FILE = self.path / 'passwd'
        mod.REQUIRE_ROOT_PLUGIN = False
        mod.PASSWD_FILE.write_text('alice:x:1000:1000::/home/alice:/bin/sh\n')

        uci_values = {
            'desktop.main.enabled': '1',
            'desktop.main.user': 'alice',
            'desktop.main.session': '',
        }

        def fake_run(argv, **kwargs):
            if argv[0] == 'uci' and argv[1] == '-q' and argv[2] == 'get':
                val = uci_values.get(argv[3], '')
                return subprocess.CompletedProcess(argv, 0 if val else 1, val + '\n' if val else '', '')
            if argv[0] == 'systemctl' and argv[1] == 'show':
                return subprocess.CompletedProcess(
                    argv, 0,
                    'ActiveState=inactive\nSubState=dead\nMainPID=0\nNRestarts=0\nActiveEnterTimestamp=\n', '')
            return subprocess.CompletedProcess(argv, 1, '', '')

        mod.run_cmd = fake_run

        # 0 available sessions -> selection_error set, preflight rejects
        st0 = mod.get_status()
        self.assertTrue(st0['ok'])
        self.assertIsNone(st0['selected_session'])
        self.assertIn('No desktop session', st0['selection_error'])
        self.assertEqual(st0['provisioned']['keyring_credential'], 'not_applicable')
        self.assertFalse(st0['runtime']['rdp_available'])
        self.assertIsNotNone(mod.preflight_start(st0))

        # 1 available non-GNOME session (no credential backend, no RDP) -> auto-selected, preflight passes without secret!
        dummy_bin = self.tool('dummy-session', 'exit 0')
        self.write_dummy_plugin(dummy_bin, self.path / 'stop.log')
        st1 = mod.get_status()
        self.assertEqual(st1['selected_session'], 'dummy')
        self.assertIsNone(st1['selection_error'])
        self.assertEqual(st1['provisioned']['keyring_credential'], 'not_applicable')
        self.assertFalse(st1['provisioned']['keyring_required'])
        self.assertFalse(st1['runtime']['rdp_available'])
        self.assertIsNone(mod.preflight_start(st1))

        # Verify desktop.init starts dummy without LoadCredential* when unconfigured
        common = self.write_common(
            'desktop_error() { printf "%s\\n" "$*" >&2; return 1; }\n'
            'desktop_validate_user() { DESKTOP_USER_UID=1000 DESKTOP_USER_HOME=/home/alice DESKTOP_USER_SHELL=/bin/sh; }\n'
            'desktop_lan_address() { echo 192.0.2.1; }\n'
            'desktop_select_output() { echo HDMI-A-1; }\n'
        )
        self.tool('logger', ':')
        self.tool('chown', ':')
        self.tool('uci', 'exit 1')
        self.tool('systemctl', '[ "$1" = is-active ] && exit 3 || exit 0')
        self.tool('systemd-run', f'printf "%s\\n" "$@" > "{self.path / "dummy-run.args"}"')
        init_src = (FILES / 'desktop.init').read_text()
        init_src = init_src.replace('/usr/libexec/desktop-common.sh', str(common))
        init_src = init_src.replace('/run/openwrt-desktop', str(self.run_dir))
        init_src = init_src.replace('/dev/tty0', str(self.path / 'no-tty0'))
        init_file = self.path / 'desktop-nocred.init'
        init_file.write_text(init_src)
        harness = self.path / 'harness-nocred.sh'
        harness.write_text(
            'config_load() { :; }\n'
            'config_get_bool() { eval "$1=1"; }\n'
            'config_get() {\n'
            '\tcase "$3" in\n'
            '\t\tuser) eval "$1=alice" ;;\n'
            '\t\tsession) eval "$1=" ;;\n'
            '\t\t*) eval "$1=\\$4" ;;\n'
            '\tesac\n'
            '}\n'
            '. "$1"\n'
            'start_service\n'
        )
        res = subprocess.run(['sh', str(harness), str(init_file)], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        args = (self.path / 'dummy-run.args').read_text().splitlines()
        self.assertIn('--setenv=OPENWRT_DESKTOP_SESSION=dummy', args)
        self.assertFalse(any('LoadCredential' in a for a in args))

        # 2 available sessions with unconfigured session -> ambiguous, both desktop-ctl and desktop_resolve_session reject
        second_bin = self.tool('second-session', 'exit 0')
        (self.sessions_dir / 'second').write_text(
            f'SESSION_ID="second"\nSESSION_TITLE="Second"\nSESSION_EXEC="{second_bin}"\n')
        st2 = mod.get_status()
        self.assertIsNone(st2['selected_session'])
        self.assertIn('Multiple desktop sessions', st2['selection_error'])
        self.assertIsNotNone(mod.preflight_start(st2))
        res = subprocess.run(
            ['sh', '-c', '. "$1"; desktop_resolve_session ""', 't', str(common)],
            capture_output=True, text=True)
        self.assertNotEqual(res.returncode, 0)
        self.assertIn('Multiple desktop sessions', res.stderr)

    def test_flatpak_session_uses_current_desktop_not_hardcoded_gnome(self):
        fp_src = (ROOT / 'package/custom/openwrt-flatpak/files/desktop-flatpak-session').read_text()
        native = self.path / 'native-systemd'
        native.mkdir()
        log = self.path / 'fp-systemctl.log'
        self.tool('systemctl', f'printf "%s\\n" "$*" >> "{log}"\n'
                  'if [ "$2" = show-environment ]; then echo "XDG_CURRENT_DESKTOP=DUMMY"; fi\n')
        fp_script = self.path / 'desktop-flatpak-session'
        fp_script.write_text(fp_src.replace('/run/systemd/system', str(native)))
        env = dict(self.env, XDG_RUNTIME_DIR=str(self.path), WAYLAND_DISPLAY='wayland-0')
        env.pop('XDG_CURRENT_DESKTOP', None)
        res = subprocess.run(['sh', str(fp_script)], env=env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = log.read_text().splitlines()
        self.assertTrue(any('import-environment' in l and 'XDG_CURRENT_DESKTOP' in l for l in lines))
        self.assertTrue(any('start openwrt-flatpak-session.target' in l for l in lines))
        self.assertNotIn('XDG_CURRENT_DESKTOP=GNOME', fp_src)

    def test_plasma_session_plugin_metadata_and_check(self):
        plasma_plugin = ROOT / 'package/custom/openwrt-desktop-plasma/files/sessions.d/plasma'
        self.assertTrue(plasma_plugin.is_file())
        mod = load_desktop_ctl()
        mod.SESSIONS_DIR = self.sessions_dir
        mod.REQUIRE_ROOT_PLUGIN = False
        startplasma = self.tool('startplasma-wayland', 'exit 0')
        (self.sessions_dir / 'plasma').write_text(
            plasma_plugin.read_text().replace('/usr/bin/startplasma-wayland', str(startplasma)))
        parsed = mod.parse_session_plugin(self.sessions_dir / 'plasma')
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['id'], 'plasma')
        self.assertEqual(parsed['title'], 'KDE Plasma (Wayland)')
        self.assertTrue(parsed['available'])
        self.assertTrue(parsed['supports_rdp'])
        self.assertFalse(parsed['supports_kms_scheduling'])
        self.assertEqual(parsed['credential_backend'], 'gnome-keyring')
        self.assertEqual(parsed['rdp_unit'], 'app-org.kde.krdpserver.service')

    def test_plasma_pre_start_and_stop_clean_compositor_and_seat_env(self):
        plasma_plugin = ROOT / 'package/custom/openwrt-desktop-plasma/files/sessions.d/plasma'
        startplasma = self.tool('startplasma-wayland', 'exit 0')
        kwin = self.tool('kwin_wayland', 'exit 0')
        plasmashell = self.tool('plasmashell', 'exit 0')
        target = self.path / 'plasma-workspace-wayland.target'
        target.write_text('[Unit]\n')
        keyring = self.tool('keyring', ':')
        user_setup = self.tool('user-setup', ':')
        self.tool('id', 'echo 1000')

        plasma_src = plasma_plugin.read_text()
        plasma_src = plasma_src.replace('/usr/bin/startplasma-wayland', str(startplasma))
        plasma_src = plasma_src.replace('/usr/bin/kwin_wayland', str(kwin))
        plasma_src = plasma_src.replace('/usr/bin/plasmashell', str(plasmashell))
        plasma_src = plasma_src.replace('/usr/lib/systemd/user/plasma-workspace-wayland.target', str(target))
        plasma_src = plasma_src.replace('/usr/libexec/desktop-keyring-unlock', str(keyring))
        (self.sessions_dir / 'plasma').write_text(plasma_src)

        common = self.write_common('desktop_error() { printf "%s\\n" "$*" >&2; return 1; }\n')
        systemctl_log = self.path / 'plasma-systemctl.log'
        self.tool('systemctl', f'printf "%s\\n" "$*" >> "{systemctl_log}"; [ "$2" = is-active ] && exit 3 || exit 0')

        bus = socket.socket(socket.AF_UNIX)
        self.addCleanup(bus.close)
        bus.bind(str(self.path / 'bus'))

        sess_src = (FILES / 'desktop-session').read_text()
        sess_src = sess_src.replace('/usr/libexec/desktop-common.sh', str(common))
        sess_src = sess_src.replace('/usr/libexec/desktop-user-setup', str(user_setup))
        sess_file = self.path / 'desktop-session-plasma'
        sess_file.write_text(sess_src)

        res = subprocess.run(
            ['sh', str(sess_file)],
            env=dict(self.env, XDG_RUNTIME_DIR=str(self.path),
                     OPENWRT_DESKTOP_SESSION='plasma',
                     WAYLAND_DISPLAY='wayland-0',
                     XDG_SESSION_ID='c102', XDG_SEAT='seat0', XDG_VTNR='7'),
            capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        lines = systemctl_log.read_text().splitlines()
        stop_idx = next(
            (i for i, l in enumerate(lines)
             if l.startswith('--user stop ') and 'plasma-kwin_wayland.service' in l),
            None)
        reset_idx = next(
            (i for i, l in enumerate(lines)
             if l.startswith('--user reset-failed ') and 'app-org.kde.krdpserver.service' in l),
            None)
        unset_idx = next(
            (i for i, l in enumerate(lines)
             if l.startswith('--user unset-environment ') and 'WAYLAND_DISPLAY' in l and 'XDG_SESSION_ID' in l),
            None)
        seat_idx = next(
            (i for i, l in enumerate(lines)
             if l == '--user import-environment XDG_SESSION_ID XDG_SEAT XDG_VTNR'),
            None)
        self.assertIsNotNone(stop_idx, lines)
        self.assertIsNotNone(reset_idx, lines)
        self.assertIsNotNone(unset_idx, lines)
        self.assertIsNotNone(seat_idx, lines)
        self.assertLess(stop_idx, unset_idx)
        self.assertLess(reset_idx, unset_idx)
        self.assertLess(unset_idx, seat_idx)

        # Verify desktop-user-stop also stops plasma-kwin_wayland.service and unsets stale env
        systemctl_log.unlink()
        user_stop = self.path / 'desktop-user-stop-plasma'
        user_stop.write_text(
            (FILES / 'desktop-user-stop').read_text().replace('/usr/libexec/desktop-common.sh', str(common)))
        res = subprocess.run(['sh', str(user_stop), 'plasma'], env=self.env, capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        stop_lines = systemctl_log.read_text().splitlines()
        self.assertTrue(any(l.startswith('--user stop ') and 'plasma-kwin_wayland.service' in l for l in stop_lines))
        self.assertTrue(any(l.startswith('--user unset-environment ') and 'WAYLAND_DISPLAY' in l and 'XDG_SESSION_ID' in l for l in stop_lines))

    def test_krdp_dropin_breaks_plasma_workspace_ordering_cycle(self):
        dropin_src = ROOT / 'package/custom/openwrt-desktop-plasma/files/krdp-openwrt.conf'
        dropin_text = dropin_src.read_text()
        self.assertIn('PartOf=graphical-session.target', dropin_text)
        after_line = next(
            (line for line in dropin_text.splitlines() if line.startswith('After=')),
            '',
        )
        for dep in (
            'plasma-workspace.target',
            'graphical-session.target',
            'xdg-desktop-portal.service',
        ):
            self.assertIn(dep, after_line)

        if not shutil.which('systemd-analyze'):
            self.skipTest('systemd-analyze not available')

        root = self.path / 'systemd-root'
        # systemd-analyze --root rejects --user; --system exercises the same unit graph and cycle detector.
        unit_dir = root / 'usr/lib/systemd/system'
        wants_dir = root / 'etc/systemd/system/plasma-workspace.target.wants'
        dropin_dir = unit_dir / 'app-org.kde.krdpserver.service.d'
        for d in (unit_dir, wants_dir, dropin_dir):
            d.mkdir(parents=True, exist_ok=True)

        for rel in (
            'usr/bin/krdpserver',
            'usr/libexec/xdg-desktop-portal',
            'usr/lib/libexec/xdg-desktop-portal-kde',
            'usr/libexec/desktop-krdp-wrapper',
        ):
            stub = root / rel
            stub.parent.mkdir(parents=True, exist_ok=True)
            stub.write_text('#!/bin/sh\nexit 0\n')
            stub.chmod(0o755)

        (unit_dir / 'basic.target').write_text('[Unit]\nDescription=Basic\n')
        (unit_dir / 'plasma-core.target').write_text('[Unit]\nDescription=Plasma Core\n')
        (unit_dir / 'graphical-session.target').write_text(
            '[Unit]\nDescription=Current graphical user session\nRequires=basic.target\n'
        )
        (unit_dir / 'plasma-workspace.target').write_text(
            '[Unit]\n'
            'Description=KDE Plasma Workspace\n'
            'Requires=plasma-core.target graphical-session.target\n'
            'BindsTo=graphical-session.target\n'
            'Before=graphical-session.target\n'
        )
        (unit_dir / 'xdg-desktop-portal.service').write_text(
            '[Unit]\n'
            'Description=Portal service\n'
            'PartOf=graphical-session.target\n'
            'Requisite=graphical-session.target\n'
            'After=graphical-session.target\n'
            '[Service]\n'
            'ExecStart=/usr/libexec/xdg-desktop-portal\n'
        )
        (unit_dir / 'plasma-xdg-desktop-portal-kde.service').write_text(
            '[Unit]\n'
            'Description=Xdg Desktop Portal For KDE\n'
            'PartOf=graphical-session.target\n'
            'After=plasma-core.target\n'
            '[Service]\n'
            'ExecStart=/usr/lib/libexec/xdg-desktop-portal-kde\n'
        )
        krdp_unit = unit_dir / 'app-org.kde.krdpserver.service'
        krdp_unit.write_text(
            '[Unit]\n'
            'Description=KRDP Server\n'
            'After=plasma-xdg-desktop-portal-kde.service\n'
            'After=plasma-core.target\n'
            '[Service]\n'
            'Type=exec\n'
            'ExecStart=/usr/bin/krdpserver\n'
            '[Install]\n'
            'WantedBy=plasma-workspace.target\n'
        )
        (wants_dir / 'app-org.kde.krdpserver.service').symlink_to(
            '/usr/lib/systemd/system/app-org.kde.krdpserver.service'
        )
        (dropin_dir / 'openwrt.conf').write_text(dropin_text)

        res = subprocess.run(
            [
                'systemd-analyze',
                '--system',
                f'--root={root}',
                'verify',
                '--man=no',
                'plasma-workspace.target',
                'app-org.kde.krdpserver.service',
            ],
            capture_output=True,
            text=True,
        )
        combined = res.stdout + res.stderr
        self.assertEqual(res.returncode, 0, combined)
        self.assertEqual(combined.strip(), '', combined)
        self.assertNotIn('ordering cycle', combined.lower())


if __name__ == '__main__':
    unittest.main()
