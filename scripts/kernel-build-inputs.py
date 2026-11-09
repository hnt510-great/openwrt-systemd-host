#!/usr/bin/env python3
"""Fingerprint source/configuration inputs, excluding unrelated userspace."""
import hashlib
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess

SCHEMA = 1


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def files_under(path, seen=None):
    seen = set() if seen is None else seen
    if not path.exists():
        yield path
    elif path.is_file():
        yield path
    elif path.is_dir() and path.resolve() not in seen:
        seen.add(path.resolve())
        for child in sorted(path.iterdir()):
            if child.name not in ('.git', '__pycache__', '.DS_Store'):
                yield from files_under(child, seen)


def file_record(path):
    if not path.is_file():
        return {'missing': True}
    value = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            value.update(block)
    return {'sha256': value.hexdigest(), 'mode': path.stat().st_mode & 0o777}


def kernel_patchver(tree, config, make_args=()):
    """Resolve literal board/subtarget selections in the same order as target.mk."""
    board = config.get('CONFIG_TARGET_BOARD', '"x86"').strip('"')
    subtarget = config.get('CONFIG_TARGET_SUBTARGET', '').strip('"')
    target = tree / 'target/linux/feeds' / board
    if not target.is_dir():
        target = tree / 'target/linux' / board
    values = {}
    for path in (target / 'Makefile', target / subtarget / 'target.mk'):
        if path.is_file():
            for name, value in re.findall(
                    r'^(KERNEL_(?:TESTING_)?PATCHVER)\s*:?=\s*([^#\n]+)', path.read_text(), re.M):
                value = value.strip()
                if not re.fullmatch(r'[0-9]+\.[0-9]+', value):
                    raise ValueError('Nonliteral kernel selection in ' + str(path))
                values[name] = value
    overrides = dict(arg.split('=', 1) for arg in make_args
                     if '=' in arg and not arg.startswith('-'))
    if 'KERNEL_PATCHVER' in overrides:
        selected = overrides['KERNEL_PATCHVER']
    elif overrides.get('CONFIG_TESTING_KERNEL', config.get('CONFIG_TESTING_KERNEL')) == 'y':
        selected = overrides.get('KERNEL_TESTING_PATCHVER', values.get('KERNEL_TESTING_PATCHVER'))
        if not selected:
            raise ValueError('Testing kernel selected without KERNEL_TESTING_PATCHVER')
    else:
        selected = values.get('KERNEL_PATCHVER')
    if selected:
        if not re.fullmatch(r'[0-9]+\.[0-9]+', selected):
            raise ValueError('Invalid kernel series: ' + selected)
        return selected
    versions = sorted((tree / 'staging_dir').glob('target-*/kernel.version'))
    arch = config.get('CONFIG_ARCH', '').strip('"')
    libc = config.get('CONFIG_LIBC', '').strip('"')
    if arch and libc:
        versions = [path for path in versions if path.parent.name == 'target-' + arch + '_' + libc]
    if len(versions) != 1:
        raise ValueError('Cannot resolve the selected kernel series')
    return '.'.join(versions[0].read_text().split('~')[0].split('.')[:2])


