"""Copy generated OS banner images to frontend/assets/banners/"""
import shutil
from pathlib import Path

BRAIN = Path(r"C:\Users\vj937\.gemini\antigravity\brain\00570194-1a8e-40cf-8c0c-f81f1366c6d5")
DEST  = Path(r"d:\AddingUI\Antigravity - Copy\OneClickVM\frontend\assets\banners")
DEST.mkdir(parents=True, exist_ok=True)

copies = [
    ("banner_arch_1777321872260.png",    "banner_arch.png"),
    ("banner_opensuse_1777321887292.png","banner_opensuse.png"),
    ("banner_alpine_1777321902846.png",  "banner_alpine.png"),
    ("banner_mint_1777321912717.png",    "banner_mint.png"),
    ("banner_nixos_1777321927262.png",   "banner_nixos.png"),
]

for src_name, dst_name in copies:
    src = BRAIN / src_name
    dst = DEST / dst_name
    if src.exists():
        shutil.copy2(str(src), str(dst))
        print(f"  ✓ {dst_name}")
    else:
        print(f"  ✗ missing: {src_name}")

print("Done.")
