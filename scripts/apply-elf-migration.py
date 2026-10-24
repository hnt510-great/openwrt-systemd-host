#!/usr/bin/env python3
"""Apply an audited offline ELF-metadata migration with a file/database rollback.

Run as root on the target. The private bundle contains plan.json, repo/ and
this script. --simulate never changes the live world. --apply is intended to
run in a transient systemd service; --accept cancels rollback only after the
operator has checked the application's runtime behavior.
"""
import argparse
import base64
import fcntl
import hashlib
import json
import os
from pathlib import Path
import posixpath
import subprocess
import tarfile


def sha(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def atomic(path, data):
    path = Path(path)
    temporary = path.with_name(path.name + '.elf-migration-tmp')
    temporary.write_bytes(data)
    temporary.chmod(0o600)
    os.replace(temporary, path)


def run(args, log=None):
    if log:
        with Path(log).open('w') as stream:
            result = subprocess.run(args, stdout=stream, stderr=subprocess.STDOUT)
    else:
        result = subprocess.run(args, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(f'Command failed ({result.returncode}): {args[:5]}; log={log}')
    return result


def installed():
    records = {}
    for record in Path('/lib/apk/db/installed').read_text().split('\n\n'):
        fields, folder, files = {}, '', []
        for line in record.splitlines():
            if line.startswith('F:'):
                folder = line[2:]
            elif line.startswith('R:'):
                files.append(folder + '/' + line[2:])
            elif line[:2] in ('P:', 'V:', 'C:'):
                fields[line[0]] = line[2:]
        if 'P' in fields:
            records[fields['P']] = {**fields, 'files': files}
    return records


def payload_path(relative):
    """Collapse merged-/usr aliases, not application symlinks or their targets."""
    first, separator, tail = relative.partition('/')
    alias = Path('/') / first
    if first in ('bin', 'sbin', 'lib', 'lib64') and alias.is_symlink():
        target = posixpath.normpath(posixpath.join('/', os.readlink(alias)))
        return posixpath.join(target, tail).lstrip('/')
    return relative


class Migration:
    def __init__(self, directory):
        self.directory = directory.resolve()
        self.plan = json.loads((self.directory / 'plan.json').read_text())
        if self.plan.get('schema') != 1 or os.geteuid() != 0:
            raise ValueError('Requires root and a schema-1 audited migration plan')
        self.cache = self.directory / 'cache'
        self.cache.mkdir(exist_ok=True)
        self.command = ['apk', '--no-logfile', '--cache-dir', str(self.cache),
                        '--no-network', '--repositories-file', '/dev/null']
        for relative in self.plan.get('repo_indexes', ['repo/packages.adb']):
            self.command += ['--repository', str(self.directory / relative)]

    def state(self, phase, **fields):
        atomic(self.directory / 'state.json', json.dumps({'phase': phase, **fields}, indent=2).encode())

    def baseline(self):
        if Path('/proc/sys/kernel/random/boot_id').read_text().strip() != self.plan['boot_id']:
            raise ValueError('Target rebooted after migration audit')
        for path, digest in self.plan['baseline_hashes'].items():
            if sha(path) != digest:
                raise ValueError('Target baseline changed: ' + path)

    def verify_payloads(self):
        if self.plan.get('tool_sha256') and sha(Path(__file__).resolve()) != self.plan['tool_sha256']:
            raise ValueError('Migration tool changed after audit')
        paths = []
        for relative, digest in self.plan['files'].items():
            path = self.directory / relative
            if Path(relative).is_absolute() or '..' in Path(relative).parts or not path.resolve().is_relative_to(self.directory) or path.is_symlink() or sha(path) != digest:
                raise ValueError('Migration payload changed: ' + relative)
            paths.append(str(path))
        run(['apk', 'verify', *paths], self.directory / 'signature-verification.log')

    def simulate(self):
        self.baseline()
        self.verify_payloads()
        atomic(self.directory / 'world.planned', self.plan['world_after'].encode())
        planfile = self.directory / 'transaction.json'
        command = self.command + ['upgrade', '--no-preupgrade', '--simulate', '--plan-json', str(planfile)]
        run(['unshare', '--mount', '--propagation', 'private', 'sh', '-c',
             'mount --bind "$1" /etc/apk/world || exit; shift; exec "$@"',
             'elf-world-view', str(self.directory / 'world.planned'), *command],
            self.directory / 'simulate.log')
        changes = json.loads(planfile.read_text())['changes']
        identity = lambda rows: sorted((x['name'], x['before'], x['after'], x.get('package_digest')) for x in rows)
        if identity(changes) != identity(self.plan['changes']):
            raise ValueError('Offline transaction differs from the signed publication audit')
        if any(x['name'] == 'kernel' or x['name'].startswith(('kmod-', 'linux-image-', 'kernel-dev-headers')) for x in changes):
            raise ValueError('Metadata migration must not change kernel packages')
        self.baseline()
        self.state('simulated', changes=len(changes))
        print('Exact offline simulation passed:', len(changes), 'packages', flush=True)

    def backup(self):
        records = installed()
        paths = {'etc', 'usr/lib/apk/db'}
        absent = []
        groups = [records[change['name']]['files'] for change in self.plan['changes']]
        groups.append(self.plan.get('package_paths', []))
        for files in groups:
            for relative in files:
                if relative.startswith('/') or '..' in Path(relative).parts or relative.startswith(('proc/', 'sys/', 'dev/', 'run/')):
                    raise ValueError('Unsafe installed package path: ' + relative)
                relative = payload_path(relative)
                path = Path('/') / relative
                if os.path.lexists(path):
                    paths.add(relative)
                else:
                    absent.append(relative)
        # --no-recursion avoids following package-owned directory entries.
        # Enumerate /etc and the package database explicitly, preserving links.
        for root in ('/etc', '/usr/lib/apk/db'):
            for directory, dirs, files in os.walk(root, followlinks=False):
                paths.add(directory.lstrip('/'))
                paths.update(str(Path(directory) / n).lstrip('/') for n in dirs + files)
        paths.update(('usr/lib/apk/packages',))
        for directory, dirs, files in os.walk('/usr/lib/apk/packages', followlinks=False):
            paths.add(directory.lstrip('/'))
            paths.update(str(Path(directory) / n).lstrip('/') for n in dirs + files)
        paths.discard('usr/lib/apk/db/lock')
        listing = self.directory / 'rollback-paths.txt'
        listing.write_text('\n'.join(sorted(paths)) + '\n')
        atomic(self.directory / 'world.before', Path('/etc/apk/world').read_bytes())
        atomic(self.directory / 'absent-before.json', json.dumps(absent).encode())
        run(['tar', '--acls', '--xattrs', '--xattrs-include=*', '--numeric-owner', '--no-recursion', '-cpf',
             str(self.directory / 'rollback-files.tar'), '-C', '/', '-T', str(listing)],
            self.directory / 'backup.log')
        self.baseline()

    def apply(self):
        self.simulate()
        self.backup()
        run(['systemd-run', '--unit', self.plan['rollback_unit'], '--on-active=20m',
             '--timer-property=AccuracySec=1s', '/usr/bin/python3', str(Path(__file__).resolve()),
             '--directory', str(self.directory), '--rollback'])
        self.baseline()
        atomic('/etc/apk/world', self.plan['world_after'].encode())
        self.state('installing')
        try:
            run(self.command + ['upgrade', '--no-preupgrade'], self.directory / 'install.log')
            self.verify_installed()
            self.state('installed-awaiting-runtime-acceptance', changes=len(self.plan['changes']))
            print('Installation passed; rollback timer remains armed.', flush=True)
        except Exception:
            self.rollback()
            raise

    def verify_installed(self):
        records = installed()
        for change in self.plan['changes']:
            record = records.get(change['name'], {})
            if record.get('V') != change['after']:
                raise ValueError('Unexpected installed version: ' + change['name'])
            identity = change.get('package_digest')
            if identity and record.get('C') != 'Q1' + base64.b64encode(bytes.fromhex(identity)[:20]).decode():
                raise ValueError('Unexpected installed APK identity: ' + change['name'])
            marker = Path('/usr/lib/apk/packages') / (change['name'] + '.elf.json')
            if change['name'] in self.plan['native_packages'] and not marker.exists():
                raise ValueError('Missing installed ELF metadata: ' + change['name'])
        if Path('/etc/apk/world').read_text() != self.plan['world_after']:
            raise ValueError('Unexpected migration world')
        for path, digest in self.plan['kernel_hashes'].items():
            if sha(path) != digest:
                raise ValueError('Kernel state changed: ' + path)
        for path, digest in self.plan.get('config_hashes', {}).items():
            if sha(path) != digest:
                raise ValueError('Protected configuration changed: ' + path)
        run(['kernelctl', 'check'], self.directory / 'kernel-check.log')

    def rollback(self):
        with open('/lib/apk/db/lock', 'rb') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            self.restore()

    def restore(self):
        archive = self.directory / 'rollback-files.tar'
        if not archive.exists():
            raise ValueError('Rollback archive does not exist')
        directories, files = [], []
        with tarfile.open(archive, 'r:') as stream:
            for member in stream:
                name = member.name.rstrip('/')
                if name in ('usr/lib/apk/db/lock', 'lib/apk/db/lock'):
                    continue
                (directories if member.isdir() else files).append(name)
        for name, paths in [('directories', directories), ('files', files)]:
            (self.directory / ('restore-' + name + '.list')).write_bytes(
                b''.join(path.encode() + b'\0' for path in paths))
        base = ['tar', '--no-recursion', '--acls', '--xattrs', '--xattrs-include=*',
                '--numeric-owner', '-xpf', str(archive), '-C', '/', '--null', '--verbatim-files-from']
        # GNU tar's --unlink-first also tries to unlink directories. Extract
        # directory entries separately, then replace files with NEW inodes,
        # and finally restore directory attributes/timestamps.
        for name, flags in [('directories', []), ('files', ['--unlink-first']), ('directories', [])]:
            run(base + flags + ['-T', str(self.directory / ('restore-' + name + '.list'))],
                self.directory / ('rollback-' + name + '.log'))
        for relative in json.loads((self.directory / 'absent-before.json').read_text()):
            path = Path('/') / relative
            if path.is_file() or path.is_symlink():
                path.unlink()
        for change in self.plan['changes']:
            marker = Path('/usr/lib/apk/packages') / (change['name'] + '.elf.json')
            if str(marker).lstrip('/') not in (self.directory / 'rollback-paths.txt').read_text().splitlines():
                marker.unlink(missing_ok=True)
        atomic('/etc/apk/world', (self.directory / 'world.before').read_bytes())
        run(['systemctl', 'daemon-reload'])
        run(['systemctl', 'stop', self.plan['rollback_unit'] + '.timer'])
        self.state('rolled-back')

    def accept(self):
        self.verify_installed()
        run(['systemctl', 'stop', self.plan['rollback_unit'] + '.timer'])
        self.state('accepted', changes=len(self.plan['changes']))
        print('Migration accepted; rollback timer cancelled.', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory', required=True, type=Path)
    group = parser.add_mutually_exclusive_group(required=True)
    for mode in ('simulate', 'apply', 'rollback', 'accept'):
        group.add_argument('--' + mode, action='store_true')
    args = parser.parse_args()
    migration = Migration(args.directory)
    for mode in ('simulate', 'apply', 'rollback', 'accept'):
        if getattr(args, mode):
            getattr(migration, mode)()


if __name__ == '__main__':
    main()
