#!/usr/bin/env python3
"""Optional preinit network cleanup must not reject native-init handoff."""
from pathlib import Path
import shutil
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
HOOK = ROOT / 'package/base-files/files/lib/preinit/99_10_run_init'
FUNCTIONS = ROOT / 'package/base-files/files/lib/functions/preinit.sh'


@unittest.skipUnless(shutil.which('busybox'), 'requires BusyBox ash')
class PreinitHandoff(unittest.TestCase):
    def check_cleanup(self, status):
        # Execute the actual hook queue, including its final shell exit status.
        # The old hook leaked the cleanup result into procd's preinit callback.
        script = '''
. "$1"
boot_hook_init preinit_main
preinit_ip_deconfig() { echo cleanup; return CLEANUP_STATUS; }
. "$2"
boot_run_hook preinit_main
'''
        script = script.replace('CLEANUP_STATUS', str(status))
        result = subprocess.run(['busybox', 'ash', '-c', script, 'preinit-test',
                                 str(FUNCTIONS), str(HOOK)], capture_output=True, text=True)
        self.assertEqual(result.stdout, 'cleanup\n')
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_no_preinit_interface(self):
        self.check_cleanup(1)

    def test_configured_interface(self):
        self.check_cleanup(0)

    def test_cleanup_command_failure(self):
        self.check_cleanup(2)


if __name__ == '__main__':
    unittest.main()
