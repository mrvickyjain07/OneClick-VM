"""
backend/vbox_error.py
Structured error handling and classification for VirtualBox operations.

Every RuntimeError raised by VBoxEngine is passed through classify_error()
to produce a VBoxError dataclass with:
  - A canonical error code (VBOX_E_OBJECT_NOT_FOUND, etc.)
  - A user-friendly message
  - Context (vm_uuid, vm_name, command)
  - Flags: is_not_found, is_fatal

Two domain exceptions are also defined for clean raise/catch patterns:
  VMNotFoundException        — VM UUID/name absent from VirtualBox
  SnapshotNotFoundException  — Snapshot absent from a VM
"""
import re
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger("VBoxError")

# ── Canonical error codes ─────────────────────────────────────────────────────
VBOX_E_OBJECT_NOT_FOUND = "VBOX_E_OBJECT_NOT_FOUND"
VBOX_E_INVALID_VM_STATE = "VBOX_E_INVALID_VM_STATE"
VBOX_E_FILE_ERROR       = "VBOX_E_FILE_ERROR"
VBOX_E_ACCESS_DENIED    = "VBOX_E_ACCESS_DENIED"
VBOX_E_TIMEOUT          = "VBOX_E_TIMEOUT"
VBOX_UNKNOWN            = "VBOX_UNKNOWN"

# ── Pattern → code mapping (evaluated in order) ───────────────────────────────
_PATTERNS: list[tuple[str, list[str]]] = [
    (VBOX_E_OBJECT_NOT_FOUND, [
        r"VBOX_E_OBJECT_NOT_FOUND",
        r"Could not find a registered machine",
        r"Could not find a snapshot",
        r"Machine .* is not found",
        r"0x80BB0001",
    ]),
    (VBOX_E_INVALID_VM_STATE, [
        r"VBOX_E_INVALID_VM_STATE",
        r"Invalid machine state",
        r"0x80BB0002",
        r"already locked",
        r"not in a valid state",
    ]),
    (VBOX_E_FILE_ERROR, [
        r"VBOX_E_FILE_ERROR",
        r"No such file or directory",
        r"file not found",
        r"Cannot open.*medium",
        r"0x80BB0004",
    ]),
    (VBOX_E_ACCESS_DENIED, [
        r"E_ACCESSDENIED",
        r"E_ACCESSDENIED",
        r"access.?denied",
        r"locked.*exclusive",
        r"VERR_ACCESS_DENIED",
    ]),
    (VBOX_E_TIMEOUT, [
        r"timed out",
        r"Timeout",
    ]),
]

# ── User-friendly messages ────────────────────────────────────────────────────
_USER_MESSAGES: dict[str, str] = {
    VBOX_E_OBJECT_NOT_FOUND: (
        "The VM or snapshot no longer exists in VirtualBox. "
        "It may have been deleted outside this application."
    ),
    VBOX_E_INVALID_VM_STATE: (
        "The VM is in an invalid state for this operation. "
        "Try stopping the VM first."
    ),
    VBOX_E_FILE_ERROR: (
        "A required VM file (disk image or config) is missing or inaccessible."
    ),
    VBOX_E_ACCESS_DENIED: (
        "Access denied — the VM may be locked by VirtualBox or another process."
    ),
    VBOX_E_TIMEOUT: (
        "VirtualBox did not respond in time. The system may be under heavy load."
    ),
}


# ── Data classes ──────────────────────────────────────────────────────────────

@dataclass
class VBoxError:
    """Structured representation of a VirtualBox operation error."""
    code:         str           = VBOX_UNKNOWN
    raw_message:  str           = ""
    user_message: str           = "An unknown VirtualBox error occurred."
    vm_uuid:      Optional[str] = None
    vm_name:      Optional[str] = None
    command:      Optional[str] = None
    # Semantic flags
    is_not_found: bool          = False   # VM/snapshot absent from VBox registry
    is_state_err: bool          = False   # Operation invalid in current VM state
    is_fatal:     bool          = False   # Cannot be retried; DB should be updated

    def __str__(self) -> str:
        parts = [f"[{self.code}]", self.user_message]
        if self.vm_name or self.vm_uuid:
            parts.append(f"(vm={self.vm_name or self.vm_uuid})")
        return " ".join(parts)


# ── Classification function ───────────────────────────────────────────────────

def classify_error(
    raw: str,
    vm_uuid: str = None,
    vm_name: str = None,
    command: str = None,
) -> VBoxError:
    """
    Inspect a raw VBoxManage error string and return a classified VBoxError.

    Parameters
    ----------
    raw     : raw stderr / exception message
    vm_uuid : UUID of the VM involved (for context)
    vm_name : name of the VM involved (for context)
    command : the VBoxManage sub-command that failed (for context)
    """
    for code, patterns in _PATTERNS:
        for pat in patterns:
            if re.search(pat, raw, re.IGNORECASE):
                err = VBoxError(
                    code         = code,
                    raw_message  = raw,
                    user_message = _USER_MESSAGES.get(code, raw[:200]),
                    vm_uuid      = vm_uuid,
                    vm_name      = vm_name,
                    command      = command,
                    is_not_found = (code == VBOX_E_OBJECT_NOT_FOUND),
                    is_state_err = (code == VBOX_E_INVALID_VM_STATE),
                    is_fatal     = (code in (
                        VBOX_E_OBJECT_NOT_FOUND,
                        VBOX_E_FILE_ERROR,
                    )),
                )
                logger.warning(
                    "VBoxError classified: code=%s  vm=%s  msg=%.120s",
                    code, vm_name or vm_uuid or "?", raw,
                )
                return err

    # No pattern matched → generic unknown error
    return VBoxError(
        code         = VBOX_UNKNOWN,
        raw_message  = raw,
        user_message = raw[:200] if raw else "Unknown VirtualBox error.",
        vm_uuid      = vm_uuid,
        vm_name      = vm_name,
        command      = command,
    )


# ── Domain exceptions ─────────────────────────────────────────────────────────

class VMNotFoundException(Exception):
    """Raised when a VM UUID/name is not registered in VirtualBox."""
    def __init__(self, identifier: str, vbox_error: VBoxError = None):
        self.identifier  = identifier
        self.vbox_error  = vbox_error
        super().__init__(f"VM not found in VirtualBox: {identifier}")


class SnapshotNotFoundException(Exception):
    """Raised when a snapshot does not exist on the given VM."""
    def __init__(self, vm_id: str, snap_name: str, vbox_error: VBoxError = None):
        self.vm_id       = vm_id
        self.snap_name   = snap_name
        self.vbox_error  = vbox_error
        super().__init__(
            f"Snapshot '{snap_name}' not found on VM '{vm_id}'"
        )


class VBoxNotInstalledError(Exception):
    """Raised when VBoxManage cannot be located on the system."""
    pass
