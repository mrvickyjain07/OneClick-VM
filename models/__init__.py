"""
models/__init__.py
State definitions and template data models.

VMState  — authoritative state from VirtualBox (sync engine uses this)
VMStatus — legacy status kept for backward compatibility with MachinesDB
"""
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class TemplateState(str, Enum):
    IDLE        = "idle"
    DOWNLOADING = "downloading"
    DOWNLOADED  = "downloaded"
    INSTALLING  = "installing"
    READY       = "ready"


class VMStatus(str, Enum):
    """Legacy status enum — kept for MachinesDB backward compatibility."""
    STOPPED = "stopped"
    RUNNING = "running"
    UNKNOWN = "unknown"


class VMState(str, Enum):
    """
    Authoritative VM state as seen by the VirtualBox sync engine.

    RUNNING  — VM is actively running in VirtualBox
    STOPPED  — VM is registered and stopped
    MISSING  — VM is in our DB but NOT found in VirtualBox registry
    ERROR    — VM exists but is in an error / inaccessible state
    UNKNOWN  — State has not yet been determined (initial/transient)
    """
    RUNNING = "running"
    STOPPED = "stopped"
    MISSING = "missing"    # in DB but absent from VBox
    ERROR   = "error"      # VBox returned an error for this VM
    UNKNOWN = "unknown"    # not yet polled


@dataclass
class OSTemplate:
    os_id:       str
    os_name:     str
    version:     str
    description: str
    tags:        list
    iso_url:     str
    iso_filename:str
    os_type_id:  str    # VirtualBox OS type
    ram_mb:      int = 4096
    cpu_count:   int = 2
    disk_gb:     int = 30
    state:       TemplateState = TemplateState.IDLE
    progress:    int = 0


@dataclass
class VMRecord:
    """
    Represents one installed VM entry in the application database.

    uuid is the VirtualBox machine UUID (primary identifier).
    vm_name is kept for display and backward compatibility.
    state reflects the latest sync from VirtualBox (VMState enum).
    """
    vm_name:    str
    os_id:      str
    os_name:    str
    created_at: str
    iso_path:   str      = ""
    status:     VMStatus = VMStatus.STOPPED  # legacy — used by MachinesDB
    state:      VMState  = VMState.UNKNOWN   # authoritative — used by sync engine
    ram_mb:     int      = 4096
    cpu_count:  int      = 2
    disk_gb:    int      = 30
    uuid:       str      = ""               # VirtualBox machine UUID


# ── Catalog ──────────────────────────────────────────────────────────────────
TEMPLATE_CATALOG: list[OSTemplate] = [
    OSTemplate(
        os_id        = "ubuntu_24_04",
        os_name      = "Ubuntu",
        version      = "24.04.4 LTS",
        description  = "Beginner-friendly OS for development and learning. "
                       "Stable, well-supported, huge community.",
        tags         = ["Beginner", "Development", "Learning"],
        iso_url      = "https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso",
        iso_filename = "ubuntu-24.04.4-desktop-amd64.iso",
        os_type_id   = "Ubuntu_64",
        ram_mb       = 4096,
        cpu_count    = 2,
        disk_gb      = 40,
    ),
    OSTemplate(
        os_id        = "fedora_40",
        os_name      = "Fedora",
        version      = "40 Workstation Live",
        description  = "Cutting-edge Linux for advanced users. "
                       "Ships the latest GNOME and developer tools.",
        tags         = ["Advanced", "Development", "Cutting-Edge"],
        iso_url      = "https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/40/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-40-1.14.iso",
        iso_filename = "Fedora-Workstation-Live-x86_64-40-1.14.iso",
        os_type_id   = "Fedora_64",
        ram_mb       = 4096,
        cpu_count    = 2,
        disk_gb      = 40,
    ),
]
