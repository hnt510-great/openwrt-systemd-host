#!/usr/bin/env python3
"""Offline final-release selection and transactional kernel metadata updates."""
import fcntl
import hashlib
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tarfile
import tempfile
import unittest

TREE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('mainline_updates', TREE / 'scripts/update-mainline-kernel.py')
U = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(U)


class Fetcher:
    def __init__(self):
        self.data = {}
        self.requests = []

    def get(self, url):
        self.requests.append(url)
        result = self.data[url]
        if isinstance(result, Exception):
            raise result
        return result

    def download(self, url, destination):
        destination.write_bytes(self.get(url))


class KernelUpdates(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='mainline-update-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.selection = self.root / 'target/linux/x86/64/target.mk'
        self.selection.parent.mkdir(parents=True)
        self.selection.write_text('ARCH:=x86_64\nKERNEL_PATCHVER:=7.3\n')
        self.metadata = self.root / 'target/linux/generic/kernel-7.3'
        self.metadata.parent.mkdir(parents=True)
        self.metadata.write_text('LINUX_VERSION-7.3 =\nLINUX_KERNEL_HASH-7.3 = ' + 'a' * 64 + '\n')
        for target in ('generic', 'x86', 'x86/64'):
            (self.root / ('target/linux/' + target + '/config-7.3')).write_text('CONFIG_FEATURE=y\n')
        for directory in U.patch_directories(self.root, '7.3'):
            directory.mkdir()
        self.patch = U.patch_directories(self.root, '7.3')[1] / '100-feature.patch'
        self.patch.write_text('--- a/feature\n+++ b/feature\n@@ -1 +1 @@\n-before\n+after\n')
        (self.root / '.config').write_text('CONFIG_TARGET_x86_64=y\nCONFIG_KEEP=y\n')
        self.git('init', '-q')
        self.git('add', '.')
        self.git('-c', 'user.name=Kernel test', '-c', 'user.email=kernel-test@localhost',
                 'commit', '-qm', 'initial')
        self.fetcher = Fetcher()
        self.release('7.3.1')

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args], stderr=subprocess.DEVNULL)

    def release(self, version, feature=b'before\n'):
        self.fetcher.data[U.RELEASES] = json.dumps({'releases': [
            {'moniker': 'mainline', 'version': version}]}).encode()
        archive = io.BytesIO()
        with tarfile.open(fileobj=archive, mode='w:xz') as stream:
            for name, contents in [('Makefile', b'VERSION = 7\n'), ('feature', feature)]:
                item = tarfile.TarInfo('linux-' + version + '/' + name)
                item.size = len(contents)
                stream.addfile(item, io.BytesIO(contents))
        self.payload = archive.getvalue()
        self.digest = hashlib.sha256(self.payload).hexdigest()
        self.base = U.CDN + '/v' + version.split('.')[0] + '.x/'
        self.archive_url = self.base + 'linux-' + version + '.tar.xz'
        self.fetcher.data[self.archive_url] = self.payload
        self.fetcher.data[self.base + 'sha256sums.asc'] = (
            self.digest + '  linux-' + version + '.tar.xz\n').encode()

    def run_sync(self, update=False, **kwargs):
        return U.sync(self.root, update, self.fetcher, **kwargs)

    def test_check_is_read_only(self):
        before = self.git('status', '--porcelain', '--untracked-files=all')
        report, status = self.run_sync()
        self.assertEqual((report['status'], status), ('available', 1))
        self.assertEqual(self.git('status', '--porcelain', '--untracked-files=all'), before)
        self.assertFalse((self.root / 'build_dir').exists())
        self.assertEqual(self.fetcher.requests, [U.RELEASES])

    def test_final_release_order_and_rc_exclusion(self):
        data = {'releases': [{'moniker': kind, 'version': version} for kind, version in [
            ('mainline', '7.4-rc1'), ('stable', '7.3.9'), ('stable', '7.3.10'),
            ('longterm', '8.0.1'), ('linux-next', 'next-20261024')]]}
        self.assertEqual(U.latest_release(data), '7.3.10')
        self.assertEqual(U.version_key('7.3'), U.version_key('7.3.0'))

    def test_no_final_release_is_an_error(self):
        with self.assertRaises(U.SyncError):
            U.latest_release({'releases': [{'moniker': 'mainline', 'version': '7.4-rc1'}]})

    def test_malformed_release_metadata_is_rejected(self):
        for data in ([], {}, {'releases': '7.3'}, {'releases': [None]}):
            with self.subTest(data=data), self.assertRaises(U.SyncError):
                U.latest_release(data)

    def test_new_series_requires_port_without_writes(self):
        self.release('7.4')
        before = self.metadata.read_bytes()
        report, status = self.run_sync(True)
        self.assertEqual((report['status'], status), ('port-required', 2))
        self.assertEqual(self.metadata.read_bytes(), before)
        self.assertEqual(self.fetcher.requests, [U.RELEASES])

    def test_major_release_requires_port(self):
        self.release('8.0')
        self.assertEqual(self.run_sync(True)[0]['status'], 'port-required')

    def test_never_downgrades(self):
        self.release('7.2.99')
        self.assertEqual(self.run_sync(True)[0]['status'], 'current')
        self.assertEqual(self.fetcher.requests, [U.RELEASES])

    def test_current_release_does_not_download(self):
        self.release('7.3')
        self.assertEqual(self.run_sync(True)[1], 0)
        self.assertEqual(self.fetcher.requests, [U.RELEASES])

    def test_update_checks_real_patches_and_preserves_config(self):
        config = (self.root / '.config').read_bytes()
        patch = self.patch.read_bytes()
        report, status = self.run_sync(True)
        self.assertEqual((report['status'], status), ('updated', 0))
        text = self.metadata.read_text()
        self.assertIn('LINUX_VERSION-7.3 = .1\n', text)
        self.assertIn('LINUX_KERNEL_HASH-7.3.1 = ' + self.digest, text)
        self.assertEqual((self.root / '.config').read_bytes(), config)
        self.assertEqual(self.patch.read_bytes(), patch)
        self.assertEqual((self.root / 'dl/linux-7.3.1.tar.xz').read_bytes(), self.payload)
        self.assertEqual(list((self.root / 'build_dir').iterdir()), [])
        self.assertEqual(self.git('diff', '--name-only').decode().splitlines(),
                         ['target/linux/generic/kernel-7.3'])

    def test_sha256_failure_preserves_metadata(self):
        self.fetcher.data[self.archive_url] += b'corrupt'
        before = self.metadata.read_bytes()
        with self.assertRaisesRegex(U.SyncError, 'SHA256 mismatch'):
            self.run_sync(True)
        self.assertEqual(self.metadata.read_bytes(), before)

    def test_ambiguous_checksum_is_rejected(self):
        key = self.base + 'sha256sums.asc'
        self.fetcher.data[key] *= 2
        with self.assertRaisesRegex(U.SyncError, 'exactly one'):
            self.run_sync(True)

    def test_patch_failure_preserves_metadata(self):
        self.release('7.3.1', b'incompatible\n')
        before = self.metadata.read_bytes()
        with self.assertRaisesRegex(U.SyncError, 'needs review'):
            self.run_sync(True)
        self.assertEqual(self.metadata.read_bytes(), before)
        self.assertFalse((self.root / 'dl').exists())

    def test_already_applied_patch_is_not_silently_reversed(self):
        self.release('7.3.1', b'after\n')
        with self.assertRaisesRegex(U.SyncError, 'needs review'):
            self.run_sync(True)

    def test_changed_inputs_are_not_overwritten(self):
        before = self.metadata.read_bytes()

        def change(*args):
            self.patch.write_text(self.patch.read_text() + '# concurrent edit\n')

        with self.assertRaisesRegex(U.SyncError, 'inputs changed'):
            self.run_sync(True, validator=change)
        self.assertEqual(self.metadata.read_bytes(), before)
        self.assertIn('concurrent edit', self.patch.read_text())

    def test_dirty_metadata_requires_review(self):
        self.metadata.write_text(self.metadata.read_text() + '# local edit\n')
        before = self.metadata.read_bytes()
        with self.assertRaisesRegex(U.SyncError, 'local kernel metadata edits'):
            self.run_sync(True)
        self.assertEqual(self.metadata.read_bytes(), before)

    def test_source_overlay_is_applied_before_patches(self):
        self.release('7.3.1', b'different upstream\n')
        overlay = self.root / 'target/linux/generic/files'
        overlay.mkdir()
        (overlay / 'feature').write_text('before\n')
        self.assertEqual(self.run_sync(True)[0]['status'], 'updated')

    def test_existing_archive_is_verified_without_download(self):
        path = self.root / 'dl/linux-7.3.1.tar.xz'
        path.parent.mkdir()
        path.write_bytes(self.payload)
        self.assertEqual(self.run_sync(True)[0]['status'], 'updated')
        self.assertNotIn(self.archive_url, self.fetcher.requests)

    def test_existing_corrupt_archive_is_preserved(self):
        path = self.root / 'dl/linux-7.3.1.tar.xz'
        path.parent.mkdir()
        path.write_bytes(b'local corrupt archive')
        with self.assertRaisesRegex(U.SyncError, 'SHA256 mismatch'):
            self.run_sync(True)
        self.assertEqual(path.read_bytes(), b'local corrupt archive')

    def test_concurrent_build_blocks_update(self):
        (self.root / 'tmp').mkdir()
        with (self.root / 'tmp/.build-and-publish.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaisesRegex(U.SyncError, 'already running'):
                self.run_sync(True)

    def test_fetch_failure_does_not_change_metadata(self):
        self.fetcher.data[U.RELEASES] = OSError('offline')
        before = self.metadata.read_bytes()
        with self.assertRaisesRegex(OSError, 'offline'):
            self.run_sync(True)
        self.assertEqual(self.metadata.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
