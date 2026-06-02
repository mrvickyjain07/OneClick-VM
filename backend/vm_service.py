"""
backend/vm_service.py
=====================
VM lifecycle orchestration — create, start, stop, delete.

Design
------
- UUID-first: every destructive operation resolves the UUID first,
  then validates it exists in VirtualBox before proceeding.
- Falls back gracefully when UUID is not yet known (legacy records).
- All errors are classified through vbox_error before re-raising.
- VMRepository is the canonical store; MachinesDB is kept in sync
  for backward compatibility with frontend widgets that read it.

Thread safety
-------------
All methods are safe to call from QThreads.
Never call from the UI thread — VBoxManage calls block.
"""
import uuid as _uuid_mod
import time
import shutil
from pathlib import Path

from models import VMRecord, VMStatus, VMState
from .vbox_engine        import VBoxEngine
from .vbox_error         import VMNotFoundException, classify_error
from .machines_db        import MachinesDB
from .vm_repository      import VMRepository, VMEntry
from .logger             import get_logger

logger = get_logger("VMService")


class VMService:
    """
    Orchestrates VM lifecycle (create / start / stop / delete).

    Parameters
    ----------
    machines_db  : legacy MachinesDB  — kept for widget backward compat
    vm_data_dir  : base directory for VM disk images
    vm_repo      : VMRepository (UUID-keyed) — the canonical store
    state_poller : VMStatePoller QThread — injected after construction
    """

    def __init__(
        self,
        machines_db: MachinesDB,
        vm_data_dir: Path,
        vm_repo:     VMRepository = None,
        state_poller              = None,
    ):
        self.db          = machines_db
        self.vm_data_dir = vm_data_dir
        self.vm_repo     = vm_repo        # may be None on first boot
        self.vbox        = VBoxEngine()
        self._poller     = state_poller   # VMStatePoller, injected later

    # ── Dependency injection ───────────────────────────────────────────────

    def set_poller(self, poller):
        """Inject the VMStatePoller after it has been constructed."""
        self._poller = poller

    def set_vm_repo(self, repo: VMRepository):
        """Inject the VMRepository after it has been constructed."""
        self.vm_repo = repo

    # Some worker classes reference self.vm_service._vm_repo (underscore prefix).
    # This property alias ensures both names resolve to the same object.
    @property
    def _vm_repo(self) -> VMRepository:
        return self.vm_repo

    # ── VBox availability ──────────────────────────────────────────────────

    def vbox_available(self) -> bool:
        return self.vbox.is_virtualbox_installed()

    # ── VM creation ────────────────────────────────────────────────────────

    def create_vm(
        self,
        os_id:            str,
        os_name:          str,
        os_type_id:       str,
        iso_path:         Path,
        ram_mb:           int,
        cpu_count:        int,
        disk_gb:          int,
        log_callback=None,
        vm_name_override: str = None,
    ) -> VMRecord:
        """
        Full VM creation pipeline — ATOMIC.

        Steps
        -----
        1.  Pre-checks  (disk space, name collision / orphan detection)
        2.  Register VM in VirtualBox (createvm)
        3.  Configure resources (memory, CPU, VRAM)
        4.  Create & attach primary disk
        5.  Attach installer ISO
        6.  Configure network (NAT)
        7.  Resolve the UUID VirtualBox assigned
        8.  Persist to VMRepository + legacy MachinesDB

        Atomicity guarantee
        -------------------
        If any VBox call after step 2 fails, a rollback is executed:
          - VBoxManage unregistervm --delete  (removes .vbox + VHDs)
          - shutil.rmtree on the VM folder    (removes any residual files)
        The caller always receives either a complete VMRecord or a clear
        exception — never a half-built VM.
        """
        def log(msg: str):
            logger.info(msg)
            if log_callback:
                log_callback(msg)

        if not self.vbox_available():
            raise RuntimeError("VirtualBox not found. Please install it first.")

        # ════════════════════════════════════════════════════════════════
        # PRE-CHECKS  (run before any VBoxManage call)
        # ════════════════════════════════════════════════════════════════

        # ── Disk space — 5 GB safety buffer ────────────────────────────
        _disk_needed_gb = disk_gb + 5
        _free_gb = shutil.disk_usage(str(self.vm_data_dir)).free / (1024 ** 3)
        if _free_gb < _disk_needed_gb:
            raise RuntimeError(
                f"[CREATE_VM_FAIL] Insufficient disk space.\n"
                f"Required: ~{_disk_needed_gb} GB  |  Available: {_free_gb:.1f} GB\n"
                f"Location: '{self.vm_data_dir}'\n"
                "Free up disk space before creating a new VM."
            )

        # ── ISO exists on disk ──────────────────────────────────────────
        if not Path(iso_path).exists():
            raise RuntimeError(
                f"[CREATE_VM_FAIL] ISO file not found: {iso_path}\n"
                "Re-mount the ISO before creating a VM."
            )

        # ── VM name ────────────────────────────────────────────────────
        if vm_name_override and vm_name_override.strip():
            vm_name = vm_name_override.strip()
        else:
            short_id = _uuid_mod.uuid4().hex[:8]
            prefix   = os_name.replace(" ", "_").replace(".", "_")
            vm_name  = f"{prefix}_OneClick_{short_id}"

        # ── Orphan / collision detection ───────────────────────────────
        #   Case A: name in our DB  → reject (user must delete first)
        #   Case B: name in VBox but NOT in our DB → orphan → auto-purge
        #   Case C: name in neither → proceed normally
        _db_collision  = self.db.get(vm_name) is not None
        _vbox_uuid     = self.vbox.get_uuid_for_name(vm_name)
        _vbox_collision = _vbox_uuid is not None

        if _db_collision and _vbox_collision:
            raise RuntimeError(
                f"[CREATE_VM_FAIL] VM '{vm_name}' already exists.\n"
                "Delete or rename the existing VM before creating a new one."
            )

        if _vbox_collision and not _db_collision:
            # Orphan: registered in VBox but unknown to our app — auto-purge
            logger.warning(
                "[CREATE_VM_ORPHAN] VM '%s' (uuid=%s) is registered in VBox "
                "but absent from app DB. Auto-purging orphan before creation.",
                vm_name, _vbox_uuid,
            )
            log(f"⚠ Cleaning up orphaned VM '{vm_name}'…")
            try:
                self.vbox.run_cmd(
                    ["unregistervm", _vbox_uuid, "--delete"],
                    timeout=30, vm_uuid=_vbox_uuid,
                )
                logger.info("[ROLLBACK_DONE] Orphan '%s' purged.", vm_name)
            except Exception as purge_exc:
                logger.warning("Orphan purge failed (continuing): %s", purge_exc)

        # ════════════════════════════════════════════════════════════════
        # ATOMIC CREATION
        # ════════════════════════════════════════════════════════════════
        logger.info(
            "[CREATE_VM_START] name='%s'  os=%s  ram=%d  cpu=%d  disk=%d  iso=%s",
            vm_name, os_type_id, ram_mb, cpu_count, disk_gb, iso_path,
        )
        log(f"Creating VM: {vm_name}")
        log(f"Resources → RAM={ram_mb} MB  CPU={cpu_count}  Disk={disk_gb} GB")

        base             = self.vm_data_dir / vm_name
        _vbox_registered = False   # True once createvm succeeds

        try:
            # ── Step 2: Register ───────────────────────────────────────
            base.mkdir(parents=True, exist_ok=True)
            self.vbox.create_vm(vm_name, os_type=os_type_id,
                                base_folder=str(self.vm_data_dir))
            _vbox_registered = True
            log("VM registered in VirtualBox.")

            # ── Step 3: Resources ──────────────────────────────────────
            self.vbox.set_vm_resources(vm_name, ram_mb, cpu_count)
            self.vbox.configure_vm_display(vm_name)
            log("Resources and display configured.")

            # ── Step 4: Storage ────────────────────────────────────────
            self.vbox.attach_storage_controller(vm_name, name="SATA",
                                                ctrl_type="IntelAHCI")
            disk_path = base / f"{vm_name}.vdi"
            self.vbox.create_disk(vm_name, disk_gb, disk_path)
            self.vbox.attach_disk(vm_name, disk_path, controller="SATA", port=0)
            log(f"Disk created: {disk_gb} GB")

            # ── Step 5: ISO ────────────────────────────────────────────
            self.vbox.attach_iso(vm_name, iso_path, controller="SATA", port=1)
            log("ISO attached.")

            # ── Step 6: Network ────────────────────────────────────────
            self.vbox.set_network_nat(vm_name)
            log("Network (NAT) configured.")

            # ── Step 7: Resolve UUID ───────────────────────────────────
            vm_uuid = self.vbox.get_uuid_for_name(vm_name) or ""
            if vm_uuid:
                log(f"VM UUID: {vm_uuid}")
            else:
                logger.warning(
                    "Could not resolve UUID for '%s' after creation", vm_name
                )

        except Exception as exc:
            # ── ROLLBACK ───────────────────────────────────────────────
            logger.error(
                "[CREATE_VM_FAIL] name='%s' failed at step: %s",
                vm_name, exc, exc_info=True,
            )
            log(f"⚠ Creation failed — rolling back: {exc}")

            if _vbox_registered:
                try:
                    _rb_uuid = self.vbox.get_uuid_for_name(vm_name) or vm_name
                    self.vbox.run_cmd(
                        ["unregistervm", _rb_uuid, "--delete"],
                        timeout=30,
                    )
                    logger.info("[ROLLBACK_DONE] unregistervm '%s' OK", vm_name)
                except Exception as rb_exc:
                    logger.warning("[ROLLBACK_DONE] unregistervm failed: %s", rb_exc)

            # Always nuke the folder — catches residual .vdi / .vbox files
            if base.exists():
                try:
                    shutil.rmtree(str(base), ignore_errors=True)
                    logger.info("[ROLLBACK_DONE] folder '%s' removed", base)
                except Exception as rf_exc:
                    logger.warning("[ROLLBACK_DONE] folder removal failed: %s", rf_exc)

            # Re-raise with the original exception so the worker can surface it
            raise RuntimeError(
                f"VM '{vm_name}' creation failed and was rolled back.\n"
                f"Reason: {exc}"
            ) from exc

        # ════════════════════════════════════════════════════════════════
        # PERSIST (only reached on full success)
        # ════════════════════════════════════════════════════════════════
        created_at = time.strftime("%Y-%m-%d %H:%M:%S")

        if self.vm_repo:
            entry = VMEntry(
                uuid       = vm_uuid,
                vm_name    = vm_name,
                os_id      = os_id,
                os_name    = os_name,
                os_type_id = os_type_id,
                created_at = created_at,
                iso_path   = str(iso_path),
                ram_mb     = ram_mb,
                cpu_count  = cpu_count,
                disk_gb    = disk_gb,
                state      = VMState.STOPPED.value,
            )
            self.vm_repo.upsert(entry)

        rec = VMRecord(
            vm_name   = vm_name,
            os_id     = os_id,
            os_name   = os_name,
            created_at= created_at,
            iso_path  = str(iso_path),
            status    = VMStatus.STOPPED,
            state     = VMState.STOPPED,
            ram_mb    = ram_mb,
            cpu_count = cpu_count,
            disk_gb   = disk_gb,
            uuid      = vm_uuid,
        )
        self.db.add(rec)

        logger.info(
            "[CREATE_VM_SUCCESS] name='%s'  uuid=%s", vm_name, vm_uuid
        )
        log(f"VM '{vm_name}' ready.")
        return rec

    # ── Start ──────────────────────────────────────────────────────────────

    def start_vm(self, vm_name: str):
        """
        Start a VM by name.

        Resolution order:
        1. Look up UUID in VMRepository (preferred)
        2. Look up UUID in legacy MachinesDB record
        3. Resolve UUID from VBoxManage (slow path)
        4. Fall back to name-based start (legacy)

        Raises VMNotFoundException if UUID is known but absent from VBox.
        """
        uuid = self._resolve_uuid(vm_name)

        # Structured log — surfaces context for every launch attempt
        iso_path = "?"
        if self.vm_repo:
            entry = self.vm_repo.get_by_name(vm_name)
            if entry:
                iso_path = entry.iso_path or "?"
        logger.info(
            "start_vm: name='%s'  uuid=%s  iso_path=%s",
            vm_name, uuid or "(none)", iso_path,
        )

        if uuid:
            # ── UUID path (preferred) ──────────────────────────────────
            if not self.vbox.validate_vm(uuid):
                self._mark_missing(vm_name, uuid)
                raise VMNotFoundException(uuid, vbox_error=None)

            logger.info("start_vm: uuid=%s validated — issuing startvm", uuid)
            # skip_validation=True: we just called validate_vm — no redundant list vms
            self.vbox.start_vm_by_uuid(uuid, gui=True, skip_validation=True)

        else:
            # ── Name fallback (legacy / no UUID yet) ───────────────────
            logger.warning(
                "start_vm '%s': no UUID found — using name-based path", vm_name
            )
            cached_state = self._cached_state(vm_name)
            self.vbox.start_vm(vm_name, gui=True, cached_state=cached_state)

        # ── Post-start state updates ───────────────────────────────────
        logger.info("start_vm: '%s' launched — updating state to RUNNING", vm_name)
        self.db.update_status(vm_name, VMStatus.RUNNING)
        if uuid and self.vm_repo:
            self.vm_repo.update_state(uuid, VMState.RUNNING)
        if self._poller:
            self._poller.set_state(vm_name, "running")

    # ── Stop ───────────────────────────────────────────────────────────────

    def stop_vm(self, vm_name: str):
        """
        Stop a VM by name. Uses UUID-first path when UUID is known.
        Falls back to name-based poweroff for legacy records.
        """
        uuid = self._resolve_uuid(vm_name)

        if uuid:
            if not self.vbox.validate_vm(uuid):
                self._mark_missing(vm_name, uuid)
                logger.warning(
                    "stop_vm '%s': uuid=%s is MISSING from VBox — aborting",
                    vm_name, uuid,
                )
                return
            self.vbox.stop_vm_by_uuid(uuid, force=True)
        else:
            self.vbox.poweroff_vm(vm_name)

        # Post-stop state updates
        self.db.update_status(vm_name, VMStatus.STOPPED)
        if uuid and self.vm_repo:
            self.vm_repo.update_state(uuid, VMState.STOPPED)
        if self._poller:
            self._poller.set_state(vm_name, "stopped")

    # ── Delete ─────────────────────────────────────────────────────────────

    def delete_vm(self, vm_name: str):
        """
        Delete a VM from VirtualBox and remove from all DB stores.

        If the VM is MISSING from VBox, the DB entry is still removed
        (cleanup of stale references).
        """
        uuid = self._resolve_uuid(vm_name)

        if uuid:
            if self.vbox.validate_vm(uuid):
                try:
                    self.vbox.delete_vm_by_uuid(uuid)
                    logger.info("Deleted VM uuid=%s ('%s')", uuid, vm_name)
                except VMNotFoundException:
                    logger.warning(
                        "delete_vm '%s': uuid=%s already absent from VBox",
                        vm_name, uuid,
                    )
                except Exception as exc:
                    logger.error("delete_vm '%s': %s", vm_name, exc)
                    raise
            else:
                logger.warning(
                    "delete_vm '%s': uuid=%s MISSING from VBox — "
                    "removing DB entry only",
                    vm_name, uuid,
                )
        else:
            # Legacy name-based delete
            self.vbox.delete_vm(vm_name)

        # Remove from all stores
        self.db.remove(vm_name)
        if uuid and self.vm_repo:
            self.vm_repo.remove(uuid)
        if self._poller:
            # Remove from poller cache so it stops tracking this VM
            with self._poller._lock:
                self._poller._cache.pop(vm_name, None)

    # ── Status queries ─────────────────────────────────────────────────────

    def get_live_status(self, vm_name: str) -> VMStatus:
        """
        Return VM status using the cached poller state when available.
        Falls back to a direct `list runningvms` call if no poller is wired.
        Never calls showvminfo.
        """
        if not self.vbox_available():
            return VMStatus.UNKNOWN

        # Fast path: poller cache (instant, no subprocess)
        if self._poller is not None:
            state = self._poller.get_cached_state(vm_name)
            if state == "running":
                return VMStatus.RUNNING
            elif state == "stopped":
                return VMStatus.STOPPED
            # "unknown" → poller hasn't polled yet — fall through

        # Fallback: direct fast call (list runningvms, 5s timeout)
        try:
            state = self.vbox.get_vm_state(vm_name)
            if state == "running":
                return VMStatus.RUNNING
            elif state == "stopped":
                return VMStatus.STOPPED
        except Exception:
            pass
        return VMStatus.UNKNOWN

    def sync_all_statuses(self):
        """
        Fast bulk sync: one `list runningvms` call for ALL VMs.
        Must only be called from a background thread.
        """
        if not self.vbox_available():
            logger.warning("sync_all_statuses: VirtualBox not available")
            return

        logger.info("sync_all_statuses: starting fast bulk sync")
        t0 = time.monotonic()
        try:
            running_names: set[str] = self.vbox.list_running_names()

            for rec in self.db.all():
                if rec.vm_name in running_names:
                    self.db.update_status(rec.vm_name, VMStatus.RUNNING)
                else:
                    self.db.update_status(rec.vm_name, VMStatus.STOPPED)

            elapsed = time.monotonic() - t0
            logger.info(
                "sync_all_statuses: done in %.2fs  running=%s",
                elapsed, list(running_names),
            )
        except Exception as exc:
            logger.warning("sync_all_statuses failed: %s", exc)

    # ── Internal helpers ───────────────────────────────────────────────────

    def _resolve_uuid(self, vm_name: str) -> str:
        """
        Resolve the VirtualBox UUID for a VM name.

        Check order:
        1. VMRepository (in-memory, fast)
        2. Legacy MachinesDB (has uuid field since schema update)
        3. VBoxManage list vms (slow path — only if both above fail)

        Returns empty string if UUID cannot be determined.
        """
        # 1. VMRepository
        if self.vm_repo:
            entry = self.vm_repo.get_by_name(vm_name)
            if entry and entry.uuid:
                return entry.uuid

        # 2. Legacy MachinesDB
        rec = self.db.get(vm_name)
        if rec and rec.uuid:
            return rec.uuid

        # 3. VBoxManage (slow — resolves and stores for next time)
        try:
            found = self.vbox.get_uuid_for_name(vm_name)
            if found:
                logger.info(
                    "_resolve_uuid '%s': resolved via VBox → %s", vm_name, found
                )
                # Back-fill into legacy DB so we don't resolve again
                self.db.set_uuid(vm_name, found)
                if self.vm_repo:
                    entry = self.vm_repo.get_by_name(vm_name)
                    if entry:
                        entry.uuid = found
                        self.vm_repo.upsert(entry)
                return found
        except Exception as exc:
            logger.debug("_resolve_uuid '%s' VBox lookup failed: %s", vm_name, exc)

        return ""

    def _cached_state(self, vm_name: str) -> str | None:
        """Return cached state from poller, or None if poller unavailable."""
        if self._poller:
            return self._poller.get_cached_state(vm_name)
        return None

    def _mark_missing(self, vm_name: str, uuid: str):
        """Update DB to reflect that this VM is MISSING from VBox."""
        logger.warning("Marking VM MISSING: name='%s'  uuid=%s", vm_name, uuid)
        self.db.update_status(vm_name, VMStatus.STOPPED)  # legacy: no MISSING
        if self.vm_repo:
            self.vm_repo.mark_missing(uuid)
        if self._poller:
            self._poller.set_state(vm_name, "stopped")
