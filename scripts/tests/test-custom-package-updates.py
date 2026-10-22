#!/usr/bin/env python3
"""Offline release, preservation and feeds integration tests."""
from contextlib import redirect_stdout
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch


TREE = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('custom_updates', TREE / 'scripts/update-custom-packages.py')
U = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(U)
PAYLOAD = b'\x1f\x8bfixture source archive'
DIGEST = hashlib.sha256(PAYLOAD).hexdigest()


class FixtureFetcher:
    def __init__(self):
        self.data = {}
        self.requests = []
        self.downloads = []

    def get(self, url):
        self.requests.append(url)
        value = self.data[url]
        if isinstance(value, Exception):
            raise value
        return value if isinstance(value, bytes) else json.dumps(value).encode()

    def json(self, url):
        return json.loads(self.get(url))

    def download(self, url, output):
        self.downloads.append(url)
        output.write_bytes(self.get(url))

    def git_tags(self, project):
        return self.json('git-tags:' + project)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='custom-update-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name) / 'source space'
        self.root.mkdir()
        self.git('init', '-q')
        self.git('config', 'user.name', 'Custom update test')
        self.git('config', 'user.email', 'custom-update@localhost')
        (self.root / '.config').write_text('CONFIG_PACKAGE_fixture=y\n')
        (self.root / 'unrelated').write_text('original\n')
        self.entries = {}
        self.fetcher = FixtureFetcher()

    def git(self, *args):
        return subprocess.check_output(['git', '-C', str(self.root), *args])

    def recipe(self, name, version='1.2.3', literal=False):
        path = self.root / 'package/custom' / name / 'Makefile'
        path.parent.mkdir(parents=True)
        path.write_text(f'PKG_NAME:={name}\nPKG_VERSION:={version}\nPKG_RELEASE:=7\n'
                        f'PKG_SOURCE:={name}-' + (version if literal else '$(PKG_VERSION)') + '.tar.gz\n'
                        'PKG_SOURCE_URL:=https://upstream.test/releases/\nPKG_HASH:=' + 'a' * 64 + '\n'
                        '# retain packaging intent\nMESON_ARGS += -Dfeature=enabled\n')
        patches = path.parent / 'patches'
        patches.mkdir()
        (patches / '001-local-feature.patch').write_text('local patch bytes\n')
        self.entries[name] = {'provider': 'directory', 'policy': 'series',
            'index': 'https://upstream.test/releases/',
            'filename_pattern': name + r'-(?P<version>[0-9]+(?:\.[0-9]+)+)\.tar\.gz'}
        return path

    def releases(self, *names, version='1.2.4', digest=DIGEST):
        links = []
        for name in names:
            filename = f'{name}-{version}.tar.gz'
            links += [f'<a href="{filename}">{filename}</a>',
                      f'<a href="{filename}.sha256">sha256</a>']
            self.fetcher.data['https://upstream.test/releases/' + filename] = PAYLOAD
            self.fetcher.data['https://upstream.test/releases/' + filename + '.sha256'] = (
                digest + '  ' + filename + '\n').encode()
        previous = self.fetcher.data.get('https://upstream.test/releases/', b'')
        self.fetcher.data['https://upstream.test/releases/'] = previous + '\n'.join(links).encode()

    def commit(self):
        self.git('add', '.')
        self.git('commit', '-qm', 'fixture source')

    def updater(self, update=True):
        return U.Updater(self.root, self.entries, self.fetcher, update=update,
                         record=self.root / 'record' if update else None)

    def execute(self, updater, selected=()):
        with redirect_stdout(io.StringIO()):
            return updater.execute(selected)

    def test_check_is_read_only_and_reports_numeric_version_order(self):
        path = self.recipe('fixture')
        self.releases('fixture', version='1.2.9')
        self.releases('fixture', version='1.2.10')
        self.releases('fixture', version='2.0.0')
        before = path.read_bytes()
        updater = self.updater(False)
        self.assertEqual(self.execute(updater), 1)
        row = updater.report['packages']['fixture']
        self.assertEqual(row['new_version'], '1.2.10')
        self.assertEqual(row['review_version'], '2.0.0')
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.fetcher.downloads)
        self.assertFalse((self.root / 'record').exists())

    def test_update_preserves_patches_config_and_unrelated_staged_work(self):
        path = self.recipe('fixture', literal=True)
        self.commit()
        (self.root / 'unrelated').write_text('staged\n')
        self.git('add', 'unrelated')
        (self.root / 'unrelated').write_text('unstaged\n')
        (self.root / 'private').write_text('private\n')
        index = (self.root / '.git/index').read_bytes()
        old = path.read_text()
        self.releases('fixture', version='1.2.30')
        updater = self.updater()
        self.assertEqual(self.execute(updater), 0)
        text = path.read_text()
        self.assertIn('PKG_VERSION:=1.2.30\n', text)
        self.assertIn('PKG_SOURCE:=fixture-1.2.30.tar.gz\n', text)
        self.assertIn('PKG_HASH:=' + DIGEST, text)
        self.assertIn('PKG_RELEASE:=1\n', text)
        self.assertIn('MESON_ARGS += -Dfeature=enabled', text)
        self.assertEqual((path.parent / 'patches/001-local-feature.patch').read_text(), 'local patch bytes\n')
        self.assertEqual((self.root / '.config').read_text(), 'CONFIG_PACKAGE_fixture=y\n')
        self.assertEqual((self.root / '.git/index').read_bytes(), index)
        self.assertEqual((self.root / 'unrelated').read_text(), 'unstaged\n')
        self.assertEqual((self.root / 'private').read_text(), 'private\n')
        self.assertEqual((self.root / 'record/before/package/custom/fixture/Makefile').read_text(), old)

    def test_bad_digest_preserves_recipe(self):
        path = self.recipe('fixture')
        self.commit()
        self.releases('fixture', digest='b' * 64)
        before = path.read_bytes()
        with self.assertRaisesRegex(U.UpdateError, 'SHA256 mismatch'):
            self.execute(self.updater())
        self.assertEqual(path.read_bytes(), before)

    def test_assume_unchanged_does_not_hide_local_recipe_edits(self):
        path = self.recipe('fixture')
        self.commit()
        self.git('update-index', '--assume-unchanged', str(path.relative_to(self.root)))
        path.write_text(path.read_text() + '# hidden local edit\n')
        self.releases('fixture')
        before = path.read_bytes()
        with self.assertRaisesRegex(U.UpdateError, 'locally modified recipe'):
            self.execute(self.updater())
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.fetcher.downloads)

    def test_dirty_recipe_is_rejected_before_download(self):
        path = self.recipe('fixture')
        self.commit()
        path.write_text(path.read_text() + '# local work\n')
        self.releases('fixture')
        before = path.read_bytes()
        with self.assertRaisesRegex(U.UpdateError, 'Local recipe changes'):
            self.execute(self.updater())
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.fetcher.downloads)

    def test_no_downgrade_and_same_version_hash_change_requires_review(self):
        path = self.recipe('fixture')
        self.releases('fixture', version='1.2.2')
        updater = self.updater(False)
        self.assertEqual(self.execute(updater), 0)
        self.assertEqual(updater.report['packages']['fixture']['status'], 'ahead')
        self.releases('fixture', version='1.2.3')
        before = path.read_bytes()
        with self.assertRaisesRegex(U.UpdateError, 'Same-version source digest'):
            self.execute(self.updater(False))
        self.assertEqual(path.read_bytes(), before)

    def test_unregistered_package_fails_without_network(self):
        self.recipe('fixture')
        self.entries.clear()
        with self.assertRaisesRegex(U.UpdateError, 'unregistered=fixture'):
            self.execute(self.updater(False))
        self.assertFalse(self.fetcher.requests)

    def test_followed_base_version_and_hash(self):
        path = self.recipe('binding')
        base = self.root / 'package/libs/base/Makefile'
        base.parent.mkdir(parents=True)
        base.write_text('PKG_VERSION:=1.3.1\nPKG_HASH:=' + DIGEST + '\n')
        self.entries['binding'] = {'provider': 'follow', 'recipe': 'package/libs/base/Makefile', 'same_source': True}
        self.commit()
        self.fetcher.data['https://upstream.test/releases/binding-1.3.1.tar.gz'] = PAYLOAD
        self.execute(self.updater())
        self.assertIn('PKG_VERSION:=1.3.1', path.read_text())
        self.assertEqual(base.read_text(), 'PKG_VERSION:=1.3.1\nPKG_HASH:=' + DIGEST + '\n')

    def linked_recipes(self):
        base, binding = self.recipe('base'), self.recipe('binding')
        self.entries['binding'] = {'provider': 'follow', 'recipe': 'package/custom/base/Makefile'}
        self.releases('base')
        self.fetcher.data['https://upstream.test/releases/binding-1.2.4.tar.gz'] = PAYLOAD
        self.commit()
        return base, binding

    def test_linked_group_selected_through_binding_updates_both(self):
        base, binding = self.linked_recipes()
        self.execute(self.updater(), ['binding'])
        self.assertIn('PKG_VERSION:=1.2.4', base.read_text())
        self.assertIn('PKG_VERSION:=1.2.4', binding.read_text())

    def test_linked_group_download_failure_writes_neither_recipe(self):
        base, binding = self.linked_recipes()
        old = [p.read_bytes() for p in (base, binding)]
        self.fetcher.data['https://upstream.test/releases/binding-1.2.4.tar.gz'] = U.UpdateError('offline')
        with self.assertRaisesRegex(U.UpdateError, 'offline'):
            self.execute(self.updater())
        self.assertEqual([p.read_bytes() for p in (base, binding)], old)

    def test_linked_group_rename_failure_restores_only_this_group(self):
        base, binding = self.linked_recipes()
        old = [p.read_bytes() for p in (base, binding)]
        replace = Path.replace
        def fail_second(path, target):
            if Path(target) == binding and path.name.startswith('Makefile.update.'):
                raise OSError('fixture rename failed')
            return replace(path, target)
        with patch.object(Path, 'replace', fail_second):
            with self.assertRaisesRegex(OSError, 'fixture rename failed'):
                self.execute(self.updater())
        self.assertEqual([p.read_bytes() for p in (base, binding)], old)
        self.assertFalse(list(self.root.rglob('Makefile.update.*')))

    def test_first_failure_keeps_completed_group_and_skips_later_group(self):
        paths = [self.recipe(n) for n in ('a', 'b', 'c')]
        self.commit()
        self.releases('a', 'c')
        self.releases('b', digest='b' * 64)
        updater = self.updater()
        with self.assertRaisesRegex(U.UpdateError, 'SHA256 mismatch'):
            self.execute(updater)
        self.assertIn('PKG_VERSION:=1.2.4', paths[0].read_text())
        self.assertIn('PKG_VERSION:=1.2.3', paths[1].read_text())
        self.assertIn('PKG_VERSION:=1.2.3', paths[2].read_text())
        self.assertEqual(updater.report['status'], 'failed')
        self.assertNotIn('c', updater.report['packages'])

    def test_special_archive_version_and_filename_override(self):
        text = ('PKG_NAME:=xorriso\nPKG_VERSION:=1.5.8_p2\nPKG_RELEASE:=3\nPKG_HASH:=' + 'a' * 64 + '\n'
                'PKG_SOURCE:=xorriso-1.5.8.pl02.tar.gz\nPKG_SOURCE_URL:=https://upstream.test/\n'
                'PKG_BUILD_DIR:=$(BUILD_DIR)/xorriso-1.5.8\n')
        updated = U.rewrite_recipe(text, '1.5.10_p3', DIGEST)
        self.assertIn('xorriso-1.5.10.pl03.tar.gz', updated)
        self.assertIn('$(BUILD_DIR)/xorriso-1.5.10\n', updated)
        self.assertEqual(U.package_version('1.5.10.pl03'), '1.5.10_p3')
        self.assertEqual(U.source_location(updated)[1], 'https://upstream.test/xorriso-1.5.10.pl03.tar.gz')
        text = ('PKG_NAME:=fixture\nPKG_VERSION:=1.2.3\nPKG_SOURCE:=fixture-$(PKG_VERSION).tar.gz\n'
                'PKG_SOURCE_URL:=https://codeload.github.com/owner/repo/tar.gz/v$(PKG_VERSION)?\n')
        self.assertEqual(U.source_location(text)[1], 'https://codeload.github.com/owner/repo/tar.gz/v1.2.3')

    def test_directory_and_unsupported_metadata_fail_closed(self):
        self.fetcher.data['https://upstream.test/'] = b'<html>login required</html>'
        with self.assertRaisesRegex(U.UpdateError, 'No recognizable'):
            U.catalog({'provider': 'directory', 'index': 'https://upstream.test/',
                       'filename_pattern': 'fixture-(?P<version>[0-9.]+).tar.gz'}, self.fetcher)
        with self.assertRaisesRegex(U.UpdateError, 'Duplicate metadata'):
            U.fields('PKG_VERSION:=1\nPKG_VERSION:=2\n')

    def test_pypi_excludes_yanked_and_prerelease_files(self):
        url = 'https://pypi.org/simple/pycairo/?format=application/vnd.pypi.simple.v1+json'
        self.fetcher.data[url] = {'files': [
            {'filename': 'pycairo-1.2.4.tar.gz', 'hashes': {'sha256': DIGEST}},
            {'filename': 'pycairo-1.2.5.tar.gz', 'yanked': True},
            {'filename': 'pycairo-1.2.8.tar.gz', 'yanked': ''},
            {'filename': 'pycairo-1.2.6rc1.tar.gz'}, {'filename': 'pycairo-1.2.7.whl'}]}
        releases = U.catalog({'provider': 'pypi', 'project': 'pycairo'}, self.fetcher)
        self.assertEqual(set(releases), {'1.2.4'})

    def test_pypi_inherited_source_fields_need_no_literal_url(self):
        path = self.recipe('pycairo')
        text = path.read_text()
        text = '\n'.join(line for line in text.splitlines() if not line.startswith(('PKG_SOURCE:=', 'PKG_SOURCE_URL:='))) + '\n'
        path.write_text(text + 'PYPI_NAME:=pycairo\n')
        self.entries['pycairo'] = {'provider': 'pypi', 'project': 'pycairo'}
        self.fetcher.data['https://pypi.org/simple/pycairo/?format=application/vnd.pypi.simple.v1+json'] = {
            'files': [{'filename': 'pycairo-1.2.3.tar.gz', 'hashes': {'sha256': 'a' * 64}}]}
        self.assertEqual(self.execute(self.updater(False)), 0)

    def test_followed_base_change_during_download_blocks_group_write(self):
        path = self.recipe('binding')
        base = self.root / 'package/libs/base/Makefile'
        base.parent.mkdir(parents=True)
        base.write_text('PKG_VERSION:=1.2.4\nPKG_HASH:=' + DIGEST + '\n')
        self.entries['binding'] = {'provider': 'follow', 'recipe': 'package/libs/base/Makefile', 'same_source': True}
        self.commit()
        self.fetcher.data['https://upstream.test/releases/binding-1.2.4.tar.gz'] = PAYLOAD
        original = path.read_bytes()
        download = self.fetcher.download
        def changed_source(url, output):
            download(url, output)
            base.write_text('PKG_VERSION:=1.2.5\nPKG_HASH:=' + DIGEST + '\n')
        with patch.object(self.fetcher, 'download', changed_source):
            with self.assertRaisesRegex(U.UpdateError, 'Followed recipe changed'):
                self.execute(self.updater())
        self.assertEqual(path.read_bytes(), original)

    def github_tags(self, *tags):
        self.fetcher.data['git-tags:owner/repo'] = [{'name': tag, 'object': '1' * 40} for tag in tags]

    def test_github_tags_use_no_rest_api_requests(self):
        self.github_tags('v1.2.4', 'v1.2.5', 'v1.2.6rc1')
        self.assertEqual(set(U.catalog({'provider': 'github', 'project': 'owner/repo'}, self.fetcher)),
                         {'1.2.4', '1.2.5'})
        self.assertEqual(self.fetcher.requests, ['git-tags:owner/repo'])

    def github_recipe(self):
        self.recipe('fixture')
        self.entries['fixture'] = {'provider': 'github', 'catalog': 'releases',
                                   'project': 'owner/repo', 'policy': 'series'}

    def test_existing_github_release_uses_no_api_quota(self):
        self.github_recipe()
        self.github_tags('v1.2.3', 'v2.0.0')
        updater = self.updater(False)
        self.assertEqual(self.execute(updater), 1)  # Review the other branch only.
        self.assertEqual(updater.report['packages']['fixture']['new_version'], '1.2.3')
        self.assertEqual(self.fetcher.requests, ['git-tags:owner/repo'])

    def test_new_github_releases_filter_draft_prerelease_and_unpublished_tags(self):
        self.github_recipe()
        self.github_tags('v1.2.3', 'v1.2.4', 'v1.2.7', 'v1.2.8', 'v1.2.9')
        url = 'https://api.github.com/repos/owner/repo/releases/tags/'
        self.fetcher.data[url + 'v1.2.9'] = {'tag_name': 'v1.2.9', 'draft': False, 'prerelease': True}
        self.fetcher.data[url + 'v1.2.8'] = {'tag_name': 'v1.2.8', 'draft': True, 'prerelease': False}
        self.fetcher.data[url + 'v1.2.7'] = U.FetchError('Not found', 404)
        self.fetcher.data[url + 'v1.2.4'] = {'tag_name': 'v1.2.4', 'draft': False, 'prerelease': False,
            'assets': [{'name': 'fixture-1.2.4.tar.gz', 'digest': 'sha256:' + DIGEST}]}
        updater = self.updater(False)
        self.execute(updater)
        self.assertEqual(updater.report['packages']['fixture']['new_version'], '1.2.4')
        self.assertNotIn(url + 'v1.2.3', self.fetcher.requests)

    def test_new_github_release_api_error_is_not_silently_ignored(self):
        self.github_recipe()
        self.github_tags('v1.2.3', 'v1.2.4')
        self.fetcher.data['https://api.github.com/repos/owner/repo/releases/tags/v1.2.4'] = U.FetchError('quota exhausted', 403)
        updater = self.updater(False)
        with self.assertRaisesRegex(U.FetchError, 'quota exhausted'):
            self.execute(updater)
        self.assertEqual(updater.report['status'], 'failed')

    def test_git_tag_listing_is_non_mutating_and_cached(self):
        output = '1' * 40 + '\trefs/tags/v1.2.4\n'
        response = subprocess.CompletedProcess([], 0, stdout=output, stderr='')
        fetcher = U.Fetcher()
        with patch.object(U.subprocess, 'run', return_value=response) as run:
            self.assertEqual(fetcher.git_tags('owner/repo'), [{'name': 'v1.2.4', 'object': '1' * 40}])
            fetcher.git_tags('owner/repo')
        run.assert_called_once()
        self.assertEqual(run.call_args.args[0],
                         ['git', 'ls-remote', '--tags', '--refs', 'https://github.com/owner/repo.git'])
        self.assertEqual(run.call_args.kwargs['env']['GIT_TERMINAL_PROMPT'], '0')

    def test_rate_limit_diagnostic_and_token_not_in_argv(self):
        def quota_response(command, **kwargs):
            self.assertNotIn('fixture-private-token', repr(command))
            self.assertEqual(kwargs['input'], b'Authorization: Bearer fixture-private-token\n')
            Path(command[command.index('--dump-header') + 1]).write_text(
                'HTTP/2 403\nx-ratelimit-remaining: 0\nx-ratelimit-reset: 1792339723\n')
            Path(command[command.index('--output') + 1]).write_text('{"message":"quota"}')
            return subprocess.CompletedProcess(command, 22, stdout=b'403', stderr=b'curl: HTTP 403')
        with patch.dict(os.environ, GH_TOKEN='fixture-private-token'), patch.object(U.subprocess, 'run', quota_response):
            with self.assertRaisesRegex(U.FetchError, 'rate limit exhausted; retry after') as caught:
                U.Fetcher().get('https://api.github.com/repos/owner/repo/releases/tags/v1.2.4')
        self.assertEqual(caught.exception.status, 403)
        self.assertNotIn('fixture-private-token', str(caught.exception))

    def test_token_is_never_sent_to_archive_host(self):
        def archive_response(command, **kwargs):
            self.assertIsNone(kwargs['input'])
            self.assertNotIn('--header', command)
            Path(command[command.index('--output') + 1]).write_bytes(PAYLOAD)
            return subprocess.CompletedProcess(command, 0, stdout=b'200', stderr=b'')
        with patch.dict(os.environ, GH_TOKEN='fixture-private-token'), patch.object(U.subprocess, 'run', archive_response):
            self.assertEqual(U.Fetcher().get('https://upstream.test/source.tar.gz'), PAYLOAD)

    def test_node_stays_in_current_lts_major(self):
        path = self.recipe('node', '24.1.0')
        self.entries['node'] = {'provider': 'node', 'policy': 'major'}
        self.fetcher.data['https://nodejs.org/dist/index.json'] = [
            {'version': 'v26.1.0', 'lts': 'New', 'files': ['linux-x64']},
            {'version': 'v25.2.0', 'lts': False, 'files': ['linux-x64']},
            {'version': 'v24.2.0', 'lts': 'Old', 'files': ['linux-x64']}]
        self.fetcher.data['https://nodejs.org/dist/v24.2.0/SHASUMS256.txt'] = (DIGEST + '  node-24.2.0.tar.gz\n').encode()
        updater = self.updater(False)
        self.execute(updater)
        self.assertEqual(updater.report['packages']['node']['new_version'], '24.2.0')
        self.assertEqual(updater.report['packages']['node']['review_version'], '26.1.0')
        self.assertIn('PKG_VERSION:=24.1.0', path.read_text())

    def test_firefox_selects_packaged_esr_major(self):
        self.recipe('firefox', '153.4.0esr')
        self.entries['firefox'] = {'provider': 'firefox', 'policy': 'major'}
        self.fetcher.data['https://product-details.mozilla.org/1.0/firefox_versions.json'] = {
            'FIREFOX_ESR': '153.5.0esr', 'FIREFOX_ESR_NEXT': '154.0.0esr'}
        self.fetcher.data['https://archive.mozilla.org/pub/firefox/releases/153.5.0esr/SHA256SUMS'] = (
            DIGEST + '  linux-x86_64/zh-CN/firefox-153.5.0esr.tar.xz\n' +
            'b' * 64 + '  linux-x86_64/en-US/firefox-153.5.0esr.tar.xz\n').encode()
        updater = self.updater(False)
        self.execute(updater)
        self.assertEqual(updater.report['packages']['firefox']['new_version'], '153.5.0esr')

    def test_source_relocation_keeps_pinned_digest_and_release(self):
        path = self.recipe('fixture')
        path.write_text(path.read_text().replace('a' * 64, DIGEST))
        self.entries['fixture']['source_url'] = 'https://new-upstream.test/v{version}/'
        self.releases('fixture', version='1.2.3')
        self.fetcher.data['https://new-upstream.test/v1.2.3/fixture-1.2.3.tar.gz'] = PAYLOAD
        self.commit()
        updater = self.updater()
        self.execute(updater)
        self.assertIn('PKG_RELEASE:=7\n', path.read_text())
        self.assertIn('PKG_HASH:=' + DIGEST, path.read_text())
        self.assertIn('PKG_SOURCE_URL:=https://new-upstream.test/v1.2.3/', path.read_text())
        self.assertTrue(updater.report['packages']['fixture']['source_relocation'])

    def test_gitlab_release_tags_and_development_archive_filter(self):
        url = 'https://gitlab.com/api/v4/projects/owner%2Frepo/releases?per_page=100&page=1'
        self.fetcher.data[url] = [{'tag_name': 'v1.2.4'}, {'tag_name': 'v1.2.5rc1'}]
        self.assertEqual(set(U.catalog({'provider': 'gitlab', 'host': 'https://gitlab.com',
            'project': 'owner/repo', 'catalog': 'releases'}, self.fetcher)), {'1.2.4'})
        self.releases('fixture', version='1.2.4')
        self.releases('fixture', version='1.2.5')
        entry = {'provider': 'directory', 'index': 'https://upstream.test/releases/',
                 'filename_pattern': r'fixture-(?P<version>[0-9.]+)\.tar\.gz',
                 'stable_pattern': r'[0-9]+\.[0-9]+\.[0-9]*[02468]'}
        self.assertEqual(set(U.catalog(entry, self.fetcher)), {'1.2.4'})
        self.releases('fixture', version='1.2.99.1')
        entry['stable_pattern'] = r'(?!.*\.99(?:\.|$))[0-9]+(?:\.[0-9]+)*'
        self.assertEqual(set(U.catalog(entry, self.fetcher)), {'1.2.4', '1.2.5'})

    def snapshot_recipe(self):
        path = self.recipe('fixture', version='2026.09.25')
        path.write_text(path.read_text().replace(
            'PKG_SOURCE:=fixture-$(PKG_VERSION).tar.gz',
            'PKG_SOURCE_VERSION:=2026_09_25.df90211\n'
            'PKG_SOURCE:=fixture-$(PKG_SOURCE_VERSION).tar.gz'))
        self.entries['fixture'].update(policy='stable', filename_pattern=
            r'fixture-(?P<source_version>(?P<version>[0-9]{4}_[0-9]{2}_[0-9]{2})\.[0-9a-f]{7,40})\.tar\.gz')
        return path

    def snapshot_release(self, tag):
        filename = 'fixture-' + tag + '.tar.gz'
        url = 'https://upstream.test/releases/'
        self.fetcher.data[url] = self.fetcher.data.get(url, b'') + (
            f'<a href="{filename}">{filename}</a>').encode()
        self.fetcher.data[url + filename] = PAYLOAD

    def test_date_snapshot_updates_version_tag_source_and_hash_together(self):
        path = self.snapshot_recipe()
        self.snapshot_release('2026_09_25.df90211')
        self.snapshot_release('2026_09_25.abcdef0')
        self.snapshot_release('2026_10_02.cba3570')
        self.commit()
        updater = self.updater()
        self.execute(updater)
        metadata = U.fields(path.read_text())
        self.assertEqual(metadata['PKG_VERSION'], '2026.10.02')
        self.assertEqual(metadata['PKG_SOURCE_VERSION'], '2026_10_02.cba3570')
        self.assertEqual(metadata['PKG_RELEASE'], '1')
        self.assertEqual(metadata['PKG_HASH'], DIGEST)
        self.assertEqual(self.fetcher.downloads,
                         ['https://upstream.test/releases/fixture-2026_10_02.cba3570.tar.gz'])
        self.assertIn('MESON_ARGS += -Dfeature=enabled', path.read_text())

    def test_date_snapshot_rejects_ambiguous_and_replaced_tags(self):
        path = self.snapshot_recipe()
        before = path.read_bytes()
        self.snapshot_release('2026_09_25.df90211')
        self.snapshot_release('2026_09_25.abcdef0')
        with self.assertRaisesRegex(U.UpdateError, 'Ambiguous source snapshots'):
            self.execute(self.updater())
        self.fetcher.data['https://upstream.test/releases/'] = b''
        self.snapshot_release('2026_09_25.abcdef0')
        with self.assertRaisesRegex(U.UpdateError, 'Same-version source snapshot changed'):
            self.execute(self.updater())
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.fetcher.downloads)

    def test_date_snapshot_retains_local_recipe_changes(self):
        path = self.snapshot_recipe()
        self.commit()
        path.write_text(path.read_text() + '# local packaging edit\n')
        before = path.read_bytes()
        self.snapshot_release('2026_10_02.cba3570')
        with self.assertRaisesRegex(U.UpdateError, 'Local recipe changes block updating'):
            self.execute(self.updater())
        self.assertEqual(path.read_bytes(), before)
        self.assertFalse(self.fetcher.downloads)

    def test_live_registry_covers_all_recipe_directories(self):
        data = json.loads((TREE / 'configs/custom-package-updates.json').read_text())
        self.assertEqual(data['schema'], 1)
        self.assertEqual(set(data['packages']),
                         {p.parent.name for p in (TREE / 'package/custom').glob('*/Makefile')})


class FeedsIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='custom-feeds-test-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for directory in ('scripts', 'bin', 'package/custom/fixture', 'local-other', 'feeds'):
            (self.root / directory).mkdir(parents=True)
        shutil.copy2(TREE / 'scripts/feeds', self.root / 'scripts/feeds')
        shutil.copy2(TREE / 'scripts/metadata.pm', self.root / 'scripts/metadata.pm')
        (self.root / 'feeds.conf.default').write_text(
            'src-link custom ../package/custom\nsrc-link other ../local-other\n')
        (self.root / 'package/custom/fixture/Makefile').write_text('PKG_VERSION:=1.2.3\n')
        (self.root / 'scripts/update-custom-packages.py').write_text('''import os
from pathlib import Path
p = Path('package/custom/fixture/Makefile')
with Path('calls').open('a') as stream: stream.write('custom-update\\n')
p.write_text('PKG_VERSION:=1.2.4\\n')
raise SystemExit(int(os.environ.get('CUSTOM_FIXTURE_FAIL', '0')))
''')
        make = '''#!/usr/bin/env python3
import os, sys
from pathlib import Path
if '-v' in sys.argv:
    print('GNU Make 4.4')
    raise SystemExit(0)
with Path('calls').open('a') as stream: stream.write('make ' + ' '.join(sys.argv[1:]) + '\\n')
if os.environ.get('CUSTOM_INDEX_FAIL'):
    raise SystemExit(1)
values = dict(a.split('=', 1) for a in sys.argv[1:] if '=' in a)
if 'SCAN_DIR' in values:
    output = Path(values['TMP_DIR']) / ('.packageinfo' if values['SCAN_TARGET'] == 'packageinfo' else '.targetinfo')
    source = Path('package/custom/fixture/Makefile')
    output.write_text(source.read_text())
'''
        for binary in ('make', 'gmake'):
            path = self.root / 'bin' / binary
            path.write_text(make)
            path.chmod(0o755)
        self.env = dict(os.environ, TOPDIR=str(self.root),
                        PATH=str(self.root / 'bin') + os.pathsep + os.environ['PATH'])

    def run_feeds(self, *args, **env):
        return subprocess.run(['perl', str(self.root / 'scripts/feeds'), 'update', *args],
                              cwd=self.root, env=dict(self.env, **env), capture_output=True, text=True)

    def calls(self):
        return (self.root / 'calls').read_text() if (self.root / 'calls').exists() else ''

    def test_update_all_runs_custom_before_indexes_without_compiling(self):
        result = self.run_feeds('-a')
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.calls().splitlines()
        self.assertEqual(calls[0], 'custom-update')
        self.assertEqual(calls.count('custom-update'), 1)
        self.assertTrue(all('compile' not in call for call in calls))
        self.assertIn('PKG_VERSION:=1.2.4', (self.root / 'feeds/custom.index').read_text())

    def test_named_custom_triggers_update_but_other_feed_does_not(self):
        self.assertEqual(self.run_feeds('other').returncode, 0)
        self.assertNotIn('custom-update', self.calls())
        self.assertEqual(self.run_feeds('custom').returncode, 0)
        self.assertEqual(self.calls().splitlines().count('custom-update'), 1)

    def test_index_only_never_calls_custom_updater(self):
        (self.root / 'feeds/custom').symlink_to('../package/custom')
        (self.root / 'feeds/other').symlink_to('../local-other')
        result = self.run_feeds('-i', '-a')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('custom-update', self.calls())
        self.assertIn('PKG_VERSION:=1.2.3', (self.root / 'feeds/custom.index').read_text())

    def test_external_src_link_named_custom_is_not_updated(self):
        (self.root / 'feeds.conf.default').write_text('src-link custom ../local-other\n')
        result = self.run_feeds('custom')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn('custom-update', self.calls())

    def test_partial_custom_failure_reindexes_and_propagates_failure(self):
        result = self.run_feeds('-a', CUSTOM_FIXTURE_FAIL='2')
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('PKG_VERSION:=1.2.4', (self.root / 'feeds/custom.index').read_text())

    def test_index_scan_failure_is_not_reported_as_success(self):
        result = self.run_feeds('-a', CUSTOM_INDEX_FAIL='1')
        self.assertNotEqual(result.returncode, 0)

    def test_failed_feed_skips_custom_upstream_changes(self):
        with (self.root / 'feeds.conf.default').open('a') as stream:
            stream.write('src-unknown broken ignored\n')
        result = self.run_feeds('-a')
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn('custom-update', self.calls())
        self.assertIn('PKG_VERSION:=1.2.3', (self.root / 'feeds/custom.index').read_text())


if __name__ == '__main__':
    unittest.main()
