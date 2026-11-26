#!/usr/bin/env python3
"""Update local custom recipes; downloading/building remains OpenWrt's job."""
import argparse
from concurrent.futures import ThreadPoolExecutor
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
import threading
from urllib.parse import quote, unquote, urljoin, urlparse
import xml.etree.ElementTree as ET


class UpdateError(Exception):
    pass


class FetchError(UpdateError):
    def __init__(self, message, status=0):
        super().__init__(message)
        self.status = status


def fields(text, names=None, allow_default=False):
    result = {}
    pattern = r'^(PKG_[A-Z_]+)[?:]=(.*)$' if allow_default else r'^(PKG_[A-Z_]+):=(.*)$'
    for key, value in re.findall(pattern, text, re.M):
        if names is not None and key not in names:
            continue
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
    """Bounded HTTPS requests, with thread-safe cached metadata and streamed archives."""
    DEFAULT_WORKERS = 6
    HOST_LIMITS = {'api.github.com': 2}
    DEFAULT_HOST_LIMIT = 4

    def __init__(self):
        self.cache = {}
        self.tag_cache = {}
        self._lock = threading.Lock()
        self._url_locks = {}
        self._tag_locks = {}
        self._host_semaphores = {}

    def _host_semaphore(self, host):
        with self._lock:
            sem = self._host_semaphores.get(host)
            if sem is None:
                sem = threading.BoundedSemaphore(self.HOST_LIMITS.get(host, self.DEFAULT_HOST_LIMIT))
                self._host_semaphores[host] = sem
            return sem

    def _key_lock(self, table, key):
        with self._lock:
            lock = table.get(key)
            if lock is None:
                lock = threading.Lock()
                table[key] = lock
            return lock

    def request(self, url, output=None):
        parsed = urlparse(url)
        if parsed.scheme != 'https':
            raise UpdateError('Expected an HTTPS upstream URL: ' + url)
        command = ['curl', '--fail', '--silent', '--show-error', '--location',
                   '--proto', '=https', '--proto-redir', '=https',
                   '--connect-timeout', '15', '--max-time', '300',
                   '--retry', '2', '--user-agent', 'openwrt-custom-package-updater']
        # Keep credentials off the command line, and restrict them to the API host.
        header_input = None
        if parsed.hostname == 'api.github.com':
            token = os.environ.get('GH_TOKEN') or os.environ.get('GITHUB_TOKEN')
            if token:
                if '\n' in token or '\r' in token:
                    raise UpdateError('Invalid GitHub token environment value')
                command += ['--header', '@-']
                header_input = ('Authorization: Bearer ' + token + '\n').encode()
        with self._host_semaphore(parsed.hostname or ''):
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
                    if (parsed.hostname == 'api.github.com' and status in (403, 429) and
                            response_headers.get('x-ratelimit-remaining') == '0'):
                        reset = response_headers.get('x-ratelimit-reset', '')
                        retry = datetime.fromtimestamp(int(reset), timezone.utc).isoformat() if reset.isdigit() else 'the quota resets'
                        reason = 'GitHub API rate limit exhausted; retry after ' + retry + ' or supply GH_TOKEN/GITHUB_TOKEN'
                    raise FetchError('Fetch failed for ' + url + ': ' + reason, status)
                return body.read_bytes() if output is None else b''

    def get(self, url):
        with self._lock:
            if url in self.cache:
                return self.cache[url]
        with self._key_lock(self._url_locks, url):
            with self._lock:
                if url in self.cache:
                    return self.cache[url]
            value = self.request(url)
            with self._lock:
                self.cache[url] = value
            return value

    def json(self, url):
        return json.loads(self.get(url))

    def download(self, url, output):
        self.request(url, output)

    def git_tags(self, project):
        if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', project):
            raise UpdateError('Invalid GitHub project name')
        with self._lock:
            if project in self.tag_cache:
                return self.tag_cache[project]
        with self._key_lock(self._tag_locks, project):
            with self._lock:
                if project in self.tag_cache:
                    return self.tag_cache[project]
            url = 'https://github.com/' + project + '.git'
            with self._host_semaphore('github.com'):
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
            with self._lock:
                self.tag_cache[project] = tags
            return tags


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


def catalog(entry, fetcher, current=None):
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
        if entry.get('version_dir_pattern'):
            parent = url
            dirs = {}
            for link in Links(fetcher.get(parent).decode(), parent).links:
                segment = unquote(urlparse(link).path.rstrip('/').rsplit('/', 1)[-1])
                if re.fullmatch(entry['version_dir_pattern'], segment):
                    target = link if link.endswith('/') else link + '/'
                    if entry.get('subdir'):
                        target = urljoin(target, entry['subdir'].lstrip('/'))
                        if not target.endswith('/'):
                            target += '/'
                    dirs[segment] = target
            if not dirs:
                raise UpdateError('No recognizable release directories from ' + parent)
            policy = entry.get('policy', 'series')
            ordered = sorted(dirs, key=version_key, reverse=True)
            if current is not None:
                allowed_dirs = [d for d in ordered if in_branch(d, current, policy)]
                newest = ordered[0]
                if not in_branch(newest, current, policy) and version_key(newest) > version_key(current):
                    review_ver = newest + '.0' if newest.count('.') == 1 else newest
                    versions.setdefault(review_ver, {'catalog': parent, 'review_only': True,
                                                     'review_series': newest})
            else:
                allowed_dirs = ordered
            scan_urls = [dirs[d] for d in allowed_dirs]
        else:
            scan_urls = [url]
        for scan_url in scan_urls:
            found_in_dir = False
            links = Links(fetcher.get(scan_url).decode(), scan_url).links
            by_name = {unquote(urlparse(link).path.rsplit('/', 1)[-1]): link for link in links}
            for name, link in by_name.items():
                match = re.fullmatch(entry['filename_pattern'], name)
                if match:
                    found_in_dir = True
                    source_version = match.groupdict().get('source_version')
                    version = package_version(match['version'].replace('_', '.') if source_version
                                              else match['version'])
                    if entry.get('stable_pattern') and not re.fullmatch(entry['stable_pattern'], version):
                        continue
                    meta = {'catalog': scan_url}
                    if source_version:
                        meta['source_version'] = source_version
                        previous = versions.get(version, {})
                        if previous.get('ambiguous_source') or (previous.get('source_version') and
                                previous['source_version'] != source_version):
                            meta['ambiguous_source'] = True
                    for suffix in ('.sha256sum', '.sha256'):
                        if name + suffix in by_name:
                            meta['checksums'] = by_name[name + suffix]
                            break
                    versions[version] = meta
            if entry.get('version_dir_pattern') and found_in_dir:
                break
        # GNOME publishes maintenance branches in separate directories.
        if entry.get('series_index'):
            parent = entry['series_index']
            policy = entry.get('policy', 'series')
            for link in Links(fetcher.get(parent).decode(), parent).links:
                series = urlparse(link).path.rstrip('/').rsplit('/', 1)[-1]
                if policy == 'major' and re.fullmatch(r'[0-9]+', series):
                    versions.setdefault(series + '.0', {'catalog': parent, 'review_only': True,
                                                        'review_series': series})
                elif re.fullmatch(r'[0-9]+\.[0-9]+', series) and int(series.split('.')[1]) % 2 == 0:
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
    elif provider == 'chrome':
        # Google's signed apt index publishes one SHA256 per channel build.
        channel = entry.get('channel', 'stable')
        if channel not in ('stable', 'beta', 'unstable'):
            raise UpdateError('Unsupported Chrome channel: ' + channel)
        url = 'https://dl.google.com/linux/chrome/deb/dists/stable/main/binary-amd64/Packages'
        for stanza in fetcher.get(url).decode().split('\n\n'):
            control = dict(re.findall(r'^([A-Za-z0-9-]+): *(.*)$', stanza, re.M))
            if control.get('Package') != 'google-chrome-' + channel:
                continue
            match = re.fullmatch(r'([0-9]+(?:\.[0-9]+){3})-1', control.get('Version', ''))
            filename = f'pool/main/g/google-chrome-{channel}/google-chrome-{channel}_{match[1]}-1_amd64.deb' if match else None
            if not match or control.get('Filename') != filename:
                raise UpdateError('Unexpected Chrome package entry: ' + control.get('Version', ''))
            versions[match[1]] = {'catalog': url, 'hash': valid_hash(control.get('SHA256', '').lower())}
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


