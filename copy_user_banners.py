"""Copy user-provided OS images to frontend/assets/banners/ with clean names."""
import shutil
from pathlib import Path

PROJECT = Path(r"d:\AddingUI\Antigravity - Copy\OneClickVM")
SRC     = PROJECT / "frontend"
DEST    = PROJECT / "frontend" / "assets" / "banners"
DEST.mkdir(parents=True, exist_ok=True)

copies = [
    (SRC / "Alpine_Linux.png",  DEST / "banner_alpine.png"),
    (SRC / "Arch Linux.png",    DEST / "banner_arch.png"),
    (SRC / "NixOS.png",         DEST / "banner_nixos.png"),
    (SRC / "OpenSUSE.jpg",      DEST / "banner_opensuse.png"),
    (SRC / "Linux Mint.png",    DEST / "banner_mint.png"),
]

for src, dst in copies:
    if src.exists():
        shutil.copy2(str(src), str(dst))
        print(f"  OK  {src.name}  →  {dst.name}")
    else:
        print(f"  MISS  {src.name}")

print("Done.")
