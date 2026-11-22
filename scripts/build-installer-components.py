#!/usr/bin/env python3
"""Assemble clean base rootfs and signed offline APK repo for component installer ISO."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

INSTALLING_RE = re.compile(r'^\(\s*\d+/\d+\)\s+Installing\s+(\S+)\s+\(([^)]+)\)')


def sha256_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def run(args, cwd=None, env=None, capture=False):
    cmd = [str(x) for x in args]
    if capture:
        res = subprocess.run(cmd, cwd=cwd, env=env, text=True,
                             stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if res.returncode != 0:
            raise RuntimeError(
                f'Command failed ({res.returncode}): {" ".join(cmd)}\n'
                f'stdout:\n{res.stdout[-2000:]}\nstderr:\n{res.stderr[-2000:]}'
            )
        return res.stdout
    subprocess.run(cmd, cwd=cwd, env=env, check=True)
    return ''


def read_installed_db(root):
    for rel in ('lib/apk/db/installed', 'usr/lib/apk/db/installed'):
        db = root / rel
        if db.exists():
            pkgs = {}
            for block in db.read_text().strip().split('\n\n'):
                name = version = None
                for line in block.splitlines():
                    if line.startswith('P:'):
                        name = line[2:]
                    elif line.startswith('V:'):
                        version = line[2:]
                if name:
                    pkgs[name] = version or ''
            return pkgs
    raise RuntimeError(f'APK installed database missing under {root}')


def make_sim_root(base_root, dest):
    for rel in ('lib/apk/db/installed', 'etc/apk/arch', 'etc/apk/world'):
        src = base_root / rel
        if not src.exists() and rel.startswith('lib/'):
            src = base_root / ('usr/' + rel)
        if src.exists():
            dst = dest / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dst)
    (dest / 'lib/apk/db').mkdir(parents=True, exist_ok=True)
    (dest / 'tmp').mkdir(parents=True, exist_ok=True)


def simulate_add(apk_bin, sim_root, keys_dir, repo_index, packages):
    if not packages:
        return []
    cmd = [
        apk_bin, '--root', sim_root, '--keys-dir', Path(keys_dir).resolve(),
        '--no-logfile', '--no-network', '--no-cache',
        '--repositories-file', '/dev/null',
        '--repository', f'file://{Path(repo_index).resolve()}',
        '--simulate', 'add', *packages,
    ]
    out = run(cmd, capture=True)
    installed = []
    for line in out.splitlines():
        m = INSTALLING_RE.match(line.strip())
        if m:
            installed.append((m.group(1), m.group(2)))
    return installed


def verify_signed_index(apk_bin, keys_dir, repo_index):
    run([apk_bin, 'verify', '--keys-dir', Path(keys_dir).resolve(), Path(repo_index).resolve()],
        capture=True)


def query_available_packages(apk_bin, keys_dir, repo_index, arch):
    verify_signed_index(apk_bin, keys_dir, repo_index)
    with tempfile.TemporaryDirectory(prefix='installer-avail-') as tmp:
        root = Path(tmp)
        (root / 'lib/apk/db').mkdir(parents=True)
        (root / 'etc/apk').mkdir(parents=True)
        (root / 'tmp').mkdir(parents=True)
        (root / 'lib/apk/db/installed').write_text('')
        (root / 'etc/apk/arch').write_text(f'{arch}\n')
        (root / 'etc/apk/world').write_text('')
        out = run([
            apk_bin, '--root', root, '--keys-dir', Path(keys_dir).resolve(),
            '--no-logfile', '--no-network', '--no-cache',
            '--repositories-file', '/dev/null',
            '--repository', f'file://{Path(repo_index).resolve()}',
            'query', '--available', '--fields', 'name,provides', '--format', 'json', '*',
        ], capture=True)
    entries = json.loads(out) if out.strip() else []
    available = set()
    for entry in entries:
        name = entry.get('name')
        if name:
            available.add(str(name))
        for prov in entry.get('provides') or []:
            available.add(str(prov).split('=', 1)[0])
    return available


def check_catalog_availability(available, base_cfg, components):
    missing_req_base = sorted({
        pkg for pkg in base_cfg.get('required_packages', [])
        if pkg not in available
    })
    missing_base = sorted({
        pkg for pkg in base_cfg.get('packages', [])
        if pkg not in available and pkg not in missing_req_base
    })
    missing_components = {}
    for comp in components:
        req = list(comp.get('packages', []))
        for cond in comp.get('conditional_packages', []):
            req.extend(cond.get('packages', []))
        missing = sorted({pkg for pkg in req if pkg not in available})
        if missing:
            missing_components[comp['id']] = missing
    if missing_req_base or missing_base or missing_components:
        details = []
        if missing_req_base:
            details.append(f"required base ({len(missing_req_base)}): {', '.join(missing_req_base)}")
        if missing_base:
            details.append(f"base ({len(missing_base)}): {', '.join(missing_base[:20])}" +
                           (' ...' if len(missing_base) > 20 else ''))
        for cid, pkgs in missing_components.items():
            details.append(f"component '{cid}' ({len(pkgs)}): {', '.join(pkgs)}")
        raise RuntimeError(
            'Installer ISO requires the complete desktop-profile base and component package set '
            '(configs/x86-64-systemd-desktop.config with CONFIG_SIGNED_PACKAGES=y), '
            'but packages are missing from the build repository:\n  - ' + '\n  - '.join(details)
        )


def all_component_packages(components):
    pkgs = []
    seen = set()
    for comp in components:
        for p in comp.get('packages', []):
            if p not in seen:
                seen.add(p)
                pkgs.append(p)
        for cond in comp.get('conditional_packages', []):
            for p in cond.get('packages', []):
                if p not in seen:
                    seen.add(p)
                    pkgs.append(p)
    return pkgs


def resolve_packages_for_selection(selected, components):
    sel = set(selected)
    pkgs = []
    seen = set()
    for comp in components:
        if comp['id'] not in sel:
            continue
        for p in comp.get('packages', []):
            if p not in seen:
                seen.add(p)
                pkgs.append(p)
        for cond in comp.get('conditional_packages', []):
            if all(req in sel for req in cond.get('when_all', [])):
                for p in cond.get('packages', []):
                    if p not in seen:
                        seen.add(p)
                        pkgs.append(p)
    return pkgs


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', required=True, type=Path)
    p.add_argument('--apk', required=True, type=Path)
    p.add_argument('--fakeroot', type=Path)
    p.add_argument('--package-dir', required=True, type=Path)
    p.add_argument('--keys-dir', required=True, type=Path)
    p.add_argument('--public-key', required=True, type=Path)
    p.add_argument('--sign-key', required=True, type=Path)
    p.add_argument('--arch', default='x86_64')
    p.add_argument('--version', required=True)
    p.add_argument('--kernel-release', required=True)
    p.add_argument('--base-files-version', required=True)
    p.add_argument('--libc-version', required=True)
    p.add_argument('--kernel-version', required=True)
    p.add_argument('--package-install-list', type=Path)
    p.add_argument('--base-root-out', required=True, type=Path)
    p.add_argument('--components-out', required=True, type=Path)
    a = p.parse_args()
    a.apk = a.apk.resolve()
    if a.fakeroot:
        a.fakeroot = a.fakeroot.resolve()
    a.package_dir = a.package_dir.resolve()
    a.keys_dir = a.keys_dir.resolve()
    a.public_key = a.public_key.resolve()
    a.sign_key = a.sign_key.resolve()

    if not a.public_key.is_file() or a.public_key.stat().st_size == 0:
        raise FileNotFoundError(f'Missing or empty APK signing public key: {a.public_key}')
    if not a.sign_key.is_file() or a.sign_key.stat().st_size == 0:
        raise FileNotFoundError(
            f'Missing or empty APK signing private key: {a.sign_key} '
            '(CONFIG_SIGNED_PACKAGES=y is required to build installer ISO)'
        )

    cfg = json.loads(a.config.read_text())
    if cfg.get('format_version') != 2:
        raise ValueError(f"Unsupported installer-components config format_version: {cfg.get('format_version')}")

    base_cfg = cfg['base']
    components = cfg['components']
    repo_index = a.package_dir / 'packages.adb'
    if not repo_index.exists():
        raise FileNotFoundError(f'Missing merged package index: {repo_index}')

    available = query_available_packages(a.apk, a.keys_dir, repo_index, a.arch)
    check_catalog_availability(available, base_cfg, components)

    pinned = {
        'base-files': f'base-files={a.base_files_version}',
        'libc': f'libc={a.libc_version}',
        'kernel': f'kernel={a.kernel_version}',
    }
    if a.package_install_list and a.package_install_list.exists():
        for token in a.package_install_list.read_text().split():
            if token.startswith('linux-image-openwrt='):
                pinned['linux-image-openwrt'] = token
                break

    base_pkgs = []
    seen = set()
    for pkg in base_cfg['packages']:
        spec = pinned.get(pkg, pkg)
        if spec not in seen:
            seen.add(spec)
            base_pkgs.append(spec)
    for key, spec in pinned.items():
        if spec not in seen:
            seen.add(spec)
            base_pkgs.append(spec)

    if base_cfg.get('include_configured_kmods') and a.package_install_list and a.package_install_list.exists():
        for token in a.package_install_list.read_text().split():
            name = token.split('=', 1)[0]
            if name.startswith('kmod-') and name not in seen:
                seen.add(name)
                base_pkgs.append(name)

    if a.base_root_out.exists():
        shutil.rmtree(a.base_root_out)
    (a.base_root_out / 'tmp').mkdir(parents=True)

    add_cmd = []
    if a.fakeroot:
        add_cmd.append(a.fakeroot)
    add_cmd += [
        a.apk, '--root', a.base_root_out, '--keys-dir', a.keys_dir.resolve(),
        '--no-logfile', '--preserve-env', 'add', '--no-cache', '--initdb',
        '--no-scripts', '--arch', a.arch, '--repositories-file', '/dev/null',
        '--repository', f'file://{repo_index.resolve()}',
    ]
    add_cmd += base_pkgs

    env = dict(os.environ, IPKG_INSTROOT=str(a.base_root_out))
    run(add_cmd, env=env)

    # Keep rolling kernel upgrades working on the installed device while still
    # pinning the exact same-build kernel generation during ISO assembly.
    if 'linux-image-openwrt' in pinned:
        world = a.base_root_out / 'etc/apk/world'
        if world.is_file():
            lines = [
                'linux-image-openwrt' if line.startswith('linux-image-openwrt=') else line
                for line in world.read_text().splitlines()
            ]
            world.write_text('\n'.join(lines) + ('\n' if lines else ''))

    run_dir = a.base_root_out / 'run'
    if run_dir.exists():
        for child in run_dir.iterdir():
            if child.name == '.keep':
                continue
            if child.is_dir() and not child.is_symlink():
                shutil.rmtree(child)
            else:
                child.unlink()

    base_installed = read_installed_db(a.base_root_out)
    missing_req = [p for p in base_cfg.get('required_packages', []) if p not in base_installed]
    if missing_req:
        raise RuntimeError(f'Base rootfs missing required packages: {", ".join(missing_req)}')
    leaked = [p for p in base_cfg.get('forbidden_packages', []) if p in base_installed]
    if leaked:
        raise RuntimeError(f'Component packages leaked into base rootfs: {", ".join(leaked)}')

    base_digest = hashlib.sha256(
        ('\n'.join(f'{k}={base_installed[k]}' for k in sorted(base_installed)) + '\n').encode()
    ).hexdigest()

    if a.components_out.exists():
        shutil.rmtree(a.components_out)
    repo_dir = a.components_out / 'repo'
    keys_dir = a.components_out / 'keys'
    repo_dir.mkdir(parents=True)
    keys_dir.mkdir(parents=True)

    pub_dest = keys_dir / a.public_key.name
    shutil.copyfile(a.public_key, pub_dest)

    base_keys_dir = a.base_root_out / 'etc/apk/keys'
    if not base_keys_dir.is_dir():
        raise RuntimeError(f'Base rootfs missing trusted APK keys directory: {base_keys_dir}')
    pub_sha = sha256_file(a.public_key)
    if not any(p.is_file() and p.suffix == '.pem' and sha256_file(p) == pub_sha for p in base_keys_dir.iterdir()):
        raise RuntimeError(
            f'Base rootfs {base_keys_dir} does not contain the build signing public key {a.public_key.name}'
        )

    with tempfile.TemporaryDirectory(prefix='installer-comp-sim-') as tmp:
        sim_root = Path(tmp) / 'sim'
        make_sim_root(a.base_root_out, sim_root)

        union_pkgs = all_component_packages(components)
        needed = simulate_add(a.apk, sim_root, a.keys_dir, repo_index, union_pkgs)

        # Copy exact APKs into offline repo and record checksums.
        repo_files = {}
        for name, version in needed:
            filename = f'{name}-{version}.apk'
            src = a.package_dir / filename
            if not src.exists():
                raise FileNotFoundError(f'Component APK missing from build package dir: {src}')
            dst = repo_dir / filename
            shutil.copyfile(src.resolve(), dst)
            repo_files[filename] = {
                'name': name,
                'version': version,
                'size': dst.stat().st_size,
                'sha256': sha256_file(dst),
            }

        # Build signed offline APK index (individual APKs may not be signed unless SIGN_EACH_PACKAGE=y).
        offline_index = repo_dir / 'packages.adb'
        mkndx_cmd = [
            a.apk, 'mkndx', '--root', a.keys_dir.resolve(), '--keys-dir', a.keys_dir.resolve(),
            '--allow-untrusted', '--sign', a.sign_key.resolve(),
            '--output', offline_index.resolve(), *sorted(repo_files.keys()),
        ]
        run(mkndx_cmd, cwd=repo_dir)

        # Verify standalone offline repo strictly against the base rootfs trusted keys (/rom/etc/apk/keys).
        verify_signed_index(a.apk, base_keys_dir, offline_index)
        verified_union = simulate_add(a.apk, sim_root, base_keys_dir, offline_index, union_pkgs)
        if not verified_union:
            raise RuntimeError('Offline repository simulation returned no packages for full component set')

        # Sanity-check key combinations against forbidden_when_unselected.
        comp_by_id = {c['id']: c for c in components}
        checks = [
            (['gnome'], ['audio', 'ime', 'rdp', 'sunshine', 'flatpak', 'appimage', 'virtualization', 'containers']),
            (['virtualization', 'containers'], ['gnome', 'audio', 'ime', 'rdp', 'sunshine', 'flatpak', 'appimage']),
        ]
        for selected_ids, unselected_ids in checks:
            sel_pkgs = resolve_packages_for_selection(selected_ids, components)
            solved = {name for name, _ in simulate_add(a.apk, sim_root, base_keys_dir, offline_index, sel_pkgs)}
            for uid in unselected_ids:
                for forb in comp_by_id[uid].get('forbidden_when_unselected', []):
                    if forb in solved:
                        raise RuntimeError(
                            f'Selection {selected_ids} unexpectedly pulled forbidden package {forb} '
                            f'from unselected component {uid}'
                        )

    # Guarantee no private keys entered components_out.
    for path in a.components_out.rglob('*'):
        if path.is_file() and 'private' in path.name.lower():
            raise RuntimeError(f'Refusing to ship private key material in ISO: {path}')

    catalog_out = {
        'format_version': 2,
        'version': a.version,
        'kernel_release': a.kernel_release,
        'arch': a.arch,
        'base_package_count': len(base_installed),
        'base_packages_sha256': base_digest,
        'repo_index_sha256': sha256_file(offline_index),
        'components': [
            {
                'id': c['id'],
                'label': c['label'],
                'description': c['description'],
                'depends': c.get('depends', []),
                'default': bool(c.get('default', True)),
                'packages': c.get('packages', []),
                'conditional_packages': c.get('conditional_packages', []),
            }
            for c in components
        ],
        'repo_files': repo_files,
    }
    (a.components_out / 'components.json').write_text(json.dumps(catalog_out, indent=2) + '\n')


if __name__ == '__main__':
    main()
