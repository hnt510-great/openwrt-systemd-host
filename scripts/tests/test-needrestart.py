#!/usr/bin/env python3
"""Exercise the compiled scanner with isolated proc/APK/systemd/Podman fixtures."""
import fcntl
import json
import os
import pwd
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import unittest


TREE = Path(__file__).resolve().parents[2]
SOURCE = TREE / 'package/custom/openwrt-needrestart/src/needrestart.c'


class NeedrestartTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.build = tempfile.TemporaryDirectory(prefix='needrestart-tests-')
        toolchains = sorted((TREE / 'staging_dir').glob('toolchain-x86_64_gcc-*_glibc'))
        if not toolchains:
            raise unittest.SkipTest('x86_64/glibc toolchain required')
        toolchain = toolchains[-1]
        staging = TREE / 'staging_dir/target-x86_64_glibc'
        cls.binary = Path(cls.build.name) / 'needrestart'
        args = [str(toolchain / 'bin/x86_64-openwrt-linux-gcc'), '-O2', '-g',
                '-Wall', '-Wextra', '-Werror', '-DNEEDRESTART_TEST',
                '-I' + str(staging / 'usr/include'), str(SOURCE),
                '-L' + str(staging / 'usr/lib'), '-Wl,-rpath-link,' + str(staging / 'usr/lib'),
                '-lubus', '-lubox', '-lblobmsg_json', '-ljson-c', '-lsystemd', '-o', str(cls.binary)]
        subprocess.run(args, check=True, env={**os.environ, 'STAGING_DIR': str(staging)})
        cls.production = Path(cls.build.name) / 'needrestart-production'
        production_args = [a for a in args if a != '-DNEEDRESTART_TEST']
        production_args[-1] = str(cls.production)
        subprocess.run(production_args, check=True, env={**os.environ, 'STAGING_DIR': str(staging)})
        cls.runner = [str(toolchain / 'lib/ld-linux-x86-64.so.2'), '--library-path',
                      ':'.join(map(str, [staging / 'usr/lib', toolchain / 'lib'])), str(cls.binary)]

    @classmethod
    def tearDownClass(cls):
        cls.build.cleanup()

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='needrestart-root-')
        self.root = Path(self.directory.name)
        (self.root / 'run').mkdir()
        self.write('lib/apk/db/installed', 'P:example\nV:2-r1\nF:usr/bin\nR:example\n\n')
        self.write('lib/apk/db/lock', '')
        self.write('proc/sys/kernel/random/boot_id', 'test-boot\n')
        self.write('release', 'test-release\n')
        self.json('ubus.json', {})
        self.json('ownership.json', {})
        self.json('podman.json', [])
        self.kernel()

    def tearDown(self):
        self.directory.cleanup()

    def write(self, name, data):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data if isinstance(data, bytes) else data.encode())
        return p

    def json(self, name, value):
        return self.write(name, json.dumps(value))

    def kernel(self, pending=None, abi='abi-one', ready=True, failed=False, running='test-release'):
        state = {'schema': 1, 'pending': pending, 'generations': {
            'current': {'release': 'test-release', 'abi': 'abi-one', 'ready': True}}}
        if pending:
            state['generations'][pending] = {'release': pending, 'abi': abi,
                                              'ready': ready, 'failed': failed}
        self.json('etc/openwrt-kernel/state.json', state)
        self.write('release', running + '\n')
        self.write('grubenv', 'next_entry=owrt-' + (pending or '') + '\n')

    def process(self, pid=123, deleted=True, changed=True, cgroup='/system.slice/example.service',
                file='usr/bin/example', executable=True):
        current = self.write(file, b'\x7fELFnew-version')
        old = self.write('old-' + str(pid), b'\x7fELFold-version' if changed else b'\x7fELFnew-version')
        proc = self.root / 'proc' / str(pid)
        proc.mkdir(parents=True, exist_ok=True)
        (proc / 'root').symlink_to(self.root)
        # The fixture retains access to old objects through an actual symlink.
        # readlink(exe) needs the kernel-style path and deleted marker, while
        # map_files supplies a readable old inode for content verification.
        fields = ['S'] + ['0'] * 18 + ['100'] + ['0'] * 5
        self.write(f'proc/{pid}/stat', f'{pid} (test (worker)) ' + ' '.join(fields))
        self.write(f'proc/{pid}/cgroup', '0::' + cgroup + '\n')
        (proc / 'exe').symlink_to('/' + file + (' (deleted)' if deleted and executable else ''))
        if not executable:
            self.write('usr/bin/interpreter', b'\x7fELFinterpreter')
            (proc / 'exe').unlink()
            (proc / 'exe').symlink_to('/usr/bin/interpreter')
        mapping = f'1000-2000 r-xp 00000000 {os.major(current.stat().st_dev):x}:{os.minor(current.stat().st_dev):x} {current.stat().st_ino} /{file}'
        if deleted:
            mapping += ' (deleted)'
        self.write(f'proc/{pid}/maps', mapping + '\n')
        (proc / 'map_files').mkdir()
        (proc / 'map_files/1000-2000').symlink_to(old)
        self.json('ownership.json', {str(pid): {'unit': 'example.service'}})
        return current, old, proc

    def call(self, *args):
        return subprocess.run([*self.runner, '--test-root', str(self.root), *args],
                              capture_output=True, text=True, timeout=30)

    def scan(self, code=0, *args):
        p = self.call('--json', *args)
        self.assertEqual(p.returncode, code, p.stderr + p.stdout)
        return json.loads(p.stdout)

    def test_clean_and_cached_report(self):
        r = self.scan()
        self.assertTrue(r['complete'])
        self.assertEqual(r['services'], [])
        self.assertEqual(self.scan(0, '--cached'), r)
        self.assertEqual((self.root / 'run/openwrt-needrestart/report.json').stat().st_mode & 0o777, 0o600)

    def test_replaced_executable_and_package_ownership(self):
        self.process()
        r = self.scan()
        s = r['services'][0]
        self.assertEqual(s['kind'], 'systemd')
        self.assertEqual(s['recommended_action'], "systemctl restart 'example.service'")
        f = s['processes'][0]['files'][0]
        self.assertEqual(f['reason'], 'replaced')
        self.assertEqual(f['package'], {'name': 'example', 'installed_version': '2-r1'})

    def test_replaced_library(self):
        self.process(file='usr/lib/libexample.so', executable=False)
        r = self.scan()
        self.assertEqual(r['services'][0]['processes'][0]['files'][0]['type'], 'loaded-code')

    def test_identical_library_replacement_is_not_outdated(self):
        self.process(file='usr/lib/libexample.so', executable=False, changed=False)
        self.assertEqual(self.scan()['services'], [])

    def test_removed_library(self):
        current, _, _ = self.process(file='usr/lib/libexample.so', executable=False)
        current.unlink()
        self.assertEqual(self.scan()['services'][0]['processes'][0]['files'][0]['reason'], 'removed')

    def test_unchanged_maps(self):
        self.process(deleted=False)
        self.assertEqual(self.scan()['services'], [])

    def test_deleted_data_and_memfd_ignored(self):
        _, _, proc = self.process(deleted=False)
        self.write('proc/123/maps', '1000-2000 rw-p 00000000 00:01 9 /tmp/data (deleted)\n'
                   '3000-4000 r-xp 00000000 00:01 8 /memfd:jit (deleted)\n')
        self.assertEqual(self.scan()['services'], [])

    def test_procd_slice_legacy_and_escaped_names(self):
        self.process(cgroup='/openwrt.slice/openwrt-my\\x2dservice.slice/openwrt-abc.scope')
        s = self.scan()['services'][0]
        self.assertEqual(s['kind'], 'procd')
        self.assertEqual(s['name'], 'my-service')
        self.assertEqual(s['recommended_action'], '/etc/init.d/my-service restart')

    def test_procd_degraded_placement_from_ubus(self):
        self.process(cgroup='/system.slice/openwrt-procd.service')
        self.json('ubus.json', {'dnsmasq': {'instances': {'main': {'pid': 123, 'running': True}}}})
        s = self.scan()['services'][0]
        self.assertEqual(s['kind'], 'procd')
        self.assertTrue(s['disruptive'])
        self.assertEqual(s['name'], 'dnsmasq')

    def test_multi_instance_service_grouping(self):
        self.process(pid=123, cgroup='/openwrt.slice/openwrt-example.slice/openwrt-1.scope')
        self.process(pid=124, cgroup='/openwrt.slice/openwrt-example.slice/openwrt-2.scope')
        s = self.scan()['services']
        self.assertEqual(len(s), 1)
        self.assertEqual(len(s[0]['processes']), 2)

    def test_supervisor_not_routine_restart(self):
        self.process()
        self.json('ownership.json', {'123': {'unit': 'openwrt-procd.service'}})
        s = self.scan()['services'][0]
        self.assertTrue(s['disruptive'])
        self.assertIn('Maintenance review', s['recommended_action'])
        self.assertNotIn('systemctl restart', s['recommended_action'])

    def test_user_service(self):
        self.process(cgroup='/user.slice/user-1000.slice/user@1000.service/app.slice/test.service')
        self.json('ownership.json', {'123': {'unit': 'test.service', 'user': True}})
        s = self.scan()['services'][0]
        self.assertEqual(s['kind'], 'user-service')
        self.assertIn('systemctl --user restart', s['recommended_action'])

    def test_unknown_ownership_does_not_become_scope_restart(self):
        self.process(cgroup='/unknown/test.scope')
        self.json('ownership.json', {'123': {'unit': 'test.scope'}})
        s = self.scan()['services'][0]
        self.assertEqual(s['kind'], 'unmanaged')
        self.assertNotIn('systemctl restart', s['recommended_action'])

    def test_process_exit_skipped(self):
        self.process()
        (self.root / 'proc/123/stat').unlink()
        self.assertEqual(self.scan()['services'], [])

    def test_inaccessible_maps_partial(self):
        self.process()
        (self.root / 'proc/123/maps').unlink()
        r = self.scan(2)
        self.assertFalse(r['complete'])
        self.assertEqual(r['processes_unreadable'], 1)

    def test_differing_overlay_identity_requires_content_evidence(self):
        _, _, proc = self.process(deleted=False, changed=False, executable=False)
        self.write('proc/123/maps', '1000-2000 r-xp 00000000 00:01 999 /usr/bin/example\n')
        self.assertEqual(self.scan()['services'], [])
        (proc / 'map_files/1000-2000').unlink()
        self.assertEqual(self.scan(2)['services'], [])

    def test_large_identical_elf_mapping(self):
        current, old, _ = self.process(deleted=False, changed=False, executable=False)
        for p in (current, old):
            with p.open('r+b') as f:
                f.truncate(112 * 1024 * 1024)
        self.write('proc/123/maps', '1000-2000 r-xp 00000000 00:01 999 /usr/bin/example\n')
        self.assertEqual(self.scan()['services'], [])
        with current.open('r+b') as f:
            f.seek(100 * 1024 * 1024)
            f.write(b'changed-code')
        self.assertEqual(self.scan()['services'][0]['processes'][0]['files'][0]['reason'],
                         'replaced')

    def test_elf_over_256_mib_and_late_difference(self):
        current, old, _ = self.process(deleted=False, changed=False, executable=False)
        for p in (current, old):
            with p.open('r+b') as f:
                f.truncate(300 * 1024 * 1024)
        self.write('proc/123/maps', '1000-2000 r-xp 00000000 00:01 999 /usr/bin/example\n')
        self.assertEqual(self.scan()['services'], [])
        with current.open('r+b') as f:
            f.seek(290 * 1024 * 1024)
            f.write(b'changed-code-near-end')
        self.assertEqual(self.scan()['services'][0]['processes'][0]['files'][0]['reason'],
                         'replaced')

    def sandbox_helper(self, matching=True, inventoried=True, executable='usr/bin/slirp4netns'):
        uid = os.getuid()
        if not uid:
            self.skipTest('sandbox helper fixture requires an ordinary host UID')
        current, old, proc = self.process(file=executable, deleted=False,
            changed=not matching, cgroup=f'/user.slice/user-{uid}.slice/user@{uid}.service/'
            'app.slice/example.service/runtime')
        (proc / 'root').unlink()
        empty = self.root / 'empty-sandbox'
        empty.mkdir()
        (proc / 'root').symlink_to(empty)
        (proc / 'test-exe').symlink_to(old)
        store = self.store(uid, local='c' * 64)
        store['containers'][0]['State']['ConmonPid'] = 124
        self.write('proc/124/comm', 'conmon\n')
        self.json('ownership.json', {str(pid): {'unit': 'example.service', 'user': True}
                                    for pid in (123, 124)})
        self.json('podman.json', [store] if inventoried else [])

    def test_sandboxed_host_network_helper(self):
        self.sandbox_helper()
        self.assertEqual(self.scan()['warnings'], [])

    def test_sandboxed_passt_helper(self):
        self.sandbox_helper(executable='usr/bin/passt')
        self.assertEqual(self.scan()['warnings'], [])

    def test_sandboxed_passt_avx2_helper(self):
        self.sandbox_helper(executable='usr/bin/passt.avx2')
        self.assertEqual(self.scan()['warnings'], [])

    def test_sandboxed_pasta_helper(self):
        self.sandbox_helper(executable='usr/bin/pasta')
        self.assertEqual(self.scan()['warnings'], [])

    def test_sandboxed_pasta_avx2_helper(self):
        self.sandbox_helper(executable='usr/bin/pasta.avx2')
        self.assertEqual(self.scan()['warnings'], [])

    def test_sandboxed_passt_lookalike_still_partial(self):
        self.sandbox_helper(executable='usr/bin/passt-unverified')
        self.assertFalse(self.scan(2)['complete'])

    def test_sandboxed_passt_mismatch_still_partial(self):
        self.sandbox_helper(executable='usr/bin/passt', matching=False)
        self.assertFalse(self.scan(2)['complete'])

    def test_sandboxed_passt_without_inventory_still_partial(self):
        self.sandbox_helper(executable='usr/bin/passt', inventoried=False)
        self.assertFalse(self.scan(2)['complete'])

    def test_unverified_sandbox_still_partial(self):
        self.sandbox_helper(matching=False)
        self.assertFalse(self.scan(2)['complete'])

    def test_uninventoried_sandbox_still_partial(self):
        self.sandbox_helper(inventoried=False)
        self.assertFalse(self.scan(2)['complete'])

    def test_sandboxed_host_helper_stale_library(self):
        self.sandbox_helper()
        self.write('usr/lib/helper.so', b'\x7fELFnew-library')
        old = self.write('old-helper.so', b'\x7fELFold-library')
        self.write('proc/123/maps', '1000-2000 r-xp 00000000 00:01 999 /usr/lib/helper.so\n')
        (self.root / 'proc/123/map_files/1000-2000').unlink()
        (self.root / 'proc/123/map_files/1000-2000').symlink_to(old)
        subject = self.scan()['services'][0]
        self.assertEqual(subject['kind'], 'user-service')
        self.assertEqual(subject['name'], 'example.service')

    def shared_helper(self):
        self.sandbox_helper(executable='usr/bin/passt')
        uid = os.getuid()
        self.write('proc/123/cgroup', f'0::/user.slice/user-{uid}.slice/'
                   f'user@{uid}.service/user.slice/rootless-netns-1234abcd.scope\n')
        self.process(pid=125, deleted=False, changed=False,
                     cgroup=f'/user.slice/user-{uid}.slice/libpod-' + 'a' * 64 + '.scope')
        self.json('ownership.json', {})
        store = self.store(uid, local='c' * 64)
        store['containers'][0]['State']['Pid'] = 125
        self.json('podman.json', [store])
        self.record = self.write(f'run/user/{uid}/containers/networks/rootless-netns/'
                                 'rootless-netns-conn.pid', '123\n')
        self.record.chmod(0o600)
        namespace = self.write('shared-user-namespace', '')
        namespace.chmod(0)
        for pid in (123, 125):
            self.write(f'proc/{pid}/ns/placeholder', '')
            (self.root / f'proc/{pid}/ns/user').symlink_to(namespace)

    def test_shared_bridge_network_helper(self):
        self.shared_helper()
        self.assertEqual(self.scan()['warnings'], [])

    def test_shared_helper_wrong_pid_record(self):
        self.shared_helper()
        self.record.write_text('999\n')
        self.assertFalse(self.scan(2)['complete'])

    def test_shared_helper_writable_pid_record(self):
        self.shared_helper()
        self.record.chmod(0o666)
        self.assertFalse(self.scan(2)['complete'])

    def test_shared_helper_symlink_pid_record(self):
        self.shared_helper()
        self.record.unlink()
        self.record.symlink_to(self.write('fake-record', '123\n'))
        self.assertFalse(self.scan(2)['complete'])

    def test_shared_helper_different_user_namespace(self):
        self.shared_helper()
        ns = self.root / 'proc/125/ns/user'
        ns.unlink()
        ns.symlink_to(self.write('other-namespace', ''))
        self.assertFalse(self.scan(2)['complete'])

    def test_shared_helper_wrong_container_identity(self):
        self.shared_helper()
        self.write('proc/125/cgroup', '0::/libpod-' + 'b' * 64 + '.scope\n')
        self.assertFalse(self.scan(2)['complete'])

    def test_shared_helper_without_inventory(self):
        self.shared_helper()
        self.json('podman.json', [])
        self.assertFalse(self.scan(2)['complete'])

    def test_shared_helper_stale_library(self):
        self.shared_helper()
        self.write('usr/lib/helper.so', b'\x7fELFnew-library')
        old = self.write('old-helper.so', b'\x7fELFold-library')
        self.write('proc/123/maps', '1000-2000 r-xp 00000000 00:01 999 /usr/lib/helper.so\n')
        mapping = self.root / 'proc/123/map_files/1000-2000'
        mapping.unlink()
        mapping.symlink_to(old)
        r = self.scan()
        self.assertEqual(r['warnings'], [])
        self.assertEqual(r['services'][0]['processes'][0]['files'][0]['path'], '/usr/lib/helper.so')

    def test_unknown_root_warning_identifies_process(self):
        self.sandbox_helper(matching=False)
        warning = self.scan(2)['warnings'][0]
        self.assertIn('PID 123', warning)
        self.assertIn('/usr/bin/slirp4netns', warning)
        self.assertIn('example.service/runtime', warning)

    def test_absolute_symlink_resolved_in_process_root(self):
        self.process(file='usr/lib/libexample.so', executable=False)
        (self.root / 'usr/lib/libexample.so').unlink()
        (self.root / 'usr/lib/libexample.so').symlink_to('/usr/lib/replacement.so')
        self.write('usr/lib/replacement.so', b'\x7fELFreplacement')
        self.assertEqual(self.scan()['services'][0]['processes'][0]['files'][0]['reason'], 'replaced')

    def browser_sandbox(self, changed=False):
        binary = 'usr/lib/firefox-esr/firefox-bin'
        current, old, child = self.process(file=binary, deleted=False, changed=changed,
            cgroup='/user.slice/user-1000.slice/session-c1.scope')
        _, _, parent = self.process(pid=124, file=binary, deleted=False, changed=False,
            cgroup='/user.slice/user-1000.slice/session-c1.scope')
        self.write('proc/124/maps', '')
        for proc in (child, parent):
            (proc / 'test-exe').symlink_to(old)
        prefix, fields = (child / 'stat').read_text().rsplit(') ', 1)
        fields = fields.split()
        fields[1] = '124'
        self.write('proc/123/stat', prefix + ') ' + ' '.join(fields))
        child.joinpath('root').unlink()
        sandbox = self.root / 'proc/900/fdinfo'
        sandbox.mkdir(parents=True)
        child.joinpath('root').symlink_to(sandbox)
        marker = self.write('proc/self/ns/mnt', 'mount-namespace')
        for proc in (child, parent):
            (proc / 'ns').mkdir()
            os.link(marker, proc / 'ns/mnt')
        self.json('ownership.json', {str(pid): {'unit': 'session-c1.scope'}
                                    for pid in (123, 124)})
        return current, old, child, parent

    def test_firefox_proc_chroot_is_host_application(self):
        self.browser_sandbox()
        r = self.scan()
        self.assertEqual(r['warnings'], [])
        self.assertEqual(r['services'], [])

    def test_firefox_proc_chroot_retains_stale_library_advice(self):
        _, _, child, _ = self.browser_sandbox()
        self.write('usr/lib/browser.so', b'\x7fELFnew-library')
        old = self.write('old-browser.so', b'\x7fELFold-library')
        self.write('proc/123/maps', '1000-2000 r-xp 00000000 00:01 999 /usr/lib/browser.so\n')
        (child / 'map_files/1000-2000').unlink()
        (child / 'map_files/1000-2000').symlink_to(old)
        s = self.scan()['services'][0]
        self.assertEqual(s['kind'], 'session')
        self.assertEqual(s['processes'][0]['files'][0]['path'], '/usr/lib/browser.so')

    def test_firefox_replaced_executable_still_detected(self):
        _, old, child, _ = self.browser_sandbox(changed=True)
        child.joinpath('exe').unlink()
        child.joinpath('exe').symlink_to('/usr/lib/firefox-esr/firefox-bin (deleted)')
        s = self.scan()['services'][0]
        self.assertEqual(s['kind'], 'session')
        self.assertEqual(s['processes'][0]['files'][0]['reason'], 'replaced')

    def test_firefox_unknown_parent_executable_stays_partial(self):
        _, _, _, parent = self.browser_sandbox()
        parent.joinpath('test-exe').unlink()
        parent.joinpath('test-exe').symlink_to(self.write('other-exe', b'\x7fELFother'))
        self.assertFalse(self.scan(2)['complete'])

    def test_firefox_private_mount_namespace_stays_partial(self):
        _, _, child, _ = self.browser_sandbox()
        (child / 'ns/mnt').unlink()
        self.write('proc/123/ns/mnt', 'private-namespace')
        self.assertFalse(self.scan(2)['complete'])

    def test_firefox_other_chroot_stays_partial(self):
        _, _, child, _ = self.browser_sandbox()
        child.joinpath('root').unlink()
        root = self.root / 'other-chroot'
        root.mkdir()
        child.joinpath('root').symlink_to(root)
        self.assertFalse(self.scan(2)['complete'])

    def flatpak(self, extensions=True):
        uid = os.getuid()
        if not uid:
            self.skipTest('Flatpak fixture requires an ordinary host UID')
        home = pwd.getpwuid(uid).pw_dir
        store = home + '/.local/share/flatpak'
        name = 'org.example.Needrestart'
        current, old, proc = self.process(file='app/bin/probe', executable=False,
            deleted=False, changed=False,
            cgroup=f'/user.slice/user-{uid}.slice/user@{uid}.service/app.slice/'
                   f'app-flatpak-{name}-42.scope')
        sandbox = self.root / 'flatpak-root'
        sandbox.mkdir()
        for file in ('app/bin/probe', 'usr/bin/interpreter'):
            dest = sandbox / file
            dest.parent.mkdir(parents=True, exist_ok=True)
            os.link(self.root / file, dest)
        proc.joinpath('root').unlink()
        proc.joinpath('root').symlink_to(sandbox)
        self.write('proc/123/maps', '1000-2000 r-xp 00000000 00:01 999 /app/bin/probe\n')
        namespace = self.write('proc/123/ns/mnt', 'flatpak-mount-namespace')
        def deploy(ref, commit):
            base = self.root / store.lstrip('/') / ref
            (base / commit / 'files').mkdir(parents=True)
            (base / 'active').symlink_to(commit)
            return f'{store}/{ref}/{commit}/files'
        app_path = deploy('app/' + name + '/x86_64/stable', 'a' * 64)
        runtime_path = deploy('runtime/org.example.Platform/x86_64/1.0', 'b' * 64)
        addon = ''
        if extensions:
            deploy('runtime/org.example.Addon/x86_64/1.0', 'c' * 64)
            addon = 'org.example.Addon=' + 'c' * 64
        info = (f'[Application]\nname={name}\nruntime=runtime/org.example.Platform/x86_64/1.0\n'
                f'[Instance]\ninstance-id=42\narch=x86_64\nbranch=stable\napp-path={app_path}\n'
                'app-commit=' + 'a' * 64 + f'\nruntime-path={runtime_path}\nruntime-commit=' +
                'b' * 64 + f'\napp-extensions={addon}\nruntime-extensions=\n'
                '[Environment]\nPRIVATE_VALUE=must-not-appear-in-report\n')
        (sandbox / '.flatpak-info').write_text(info)
        self.write(f'run/user/{uid}/.flatpak/42/info', info)
        self.json(f'run/user/{uid}/.flatpak/42/bwrapinfo.json',
                  {'child-pid': 123, 'mnt-namespace': namespace.stat().st_ino})
        return store, sandbox, uid

    def flatpak_proxy(self):
        store, sandbox, uid = self.flatpak()
        cg = (self.root / 'proc/123/cgroup').read_text().strip()[3:]
        _, old, proxy = self.process(pid=122, deleted=False, changed=False,
                                     file='usr/bin/xdg-dbus-proxy', cgroup=cg)
        empty = self.root / 'proxy-root'
        empty.mkdir()
        (empty / '.flatpak-info').write_bytes((sandbox / '.flatpak-info').read_bytes())
        (proxy / 'root').unlink()
        (proxy / 'root').symlink_to(empty)
        (proxy / 'test-exe').symlink_to(old)
        self.json('ownership.json', {})
        return proxy, empty, uid

    def test_flatpak_proxy_private_root_is_verified(self):
        self.flatpak_proxy()
        r = self.scan()
        self.assertTrue(r['complete'])
        self.assertEqual(len(r['applications']), 1)
        self.assertEqual(r['warnings'], [])

    def test_flatpak_proxy_retains_stale_host_library(self):
        proxy, _, _ = self.flatpak_proxy()
        self.write('usr/lib/proxy.so', b'\x7fELFnew')
        old = self.write('old-proxy.so', b'\x7fELFold')
        self.write('proc/122/maps', '1000-2000 r-xp 00000000 00:01 999 /usr/lib/proxy.so\n')
        (proxy / 'map_files/1000-2000').unlink()
        (proxy / 'map_files/1000-2000').symlink_to(old)
        r = self.scan()
        self.assertEqual(r['warnings'], [])
        self.assertEqual(r['services'][0]['kind'], 'flatpak')
        self.assertEqual(r['services'][0]['processes'][0]['files'][0]['path'], '/usr/lib/proxy.so')

    def test_flatpak_proxy_wrong_metadata_stays_partial(self):
        _, empty, _ = self.flatpak_proxy()
        p = empty / '.flatpak-info'
        p.write_text(p.read_text().replace('app-commit=' + 'a' * 64, 'app-commit=' + 'd' * 64))
        self.assertFalse(self.scan(2)['complete'])

    def test_flatpak_proxy_wrong_scope_stays_partial(self):
        self.flatpak_proxy()
        self.write('proc/122/cgroup', '0::/user.slice/user-1000.slice/app-flatpak-other-42.scope\n')
        self.assertFalse(self.scan(2)['complete'])

    def test_flatpak_proxy_wrong_executable_stays_partial(self):
        proxy, _, _ = self.flatpak_proxy()
        (proxy / 'test-exe').unlink()
        (proxy / 'test-exe').symlink_to(self.write('other-proxy', b'\x7fELFother'))
        self.assertFalse(self.scan(2)['complete'])

    def test_flatpak_proxy_missing_child_stays_partial(self):
        _, _, uid = self.flatpak_proxy()
        self.json(f'run/user/{uid}/.flatpak/42/bwrapinfo.json', {'child-pid': 999})
        self.assertFalse(self.scan(2)['complete'])

    def test_flatpak_current_and_private_environment_not_reported(self):
        self.flatpak()
        r = self.scan()
        self.assertEqual(r['applications'][0]['deployment_status'], 'current')
        self.assertEqual(r['services'], [])
        self.assertNotIn('PRIVATE_VALUE', json.dumps(r))
        self.assertNotIn('must-not-appear', json.dumps(r))

    def update_flatpak_ref(self, store, ref):
        base = self.root / store.lstrip('/') / ref
        (base / ('d' * 64) / 'files').mkdir(parents=True)
        (base / 'active').unlink()
        (base / 'active').symlink_to('d' * 64)

    def test_flatpak_app_update_advises_relaunch(self):
        store, _, _ = self.flatpak()
        self.update_flatpak_ref(store, 'app/org.example.Needrestart/x86_64/stable')
        r = self.scan()
        self.assertEqual(r['applications'][0]['deployment_status'], 'changed')
        self.assertEqual(r['services'][0]['kind'], 'flatpak')
        self.assertIn('Close and relaunch', r['services'][0]['recommended_action'])

    def test_flatpak_runtime_update_advises_relaunch(self):
        store, _, _ = self.flatpak()
        self.update_flatpak_ref(store, 'runtime/org.example.Platform/x86_64/1.0')
        self.assertEqual(self.scan()['services'][0]['kind'], 'flatpak')

    def test_flatpak_extension_update_advises_relaunch(self):
        store, _, _ = self.flatpak()
        self.update_flatpak_ref(store, 'runtime/org.example.Addon/x86_64/1.0')
        self.assertEqual(self.scan()['services'][0]['kind'], 'flatpak')

    def test_flatpak_missing_extension_stays_partial(self):
        store, _, _ = self.flatpak()
        shutil.rmtree(self.root / store.lstrip('/') / 'runtime/org.example.Addon')
        self.assertEqual(self.scan(2)['applications'][0]['deployment_status'], 'unknown')

    def test_flatpak_bad_namespace_stays_partial(self):
        _, _, uid = self.flatpak()
        self.json(f'run/user/{uid}/.flatpak/42/bwrapinfo.json',
                  {'child-pid': 123, 'mnt-namespace': 999})
        r = self.scan(2)
        self.assertEqual(r['applications'], [])

    def test_flatpak_mismatched_instance_info_stays_partial(self):
        _, _, uid = self.flatpak()
        self.write(f'run/user/{uid}/.flatpak/42/info', '[Application]\nname=org.wrong.App\n')
        self.assertEqual(self.scan(2)['applications'], [])

    def test_flatpak_foreign_store_stays_partial(self):
        _, sandbox, uid = self.flatpak()
        info = sandbox.joinpath('.flatpak-info').read_text().replace('app-path=/', 'app-path=/unverified/')
        sandbox.joinpath('.flatpak-info').write_text(info)
        self.write(f'run/user/{uid}/.flatpak/42/info', info)
        self.assertEqual(self.scan(2)['applications'][0]['deployment_status'], 'unknown')

    def test_flatpak_stale_code_remains_detected(self):
        _, sandbox, _ = self.flatpak()
        sandbox.joinpath('app/bin/probe').write_bytes(b'\x7fELFchanged-program')
        s = self.scan()['services'][0]
        self.assertEqual(s['kind'], 'flatpak')
        self.assertEqual(s['processes'][0]['files'][0]['reason'], 'replaced')

    def test_flatpak_extension_id_in_multiple_branches(self):
        store, sandbox, uid = self.flatpak()
        branch = self.root / store.lstrip('/') / 'runtime/org.example.Addon/x86_64/2.0'
        (branch / ('e' * 64) / 'files').mkdir(parents=True)
        (branch / 'active').symlink_to('e' * 64)
        info = sandbox.joinpath('.flatpak-info').read_text().replace(
            'runtime-extensions=\n', 'runtime-extensions=org.example.Addon=' + 'e' * 64 + '\n')
        sandbox.joinpath('.flatpak-info').write_text(info)
        self.write(f'run/user/{uid}/.flatpak/42/info', info)
        self.assertEqual(self.scan()['applications'][0]['extensions_status'], 'current')

    def test_flatpak_known_update_not_hidden_by_unknown_extension(self):
        store, _, _ = self.flatpak()
        self.update_flatpak_ref(store, 'app/org.example.Needrestart/x86_64/stable')
        shutil.rmtree(self.root / store.lstrip('/') / 'runtime/org.example.Addon')
        r = self.scan(2)
        self.assertEqual(r['applications'][0]['deployment_status'], 'changed')
        self.assertEqual(r['services'][0]['kind'], 'flatpak')

    def test_kernel_pending_different_abi(self):
        self.kernel(pending='candidate', abi='abi-two')
        self.assertEqual(self.scan()['kernel']['status'], 'reboot-pending')

    def test_kernel_same_abi_no_required_reboot(self):
        self.kernel(pending='candidate-g99')
        k = self.scan()['kernel']
        self.assertEqual(k['status'], 'optional-same-abi-trial')
        self.assertIn('no required kernel reboot', k['recommended_action'])

    def test_kernel_trial_already_running(self):
        self.kernel(pending='candidate', abi='abi-two', running='candidate')
        self.assertEqual(self.scan()['kernel']['status'], 'trial-running')

    def test_kernel_not_armed_or_failed_is_incomplete(self):
        self.kernel(pending='candidate', abi='abi-two')
        self.write('grubenv', '')
        self.assertEqual(self.scan(2)['kernel']['status'], 'activation-incomplete')
        self.kernel(pending='candidate', abi='abi-two', failed=True)
        self.assertEqual(self.scan(2)['kernel']['status'], 'activation-incomplete')

    def test_missing_kernel_state_unknown(self):
        (self.root / 'etc/openwrt-kernel/state.json').unlink()
        self.assertEqual(self.scan(2)['kernel']['status'], 'unknown')

    def test_large_kernel_inventory(self):
        p = self.root / 'etc/openwrt-kernel/state.json'
        state = json.loads(p.read_text())
        state['inventory'] = 'x' * (5 * 1024 * 1024)
        self.json('etc/openwrt-kernel/state.json', state)
        self.assertEqual(self.scan()['kernel']['status'], 'current')

    def test_kernel_inventory_input_remains_bounded(self):
        self.write('etc/openwrt-kernel/state.json', b' ' * (16 * 1024 * 1024 + 1))
        self.assertEqual(self.scan(2)['kernel']['status'], 'unknown')

    def test_adoption_incomplete_is_not_current(self):
        p = self.root / 'etc/openwrt-kernel/state.json'
        state = json.loads(p.read_text())
        state['phase'] = 'adopting'
        self.json('etc/openwrt-kernel/state.json', state)
        self.assertEqual(self.scan(2)['kernel']['status'], 'activation-incomplete')

    def test_selected_but_unarmed_kernel_is_not_current(self):
        self.json('usr/share/openwrt-kernel/selected.json', {'generation': 'other-kernel'})
        self.assertEqual(self.scan(2)['kernel']['status'], 'activation-incomplete')

    def store(self, uid=0, ref='example.org/test:latest', local='b' * 64):
        return {'uid': uid, 'containers': [{'Id': 'a' * 64, 'Name': 'test',
                'Image': 'c' * 64, 'ImageName': ref,
                'State': {'Running': True, 'Pid': 123}}],
                'images': [{'Id': local, 'Names': [ref]}]}

    def test_container_local_image_changes(self):
        self.json('podman.json', [self.store()])
        c = self.scan()['containers'][0]
        self.assertEqual(c['image_status'], 'changed')
        self.assertEqual(c['local_image'], 'b' * 64)

    def test_digest_pinned_not_affected_by_tags(self):
        self.json('podman.json', [self.store(ref='example.org/test@sha256:' + 'c' * 64)])
        self.assertEqual(self.scan()['containers'][0]['image_status'], 'digest-pinned')

    def test_rootless_store_separation(self):
        self.json('podman.json', [self.store(0, local='c' * 64), self.store(1000)])
        self.process(cgroup='/user.slice/user-1000.slice/user@1000.service/app.slice/libpod-' + 'a' * 64 + '.scope')
        r = self.scan()
        self.assertEqual([c['image_status'] for c in r['containers']], ['current', 'changed'])
        s = r['services'][0]
        self.assertEqual(s['kind'], 'container')
        self.assertEqual(s['container']['uid'], 1000)
        self.assertNotIn('package', s['processes'][0]['files'][0])

    def test_uninventoried_container_coverage_partial(self):
        self.process(cgroup='/machine.slice/libpod-' + 'a' * 64 + '.scope')
        r = self.scan(2)
        self.assertEqual(r['services'][0]['kind'], 'container')

    def test_podman_payload_cgroup(self):
        self.json('podman.json', [self.store()])
        self.process(cgroup='/system.slice/example.service/libpod-payload-' + 'a' * 64)
        r = self.scan()
        self.assertEqual(r['services'][0]['kind'], 'container')
        self.assertEqual(r['services'][0]['name'], 'a' * 64)

    def test_rootless_payload_cgroup(self):
        self.json('podman.json', [self.store(1000)])
        self.process(cgroup='/user.slice/user-1000.slice/user@1000.service/app.slice/'
                     'example.service/libpod-payload-' + 'a' * 64 + '/child')
        r = self.scan()
        self.assertEqual(r['services'][0]['kind'], 'container')
        self.assertEqual(r['services'][0]['container']['uid'], 1000)

    def test_invalid_container_cgroup_suffix(self):
        for i, suffix in enumerate(('.scope-extra', 'f.scope', '.scopex')):
            with self.subTest(suffix=suffix):
                self.process(pid=123 + i, cgroup='/system.slice/libpod-' + 'a' * 64 + suffix)
        r = self.scan()
        self.assertFalse(any(s['kind'] == 'container' for s in r['services']))

    def test_invalid_payload_cgroup_id(self):
        self.process(cgroup='/system.slice/libpod-payload-' + 'a' * 65)
        r = self.scan()
        self.assertNotEqual(r['services'][0]['kind'], 'container')

    def test_missing_local_reference_is_unknown(self):
        store = self.store()
        store['images'] = []
        self.json('podman.json', [store])
        self.assertEqual(self.scan(2)['containers'][0]['image_status'], 'unknown')

    def test_old_boot_cache_cannot_be_clean(self):
        self.scan()
        self.write('proc/sys/kernel/random/boot_id', 'another-boot\n')
        self.assertEqual(self.scan(2, '--cached')['scan_status'], 'stale')

    def test_worker_acknowledges_request_and_partial_reports(self):
        self.write('run/openwrt-needrestart/pending', 'request')
        os.chmod(self.root / 'run/openwrt-needrestart', 0o700)
        (self.root / 'etc/openwrt-kernel/state.json').unlink()
        r = self.scan(0, '--worker')
        self.assertEqual(r['scan_status'], 'partial')
        self.assertFalse((self.root / 'run/openwrt-needrestart/pending').exists())

    def test_apk_lock_wait_without_recursive_apk(self):
        with (self.root / 'lib/apk/db/lock').open() as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            p = self.call('--json')
        self.assertEqual(p.returncode, 1)
        self.assertIn('APK transaction is busy', p.stderr)
        self.assertFalse((self.root / 'run/openwrt-needrestart/report.json').exists())

    def test_first_boot_creates_only_apk_lock(self):
        database = (self.root / 'lib/apk/db/installed').read_bytes()
        (self.root / 'lib/apk/db/lock').unlink()
        self.scan()
        self.assertTrue((self.root / 'lib/apk/db/lock').is_file())
        self.assertEqual((self.root / 'lib/apk/db/installed').read_bytes(), database)

    def test_runtime_symlink_and_open_permissions_rejected(self):
        self.write('run/openwrt-needrestart/unrelated', '')
        p = self.call('--json')
        self.assertEqual(p.returncode, 1)
        self.assertIn('runtime', p.stderr)

    def test_no_restart_command_interface(self):
        p = self.call('--restart', 'example.service')
        self.assertEqual(p.returncode, 1)
        self.assertIn('Usage:', p.stderr)

    def test_production_has_no_fixture_interface(self):
        p = subprocess.run([*self.runner[:-1], str(self.production), '--test-root', str(self.root)],
                           capture_output=True, text=True, timeout=5)
        self.assertEqual(p.returncode, 1)
        self.assertIn('Usage:', p.stderr)

    def paused_scan(self, mutate, worker=False):
        self.process()
        self.write('proc/123/test-pause', '')
        argv = [*self.runner, '--test-root', str(self.root), '--json']
        if worker:
            argv.append('--worker')
        with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
            end = time.monotonic() + 5
            while not (self.root / 'proc/123/test-paused').exists():
                self.assertIsNone(process.poll())
                if time.monotonic() > end:
                    process.kill()
                    self.fail('Scanner did not reach synchronization point')
                time.sleep(.01)
            mutate()
            (self.root / 'proc/123/test-pause').unlink()
            stdout, stderr = process.communicate(timeout=10)
            return process.returncode, json.loads(stdout), stderr

    def test_pid_reuse_discards_old_evidence(self):
        def reuse():
            p = self.root / 'proc/123/stat'
            p.write_text(p.read_text().replace('100', '200'))
        code, report, _ = self.paused_scan(reuse)
        self.assertEqual(code, 0)
        self.assertEqual(report['services'], [])
        self.assertEqual(report['processes_exited'], 1)

    def test_comparison_cache_invalidates_changed_object(self):
        current, old, first = self.process(deleted=False, changed=False, executable=False)
        _, _, second = self.process(pid=124, deleted=False, changed=False, executable=False)
        (second / 'map_files/1000-2000').unlink()
        (second / 'map_files/1000-2000').symlink_to(old)
        for pid in (123, 124):
            self.write(f'proc/{pid}/maps',
                       '1000-2000 r-xp 00000000 00:01 999 /usr/bin/example\n')
        for pid in (123, 124):
            self.write(f'proc/{pid}/test-pause', '')
        argv = [*self.runner, '--test-root', str(self.root), '--json']
        with subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as p:
            end = time.monotonic() + 5
            paused = []
            while not paused:
                paused = [pid for pid in (123, 124)
                          if (self.root / f'proc/{pid}/test-paused').exists()]
                if paused:
                    break
                self.assertIsNone(p.poll())
                if time.monotonic() > end:
                    p.kill()
                    self.fail('Scanner did not reach cache synchronization point')
                time.sleep(.01)
            current.write_bytes(b'\x7fELFbad-version')
            for pid in (123, 124):
                (self.root / f'proc/{pid}/test-pause').unlink()
            stdout, stderr = p.communicate(timeout=10)
        self.assertEqual(p.returncode, 0, stderr)
        r = json.loads(stdout)
        self.assertEqual([proc['pid'] for s in r['services'] for proc in s['processes']],
                         [124 if paused[0] == 123 else 123])

    def test_state_change_keeps_worker_request_for_rescan(self):
        self.write('run/openwrt-needrestart/pending', 'one')
        os.chmod(self.root / 'run/openwrt-needrestart', 0o700)
        def mutate():
            self.kernel(pending='candidate', abi='abi-two')
        code, report, _ = self.paused_scan(mutate, worker=True)
        self.assertEqual(code, 0)
        self.assertFalse(report['complete'])
        self.assertTrue(report['changed_during_scan'])
        self.assertTrue((self.root / 'run/openwrt-needrestart/pending').exists())

    def test_new_request_survives_worker_acknowledgement(self):
        self.write('run/openwrt-needrestart/pending', 'one')
        os.chmod(self.root / 'run/openwrt-needrestart', 0o700)
        def mutate():
            self.write('run/openwrt-needrestart/request.new', 'two').replace(self.root / 'run/openwrt-needrestart/pending')
        code, report, _ = self.paused_scan(mutate, worker=True)
        self.assertEqual(code, 0)
        self.assertTrue(report['changed_during_scan'])
        self.assertEqual((self.root / 'run/openwrt-needrestart/pending').read_text(), 'two')


if __name__ == '__main__':
    unittest.main()
