"""
backend/ai_recommendation.py
AI-based resource recommendation engine for VM configuration.
Uses psutil to detect system specs and applies intelligent allocation logic.
"""
from dataclasses import dataclass
from typing import Literal
from .logger import get_logger

logger = get_logger("AIRecommendation")

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False


@dataclass
class SystemSpecs:
    total_ram_mb:   int
    available_ram_mb: int
    total_cores:    int
    physical_cores: int
    disk_free_gb:   int
    disk_total_gb:  int


@dataclass
class VMConfig:
    ram_mb:     int
    cpu_count:  int
    disk_gb:    int
    confidence: Literal["Optimal", "Balanced", "Low"]
    reason:     str


# OS profiles: (min_ram_mb, rec_ram_mb, min_disk_gb, rec_disk_gb)
_OS_PROFILES = {
    "ubuntu":  (2048,  4096,  25, 40),
    "fedora":  (2048,  4096,  25, 40),
    "debian":  (1024,  2048,  20, 30),
    "kali":    (2048,  4096,  30, 50),
    "windows": (4096,  8192,  64, 80),
    "default": (2048,  4096,  25, 40),
}


def get_system_specs() -> SystemSpecs:
    """Detect live system specs via psutil."""
    if not _HAS_PSUTIL:
        # Safe defaults if psutil isn't installed
        return SystemSpecs(
            total_ram_mb    = 8192,
            available_ram_mb= 4096,
            total_cores     = 4,
            physical_cores  = 2,
            disk_free_gb    = 100,
            disk_total_gb   = 500,
        )

    mem   = psutil.virtual_memory()
    disk  = psutil.disk_usage("/") if not _is_windows() else psutil.disk_usage("C:\\")
    cores = psutil.cpu_count(logical=True)
    phys  = psutil.cpu_count(logical=False) or max(1, cores // 2)

    specs = SystemSpecs(
        total_ram_mb     = mem.total     // (1024 * 1024),
        available_ram_mb = mem.available // (1024 * 1024),
        total_cores      = cores,
        physical_cores   = phys,
        disk_free_gb     = disk.free     // (1024 ** 3),
        disk_total_gb    = disk.total    // (1024 ** 3),
    )
    logger.info(f"System detected: {specs}")
    return specs


def recommend_config(os_id: str, specs: SystemSpecs) -> VMConfig:
    """
    Intelligently recommend RAM / CPU / Disk for a VM.

    Algorithm:
    - RAM   : 35% of available RAM, capped at 70% of total, clipped to [min, rec]
    - CPU   : half of physical cores, min 1, max 4
    - Disk  : recommended profile disk size (capped to free space)
    - Confidence: Optimal if available RAM ≥ 2×min, Balanced if ≥ min, Low otherwise
    """
    os_key = _match_os_key(os_id)
    min_ram, rec_ram, min_disk, rec_disk = _OS_PROFILES[os_key]

    # ── RAM ──────────────────────────────────────────────────────────────────
    safe_ceiling = int(specs.total_ram_mb * 0.70)           # never >70% total
    target_ram   = int(specs.available_ram_mb * 0.35)       # 35% of available
    ram_mb       = max(min_ram, min(target_ram, safe_ceiling, rec_ram))

    # ── CPU ──────────────────────────────────────────────────────────────────
    cpu_count = max(1, min(specs.physical_cores // 2, 4))

    # ── Disk ─────────────────────────────────────────────────────────────────
    disk_gb = rec_disk
    if specs.disk_free_gb < rec_disk + 5:           # safety buffer of 5 GB
        disk_gb = max(min_disk, specs.disk_free_gb - 5)

    # ── Confidence ───────────────────────────────────────────────────────────
    if specs.available_ram_mb >= min_ram * 2 and specs.disk_free_gb >= rec_disk + 20:
        confidence = "Optimal"
        reason     = "Your system has plenty of headroom for this VM."
    elif specs.available_ram_mb >= min_ram and specs.disk_free_gb >= min_disk + 5:
        confidence = "Balanced"
        reason     = "Resources are sufficient but leaving limited headroom."
    else:
        confidence = "Low"
        reason     = "System resources are tight. Consider freeing RAM or disk before continuing."

    result = VMConfig(
        ram_mb    = round_to_nearest(ram_mb, 512),   # round to nearest 512 MB
        cpu_count = cpu_count,
        disk_gb   = disk_gb,
        confidence= confidence,
        reason    = reason,
    )
    logger.info(f"Recommendation for '{os_id}': {result}")
    return result


def round_to_nearest(value: int, step: int) -> int:
    return max(step, int(round(value / step) * step))


def _match_os_key(os_id: str) -> str:
    os_id_lower = os_id.lower()
    for key in _OS_PROFILES:
        if key in os_id_lower:
            return key
    return "default"


def _is_windows() -> bool:
    import sys
    return sys.platform.startswith("win")