def rewrite_recipe(text, version, digest, source_url=None, source_version=None):
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
    if source_version:
        changed['PKG_SOURCE_VERSION'] = source_version
    for key, value in changed.items():
        text, count = re.subn(r'^' + key + r':=.*$', lambda m: key + ':=' + value, text, flags=re.M)
        if count != 1:
            raise UpdateError('Missing/ambiguous metadata field: ' + key)
    return text


def variable_value(text, key):
    values = re.findall(r'^' + re.escape(key) + r':=(.*)$', text, re.M)
    if len(values) != 1:
        raise UpdateError('Missing/ambiguous metadata field: ' + key)
    return values[0].strip()


def rewrite_variable(text, key, value, op=':='):
    text, count = re.subn(r'^' + re.escape(key) + re.escape(op) + r'.*$',
                          lambda m: key + op + value, text, flags=re.M)
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
                         ('.bz2', b'BZh'), ('.otf', b'OTTO'), ('.zip', b'PK\x03\x04'),
                         ('.deb', b'!<arch>\n'), ('.zst', b'\x28\xb5\x2f\xfd'))
                      if filename.endswith(suffix)), None)
    if signature is None or not prefix.startswith(signature):
        raise UpdateError('Unexpected source format for ' + filename)


SUPPORTED_PROVIDERS = {
    'github': ({'project'}, {'catalog', 'tag_pattern', 'policy', 'checksums', 'checksum_filename',
                             'source_url', 'companion_assets', 'rebuild_dependents', 'linked_sources'}),
    'gitlab': ({'host', 'project'}, {'catalog', 'tag_pattern', 'policy', 'checksums', 'checksum_filename',
                                     'source_url', 'rebuild_dependents', 'linked_sources'}),
    'directory': ({'index', 'filename_pattern'}, {'series_index', 'version_dir_pattern', 'subdir',
                                                  'stable_pattern', 'policy', 'checksums',
                                                  'checksum_filename', 'source_url',
                                                  'rebuild_dependents', 'linked_sources'}),
    'pypi': ({'project'}, {'policy', 'rebuild_dependents', 'linked_sources'}),
    'node': (set(), {'policy', 'rebuild_dependents', 'linked_sources'}),
    'firefox': (set(), {'policy', 'rebuild_dependents', 'linked_sources'}),
    'chrome': (set(), {'channel', 'policy', 'rebuild_dependents', 'linked_sources'}),
    'sourceforge': ({'project'}, {'policy', 'rebuild_dependents', 'linked_sources'}),
    'follow': ({'recipe'}, {'same_source', 'feed_group', 'rebuild_dependents', 'linked_sources'}),
    'local': ({'reason'}, {'local_kind', 'upgrade_condition', 're_evaluate'}),
    'git-checkout': ({'url', 'branch'}, {'rebuild_dependents'}),
}


def validate_regex(pattern, label, errors, require_version=False):
    if not isinstance(pattern, str) or not pattern:
        errors.append(f'{label}: pattern must be a non-empty string')
        return
    try:
        compiled = re.compile(pattern)
    except re.error as error:
        errors.append(f'{label}: invalid regex ({error})')
        return
    if require_version and 'version' not in compiled.groupindex:
        errors.append(f'{label}: pattern must define named group (?P<version>...)')


