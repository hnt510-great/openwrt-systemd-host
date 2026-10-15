#!/usr/bin/env python3
import importlib.util
import os
from pathlib import Path
import tempfile
import unittest

spec = importlib.util.spec_from_file_location("merge_usr", Path(__file__).parents[1] / "merge-usr.py")
merge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(merge)


class MergeUsrTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)

    def file(self, name, data="binary", mode=0o755):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(data)
        p.chmod(mode)
        return p

    def link(self, name, target):
        p = self.root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.symlink_to(target)
        return p

    def test_relative_links_and_suid_survive(self):
        self.file("bin/tool", mode=0o4755)
        self.link("usr/bin/tool-link", "../../bin/tool")
        self.link("sbin/other", "../bin/tool")
        merge.normalize(self.root, aliases=True)
        self.assertEqual((self.root / "usr/bin/tool").stat().st_mode & 0o7777, 0o4755)
        self.assertEqual(os.readlink(self.root / "usr/bin/tool-link"), "tool")
        self.assertEqual(os.readlink(self.root / "usr/sbin/other"), "../bin/tool")
        self.assertEqual(os.readlink(self.root / "bin"), "usr/bin")
        merge.normalize(self.root, aliases=True)
        self.assertTrue((self.root / "usr/bin/tool").is_file())

    def test_real_collision_fails(self):
        self.file("bin/tool", "one")
        self.file("usr/bin/tool", "two")
        with self.assertRaisesRegex(ValueError, "conflicting payload"):
            merge.normalize(self.root)

    def test_identical_duplicate_and_collapsed_alias(self):
        self.file("sbin/xfs_db")
        self.file("usr/sbin/xfs_db")
        self.file("usr/bin/zsh")
        self.link("bin/zsh", "../usr/bin/zsh")
        merge.normalize(self.root)
        self.assertFalse((self.root / "sbin").exists())
        self.assertFalse((self.root / "bin").exists())
        self.assertTrue((self.root / "usr/bin/zsh").is_file())

    def test_metadata_and_alternatives_are_canonical(self):
        self.file("bin/mount")
        self.file("lib/apk/packages/mount-utils.list", "/bin/mount\n")
        self.file("lib/apk/packages/mount-utils.conffiles_static", "/bin/mount abc\n")
        merge.normalize(self.root, "mount-utils")
        meta = self.root / "usr/lib/apk/packages"
        self.assertIn("200:/usr/bin/mount:/usr/bin/openwrt-mount-utils-mount", (meta / "mount-utils.alternatives").read_text())
        self.assertEqual((meta / "mount-utils.conffiles_static").read_text(), "/usr/bin/openwrt-mount-utils-mount abc\n")
        self.assertNotIn("/bin/mount\n", (meta / "mount-utils.list").read_text())

    def test_busybox_fallback_has_no_conflicting_payload(self):
        self.file("bin/busybox")
        self.link("bin/mount", "busybox")
        self.file("lib/apk/packages/busybox.list", "/bin/busybox\n/bin/mount\n")
        merge.normalize(self.root, "busybox")
        self.assertFalse(os.path.lexists(self.root / "usr/bin/mount"))
        self.assertIn("100:/usr/bin/mount:/usr/bin/busybox", (self.root / "usr/lib/apk/packages/busybox.alternatives").read_text())

    def test_absolute_image_link_does_not_touch_host(self):
        self.link("lib/host-link", "/etc/passwd")
        merge.normalize(self.root)
        self.assertEqual(os.readlink(self.root / "usr/lib/host-link"), "/etc/passwd")

    def test_relative_alternative_targets_resolve_from_link_parent(self):
        self.file("usr/sbin/xtables-nft-multi")
        self.file("lib/apk/packages/iptables-nft.alternatives",
                  "300:/sbin/iptables:xtables-nft-multi "
                  "300:/usr/sbin/iptables-save:../../sbin/xtables-nft-multi\n")
        merge.normalize(self.root, "iptables-nft")
        metadata = self.root / "usr/lib/apk/packages/iptables-nft.alternatives"
        expected = ("300:/usr/sbin/iptables:/usr/sbin/xtables-nft-multi "
                    "300:/usr/sbin/iptables-save:/usr/sbin/xtables-nft-multi\n")
        self.assertEqual(metadata.read_text(), expected)
        merge.normalize(self.root, "iptables-nft")
        self.assertEqual(metadata.read_text(), expected)

    def test_symlink_destination_parent_is_rejected(self):
        self.file("bin/tool")
        with tempfile.TemporaryDirectory() as outside:
            self.link("usr/bin", outside)
            with self.assertRaisesRegex(ValueError, "symlink payload parent"):
                merge.normalize(self.root)
            self.assertEqual(list(Path(outside).iterdir()), [])


if __name__ == "__main__":
    unittest.main()
