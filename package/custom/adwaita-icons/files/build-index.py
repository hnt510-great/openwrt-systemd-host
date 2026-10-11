from pathlib import Path
import sys
root = Path(sys.argv[1])
dirs = []
for size in [16, 22, 24, 32, 48, 64, 96, 256]:
    dirs.extend(sorted((root / "Adwaita" / f"{size}x{size}").iterdir()))
dirs = [p for p in dirs if p.is_dir()]
text = (root / "index.theme.in").read_text().replace("@THEME_DIRS@", ",".join(str(p.relative_to(root / "Adwaita")) for p in dirs))
for p in dirs:
    size = int(p.parent.name.split("x")[0])
    text += f"\n[{p.relative_to(root / 'Adwaita')}]\nSize={size}\nType=Fixed\n"
(root / "index.theme").write_text(text)
