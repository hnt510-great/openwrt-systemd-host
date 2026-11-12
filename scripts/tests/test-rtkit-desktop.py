#!/usr/bin/env python3
"""Check the RealtimeKit package, desktop KMS scheduling and the kernel baseline."""
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
RTKIT = ROOT / 'package/custom/rtkit'
DESKTOP = ROOT / 'package/custom/openwrt-desktop'
AUDIO = ROOT / 'package/custom/openwrt-desktop-audio'
SESSION_IMPORTS = ['XDG_CURRENT_DESKTOP', 'XDG_SESSION_DESKTOP', 'DESKTOP_SESSION',
                   'XDG_SESSION_TYPE', 'XMODIFIERS', 'XDG_DATA_DIRS']
KMS_VARIABLE = 'MUTTER_DEBUG_KMS_SCHEDULING_PRIORITY'


def depends(makefile, package):
    text = makefile.read_text()
    match = re.search(r'define Package/' + re.escape(package) + r'\n(.*?)\nendef', text, re.S)
    block = match[1].replace('\\\n', ' ')
    line = re.search(r'^\s*DEPENDS:=(.*)$', block, re.M)[1]
    return line.split()


class RtkitPackage(unittest.TestCase):
    def test_update_registry(self):
        packages = json.loads((ROOT / 'configs/custom-package-updates.json').read_text())['packages']
        self.assertEqual(packages['rtkit'], {
            'provider': 'gitlab', 'policy': 'series',
            'host': 'https://gitlab.freedesktop.org', 'project': 'pipewire/rtkit'})

    def test_recipe(self):
        text = (RTKIT / 'Makefile').read_text()
        self.assertIn('PKG_VERSION:=0.14\n', text)
        self.assertIn('PKG_SOURCE_URL:=https://gitlab.freedesktop.org/pipewire/rtkit/-/archive/v$(PKG_VERSION)\n', text)
        self.assertIn('USERID:=rtkit=193:rtkit=193\n', text)
        self.assertNotIn('github.com/heftig', text)
        for dependency in ['+dbus', '+libdbus', '+libcap', '+libsystemd', '+polkit', '+librt', '+libpthread']:
            self.assertIn(dependency, depends(RTKIT / 'Makefile', 'rtkit'))
        for installed in [
                '/usr/libexec/rtkit-daemon', '/usr/sbin/rtkitctl',
                'system-services/org.freedesktop.RealtimeKit1.service',
                'system.d/org.freedesktop.RealtimeKit1.conf',
                'interfaces/org.freedesktop.RealtimeKit1.xml',
                'actions/org.freedesktop.RealtimeKit1.policy',
                'rules.d/20-openwrt-rtkit.rules',
                'system/rtkit-daemon.service',
                'rtkit-daemon.service.d/openwrt.conf']:
            self.assertIn(installed, text)

    def test_uid_is_unique(self):
        owners = {}
        for makefile in [*ROOT.glob('package/**/Makefile'), *ROOT.glob('feeds/*/**/Makefile')]:
            try:
                text = makefile.read_text(errors='replace')
            except OSError:
                continue
            for match in re.finditer(r'USERID:=.*?=(\d+)', text):
                if match[1] == '193':
                    owners.setdefault(makefile.parent.name, makefile)
        self.assertEqual(sorted(owners), ['rtkit'])

    def test_polkit_rule(self):
        text = (RTKIT / 'files/20-openwrt-rtkit.rules').read_text()
        self.assertIn('"org.freedesktop.RealtimeKit1.acquire-high-priority"', text)
        self.assertIn('"org.freedesktop.RealtimeKit1.acquire-real-time"', text)
        self.assertIn('subject.isInGroup("audio") || subject.isInGroup("video")', text)
        self.assertIn('return polkit.Result.YES;', text)
        self.assertNotIn('isInGroup("render")', text)

    def test_service_drop_in(self):
        text = (RTKIT / 'files/rtkit-service.conf').read_text()
        self.assertIn('Environment=DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket\n', text)
        self.assertIn('Requires=dbus.service\n', text)


