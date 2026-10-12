#!/usr/bin/env python3
"""Verify directory metadata without expanding the selected backup contents."""
from pathlib import Path
import os
import re
import subprocess
import tarfile
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[2]
SCRIPT = SOURCE / 'package/base-files/files/sbin/sysupgrade'
FUNCTION = re.search(r'^include_home_directory_metadata\(\) \{\n.*?^\}', SCRIPT.read_text(), re.M | re.S).group()


class HomeMetadataBackupTest(unittest.TestCase):
    def test_permissions_and_selected_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            profile = root / 'home/alice/Profile With Spaces'
            profile.mkdir(parents=True)
            profile.parent.chmod(0o700)
            profile.chmod(0o710)
            (profile / 'prefs.js').write_text('selected')
            (profile / 'unselected.txt').write_text('must not be included')
            listing = root / 'backup.list'
            listing.write_text('home/alice/Profile With Spaces/prefs.js\n')
            result = subprocess.run(['sh', '-c', FUNCTION + '\ninclude_home_directory_metadata "$1"', 'test', str(listing)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            archive = root / 'backup.tar'
            subprocess.run(['tar', 'cf', str(archive), '--no-recursion', '-C', str(root), '-T', str(listing)], check=True)
            with tarfile.open(archive) as backup:
                self.assertEqual(set(backup.getnames()), {'home', 'home/alice', 'home/alice/Profile With Spaces', 'home/alice/Profile With Spaces/prefs.js'})
                self.assertEqual(backup.getmember('home/alice').mode, 0o700)
                directory = backup.getmember('home/alice/Profile With Spaces')
                self.assertEqual(directory.mode, 0o710)
                self.assertEqual(directory.uid, os.getuid())
                self.assertEqual(directory.gid, os.getgid())

    def test_non_home_selection_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            listing = Path(tmp) / 'backup.list'
            listing.write_text('etc/config/network\n')
            result = subprocess.run(['sh', '-c', FUNCTION + '\ninclude_home_directory_metadata "$1"', 'test', str(listing)], capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(listing.read_text(), 'etc/config/network\n')

    def test_tar_without_no_recursion_stays_unchanged(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            listing = root / 'backup.list'
            listing.write_text('home/alice/prefs.js\n')
            stub = root / 'tar'
            stub.write_text('#!/bin/sh\necho "tar without long options"\n')
            stub.chmod(0o755)
            env = dict(os.environ, PATH=str(root) + os.pathsep + os.environ['PATH'])
            result = subprocess.run(['sh', '-c', FUNCTION + '\ninclude_home_directory_metadata "$1"', 'test', str(listing)], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(listing.read_text(), 'home/alice/prefs.js\n')


if __name__ == '__main__':
    unittest.main()
