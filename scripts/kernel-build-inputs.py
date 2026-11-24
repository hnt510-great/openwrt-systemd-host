#!/usr/bin/env python3
"""Fingerprint active kernel source/configuration inputs, excluding unrelated userspace."""
import hashlib
import getpass
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess

SCHEMA = 2

EXCLUDED_TARGET_CONFIG_PREFIXES = (
    'CONFIG_TARGET_ROOTFS_',
    'CONFIG_TARGET_SQUASHFS_',
    'CONFIG_TARGET_UBIFS_',
    'CONFIG_TARGET_IMAGES_',
)
EXCLUDED_TARGET_CONFIGS = {
    'CONFIG_TARGET_KERNEL_PARTSIZE',
    'CONFIG_TARGET_ROOTFS_PARTSIZE',
    'CONFIG_TARGET_SERIAL',
    'CONFIG_OPENWRT_KERNEL_SEQUENCE',
    'CONFIG_INSTALLER_ISO_IMAGES',
    'CONFIG_ISO_IMAGES',
    'CONFIG_VDI_IMAGES',
    'CONFIG_VMDK_IMAGES',
    'CONFIG_VHDX_IMAGES',
    'CONFIG_ONIE_INSTALLER_IMAGES',
    'CONFIG_GRUB_IMAGES',
    'CONFIG_GRUB_EFI_IMAGES',
    'CONFIG_GRUB_CONSOLE',
    'CONFIG_GRUB_SERIAL',
    'CONFIG_GRUB_BAUDRATE',
    'CONFIG_GRUB_FLOWCONTROL',
    'CONFIG_GRUB_TIMEOUT',
    'CONFIG_GRUB_TITLE',
    'CONFIG_GRUB_BOOTOPTS',
}
IGNORED_MAKE_ARGS = {
    'V', 'OPENWRT_VERBOSE', 'SOURCE_DATE_EPOCH',
    'ROLLING_APK_DIR', 'VM_MEDIA_DIR', 'KERNEL_REUSE_DIR',
}


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


def metadata_status(tree):
    """Check tmp/.packageinfo freshness without mutating the tree."""
    metadata = tree / 'tmp/.packageinfo'
    if not metadata.is_file():
        return 'missing'
    config = tree / '.config'
    if config.is_file() and config.stat().st_mtime > metadata.stat().st_mtime:
        return 'stale'
    return 'fresh'


def _target_dir(tree, board):
    feed_target = tree / 'target/linux/feeds' / board
    if feed_target.is_dir():
        return feed_target
    return tree / 'target/linux' / board


def kernel_patchver(tree, config, make_args=()):
    """Resolve literal board/subtarget selections in the same order as target.mk."""
    board = config.get('CONFIG_TARGET_BOARD', '"x86"').strip('"')
    subtarget = config.get('CONFIG_TARGET_SUBTARGET', '').strip('"')
    target = _target_dir(tree, board)
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


def _collect_group_files(tree, roots, references):
    records = {}
    for root in roots:
        for path in files_under(root):
            try:
                name = str(path.relative_to(tree))
            except ValueError:
                name = str(path)
            if name in records:
                continue
            records[name] = file_record(path)
            if path.is_file() and (path.suffix in ('.mk', '.in') or path.name in ('Makefile', 'Config.in')):
                references.update(re.findall(r'CONFIG_[A-Za-z0-9_-]+', path.read_text(errors='replace')))
    return records


