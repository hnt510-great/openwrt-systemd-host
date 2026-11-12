#!/usr/bin/env python3
"""Interrupt the patched APK in disposable chroots and finish its transactions.

Run with sudo access. APK_TRANSACTION_APK selects the patched APK under test
(default: staging_dir/host/bin/apk); the host APK database is never used.
"""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
APK = os.environ.get('APK_TRANSACTION_APK', str(TREE / 'staging_dir/host/bin/apk'))
BUILDER = os.environ.get('APK_TRANSACTION_BUILDER', APK)
RESUME = TREE / 'package/custom/apk-transaction-guard/files/apk-resume'
# The router runs apk-resume with BusyBox ash; APK_RESUME_SHELL='busybox ash' checks that.
SHELL = os.environ.get('APK_RESUME_SHELL', 'sh').split()


def patched():
    try:
        return b'openwrt-resume' in Path(APK).read_bytes()
    except OSError:
        return False


# One static helper serves as every maintainer script and commit hook. It logs
# each call and, when /etc/kill-on-<APK_SCRIPT> exists, removes that marker
# and sends the signal number written in it to its parent (apk).
HELPER = r'''
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>
int main(int argc, char **argv) {
 const char *kind = getenv("APK_SCRIPT");
 char path[256]; int sig = 0;
 FILE *log = fopen("/run/script-log", "a");
 if (log) { fprintf(log, "%s %s\n", kind ? kind : "-", argc > 1 ? argv[1] : "-"); fclose(log); }
 snprintf(path, sizeof path, "/etc/kill-on-%s", kind ? kind : "-");
 FILE *marker = fopen(path, "r");
 if (marker) {
  if (fscanf(marker, "%d", &sig) != 1) sig = 0;
  fclose(marker);
  unlink(path);
  if (sig) kill(getppid(), sig);
  if (sig == SIGKILL) sleep(5);
 }
 return 0;
}
'''


