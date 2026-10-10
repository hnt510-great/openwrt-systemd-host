#!/usr/bin/env python3
"""Normalize an OpenWrt APK payload without following image symlinks."""
import argparse
import filecmp
import os
from pathlib import Path
import posixpath

PREFIXES = {"/bin": "/usr/bin", "/sbin": "/usr/sbin", "/lib": "/usr/lib"}
# These applets otherwise overlap standalone tools after /usr is merged.
ALTERNATIVE_COMMANDS = {"dmesg", "mount", "umount", "passwd", "ping", "ping6",
                        "mkswap", "swapon", "swapoff", "reboot", "halt", "poweroff"}


def canonical(path):
    path = posixpath.normpath(path)
    for old, new in PREFIXES.items():
        if path == old or path.startswith(old + "/"):
            return new + path[len(old):]
    return path


def entries(root):
    for directory, dirs, files in os.walk(root, followlinks=False):
        for name in dirs[:] + files:
            p = Path(directory) / name
            if p.is_symlink() or not p.is_dir():
                yield p
            if p.is_symlink() and name in dirs:
                dirs.remove(name)


def safe_parent(root, destination):
    """Reject image symlinks before any host-side filesystem mutation."""
    current = root
    for component in destination.parent.relative_to(root).parts:
        current /= component
        if current.is_symlink():
            raise ValueError(f"symlink payload parent: {current.relative_to(root)}")
        current.mkdir(exist_ok=True)


def normalize(root, package=None, aliases=False):
    root = Path(root)
    if root.is_symlink():
        raise ValueError("payload root must not be a symlink")
    alternatives = []
    renames = {}
    for source in sorted(entries(root), key=lambda p: str(p)):
        old = "/" + source.relative_to(root).as_posix()
        new = canonical(old)
        target = None
        if source.is_symlink():
            raw = os.readlink(source)
            resolved = posixpath.normpath(posixpath.join(posixpath.dirname(old), raw))
            target = canonical(resolved)
            if target == new:
                source.unlink()  # compatibility alias collapses onto its own target
                continue
        if package and posixpath.dirname(new) in ("/usr/bin", "/usr/sbin"):
            command = posixpath.basename(new)
            if command in ALTERNATIVE_COMMANDS:
                if target == "/usr/bin/busybox":
                    alternatives.append(f"100:{new}:/usr/bin/busybox")
                    source.unlink()
                    continue
                if package != "busybox":
                    replacement = posixpath.join(posixpath.dirname(new),
                                                 f"openwrt-{package}-{command}")
                    alternatives.append(f"200:{new}:{replacement}")
                    renames[new] = replacement
                    new = replacement
        destination = root / new.lstrip("/")
        if source == destination and target is None:
            continue
        safe_parent(root, destination)
        if target is not None:
            # Absolute links stay absolute; relative links retain root-relative meaning.
            rewritten = target if raw.startswith("/") else posixpath.relpath(target, posixpath.dirname(new))
            if destination != source and os.path.lexists(destination):
                if not destination.is_symlink() or os.readlink(destination) != rewritten:
                    raise ValueError(f"conflicting payload paths: {old} and {new}")
                source.unlink()
            else:
                source.unlink()
                destination.symlink_to(rewritten)
        elif os.path.lexists(destination):
            if destination.is_symlink() or not filecmp.cmp(source, destination, shallow=False) or source.stat().st_mode != destination.stat().st_mode:
                raise ValueError(f"conflicting payload paths: {old} and {new}")
            source.unlink()
        else:
            source.rename(destination)
    for old in PREFIXES:
        directory = root / old.lstrip("/")
        if directory.is_dir() and not directory.is_symlink():
            for current, dirs, files in os.walk(directory, topdown=False):
                Path(current).rmdir()
        if aliases:
            expected = PREFIXES[old].lstrip("/")
            if os.path.lexists(directory):
                if not directory.is_symlink() or os.readlink(directory) != expected:
                    raise ValueError(f"invalid legacy directory alias: {old}")
            else:
                directory.symlink_to(expected)
    metadata = root / "usr/lib/apk/packages"
    if os.path.lexists(metadata) or alternatives:
        safe_parent(root, metadata / ".metadata")
    if alternatives:
        metadata.mkdir(parents=True, exist_ok=True)
    if metadata.is_dir():
        for p in metadata.iterdir():
            if p.suffix in (".conffiles", ".conffiles_static", ".alternatives"):
                content = p.read_text()
                if p.suffix == ".alternatives":
                    content = " ".join(":".join(canonical(v) if v.startswith("/") else v
                                                for v in item.split(":")) for item in content.split()) + "\n"
                else:
                    lines = []
                    for line in content.splitlines():
                        fields = line.split(maxsplit=1)
                        if fields:
                            mapped = canonical(fields[0])
                            fields[0] = renames.get(mapped, mapped)
                        lines.append(" ".join(fields))
                    content = "\n".join(lines) + "\n"
                p.write_text(content)
        if alternatives:
            p = metadata / f"{package}.alternatives"
            existing = p.read_text().split() if p.exists() else []
            p.write_text(" ".join(sorted(set(existing + alternatives))) + "\n")
        if package:
            lists = list(metadata.glob(f"{package}*.list"))
            if len(lists) == 1:
                lists[0].write_text("\n".join(sorted("/" + p.relative_to(root).as_posix()
                                                       for p in entries(root))) + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    parser.add_argument("--package")
    parser.add_argument("--aliases", action="store_true")
    args = parser.parse_args()
    try:
        normalize(args.root, args.package, args.aliases)
    except (OSError, ValueError) as error:
        parser.exit(1, f"merge-usr: {error}\n")
