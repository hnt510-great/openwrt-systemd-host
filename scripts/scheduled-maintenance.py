#!/usr/bin/env python3
"""Every-72-hour source integration, image build, isolated VM gate and feed publication."""
import argparse
from datetime import datetime, timedelta, timezone
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import signal
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from zoneinfo import ZoneInfo

SOURCE = Path(__file__).resolve().parents[1]
INTERVAL = 3 * 24 * 60 * 60
REF = 'refs/automation/scheduled-input'


def initial_run_time(now, config):
    local = datetime.fromtimestamp(now, ZoneInfo(config.get('timezone', 'Asia/Singapore')))
    start = local.replace(hour=config.get('start_hour', 4), minute=0, second=0, microsecond=0)
    if start <= local:
        start += timedelta(days=1)
    return int(start.timestamp()) + INTERVAL


def load(name, filename):
    spec = importlib.util.spec_from_file_location(name, SOURCE / 'scripts' / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile('w', dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write('\n')
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(temporary, path)


def command(argv, cwd=None, **kwargs):
    return subprocess.run([str(a) for a in argv], cwd=cwd, check=True, **kwargs)


def git(repo, *args, **kwargs):
    kwargs.setdefault('timeout', 300)
    return subprocess.check_output(['git', '-C', str(repo), *args], **kwargs).decode().strip()


def source_snapshot(source, record):
    """Use a temporary index; preserve the user's index, worktree, stashes and branch."""
    record.mkdir(parents=True, exist_ok=True)
    head = git(source, 'rev-parse', 'HEAD')
    status = git(source, 'status', '--porcelain=v1', '--untracked-files=all')
    (record / 'status.txt').write_text(status + '\n')
    (record / 'working.patch').write_bytes(subprocess.check_output(
        ['git', '-C', str(source), 'diff', '--binary', 'HEAD']))
    (record / 'index.patch').write_bytes(subprocess.check_output(
        ['git', '-C', str(source), 'diff', '--cached', '--binary']))
    (record / 'stashes.txt').write_text(git(source, 'stash', 'list') + '\n')
    index = Path(git(source, 'rev-parse', '--path-format=absolute', '--git-path', 'index'))
    if index.exists():
        shutil.copy2(index, record / 'original-index')
    env = dict(os.environ, GIT_INDEX_FILE=str(record / 'snapshot-index'))
    git(source, 'read-tree', 'HEAD', env=env)
    git(source, 'add', '-u', env=env)
    untracked = subprocess.check_output(['git', '-C', str(source), 'ls-files', '--others',
                                        '--exclude-standard', '-z']).decode().split('\0')
    skipped, included = [], []
    for name in filter(None, untracked):
        path = Path(name)
        if ('__pycache__' in path.parts or path.name.startswith('._') or
                path.suffix == '.pyc' or re.match(r'^backup-.*\.(tar|tar\.gz|tgz)$', path.name)):
            skipped.append(name)
            continue
        item = source / name
        if not item.is_symlink() and item.stat().st_size > 16 * 1024 * 1024:
            raise ValueError('Large untracked source requires explicit handling: ' + str(item))
        git(source, 'add', '--', name, env=env)
        included.append(name)
    tree = git(source, 'write-tree', env=env)
    previous = subprocess.run(['git', '-C', str(source), 'rev-parse', '--verify', REF],
                              capture_output=True, text=True)
    parent = previous.stdout.strip() if previous.returncode == 0 else None
    ancestor = parent and subprocess.run(['git', '-C', str(source), 'merge-base',
                                         '--is-ancestor', head, parent]).returncode == 0
    if ancestor and git(source, 'rev-parse', parent + '^{tree}') == tree:
        commit = parent
    else:
        parents = ['-p', parent] if parent else []
        if head != parent:
            parents += ['-p', head]
        commit = git(source, '-c', 'user.name=OpenWrt scheduler', '-c',
                     'user.email=openwrt-scheduler@localhost', 'commit-tree', tree, *parents,
                     input=b'Snapshot local inputs for scheduled integration\n')
        git(source, 'update-ref', REF, commit)
    (record / 'snapshot-index').unlink(missing_ok=True)
    data = {'source': str(source), 'head': head, 'snapshot': commit, 'skipped_non_source': skipped, 'included_untracked': included}
    atomic_json(record / 'snapshot.json', data)
    return data


def feed_definitions(source):
    config = source / 'feeds.conf'
    if not config.exists():
        config = source / 'feeds.conf.default'
    feeds = []
    for line in config.read_text().splitlines():
        if not line.strip() or line.lstrip().startswith('#'):
            continue
        fields = line.split()
        kind, name, remote = fields[:3]
        if not re.fullmatch(r'[A-Za-z0-9_-]+', name):
            raise ValueError('Invalid feed name: ' + name)
        if kind == 'src-link':
            feeds.append({'kind': kind, 'name': name, 'path': remote})
        elif kind in ('src-git', 'src-git-full'):
            if '^' in remote:
                url, revision = remote.rsplit('^', 1)
            elif ';' in remote:
                url, revision = remote.rsplit(';', 1)
            else:
                url, revision = remote, 'HEAD'
            feeds.append({'kind': kind, 'name': name, 'url': url, 'revision': revision})
        else:
            raise ValueError('Unsupported scheduled feed type: ' + kind)
    return feeds


def check_repository_idle(source):
    for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'rebase-merge', 'rebase-apply', 'index.lock'):
        pending = Path(git(source, 'rev-parse', '--path-format=absolute', '--git-path', marker))
        if pending.exists():
            raise ValueError('Repository already has an unfinished Git operation: ' + str(pending))


def prepare_repository(source, record, url=None, revision=None):
    check_repository_idle(source)
    snapshot = source_snapshot(source, record)
    branch = git(source, 'symbolic-ref', 'HEAD')
    # Snapshot commits are private recovery points, never merged into the user's branch.
    return {'path': str(source), 'original_head': snapshot['head'],
            'local_snapshot': snapshot['snapshot'], 'branch': branch,
            'backup': str(record), 'url': url, 'revision': revision,
            'original_stashes': git(source, 'stash', 'list', '--format=%H').splitlines(),
            'original_untracked': snapshot['included_untracked'],
            'original_dirty_paths': subprocess.check_output(
                ['git', '-C', str(source), 'diff', '--name-only', '-z', 'HEAD']).decode().split('\0')}


def prepare(source, run):
    url = git(source, 'remote', 'get-url', 'origin')
    branch = git(source, 'symbolic-ref', '--short', 'HEAD')
    definitions = [(source, run / 'inputs/main', url, branch)]
    for entry in subprocess.check_output(['git', '-C', str(source), 'ls-files', '--stage']).decode().splitlines():
        if entry.startswith('160000 '):
            name = entry.split('\t', 1)[1]
            definitions.append((source / name, run / 'inputs/nested' / name, None, None))
    for feed in feed_definitions(source):
        if feed['kind'] == 'src-link':
            target = (source / 'feeds' / feed['path']).resolve()
            if not target.is_relative_to(source.resolve()):
                raise ValueError('External src-link feed is outside the scheduled workspace: ' + feed['name'])
        else:
            definitions.append((source / 'feeds' / feed['name'], run / 'inputs/feeds' / feed['name'],
                                feed['url'], feed['revision']))
    # Audit all repositories before taking snapshots or starting an integration.
    for repo, _, _, _ in definitions:
        check_repository_idle(repo)
        git(repo, 'symbolic-ref', 'HEAD')
    repositories = [prepare_repository(*entry) for entry in definitions]
    shutil.copy2(source / '.config', run / 'input.config')
    for name in ('files', 'overlay'):
        original = source / name
        if original.exists():
            with tarfile.open(run / (name + '.tar.gz'), 'w:gz') as archive:
                archive.add(original, arcname=name)
    atomic_json(run / 'repositories.json', repositories)
    return repositories


def merge_prompt(repositories, workspace):
    return f'''Perform the user-authorized scheduled OpenWrt upstream integration IN PLACE in {workspace}.
This is the user's current workspace. Do not create or maintain another checkout/worktree.
Repository inputs:\n{json.dumps(repositories, indent=2)}

For EVERY repository with a url, fetch that exact URL and merge the specified
revision (HEAD means the remote default branch). Do not change remotes or branches.
Fetch missing/shallow history as needed. Record the fetched commit in the file
.git/scheduled-upstream after a successful fetch, before merging. Merge rather
than reset/rebase so the original local HEAD and upstream remain ancestors.
The local_snapshot values are BACKUPS ONLY: do not merge them or commit the user's
uncommitted work. They contain unrelated/private files intentionally left uncommitted.
Before merging, inspect tracked edits and staged changes. If they block merging,
use a uniquely named temporary stash limited to explicit colliding paths; preserve
its hash in the run backup directory first. Reapply the stash with --index after
the merge, automatically resolve any conflicts retaining the user's local intent,
and restore the original staged/unstaged distinction wherever possible. Keep any
automation stash on failure; never pop/drop existing user stashes. Preserve every
original untracked file; move a colliding one into the private backup directory
before merging, then reconcile its local content. Do not stage unrelated work,
blanket git add, clean/reset, overwrite .config/overlays/signing keys or discard files.
Automatically resolve conflicts by understanding both changes and keeping local
OpenWrt native-systemd, glibc, APK, desktop, virtualization and package fixes while
incorporating upstream fixes. Do not blindly choose ours/theirs, skip a repository,
drop local patches, change remotes, push, or silently disable selected features.
Process nested repositories before the main repository where gitlinks overlap.
Commit only merge/conflict resolutions and necessary parent gitlink updates, using
a temporary index if the real index contains unrelated staged work. Preserve all
other local edits as uncommitted work, and preserve original branches and stashes.
No package installation on the physical router, no host service changes, VM changes,
firmware flashing, building or feed publication in this step. Do not leave unresolved
conflicts or unfinished merges. Inspect git diff --check for every repo. Report each
old/new/upstream commit, conflict resolutions and any changed staged/unstaged intent
in your final response. If semantic integration cannot be established, fail the task
and explain why; do not discard work to obtain a clean status.
'''


def verify_repositories(repositories):
    for repo in repositories:
        path = Path(repo['path'])
        for marker in ('MERGE_HEAD', 'CHERRY_PICK_HEAD', 'rebase-merge', 'rebase-apply'):
            pending = Path(git(path, 'rev-parse', '--path-format=absolute', '--git-path', marker))
            if pending.exists():
                raise ValueError('Unfinished Git operation: ' + str(pending))
        if git(path, 'ls-files', '--unmerged'):
            raise ValueError('Unfinished integration: ' + str(path))
        if git(path, 'symbolic-ref', 'HEAD') != repo['branch']:
            raise ValueError('Integration changed the current branch: ' + str(path))
        git(path, 'merge-base', '--is-ancestor', repo['original_head'], 'HEAD')
        stashes = set(git(path, 'stash', 'list', '--format=%H').splitlines())
        if not set(repo['original_stashes']).issubset(stashes):
            raise ValueError('Integration removed an original user stash: ' + str(path))
        for name in repo['original_untracked']:
            item = path / name
            if not item.exists() and not item.is_symlink():
                raise ValueError('Integration removed an original untracked source file: ' + str(item))
        dirty = set(subprocess.check_output(['git', '-C', str(path), 'diff',
                                            '--name-only', '-z', 'HEAD']).decode().split('\0'))
        gitlinks = {line.split('\t', 1)[1] for line in git(path, 'ls-files', '--stage').splitlines()
                    if line.startswith('160000 ')}
        if dirty - set(repo['original_dirty_paths']) - gitlinks - {''}:
            raise ValueError('Integration left new uncommitted tracked fixes: ' + str(path))
        if repo['url']:
            marker = Path(git(path, 'rev-parse', '--path-format=absolute', '--git-path', 'scheduled-upstream'))
            upstream = marker.read_text().strip()
            if not re.fullmatch('[0-9a-f]{40,64}', upstream):
                raise ValueError('Missing exact fetched upstream commit')
            revision = repo['revision']
            if re.fullmatch('[0-9a-f]{40,64}', revision):
                expected = revision
            else:
                remote_ref = 'HEAD' if revision == 'HEAD' else 'refs/heads/' + revision
                lines = git(path, 'ls-remote', repo['url'], remote_ref).splitlines()
                if len(lines) != 1:
                    raise ValueError('Could not resolve upstream revision: ' + revision)
                expected = lines[0].split()[0]
            if upstream != expected:
                raise ValueError('Recorded upstream differs from current remote: ' + str(path))
            git(path, 'merge-base', '--is-ancestor', upstream, 'HEAD')
            repo['upstream_commit'] = upstream
        git(path, 'diff', '--check')
        repo['merged_commit'] = git(path, 'rev-parse', 'HEAD')


def run_logged(argv, cwd, log, timeout):
    with log.open('ab') as stream:
        process = subprocess.Popen([str(a) for a in argv], cwd=cwd, stdout=stream,
            stderr=subprocess.STDOUT, env=dict(os.environ, PYTHONUNBUFFERED='1'),
            umask=0o022, start_new_session=True)
        try:
            status = process.wait(timeout=timeout)
            if status:
                raise subprocess.CalledProcessError(status, argv)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGTERM)
                process.wait(timeout=10)
            except ProcessLookupError:
                pass
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
            raise