def fingerprint(tree, config, make_args=()):
    metadata = tree / 'tmp/.packageinfo'
    if not metadata.is_file():
        raise ValueError('Refresh package metadata before selecting a kernel generation')
    selected = {key.removeprefix('CONFIG_PACKAGE_') for key, value in config.items()
                if key.startswith('CONFIG_PACKAGE_') and value in ('y', 'm')}
    providers, definitions, build_deps, kernel_packages, package_info = {}, {}, {}, set(), {}
    source = package = None
    for line in metadata.read_text().splitlines():
        if line.startswith('Source-Makefile: '):
            source = line.split(': ', 1)[1]
            definitions[source] = []
            build_deps[source] = []
        elif source and re.match(r'^Build-Depends(?:/[^:]+)?: ', line):
            build_deps[source] += line.split(': ', 1)[1].split()
        elif line.startswith('Package: '):
            package = line.split(': ', 1)[1]
            providers[package] = source
            package_info[package] = {}
        elif package and line.startswith('Kernel-Config: '):
            kernel_packages.add(package)
        if package and line.startswith(('Version: ', 'Source: ')):
            field, value = line.split(': ', 1)
            # The sequence is an output of this decision, not a new input.
            package_info[package][field] = re.sub(r'^1000\.[0-9]+\.', '1000.GENERATION.', value)
    wanted = {p for p in selected if p.startswith('kmod-') or p == 'kernel-dev-headers'}
    wanted |= selected & kernel_packages
    for package in wanted:
        if not providers.get(package):
            raise ValueError('Kernel package metadata missing: ' + package)
    sources = {providers[p] for p in wanted}
    pending = list(sources)
    # Package-level build dependencies can supply source generators/headers.
    aliases = {Path(path).parent.name: path for path in definitions}
    while pending:
        for dep in build_deps.get(pending.pop(), []):
            name = dep.split(':')[-1].removesuffix('/host')
            provider = providers.get(name) or aliases.get(name)
            if provider and provider not in sources:
                sources.add(provider)
                pending.append(provider)
    board = config.get('CONFIG_TARGET_BOARD', '"x86"').strip('"')
    target = tree / 'target/linux' / board
    roots = [tree / 'target/linux/generic', target, tree / 'package/kernel/linux',
             tree / 'toolchain', tree / 'rules.mk', tree / 'package/system/apk']
    roots += [tree / 'tools' / name for name in (
        'fakeroot', 'tar', 'patch', 'xz', 'zstd', 'libdeflate', 'bison', 'flex')]
    roots += [tree / path for path in ('include/download.mk', 'include/depends.mk',
        'include/quilt.mk', 'include/target.mk', 'include/toolchain-build.mk',
        'include/netfilter.mk', 'scripts/kconfig.pl', 'scripts/package-metadata.pl',
        'scripts/metadata.pm', 'scripts/kernel-package.py', 'scripts/kernel-bundle.py',
        'scripts/merge-usr.py',
        'scripts/strip-kmod.sh', 'scripts/strip.sh', 'scripts/gen-dependencies.sh',
        'scripts/apk-migrations.py', 'configs/apk-migrations.json')]
    roots += sorted((tree / 'include').glob('kernel*'))
    roots += sorted((tree / 'include').glob('package*.mk'))
    roots += sorted((tree / 'target/linux').glob('*/modules.mk'))
    roots += [tree / source for source in sources]
    # A provider's patches, local sources, config includes and symlinked feed
    # contents are inputs, not merely its Makefile or git revision.
    roots += [(tree / source).parent for source in sources]
    records, references = {}, set()
    for root in roots:
        for path in files_under(root):
            name = str(path.relative_to(tree))
            if name in records:
                continue
            records[name] = file_record(path)
            if path.is_file() and (path.suffix in ('.mk', '.in') or path.name in ('Makefile', 'Config.in')):
                references.update(re.findall(r'CONFIG_[A-Za-z0-9_-]+', path.read_text(errors='replace')))
    references |= {name for name in config if name.startswith(('CONFIG_KERNEL_',
                   'CONFIG_GCC_', 'CONFIG_BINUTILS_', 'CONFIG_TOOLCHAIN_'))}
    references |= {name for name in config if name.startswith('CONFIG_TARGET_') and not
        name.startswith(('CONFIG_TARGET_ROOTFS_', 'CONFIG_TARGET_SQUASHFS_',
                         'CONFIG_TARGET_UBIFS_', 'CONFIG_TARGET_IMAGES_')) and
        name not in ('CONFIG_TARGET_KERNEL_PARTSIZE', 'CONFIG_TARGET_SERIAL')}
    references |= {'CONFIG_OPENWRT_KERNEL_UPGRADE', 'CONFIG_PACKAGE_kernel-dev-headers'}
    references |= {'CONFIG_PACKAGE_' + name for name in wanted}
    references.discard('CONFIG_OPENWRT_KERNEL_SEQUENCE')
    options = {name: config.get(name, 'n') for name in sorted(references)}
    # Evaluate OpenWrt's real package -> kernel configuration requests. A
    # userspace selection matters only if it changes those kernel requests.
    patchver = kernel_patchver(tree, config, make_args)
    helper = Path(__file__).with_name('package-metadata.pl')
    override = subprocess.check_output(['perl', str(helper), 'kconfig', str(metadata),
        str(tree / '.config'), patchver], text=True)
    arguments = [arg for arg in make_args if '=' in arg and not arg.startswith('-')
                 and arg.split('=', 1)[0] not in ('V', 'OPENWRT_VERBOSE', 'SOURCE_DATE_EPOCH')]
    environment = {name: os.environ[name] for name in (
        'CC', 'HOSTCC', 'HOSTCFLAGS', 'HOST_CFLAGS', 'KCFLAGS', 'KAFLAGS',
        'HOSTLDFLAGS', 'HOST_LDFLAGS', 'LD', 'AR', 'AS', 'CROSS_COMPILE', 'ARCH',
        'LLVM', 'LLVM_IAS', 'KERNEL_CC', 'KERNEL_CROSS', 'KBUILD_BUILD_TIMESTAMP') if name in os.environ}
    defaults = {}
    if not config.get('CONFIG_KERNEL_BUILD_USER', '').strip('"'):
        defaults['user'] = getpass.getuser()
    if not config.get('CONFIG_KERNEL_BUILD_DOMAIN', '').strip('"'):
        defaults['host'] = socket.gethostname()
    source_hash = digest({'schema': SCHEMA, 'files': records, 'config': options,
                          'override': override, 'arguments': arguments,
                          'environment': environment, 'build_defaults': defaults,
                          'package_info': {name: package_info[name] for name in sorted(wanted)}})
    tools = {}
    gcc = config.get('CONFIG_GCC_VERSION', '').strip('"')
    libc = config.get('CONFIG_LIBC', '').strip('"')
    for folder in sorted((tree / 'staging_dir').glob('toolchain-*')):
        if gcc and '_gcc-' + gcc + '_' not in folder.name:
            continue
        if libc and not folder.name.endswith('_' + libc):
            continue
        for root in (folder / 'bin', folder / 'libexec/gcc'):
            for path in files_under(root):
                if path.is_file():
                    tools[str(path.relative_to(tree))] = file_record(path)
    for name in ('apk', 'fakeroot', 'tar', 'patch', 'xz', 'zstd', 'libdeflate-gzip', 'bison', 'flex'):
        path = tree / 'staging_dir/host/bin' / name
        tools[str(path.relative_to(tree))] = file_record(path)
    for pattern in ('libapk*', 'libfakeroot*', 'libmbed*', 'libcrypto*', 'libzstd*', 'liblzma*'):
        for path in sorted((tree / 'staging_dir/host/lib').glob(pattern)):
            if path.is_file():
                tools[str(path.relative_to(tree))] = file_record(path)
    # Host system programs only build helpers (kconfig, fixdep, modpost,
    # objtool) and run scripts; the kernel and modules come from the OpenWrt
    # cross toolchain above. Distribution upgrades of these programs alone do
    # not reserve a new generation: make does not rebuild the kernel for them,
    # and the kernel publisher refuses changed bytes under a published
    # generation. They are recorded for diagnosis only.
    host = {}
    for name in ('cc', 'ld', 'objcopy', 'bison', 'flex', 'perl', 'python3', 'make', 'bash'):
        path = shutil.which(name)
        if path:
            host['host-' + name] = file_record(Path(path))
    return {'source': source_hash, 'tools': digest(tools), 'host': digest(host),
            # The pre-split tools digest, for comparing state recorded by older builds.
            'legacy_tools': digest({**tools, **host}), 'schema': SCHEMA}


def same_tools(previous, current):
    """Whether the generation-relevant build tools match a recorded fingerprint."""
    if 'host' in previous:
        return previous.get('tools') == current['tools']
    # Recorded before host programs were split out of the tools digest.
    return previous.get('tools') in (current['tools'], current['legacy_tools'])


def same_inputs(previous, current):
    """Whether a recorded fingerprint still describes the same kernel generation."""
    return (previous.get('schema') == current['schema'] and
            previous.get('source') == current['source'] and same_tools(previous, current))
