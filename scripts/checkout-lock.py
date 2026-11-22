#!/usr/bin/env python3
"""Stable per-checkout exclusive build lock with inheritance verification."""
import argparse
from contextlib import contextmanager
import fcntl
import os
from pathlib import Path
import subprocess
import sys


ENV_FD = 'OPENWRT_CHECKOUT_LOCK_FD'
ENV_ID = 'OPENWRT_CHECKOUT_LOCK_ID'


def checkout_lock_path(tree):
    """Return a lock path outside tmp/ so dirclean cannot remove its inode."""
    root = Path(tree).resolve()
    dotgit = root / '.git'
    if dotgit.is_dir():
        return dotgit / 'openwrt-checkout.lock'
    if dotgit.is_file():
        text = dotgit.read_text().strip()
        if text.startswith('gitdir:'):
            raw = text.split(':', 1)[1].strip()
            gitdir = Path(raw)
            if not gitdir.is_absolute():
                gitdir = (root / gitdir).resolve()
            if gitdir.is_dir():
                return gitdir / 'openwrt-checkout.lock'
    return root / '.openwrt-checkout.lock'


def file_id(path_or_fd):
    st = os.fstat(path_or_fd) if isinstance(path_or_fd, int) else os.stat(path_or_fd)
    return (st.st_dev, st.st_ino)


def inherited_lock_matches(lock_path, lock_fd=None):
    """Return inherited fd if it is valid and refers to lock_path's exact inode."""
    fd = lock_fd
    expected_id = None
    if fd is None:
        raw_fd = os.environ.get(ENV_FD)
        raw_id = os.environ.get(ENV_ID)
        if not raw_fd or not raw_id:
            return None
        try:
            fd = int(raw_fd)
            dev_s, ino_s = raw_id.split(':', 1)
            expected_id = (int(dev_s), int(ino_s))
        except ValueError:
            return None
    try:
        fd_id = file_id(fd)
        path_id = file_id(lock_path)
    except OSError:
        return None
    if fd_id != path_id:
        return None
    if expected_id is not None and fd_id != expected_id:
        return None
    return fd


@contextmanager
def acquire_checkout_lock(tree, lock_fd=None, nonblocking=False, extra_dirs=()):
    """Acquire or verify the exclusive checkout lock (and any shared output locks)."""
    lock_path = checkout_lock_path(tree)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.touch(exist_ok=True)

    if lock_fd is not None:
        if inherited_lock_matches(lock_path, lock_fd=lock_fd) is None:
            raise ValueError('Inherited build lock does not belong to this checkout')
        held_fd = lock_fd
        owned = None
    else:
        reused = inherited_lock_matches(lock_path)
        if reused is not None:
            held_fd = reused
            owned = None
        else:
            owned = lock_path.open('a')
            flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
            try:
                fcntl.flock(owned, flags)
            except BaseException:
                owned.close()
                raise
            held_fd = owned.fileno()

    extra_files = []
    try:
        # Lock any explicit shared output directories in deterministic order.
        root = Path(tree).resolve()
        extra_paths = sorted({
            Path(d).resolve() / '.openwrt-output.lock'
            for d in extra_dirs
            if d and not Path(d).resolve().is_relative_to(root)
        })
        flags = fcntl.LOCK_EX | (fcntl.LOCK_NB if nonblocking else 0)
        for ep in extra_paths:
            ep.parent.mkdir(parents=True, exist_ok=True)
            f = ep.open('a')
            try:
                fcntl.flock(f, flags)
            except BaseException:
                f.close()
                raise
            extra_files.append(f)

        dev, ino = file_id(held_fd)
        yield held_fd, f'{dev}:{ino}', lock_path
    finally:
        for f in reversed(extra_files):
            f.close()
        if owned is not None:
            owned.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--tree', type=Path, required=True)
    parser.add_argument('--extra-dir', action='append', default=[])
    parser.add_argument('--nonblocking', action='store_true')
    parser.add_argument('--sh', help='Run a shell command string via /bin/sh -c')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()

    cmd = args.command
    if cmd and cmd[0] == '--':
        cmd = cmd[1:]
    if args.sh is not None:
        if cmd:
            sys.exit('checkout-lock.py: cannot combine --sh with command arguments')
        exec_cmd = ['/bin/sh', '-c', args.sh]
    else:
        if not cmd:
            sys.exit('checkout-lock.py: missing command')
        exec_cmd = cmd

    with acquire_checkout_lock(args.tree, nonblocking=args.nonblocking, extra_dirs=args.extra_dir) as (fd, ident, _):
        os.set_inheritable(fd, True)
        env = {**os.environ, ENV_FD: str(fd), ENV_ID: ident}
        # Preserve GNU Make jobserver pipe FDs in addition to the checkout lock FD.
        res = subprocess.run(exec_cmd, env=env, close_fds=False)
        sys.exit(res.returncode)


if __name__ == '__main__':
    main()