def verify_feature_config(original, worker):
    publisher = load('scheduled_feature_config', 'build-and-publish.py')
    required = dict(line.split('=', 1) for line in original.read_text().splitlines()
                    if line.startswith('CONFIG_') and '=' in line)
    actual = publisher.configuration(worker)
    for name in ('CONFIG_OPENWRT_SYSTEMD', 'CONFIG_USE_GLIBC', 'CONFIG_USE_APK', 'CONFIG_TARGET_x86_64'):
        if required.get(name) != 'y':
            raise ValueError('This scheduled workflow requires the native x86_64/glibc/APK build: ' + name)
    features = ['CONFIG_OPENWRT_SYSTEMD', 'CONFIG_USE_GLIBC', 'CONFIG_USE_APK',
                'CONFIG_TARGET_x86_64', 'CONFIG_OPENWRT_KERNEL_UPGRADE',
                'CONFIG_WESTON_XWAYLAND', 'CONFIG_WESTON_VNC', 'CONFIG_WESTON_RDP',
                'CONFIG_QEMU_OPENGL', 'CONFIG_QEMU_VIRGLRENDERER']
    features += ['CONFIG_PACKAGE_' + name for name in (
        'openwrt-desktop', 'libvirt-daemon', 'openwrt-flatpak', 'podman',
        'openwrt-appimage', 'distrobox', 'gcc', 'native-libs-dev',
        'virt-manager', 'firefox-esr-bin', 'openwrt-podman-rootless')]
    for name in features:
        if required.get(name) == 'y' and actual.get(name) != 'y':
            raise ValueError('Configuration lost a selected core feature: ' + name)


