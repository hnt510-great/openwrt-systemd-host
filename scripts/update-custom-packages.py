#!/usr/bin/env python3
"""Update local custom recipes; downloading/building remains OpenWrt's job."""
import argparse
from datetime import datetime, timezone
import fcntl
import hashlib
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import quote, unquote, urljoin, urlparse
import xml.etree.ElementTree as ET


class UpdateError(Exception):
    pass


class FetchError(UpdateError):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def fields(text):
    result = {}
    for key, value in re.findall(r'^(PKG_[A-Z_]+):=(.*)$', text, re.M):
        if key in result:
            raise UpdateError('Duplicate metadata field: ' + key)
        result[key] = value.strip()
    return result


def version_key(version):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+)*(?:_p[0-9]+)?(?:esr)?', version):
        raise UpdateError('Unsupported stable version: ' + version)
    numbers = tuple(map(int, re.findall(r'[0-9]+', version)))
    return numbers + (0,) * max(0, 8 - len(numbers))


def package_version(raw):
    return re.sub(r'\.pl0*([0-9]+)$', r'_p\1', raw)


def archive_version(version):
    return re.sub(r'_p([0-9]+)$', lambda m: '.pl' + m[1].zfill(2), version)


def in_branch(version, current, policy):
    if policy == 'stable':
        return True
    width = 1 if policy == 'major' else 2
    return version_key(version)[:width] == version_key(current)[:width]


class Links(HTMLParser):
    def __init__(self, body, base):
        super().__init__()
        self.links = []
        self.base = base
        self.feed(body)

    def handle_starttag(self, tag, attrs):
        if tag == 'a':
            for key, value in attrs:
                if key == 'href' and value:
                    self.links.append(urljoin(self.base, value))


class Fetcher:
    """Bounded HTTPS requests, with cached metadata and streamed archives."""
    def __init__(self):
        self.cache = {}
        self.tag_cache = {}

    def request(self, url, output=None):
        if urlparse(url).scheme != 'https':
            raise UpdateError('Expected an HTTPS upstream URL: ' + url)
        command = ['curl', '--fail', '--silent', '--show-error', '--location',
                   '--proto', '=https', '--proto-redir', '=https',
                   '--connect-timeout', '15', '--max-time', '300',
                   '--retry', '2', '--user-agent', 'openwrt-custom-package-updater']
        # Keep credentials off the command line, and restrict them to the API host.
        header_input = None
        if urlparse(url).hostname == 'api.github.com':
            token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
            if token:
                if '\n' in token or '\r' in token:
                    raise UpdateError('Invalid GitHub token environment value')
                command += ['--header', '@-']
                header_input = ('Authorization: Bearer ' + token + '\n').encode()
        with tempfile.TemporaryDirectory(prefix='openwrt-custom-http-') as directory:
            headers = Path(directory) / 'headers'
            body = Path(directory) / 'body' if output is None else output
            result = subprocess.run(command + ['--dump-header', str(headers), '--output', str(body),
                                    '--write-out', '%{http_code}', url], input=header_input,
                                    capture_output=True)
            status = int(result.stdout) if result.stdout.strip().isdigit() else 0
            if result.returncode:
                response_headers = {}
                if headers.exists():
                    for line in headers.read_text(errors='replace').splitlines():
                        if line.startswith('HTTP/'):
                            response_headers = {}
                        elif ':' in line:
                            key, value = line.split(':', 1)
                            response_headers[key.lower()] = value.strip()
                reason = result.stderr.decode(errors='replace').strip()
                if (urlparse(url).hostname == 'api.github.com' and status in (403, 429) and
                        response_headers.get('x-ratelimit-remaining') == '0'):
                    reset = response_headers.get('x-ratelimit-reset', '')
                    retry = datetime.fromtimestamp(int(reset), timezone.utc).isoformat() if reset.isdigit() else 'the quota resets'
                    reason = 'GitHub API rate limit exhausted; retry after ' + retry + ' or supply GH_TOKEN/GITHUB_TOKEN'
                raise FetchError('Fetch failed for ' + url + ': ' + reason, status)
            return body.read_bytes() if output is None else b''

    def get(self, url):
        if url not in self.cache:
            self.cache[url] = self.request(url)
        return self.cache[url]

    def json(self, url):
        return json.loads(self.get(url))

    def download(self, url, output):
        self.request(url, output)


    def git_tags(self, project):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', project):
            raise UpdateError('Invalid GitHub project name')
        if project not in self.tag_cache:
            url = 'https://github.com/' + project + '.git'
            try:
                result = subprocess.run(['git', 'ls-remote', '--tags', '--refs', url],
                                        env=dict(os.environ, GIT_TERMINAL_PROMPT='0'),
                                        capture_output=True, text=True, timeout=120)
            except subprocess.TimeoutExpired as error:
                raise UpdateError('Timed out listing upstream tags: ' + url) from error
            if result.returncode:
                raise UpdateError('Cannot list upstream tags for ' + url + ': ' + result.stderr.strip())
            tags = []
            for line in result.stdout.splitlines():
                match = re.fullmatch(r'([0-9a-f]{40,64})\trefs/tags/(.+)', line)
                if not match:
                    raise UpdateError('Unexpected Git tag advertisement from ' + url)
                tags.append({'name': match[2], 'object': match[1]})
            self.tag_cache[project] = tags
        return self.tag_cache[project]


