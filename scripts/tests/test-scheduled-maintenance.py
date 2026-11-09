#!/usr/bin/env python3
"""Source preservation, recurrence, merge provenance and fail-closed publication."""
import argparse
from datetime import datetime
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

TREE = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('scheduler', TREE / 'scripts/scheduled-maintenance.py')
S = importlib.util.module_from_spec(spec)
spec.loader.exec_module(S)


class ScheduledTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='scheduled-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.repo = self.root / 'source'
        self.repo.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Scheduler test')
        self.git('config', 'user.email', 'scheduler@localhost')
        (self.repo / 'tracked').write_text('base\n')
        self.git('add', 'tracked')
        self.git('commit', '-qm', 'base')

    def git(self, *args):
        return S.git(self.repo, *args)

    def test_snapshot_preserves_index_worktree_stash_and_untracked(self):
        (self.repo / 'tracked').write_text('staged\n')
        self.git('add', 'tracked')
        (self.repo / 'tracked').write_text('working\n')
        (self.repo / 'untracked').write_bytes(b'private\0input')
        (self.repo / '__pycache__').mkdir()
        (self.repo / '__pycache__/cached.pyc').write_bytes(b'cache')
        index = (self.repo / '.git/index').read_bytes()
        head = self.git('rev-parse', 'HEAD')
        status = self.git('status', '--porcelain')
        snapshot = S.source_snapshot(self.repo, self.root / 'record')
        self.assertEqual((self.repo / '.git/index').read_bytes(), index)
        self.assertEqual(self.git('rev-parse', 'HEAD'), head)
        self.assertEqual(self.git('status', '--porcelain'), status)
        self.assertEqual(self.git('show', snapshot['snapshot'] + ':tracked'), 'working')
        self.assertEqual(self.git('show', snapshot['snapshot'] + ':untracked'), 'private\0input')
        self.assertEqual(snapshot['skipped_non_source'], ['__pycache__/cached.pyc'])
        again = S.source_snapshot(self.repo, self.root / 'record-2')
        self.assertEqual(again['snapshot'], snapshot['snapshot'])

    def test_new_snapshot_retains_previous_and_new_local_history(self):
        first = S.source_snapshot(self.repo, self.root / 'first')['snapshot']
        (self.repo / 'tracked').write_text('committed later\n')
        self.git('commit', '-qam', 'later source change')
        head = self.git('rev-parse', 'HEAD')
        second = S.source_snapshot(self.repo, self.root / 'second')['snapshot']
        self.git('merge-base', '--is-ancestor', first, second)
        self.git('merge-base', '--is-ancestor', head, second)

    def test_large_untracked_source_fails_instead_of_silently_dropping_it(self):
        with (self.repo / 'large-source').open('wb') as stream:
            stream.truncate(17 * 1024 * 1024)
        with self.assertRaisesRegex(ValueError, 'Large untracked'):
            S.source_snapshot(self.repo, self.root / 'record')

    def test_feed_parser_preserves_branch_pins_and_local_feed(self):
        (self.repo / 'feeds.conf.default').write_text(
            'src-git packages https://example.test/packages;master\n'
            'src-git-full pinned https://example.test/feed^' + 'a' * 40 + '\n'
            'src-link custom ../package/custom\n')
        result = S.feed_definitions(self.repo)
        self.assertEqual(result[0]['revision'], 'master')
        self.assertEqual(result[1]['revision'], 'a' * 40)
        self.assertEqual(result[2]['path'], '../package/custom')

    def test_merge_verification_requires_both_local_and_actual_upstream(self):
        repo = S.prepare_repository(self.repo, self.root / 'record', str(self.repo), 'published')
        snapshot = repo['original_head']
        self.git('branch', 'published')
        (self.repo / '.git/scheduled-upstream').write_text(snapshot)
        S.verify_repositories([repo])
        self.assertEqual(repo['upstream_commit'], snapshot)
        (self.repo / '.git/scheduled-upstream').write_text('a' * 40)
        with self.assertRaisesRegex(ValueError, 'differs'):
            S.verify_repositories([repo])

    def test_in_place_prepare_and_verification_preserve_existing_dirty_work(self):
        (self.repo / 'tracked').write_text('staged local work\n')
        self.git('add', 'tracked')
        (self.repo / 'tracked').write_text('unstaged local work\n')
        (self.repo / 'private').write_text('untracked work\n')
        index = (self.repo / '.git/index').read_bytes()
        original_status = self.git('status', '--porcelain')
        repo = S.prepare_repository(self.repo, self.root / 'record')
        S.verify_repositories([repo])
        self.assertEqual(repo['path'], str(self.repo))
        self.assertEqual(self.git('status', '--porcelain'), original_status)
        self.assertEqual((self.repo / '.git/index').read_bytes(), index)
        self.assertEqual(self.git('rev-parse', 'HEAD'), repo['original_head'])
        self.assertNotEqual(repo['local_snapshot'], repo['original_head'])
        self.assertEqual((self.repo / 'private').read_text(), 'untracked work\n')

    def test_original_untracked_source_cannot_be_silently_removed(self):
        item = self.repo / 'private-local-source'
        item.write_text('private input\n')
        repo = S.prepare_repository(self.repo, self.root / 'record')
        item.unlink()
        with self.assertRaisesRegex(ValueError, 'original untracked'):
            S.verify_repositories([repo])

    def test_new_uncommitted_fixes_cannot_pass_integration(self):
        repo = S.prepare_repository(self.repo, self.root / 'record')
        (self.repo / 'tracked').write_text('new unfixed work\n')
        with self.assertRaisesRegex(ValueError, 'new uncommitted'):
            S.verify_repositories([repo])

    def test_original_branch_and_user_stash_must_survive(self):
        (self.repo / 'tracked').write_text('user stashed work\n')
        self.git('stash', 'push', '-m', 'original user stash')
        repo = S.prepare_repository(self.repo, self.root / 'record')
        self.git('checkout', '-qb', 'another')
        with self.assertRaisesRegex(ValueError, 'current branch'):
            S.verify_repositories([repo])
        self.git('checkout', repo['branch'].removeprefix('refs/heads/'))
        self.git('stash', 'drop')
        with self.assertRaisesRegex(ValueError, 'original user stash'):
            S.verify_repositories([repo])

    def test_prepare_uses_current_workspace_without_cloning_or_overwriting_config(self):
        (self.repo / '.config').write_text('CONFIG_PRIVATE=y\n')
        (self.repo / 'feeds.conf.default').write_text('src-link custom ../package/custom\n')
        self.git('remote', 'add', 'origin', 'https://example.test/main')
        run = self.root / 'run'
        run.mkdir()
        with patch.object(S, 'command', side_effect=AssertionError('must not clone')):
            repositories = S.prepare(self.repo, run)
        self.assertEqual([r['path'] for r in repositories], [str(self.repo)])
        self.assertEqual((self.repo / '.config').read_text(), 'CONFIG_PRIVATE=y\n')
        self.assertEqual((run / 'input.config').read_bytes(), (self.repo / '.config').read_bytes())
        self.assertFalse((self.root / 'checkout').exists())

    def test_preexisting_index_lock_blocks_before_snapshot(self):
        (self.repo / '.git/index.lock').touch()
        with self.assertRaisesRegex(ValueError, 'unfinished Git operation'):
            S.prepare_repository(self.repo, self.root / 'record')
        self.assertFalse((self.root / 'record').exists())

    def test_publication_requires_exact_image_and_every_check(self):
        checks = {'routing', 'dns', 'luci'}
        smoke = types.SimpleNamespace(REQUIRED=checks, sha256=lambda path: 'good-hash')
        publisher = Mock()
        image = self.root / 'image.gz'
        receipt = {'status': 'passed', 'checks': dict.fromkeys(checks, True),
                   'image_sha256': 'good-hash', 'image': str(image.resolve())}
        def loader(name, filename):
            return smoke if filename == 'test-image-network.py' else publisher
        with patch.object(S, 'load', side_effect=loader):
            S.gated_publish(self.repo, receipt, image)
            publisher.publish.assert_called_once()
            for key, value in [('status', 'failed'), ('image_sha256', 'other'),
                               ('image', '/another-image'), ('checks', {'routing': True}),
                               ('checks', dict.fromkeys(checks, False))]:
                publisher.reset_mock()
                with self.assertRaises(ValueError):
                    S.gated_publish(self.repo, dict(receipt, **{key: value}), image)
                publisher.publish.assert_not_called()

    def test_unfinished_merge_blocks_integration_even_with_clean_files(self):
        (self.repo / '.git/MERGE_HEAD').write_text(self.git('rev-parse', 'HEAD'))
        with self.assertRaisesRegex(ValueError, 'Unfinished Git operation'):
            S.verify_repositories([{'path': str(self.repo)}])

    def test_repair_cannot_silently_disable_core_features(self):
        original = self.root / 'input.config'
        core = ('CONFIG_OPENWRT_SYSTEMD=y\nCONFIG_USE_GLIBC=y\nCONFIG_USE_APK=y\n'
                'CONFIG_TARGET_x86_64=y\n')
        original.write_text(core + 'CONFIG_PACKAGE_openwrt-desktop=y\n')
        (self.repo / '.config').write_text(core)
        with self.assertRaisesRegex(ValueError, 'openwrt-desktop'):
            S.verify_feature_config(original, self.repo)

    def test_status_does_not_create_state_root(self):
        config, root = self.configuration()
        self.invoke(config, '--status')
        self.assertFalse(root.exists())

    def test_disabled_schedule_does_not_create_state(self):
        config, root = self.configuration()
        data = json.loads(config.read_text())
        data['enabled'] = False
        config.write_text(json.dumps(data))
        with patch.object(S, 'execute') as execute:
            self.invoke(config, '--scheduled')
            execute.assert_not_called()
        self.assertFalse(root.exists())

    def test_modular_and_gnome_selections_are_protected(self):
        original = self.root / 'input.config'
        core = ('CONFIG_OPENWRT_SYSTEMD=y\nCONFIG_USE_GLIBC=y\nCONFIG_USE_APK=y\n'
                'CONFIG_TARGET_x86_64=y\n')
        for selection in ('CONFIG_PACKAGE_gnome-shell=y\n', 'CONFIG_PACKAGE_example=m\n'):
            original.write_text(core + selection)
            (self.repo / '.config').write_text(core)
            with self.assertRaisesRegex(ValueError, 'selected core feature'):
                S.verify_feature_config(original, self.repo)

    def test_bundle_receipt_mismatch_blocks_publication(self):
        smoke = types.SimpleNamespace(REQUIRED={'routing'}, sha256=lambda p: 'hash')
        publisher = Mock()
        receipt = {'status': 'passed', 'checks': {'routing': True},
                   'image_sha256': 'hash', 'image': str((self.root / 'image').resolve())}
        with patch.object(S, 'load', side_effect=lambda n, f: smoke if f == 'test-image-network.py' else publisher):
            with self.assertRaisesRegex(ValueError, 'manifest'):
                S.gated_publish(self.repo, receipt, self.root / 'image', self.root / 'bundle')
        publisher.publish.assert_not_called()

    def test_reuse_identity_tracks_local_source_config_and_overlay(self):
        (self.repo / '.config').write_text('CONFIG_PRIVATE=y\n')
        publisher = Mock()
        publisher.INPUTS.fingerprint.return_value = {'source': 'fixed', 'tools': 'fixed'}
        repositories = [{'path': str(self.repo)}]
        with patch.object(S, 'load', return_value=publisher):
            previous = S.workflow_fingerprint(self.repo, repositories)
            for name in ('untracked-source', '.config', 'files/etc/private'):
                item = self.repo / name
                item.parent.mkdir(parents=True, exist_ok=True)
                item.write_text('new content\n')
                current = S.workflow_fingerprint(self.repo, repositories)
                self.assertNotEqual(previous, current)
                previous = current

    def configuration(self):
        root = self.root / 'state'
        config = self.root / 'scheduler.json'
        config.write_text(json.dumps({'enabled': True, 'state_root': str(root), 'minimum_free_gib': 0}))
        return config, root

    def invoke(self, config, *arguments):
        with patch.object(sys, 'argv', ['scheduler', '--config', str(config), *arguments]):
            S.main()

    def test_schedule_is_72_hours_without_day_of_month_reset_or_hourly_drift(self):
        config, root = self.configuration()
        with patch.object(S.time, 'time', return_value=10000):
            self.invoke(config, '--initialize')
        state = json.loads((root / 'schedule.json').read_text())
        anchor = state['next_run']
        self.assertEqual(anchor, datetime(1970, 1, 5, 4, tzinfo=ZoneInfo('Asia/Singapore')).timestamp())
        with patch.object(S.time, 'time', return_value=anchor + .7), patch.object(S, 'execute') as execute:
            self.invoke(config, '--scheduled')
            execute.assert_called_once()
        state = json.loads((root / 'schedule.json').read_text())
        self.assertEqual(state['next_run'], anchor + S.INTERVAL)
        with patch.object(S.time, 'time', return_value=anchor + 1000), patch.object(S, 'execute') as execute:
            self.invoke(config, '--scheduled')
            execute.assert_not_called()

    def test_manual_run_preserves_existing_anchor(self):
        config, root = self.configuration()
        with patch.object(S.time, 'time', return_value=10000):
            self.invoke(config, '--initialize')
        anchor = json.loads((root / 'schedule.json').read_text())['next_run']
        with patch.object(S.time, 'time', return_value=anchor + 500), patch.object(S, 'execute'):
            self.invoke(config, '--run-now')
        self.assertEqual(json.loads((root / 'schedule.json').read_text())['next_run'], anchor)

    def test_uninitialized_enabled_schedule_only_anchors(self):
        config, root = self.configuration()
        with patch.object(S, 'execute') as execute:
            self.invoke(config, '--scheduled')
            execute.assert_not_called()
        self.assertIn('next_run', json.loads((root / 'schedule.json').read_text()))

    def test_initial_schedule_uses_singapore_time_across_month_boundaries(self):
        zone = ZoneInfo('Asia/Singapore')
        for hour, expected_day in [(3, 3), (4, 4), (15, 4)]:
            now = datetime(2026, 10, 31, hour, tzinfo=zone).timestamp()
            expected = datetime(2026, 11, expected_day, 4, tzinfo=zone).timestamp()
            self.assertEqual(S.initial_run_time(now, {}), expected)

    def test_failed_run_preserves_schedule_and_records_failure(self):
        config, root = self.configuration()
        with patch.object(S.time, 'time', return_value=10000):
            self.invoke(config, '--initialize')
        with patch.object(S.time, 'time', return_value=400000), patch.object(S, 'execute', side_effect=RuntimeError('merge failed')):
            with self.assertRaisesRegex(RuntimeError, 'merge failed'):
                self.invoke(config, '--scheduled')
        state = json.loads((root / 'schedule.json').read_text())
        self.assertEqual(state['status'], 'failed')
        self.assertGreater(state['next_run'], 400000)
        self.assertGreater(state['retry_at'], 400000)
        self.assertLessEqual(state['retry_at'] - 400000, 86400)
        self.assertEqual(json.loads((Path(state['last_run']) / 'result.json').read_text())['error'], 'merge failed')


if __name__ == '__main__':
    unittest.main()
