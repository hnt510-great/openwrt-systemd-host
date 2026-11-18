#!/usr/bin/env python3
"""Exercise the installed x86/64 configuration tool's command boundary."""
from pathlib import Path
import subprocess
import tempfile
import unittest

BASE = Path(__file__).resolve().parents[2] / 'package/base-files'


class BackupCliTests(unittest.TestCase):
    def setUp(self):
        work = tempfile.TemporaryDirectory()
        self.addCleanup(work.cleanup)
        self.script = Path(work.name) / 'sysupgrade'
        self.script.write_text((BASE / 'files/sbin/sysupgrade').read_text())
        recipe = (BASE / 'Makefile').read_text()
        sed = next(line.split("'")[1] for line in recipe.splitlines()
                   if 'BEGIN_FIRMWARE_ONLY' in line).replace('$$$$', '$').replace('$$', '$')
        subprocess.run(['sed', '-i', sed, self.script], check=True)
        # Command parsing happens before any backup operation. Stub rootfs imports.
        self.script.write_text('\n'.join(line for line in self.script.read_text().splitlines()
                                         if not line.startswith('. /lib/functions')))

    def command(self, *args):
        return subprocess.run(['sh', self.script, *args], capture_output=True, text=True)

    def test_help_only_advertises_backup_operations(self):
        result = self.command('--help')
        self.assertEqual(result.returncode, 0)
        for option in ('--create-backup', '--list-backup', '--restore-backup'):
            self.assertIn(option, result.stdout)
        self.assertNotIn('--test', result.stdout)
        self.assertNotIn('--force', result.stdout)

    def test_firmware_options_and_arguments_fail_during_parsing(self):
        for args in (('/tmp/test.img',), ('https://example.invalid/test.img',),
                     ('-T', '/tmp/test.img'), ('--force', '/tmp/test.img'),
                     ('--list-backup', '/tmp/test.img'), ('-b',), ('-r',)):
            with self.subTest(args=args):
                result = self.command(*args)
                self.assertEqual(result.returncode, 1)
                self.assertRegex(result.stderr, 'unavailable|Invalid option|Backup file is required')


if __name__ == '__main__':
    unittest.main()