class DesktopIntegration(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.bin = self.path / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=str(self.bin) + ':' + os.environ['PATH'],
                        HOME=str(self.path), RECORD=str(self.path / 'record'))

    def tool(self, name, body):
        path = self.bin / name
        path.write_text('#!/bin/sh\n' + body + '\n')
        path.chmod(0o755)
        return path

    def test_meta_packages_depend_on_rtkit(self):
        self.assertIn('+rtkit', depends(DESKTOP / 'Makefile', 'openwrt-desktop'))
        self.assertIn('+rtkit', depends(AUDIO / 'Makefile', 'openwrt-desktop-audio'))

    def test_default_config(self):
        text = (DESKTOP / 'files/desktop.config').read_text()
        self.assertIn("\toption kms_scheduling 'high-priority'\n", text)

    def run_init(self, kms_scheduling):
        run = self.path / 'run'
        native = self.path / 'native'
        native.mkdir(exist_ok=True)
        session = self.path / 'gnome-session'
        session.write_text('')
        session.chmod(0o755)
        secret = self.path / 'secret'
        secret.write_text('x')
        common = self.path / 'common.sh'
        common.write_text(
            'desktop_error() { printf "%s\\n" "$*" >&2; return 1; }\n'
            'desktop_validate_user() { DESKTOP_USER_UID=1000 DESKTOP_USER_HOME=/home/alice '
            'DESKTOP_USER_SHELL=/bin/sh; }\n'
            'desktop_lan_address() { echo 192.0.2.1; }\n'
            'desktop_select_output() { echo HDMI-A-1; }\n')
        for name, body in [('logger', ':'), ('chown', ':'), ('uci', 'exit 1'),
                           ('stat', 'echo 0:600'),
                           ('systemctl', 'exit 3'),
                           ('systemd-run', 'printf "%s\\n" "$@" > "$RECORD"')]:
            self.tool(name, body)
        source = (DESKTOP / 'files/desktop.init').read_text()
        replacements = {
            '/usr/libexec/desktop-common.sh': str(common),
            '/run/systemd/system': str(native),
            '/run/openwrt-desktop': str(run),
            '/usr/bin/gnome-session': str(session),
            '"/etc/desktop/gnome/$DESKTOP_USER_UID.keyring-passphrase"': '"' + str(secret) + '"',
            '/dev/tty0': str(self.path / 'no-tty0'),
        }
        for old, new in replacements.items():
            self.assertIn(old, source)
            source = source.replace(old, new)
        init = self.path / 'desktop.init'
        init.write_text(source)
        harness = self.path / 'harness'
        harness.write_text(
            'config_load() { :; }\n'
            'config_get_bool() { eval "$1=1"; }\n'
            'config_get() {\n'
            '\tcase "$3" in\n'
            '\t\tuser) eval "$1=alice" ;;\n'
            '\t\tkms_scheduling) if [ "${KMS+set}" = set ]; then eval "$1=\\$KMS"; '
            'else eval "$1=\\$4"; fi ;;\n'
            '\t\t*) eval "$1=\\$4" ;;\n'
            '\tesac\n'
            '}\n'
            '. "$1"\n'
            'start_service\n')
        record = self.path / 'record'
        record.unlink(missing_ok=True)
        env = dict(self.env)
        env.pop('KMS', None)
        if kms_scheduling is not None:
            env['KMS'] = kms_scheduling
        result = subprocess.run(['sh', str(harness), str(init)], env=env,
                                capture_output=True, text=True)
        arguments = record.read_text().splitlines() if record.exists() else None
        return result, arguments

    def test_init_validates_and_forwards_kms_scheduling(self):
        for value, expected in [(None, 'high-priority'), ('high-priority', 'high-priority'),
                                ('realtime', 'realtime'), ('normal', 'normal')]:
            with self.subTest(value=value):
                result, arguments = self.run_init(value)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertIsNotNone(arguments)
                self.assertIn('--setenv=OPENWRT_DESKTOP_KMS_SCHEDULING=' + expected, arguments)
                self.assertIn('--setenv=XDG_SESSION_CLASS=user', arguments)
                self.assertEqual(arguments[-1], '/usr/libexec/desktop-session')
        for value in ['fifo', 'Realtime', 'realtime normal', 'normal;id']:
            with self.subTest(value=value):
                result, arguments = self.run_init(value)
                self.assertNotEqual(result.returncode, 0)
                self.assertIsNone(arguments)
                self.assertIn('Invalid kms_scheduling', result.stderr)

    def run_session(self, kms_scheduling, inherited=None):
        import socket
        bus = self.path / 'bus'
        if not bus.exists():
            listener = socket.socket(socket.AF_UNIX)
            self.addCleanup(listener.close)
            listener.bind(str(bus))
        keyring = self.tool('keyring', ':')
        session = self.tool('gnome-session',
                            "/usr/bin/python3 -c 'import json,os,sys; "
                            'json.dump(dict(os.environ),open(os.environ["SESSION_OUTPUT"],"w"))\'')
        self.tool('id', 'echo 1000')
        self.tool('systemctl', 'printf "%s\\n" "$*" >> "$RECORD"')
        source = (DESKTOP / 'files/desktop-session').read_text()
        source = source.replace('/usr/libexec/desktop-keyring-unlock', str(keyring))
        source = source.replace('/usr/bin/gnome-session', str(session))
        script = self.path / 'desktop-session'
        script.write_text(source)
        record = self.path / 'record'
        record.unlink(missing_ok=True)
        output = self.path / 'session.json'
        output.unlink(missing_ok=True)
        env = dict(self.env, XDG_RUNTIME_DIR=str(self.path), SESSION_OUTPUT=str(output),
                   **(inherited or {}))
        env.pop('OPENWRT_DESKTOP_KMS_SCHEDULING', None)
        if kms_scheduling is not None:
            env['OPENWRT_DESKTOP_KMS_SCHEDULING'] = kms_scheduling
        result = subprocess.run(['sh', str(script)], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = [line.split() for line in record.read_text().splitlines()]
        return calls, json.loads(output.read_text())

    def test_session_imports_override_only_for_non_default_modes(self):
        for value in [None, 'high-priority', 'realtime', 'normal']:
            with self.subTest(value=value):
                calls, environment = self.run_session(value, {KMS_VARIABLE: 'realtime'})
                unset = [call for call in calls if call[:2] == ['--user', 'unset-environment']]
                imported = [call for call in calls if call[:2] == ['--user', 'import-environment']]
                self.assertEqual(len(unset), 1)
                self.assertEqual(len(imported), 1)
                self.assertIn(KMS_VARIABLE, unset[0])
                self.assertLess(calls.index(unset[0]), calls.index(imported[0]))
                if value in ('realtime', 'normal'):
                    self.assertEqual(imported[0][2:], SESSION_IMPORTS + [KMS_VARIABLE])
                    self.assertEqual(environment[KMS_VARIABLE], value)
                else:
                    self.assertEqual(imported[0][2:], SESSION_IMPORTS)
                    self.assertNotIn(KMS_VARIABLE, environment)


class KernelBaseline(unittest.TestCase):
    def test_kconfig_symbol(self):
        text = (ROOT / 'config/Config-kernel.in').read_text()
        match = re.search(r'\n\t\tconfig KERNEL_RT_GROUP_SCHED_DEFAULT_DISABLED\n(.*?)\n\n', text, re.S)
        self.assertIsNotNone(match)
        block = match[1]
        self.assertIn('\t\t\tbool ', block)
        self.assertIn('\t\t\tdefault n\n', block)
        self.assertIn('\t\t\tdepends on KERNEL_RT_GROUP_SCHED\n', block)
        self.assertLess(text.index('config KERNEL_RT_GROUP_SCHED\n'),
                        text.index('config KERNEL_RT_GROUP_SCHED_DEFAULT_DISABLED\n'))

    def test_target_config(self):
        lines = (ROOT / 'target/linux/x86/64/config-7.3').read_text().splitlines()
        for line in ['# CONFIG_HZ_100 is not set', 'CONFIG_HZ_1000=y', 'CONFIG_HZ=1000',
                     'CONFIG_PREEMPT=y', 'CONFIG_PREEMPT_DYNAMIC=y', '# CONFIG_PREEMPT_LAZY is not set',
                     'CONFIG_RT_GROUP_SCHED_DEFAULT_DISABLED=y', '# CONFIG_UCLAMP_TASK is not set']:
            self.assertEqual(lines.count(line), 1, line)
        self.assertNotIn('CONFIG_PREEMPT_LAZY=y', lines)
        self.assertNotIn('CONFIG_UCLAMP_TASK=y', lines)

    def test_desktop_configs(self):
        for name in ['configs/gnome-desktop.config', 'configs/x86-64-systemd-desktop.config']:
            lines = (ROOT / name).read_text().splitlines()
            with self.subTest(config=name):
                for line in ['CONFIG_KERNEL_PREEMPT=y', '# CONFIG_KERNEL_PREEMPT_NONE is not set',
                             'CONFIG_KERNEL_RT_GROUP_SCHED_DEFAULT_DISABLED=y', 'CONFIG_PACKAGE_rtkit=y']:
                    self.assertEqual(lines.count(line), 1, line)
                self.assertNotIn('CONFIG_KERNEL_PREEMPT_NONE=y', lines)
                self.assertNotIn('# CONFIG_KERNEL_PREEMPT is not set', lines)


if __name__ == '__main__':
    unittest.main()
