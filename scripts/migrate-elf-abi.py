#!/usr/bin/env python3
"""Repackage verified, ABI-compatible APK payloads for the ELF metadata migration.

The input inventory is an audit of exact signed APKs. Repackaging preserves
scripts and every existing file's ACL, target, content and timestamp, except
the package file list and the generated ELF inventory's release metadata. Incompatible ELF
must be rebuilt separately before this tool accepts the complete package set.
Run --worker only inside fakeroot; it cannot publish or install packages.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import subprocess

TREE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('migrate_elf', TREE / 'scripts/elf-abi.py')
ELF = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ELF)


def run(command, **kwargs):
    return subprocess.run(list(map(str, command)), check=True, capture_output=True, **kwargs)


def path_records(metadata):
    for directory in metadata.get('paths', []):
        prefix = directory.get('name', '')
        yield prefix, directory
        for file in directory.get('files', []):
            yield prefix + '/' + file['name'], file


def worker(plan, names):
    if not os.environ.get('FAKEROOTKEY'):
        raise ValueError('Migration worker requires fakeroot to preserve original ACLs')
    apk = TREE / 'staging_dir/host/bin/apk'
    context = ELF.Context({n: r['elf'] for n, r in plan['records'].items()})
    for name in names:
        record = plan['records'][name]
        old = record['metadata']
        inventory = record['elf']
        root = Path(record.get('root', Path(plan['workspace']) / 'payloads' / name))
        actual = ELF.inspect(root)
        output_inventory = root / 'usr/lib/apk/packages' / (name + '.elf.json')
        if output_inventory.exists():
            original_inventory = {**actual, 'package': name, 'version': old['info']['version']}
            if json.loads(output_inventory.read_text()) != original_inventory:
                raise ValueError(f'{name}: existing ELF inventory is stale')
        actual.update(package=name, version=inventory['version'])
        if actual != inventory:
            raise ValueError(f'{name}: payload changed after audit')
        deps, provides = ELF.contracts(inventory, name, context)
        info = dict(old['info'])
        info['version'] = inventory['version']
        dependencies = []
        ledger = ELF.migration_releases()
        for dependency in info.get('depends', []):
            match = re.fullmatch(r'([^=<>~]+)=([^=]+)', dependency)
            if match and match[1] in plan['records']:
                provider = plan['records'][match[1]]
                if match[2] == provider['info']['version']:
                    dependency = match[1] + '=' + provider['elf']['version']
                else:
                    rebuild = next((e for e in ledger.get(match[1], []) if e['before'] == match[2]), None)
                    if rebuild:
                        dependency = match[1] + '=' + rebuild['after']
            dependencies.append(dependency)
        info['depends'] = sorted(set(dependencies + deps))
        aliases = []
        for provide in info.get('provides', []):
            alias, separator, version = provide.partition('=')
            if separator and version == old['info']['version']:
                provide = alias + '=' + info['version']
            aliases.append(provide)
        info['provides'] = sorted(set(aliases + provides))
        if inventory['files'] or output_inventory.exists():
            ELF.write_changed(output_inventory, json.dumps(inventory, sort_keys=True, separators=(',', ':')) + '\n', mode=0o644)
        filelist = root / 'usr/lib/apk/packages' / (name + '.list')
        if filelist.exists():
            entries = filelist.read_text().splitlines()
            if output_inventory.exists():
                entries.append('/usr/lib/apk/packages/' + name + '.elf.json')
            ELF.write_changed(filelist, '\n'.join(sorted(set(entries))) + '\n')
        # Unknown IDs are given private synthetic numbers; --root idroot maps
        # those numbers back to their ORIGINAL package owner/group names.
        for directory, dirs, files in os.walk(root, followlinks=False):
            for path in [Path(directory), *[Path(directory) / n for n in dirs + files]]:
                os.chown(path, 0, 0, follow_symlinks=False)
        for relative, item in path_records(old):
            path = root / relative.lstrip('/')
            acl = item['acl']
            os.chown(path, plan['users'][acl['user']], plan['groups'][acl['group']], follow_symlinks=False)
            if not path.is_symlink():
                os.chmod(path, acl['mode'])
        scripts = Path(plan['workspace']) / 'scripts' / name
        scripts.mkdir(parents=True, exist_ok=True)
        output = Path(plan['output']) / record['repository'] / (name + '-' + info['version'] + '.apk')
        output.parent.mkdir(parents=True, exist_ok=True)
        command = [apk, '--root', plan['idroot'], 'mkpkg', '--files', root,
                   '--output', output, '--sign-key', TREE / 'private-key.pem']
        for key, value in info.items():
            if key in ('hashes', 'installed-size', 'file-size', 'build-time'):
                continue
            if isinstance(value, list):
                value = ' '.join(map(str, value))
            command += ['--info', key + ':' + str(value)]
        for typ, content in old.get('scripts', {}).items():
            path = scripts / typ
            path.write_text(content)
            command += ['--script', typ + ':' + str(path)]
        for trigger in old.get('triggers', []):
            command += ['--trigger', trigger]
        run(command, env={**os.environ, 'SOURCE_DATE_EPOCH': '0'})
        fresh = json.loads(run([apk, 'adbdump', '--format', 'json', output]).stdout)
        if fresh.get('scripts', {}) != old.get('scripts', {}) or fresh.get('triggers', []) != old.get('triggers', []):
            raise ValueError(f'{name}: package scripts/triggers changed')
        before = dict(path_records(old))
        after = dict(path_records(fresh))
        unexpected = set(after) - set(before) - {'usr/lib/apk/packages/' + name + '.elf.json'}
        if unexpected:
            raise ValueError(f'{name}: unexpected new package paths: {sorted(unexpected)}')
        for relative, item in before.items():
            new = after.get(relative)
            if new is None:
                raise ValueError(f'{name}: package path disappeared: {relative}')
            for key in ('acl', 'target', 'mtime', 'hash', 'size'):
                if relative in ('usr/lib/apk/packages/' + name + '.list',
                                'usr/lib/apk/packages/' + name + '.elf.json') and key in ('hash', 'size'):
                    continue
                if item.get(key) != new.get(key):
                    raise ValueError(f'{name}: {relative}: {key} changed: {item.get(key)!r} -> {new.get(key)!r}')
        print(json.dumps({'package': name, 'version': info['version'], 'output': str(output),
                          'sha256': hashlib.file_digest(output.open('rb'), 'sha256').hexdigest()}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plan', type=Path, required=True)
    parser.add_argument('--worker', nargs='+', required=True)
    args = parser.parse_args()
    try:
        worker(json.loads(args.plan.read_text()), args.worker)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        parser.exit(1, str(error) + (('\n' + error.stderr.decode()) if isinstance(error, subprocess.CalledProcessError) else '') + '\n')


if __name__ == '__main__':
    main()
