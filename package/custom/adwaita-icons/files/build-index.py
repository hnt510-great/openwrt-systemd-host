from pathlib import Path
import sys
root = Path(sys.argv[1])
dirs = []
for size in [16, 22, 24, 32, 48, 64, 96, 256]:
    dirs.extend(sorted((root / "Adwaita" / f"{size}x{size}").iterdir()))
for name in ["scalable", "scalable-up-to-32"]:
    dirs.extend(sorted((root / "Adwaita" / name).iterdir()))
dirs = [p for p in dirs if p.is_dir()]
text = (root / "index.theme.in").read_text().replace("@THEME_DIRS@", ",".join(str(p.relative_to(root / "Adwaita")) for p in dirs))
for p in dirs:
    section = f"\n[{p.relative_to(root / 'Adwaita')}]\n"
    if p.parent.name.startswith("scalable"):
        maximum = 32 if p.parent.name.endswith("32") else 512
        text += section + f"Size=16\nType=Scalable\nMinSize=8\nMaxSize={maximum}\n"
    else:
        size = int(p.parent.name.split("x")[0])
        text += section + f"Size={size}\nType=Fixed\n"
(root / "index.theme").write_text(text)
