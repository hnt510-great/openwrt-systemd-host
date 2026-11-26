"""Read literal package versions for host-side build artifact tests."""
from pathlib import Path
import re


def recipe_version(makefile: Path) -> str:
    match = re.search(r'^PKG_VERSION:=(.+)$', makefile.read_text(), re.M)
    if not match:
        raise ValueError(f'PKG_VERSION missing in {makefile}')
    return match.group(1).strip()