def gated_publish(worker, receipt, image):
    smoke = load('scheduled_smoke', 'test-image-network.py')
    if (receipt.get('status') != 'passed' or set(receipt.get('checks', {})) != smoke.REQUIRED
            or not all(value is True for value in receipt['checks'].values())
            or receipt['image_sha256'] != smoke.sha256(image)
            or receipt['image'] != str(image.resolve())):
        raise ValueError('Exact image has no complete passing VM validation receipt')
    publisher = load('scheduled_publisher', 'build-and-publish.py')
    # Existing signed, ABI-pinned publisher validates both repository views first.
    return publisher.publish(worker, publisher.settings(worker))


def execute(config, run):
    worker = SOURCE
    repositories = prepare(worker, run)
    daemon = load('scheduled_daemon', 'codex-daemon-task.py')
    prompt = merge_prompt(repositories, worker)
    (run / 'integration-prompt.txt').write_text(prompt)
    atomic_json(run / 'codex-integration.json', daemon.run_task(
        worker, prompt, run / 'codex-integration.jsonl', config['codex_timeout'], extra_writable=[run]))
    verify_repositories(repositories)
    atomic_json(run / 'repositories.json', repositories)
    run_logged(['./scripts/feeds', 'update', '-i', '-a'], worker, run / 'feed-index.log', 3600)
    run_logged(['./scripts/feeds', 'install', '-a'], worker, run / 'feed-install.log', 3600)
    jobs = config['jobs']
    for attempt in range(config['repair_attempts'] + 1):
        log = run / f'build-{attempt}.log'
        try:
            run_logged(['make', 'defconfig'], worker, log, 600)
            run_logged(['scripts/config/conf', '--fatalrecursive', '--defconfig=.config',
                        '-w', '.config', 'Config.in'], worker, log, 600)
            verify_feature_config(run / 'input.config', worker)
            run_logged([sys.executable, str(SOURCE / 'scripts/scheduled-maintenance.py'),
                        '--build-worker', str(worker), '--jobs', str(jobs)],
                        worker, log, config['build_timeout'])
            break
        except (subprocess.CalledProcessError, ValueError) as failure:
            if attempt == config['repair_attempts']:
                raise
            prompt = (f'Repair the failed scheduled OpenWrt build in {worker}. Read {log}. '
                      f'Failure: {failure}. '
                      'Preserve local features, exact kernel ABI rules, config selections and '
                      'upstream integration. Fix root causes; do not weaken validation, disable '
                      'selected features, publish, push or contact/modify the physical router. '
                      'Work IN PLACE in this current workspace and its feeds. Preserve the user\'s '
                      'pre-existing uncommitted/staged work and original stashes; do not commit '
                      'unrelated work. Commit only your source fixes using an alternate index '
                      'when needed. Do not create another checkout. Repository backup/provenance: '
                      f'{run / "repositories.json"}. The scheduler will retry the full build.')
            atomic_json(run / f'codex-repair-{attempt}.json', daemon.run_task(
                worker, prompt, run / f'codex-repair-{attempt}.jsonl', config['codex_timeout'], extra_writable=[run]))
            verify_repositories(repositories)
            atomic_json(run / f'repositories-after-repair-{attempt}.json', repositories)
    verify_repositories(repositories)
    atomic_json(run / 'repositories-built.json', repositories)
    image = worker / 'bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-squashfs-combined-efi.img.gz'
    smoke = load('scheduled_image_test', 'test-image-network.py')
    receipt = smoke.test_image(image, run / 'vm')
    atomic_json(run / 'publication.json', gated_publish(worker, receipt, image))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=SOURCE / 'configs/scheduled-maintenance.json')
    parser.add_argument('--scheduled', action='store_true', help='Run only when the 72-hour interval is due')
    parser.add_argument('--status', action='store_true')
    parser.add_argument('--initialize', action='store_true', help='Anchor first run 72 hours after the next configured start time')
    parser.add_argument('--run-now', action='store_true', help='Run all five steps now')
    parser.add_argument('--build-worker', type=Path, help=argparse.SUPPRESS)
    parser.add_argument('--jobs', type=int, default=8)
    args = parser.parse_args()
    if args.build_worker:
        publisher = load('scheduled_build', 'build-and-publish.py')
        print(json.dumps(publisher.build(args.build_worker, ['-j' + str(args.jobs), 'V=s'], publish_after=False)))
        return
    config = json.loads(args.config.read_text())
    root = Path(config['state_root']).resolve()
    if root == SOURCE or root.is_relative_to(SOURCE) or SOURCE.is_relative_to(root):
        raise ValueError('State root must be separate from the source checkout')
    root.mkdir(parents=True, exist_ok=True)
    root.chmod(0o700)
    state = root / 'schedule.json'
    if args.status and not args.initialize:
        print(state.read_text() if state.exists() else '{}')
        return
    with (root / 'scheduler.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print('Scheduled maintenance already running; skipped')
            return
        data = json.loads(state.read_text()) if state.exists() else {}
        if args.initialize:
            if not data:
                data = {'next_run': initial_run_time(time.time(), config), 'interval_seconds': INTERVAL}
                atomic_json(state, data)
        if args.status or args.initialize:
            print(json.dumps(data, indent=2))
            return
        if not args.scheduled and not args.run_now:
            parser.error('Choose --scheduled, --status, --initialize or --run-now')
        now = time.time()
        if args.scheduled and now < data.get('next_run', 0):
            return
        if any(shutil.disk_usage(path).free < config['minimum_free_gib'] * 1024 ** 3
               for path in (SOURCE, root)):
            raise ValueError('Insufficient free space for scheduled image build')
        run = root / 'runs' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
        run.mkdir(parents=True, mode=0o700)
        anchor = data.get('next_run', (int(now) // 3600) * 3600)
        next_run = anchor + (int((now - anchor) // INTERVAL) + 1) * INTERVAL if anchor <= now else anchor
        data.update(last_started=now, next_run=next_run, last_run=str(run), status='running')
        atomic_json(state, data)
        # Cron has a minimal environment. Keep binaries deterministic and avoid Android qemu-img.
        os.environ['PATH'] = str(Path.home() / '.local/bin') + ':/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin'
        os.environ['GIT_TERMINAL_PROMPT'] = '0'
        os.environ['GIT_MERGE_AUTOEDIT'] = 'no'
        try:
            execute(config, run)
            data.update(status='passed', last_success=time.time())
        except BaseException as error:
            data.update(status='failed', error=str(error))
            raise
        finally:
            data['last_finished'] = time.time()
            atomic_json(state, data)
            atomic_json(run / 'result.json', data)


if __name__ == '__main__':
    main()
