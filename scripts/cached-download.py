#!/usr/bin/env python3
"""Coordinate all download backends by the actual shared output filename."""
import fcntl
import hashlib
import os
from pathlib import Path
import subprocess
import sys
import tempfile


def verify(path, expected):
    if expected in ('', 'x', 'skip'):
        return
    digest = hashlib.sha256() if len(expected) == 64 else hashlib.md5()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    if digest.hexdigest() != expected:
        raise ValueError(f'{path}: expected {expected}, got {digest.hexdigest()}')


def main():
    if len(sys.argv) != 5:
        sys.exit(f'Usage: {sys.argv[0]} DESTINATION FILENAME EXPECTED_HASH COMMAND')
    destination, filename, expected, command = sys.argv[1:]
    if '/' in filename or filename in ('', '.', '..'):
        raise ValueError(f'invalid download filename: {filename!r}')
    root = Path(destination).resolve()
    root.mkdir(parents=True, exist_ok=True)
    lockdir = root / '.locks'
    lockdir.mkdir(parents=True, exist_ok=True)
    with (lockdir / filename).open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        archive = root / filename
        if archive.exists():
            verify(archive, expected)
            return
        with tempfile.TemporaryDirectory(dir=root, prefix='.download-') as tmp:
            work = Path(tmp) / 'work'
            work.mkdir()
            env = {
                **os.environ,
                'dl_output': tmp,
                'dl_work': str(work),
                'OPENWRT_DL_LOCKED': f'{root}:{filename}',
            }
            subprocess.run(['bash', '-o', 'pipefail', '-c', command], check=True, env=env)
            candidate = Path(tmp) / filename
            if not candidate.is_file():
                raise ValueError(f'download command did not produce {filename}')
            verify(candidate, expected)
            os.replace(candidate, archive)


if __name__ == '__main__':
    try:
        main()
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        sys.exit(str(error))
