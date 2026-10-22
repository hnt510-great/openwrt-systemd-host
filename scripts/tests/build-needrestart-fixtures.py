#!/usr/bin/env python3
"""Build tiny target ELF fixtures for needrestart-guest.py outside the tree."""
import argparse
import os
from pathlib import Path
import subprocess


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    tree = Path(__file__).resolve().parents[2]
    toolchain = sorted((tree / 'staging_dir').glob('toolchain-x86_64_gcc-*_glibc'))[-1]
    staging = tree / 'staging_dir/target-x86_64_glibc'
    compiler = toolchain / 'bin/x86_64-openwrt-linux-gcc'
    args.output.mkdir(parents=True, exist_ok=True)
    worker = args.output / 'worker.c'
    library = args.output / 'library.c'
    worker.write_text('''#include <dlfcn.h>
#include <unistd.h>
int main(int argc, char **argv) {
    if (argc != 2 || !dlopen(argv[1], RTLD_NOW)) return 1;
    for (;;) pause();
}
''')
    library.write_text('int needrestart_probe(void) { return VERSION; }\n')
    env = {**os.environ, 'STAGING_DIR': str(staging)}
    subprocess.run([str(compiler), '-O2', '-Wall', '-Wextra', '-Werror', str(worker),
                    '-ldl', '-o', str(args.output / 'dl-worker')], check=True, env=env)
    for version in (1, 2):
        subprocess.run([str(compiler), '-shared', '-fPIC', '-O2', f'-DVERSION={version}',
                        str(library), '-o', str(args.output / f'libprobe-v{version}.so')],
                       check=True, env=env)
    static = args.output / 'flatpak-worker.S'
    static.write_text('.text\n.global _start\n_start:\n mov $34,%eax\n syscall\n jmp _start\n'
                      '.section .note.GNU-stack,"",@progbits\n')
    subprocess.run([str(compiler), '-nostdlib', '-static', '-no-pie',
                    str(static), '-o', str(args.output / 'flatpak-worker')], check=True, env=env)


if __name__ == '__main__':
    main()
