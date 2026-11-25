#!/usr/bin/env python3
"""Host tests for udev/hotplug migration (Batches 2, 3, 4 and merge audit tool)."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import shutil
import stat
import subprocess
import tempfile
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
PROCD_SRC = next((ROOT / 'build_dir/target-x86_64_glibc/procd-default').glob('procd-*'), None)


class DesktopAudioSunshineBatch3Test(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory(prefix='udev-mig-b3-')
        self.addCleanup(self.td.cleanup)
        self.tmp = Path(self.td.name)
        self.bin = self.tmp / 'bin'
        self.bin.mkdir()
        self.env = dict(os.environ, PATH=f'{self.bin}:{os.environ["PATH"]}')

    def tool(self, name, body):
        p = self.bin / name
        p.write_text('#!/bin/sh\n' + body + '\n')
        p.chmod(0o755)
        return p

    def test_desktop_lock_fd1000_passing_and_concurrency(self):
        path = ROOT / 'package/custom/openwrt-desktop/files/desktop-ctl'
        loader = importlib.machinery.SourceFileLoader('desktop_ctl_lock_test', str(path))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        mod = importlib.util.module_from_spec(spec)
        loader.exec_module(mod)

        lock_file = self.tmp / 'procd_desktop.lock'
        mod.LOCK_FILE = lock_file
        with mod.desktop_op_lock() as lock_fds:
            self.assertEqual(lock_fds, (1000,))
            # Same-OFD fd 1000 passed to child (simulating rc.common procd_lock) succeeds immediately
            r_reentrant = subprocess.run(['sh', '-c', 'flock -n 1000'], pass_fds=lock_fds)
            self.assertEqual(r_reentrant.returncode, 0)
            # Independent process opening the lock file is blocked (flock -n fails)
            r_other = subprocess.run(['sh', '-c', f'exec 9>"{lock_file}"; flock -n 9'])
            self.assertNotEqual(r_other.returncode, 0)
        # After exiting context manager, another process acquires the lock cleanly
        r_after = subprocess.run(['sh', '-c', f'exec 9>"{lock_file}"; flock -n 9'])
        self.assertEqual(r_after.returncode, 0)

    def test_desktop_drm_notify_and_reconcile_claim_before_run(self):
        run_dir = self.tmp / 'run-drm'
        calls = self.tmp / 'calls.log'
        self.tool('chown', ':')
        self.tool('id', 'echo 0')
        self.tool('logger', ':')
        # Fake desktop init that creates a new pending marker mid-run to verify coalescing
        notify_src = (ROOT / 'package/custom/openwrt-desktop/files/desktop-drm-udev-notify').read_text()
        notify = self.tmp / 'notify'
        notify.write_text(notify_src.replace('/run/openwrt-desktop-drm', str(run_dir)))
        notify.chmod(0o755)

        fake_init = self.tool(
            'desktop-init',
            f'printf "%s pending=%s\\n" "$*" "$(test -e "{run_dir}/pending" && echo yes || echo no)" >> "{calls}"\n'
            f'if [ "${{EMIT_MIDRUN:-0}}" = 1 ]; then SEQNUM=99 ACTION=change DEVPATH=/dev/drm "{notify}"; fi\n'
            'exit "${INIT_RC:-0}"\n',
        )
        rec_src = (ROOT / 'package/custom/openwrt-desktop/files/desktop-drm-reconcile').read_text()
        reconcile = self.tmp / 'reconcile'
        reconcile.write_text(
            rec_src.replace('/run/openwrt-desktop-drm', str(run_dir))
            .replace('/etc/init.d/desktop', str(fake_init))
            .replace('sleep "$backoff"', 'printf "backoff=%s\\n" "$backoff" >> "' + str(calls) + '"')
        )
        reconcile.chmod(0o755)

        # udev notify creates private 0700 dir and pending file
        res = subprocess.run(['sh', str(notify)], env=dict(self.env, SEQNUM='42', ACTION='change', DEVPATH='/devices/drm'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual(stat.S_IMODE(run_dir.stat().st_mode), 0o700)
        self.assertTrue((run_dir / 'pending').is_file())

        # Reconcile claims pending BEFORE invoking init, and preserves mid-run pending marker
        res = subprocess.run(['sh', str(reconcile)], env=dict(self.env, EMIT_MIDRUN='1'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertIn('autostart pending=no', calls.read_text())
        self.assertTrue((run_dir / 'pending').is_file(), 'mid-run event must schedule follow-up pass')

        # Failure applies bounded backoff and does not leave pending marker behind
        res = subprocess.run(['sh', str(reconcile)], env=dict(self.env, INIT_RC='1'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertFalse((run_dir / 'pending').exists())
        self.assertIn('backoff=1', calls.read_text())

    def test_audio_acl_user_switch_and_vanished_node_tolerance(self):
        run_dir = self.tmp / 'run-audio'
        snd_dir = self.tmp / 'dev-snd'
        snd_dir.mkdir()
        n0 = snd_dir / 'controlC0'
        n1 = snd_dir / 'pcmC0D0p'
        n0.write_text('')
        n1.write_text('')

        common = self.tmp / 'common.sh'
        common.write_text(
            'desktop_validate_user() {\n'
            '  case "$1" in alice) DESKTOP_USER_UID=1000;; bob) DESKTOP_USER_UID=1001;; *) return 1;; esac\n'
            '}\n'
        )
        acl_log = self.tmp / 'acl.log'
        self.tool('id', 'echo 0')
        self.tool('chown', ':')
        self.tool('logger', ':')
        self.tool('uci', 'case "$*" in *audio_enabled*) echo "${AUDIO_EN:-1}";; *audio_user*|*main.user*) echo "${CUR_USER:-alice}";; esac')
        # Simulate controlC0 vanishing mid-enumeration when VANISH=1
        self.tool(
            'setfacl',
            f'printf "%s\\n" "$*" >> "{acl_log}"\n'
            f'if [ "${{VANISH:-0}}" = 1 ] && [ "$3" = "{n0}" ]; then rm -f "{n0}"; exit 1; fi\n'
            'exit 0\n',
        )

        src = (ROOT / 'package/custom/openwrt-desktop-audio/files/desktop-audio-permissions').read_text()
        script = self.tmp / 'audio-perms'
        script.write_text(
            src.replace('/usr/libexec/desktop-common.sh', str(common))
            .replace('/run/openwrt-desktop-audio', str(run_dir))
            .replace('/run/desktop-audio-acl-uid', str(self.tmp / 'legacy-uid'))
            .replace('/dev/snd', str(snd_dir))
            .replace('[ -c "$node" ]', '[ -f "$node" ]')
        )
        script.chmod(0o755)

        # Grant alice (1000)
        res = subprocess.run(['sh', str(script)], env=dict(self.env, CUR_USER='alice'), capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        self.assertEqual((run_dir / 'acl-uid').read_text().strip(), '1000')
        self.assertIn(f'-m u:1000:rw {n0}', acl_log.read_text())
        self.assertIn(f'-m u:1000:rw {n1}', acl_log.read_text())

        # Switch to bob (1001) while controlC0 vanishes mid-enumeration -> pcmC0D0p MUST still converge!
        acl_log.unlink()
        res = subprocess.run(['sh', str(script)], env=dict(self.env, CUR_USER='bob', VANISH='1'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        log_text = acl_log.read_text()
        self.assertIn(f'-x u:1000 {n1}', log_text)
        self.assertIn(f'-m u:1001:rw {n1}', log_text)
        self.assertEqual((run_dir / 'acl-uid').read_text().strip(), '1001')

    def test_sunshine_uinput_only_never_grants_kms_and_revocation_cleans_acls(self):
        run_dir = self.tmp / 'run-sunshine'
        state_file = self.tmp / 'sunshine-users'
        state_file.write_text('alice\n')
        state_file.chmod(0o600)
        uinput = self.tmp / 'uinput'
        uinput.write_text('')
        sun_bin = self.tmp / 'sunshine-bin'
        sun_bin.write_text('bin')

        common = self.tmp / 'common.sh'
        common.write_text(
            'desktop_validate_user() {\n'
            '  case "$1" in alice) DESKTOP_USER_UID=1000;; bob) DESKTOP_USER_UID=1001;; *) return 1;; esac\n'
            '}\n'
        )
        ops_log = self.tmp / 'ops.log'
        self.tool('id', 'case "$1" in -u) echo 0;; -Gn) echo "users sunshine";; esac')
        self.tool('chown', f'printf "chown %s\\n" "$*" >> "{ops_log}"')
        self.tool('chmod', f'printf "chmod %s\\n" "$*" >> "{ops_log}"')
        self.tool('stat', 'case "$2" in %u:%a) echo "0:600";; %U:%G:%a) echo "root:sunshine:750";; esac')
        self.tool('setfacl', f'printf "setfacl %s\\n" "$*" >> "{ops_log}"')
        self.tool('getcap', 'echo "${CUR_CAP:-}"')
        self.tool('setcap', f'printf "setcap %s\\n" "$*" >> "{ops_log}"')
        self.tool('uci', 'case "$*" in *sunshine_capture*) echo "${CAP_MODE:-portal}";; *main.user*) echo "${CUR_USER:-alice}";; esac')

        src = (ROOT / 'package/custom/sunshine/files/sunshine-permissions').read_text()
        script = self.tmp / 'sunshine-perms'
        script.write_text(
            src.replace('/usr/libexec/desktop-common.sh', str(common))
            .replace('/run/openwrt-sunshine', str(run_dir))
            .replace('/etc/desktop/sunshine-users', str(state_file))
            .replace('/dev/uinput', str(uinput))
            .replace('/usr/bin/sunshine', str(sun_bin))
            .replace('[ -c ', '[ -f ')
        )
        script.chmod(0o755)

        # 1. --uinput-only (even if UCI says kms!) MUST NOT touch binary or call setcap!
        res = subprocess.run(['sh', str(script), '--uinput-only'],
                             env=dict(self.env, CAP_MODE='kms', CUR_USER='alice'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        ops = ops_log.read_text()
        self.assertIn(f'setfacl -m u:1000:rw {uinput}', ops)
        self.assertNotIn('setcap', ops)
        self.assertNotIn(str(sun_bin), ops)

        # 2. Full mode in portal mode strips existing KMS capability and never grants it
        ops_log.unlink()
        res = subprocess.run(['sh', str(script)],
                             env=dict(self.env, CAP_MODE='portal', CUR_USER='alice',
                                      CUR_CAP=f'{sun_bin} cap_sys_admin=p'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        ops = ops_log.read_text()
        self.assertIn(f'setcap -r {sun_bin}', ops)
        self.assertNotIn('cap_sys_admin+p', ops)

        # 3. Switch user alice -> bob cleans alice's old uinput and binary ACLs
        ops_log.unlink()
        state_file.write_text('bob\n')
        res = subprocess.run(['sh', str(script)],
                             env=dict(self.env, CAP_MODE='kms', CUR_USER='bob'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        ops = ops_log.read_text()
        self.assertIn(f'setfacl -x u:1000 {sun_bin}', ops)
        self.assertIn(f'setfacl -m u:1001:rx {sun_bin}', ops)
        self.assertIn(f'setcap cap_sys_admin+p {sun_bin}', ops)
        self.assertIn(f'setfacl -x u:1000 {uinput}', ops)
        self.assertIn(f'setfacl -m u:1001:rw {uinput}', ops)

        # 4. Revocation (empty enrollment file) cleans bob's ACLs and strips KMS capability
        ops_log.unlink()
        state_file.write_text('')
        res = subprocess.run(['sh', str(script)],
                             env=dict(self.env, CUR_CAP=f'{sun_bin} cap_sys_admin=p'),
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stderr)
        ops = ops_log.read_text()
        self.assertIn(f'setfacl -x u:1001 {uinput}', ops)
        self.assertIn(f'setfacl -x u:1001 {sun_bin}', ops)
        self.assertIn(f'setcap -r {sun_bin}', ops)

    def test_compat_hotplug_adapters_respect_udev_origin_marker(self):
        calls = self.tmp / 'compat.log'
        fake_audio = self.tool('audio-perms', f'echo audio >> "{calls}"')
        fake_sun = self.tool('sun-perms', f'echo "sun $*" >> "{calls}"')
        self.tool('systemctl', 'exit 3')

        audio_hp = self.tmp / '95-audio'
        audio_hp.write_text(
            (ROOT / 'package/custom/openwrt-desktop-audio/files/desktop-audio.hotplug').read_text()
            .replace('/usr/libexec/desktop-audio-permissions', str(fake_audio))
            .replace('/run/openwrt-desktop-audio', str(self.tmp / 'no-audio'))
        )
        sun_hp = self.tmp / '95-sun'
        sun_hp.write_text(
            (ROOT / 'package/custom/sunshine/files/sunshine.hotplug').read_text()
            .replace('/usr/libexec/sunshine-permissions', str(fake_sun))
            .replace('/run/openwrt-sunshine', str(self.tmp / 'no-sun'))
        )

        # With udev marker -> skipped (no duplicate submission)
        subprocess.run(['sh', str(audio_hp)], env=dict(self.env, ACTION='add', OPENWRT_UDEV_HANDLED_AUDIO='1'), check=True)
        subprocess.run(['sh', str(sun_hp)], env=dict(self.env, ACTION='add', DEVNAME='uinput', OPENWRT_UDEV_HANDLED_SUNSHINE='1'), check=True)
        self.assertFalse(calls.exists())

        # Without udev marker (explicit hotplug-call / ubus call) -> invokes shared policy
        subprocess.run(['sh', str(audio_hp)], env=dict(self.env, ACTION='add'), check=True)
        subprocess.run(['sh', str(sun_hp)], env=dict(self.env, ACTION='add', DEVNAME='uinput'), check=True)
        self.assertEqual(calls.read_text().splitlines(), ['audio', 'sun --uinput-only'])

    def test_path_units_do_not_order_after_basic_target_services(self):
        for unit in (
            ROOT / 'package/custom/openwrt-desktop/files/openwrt-desktop-drm.path',
            ROOT / 'package/custom/openwrt-desktop-audio/files/openwrt-desktop-audio-acl.path',
            ROOT / 'package/custom/sunshine/files/openwrt-sunshine-uinput.path',
        ):
            text = unit.read_text()
            self.assertNotIn('After=openwrt-services.service', text, str(unit))
            self.assertNotIn('After=openwrt-procd.service', text, str(unit))
            self.assertIn('PathExists=/run/', text, str(unit))
            self.assertIn('TriggerLimitIntervalSec=', text, str(unit))


class HotplugQueueBatch4CTest(unittest.TestCase):
    def test_c_queue_concurrency_dedup_overflow_and_cap(self):
        procd_src = next((ROOT / 'build_dir/target-x86_64_glibc/procd-default').glob('procd-*'), None)
        if not procd_src or not (procd_src / 'hotplug-queue.c').is_file():
            self.skipTest('procd hotplug-queue.c not unpacked in build_dir')

        use_target = False
        pkg = subprocess.run(['pkg-config', '--cflags', '--libs', 'json-c'], capture_output=True, text=True)
        if pkg.returncode == 0 and shutil.which('gcc'):
            compiler = ['gcc']
            extra_flags = pkg.stdout.split()
            runner_prefix = []
        else:
            tc_gcc = next((ROOT / 'staging_dir').glob('toolchain-x86_64_gcc-*_glibc/bin/x86_64-openwrt-linux-gnu-gcc'), None)
            sysroot_lib = ROOT / 'staging_dir/target-x86_64_glibc/root-x86-systemd/usr/lib'
            stage_inc = ROOT / 'staging_dir/target-x86_64_glibc/usr/include'
            stage_lib = ROOT / 'staging_dir/target-x86_64_glibc/usr/lib'
            if not (tc_gcc and (sysroot_lib / 'ld-linux-x86-64.so.2').is_file() and (stage_inc / 'json-c/json.h').is_file()):
                self.skipTest('neither host json-c nor target OpenWrt toolchain is available')
            use_target = True
            compiler = [str(tc_gcc)]
            extra_flags = [f'-I{stage_inc}', f'-L{stage_lib}', '-ljson-c']
            runner_prefix = [str(sysroot_lib / 'ld-linux-x86-64.so.2'), '--library-path', f'{sysroot_lib}:{stage_lib}']

        with tempfile.TemporaryDirectory(prefix='hq-ctest-') as td:
            t = Path(td)
            stub_hdr = t / 'libubox'
            stub_hdr.mkdir()
            (stub_hdr / 'blobmsg.h').write_text(
                '#ifndef _STUB_BLOBMSG_H\n#define _STUB_BLOBMSG_H\n'
                'struct blob_attr { int dummy; };\n'
                '#define BLOBMSG_TYPE_STRING 3\n'
                '#define blobmsg_for_each_attr(pos, attr, rem) for ((void)(pos),(void)(attr),(void)(rem); 0; )\n'
                'static inline int blobmsg_type(const struct blob_attr *a) { return 0; }\n'
                'static inline const char *blobmsg_name(const struct blob_attr *a) { return ""; }\n'
                'static inline const char *blobmsg_get_string(const struct blob_attr *a) { return ""; }\n'
                '#endif\n'
            )
            driver = t / 'driver.c'
            driver.write_text(r'''
#define _GNU_SOURCE
#include <assert.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/wait.h>
#include <unistd.h>
#include "hotplug-queue.h"

int main(int argc, char **argv)
{
	const char *dir = argv[1];
	char id1[64], id2[64];
	size_t items = 0, bytes = 0;
	struct hotplug_queue_stats st;

	assert(!hotplug_queue_receiver_active(dir));
	assert(hotplug_queue_init_dirs(dir) == 0);
	assert(!hotplug_queue_receiver_active(dir));
	assert(hotplug_queue_write_cap(dir, getpid()) == 0);
	assert(hotplug_queue_receiver_active(dir));

	/* Dedup same (boot_id, SEQNUM), allow distinct replay SEQNUM and direct calls */
	char *env1[] = { "SUBSYSTEM=mem", "ACTION=change", "DEVPATH=/devices/virtual/mem/null", "SEQNUM=100", NULL };
	char *env2[] = { "SUBSYSTEM=mem", "ACTION=change", "DEVPATH=/devices/virtual/mem/null", "SEQNUM=101", NULL };
	char *env_direct[] = { "SUBSYSTEM=mem", "ACTION=change", "DEVPATH=/devices/virtual/mem/null", NULL };

	assert(hotplug_queue_enqueue_envp(dir, env1, id1, sizeof(id1)) == HQ_ENQ_OK);
	assert(hotplug_queue_enqueue_envp(dir, env1, id2, sizeof(id2)) == HQ_ENQ_DEDUP);
	assert(hotplug_queue_enqueue_envp(dir, env2, id2, sizeof(id2)) == HQ_ENQ_OK);
	assert(strcmp(id1, id2) < 0);
	assert(hotplug_queue_enqueue_envp(dir, env_direct, NULL, 0) == HQ_ENQ_OK);
	assert(hotplug_queue_enqueue_envp(dir, env_direct, NULL, 0) == HQ_ENQ_OK);

	/* Concurrent writers across 4 child processes * 20 events = 80 events */
	for (int p = 0; p < 4; p++) {
		pid_t pid = fork();
		if (pid == 0) {
			for (int k = 0; k < 20; k++) {
				char seq[32];
				snprintf(seq, sizeof(seq), "SEQNUM=%d", 1000 + p * 100 + k);
				char *e[] = { "SUBSYSTEM=misc", "ACTION=change", "DEVPATH=/devices/test", seq, NULL };
				assert(hotplug_queue_enqueue_envp(dir, e, NULL, 0) == HQ_ENQ_OK);
			}
			_exit(0);
		}
	}
	for (int p = 0; p < 4; p++) {
		int status = 0;
		wait(&status);
		assert(WIFEXITED(status) && WEXITSTATUS(status) == 0);
	}

	char pending[512];
	snprintf(pending, sizeof(pending), "%s/pending", dir);
	assert(hotplug_queue_count_dir(pending, &items, &bytes) == 0);
	assert(items == 84);
	assert(hotplug_queue_read_stats(dir, &st) == 0);
	assert(st.deduped == 1);
	assert(st.next_seq == 84);

	/* ID validation rejects traversal */
	assert(hotplug_queue_valid_id("0000000000000001"));
	assert(!hotplug_queue_valid_id("../etc/passwd"));
	assert(!hotplug_queue_valid_id("a/b"));
	assert(!hotplug_queue_valid_id(""));

	/* Prune directory bounds items */
	assert(hotplug_queue_prune_dir(pending, 10, 8 * 1024 * 1024) == 0);
	assert(hotplug_queue_count_dir(pending, &items, &bytes) == 0);
	assert(items == 10);

	/* Fill up to HOTPLUG_QUEUE_MAX_ITEMS and verify overflow rejects cleanly */
	for (int i = 0; i < HOTPLUG_QUEUE_MAX_ITEMS - 10; i++) {
		char *e[] = { "SUBSYSTEM=misc", "ACTION=add", "DEVPATH=/devices/fill", NULL };
		assert(hotplug_queue_enqueue_envp(dir, e, NULL, 0) == HQ_ENQ_OK);
	}
	char *extra[] = { "SUBSYSTEM=misc", "ACTION=add", "DEVPATH=/devices/overflow", NULL };
	assert(hotplug_queue_enqueue_envp(dir, extra, NULL, 0) == HQ_ENQ_OVERFLOW);
	assert(hotplug_queue_count_dir(pending, &items, &bytes) == 0);
	assert(items == HOTPLUG_QUEUE_MAX_ITEMS);
	assert(hotplug_queue_read_stats(dir, &st) == 0);
	assert(st.overflow == 1);

	printf("C_QUEUE_TESTS_OK\n");
	return 0;
}
''')
            binary = t / 'test_hq'
            cmd = [
                *compiler, '-Wall', '-Werror', '-std=gnu99',
                f'-I{t}', f'-I{procd_src}',
                str(driver), str(procd_src / 'hotplug-queue.c'),
                '-o', str(binary), *extra_flags,
            ]
            comp = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(comp.returncode, 0, comp.stdout + comp.stderr)
            qdir = t / 'queue'
            run = subprocess.run([*runner_prefix, str(binary), str(qdir)], capture_output=True, text=True, timeout=60)
            self.assertEqual(run.returncode, 0, f'use_target={use_target}\n' + run.stdout + run.stderr)
            self.assertIn('C_QUEUE_TESTS_OK', run.stdout)


class MergeAuditToolTest(unittest.TestCase):
    def test_current_tree_passes_strict_audit(self):
        res = subprocess.run(['python3', str(ROOT / 'scripts/audit-hotplug-merge.py'), '--json'],
                             capture_output=True, text=True)
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        data = json.loads(res.stdout)
        self.assertTrue(data['ok'])
        self.assertEqual(data['classifications']['unclassified'], [])
        self.assertEqual(data['classifications']['hash_mismatches'], [])
        self.assertGreaterEqual(data['classifications']['discovered_count'], 14)

    def test_tampered_classification_blocks_acceptance(self):
        with tempfile.TemporaryDirectory(prefix='audit-test-') as td:
            bad = Path(td) / 'bad.json'
            orig = json.loads((ROOT / 'configs/hotplug-merge-classifications.json').read_text())
            orig['json_files']['package/system/hardware-support/files/20-audio.json']['sha256'] = '0' * 64
            bad.write_text(json.dumps(orig))
            res = subprocess.run(
                ['python3', str(ROOT / 'scripts/audit-hotplug-merge.py'),
                 '--classifications', str(bad), '--json'],
                capture_output=True, text=True,
            )
            self.assertNotEqual(res.returncode, 0)
            data = json.loads(res.stdout)
            self.assertFalse(data['ok'])
            self.assertEqual(len(data['classifications']['hash_mismatches']), 1)

    def test_detects_upstream_audio_support_split_commit(self):
        chk = subprocess.run(['git', '-C', str(ROOT), 'rev-parse', '--verify', 'e06e3a621b'],
                             capture_output=True, text=True)
        if chk.returncode != 0:
            self.skipTest('e06e3a621b not in local git history')
        res = subprocess.run(
            ['python3', str(ROOT / 'scripts/audit-hotplug-merge.py'),
             '--repo', f'main={ROOT}:e06e3a621b~1:e06e3a621b', '--json'],
            capture_output=True, text=True,
        )
        self.assertEqual(res.returncode, 0, res.stdout + res.stderr)
        data = json.loads(res.stdout)
        repo = data['repos'][0]
        hw_paths = {x['path'] for x in repo['hardware_support']}
        self.assertIn('package/system/hardware-support/files/20-audio.json', hw_paths)
        json_paths = {x['path'] for x in repo['stock_or_preinit_json']}
        self.assertIn('package/system/procd/files/hotplug.json', json_paths)


if __name__ == '__main__':
    unittest.main()
