#!/usr/bin/env python3
"""Exercise release selection and failure atomicity without network or repo edits."""
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[2]


class FirefoxUpdaterTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        (self.root / "scripts").mkdir()
        (self.root / "firefox-esr-bin").mkdir()
        (self.root / "bin").mkdir()
        self.script = self.root / "scripts/update-firefox-esr.sh"
        shutil.copy2(SOURCE / "package/custom/scripts/update-firefox-esr.sh", self.script)
        self.makefile = self.root / "firefox-esr-bin/Makefile"
        self.initial = "PKG_VERSION:=153.4.0esr\nPKG_RELEASE:=3\nPKG_HASH:=" + "a" * 64 + "\n"
        self.makefile.write_text(self.initial)
        self.payload = b"fixed test archive payload"
        self.hash = hashlib.sha256(self.payload).hexdigest()
        self.fixture = self.root / "fixture"
        self.fixture.mkdir()
        (self.fixture / "archive").write_bytes(self.payload)
        self.releases("140.17.0esr", "153.5.0esr")
        stub = self.root / "bin/curl"
        stub.write_text("""#!/usr/bin/env python3
import os, sys
from pathlib import Path
p = Path(os.environ['FIREFOX_UPDATE_FIXTURE'])
url = sys.argv[-1]
name = 'versions.json' if url.endswith('firefox_versions.json') else 'SHA256SUMS' if url.endswith('SHA256SUMS') else 'archive'
sys.stdout.buffer.write((p / name).read_bytes())
""")
        stub.chmod(0o755)
        self.env = dict(os.environ, PATH=str(self.root / "bin") + os.pathsep + os.environ["PATH"],
                        FIREFOX_UPDATE_FIXTURE=str(self.fixture))

    def tearDown(self):
        self.tmp.cleanup()

    def releases(self, current, next_version, digest=None):
        (self.fixture / "versions.json").write_text(json.dumps({"FIREFOX_ESR": current, "FIREFOX_ESR_NEXT": next_version}))
        (self.fixture / "SHA256SUMS").write_text(
            f"{digest or self.hash}  linux-x86_64/zh-CN/firefox-{next_version}.tar.xz\n")

    def run_updater(self, *args):
        return subprocess.run([str(self.script), *args], env=self.env, capture_output=True, text=True)

    def test_default_check_is_read_only(self):
        self.assertEqual(self.run_updater().returncode, 1)
        self.assertEqual(self.makefile.read_text(), self.initial)

    def test_update_verifies_archive_and_resets_release(self):
        result = self.run_updater("--update")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.makefile.read_text(), f"PKG_VERSION:=153.5.0esr\nPKG_RELEASE:=1\nPKG_HASH:={self.hash}\n")
        self.assertFalse(list(self.makefile.parent.glob("Makefile.update.*")))

    def test_checksum_failure_preserves_metadata(self):
        self.releases("140.17.0esr", "153.5.0esr", "b" * 64)
        self.assertNotEqual(self.run_updater("--update").returncode, 0)
        self.assertEqual(self.makefile.read_text(), self.initial)

    def test_major_upgrade_requires_review(self):
        self.releases("154.0.0esr", "155.0.0esr")
        self.assertEqual(self.run_updater("--update").returncode, 2)
        self.assertEqual(self.makefile.read_text(), self.initial)

    def test_newer_major_does_not_hide_packaged_branch(self):
        self.releases("153.5.0esr", "154.0.0esr")
        (self.fixture / "SHA256SUMS").write_text(f"{self.hash}  linux-x86_64/zh-CN/firefox-153.5.0esr.tar.xz\n")
        self.assertEqual(self.run_updater("--update").returncode, 0)
        self.assertIn("PKG_VERSION:=153.5.0esr", self.makefile.read_text())

    def test_downgrade_is_rejected(self):
        self.releases("140.17.0esr", "153.3.0esr")
        self.assertEqual(self.run_updater("--update").returncode, 2)
        self.assertEqual(self.makefile.read_text(), self.initial)

    def test_invalid_hash_is_rejected(self):
        self.releases("140.17.0esr", "153.5.0esr", "invalid")
        self.assertNotEqual(self.run_updater("--update").returncode, 0)
        self.assertEqual(self.makefile.read_text(), self.initial)


if __name__ == "__main__":
    unittest.main()
