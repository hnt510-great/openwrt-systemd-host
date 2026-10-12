#!/usr/bin/env python3
"""Exercise repository setup without changing host accounts or /srv."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[2] / "package/custom/openwrt-flatpak/files/flatpak-user-link"


class RepositoryLinkTest(unittest.TestCase):
    def setUp(self):
        if os.getuid() < 1000:
            self.skipTest("Run this test as an ordinary user")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "Home With Spaces"
        self.home.mkdir()
        self.repo = self.root / "repository"
        self.repo.mkdir(mode=0o700)
        self.link = self.home / ".local/share/flatpak"

    def run_setup(self, repo=None):
        return subprocess.run(["sh", str(SCRIPT), str(repo or self.repo)],
                              env={**os.environ, "HOME": str(self.home)},
                              capture_output=True, text=True)

    def test_setup_and_repeat_preserve_data(self):
        self.assertEqual(self.run_setup().returncode, 0)
        (self.repo / "installed-data").write_text("keep")
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertEqual(self.link.readlink(), self.repo)
        self.assertEqual((self.repo / "installed-data").read_text(), "keep")
        self.assertTrue((self.home / ".var/app").is_dir())

    def test_nonempty_and_hidden_existing_repository_is_preserved(self):
        self.link.mkdir(parents=True)
        original = self.link / ".hidden"
        original.write_text("keep")
        self.assertNotEqual(self.run_setup().returncode, 0)
        self.assertEqual(original.read_text(), "keep")

    def test_empty_existing_directory_is_linked(self):
        self.link.mkdir(parents=True)
        self.assertEqual(self.run_setup().returncode, 0)
        self.assertEqual(self.link.readlink(), self.repo)

    def test_wrong_or_dangling_link_is_preserved(self):
        self.link.parent.mkdir(parents=True)
        wrong = self.root / "missing"
        self.link.symlink_to(wrong)
        self.assertNotEqual(self.run_setup().returncode, 0)
        self.assertEqual(self.link.readlink(), wrong)

    def test_linked_repository_is_rejected(self):
        alias = self.root / "alias"
        alias.symlink_to(self.repo)
        self.assertNotEqual(self.run_setup(alias).returncode, 0)
        self.assertFalse(self.link.exists())

    def test_existing_file_is_preserved(self):
        self.link.parent.mkdir(parents=True)
        self.link.write_text("keep")
        self.assertNotEqual(self.run_setup().returncode, 0)
        self.assertEqual(self.link.read_text(), "keep")


if __name__ == "__main__":
    unittest.main()