class Updater:
    def __init__(self, root, entries, fetcher=None, update=False, record=None, feed_groups=None, workers=None):
        self.root = root.resolve()
        self.entries = entries
        self.feed_groups = feed_groups or {}
        self.fetcher = fetcher or Fetcher()
        self.update = update
        self.record = record
        self.workers = (Fetcher.DEFAULT_WORKERS if isinstance(self.fetcher, Fetcher) else 1) if workers is None else max(1, int(workers))
        self.followed_inputs = {}
        self._report_lock = threading.Lock()
        self.report = {'schema': 1, 'mode': 'update' if update else 'check',
                       'status': 'running', 'packages': {}}

    def recipe(self, name):
        return self.root / 'package/custom' / name / 'Makefile'

    def validate_registry(self):
        errors = []
        actual = {p.parent.name for p in (self.root / 'package/custom').glob('*/Makefile')}
        if actual != set(self.entries):
            errors.append('Custom registry mismatch; unregistered=' +
                          ','.join(sorted(actual - set(self.entries))) + '; missing=' +
                          ','.join(sorted(set(self.entries) - actual)))
        for group_name, group in sorted(self.feed_groups.items()):
            if not isinstance(group, dict):
                errors.append(f'feed_groups.{group_name}: must be an object')
                continue
            for req in ('provider', 'index', 'series_dir_pattern', 'version_dir_pattern',
                        'version_file', 'feed_repo', 'feed_manifest', 'feed_name', 'feed_modules'):
                if not group.get(req):
                    errors.append(f'feed_groups.{group_name}: missing required field {req}')
            if group.get('provider') not in (None, 'directory'):
                errors.append(f'feed_groups.{group_name}: unsupported provider {group.get("provider")}')
            if group.get('policy') and group['policy'] not in ('series', 'major', 'stable'):
                errors.append(f'feed_groups.{group_name}: invalid policy {group["policy"]}')
            if group.get('series_dir_pattern'):
                validate_regex(group['series_dir_pattern'], f'feed_groups.{group_name}.series_dir_pattern', errors)
            if group.get('version_dir_pattern'):
                validate_regex(group['version_dir_pattern'], f'feed_groups.{group_name}.version_dir_pattern', errors)
            for path_field in ('version_file', 'feed_repo', 'feed_manifest'):
                rel = group.get(path_field)
                if rel:
                    resolved = (self.root / rel).resolve()
                    if not resolved.is_relative_to(self.root):
                        errors.append(f'feed_groups.{group_name}.{path_field}: path outside workspace ({rel})')
                    elif not resolved.exists():
                        errors.append(f'feed_groups.{group_name}.{path_field}: missing path ({rel})')
            modules = group.get('feed_modules')
            if isinstance(modules, dict):
                for mod_name, mod in sorted(modules.items()):
                    if not isinstance(mod, dict) or not mod.get('recipe') or not mod.get('module'):
                        errors.append(f'feed_groups.{group_name}.feed_modules.{mod_name}: requires recipe and module')
                        continue
                    resolved = (self.root / mod['recipe']).resolve()
                    if not resolved.is_relative_to(self.root):
                        errors.append(f'feed_groups.{group_name}.feed_modules.{mod_name}: recipe outside workspace')
                    elif not resolved.exists():
                        errors.append(f'feed_groups.{group_name}.feed_modules.{mod_name}: missing recipe ({mod["recipe"]})')
            elif modules is not None:
                errors.append(f'feed_groups.{group_name}.feed_modules: must be an object')

        parents = {}
        for name, entry in sorted(self.entries.items()):
            if not isinstance(entry, dict):
                errors.append(f'{name}: registry entry must be an object')
                continue
            provider = entry.get('provider')
            if provider not in SUPPORTED_PROVIDERS:
                errors.append(f'{name}: unsupported provider {provider!r}')
                continue
            required, optional = SUPPORTED_PROVIDERS[provider]
            allowed = {'provider'} | required | optional
            missing = sorted(k for k in required if not entry.get(k))
            if missing:
                errors.append(f'{name}: missing required field(s) {", ".join(missing)} for provider {provider}')
            unknown = sorted(set(entry) - allowed)
            if unknown:
                errors.append(f'{name}: unsupported field(s) {", ".join(unknown)} for provider {provider}')
            if 'policy' in entry and entry['policy'] not in ('series', 'major', 'stable'):
                errors.append(f'{name}: invalid policy {entry["policy"]!r}')
            if provider == 'github':
                if entry.get('project') and not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+', entry['project']):
                    errors.append(f'{name}: invalid GitHub project {entry["project"]!r}')
                if 'catalog' in entry and entry['catalog'] not in ('tags', 'releases'):
                    errors.append(f'{name}: invalid GitHub catalog {entry["catalog"]!r}')
                if 'tag_pattern' in entry:
                    validate_regex(entry['tag_pattern'], f'{name}.tag_pattern', errors, require_version=True)
            elif provider == 'gitlab':
                if entry.get('host') and urlparse(entry['host']).scheme != 'https':
                    errors.append(f'{name}: GitLab host must be HTTPS')
                if 'catalog' in entry and entry['catalog'] not in ('tags', 'releases'):
                    errors.append(f'{name}: invalid GitLab catalog {entry["catalog"]!r}')
                if 'tag_pattern' in entry:
                    validate_regex(entry['tag_pattern'], f'{name}.tag_pattern', errors, require_version=True)
            elif provider == 'directory':
                if entry.get('index') and urlparse(entry['index']).scheme != 'https':
                    errors.append(f'{name}: directory index must be HTTPS')
                if entry.get('series_index') and urlparse(entry['series_index']).scheme != 'https':
                    errors.append(f'{name}: series_index must be HTTPS')
                if entry.get('filename_pattern'):
                    validate_regex(entry['filename_pattern'], f'{name}.filename_pattern', errors, require_version=True)
                if 'version_dir_pattern' in entry:
                    validate_regex(entry['version_dir_pattern'], f'{name}.version_dir_pattern', errors)
                if 'stable_pattern' in entry:
                    validate_regex(entry['stable_pattern'], f'{name}.stable_pattern', errors)
            elif provider == 'chrome':
                if 'channel' in entry and entry['channel'] not in ('stable', 'beta', 'unstable'):
                    errors.append(f'{name}: invalid Chrome channel {entry["channel"]!r}')
            elif provider == 'local':
                if 'local_kind' in entry and entry['local_kind'] not in (
                        'local-integration', 'derived-from-base', 'pinned-upstream'):
                    errors.append(f'{name}: invalid local_kind {entry["local_kind"]!r}')
            elif provider == 'git-checkout':
                if entry.get('url') and urlparse(entry['url']).scheme not in ('https', 'file'):
                    errors.append(f'{name}: invalid git-checkout url {entry["url"]!r}')
            elif provider == 'follow':
                rel = entry.get('recipe')
                if rel:
                    path = self.root / rel
                    if not path.resolve().is_relative_to(self.root):
                        errors.append(f'{name}: Followed recipe is outside the workspace ({rel})')
                    elif not path.exists():
                        errors.append(f'{name}: Followed recipe does not exist ({rel})')
                    elif path.parent.parent == self.root / 'package/custom':
                        parents.setdefault(name, []).append(path.parent.name)
                if 'feed_group' in entry and entry['feed_group'] not in self.feed_groups:
                    errors.append(f'{name}: unknown feed_group {entry["feed_group"]!r}')
            for idx, linked in enumerate(entry.get('linked_sources', [])):
                if not isinstance(linked, dict) or not all(linked.get(k) for k in ('recipe', 'version_var', 'hash_var')):
                    errors.append(f'{name}.linked_sources[{idx}]: requires recipe, version_var and hash_var')
                    continue
                path = self.root / linked['recipe']
                if not path.resolve().is_relative_to(self.root):
                    errors.append(f'{name}.linked_sources[{idx}]: recipe outside workspace ({linked["recipe"]})')
                elif not path.exists():
                    errors.append(f'{name}.linked_sources[{idx}]: missing recipe ({linked["recipe"]})')
                elif path.parent.parent == self.root / 'package/custom':
                    parents.setdefault(name, []).append(path.parent.name)

        # Detect cyclic follow / linked_sources relationships.
        state = {}
        def visit(node):
            if state.get(node) == 1:
                errors.append(f'Cyclic custom follow relationship involving {node}')
                return
            if state.get(node) == 2:
                return
            state[node] = 1
            for parent in parents.get(node, ()):
                visit(parent)
            state[node] = 2
        for node in sorted(parents):
            visit(node)

        if errors:
            raise UpdateError('Registry validation failed:\n' + '\n'.join('  - ' + e for e in errors))

    def groups(self, selected):
        actual = set(self.entries)
        feed_member_to_group = {}
        feed_group_custom = {g: [] for g in self.feed_groups}
        for group_name, group in self.feed_groups.items():
            feed_member_to_group[group_name] = group_name
            for mod_name in group.get('feed_modules', {}):
                feed_member_to_group[mod_name] = group_name
        for name, entry in self.entries.items():
            fg = entry.get('feed_group')
            if fg:
                feed_member_to_group[name] = fg
                feed_group_custom[fg].append(name)

        known = actual | set(feed_member_to_group)
        unknown = set(selected) - known
        if unknown:
            raise UpdateError('Unknown custom package: ' + ','.join(sorted(unknown)))

        parents = {}
        for name, entry in self.entries.items():
            if entry.get('feed_group'):
                continue
            if entry['provider'] == 'follow':
                path = self.root / entry['recipe']
                if path.parent.parent == self.root / 'package/custom':
                    parents[name] = path.parent.name
            elif entry.get('linked_sources'):
                for linked in entry['linked_sources']:
                    path = self.root / linked['recipe']
                    if path.parent.parent == self.root / 'package/custom':
                        parents[name] = path.parent.name
                        break

        def leader(name, seen=()):
            if name in seen:
                raise UpdateError('Cyclic custom follow relationship')
            return leader(parents[name], seen + (name,)) if name in parents else name

        wanted_feed_groups = set()
        wanted_custom = set()
        if selected:
            for item in selected:
                if item in feed_member_to_group:
                    wanted_feed_groups.add(feed_member_to_group[item])
                else:
                    wanted_custom.add(leader(item))
        else:
            wanted_feed_groups = set(self.feed_groups)
            wanted_custom = {leader(n) for n in actual if not self.entries[n].get('feed_group')}

        plan = []
        for group_name in sorted(wanted_feed_groups):
            plan.append(('feed_group', group_name, sorted(feed_group_custom[group_name])))

        custom_groups = {}
        for name in sorted(actual):
            if self.entries[name].get('feed_group'):
                continue
            root = leader(name)
            if root in wanted_custom:
                custom_groups.setdefault(root, []).append(name)
        for key, names in sorted(custom_groups.items()):
            plan.append(('custom', key, [key] + [n for n in names if n != key]))
        return plan

    def assert_clean(self, paths, repo_root=None):
        repo = (repo_root or self.root).resolve()
        rel_paths = [str(p.resolve().relative_to(repo)) for p in paths]
        result = subprocess.run(['git', '-C', str(repo), 'status', '--porcelain=v1', '-z',
                                 '--untracked-files=all', '--', *rel_paths],
                                capture_output=True)
        if result.returncode:
            raise UpdateError('Cannot inspect recipe Git state: ' + result.stderr.decode().strip())
        if result.stdout:
            raise UpdateError('Local recipe changes block updating: ' + ', '.join(rel_paths))
        # status can hide working-tree edits marked assume-unchanged/skip-worktree,
        # and ignored untracked recipes. Compare the actual bytes with HEAD too.
        for path, relative in zip(paths, rel_paths):
            committed = subprocess.run(['git', '-C', str(repo), 'show', 'HEAD:' + relative],
                                       capture_output=True)
            if committed.returncode or committed.stdout != path.read_bytes():
                raise UpdateError('Untracked or locally modified recipe: ' + relative)

    def sync_linked_sources(self, name, entry, text, planned, row, version_changed, followed_inputs=None):
        linked_list = entry.get('linked_sources', [])
        if not linked_list:
            return text, False
        inputs = self.followed_inputs if followed_inputs is None else followed_inputs
        changed = False
        updates = {}
        for linked in linked_list:
            path = self.root / linked['recipe']
            inputs[path] = path.read_text()
            source_text = planned.get(path, inputs[path])
            source_fields = fields(source_text, {'PKG_VERSION', 'PKG_HASH'}, allow_default=True)
            new_ver = source_fields['PKG_VERSION']
            new_hash = valid_hash(source_fields['PKG_HASH'])
            cur_ver = variable_value(text, linked['version_var'])
            cur_hash = variable_value(text, linked['hash_var'])
            if cur_ver != new_ver or cur_hash != new_hash:
                text = rewrite_variable(text, linked['version_var'], new_ver)
                text = rewrite_variable(text, linked['hash_var'], new_hash)
                updates[linked['version_var']] = {'old': cur_ver, 'new': new_ver, 'sha256': new_hash}
                changed = True
        if changed:
            if not version_changed:
                cur_rel = fields(text)['PKG_RELEASE']
                text = rewrite_variable(text, 'PKG_RELEASE', str(int(cur_rel) + 1))
            row['linked_updates'] = updates
        return text, changed

    def discover(self, name, planned, followed_inputs=None):
        entry = self.entries[name]
        inputs = self.followed_inputs if followed_inputs is None else followed_inputs
        text = self.recipe(name).read_text()
        metadata = fields(text, {'PKG_VERSION', 'PKG_RELEASE'} if entry['provider'] == 'git-checkout' else None)
        row = {'old_version': metadata.get('PKG_VERSION'), 'provider': entry['provider']}
        if entry.get('rebuild_dependents'):
            row['rebuild_dependents'] = list(entry['rebuild_dependents'])
        with self._report_lock:
            self.report['packages'][name] = row
        if entry['provider'] == 'git-checkout':
            self.update_checkout(name, entry, row)
            return None
        if entry['provider'] == 'local':
            row.update(status='local', reason=entry['reason'])
            if entry.get('local_kind'):
                row['local_kind'] = entry['local_kind']
            if entry.get('upgrade_condition'):
                row['upgrade_condition'] = entry['upgrade_condition']
            return None
        current = metadata['PKG_VERSION']
        version_key(current)
        valid_hash(metadata['PKG_HASH'])
        if not metadata.get('PKG_RELEASE', '').isdecimal():
            raise UpdateError('Expected a literal PKG_RELEASE in ' + name)
        if entry['provider'] == 'follow':
            path = self.root / entry['recipe']
            inputs[path] = path.read_text()
            followed_text = planned.get(path, inputs[path])
            followed_names = {'PKG_VERSION', 'PKG_HASH'} if entry.get('same_source') else {'PKG_VERSION'}
            followed = fields(followed_text, followed_names, allow_default=True)
            version = followed['PKG_VERSION']
            if version_key(version) < version_key(current):
                raise UpdateError('Refusing followed-source downgrade for ' + name)
            meta = {'catalog': entry['recipe']}
            if entry.get('same_source'):
                meta['hash'] = valid_hash(followed['PKG_HASH'])
        else:
            versions = catalog(entry, self.fetcher, current=current)
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
        if meta.get('source_version'):
            if meta.get('ambiguous_source'):
                raise UpdateError('Ambiguous source snapshots for version ' + version)
            row['source_version'] = meta['source_version']
            if version == current and meta['source_version'] != metadata.get('PKG_SOURCE_VERSION'):
                raise UpdateError('Same-version source snapshot changed; review ' + name + ' manually')
        proposed = rewrite_recipe(text, version, metadata['PKG_HASH'], entry.get('source_url'),
                                  meta.get('source_version'))
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
            checksum_name = entry.get('checksum_filename', meta.get('checksum_filename', filename)).format(version=version)
            digest = checksum_for(self.fetcher.get(sums), checksum_name)
        if digest:
            valid_hash(digest)
        if version == current:
            if digest and digest != metadata['PKG_HASH']:
                raise UpdateError('Same-version source digest changed; review ' + name + ' manually')
            if fields(proposed).get('PKG_SOURCE_URL') == metadata.get('PKG_SOURCE_URL'):
                linked_text, linked_changed = self.sync_linked_sources(name, entry, text, planned, row, False, inputs)
                if not linked_changed:
                    row['status'] = 'review' if row.get('review_version') else 'current'
                    return None
                row['status'] = 'available'
                if self.update:
                    self.assert_clean([self.recipe(name)])
                return linked_text
            row['source_relocation'] = True
            digest = metadata['PKG_HASH']
        row['status'] = 'available'
        proposed = self.companion_assets(name, entry, meta, proposed, row)
        proposed, _ = self.sync_linked_sources(name, entry, proposed, planned, row, True, inputs)
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
        updated = rewrite_recipe(text, version, digest, entry.get('source_url'), meta.get('source_version'))
        for variable in entry.get('companion_assets', {}):
            updated = rewrite_variable(updated, variable, variable_value(proposed, variable))
        updated, _ = self.sync_linked_sources(name, entry, updated, planned, row, True, inputs)
        return updated

    def companion_assets(self, name, entry, meta, text, row):
        """Refresh hashes of extra release assets (for example a prebuilt web UI).

        Each entry maps a recipe variable holding a SHA256 to the asset name in the
        same GitHub release. The asset must publish a SHA256 digest; in update mode
        the asset is also downloaded and checked against it."""
        assets = entry.get('companion_assets', {})
        if not assets:
            return text
        release = meta.get('release')
        if not release:
            raise UpdateError('Companion assets need GitHub release metadata for ' + name)
        published = {asset['name']: asset for asset in release.get('assets', [])}
        rows = row.setdefault('companion_assets', {})
        for variable, filename in assets.items():
            variable_value(text, variable)
            asset = published.get(filename)
            if not asset or not str(asset.get('digest', '')).startswith('sha256:'):
                raise UpdateError('Companion asset without SHA256 digest for ' + name + ': ' + filename)
            digest = valid_hash(asset['digest'].split(':', 1)[1])
            if self.update:
                url = asset.get('browser_download_url', '')
                if not url.startswith('https://'):
                    raise UpdateError('Companion asset without HTTPS URL for ' + name + ': ' + filename)
                with tempfile.TemporaryDirectory(prefix='openwrt-custom-asset-') as temporary:
                    downloaded = Path(temporary) / filename
                    self.fetcher.download(url, downloaded)
                    validate_payload(downloaded, filename)
                    if file_hash(downloaded) != digest:
                        raise UpdateError('Companion asset SHA256 mismatch for ' + name + ': ' + filename)
            rows[variable] = {'asset': filename, 'sha256': digest}
            text = rewrite_variable(text, variable, digest)
        return text

    def update_checkout(self, name, entry, row):
        """Merge an upstream branch into a separately maintained source checkout."""
        path = self.recipe(name).parent
        if not (path / '.git').exists():
            raise UpdateError('Initialize the nested Git checkout first: ' + str(path))

        def git(*args, check=True):
            result = subprocess.run(['git', '-C', str(path), '-c', 'merge.autoStash=false',
                                     *args], capture_output=True, text=True, timeout=120,
                                    env=dict(os.environ, GIT_TERMINAL_PROMPT='0'))
            if check and result.returncode:
                raise UpdateError('Git checkout ' + name + ': ' + result.stderr.strip())
            return result

        if Path(git('rev-parse', '--show-toplevel').stdout.strip()).resolve() != path.resolve():
            raise UpdateError('Expected an independent Git repository: ' + name)
        url, branch = entry['url'], entry['branch']
        if urlparse(url).scheme not in ('https', 'file') or not re.fullmatch(r'[A-Za-z0-9_./-]+', branch):
            raise UpdateError('Invalid checkout upstream: ' + name)
        head = git('rev-parse', 'HEAD').stdout.strip()
        remote = git('ls-remote', '--exit-code', url, 'refs/heads/' + branch).stdout.split()
        if len(remote) != 2 or not re.fullmatch(r'[0-9a-f]{40,64}', remote[0]):
            raise UpdateError('Ambiguous checkout branch: ' + name)
        target = remote[0]
        row.update(old_revision=head, new_revision=target, catalog=url, branch=branch)
        if git('merge-base', '--is-ancestor', target, head, check=False).returncode == 0:
            row.update(status='current', new_version=row['old_version'])
            return
        row['status'] = 'available'
        if not self.update:
            return
        if git('symbolic-ref', '-q', 'HEAD', check=False).returncode:
            raise UpdateError('Detached checkout blocks updating: ' + name)
        # Preserve untracked directories; Git itself rejects any overwritten paths.
        if git('status', '--porcelain=v1', '--untracked-files=no').stdout:
            raise UpdateError('Local checkout changes block updating: ' + name)
        if any(line[:1].islower() or line.startswith('S ') for line in git('ls-files', '-v').stdout.splitlines()):
            raise UpdateError('Hidden checkout changes may block updating: ' + name)
        gitdir = Path(git('rev-parse', '--absolute-git-dir').stdout.strip())
        for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'rebase-merge', 'rebase-apply', 'index.lock'):
            if (gitdir / marker).exists():
                raise UpdateError('Finish the pending checkout Git operation: ' + marker)
        git('fetch', '--no-tags', url, 'refs/heads/' + branch)
        if git('rev-parse', 'FETCH_HEAD').stdout.strip() != target:
            raise UpdateError('Upstream moved during checkout update; retry: ' + name)
        # Detect conflicts before touching the working tree or index.
        preview = git('merge-tree', '--write-tree', head, target, check=False)
        if preview.returncode:
            raise UpdateError('Upstream merge requires manual conflict resolution: ' + name)
        if git('rev-parse', 'HEAD').stdout.strip() != head:
            raise UpdateError('Checkout changed while checking upstream: ' + name)
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        backup = 'refs/custom-package-updates/' + stamp
        git('update-ref', backup, head)
        old = fields(self.recipe(name).read_text(), {'PKG_VERSION', 'PKG_RELEASE'})
        if self.record:
            saved = self.record / 'before' / self.recipe(name).relative_to(self.root)
            saved.parent.mkdir(parents=True, exist_ok=True)
            saved.write_text(self.recipe(name).read_text())
        git('merge', '--no-edit', '--no-stat', target)
        text = self.recipe(name).read_text()
        metadata = fields(text, {'PKG_VERSION', 'PKG_RELEASE'})
        # Branch updates can change payloads without changing the upstream version.
        # Leave the release bump for the maintainer to commit, like recipe updates.
        if metadata['PKG_VERSION'] == old['PKG_VERSION'] and int(metadata['PKG_RELEASE']) <= int(old['PKG_RELEASE']):
            release = str(max(int(datetime.now(timezone.utc).strftime('%Y%m%d')), int(old['PKG_RELEASE']) + 1))
            text = re.sub(r'^PKG_RELEASE:=.*$', 'PKG_RELEASE:=' + release, text, flags=re.M)
            self.recipe(name).write_text(text)
        row.update(status='updated', new_version=metadata['PKG_VERSION'], backup_ref=backup,
                   merged_revision=git('rev-parse', 'HEAD').stdout.strip())

    def render_feed_patch(self, feed_repo, base_rev, patch_path, manifest_paths, proposed_files):
        """Render the updated feed patch mirror without mutating the feed repo's Git state."""
        feed_git = Path(subprocess.check_output(
            ['git', '-C', str(feed_repo), 'rev-parse', '--absolute-git-dir'], text=True).strip())
        with tempfile.TemporaryDirectory(prefix='openwrt-feed-patch-') as tmpdir:
            tmp = Path(tmpdir)
            (tmp / 'objects').mkdir()
            env = dict(os.environ,
                       GIT_INDEX_FILE=str(tmp / 'index'),
                       GIT_OBJECT_DIRECTORY=str(tmp / 'objects'),
                       GIT_ALTERNATE_OBJECT_DIRECTORIES=str(feed_git / 'objects'))
            subprocess.run(['git', '-C', str(feed_repo), 'read-tree', 'HEAD'],
                           env=env, check=True, capture_output=True)
            for abs_path, new_text in proposed_files.items():
                rel = str(abs_path.resolve().relative_to(feed_repo.resolve()))
                hashed = subprocess.run(
                    ['git', '-C', str(feed_repo), 'hash-object', '-w', '--stdin'],
                    input=new_text.encode(), env=env, check=True, capture_output=True)
                blob = hashed.stdout.decode().strip()
                mode = '100755' if (abs_path.stat().st_mode & 0o111) else '100644'
                subprocess.run(
                    ['git', '-C', str(feed_repo), 'update-index', '--cacheinfo', f'{mode},{blob},{rel}'],
                    env=env, check=True, capture_output=True)
            diff_args = ['git', '-C', str(feed_repo), 'diff', '--cached']
            if not manifest_paths:
                diff_args.append('--binary')
            diff_args += ['--stat', '--patch', base_rev]
            if manifest_paths:
                diff_args += ['--', *manifest_paths]
            diff = subprocess.run(diff_args, env=env, check=True, capture_output=True).stdout.decode()
            new_tree = subprocess.run(
                ['git', '-C', str(feed_repo), 'write-tree'],
                env=env, check=True, capture_output=True).stdout.decode().strip()
        existing = patch_path.read_text() if patch_path.exists() else ''
        if '\n---\n' in existing:
            header = existing.split('\n---\n', 1)[0] + '\n---\n'
            return header + diff, new_tree
        return diff, new_tree

    def execute_feed_group(self, group_name, custom_members):
        group = self.feed_groups[group_name]
        policy = group.get('policy', 'series')
        version_file = (self.root / group['version_file']).resolve()
        feed_repo = (self.root / group['feed_repo']).resolve()
        manifest_path = (self.root / group['feed_manifest']).resolve()
        manifest = json.loads(manifest_path.read_text())
        feed_spec = manifest.get(group['feed_name'])
        if not isinstance(feed_spec, dict) or not feed_spec.get('base') or not feed_spec.get('patch'):
            raise UpdateError(f'Invalid feed manifest {group["feed_manifest"]} for {group["feed_name"]}')
        patch_path = (self.root / feed_spec['patch']).resolve()
        if not patch_path.is_relative_to(self.root):
            raise UpdateError('Feed patch mirror path is outside the workspace: ' + feed_spec['patch'])

        common_text = version_file.read_text()
        current = fields(common_text, {'PKG_VERSION'}, allow_default=True)['PKG_VERSION']
        version_key(current)

        # 1. Discover series and maintenance versions from upstream index.
        parent = group['index']
        series_dirs = {}
        for link in Links(self.fetcher.get(parent).decode(), parent).links:
            segment = unquote(urlparse(link).path.rstrip('/').rsplit('/', 1)[-1])
            if re.fullmatch(group['series_dir_pattern'], segment):
                series_dirs[segment] = link if link.endswith('/') else link + '/'
        if not series_dirs:
            raise UpdateError('No recognizable release series from ' + parent)

        ordered_series = sorted(series_dirs, key=version_key, reverse=True)
        review_series = None
        for s in ordered_series:
            if not in_branch(s, current, policy) and version_key(s) > version_key(current):
                review_series = s
                break
        in_branch_series = [s for s in ordered_series if in_branch(s, current, policy)]
        if not in_branch_series:
            for mod_name in (*sorted(group['feed_modules']), *custom_members):
                row = {'old_version': current, 'new_version': current, 'provider': 'feed-group',
                       'group': group_name, 'status': 'review',
                       'reason': 'Current maintenance branch is not advertised upstream'}
                if review_series:
                    row['review_version'] = review_series
                if group.get('rebuild_dependents'):
                    row['rebuild_dependents'] = list(group['rebuild_dependents'])
                self.report['packages'][mod_name] = row
            return

        series_url = series_dirs[in_branch_series[0]]
        ver_dirs = {}
        for link in Links(self.fetcher.get(series_url).decode(), series_url).links:
            segment = unquote(urlparse(link).path.rstrip('/').rsplit('/', 1)[-1])
            if re.fullmatch(group['version_dir_pattern'], segment) and in_branch(segment, current, policy):
                target = link if link.endswith('/') else link + '/'
                if group.get('subdir'):
                    target = urljoin(target, group['subdir'].lstrip('/'))
                    if not target.endswith('/'):
                        target += '/'
                ver_dirs[segment] = target
        if not ver_dirs:
            raise UpdateError('No recognizable maintenance releases from ' + series_url)

        target_ver = max(ver_dirs, key=version_key)
        submodules_url = ver_dirs[target_ver]
        sub_links = Links(self.fetcher.get(submodules_url).decode(), submodules_url).links
        by_name = {unquote(urlparse(link).path.rsplit('/', 1)[-1]): link for link in sub_links}

        # 2. Verify all 12 modules (feed + custom) exist for the target version.
        feed_modules = group['feed_modules']
        module_specs = []
        needs_update = target_ver != current
        for mod_name in sorted(feed_modules):
            mod = feed_modules[mod_name]
            mod_path = (self.root / mod['recipe']).resolve()
            mod_text = mod_path.read_text()
            mod_meta = fields(mod_text, {'PKG_RELEASE', 'PKG_HASH'})
            valid_hash(mod_meta['PKG_HASH'])
            filename = f'{mod["module"]}-everywhere-src-{target_ver}.tar.xz'
            if filename not in by_name:
                raise UpdateError(f'Missing {group_name} module archive in {submodules_url}: {mod_name} ({filename})')
            checksum_url = next((by_name[filename + s] for s in ('.sha256sum', '.sha256') if filename + s in by_name), None)
            module_specs.append(('feed', mod_name, mod_path, mod_text, current, filename, by_name[filename], checksum_url))

        for name in custom_members:
            mod_path = self.recipe(name)
            mod_text = mod_path.read_text()
            mod_meta = fields(mod_text)
            old_ver = mod_meta['PKG_VERSION']
            valid_hash(mod_meta['PKG_HASH'])
            if old_ver != target_ver:
                needs_update = True
            proposed = rewrite_recipe(mod_text, target_ver, mod_meta['PKG_HASH'])
            filename, url = source_location(proposed)
            if filename not in by_name:
                raise UpdateError(f'Missing {group_name} module archive in {submodules_url}: {name} ({filename})')
            checksum_url = next((by_name[filename + s] for s in ('.sha256sum', '.sha256') if filename + s in by_name), None)
            module_specs.append(('custom', name, mod_path, mod_text, old_ver, filename, url, checksum_url))

        for kind, mod_name, _, _, old_ver, _, url, _ in module_specs:
            row = {
                'old_version': old_ver,
                'new_version': target_ver,
                'provider': 'feed-group' if kind == 'feed' else 'follow',
                'group': group_name,
                'source': url,
                'catalog': submodules_url,
            }
            if review_series:
                row['review_version'] = review_series
            if group.get('rebuild_dependents'):
                row['rebuild_dependents'] = list(group['rebuild_dependents'])
            if version_key(target_ver) < version_key(old_ver):
                row.update(status='ahead', new_version=old_ver,
                           reason='Local version is newer than the advertised maintenance releases')
            elif not needs_update:
                row['status'] = 'review' if review_series else 'current'
            else:
                row['status'] = 'available'
            self.report['packages'][mod_name] = row

        if not needs_update or version_key(target_ver) < version_key(current) or not self.update:
            return

        # 3. Check both repos' cleanliness and video feed base commit BEFORE downloading.
        update_snapshot_manifest = not feed_spec.get('paths') and ('tree' in feed_spec or 'commit' in feed_spec)
        main_paths = [self.recipe(n) for n in custom_members]
        if patch_path.exists():
            main_paths.append(patch_path)
        if update_snapshot_manifest and manifest_path.exists():
            main_paths.append(manifest_path)
        feed_paths = [version_file] + [(self.root / feed_modules[m]['recipe']).resolve() for m in sorted(feed_modules)]
        self.assert_clean(main_paths, repo_root=self.root)
        self.assert_clean(feed_paths, repo_root=feed_repo)
        ancestor = subprocess.run(
            ['git', '-C', str(feed_repo), 'merge-base', '--is-ancestor', feed_spec['base'], 'HEAD'],
            capture_output=True)
        if ancestor.returncode != 0:
            raise UpdateError(f'Feed repository {group["feed_repo"]} HEAD does not descend from manifest base {feed_spec["base"]}')

        # 4. Download & verify all 12 tarballs before writing any file.
        originals = {version_file: common_text}
        changes = {}
        feed_proposed = {}
        if target_ver != current:
            new_common = rewrite_variable(common_text, 'PKG_VERSION', target_ver, op='?=')
            changes[version_file] = new_common
            feed_proposed[version_file] = new_common

        for kind, mod_name, mod_path, mod_text, old_ver, filename, url, checksum_url in module_specs:
            originals[mod_path] = mod_text
            expected_digest = checksum_for(self.fetcher.get(checksum_url), filename) if checksum_url else None
            with tempfile.TemporaryDirectory(prefix='openwrt-qt6-source-') as temporary:
                downloaded = Path(temporary) / filename
                self.fetcher.download(url, downloaded)
                validate_payload(downloaded, filename)
                actual = file_hash(downloaded)
            if expected_digest and actual != expected_digest:
                raise UpdateError(f'Upstream SHA256 mismatch for {group_name} module {mod_name}')
            self.report['packages'][mod_name].update(
                sha256=actual,
                verification='upstream-sha256' if expected_digest else 'downloaded-https-source')
            if kind == 'feed':
                updated = rewrite_variable(mod_text, 'PKG_HASH', actual)
                if target_ver != old_ver:
                    updated = rewrite_variable(updated, 'PKG_RELEASE', '1')
                changes[mod_path] = updated
                feed_proposed[mod_path] = updated
            else:
                changes[mod_path] = rewrite_recipe(mod_text, target_ver, actual)

        # 5. Regenerate the video feed patch mirror and apply all files atomically.
        originals[patch_path] = patch_path.read_text() if patch_path.exists() else ''
        patch_text, new_tree = self.render_feed_patch(
            feed_repo, feed_spec['base'], patch_path, feed_spec.get('paths', []), feed_proposed)
        changes[patch_path] = patch_text
        if update_snapshot_manifest:
            updated_spec = dict(feed_spec, tree=new_tree)
            updated_spec.pop('commit', None)
            updated_manifest = dict(manifest)
            updated_manifest[group['feed_name']] = updated_spec
            originals[manifest_path] = manifest_path.read_text()
            changes[manifest_path] = json.dumps(updated_manifest, indent=2) + '\n'
            if manifest_path not in main_paths:
                main_paths.append(manifest_path)
        repo_paths = {
            self.root: [p for p in changes if p in main_paths],
            feed_repo: [p for p in changes if p in feed_paths],
        }
        self.apply(changes, originals, repo_paths=repo_paths)
        for _, mod_name, _, _, _, _, _, _ in module_specs:
            self.report['packages'][mod_name]['status'] = 'updated'

    def apply(self, changes, originals, repo_paths=None):
        if repo_paths is None:
            self.assert_clean(list(changes))
        else:
            for repo_root, paths in repo_paths.items():
                if paths:
                    self.assert_clean(paths, repo_root=repo_root)
        for path, original in self.followed_inputs.items():
            if path.read_text() != original:
                raise UpdateError('Followed recipe changed while checking upstream: ' + str(path))
        staged = {}
        replaced = []
        try:
            for path, text in changes.items():
                if path.exists() and path.read_text() != originals[path]:
                    raise UpdateError('Recipe changed while checking upstream: ' + str(path))
                if self.record:
                    backup = self.record / 'before' / path.resolve().relative_to(self.root)
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    backup.write_text(originals[path])
                fd, temporary = tempfile.mkstemp(prefix='Makefile.update.', dir=path.parent)
                staged[path] = Path(temporary)
                with os.fdopen(fd, 'w') as stream:
                    stream.write(text)
                    stream.flush()
                    os.fsync(stream.fileno())
                if path.exists():
                    staged[path].chmod(path.stat().st_mode & 0o777)
            for path, temporary in staged.items():
                if path.exists() and path.read_text() != originals[path]:
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

    def format_status_line(self, name, row, group_label=None):
        parts = [f'{name}: {row["status"]}']
        if 'new_version' in row:
            parts.append(f'{row["old_version"]} -> {row["new_version"]}')
        if group_label:
            parts.append(f'[group {group_label}]')
        if row.get('review_version'):
            parts.append(f'(review branch {row["review_version"]})')
        if row.get('rebuild_dependents') and (row['status'] in ('available', 'review', 'updated') or row.get('review_version')):
            parts.append(f'(rebuild: {", ".join(row["rebuild_dependents"])})')
        if row['status'] == 'failed' and row.get('error'):
            parts.append(f'({row["error"]})')
        return ' '.join(parts)

    def _prefetch_catalogs(self, plan):
        """Warm read-only upstream catalogs concurrently before sequential --update."""
        targets = []
        for kind, _, members in plan:
            if kind != 'custom':
                continue
            for name in members:
                entry = self.entries[name]
                if entry['provider'] in ('local', 'follow', 'git-checkout'):
                    continue
                targets.append((name, entry))
        if len(targets) <= 1 or self.workers <= 1:
            return

        def warm(item):
            name, entry = item
            try:
                current = fields(self.recipe(name).read_text()).get('PKG_VERSION')
                if current:
                    catalog(entry, self.fetcher, current=current)
            except Exception:
                # Let the deterministic main loop surface any upstream error.
                pass

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            list(pool.map(warm, targets))

    def _run_custom_group_check(self, group_key, members):
        followed_inputs = {}
        changes = {}
        group_label = group_key if len(members) > 1 else None
        group_failures = []
        for name in members:
            try:
                updated = self.discover(name, changes, followed_inputs)
                with self._report_lock:
                    if group_label:
                        self.report['packages'][name]['group'] = group_label
                if updated is not None:
                    changes[self.recipe(name)] = updated
            except Exception as error:
                with self._report_lock:
                    self.report['packages'].setdefault(name, {}).update(status='failed', error=str(error))
                    if group_label:
                        self.report['packages'][name]['group'] = group_label
                    for remaining in members[members.index(name) + 1:]:
                        self.report['packages'].setdefault(remaining, {}).update(
                            status='failed', error=f'Blocked by group member {name}: {error}')
                        if group_label:
                            self.report['packages'][remaining]['group'] = group_label
                group_failures.append((name, str(error)))
                break
        return group_label, group_failures

    def execute(self, selected=()):
        self.validate_registry()
        failures = []
        plan = self.groups(selected)
        try:
            if not self.update and self.workers > 1 and sum(1 for k, _, _ in plan if k == 'custom') > 1:
                with ThreadPoolExecutor(max_workers=self.workers) as pool:
                    futures = {
                        idx: pool.submit(self._run_custom_group_check, group_key, members)
                        for idx, (kind, group_key, members) in enumerate(plan)
                        if kind == 'custom'
                    }
                    for idx, (kind, group_key, members) in enumerate(plan):
                        if kind == 'feed_group':
                            all_members = [*sorted(self.feed_groups[group_key]['feed_modules']), *members]
                            try:
                                self.execute_feed_group(group_key, members)
                            except Exception as error:
                                for mod_name in all_members:
                                    self.report['packages'].setdefault(mod_name, {'group': group_key}).update(
                                        status='failed', error=str(error))
                                failures.append((group_key, str(error)))
                            for mod_name in all_members:
                                row = self.report['packages'][mod_name]
                                print(self.format_status_line(mod_name, row, group_key), flush=True)
                            continue
                        group_label, group_failures = futures[idx].result()
                        failures.extend(group_failures)
                        for name in members:
                            row = self.report['packages'][name]
                            print(self.format_status_line(name, row, group_label), flush=True)
            else:
                if self.update and self.workers > 1:
                    self._prefetch_catalogs(plan)
                for kind, group_key, members in plan:
                    if kind == 'feed_group':
                        all_members = [*sorted(self.feed_groups[group_key]['feed_modules']), *members]
                        try:
                            self.execute_feed_group(group_key, members)
                        except Exception as error:
                            for mod_name in all_members:
                                self.report['packages'].setdefault(mod_name, {'group': group_key}).update(
                                    status='failed', error=str(error))
                            if self.update:
                                raise
                            failures.append((group_key, str(error)))
                        for mod_name in all_members:
                            row = self.report['packages'][mod_name]
                            print(self.format_status_line(mod_name, row, group_key), flush=True)
                        continue

                    self.followed_inputs = {}
                    originals = {self.recipe(n): self.recipe(n).read_text() for n in members}
                    changes = {}
                    group_label = group_key if len(members) > 1 else None
                    group_failed = False
                    for name in members:
                        try:
                            updated = self.discover(name, changes, self.followed_inputs)
                            if group_label:
                                self.report['packages'][name]['group'] = group_label
                            if updated is not None:
                                changes[self.recipe(name)] = updated
                        except Exception as error:
                            self.report['packages'].setdefault(name, {}).update(status='failed', error=str(error))
                            if group_label:
                                self.report['packages'][name]['group'] = group_label
                            if self.update:
                                raise
                            failures.append((name, str(error)))
                            group_failed = True
                            for remaining in members[members.index(name) + 1:]:
                                self.report['packages'].setdefault(remaining, {}).update(
                                    status='failed', error=f'Blocked by group member {name}: {error}')
                                if group_label:
                                    self.report['packages'][remaining]['group'] = group_label
                            break
                    if self.update and changes and not group_failed:
                        self.apply(changes, originals)
                        for path in changes:
                            self.report['packages'][path.parent.name]['status'] = 'updated'
                    for name in members:
                        row = self.report['packages'][name]
                        print(self.format_status_line(name, row, group_label), flush=True)
            if failures:
                self.report.update(status='failed', failures=[{'target': t, 'error': e} for t, e in failures])
                print(f'Custom check finished with {len(failures)} failure(s):', file=sys.stderr)
                for target, err in failures:
                    print(f'  - {target}: {err}', file=sys.stderr)
                return 2
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
    parser.add_argument('--jobs', type=int, default=None, help='Bounded concurrent upstream checks (default: 6)')
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    root = args.root.resolve()
    updater = None
    try:
        registry = json.loads((root / 'configs/custom-package-updates.json').read_text())
        if registry['schema'] != 1:
            raise UpdateError('Unsupported custom registry schema')
        feed_groups = registry.get('feed_groups', {})
        if not args.update:
            return Updater(root, registry['packages'], feed_groups=feed_groups, workers=args.jobs).execute(args.package)
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
            updater = Updater(root, registry['packages'], update=True, record=record,
                              feed_groups=feed_groups, workers=args.jobs)
            try:
                return updater.execute(args.package)
            finally:
                (record / 'report.json').write_text(json.dumps(updater.report, indent=2) + '\n')
                print('Custom update report: ' + str(record / 'report.json'), flush=True)
    except (UpdateError, OSError, ValueError, KeyError, subprocess.SubprocessError, ET.ParseError) as error:
        print('Custom update failed: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    sys.exit(main())
