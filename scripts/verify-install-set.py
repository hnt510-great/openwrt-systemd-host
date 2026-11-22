#!/usr/bin/env python3
"""Verify that every expected .install manifest exists before assembling rootfs/ISO."""
import argparse
from pathlib import Path
import sys


def parse_selected_y(config_path):
    selected = set()
    for line in Path(config_path).read_text().splitlines():
        if line.startswith('CONFIG_PACKAGE_') and line.endswith('=y'):
            selected.add(line[len('CONFIG_PACKAGE_'):-2])
    return selected


def recipes_with_install_output(packageinfo_path, selected_y):
    """Return set of (recipe_basename, variant) expected to emit a .install manifest."""
    expected = set()
    cur_recipe = None
    cur_pkg = None
    cur_variant = None
    cur_build_only = False

    def flush_pkg():
        if cur_recipe and cur_pkg and not cur_build_only and cur_pkg in selected_y:
            expected.add((cur_recipe, cur_variant or 'default'))

    for line in Path(packageinfo_path).read_text().splitlines():
        if line.startswith('Source-Makefile:'):
            flush_pkg()
            makefile = line.split(':', 1)[1].strip()
            # e.g. package/libs/zlib/Makefile -> zlib
            cur_recipe = Path(makefile).parent.name
            cur_pkg = None
            cur_variant = None
            cur_build_only = False
        elif line.startswith('Package:'):
            flush_pkg()
            cur_pkg = line.split(':', 1)[1].strip()
            cur_variant = None
            cur_build_only = False
        elif line.startswith('Build-Variant:'):
            cur_variant = line.split(':', 1)[1].strip() or None
        elif line.startswith('Build-Only:'):
            val = line.split(':', 1)[1].strip()
            cur_build_only = val not in ('', '0', 'n', 'no')
    flush_pkg()
    return expected


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packageinfo', type=Path)
    parser.add_argument('--config', type=Path)
    parser.add_argument('--install-files', nargs='*', default=[])
    parser.add_argument('--output-pkgs', type=Path, help='Write package names from manifests')
    args = parser.parse_args()

    expected_pairs = None
    if args.packageinfo and args.config:
        selected_y = parse_selected_y(args.config)
        expected_pairs = recipes_with_install_output(args.packageinfo, selected_y)

    missing = []
    packages = []
    for raw in args.install_files:
        path = Path(raw)
        if not path.is_file():
            flags_path = Path(str(path) + '.flags')
            if expected_pairs is not None:
                # Filename format: <recipe>.<variant>.install
                stem = path.name.removesuffix('.install')
                if '.' in stem:
                    recipe, variant = stem.rsplit('.', 1)
                else:
                    recipe, variant = stem, 'default'
                if (recipe, variant) not in expected_pairs:
                    # Legitimate host-only, Build-Only, or =m-only recipe/variant.
                    continue
                if flags_path.is_file():
                    # Producer ran prepare-package-install and legitimately had no
                    # Package/*/install section (e.g. argp-standalone, golang-bootstrap).
                    continue
            missing.append(str(path))
            continue
        for line in path.read_text().splitlines():
            pkg = line.strip()
            if pkg:
                packages.append(pkg)

    if missing:
        sys.stderr.write(
            'ERROR: missing expected package .install manifest(s) before rootfs assembly:\n'
            + ''.join(f'  {m}\n' for m in sorted(missing))
        )
        return 1

    if args.output_pkgs:
        args.output_pkgs.write_text('\n'.join(packages) + ('\n' if packages else ''))
    return 0


if __name__ == '__main__':
    sys.exit(main())
