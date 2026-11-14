#!/usr/bin/env python3
"""Host tests for the openwrt-desktop icon theme refresh APK commit hook."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


HOOK = Path(__file__).resolve().parents[2] / 'package/custom/openwrt-desktop/files/icon-theme-refresh.hook'
OLD = 1_000_000_000


class IconThemeHookTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='icon-theme-hook-')
        self.addCleanup(self.temporary.cleanup)
        self.icons = Path(self.temporary.name)

    def theme(self, name, index=True):
        apps = self.icons / name / '48x48/apps'
        apps.mkdir(parents=True)
        if index:
            (self.icons / name / 'index.theme').write_text('[Icon Theme]\n')
        for path in (apps, apps.parent, apps.parent.parent):
            os.utime(path, (OLD, OLD))
        return apps

    def run_hook(self, *args, **env):
        environment = dict(os.environ, OPENWRT_ICON_THEME_DIR=str(self.icons))
        environment.pop('IPKG_INSTROOT', None)
        environment.update(env)
        result = subprocess.run(['sh', str(HOOK), *args], env=environment, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_marks_only_themes_with_changed_subdirectories(self):
        changed = self.theme('hicolor')
        self.theme('Adwaita')
        (changed / 'google-chrome.png').write_bytes(b'png')
        self.run_hook('post-commit')
        self.assertGreater((self.icons / 'hicolor').stat().st_mtime, OLD)
        self.assertEqual((self.icons / 'Adwaita').stat().st_mtime, OLD)

    def test_ignores_pre_commit_image_builds_and_non_themes(self):
        apps = self.theme('hicolor')
        loose = self.theme('loose', index=False)
        (apps / 'a.png').write_bytes(b'png')
        (loose / 'a.png').write_bytes(b'png')
        self.run_hook('pre-commit')
        self.run_hook('post-commit', IPKG_INSTROOT='/build/root')
        self.assertEqual((self.icons / 'hicolor').stat().st_mtime, OLD)
        self.run_hook('post-commit')
        self.assertEqual((self.icons / 'loose').stat().st_mtime, OLD)
        self.assertGreater((self.icons / 'hicolor').stat().st_mtime, OLD)


if __name__ == '__main__':
    unittest.main()