def _compact_entries(group_data):
    """Build a compact item -> digest map for readable per-entry diffing."""
    entries = {}
    for key, value in sorted(group_data.items()):
        if isinstance(value, dict) and value and set(value.keys()) <= {'sha256', 'mode', 'missing'}:
            entries[key] = 'missing' if value.get('missing') else f"{value['sha256'][:16]}:{value['mode']:o}"
        else:
            entries[key] = digest(value)[:16]
    return entries


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
    subtarget = config.get('CONFIG_TARGET_SUBTARGET', '').strip('"')
    patchver = kernel_patchver(tree, config, make_args)
    generic = tree / 'target/linux/generic'
    target = _target_dir(tree, board)
    subtarget_dir = target / subtarget if subtarget else None

    references = set()

    # 1. Active kernel series version & hash metadata
    version_roots = [
        generic / f'kernel-{patchver}',
        tree / 'include/kernel-version.mk',
    ]
    kernel_version_group = _collect_group_files(tree, version_roots, references)

    # 2. Active kernel series patches and overlay files only (excludes other series and target/image)
    patch_roots = [
        generic / 'backport',
        generic / f'backport-{patchver}',
        generic / 'pending',
        generic / f'pending-{patchver}',
        generic / 'hack',
        generic / f'hack-{patchver}',
        generic / 'files',
        generic / f'files-{patchver}',
        target / 'patches',
        target / f'patches-{patchver}',
        target / 'files',
        target / f'files-{patchver}',
    ]
    if subtarget_dir is not None and subtarget_dir.is_dir():
        patch_roots += [
            subtarget_dir / 'patches',
            subtarget_dir / f'patches-{patchver}',
            subtarget_dir / 'files',
            subtarget_dir / f'files-{patchver}',
        ]
    # Include existing active patch/file dirs, plus always track active patches-<patchver>
    # even if missing so creating a new patch directory is detected.
    active_patch_roots = [
        p for p in patch_roots
        if p.exists() or p.name.endswith(f'-{patchver}')
    ]
    kernel_patches_group = _collect_group_files(tree, active_patch_roots, references)

    # 3. Active kernel config files, board/subtarget definitions, env/kernel-config
    config_roots = [
        generic / f'config-{patchver}',
        target / 'Makefile',
        target / 'config-default',
        target / f'config-{patchver}',
    ]
    if subtarget_dir is not None and subtarget_dir.is_dir():
        config_roots += [
            subtarget_dir / 'target.mk',
            subtarget_dir / 'config-default',
            subtarget_dir / f'config-{patchver}',
        ]
    env_kconfig = tree / 'env/kernel-config'
    if env_kconfig.exists():
        config_roots.append(env_kconfig)
    kernel_config_files = _collect_group_files(tree, [p for p in config_roots if p.exists() or p.name.endswith(f'-{patchver}') or p.name == 'Makefile'], references)

    # 4. Active kernel modules and selected module/kernel-config package providers
    module_roots = [tree / 'package/kernel/linux']
    board_modules = target / 'modules.mk'
    if board_modules.exists():
        module_roots.append(board_modules)
    module_roots += [tree / source for source in sorted(sources)]
    # A provider's patches, local sources, config includes and symlinked feed
    # contents are inputs, not merely its Makefile or git revision.
    module_roots += [(tree / source).parent for source in sorted(sources)]
    kernel_modules_files = _collect_group_files(tree, module_roots, references)

    # 5. Core build/packaging rules & toolchain recipes (excludes target/<board>/image/)
    rules_roots = [
        tree / 'toolchain',
        tree / 'rules.mk',
        tree / 'package/system/apk',
    ]
    rules_roots += [tree / 'tools' / name for name in (
        'fakeroot', 'tar', 'patch', 'xz', 'zstd', 'libdeflate', 'bison', 'flex')]
    rules_roots += [tree / path for path in (
        'include/download.mk', 'include/depends.mk',
        'include/quilt.mk', 'include/target.mk', 'include/toolchain-build.mk',
        'include/netfilter.mk', 'scripts/kconfig.pl', 'scripts/package-metadata.pl',
        'scripts/metadata.pm', 'scripts/kernel-package.py', 'scripts/kernel-bundle.py',
        'scripts/merge-usr.py',
        'scripts/strip-kmod.sh', 'scripts/strip.sh', 'scripts/gen-dependencies.sh',
        'scripts/apk-migrations.py', 'configs/apk-migrations.json')]
    rules_roots += sorted((tree / 'include').glob('kernel*'))
    rules_roots += sorted((tree / 'include').glob('package*.mk'))
    build_rules_group = _collect_group_files(tree, rules_roots, references)

    # Filter CONFIG_* references to exclude pure image/ISO/GRUB/sequence options
    references |= {name for name in config if name.startswith((
        'CONFIG_KERNEL_', 'CONFIG_GCC_', 'CONFIG_BINUTILS_', 'CONFIG_TOOLCHAIN_'))}
    references |= {name for name in config if name.startswith('CONFIG_TARGET_') and not
        name.startswith(EXCLUDED_TARGET_CONFIG_PREFIXES)}
    references |= {'CONFIG_OPENWRT_KERNEL_UPGRADE', 'CONFIG_PACKAGE_kernel-dev-headers', 'CONFIG_TESTING_KERNEL'}
    references |= {'CONFIG_PACKAGE_' + name for name in wanted}
    references = {name for name in references
                  if name not in EXCLUDED_TARGET_CONFIGS
                  and not name.startswith(EXCLUDED_TARGET_CONFIG_PREFIXES)}
    options = {name: config.get(name, 'n') for name in sorted(references)}

    # Evaluate OpenWrt's real package -> kernel configuration requests. A
    # userspace selection matters only if it changes those kernel requests.
    helper = Path(__file__).with_name('package-metadata.pl')
    override = subprocess.check_output(['perl', str(helper), 'kconfig', str(metadata),
        str(tree / '.config'), patchver], text=True)

    kernel_config_group = {
        **kernel_config_files,
        **{f'config:{k}': v for k, v in options.items()},
        'package-metadata:kconfig': override,
    }
    kernel_modules_group = {
        **kernel_modules_files,
        **{f'pkginfo:{name}': package_info[name] for name in sorted(wanted)},
    }

    # 6. Build environment / explicit kernel arguments
    arguments = [arg for arg in make_args if '=' in arg and not arg.startswith('-')
                 and arg.split('=', 1)[0] not in IGNORED_MAKE_ARGS]
    environment = {name: os.environ[name] for name in (
        'CC', 'HOSTCC', 'HOSTCFLAGS', 'HOST_CFLAGS', 'KCFLAGS', 'KAFLAGS',
        'HOSTLDFLAGS', 'HOST_LDFLAGS', 'LD', 'AR', 'AS', 'CROSS_COMPILE', 'ARCH',
        'LLVM', 'LLVM_IAS', 'KERNEL_CC', 'KERNEL_CROSS', 'KBUILD_BUILD_TIMESTAMP') if name in os.environ}
    defaults = {}
    if not config.get('CONFIG_KERNEL_BUILD_USER', '').strip('"'):
        defaults['user'] = getpass.getuser()
    if not config.get('CONFIG_KERNEL_BUILD_DOMAIN', '').strip('"'):
        defaults['host'] = socket.gethostname()
    build_env_group = {
        'arguments': arguments,
        'environment': environment,
        'build_defaults': defaults,
    }

    group_payloads = {
        'kernel_version': kernel_version_group,
        'kernel_patches': kernel_patches_group,
        'kernel_config': kernel_config_group,
        'kernel_modules': kernel_modules_group,
        'build_rules': build_rules_group,
        'build_env': build_env_group,
    }
    groups = {name: digest(payload) for name, payload in group_payloads.items()}
    entries = {name: _compact_entries(payload) for name, payload in group_payloads.items()}
    source_hash = digest({'schema': SCHEMA, 'patchver': patchver, 'board': board,
                          'subtarget': subtarget, 'groups': groups})

    # 7. Staged cross toolchain & packaging tools
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
    entries['tools'] = _compact_entries(tools)

    # Host system programs are recorded for diagnosis only.
    host = {}
    for name in ('cc', 'ld', 'objcopy', 'bison', 'flex', 'perl', 'python3', 'make', 'bash'):
        path = shutil.which(name)
        if path:
            host['host-' + name] = file_record(Path(path))

    return {
        'schema': SCHEMA,
        'patchver': patchver,
        'board': board,
        'subtarget': subtarget,
        'source': source_hash,
        'tools': digest(tools),
        'host': digest(host),
        'legacy_tools': digest({**tools, **host}),
        'groups': groups,
        'entries': entries,
    }


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


