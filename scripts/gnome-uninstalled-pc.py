#!/usr/bin/env python3
"""Keep local Meson build paths independent of OpenWrt's prefix override.

OpenWrt pkg-config replaces prefix with the target staging prefix. For a
Meson -uninstalled.pc, prefix instead points at the current build directory.
Resolve its references before Cargo queries it, while normal installed
packages continue to use the OpenWrt staging override.
"""
from pathlib import Path
import sys

for path in Path(sys.argv[1]).glob('*-uninstalled.pc'):
    text = path.read_text()
    prefix = next(line.removeprefix('prefix=') for line in text.splitlines()
                  if line.startswith('prefix='))
    if not Path(prefix).is_absolute() or '${' in prefix:
        raise ValueError(f'Unexpected uninstalled prefix in {path}')
    path.write_text(text.replace('${prefix}', prefix))
