#!/usr/bin/env python3
"""Test the actual logd journal converter and init-script boot-mode selection.

Requires the downloaded ubox source and staged development headers, but does
not run a daemon, open a journal, or modify the checkout's build directory.
"""
from pathlib import Path
import os
import shlex
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[2]


class LogdJournalTests(unittest.TestCase):
    def build_harness(self, fixture):
        archives = list((ROOT / 'dl').glob('ubox-*.tar.zst'))
        headers = ROOT / 'staging_dir/target-x86_64_glibc/usr/include'
        if len(archives) != 1 or not headers.joinpath('systemd/sd-journal.h').is_file():
            self.skipTest('requires downloaded ubox source and staged native headers')
        if not shutil.which('cc'):
            self.skipTest('requires a host C compiler')
        with tempfile.TemporaryDirectory(prefix='logd-journal-test-') as directory:
            work = Path(directory)
            subprocess.run(['tar', '-xf', str(archives[0]), '-C', str(work)], check=True)
            source = next(work.glob('ubox-*'))
            with (ROOT / 'package/system/ubox/patches/101-journal-reader.patch').open() as patch:
                subprocess.run(['patch', '-p1', '--batch'], cwd=source, stdin=patch,
                               check=True, stdout=subprocess.DEVNULL)
            shutil.copyfile(ROOT / 'scripts/tests' / fixture, source / 'log/test-record.c')
            program = work / 'test-record'
            subprocess.run([
                'cc', '-std=gnu99', '-DOPENWRT_SYSTEMD', '-Wall', '-Wextra', '-Werror',
                '-Wno-unused-parameter', '-ffunction-sections', '-fdata-sections',
                '-Wno-sign-compare',
                '-Wl,--gc-sections', '-idirafter', str(headers),
                str(source / 'log/test-record.c'), '-o', str(program),
            ], check=True)
            subprocess.run([str(program)], check=True)

    def test_record_conversion(self):
        self.build_harness('logd-journal-record.c')

    def test_forwarder_reconnect(self):
        self.build_harness('logread-reconnect.c')

    def test_boot_mode_selection(self):
        init = shlex.quote(str(ROOT / 'package/system/ubox/files/log.init'))
        for mode, marker in [('systemd', True), ('systemd', False), ('procd', True), ('procd', False)]:
            with self.subTest(mode=mode, marker=marker):
                script = '''
cat() { printf '%s\\n' "$TEST_PID1"; }
test() { [ "$TEST_MARKER" = 1 ]; }
procd_open_instance() { :; }
procd_close_instance() { :; }
procd_set_param() { printf 'set %s\\n' "$*"; }
procd_append_param() { printf 'append %s\\n' "$*"; }
. ''' + init + '''
log_buffer_size=64
log_size=0
start_service_daemon
'''
                result = subprocess.check_output(['sh', '-c', script], text=True,
                                                 env=dict(os.environ, TEST_PID1=mode,
                                                          TEST_MARKER='1' if marker else '0'))
                self.assertIn('set command /sbin/logd', result)
                self.assertEqual('append command -J' in result, mode == 'systemd' and marker)
                self.assertEqual('set stderr 1' in result, mode == 'systemd' and marker)


if __name__ == '__main__':
    unittest.main()