def diff_inputs(previous, current, limit=12):
    """Return (comparable_groups, first_changes) between two fingerprints."""
    if not previous or not current:
        return [], ['missing baseline fingerprint']
    if previous.get('schema') != current.get('schema'):
        return [], [f"fingerprint schema changed ({previous.get('schema')} -> {current.get('schema')})"]
    comparable = []
    changes = []
    prev_groups = previous.get('groups') or {}
    curr_groups = current.get('groups') or {}
    prev_entries = previous.get('entries') or {}
    curr_entries = current.get('entries') or {}

    for group in sorted(set(prev_groups) | set(curr_groups)):
        comparable.append(group)
        if prev_groups.get(group) == curr_groups.get(group):
            continue
        p_map = prev_entries.get(group) or {}
        c_map = curr_entries.get(group) or {}
        found_item = False
        for key in sorted(set(p_map) | set(c_map)):
            if p_map.get(key) != c_map.get(key):
                if key not in p_map:
                    status = 'added'
                elif key not in c_map:
                    status = 'removed'
                else:
                    status = 'changed'
                changes.append(f'{group}: {key} ({status})')
                found_item = True
                if len(changes) >= limit:
                    return comparable, changes
        if not found_item:
            changes.append(f'{group}: digest changed')
            if len(changes) >= limit:
                return comparable, changes

    comparable.append('tools')
    if not same_tools(previous, current):
        p_map = prev_entries.get('tools') or {}
        c_map = curr_entries.get('tools') or {}
        found_item = False
        for key in sorted(set(p_map) | set(c_map)):
            if p_map.get(key) != c_map.get(key):
                status = 'added' if key not in p_map else ('removed' if key not in c_map else 'changed')
                changes.append(f'tools: {key} ({status})')
                found_item = True
                if len(changes) >= limit:
                    return comparable, changes
        if not found_item:
            changes.append('tools: digest changed')

    if not changes and previous.get('source') != current.get('source'):
        changes.append('source: top-level digest changed')
    return comparable, changes
