#!/usr/bin/env python3
"""Exercise the C executor's runtime guard against real filesystem objects."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / 'package/custom/luci-app-podman/src/podman-luci-exec.c'


class RuntimeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='podman-runtime-test-')
        cls.work = Path(cls.temp.name)
        harness = cls.work / 'guard.c'
        harness.write_text(
            '#define main executor_main\n'
            f'#include "{SOURCE}"\n'
            '#undef main\n'
            'int main(int argc, char **argv) {\n'
            '  return runtime_available(argv[1], strtoul(argv[2], NULL, 10)) ? 0 : 1;\n'
            '}\n')
        cls.binary = cls.work / 'guard'
        subprocess.run(['cc', '-Wall', '-Werror', '-Wno-unused-parameter',
                        str(harness), '-o', str(cls.binary)], check=True)

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def allowed(self, path, uid=None):
        return subprocess.run([str(self.binary), str(path),
                               str(os.getuid() if uid is None else uid)]).returncode == 0

    def test_modes(self):
        directory = self.work / 'runtime'
        directory.mkdir()
        try:
            for mode in [0o700, 0o710]:
                directory.chmod(mode)
                self.assertTrue(self.allowed(directory), oct(mode))
            for mode in [0o740, 0o720, 0o750, 0o770, 0o701, 0o702, 0o704, 0o777]:
                directory.chmod(mode)
                self.assertFalse(self.allowed(directory), oct(mode))
            directory.chmod(0o700)
            self.assertFalse(self.allowed(directory, os.getuid() + 1))
            link = self.work / 'link'
            link.symlink_to(directory)
            self.assertFalse(self.allowed(link))
            link.unlink()
        finally:
            directory.chmod(0o700)
            directory.rmdir()

    def test_missing_and_regular_file(self):
        self.assertFalse(self.allowed(self.work / 'missing'))
        regular = self.work / 'regular'
        regular.touch(mode=0o700)
        self.assertFalse(self.allowed(regular))


if __name__ == '__main__':
    unittest.main()
