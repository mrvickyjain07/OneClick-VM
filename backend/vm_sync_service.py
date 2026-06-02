"""
backend/vm_sync_service.py
==========================
Startup VM synchronization engine.

Responsibility
--------------
On application startup (or on demand), this service:

1.  Calls `VBoxManage list vms` to get every registered VM from VirtualBox.
2.  Calls `VBoxManage list runningvms` to determine which are running.
3.  Compares the VBox registry against our VMRepository (local DB cache).
4.  Classifies each VM as:
        NEW     — in VBox but not in our DB  → auto-imports entry
        SYNCED  — in both, state updated
        MISSING — in our DB but absent from VBox → marked MISSING
5.  Updates the SnapshotRepository for any snapshots whose parent VM is MISSING.
6.  Emits a SyncResult dataclass describing what changed.

This service does NOT touch the UI — it is pure backend logic meant to be
called from a QThread or worker at startup.

Guarantees
----------
- Never raises. All exceptions are caught, logged, and reflected in SyncResult.
- Safe to call multiple times (idempotent).
- All VBoxManage calls go through VBoxEngine (timed, logged, classified).
"""
import time
from dataclasses import dataclass, field
from typing import Optional

from .logger             import get_logger
from .vbox_engine        import VBoxEngine
from .vm_repository      import VMRepository, VMEntry
from .snapshot_repository import SnapshotRepository
from models              import VMState

logger = get_logger("VMSyncService")