def paged(fetcher, url):
    separator = '&' if '?' in url else '?'
    for page in range(1, 101):
        data = fetcher.json(f'{url}{separator}per_page=100&page={page}')
        if not isinstance(data, list):
            raise UpdateError('Expected a release/tag list from ' + url)
        yield from data
        if len(data) < 100:
            return
    raise UpdateError('Release pagination limit reached: ' + url)


def stable_tag(tag, pattern=r'v?(?P<version>[0-9]+(?:\.[0-9]+)*)'):
    match = re.fullmatch(pattern, tag)
    return match['version'] if match else None


def catalog(entry, fetcher):
    provider = entry['provider']
    versions = {}
    if provider == 'github':
        kind = entry.get('catalog', 'tags')
        url = f'https://github.com/{entry["project"]}.git'
        for reference in fetcher.git_tags(entry['project']):
            tag = reference['name']
            version = stable_tag(tag, entry.get('tag_pattern',
                                 r'v?(?P<version>[0-9]+(?:\.[0-9]+)*)'))
            if version:
                meta = {'catalog': url, 'tag': tag, 'tag_object': reference['object']}
                if kind == 'releases':
                    meta['release_url'] = f'https://api.github.com/repos/{entry["project"]}/releases/tags/' + quote(tag, safe='')
                versions[version] = meta
    elif provider == 'gitlab':
        kind = 'releases' if entry.get('catalog') == 'releases' else 'repository/tags'
        url = entry['host'] + '/api/v4/projects/' + quote(entry['project'], safe='') + '/' + kind
        for tag in paged(fetcher, url):
            if tag.get('upcoming_release'):
                continue
            version = stable_tag(tag.get('tag_name', tag.get('name', '')))
            if version:
                versions[version] = {'catalog': url}
    elif provider == 'directory':
        url = entry['index']
        links = Links(fetcher.get(url).decode(), url).links
        by_name = {unquote(urlparse(link).path.rsplit('/', 1)[-1]): link for link in links}
        for name, link in by_name.items():
            match = re.fullmatch(entry['filename_pattern'], name)
            if match:
                version = package_version(match['version'])
                if entry.get('stable_pattern') and not re.fullmatch(entry['stable_pattern'], version):
                    continue
                meta = {'catalog': url}
                for suffix in ('.sha256sum', '.sha256'):
                    if name + suffix in by_name:
                        meta['checksums'] = by_name[name + suffix]
                        break
                versions[version] = meta
        # GNOME publishes maintenance branches in separate directories.
        if entry.get('series_index'):
            parent = entry['series_index']
            for link in Links(fetcher.get(parent).decode(), parent).links:
                series = urlparse(link).path.rstrip('/').rsplit('/', 1)[-1]
                if re.fullmatch(r'[0-9]+\.[0-9]+', series) and int(series.split('.')[1]) % 2 == 0:
                    versions.setdefault(series + '.0', {'catalog': parent, 'review_only': True,
                                                        'review_series': series})
    elif provider == 'pypi':
        url = f'https://pypi.org/simple/{entry["project"]}/'
        # PEP 691 JSON is also selectable through the format query parameter.
        data = fetcher.json(url + '?format=application/vnd.pypi.simple.v1+json')
        prefix = entry['project'].replace('-', '_') + '-'
        for file in data['files']:
            filename = file['filename']
            if file.get('yanked', False) is not False or not filename.endswith('.tar.gz'):
                continue
            normalized = filename.replace('-', '_', len(entry['project'].split('-')) - 1)
            if not normalized.startswith(prefix):
                continue
            version = normalized[len(prefix):-7]
            if re.fullmatch(r'[0-9]+(?:\.[0-9]+)*', version):
                versions[version] = {'hash': file['hashes']['sha256'], 'catalog': url}
    elif provider == 'node':
        url = 'https://nodejs.org/dist/index.json'
        for release in fetcher.json(url):
            if isinstance(release.get('lts'), str) and 'linux-x64' in release.get('files', []):
                version = stable_tag(release['version'])
                if version:
                    versions[version] = {'catalog': url, 'checksums':
                                        f'https://nodejs.org/dist/v{version}/SHASUMS256.txt'}
    elif provider == 'firefox':
        url = 'https://product-details.mozilla.org/1.0/firefox_versions.json'
        data = fetcher.json(url)
        for key in ('FIREFOX_ESR', 'FIREFOX_ESR_NEXT'):
            version = data.get(key, '')
            if re.fullmatch(r'[0-9]+(?:\.[0-9]+)+esr', version):
                versions[version] = {'catalog': url, 'checksums':
                    f'https://archive.mozilla.org/pub/firefox/releases/{version}/SHA256SUMS',
                    'checksum_filename': f'linux-x86_64/zh-CN/firefox-{version}.tar.xz'}
    elif provider == 'sourceforge':
        url = f'https://sourceforge.net/projects/{entry["project"]}/rss?path=/traceroute&limit=100'
        data = ET.fromstring(fetcher.get(url))
        for item in data.findall('.//item/link'):
            match = re.search(r'/traceroute-([0-9]+(?:\.[0-9]+)+)/', item.text or '')
            if match:
                versions[match[1]] = {'catalog': url}
    else:
        raise UpdateError('Unknown upstream provider: ' + provider)
    if not versions:
        raise UpdateError('No recognizable stable releases from ' + provider)
    return versions