@unittest.skipUnless(patched(), 'Set APK_TRANSACTION_APK to an APK carrying the journal patch')
class JournalTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.work = Path(self.temp.name)
        self.addCleanup(self.cleanup)
        self.root = self.work / 'root'; self.root.mkdir()
        self.repo = self.work / 'repo'; self.repo.mkdir()
        self.key = self.work / 'private.pem'
        subprocess.run(['openssl', 'ecparam', '-name', 'prime256v1', '-genkey', '-noout', '-out', str(self.key)],
                       check=True)
        subprocess.run(['openssl', 'ec', '-in', str(self.key), '-pubout', '-out', str(self.work / 'public.pem')],
                       check=True, capture_output=True)
        self.helper = self.work / 'helper'
        source = self.work / 'helper.c'
        source.write_text(HELPER)
        subprocess.run(['cc', '-static', '-O2', str(source), '-o', str(self.helper)], check=True)
        for name, dependencies in (('alpha', ''), ('beta', 'alpha=1-r1'), ('gamma', 'beta=1-r1'), ('obsolete', '')):
            self.pkg(name, '1-r1', 'usr/share/' + name, b'one', dependencies)
        self.index()
        self.apk('add', '--initdb', '--no-scripts', 'gamma', 'obsolete')
        self.sudo('chown', '-R', '%d:%d' % (os.getuid(), os.getgid()), str(self.root))
        for path in self.repo.glob('*.apk'):
            path.unlink()
        for name, dependencies in (('alpha', ''), ('beta', 'alpha=1-r2'), ('gamma', 'beta=1-r2')):
            self.pkg(name, '1-r2', 'usr/share/' + name, b'two', dependencies)
        self.index()
        for name in ('run', 'etc/apk/commit_hooks.d'):
            (self.root / name).mkdir(parents=True, exist_ok=True)
        hook = self.root / 'etc/apk/commit_hooks.d/50-probe'
        hook.write_bytes(self.helper.read_bytes()); hook.chmod(0o755)
        (self.root / 'etc/apk/world').write_text('gamma\n')
        self.sudo('chown', '-R', 'root:root', str(self.root))

    def cleanup(self):
        self.sudo('chown', '-R', '%d:%d' % (os.getuid(), os.getgid()), str(self.work))
        self.temp.cleanup()

    def sudo(self, *args, check=True):
        return subprocess.run(['sudo', '-n', *args], check=check, capture_output=True, text=True)

    def pkg(self, name, version, path, data, dependencies=''):
        with tempfile.TemporaryDirectory(dir=self.work) as temp:
            files = Path(temp) / 'files'
            target = files / path; target.parent.mkdir(parents=True); target.write_bytes(data)
            args = [BUILDER, 'mkpkg', '--info', 'name:' + name, '--info', 'version:' + version,
                    '--info', 'arch:x86_64', '--info', 'depends:' + dependencies,
                    '--sign', str(self.key), '--files', str(files),
                    '--script', 'post-upgrade:' + str(self.helper),
                    '--script', 'post-install:' + str(self.helper),
                    '--output', str(self.repo / (name + '-' + version + '.apk'))]
            subprocess.run(args, check=True, capture_output=True)

    def index(self):
        subprocess.run([BUILDER, 'mkndx', '--keys-dir', str(self.work), '--sign-key', str(self.key), '--output',
                        str(self.repo / 'packages.adb'), *map(str, sorted(self.repo.glob('*.apk')))],
                       check=True, capture_output=True)

    def base(self):
        return ['--root', str(self.root), '--keys-dir', str(self.work), '--no-logfile']

    def apk(self, *args, code=0):
        command = ['sudo', '-n', 'env', 'APK_OPENWRT_JOURNAL=1', APK, *self.base(),
                   '--repositories-file', '/dev/null', '--repository', str(self.repo / 'packages.adb'),
                   '--no-cache', *args]
        result = subprocess.run(command, capture_output=True, text=True)
        if code is not None:
            self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def resume(self, *args, code=0):
        environment = ['APK_OPENWRT_JOURNAL=1', 'APK_RESUME_APK=' + APK,
                       'APK_RESUME_ARGS=--keys-dir %s --no-logfile' % self.work]
        result = subprocess.run(['sudo', '-n', 'env', *environment, *SHELL, str(RESUME), '--root', str(self.root), *args],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, code, result.stdout + result.stderr)
        return result

    def mark(self, kind, signal):
        self.sudo('sh', '-c', 'echo %d > %s' % (signal, self.root / ('etc/kill-on-' + kind)))

    def installed(self):
        result = {}
        text = self.sudo('cat', str(self.root / 'lib/apk/db/installed')).stdout
        for record in text.split('\n\n'):
            data = dict(line.split(':', 1) for line in record.splitlines() if len(line) > 2 and line[1] == ':')
            if 'P' in data:
                result[data['P']] = data['V']
        return result

    def exists(self, path):
        return self.sudo('test', '-e', str(self.root / path), check=False).returncode == 0

    def read(self, path):
        return self.sudo('cat', str(self.root / path)).stdout

    def journal(self):
        return self.read('lib/apk/db/transaction/journal')

    def assert_upgraded(self):
        self.assertEqual(self.installed(), {'alpha': '1-r2', 'beta': '1-r2', 'gamma': '1-r2'})
        for name in ('alpha', 'beta', 'gamma'):
            self.assertEqual(self.read('usr/share/' + name), 'two')
        self.assertFalse(self.exists('usr/share/obsolete'))
        self.assertFalse(self.exists('lib/apk/db/transaction'))

    def test_clean_upgrade_leaves_no_journal(self):
        self.apk('upgrade')
        self.assert_upgraded()

    def deferred(self, signal):
        self.mark('post-upgrade', signal)
        result = self.apk('upgrade', code=128 + signal)
        self.assertIn('stopping after the database is written', result.stderr)
        self.assert_upgraded()

    def test_interrupt_is_deferred_until_the_database_is_written(self):
        self.deferred(2)

    def test_hangup_is_deferred_until_the_database_is_written(self):
        self.deferred(1)

    def test_terminate_is_deferred_until_the_database_is_written(self):
        self.deferred(15)

    def test_sigkill_during_packages_is_finished_offline(self):
        self.mark('post-upgrade', 9)
        self.apk('upgrade', code=None)
        self.assertTrue(self.exists('lib/apk/db/transaction/journal'))
        self.assertFalse(self.exists('lib/apk/db/transaction/phase-database'))
        journal = self.journal()
        mode = self.sudo('stat', '-c', '%a', str(self.root / 'lib/apk/db/transaction')).stdout.strip()
        self.assertEqual(mode, '700')
        self.assertIn('payloads 1', journal)
        self.assertIn('world gamma', journal)
        self.assertEqual(sum(line.startswith('change ') for line in journal.splitlines()), 4)
        self.assertIn('change obsolete 1-r1 - - 0 -', journal)
        # The database still describes the old packages; the first files are new.
        self.assertEqual(self.installed()['alpha'], '1-r1')
        self.assertEqual(self.read('usr/share/alpha'), 'two')
        refused = self.apk('add', 'alpha', code=None)
        self.assertNotEqual(refused.returncode, 0)
        self.assertIn('interrupted', refused.stderr)
        self.resume('--status', code=1)
        # The original repository is gone: only the journal copies remain.
        for path in self.repo.iterdir():
            path.unlink()
        self.resume()
        self.assert_upgraded()
        log = self.read('run/script-log')
        self.assertIn('post-commit', log)
        self.resume('--status')

    def test_sigkill_after_database_write_runs_post_commit_actions(self):
        self.mark('post-commit', 9)
        self.apk('upgrade', code=None)
        self.assertTrue(self.exists('lib/apk/db/transaction/phase-database'))
        self.assertEqual(self.installed()['gamma'], '1-r2')
        self.sudo('rm', '-f', str(self.root / 'run/script-log'))
        result = self.resume()
        self.assertIn('post-commit actions', result.stdout + result.stderr)
        self.assertEqual(self.read('run/script-log').split(), ['post-commit', 'post-commit'])
        self.assert_upgraded()

    def test_database_phase_recreates_the_kernel_transaction(self):
        # With kernel policy active, kernelctl apk-post must still run.
        self.sudo('mkdir', '-p', str(self.root / 'etc/openwrt-kernel'), str(self.root / 'usr/sbin'))
        self.sudo('touch', str(self.root / 'etc/openwrt-kernel/protected'))
        self.sudo('install', '-m', '0755', str(self.helper), str(self.root / 'usr/sbin/kernelctl'))
        self.mark('post-commit', 9)
        self.apk('upgrade', code=None)
        self.assertNotIn('apk-post', self.read('run/script-log'))
        self.sudo('rm', '-f', str(self.root / 'run/openwrt-kernel-apk.txn'), str(self.root / 'run/script-log'))
        self.resume()
        self.assertEqual(self.read('run/script-log').splitlines(), ['post-commit post-commit', 'apk-post apk-post'])
        transaction = self.read('run/openwrt-kernel-apk.txn')
        self.assertIn('alpha\t1-r1\talpha\t1-r2\t0', transaction)
        self.assertIn('obsolete\t1-r1\t-\t-\t0', transaction)
        self.assert_upgraded()

    def test_changed_database_is_left_for_manual_recovery(self):
        self.mark('post-upgrade', 9)
        self.apk('upgrade', code=None)
        self.sudo('sh', '-c', 'echo >> %s' % (self.root / 'lib/apk/db/installed'))
        result = self.resume(code=1)
        self.assertIn('changed outside', result.stderr)
        self.assertTrue(self.exists('lib/apk/db/transaction/journal'))

    def test_repeated_interruption_increments_the_attempt(self):
        self.mark('post-upgrade', 9)
        self.apk('upgrade', code=None)
        self.mark('post-upgrade', 9)
        self.resume(code=1)
        self.assertIn('attempt 1', self.journal())
        self.resume()
        self.assert_upgraded()


if __name__ == '__main__':
    unittest.main()