# ─────────────────────────────────────────────────────────────────────────────
# Result types
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class SyncResult:
    """
    Summary of one sync pass.

    Attributes
    ----------
    elapsed_s        : wall-clock seconds for the entire sync
    vbox_total       : total VMs seen in VBox registry
    synced_count     : VMs that existed in both DB and VBox (state refreshed)
    new_count        : VMs newly imported from VBox into DB
    missing_count    : VMs in DB but absent from VBox (marked MISSING)
    orphan_snaps     : snapshot IDs marked orphaned (parent VM is MISSING)
    errors           : list of non-fatal error messages
    success          : True if sync completed without catastrophic failure
    """
    elapsed_s:    float         = 0.0
    vbox_total:   int           = 0
    synced_count: int           = 0
    new_count:    int           = 0
    missing_count:int           = 0
    orphan_snaps: list[str]     = field(default_factory=list)
    errors:       list[str]     = field(default_factory=list)
    success:      bool          = True

    def summary(self) -> str:
        return (
            f"Sync done in {self.elapsed_s:.2f}s — "
            f"VBox={self.vbox_total}  synced={self.synced_count}  "
            f"new={self.new_count}  missing={self.missing_count}  "
            f"orphan_snaps={len(self.orphan_snaps)}"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Sync service
# ─────────────────────────────────────────────────────────────────────────────

class VMSyncService:
    """
    Stateless sync engine.  Instantiate once; call sync() as needed.

    Parameters
    ----------
    vbox        : VBoxEngine instance
    repo        : VMRepository (UUID-keyed cache)
    snap_repo   : SnapshotRepository (for orphan marking)
    machines_db : legacy MachinesDB (updated in parallel for compat)
                  Pass None to skip legacy sync.
    """

    def __init__(
        self,
        vbox:        VBoxEngine,
        repo:        VMRepository,
        snap_repo:   Optional[SnapshotRepository]  = None,
        machines_db                                = None,
    ):
        self.vbox        = vbox
        self.repo        = repo
        self.snap_repo   = snap_repo
        self.machines_db = machines_db

    # ── Public API ────────────────────────────────────────────────────────────

    def sync(self) -> SyncResult:
        """
        Full synchronization pass.  Safe to call from any thread.
        Never raises — all errors are captured in SyncResult.errors.
        """
        result = SyncResult()
        t0 = time.monotonic()
        logger.info("=== VMSyncService.sync() START ===")

        try:
            self._do_sync(result)
        except Exception as exc:
            msg = f"Critical error during sync: {exc}"
            logger.exception(msg)
            result.errors.append(msg)
            result.success = False

        result.elapsed_s = time.monotonic() - t0
        logger.info("=== VMSyncService.sync() %s ===", result.summary())
        return result

    def repair_state(self) -> SyncResult:
        """
        Alias for sync() — re-runs a full pass to repair stale state.
        Useful when called from the health-check API after detecting drift.
        """
        logger.info("repair_state() triggered — running full sync")
        return self.sync()

    # ── Internal implementation ───────────────────────────────────────────────

    def _do_sync(self, result: SyncResult):
        # ── Step 1: Get VBox ground truth ─────────────────────────────────
        logger.info("Step 1: reading VBox registry (list vms + list runningvms)")
        try:
            vbox_vms = self.vbox.list_all_vms()         # {uuid: name}
        except Exception as exc:
            result.errors.append(f"list vms failed: {exc}")
            result.success = False
            return

        try:
            running_uuids = self.vbox.list_running_uuids()  # set[uuid]
        except Exception as exc:
            logger.warning("list runningvms failed during sync: %s", exc)
            running_uuids = set()
            result.errors.append(f"list runningvms failed (states may be stale): {exc}")

        result.vbox_total = len(vbox_vms)
        logger.info("VBox reports %d VMs (%d running)", len(vbox_vms), len(running_uuids))

        # ── Step 2: Update / import VBox VMs into our repo ────────────────
        logger.info("Step 2: updating repository from VBox data")
        for uuid, name in vbox_vms.items():
            try:
                self._sync_vm(uuid, name, running_uuids, result)
            except Exception as exc:
                msg = f"Error syncing uuid={uuid} name='{name}': {exc}"
                logger.warning(msg)
                result.errors.append(msg)

        # ── Step 3: Detect MISSING VMs (in DB but not in VBox) ────────────
        logger.info("Step 3: detecting missing VMs")
        for entry in self.repo.all():
            if entry.uuid not in vbox_vms:
                if entry.vm_state != VMState.MISSING:
                    logger.warning(
                        "VM MISSING from VBox: uuid=%s name='%s'",
                        entry.uuid, entry.vm_name,
                    )
                    self.repo.mark_missing(entry.uuid)
                    # Mirror to legacy MachinesDB
                    self._legacy_update_status(entry.vm_name, "stopped")
                result.missing_count += 1

        # ── Step 4: Orphan snapshots whose parent VM is MISSING ────────────
        if self.snap_repo:
            logger.info("Step 4: marking orphaned snapshots")
            self._mark_orphaned_snapshots(vbox_vms, result)

    def _sync_vm(
        self,
        uuid: str,
        name: str,
        running_uuids: set[str],
        result: SyncResult,
    ):
        """Update or create a VMEntry for a UUID that exists in VBox."""
        state = VMState.RUNNING if uuid in running_uuids else VMState.STOPPED

        existing = self.repo.get_by_uuid(uuid)
        if existing:
            # Known VM — update state only
            if existing.vm_state != state:
                logger.debug(
                    "State change: uuid=%s '%s' %s → %s",
                    uuid, name, existing.vm_state.value, state.value,
                )
            existing.vm_name  = name          # name may have changed
            existing.vm_state = state
            existing.last_seen = time.time()
            existing.error_msg = ""
            self.repo.upsert(existing)
            result.synced_count += 1
        else:
            # New VM — import into our DB
            entry = VMEntry(
                uuid     = uuid,
                vm_name  = name,
                state    = state.value,
            )
            self.repo.upsert(entry)
            logger.info("Auto-imported new VM: uuid=%s name='%s'", uuid, name)
            result.new_count += 1

        # Mirror state to legacy MachinesDB (for backward compat)
        self._legacy_update_status(name, state.value)

    def _mark_orphaned_snapshots(self, vbox_vms: dict, result: SyncResult):
        """
        Snapshots linked to a MISSING VM are marked orphaned.
        We do NOT call VBoxManage for these — their VM no longer exists.
        """
        if not self.snap_repo:
            return

        # Build the set of VM names still in VBox
        live_names = set(vbox_vms.values())
        live_uuids = set(vbox_vms.keys())

        for snap in self.snap_repo.all():
            # Check by vm_uuid (preferred) or vm_name (fallback)
            vm_missing = False
            if snap.vm_uuid and snap.vm_uuid not in live_uuids:
                vm_missing = True
            elif not snap.vm_uuid and snap.vm_name not in live_names:
                vm_missing = True

            if vm_missing and snap.status != "orphaned":
                logger.warning(
                    "Orphaning snapshot '%s' (id=%s) — parent VM '%s' is MISSING",
                    snap.snapshot_name, snap.id, snap.vm_name,
                )
                snap.status    = "orphaned"
                snap.error_msg = "Parent VM no longer exists in VirtualBox."
                self.snap_repo.update(snap)
                result.orphan_snaps.append(snap.id)

    def _legacy_update_status(self, vm_name: str, state_str: str):
        """Silently mirror state updates to the legacy MachinesDB."""
        if not self.machines_db:
            return
        try:
            from models import VMStatus
            status_map = {
                "running": VMStatus.RUNNING,
                "stopped": VMStatus.STOPPED,
                "missing": VMStatus.STOPPED,   # legacy has no MISSING
                "error":   VMStatus.STOPPED,
                "unknown": VMStatus.UNKNOWN,
            }
            legacy_status = status_map.get(state_str, VMStatus.UNKNOWN)
            self.machines_db.update_status(vm_name, legacy_status)
        except Exception as exc:
            logger.debug("Legacy DB mirror failed for '%s': %s", vm_name, exc)