def rewrite_recipe(text, version, digest, source_url=None):
    old = fields(text)['PKG_VERSION']
    before, after = archive_version(old), archive_version(version)
    metadata = fields(text)
    changed = {'PKG_VERSION': version, 'PKG_HASH': digest,
               'PKG_RELEASE': '1' if version != old else metadata['PKG_RELEASE']}
    for key in ('PKG_SOURCE', 'PKG_SOURCE_URL', 'PKG_SOURCE_URL_FILE', 'PKG_BUILD_DIR'):
        if key in metadata:
            replacements = {old: version, before: after}
            if '_p' in old:
                replacements[before.split('.pl')[0]] = after.split('.pl')[0]
            if key == 'PKG_SOURCE_URL':
                replacements['.'.join(old.split('.')[:2])] = '.'.join(version.split('.')[:2])
            pattern = '|'.join(re.escape(k) for k in sorted(replacements, key=len, reverse=True))
            value = re.sub(pattern, lambda m: replacements[m[0]], metadata[key])
            changed[key] = value
    if source_url:
        changed['PKG_SOURCE_URL'] = source_url.format(version=version)
    for key, value in changed.items():
        text, count = re.subn(r'^' + key + r':=.*$', lambda m: key + ':=' + value, text, flags=re.M)
        if count != 1:
            raise UpdateError('Missing/ambiguous metadata field: ' + key)
    return text


def source_location(text):
    values = fields(text)
    if 'PKG_SOURCE' not in values and 'PYPI_NAME:=' in text:
        project = re.search(r'^PYPI_NAME:=(.+)$', text, re.M)[1].strip()
        values['PKG_SOURCE'] = project + '-' + values['PKG_VERSION'] + '.tar.gz'
        values['PKG_SOURCE_URL'] = f'https://files.pythonhosted.org/packages/source/{project[0]}/{project}/'

    def expand(value):
        for _ in range(8):
            if '$(' not in value:
                break
            value = re.sub(r'\$\((PKG_[A-Z_]+)\)', lambda m: values.get(m[1], m[0]), value)
        if '$' in value:
            raise UpdateError('Unsupported source expression: ' + value)
        return value

    filename = expand(values['PKG_SOURCE'])
    url = expand(values['PKG_SOURCE_URL'])
    for alias, base in (('@GNOME/', 'https://download.gnome.org/sources/'),
                        ('@GNU/', 'https://ftp.gnu.org/gnu/'),
                        ('@KERNEL/', 'https://cdn.kernel.org/pub/')):
        if url.startswith(alias):
            url = base + url[len(alias):]
    if url.endswith('?'):
        url = url[:-1]
    else:
        url = url.rstrip('/') + '/' + expand(values.get('PKG_SOURCE_URL_FILE', filename))
    if urlparse(url).scheme != 'https' or '/' in filename or filename in ('', '.', '..'):
        raise UpdateError('Unsupported source location: ' + url)
    return filename, url


