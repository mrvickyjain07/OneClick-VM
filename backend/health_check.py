"""
backend/health_check.py
=======================
Health Check API for VirtualBox integration.

Public functions
----------------
    validate_vm(uuid, vbox)    → bool
        Check if a single VM UUID exists in VirtualBox right now.

    sync_vms(engine)           → SyncResult
        Run a full VM synchronization pass against VirtualBox.

    repair_state(engine)       → SyncResult
        Alias for sync_vms; re-validates all VMs and repairs stale DB state.

    get_health_report(engine)  → HealthReport
        Produces a complete health snapshot: VBox availability, VM counts,
        missing VMs, orphaned snapshots.

This module is intentionally stateless — it takes engines/repos as arguments
so it works from anywhere (startup, background threads, diagnostic tools).
"""
import time
from dataclasses import dataclass, field
from typing import Optional

from .logger             import get_logger
from .vbox_engine        import VBoxEngine
from .vm_repository      import VMRepository, VMEntry
from .snapshot_repository import SnapshotRepository
from .vm_sync_service    import VMSyncService, SyncResult
from models              import VMState

logger = get_logger("HealthCheck")


# ─────────────────────────────────────────────────────────────────────────────
# HealthReport dataclass
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HealthReport:
    """
    Snapshot of application health at a point in time.

    Attributes
    ----------
    timestamp          : ISO timestamp when report was generated
    vbox_installed     : whether VBoxManage is reachable
    vbox_total_vms     : total VMs registered in VirtualBox
    db_total_vms       : total VM entries in our repository
    running_vms        : list of (uuid, name) for running VMs
    missing_vms        : list of (uuid, name) for MISSING VMs (DB not VBox)
    orphaned_snapshots : list of (snap_id, snap_name, vm_name)
    errors             : non-fatal error messages
    overall_ok         : True if no MISSING VMs and no orphaned snapshots
    elapsed_s          : seconds to generate the report
    """
    timestamp:          str              = ""
    vbox_installed:     bool             = False
    vbox_total_vms:     int              = 0
    db_total_vms:       int              = 0
    running_vms:        list             = field(default_factory=list)
    missing_vms:        list             = field(default_factory=list)
    orphaned_snapshots: list             = field(default_factory=list)
    errors:             list[str]        = field(default_factory=list)
    overall_ok:         bool             = True
    elapsed_s:          float            = 0.0

    def summary(self) -> str:
        status = "OK" if self.overall_ok else "DEGRADED"
        return (
            f"[{status}] vbox={self.vbox_installed}  "
            f"vms={self.db_total_vms}/{self.vbox_total_vms}  "
            f"missing={len(self.missing_vms)}  "
            f"orphan_snaps={len(self.orphaned_snapshots)}  "
            f"({self.elapsed_s:.2f}s)"
        )


# ─────────────────────────────────────────────────────────────────────────────
# Core health-check functions
# ─────────────────────────────────────────────────────────────────────────────

def validate_vm(uuid: str, vbox: VBoxEngine) -> bool:
    """
    Check whether a specific VM UUID exists in VirtualBox right now.

    Parameters
    ----------
    uuid  : the VirtualBox machine UUID to validate
    vbox  : VBoxEngine instance

    Returns
    -------
    True   — UUID is present in `VBoxManage list vms`
    False  — UUID is absent (VM is MISSING or VBox is unavailable)

    Never raises.
    """
    if not uuid:
        logger.warning("validate_vm called with empty UUID")
        return False
    if not vbox.is_virtualbox_installed():
        logger.warning("validate_vm: VirtualBox not installed")
        return False
    try:
        result = vbox.validate_vm(uuid)
        logger.debug("validate_vm uuid=%s → %s", uuid, result)
        return result
    except Exception as exc:
        logger.error("validate_vm uuid=%s error: %s", uuid, exc)
        return False


