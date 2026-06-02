"""
ui/state_manager.py
===================
Central single-source-of-truth for VM and Snapshot state.

Design
------
• VMStateManager holds the authoritative in-memory state for every known VM.
• Pages bind to `state_changed` signal — they never guess state from stale copies.
• All mutating writes go through set_vm_state() / set_vm_busy().
• Snapshot states are stored alongside VM states.

Usage
-----
    from ui.state_manager import vm_state_manager
    vm_state_manager.set_vm_state("Ubuntu-1", "running")
    vm_state_manager.set_vm_busy("Ubuntu-1", True)
    vm_state_manager.state_changed.connect(my_handler)
"""
from PyQt5.QtCore import QObject, pyqtSignal
import threading


class VMStateManager(QObject):
    """Thread-safe VM state registry with Qt change signals."""

    # Emitted on any state change — receivers refresh their UI
    state_changed   = pyqtSignal(str, str)   # vm_name, new_state
    busy_changed    = pyqtSignal(str, bool)  # vm_name, is_busy

    def __init__(self):
        super().__init__()
        self._states: dict[str, str]  = {}   # vm_name → "running"|"stopped"|"missing"|"unknown"
        self._busy:   dict[str, bool] = {}   # vm_name → True while an operation is in progress
        self._lock = threading.RLock()

    # ── State mutations ───────────────────────────────────────────────────────

    def set_vm_state(self, vm_name: str, state: str):
        """Update VM state and notify observers. Call from any thread."""
        with self._lock:
            old = self._states.get(vm_name)
            self._states[vm_name] = state
        if old != state:
            self.state_changed.emit(vm_name, state)

    def set_vm_busy(self, vm_name: str, busy: bool):
        """Mark a VM as 'busy' (operation in progress) to lock action buttons."""
        with self._lock:
            old = self._busy.get(vm_name, False)
            self._busy[vm_name] = busy
        if old != busy:
            self.busy_changed.emit(vm_name, busy)

    def bulk_update(self, states: dict[str, str]):
        """Apply a dict of {vm_name: state} changes from the poller."""
        for name, state in states.items():
            self.set_vm_state(name, state)

    # ── State queries ─────────────────────────────────────────────────────────

    def get_state(self, vm_name: str) -> str:
        with self._lock:
            return self._states.get(vm_name, "unknown")

    def is_busy(self, vm_name: str) -> bool:
        with self._lock:
            return self._busy.get(vm_name, False)

    def is_running(self, vm_name: str) -> bool:
        return self.get_state(vm_name) == "running"

    def all_states(self) -> dict:
        with self._lock:
            return dict(self._states)

    def register(self, vm_name: str, initial_state: str = "unknown"):
        """Ensure vm_name is in the registry (idempotent)."""
        with self._lock:
            if vm_name not in self._states:
                self._states[vm_name] = initial_state

    def unregister(self, vm_name: str):
        """Remove a VM from the registry."""
        with self._lock:
            self._states.pop(vm_name, None)
            self._busy.pop(vm_name, None)


# ── Module-level singleton (import-safe) ─────────────────────────────────────
vm_state_manager = VMStateManager()