def checksum_for(body, filename):
    matches = []
    for line in body.decode().splitlines():
        match = re.fullmatch(r'([0-9a-fA-F]{64})\s+\*?(\S+)', line.strip())
        if match and (match[2] == filename if '/' in filename else match[2].rsplit('/', 1)[-1] == filename):
            matches.append(match[1].lower())
        elif re.fullmatch(r'[0-9a-fA-F]{64}', line.strip()):
            matches.append(line.strip().lower())
    if len(matches) != 1:
        raise UpdateError('Missing/ambiguous SHA256 for ' + filename)
    return matches[0]


def valid_hash(digest):
    if not isinstance(digest, str) or not re.fullmatch(r'[0-9a-f]{64}', digest):
        raise UpdateError('Invalid SHA256 digest')
    return digest


def file_hash(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def validate_payload(path, filename):
    with path.open('rb') as stream:
        prefix = stream.read(8)
    signature = next((magic for suffix, magic in (('.gz', b'\x1f\x8b'), ('.xz', b'\xfd7zXZ\x00'),
                         ('.bz2', b'BZh'), ('.otf', b'OTTO')) if filename.endswith(suffix)), None)
    if signature is None or not prefix.startswith(signature):
        raise UpdateError('Unexpected source format for ' + filename)


class Updater:
    def __init__(self, root, entries, fetcher=None, update=False, record=None):
        self.root = root.resolve()
        self.entries = entries
        self.fetcher = fetcher or Fetcher()
        self.update = update
        self.record = record
        self.followed_inputs = {}
        self.report = {'schema': 1, 'mode': 'update' if update else 'check',
                       'status': 'running', 'packages': {}}

    def recipe(self, name):
        return self.root / 'package/custom' / name / 'Makefile'

    def groups(self, selected):
        actual = {p.parent.name for p in (self.root / 'package/custom').glob('*/Makefile')}
        if actual != set(self.entries):
            raise UpdateError('Custom registry mismatch; unregistered=' +
                              ','.join(sorted(actual - set(self.entries))) + '; missing=' +
                              ','.join(sorted(set(self.entries) - actual)))
        unknown = set(selected) - actual
        if unknown:
            raise UpdateError('Unknown custom package: ' + ','.join(sorted(unknown)))
        parents = {}
        for name, entry in self.entries.items():
            if entry['provider'] == 'follow':
                path = self.root / entry['recipe']
                if not path.resolve().is_relative_to(self.root):
                    raise UpdateError('Followed recipe is outside the workspace')
                if path.parent.parent == self.root / 'package/custom':
                    parents[name] = path.parent.name
        def leader(name, seen=()):
            if name in seen:
                raise UpdateError('Cyclic custom follow relationship')
            return leader(parents[name], seen + (name,)) if name in parents else name
        wanted = {leader(n) for n in selected} if selected else {leader(n) for n in actual}
        groups = {}
        for name in sorted(actual):
            root = leader(name)
            if root in wanted:
                groups.setdefault(root, []).append(name)
        return [[key] + [n for n in names if n != key] for key, names in sorted(groups.items())]

    def assert_clean(self, paths):
        result = subprocess.run(['git', '-C', str(self.root), 'status', '--porcelain=v1', '-z',
                                 '--untracked-files=all', '--', *[str(p.relative_to(self.root)) for p in paths]],
                                capture_output=True)
        if result.returncode:
            raise UpdateError('Cannot inspect recipe Git state: ' + result.stderr.decode().strip())
        if result.stdout:
            raise UpdateError('Local recipe changes block updating: ' +
                              ', '.join(str(p.relative_to(self.root)) for p in paths))
        # status can hide working-tree edits marked assume-unchanged/skip-worktree,
        # and ignored untracked recipes. Compare the actual bytes with HEAD too.
        for path in paths:
            relative = str(path.relative_to(self.root))
            committed = subprocess.run(['git', '-C', str(self.root), 'show', 'HEAD:' + relative],
                                       capture_output=True)
            if committed.returncode or committed.stdout != path.read_bytes():
                raise UpdateError('Untracked or locally modified recipe: ' + relative)

    def discover(self, name, planned):
        entry = self.entries[name]
        text = self.recipe(name).read_text()
        metadata = fields(text)
        row = {'old_version': metadata.get('PKG_VERSION'), 'provider': entry['provider']}
        self.report['packages'][name] = row
        if entry['provider'] == 'local':
            row.update(status='local', reason=entry['reason'])
            return None
        current = metadata['PKG_VERSION']
        version_key(current)
        valid_hash(metadata['PKG_HASH'])
        if not metadata.get('PKG_RELEASE', '').isdecimal():
            raise UpdateError('Expected a literal PKG_RELEASE in ' + name)
        if entry['provider'] == 'follow':
            path = self.root / entry['recipe']
            self.followed_inputs[path] = path.read_text()
            followed_text = planned.get(path, self.followed_inputs[path])
            followed = fields(followed_text)
            version = followed['PKG_VERSION']
            if version_key(version) < version_key(current):
                raise UpdateError('Refusing followed-source downgrade for ' + name)
            meta = {'catalog': entry['recipe']}
            if entry.get('same_source'):
                meta['hash'] = valid_hash(followed['PKG_HASH'])
        else:
            versions = catalog(entry, self.fetcher)
            allowed = [v for v, info in versions.items() if not info.get('review_only') and
                       in_branch(v, current, entry.get('policy', 'series'))]
            # Existing pinned versions need no release-history request. Validate
            # only newer candidates, keeping draft/prerelease filtering intact.
            published = []
            for candidate in sorted(allowed, key=version_key, reverse=True):
                info = versions[candidate]
                if version_key(candidate) > version_key(current) and info.get('release_url'):
                    try:
                        release = self.fetcher.json(info['release_url'])
                    except FetchError as error:
                        if error.status == 404:  # A tag need not have a published release.
                            continue
                        raise
                    if not isinstance(release, dict) or any(type(release.get(k)) is not bool
                                                           for k in ('draft', 'prerelease')):
                        raise UpdateError('Invalid upstream release metadata for ' + name)
                    if release.get('draft') or release.get('prerelease'):
                        continue
                    if release.get('tag_name') != info['tag']:
                        raise UpdateError('Upstream release/tag mismatch for ' + name)
                    info.update(release=release, catalog=info['release_url'])
                published.append(candidate)
                break
            allowed = published
            available = max(versions, key=version_key)
            if version_key(available) > version_key(current) and not in_branch(
                    available, current, entry.get('policy', 'series')):
                row['review_version'] = versions[available].get('review_series', available)
            version = max(allowed, key=version_key) if allowed else current
            if version_key(version) < version_key(current):
                row.update(status='ahead', new_version=current,
                           reason='Local version is newer than the advertised maintenance releases')
                return None
            if not allowed:
                row.update(status='review', new_version=current,
                           reason='Current maintenance branch is not advertised upstream')
                return None
            meta = versions[version]
        # A placeholder digest allows source names to be expanded before downloading.
        proposed = rewrite_recipe(text, version, metadata['PKG_HASH'], entry.get('source_url'))
        filename, url = source_location(proposed)
        row.update(new_version=version, source=url, catalog=meta['catalog'])
        if meta.get('tag_object'):
            row['tag_object'] = meta['tag_object']
        digest = meta.get('hash')
        for asset in meta.get('release', {}).get('assets', []):
            if asset['name'] == filename and asset.get('digest'):
                if not asset['digest'].startswith('sha256:'):
                    raise UpdateError('Unsupported upstream asset digest')
                digest = asset['digest'].split(':', 1)[1]
        sums = entry.get('checksums', meta.get('checksums'))
        if sums:
            sums = sums.format(version=version)
            digest = checksum_for(self.fetcher.get(sums), meta.get('checksum_filename', filename))
        if digest:
            valid_hash(digest)
        if version == current:
            if digest and digest != metadata['PKG_HASH']:
                raise UpdateError('Same-version source digest changed; review ' + name + ' manually')
            if fields(proposed).get('PKG_SOURCE_URL') == metadata.get('PKG_SOURCE_URL'):
                row['status'] = 'review' if row.get('review_version') else 'current'
                return None
            row['source_relocation'] = True
            digest = metadata['PKG_HASH']
        row['status'] = 'available'
        if not self.update:
            return proposed
        self.assert_clean([self.recipe(name)])
        with tempfile.TemporaryDirectory(prefix='openwrt-custom-source-') as temporary:
            downloaded = Path(temporary) / filename
            self.fetcher.download(url, downloaded)
            validate_payload(downloaded, filename)
            actual = file_hash(downloaded)
        if digest and actual != digest:
            raise UpdateError('Upstream SHA256 mismatch for ' + name)
        digest = actual
        row.update(sha256=digest, verification='upstream-sha256' if meta.get('hash') or sums or
                   any(a.get('digest') for a in meta.get('release', {}).get('assets', [])
                       if a['name'] == filename) else 'downloaded-https-source')
        return rewrite_recipe(text, version, digest, entry.get('source_url'))

    def apply(self, changes, originals):
        self.assert_clean(list(changes))
        for path, original in self.followed_inputs.items():
            if path.read_text() != original:
                raise UpdateError('Followed recipe changed while checking upstream: ' + str(path))
        staged = {}
        replaced = []
        try:
            for path, text in changes.items():
                if path.read_text() != originals[path]:
                    raise UpdateError('Recipe changed while checking upstream: ' + str(path))
                if self.record:
                    backup = self.record / 'before' / path.relative_to(self.root)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    backup.write_text(originals[path])
                fd, temporary = tempfile.mkstemp(prefix='Makefile.update.', dir=path.parent)
                staged[path] = Path(temporary)
                with os.fdopen(fd, 'w') as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                staged[path].chmod(path.stat().st_mode & 0o777)
            for path, temporary in staged.items():
                if path.read_text() != originals[path]:
                    raise UpdateError('Recipe changed before replacement: ' + str(path))
                temporary.replace(path)
                replaced.append(path)
        except BaseException:
            # A linked group must not be left at different versions on an I/O error.
            for path in reversed(replaced):
                if path.read_text() == changes[path]:
                    fd, temporary = tempfile.mkstemp(prefix='Makefile.restore.', dir=path.parent)
                    with os.fdopen(fd, 'w') as stream:
                        stream.write(originals[path])
                    Path(temporary).chmod(path.stat().st_mode & 0o777)
                    Path(temporary).replace(path)
            raise
        finally:
            for temporary in staged.values():
                temporary.unlink(missing_ok=True)

    def execute(self, selected=()):
        try:
            for group in self.groups(selected):
                self.followed_inputs = {}
                originals = {self.recipe(n): self.recipe(n).read_text() for n in group}
                changes = {}
                for name in group:
                    try:
                        updated = self.discover(name, changes)
                        if updated is not None:
                            changes[self.recipe(name)] = updated
                    except Exception as error:
                        self.report['packages'].setdefault(name, {}).update(status='failed', error=str(error))
                        raise
                if self.update and changes:
                    self.apply(changes, originals)
                    for path in changes:
                        self.report['packages'][path.parent.name]['status'] = 'updated'
                for name in group:
                    row = self.report['packages'][name]
                    print(f'{name}: {row["status"]}' +
                          (f' {row["old_version"]} -> {row["new_version"]}' if 'new_version' in row else '') +
                          (f' (review branch {row["review_version"]})' if row.get('review_version') else ''), flush=True)
            self.report['status'] = 'passed'
        except BaseException as error:
            self.report.update(status='failed', error=str(error))
            raise
        return int(not self.update and any(r['status'] in ('available', 'review') or r.get('review_version')
                                          for r in self.report['packages'].values()))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--check', action='store_true', help='Read-only check (default); exit 1 for updates/review')
    mode.add_argument('--update', action='store_true', help='Update recipes, without building or publishing')
    parser.add_argument('--package', action='append', default=[], help='Restrict to a package and its linked group')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    updater = None
    try:
        registry = json.loads((root / 'configs/custom-package-updates.json').read_text())
        if registry['schema'] != 1:
            raise UpdateError('Unsupported custom registry schema')
        if not args.update:
            return Updater(root, registry['packages']).execute(args.package)
        gitdir = subprocess.check_output(['git', '-C', str(root), 'rev-parse', '--absolute-git-dir'], text=True).strip()
        with (Path(gitdir) / 'custom-package-updates.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise UpdateError('Another custom package update is running')
            for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'rebase-merge', 'rebase-apply', 'index.lock'):
                if (Path(gitdir) / marker).exists():
                    raise UpdateError('Finish the pending Git operation first: ' + marker)
            stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
            record = root / 'logs/custom-package-updates' / stamp
            record.mkdir(parents=True)
            updater = Updater(root, registry['packages'], update=True, record=record)
            try:
                return updater.execute(args.package)
            finally:
                (record / 'report.json').write_text(json.dumps(updater.report, indent=2) + '\n')
                print('Custom update report: ' + str(record / 'report.json'), flush=True)
    except (UpdateError, OSError, ValueError, KeyError, subprocess.CalledProcessError, ET.ParseError) as error:
        print('Custom update failed: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
