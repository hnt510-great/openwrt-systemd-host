#!/usr/bin/env python3
"""Audit an extracted target rootfs without loading target libraries on the host."""
import argparse
import json
from pathlib import Path, PurePosixPath
import re
import subprocess


def rooted_file(root, path):
    """Resolve absolute target symlinks inside root, never against the host /lib."""
    parts = list(PurePosixPath(path).parts)
    if parts and parts[0] == "/":
        parts.pop(0)
    resolved = []
    for _ in range(128):
        if not parts:
            return root.joinpath(*resolved)
        part = parts.pop(0)
        if part in ("", "."):
            continue
        if part == "..":
            if not resolved:
                raise RuntimeError(f"Target path escapes root: {path}")
            resolved.pop()
            continue
        candidate = root.joinpath(*resolved, part)
        if candidate.is_symlink():
            target = PurePosixPath(candidate.readlink().as_posix())
            if target.is_absolute():
                resolved = []
                parts = list(target.parts[1:]) + parts
            else:
                parts = list(target.parts) + parts
        else:
            resolved.append(part)
    raise RuntimeError(f"Too many target symlinks: {path}")


def readelf(path, *args):
    return subprocess.check_output(["readelf", *args, str(path)], text=True)


def audit(root):
    private = root / "usr/lib/firefox-esr"
    assert private.is_dir(), "Firefox payload missing"
    roots = [p for p in private.rglob("*") if p.is_file() and p.open("rb").read(4) == b"\x7fELF"]
    checked = set()
    queue = list(roots)
    while queue:
        path = queue.pop()
        if path in checked:
            continue
        checked.add(path)
        assert "Advanced Micro Devices X86-64" in readelf(path, "-h"), path
        for name in re.findall(r"\(NEEDED\).*\[(.*?)\]", readelf(path, "-d")):
            candidates = [path.parent / name, private / name]
            candidates += [root / directory / name for directory in ["lib", "usr/lib", "lib64", "usr/lib64"]]
            library = None
            for candidate in candidates:
                candidate = rooted_file(root, "/" + candidate.relative_to(root).as_posix())
                if candidate.is_file():
                    library = candidate
                    break
            assert library, f"{path.relative_to(root)} needs missing {name}"
            queue.append(library)
    definitions = set()
    undefined = {}
    for path in checked:
        lines = readelf(path, "--dyn-syms", "--wide").splitlines()
        for line in lines:
            fields = line.split()
            if len(fields) < 8 or not fields[0].endswith(":"):
                continue
            name = fields[7].split("@", 1)[0]
            if fields[6] != "UND":
                definitions.add(name)
            elif fields[4] == "GLOBAL" and path in roots:
                undefined.setdefault(name, set()).add(str(path.relative_to(root)))
    # glibc's dynamic loader supplies symbols even when not listed in DT_NEEDED.
    loader = rooted_file(root, "/lib64/ld-linux-x86-64.so.2")
    for line in readelf(loader, "--dyn-syms", "--wide").splitlines():
        fields = line.split()
        if len(fields) >= 8 and fields[6] != "UND":
            definitions.add(fields[7].split("@", 1)[0])
    missing = {name: sorted(paths) for name, paths in undefined.items() if name not in definitions}
    assert not missing, json.dumps(missing, indent=2)
    for name in ["libnss3.so", "libnspr4.so", "libmozsqlite3.so"]:
        assert (private / name).is_file(), f"Missing private {name}"
        assert not (root / "usr/lib" / name).exists(), f"Bundled {name} escaped its private directory"
    return {"browser_elf_files": len(roots), "dependency_elf_files": len(checked),
            "missing_libraries": [], "missing_symbols": [], "private_libraries": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", type=Path)
    args = parser.parse_args()
    print(json.dumps(audit(args.root.absolute()), indent=2))
