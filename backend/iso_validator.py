"""
backend/iso_validator.py
Validates ISO / IMG files before they are admitted to the library.
"""
from pathlib import Path
from .logger import get_logger

logger = get_logger("ISOValidator")

SUPPORTED_EXTENSIONS = {".iso", ".img", ".dmg"}
MIN_SIZE_MB = 1      # files smaller than this are rejected
MAX_SIZE_GB = 100    # warn-only (not rejected) above this threshold


def validate_iso_file(file_path: str) -> tuple:
    """
    Returns (ok: bool, message: str).
    All failure paths return (False, reason).
    """
    path = Path(file_path)

    if not path.exists():
        return False, f"File does not exist: {file_path}"
    if not path.is_file():
        return False, f"Path is not a regular file: {file_path}"

    ext = path.suffix.lower()
    if ext not in SUPPORTED_EXTENSIONS:
        return False, (
            f"Unsupported file type '{ext}'. "
            f"Accepted: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    try:
        size_bytes = path.stat().st_size
    except Exception as e:
        return False, f"Cannot stat file: {e}"

    size_mb = size_bytes / (1024 * 1024)
    if size_mb < MIN_SIZE_MB:
        return False, f"File too small ({size_mb:.1f} MB). Minimum accepted size: {MIN_SIZE_MB} MB."

    # Verify readability (read first 16 bytes)
    try:
        with open(path, "rb") as fh:
            header = fh.read(16)
        if len(header) < 4:
            return False, "File appears empty or unreadable."
    except PermissionError:
        return False, "Permission denied — cannot open the file."
    except Exception as e:
        return False, f"Cannot open file: {e}"

    return True, "OK"


def guess_category(name: str) -> str:
    n = name.lower()
    linux_kws   = ("ubuntu", "fedora", "debian", "arch", "mint", "centos",
                   "rhel", "opensuse", "manjaro", "void", "nixos", "gentoo")
    windows_kws = ("windows", "win10", "win11", "winserver", "server2")
    security_kws= ("kali", "parrot", "tails", "blackarch", "commando")
    utility_kws = ("hirens", "gparted", "clonezilla", "sysrescue", "dban",
                   "grml", "memtest", "systemrescue")

    if any(k in n for k in security_kws): return "Security"
    if any(k in n for k in linux_kws):   return "Linux"
    if any(k in n for k in windows_kws): return "Windows"
    if any(k in n for k in utility_kws): return "Utility"
    return "Custom"


def guess_vendor(name: str) -> str:
    n = name.lower()
    VENDORS = {
        "ubuntu": "Canonical",       "fedora": "Red Hat",
        "debian": "Debian Project",  "kali": "Offensive Security",
        "arch":   "Arch Linux",      "mint": "Linux Mint",
        "centos": "CentOS",          "rhel": "Red Hat",
        "windows":"Microsoft",       "opensuse": "openSUSE",
        "parrot": "Parrot Security", "manjaro": "Manjaro Linux",
        "tails":  "Tails Project",   "void": "Void Linux",
    }
    for key, vendor in VENDORS.items():
        if key in n:
            return vendor
    return "Unknown"


def format_size(size_bytes: int) -> str:
    if size_bytes >= 1024 ** 3:
        return f"{size_bytes / 1024**3:.2f} GB"
    if size_bytes >= 1024 ** 2:
        return f"{size_bytes / 1024**2:.0f} MB"
    return f"{size_bytes / 1024:.0f} KB"
