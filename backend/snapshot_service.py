"""
backend/snapshot_service.py
============================
Snapshot lifecycle orchestration: create, restore, delete, export.

Safety contract
---------------
Before any VBoxManage snapshot call, this service:
1. Resolves the parent VM's UUID.
2. Calls VBoxEngine.validate_vm(uuid) to confirm existence in VBox.
3. If the VM is MISSING:
   - Marks the SnapshotRecord as 'orphaned' in the repository.
   - Raises VMNotFoundException — does NOT call VBoxManage.

This prevents VBOX_E_OBJECT_NOT_FOUND errors from propagating
as unclassified RuntimeErrors into the UI.

All blocking VBoxManage calls must be made from a QThread, never the UI thread.
"""
import time, uuid as _uuid_mod
from pathlib import Path
from typing import Optional

from .logger              import get_logger
from .snapshot_repository import SnapshotRepository, SnapshotRecord
from .vbox_engine         import VBoxEngine
from .vbox_error          import VMNotFoundException, classify_error
from .machines_db         import MachinesDB

logger = get_logger("SnapshotService")


class SnapshotService:
    """
    Orchestrates snapshot create, restore, delete, and export.

    Parameters
    ----------
    repo        : SnapshotRepository — persistent metadata store
    machines_db : MachinesDB (legacy) — used for vm_name → uuid resolution
    vm_repo     : VMRepository (preferred) — UUID-keyed store; may be None
                  on first boot before sync has run.
    """

    def __init__(
        self,
        repo:        SnapshotRepository,
        machines_db: MachinesDB,
        vm_repo=None,
    ):
        self.repo        = repo
        self.machines_db = machines_db
        self.vm_repo     = vm_repo   # injected by app after creation
        self.vbox        = VBoxEngine()

    # ── Dependency injection ──────────────────────────────────────────────────

    def set_vm_repo(self, repo):
        """Wire in the VMRepository after construction."""
        self.vm_repo = repo

    # ── Create ────────────────────────────────────────────────────────────────

    def begin_snapshot(
        self,
        vm_name:       str,
        snapshot_name: str,
        description:   str  = "",
        live:          bool = False,
        vm_uuid:       str  = "",
    ) -> SnapshotRecord:
        """
        Stage a snapshot record with status='creating' for immediate UI feedback.
        Caller must subsequently call execute_snapshot() in a QThread.

        Parameters
        ----------
        vm_uuid : VirtualBox machine UUID — stored on the record so orphan
                  detection works even if the VM name changes later.
        """
        resolved_uuid = vm_uuid or self._resolve_uuid(vm_name)
        rec = SnapshotRecord(
            id            = _uuid_mod.uuid4().hex[:12],
            vm_name       = vm_name,
            vm_uuid       = resolved_uuid,
            snapshot_name = snapshot_name,
            description   = description,
            timestamp     = time.strftime("%Y-%m-%d %H:%M:%S"),
            status        = "creating",
            has_memory    = live,
        )
        self.repo.add(rec)
        logger.info(
            "begin_snapshot  vm='%s' (uuid=%s)  snap='%s'",
            vm_name, resolved_uuid or "?", snapshot_name,
        )
        return rec

    def execute_snapshot(
        self,
        rec:          SnapshotRecord,
        cached_state: Optional[str] = None,
    ) -> SnapshotRecord:
        """
        Run the VBoxManage snapshot take command (blocking — call from QThread).

        Pre-validates VM existence before calling VBoxManage.
        On VMNotFoundException: marks record as 'orphaned' and re-raises.
        """
        # ── Pre-op VM validation ──────────────────────────────────────────
        self._require_vm_exists(rec)

        try:
            current_state = (
                cached_state
                if cached_state
                else self.vbox.get_vm_state(rec.vm_name)
            )
            use_live = rec.has_memory and current_state == "running"

            self.vbox.take_snapshot(
                rec.vm_name, rec.snapshot_name,
                description  = rec.description,
                live         = use_live,
                cached_state = cached_state,
            )

            # Resolve the VBox snapshot UUID for future reference
            snaps = self.vbox.list_snapshots(rec.vm_name)
            for s in snaps:
                if s.get("name") == rec.snapshot_name:
                    rec.vbox_uuid = s.get("uuid", "")
                    break

            rec.status    = "completed"
            rec.error_msg = ""
            self.repo.update(rec)
            logger.info(
                "Snapshot '%s' completed for '%s' (vbox_uuid=%s)",
                rec.snapshot_name, rec.vm_name, rec.vbox_uuid,
            )

        except VMNotFoundException:
            rec = self._mark_orphaned(rec, "Parent VM is no longer registered in VirtualBox.")
            raise

        except Exception as exc:
            rec.status    = "failed"
            rec.error_msg = str(exc)
            self.repo.update(rec)
            logger.error("Snapshot '%s' failed: %s", rec.snapshot_name, exc)
            raise

        return rec

    # ── Restore ───────────────────────────────────────────────────────────────

    def restore(
        self,
        snap_id:      str,
        auto_start:   bool = True,
        cached_state: Optional[str] = None,
    ) -> SnapshotRecord:
        """
        Power off VM if needed → restore snapshot → optionally restart VM.
        Blocking — call from a QThread.

        Raises VMNotFoundException if the parent VM is missing from VBox.
        """
        rec = self._get(snap_id)

        # ── Pre-op VM validation ──────────────────────────────────────────
        self._require_vm_exists(rec)

        try:
            self.vbox.restore_snapshot(
                rec.vm_name, rec.snapshot_name,
                cached_state=cached_state,
            )
            if auto_start:
                time.sleep(1)
                self.vbox.start_vm(rec.vm_name, gui=True)
                if self.machines_db:
                    from models import VMStatus
                    self.machines_db.update_status(rec.vm_name, VMStatus.RUNNING)
            logger.info("Restored '%s' → '%s'", rec.vm_name, rec.snapshot_name)

        except VMNotFoundException:
            self._mark_orphaned(rec, "Parent VM not found during restore.")
            raise

        except Exception as exc:
            logger.error("Restore failed for snap_id=%s: %s", snap_id, exc)
            raise

        return rec

    # ── Delete ────────────────────────────────────────────────────────────────

    def delete(self, snap_id: str):
        """
        Delete a snapshot from VirtualBox and remove the metadata record.

        If the parent VM is MISSING:
        - Marks the snapshot as 'orphaned'.
        - Does NOT call VBoxManage.
        - Removes the metadata record (no point keeping an orphan).
        """
        rec = self._get(snap_id)

        # Check VM existence
        uuid = self._resolve_uuid(rec.vm_name) or rec.vm_uuid
        if uuid and not self.vbox.validate_vm(uuid):
            logger.warning(
                "delete snapshot '%s': parent VM '%s' (uuid=%s) is MISSING — "
                "skipping VBoxManage, removing metadata only.",
                rec.snapshot_name, rec.vm_name, uuid,
            )
            self.repo.remove(snap_id)
            return

        # VM exists — proceed with VBox call
        try:
            self.vbox.delete_snapshot(rec.vm_name, rec.snapshot_name)
            self.repo.remove(snap_id)
            logger.info("Deleted snapshot '%s' from '%s'", rec.snapshot_name, rec.vm_name)

        except VMNotFoundException:
            logger.warning(
                "delete snapshot '%s': VMNotFoundException — removing metadata",
                rec.snapshot_name,
            )
            self._mark_orphaned(rec, "Parent VM disappeared during delete.")
            self.repo.remove(snap_id)
            raise

        except Exception as exc:
            logger.error("delete snapshot '%s' failed: %s", rec.snapshot_name, exc)
            raise

    # ── Export ────────────────────────────────────────────────────────────────

    def export(self, snap_id: str, output_path: str):
        """
        Export the VM as OVA.
        Pre-validates VM existence before calling VBoxManage.
        """
        rec = self._get(snap_id)
        self._require_vm_exists(rec)
        self.vbox.export_vm(rec.vm_name, output_path)
        logger.info("Exported '%s' to '%s'", rec.vm_name, output_path)

    # ── Query pass-throughs ───────────────────────────────────────────────────

    def all(self)             -> list: return self.repo.all()
    def for_vm(self, vm)      -> list: return self.repo.for_vm(vm)
    def search(self, q, flt)  -> list: return self.repo.search(q, flt)
    def counts(self)          -> dict: return self.repo.counts()
    def get(self, snap_id)         :  return self.repo.get(snap_id)

    def vm_names(self) -> list:
        """List of VM names from the machines DB."""
        return [r.vm_name for r in self.machines_db.all()]

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, snap_id: str) -> SnapshotRecord:
        rec = self.repo.get(snap_id)
        if not rec:
            raise ValueError(f"Snapshot '{snap_id}' not found in repository.")
        return rec

    def _resolve_uuid(self, vm_name: str) -> str:
        """Resolve VM UUID from VMRepository → MachinesDB → VBox."""
        # 1. VMRepository (preferred)
        if self.vm_repo:
            entry = self.vm_repo.get_by_name(vm_name)
            if entry and entry.uuid:
                return entry.uuid

        # 2. Legacy MachinesDB
        rec = self.machines_db.get(vm_name) if self.machines_db else None
        if rec and rec.uuid:
            return rec.uuid

        # 3. VBoxManage (slow path)
        try:
            found = self.vbox.get_uuid_for_name(vm_name)
            if found:
                return found
        except Exception:
            pass

        return ""

    def _require_vm_exists(self, rec: SnapshotRecord):
        """
        Validate the parent VM exists in VirtualBox.
        Raises VMNotFoundException (marks record orphaned) if not.
        """
        uuid = rec.vm_uuid or self._resolve_uuid(rec.vm_name)

        if not uuid:
            # No UUID — try name-based existence check via list_all_vms
            all_vms = self.vbox.list_all_vms()
            name_found = any(n == rec.vm_name for n in all_vms.values())
            if not name_found:
                logger.warning(
                    "_require_vm_exists: '%s' not found in VBox (no UUID, name search failed)",
                    rec.vm_name,
                )
                self._mark_orphaned(rec, "Parent VM not found in VirtualBox.")
                raise VMNotFoundException(rec.vm_name)
            return

        if not self.vbox.validate_vm(uuid):
            logger.warning(
                "_require_vm_exists: uuid=%s ('%s') is MISSING from VBox",
                uuid, rec.vm_name,
            )
            self._mark_orphaned(
                rec, f"Parent VM (uuid={uuid}) is no longer registered in VirtualBox."
            )
            raise VMNotFoundException(uuid)

    def _mark_orphaned(self, rec: SnapshotRecord, reason: str) -> SnapshotRecord:
        """Mark a snapshot record as orphaned and persist."""
        if rec.status != "orphaned":
            rec.status    = "orphaned"
            rec.error_msg = reason
            self.repo.update(rec)
            logger.warning(
                "Snapshot '%s' (id=%s) marked ORPHANED: %s",
                rec.snapshot_name, rec.id, reason,
            )
        return rec