def sync_vms(
    vbox:        VBoxEngine,
    repo:        VMRepository,
    snap_repo:   Optional[SnapshotRepository] = None,
    machines_db                               = None,
) -> SyncResult:
    """
    Run a full VM synchronization pass.

    1. Queries VBoxManage for all registered VMs.
    2. Updates VMRepository state (RUNNING / STOPPED / MISSING).
    3. Marks orphaned snapshots.
    4. Mirrors to legacy MachinesDB for backward compatibility.

    Parameters
    ----------
    vbox        : VBoxEngine
    repo        : VMRepository (UUID-keyed cache)
    snap_repo   : SnapshotRepository (pass None to skip orphan detection)
    machines_db : legacy MachinesDB (pass None to skip legacy mirror)

    Returns
    -------
    SyncResult — never raises; errors are captured in SyncResult.errors.
    """
    svc = VMSyncService(
        vbox        = vbox,
        repo        = repo,
        snap_repo   = snap_repo,
        machines_db = machines_db,
    )
    result = svc.sync()
    logger.info("sync_vms: %s", result.summary())
    return result


def repair_state(
    vbox:        VBoxEngine,
    repo:        VMRepository,
    snap_repo:   Optional[SnapshotRepository] = None,
    machines_db                               = None,
) -> SyncResult:
    """
    Re-validate all VM states and repair stale DB entries.
    Alias for sync_vms — the sync engine is idempotent.
    """
    logger.info("repair_state() called — running full sync")
    return sync_vms(vbox, repo, snap_repo, machines_db)


def get_health_report(
    vbox:      VBoxEngine,
    repo:      VMRepository,
    snap_repo: Optional[SnapshotRepository] = None,
) -> HealthReport:
    """
    Produce a comprehensive health report without modifying any state.

    This is a READ-ONLY operation — it does not update the DB.
    Use sync_vms() or repair_state() to actually fix inconsistencies.

    Parameters
    ----------
    vbox      : VBoxEngine
    repo      : VMRepository
    snap_repo : SnapshotRepository (pass None to skip snapshot checks)

    Returns
    -------
    HealthReport dataclass — never raises.
    """
    t0     = time.monotonic()
    report = HealthReport(
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S"),
    )

    # ── VBox availability ─────────────────────────────────────────────────
    report.vbox_installed = vbox.is_virtualbox_installed()
    if not report.vbox_installed:
        report.errors.append("VirtualBox is not installed or VBoxManage not found.")
        report.overall_ok = False
        report.elapsed_s  = time.monotonic() - t0
        return report

    # ── Query VBox ground truth ───────────────────────────────────────────
    try:
        vbox_vms      = vbox.list_all_vms()         # {uuid: name}
        running_uuids = vbox.list_running_uuids()   # set[uuid]
        report.vbox_total_vms = len(vbox_vms)
    except Exception as exc:
        report.errors.append(f"Failed to query VirtualBox: {exc}")
        report.overall_ok = False
        report.elapsed_s  = time.monotonic() - t0
        return report

    # ── Running VMs ───────────────────────────────────────────────────────
    for uuid in running_uuids:
        name = vbox_vms.get(uuid, "<unknown>")
        report.running_vms.append({"uuid": uuid, "name": name})

    # ── DB entries ────────────────────────────────────────────────────────
    db_entries = repo.all()
    report.db_total_vms = len(db_entries)

    # ── Missing VMs (in DB but not in VBox) ───────────────────────────────
    for entry in db_entries:
        if entry.uuid and entry.uuid not in vbox_vms:
            report.missing_vms.append({
                "uuid":    entry.uuid,
                "name":    entry.vm_name,
                "last_seen": entry.last_seen,
            })
    if report.missing_vms:
        report.overall_ok = False

    # ── Orphaned snapshots ────────────────────────────────────────────────
    if snap_repo:
        try:
            live_names = set(vbox_vms.values())
            live_uuids = set(vbox_vms.keys())
            for snap in snap_repo.all():
                is_orphaned = False
                if snap.vm_uuid and snap.vm_uuid not in live_uuids:
                    is_orphaned = True
                elif not snap.vm_uuid and snap.vm_name not in live_names:
                    is_orphaned = True
                if is_orphaned:
                    report.orphaned_snapshots.append({
                        "id":            snap.id,
                        "snapshot_name": snap.snapshot_name,
                        "vm_name":       snap.vm_name,
                        "vm_uuid":       snap.vm_uuid,
                        "status":        snap.status,
                    })
            if report.orphaned_snapshots:
                report.overall_ok = False
        except Exception as exc:
            report.errors.append(f"Snapshot health check failed: {exc}")

    report.elapsed_s = time.monotonic() - t0
    logger.info("HealthReport: %s", report.summary())
    return report
