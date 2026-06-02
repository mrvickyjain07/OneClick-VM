"""
ui/workers.py
=============
All QThread worker classes for async background operations.

Section 4 — VM Launch Performance Optimization applied:
  • VMStartWorker: pre-checks VM state, launches headless or gui based on flag,
    runs in background thread — zero UI freeze.
  • State is passed from VMStatePoller cache; no redundant VBoxManage call.
  • Centralized error handling via vbox_error classification.

Section 5 — Loading state signals emitted on every worker.
Section 7 — Workers emit state changes to vm_state_manager.
"""
from PyQt5.QtCore import QThread, pyqtSignal
import sys, os, time, logging

# Ensure project root is importable
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from backend.iso_manager import ISOManager
from backend.vm_service import VMService
from models import OSTemplate, VMRecord

logger = logging.getLogger("Workers")


# ─────────────────────────────────────────────────────────────────────────────
# Base worker — common lifecycle helpers
# ─────────────────────────────────────────────────────────────────────────────

class _BaseWorker(QThread):
    """Mixin: adds cancel() and _cancelled guard."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cancelled = False

    def cancel(self):
        self._cancelled = True

    def _check_cancelled(self) -> bool:
        return self._cancelled


# ─────────────────────────────────────────────────────────────────────────────
# Download / Install / Quick Deploy
# ─────────────────────────────────────────────────────────────────────────────

class DownloadWorker(_BaseWorker):
    """Downloads an ISO file. Emits progress 0-100 and a result signal."""
    progress  = pyqtSignal(int)
    finished  = pyqtSignal(str)   # iso file path
    error     = pyqtSignal(str)

    def __init__(self, template: OSTemplate, iso_manager: ISOManager, parent=None):
        super().__init__(parent)
        self.template    = template
        self.iso_manager = iso_manager
        self._paused     = False

    def pause(self):    self._paused    = True
    def resume(self):   self._paused    = False

    def run(self):
        try:
            path = self.iso_manager.download_iso(
                url                  = self.template.iso_url,
                filename             = self.template.iso_filename,
                progress_callback    = self.progress.emit,
                pause_check_callback = lambda: self._paused,
                cancel_check_callback= lambda: self._cancelled,
            )
            if path:
                self.finished.emit(str(path))
            else:
                self.error.emit("Download cancelled.")
        except Exception as e:
            self.error.emit(str(e))


class InstallWorker(_BaseWorker):
    """Runs VBoxManage to create the full VM. Emits log lines and a result."""
    log      = pyqtSignal(str)
    finished = pyqtSignal(object)   # VMRecord
    error    = pyqtSignal(str)

    def __init__(
        self,
        vm_service: VMService,
        template: OSTemplate,
        iso_path: str,
        parent=None,
    ):
        super().__init__(parent)
        self.vm_service = vm_service
        self.template   = template
        self.iso_path   = iso_path

    def run(self):
        try:
            from pathlib import Path
            rec = self.vm_service.create_vm(
                os_id       = self.template.os_id,
                os_name     = self.template.os_name,
                os_type_id  = self.template.os_type_id,
                iso_path    = Path(self.iso_path),
                ram_mb      = self.template.ram_mb,
                cpu_count   = self.template.cpu_count,
                disk_gb     = self.template.disk_gb,
                log_callback= self.log.emit,
            )
            self.finished.emit(rec)
        except Exception as e:
            self.error.emit(str(e))


class VMActionWorker(_BaseWorker):
    """Runs a single VM action (start/stop/delete) in the background."""
    finished = pyqtSignal(str)   # success message
    error    = pyqtSignal(str)

    def __init__(self, fn, success_msg: str, parent=None):
        super().__init__(parent)
        self._fn          = fn
        self._success_msg = success_msg

    def run(self):
        try:
            self._fn()
            self.finished.emit(self._success_msg)
        except Exception as e:
            self.error.emit(str(e))


class QuickDeployWorker(_BaseWorker):
    """
    One-click deploy: Download ISO (if needed) → Create VM → optionally launch.
    Emits granular stage + progress signals so the dialog can show live feedback.
    """
    stage    = pyqtSignal(str)   # human-readable status text
    progress = pyqtSignal(int)   # 0-100 overall percent
    finished = pyqtSignal(object)  # VMRecord on success
    error    = pyqtSignal(str)

    def __init__(
        self,
        template,
        iso_manager,
        vm_service,
        ram_mb:   int,
        cpu_count: int,
        disk_gb:  int,
        auto_launch: bool = False,
        parent=None,
    ):
        super().__init__(parent)
        self.template    = template
        self.iso_manager = iso_manager
        self.vm_service  = vm_service
        self.ram_mb      = ram_mb
        self.cpu_count   = cpu_count
        self.disk_gb     = disk_gb
        self.auto_launch = auto_launch
        self._paused     = False

    def pause(self):  self._paused = True
    def resume(self): self._paused = False

    def run(self):
        try:
            from pathlib import Path

            # ── Stage 1: Download (0-60%) ────────────────────────────────
            if self.iso_manager.is_downloaded(self.template.iso_filename):
                self.stage.emit("ISO already cached — skipping download…")
                self.progress.emit(60)
                iso_path = self.iso_manager.get_iso_path(self.template.iso_filename)
            else:
                self.stage.emit(f"Downloading {self.template.os_name} ISO…")

                def _dl_progress(pct: int):
                    self.progress.emit(int(pct * 0.60))

                iso_path = self.iso_manager.download_iso(
                    url                  = self.template.iso_url,
                    filename             = self.template.iso_filename,
                    progress_callback    = _dl_progress,
                    pause_check_callback = lambda: self._paused,
                    cancel_check_callback= lambda: self._cancelled,
                )
                if iso_path is None:
                    self.error.emit("Download cancelled.")
                    return

            if self._cancelled:
                self.error.emit("Cancelled by user.")
                return

            # ── Stage 2: Create VM (60-90%) ──────────────────────────────
            self.stage.emit("Creating virtual machine…")
            self.progress.emit(65)

            rec = self.vm_service.create_vm(
                os_id      = self.template.os_id,
                os_name    = self.template.os_name,
                os_type_id = self.template.os_type_id,
                iso_path   = Path(iso_path),
                ram_mb     = self.ram_mb,
                cpu_count  = self.cpu_count,
                disk_gb    = self.disk_gb,
                log_callback = self.stage.emit,
            )
            self.progress.emit(90)

            # ── Stage 3: Launch (90-100%) ────────────────────────────────
            if self.auto_launch:
                self.stage.emit(f"Launching '{rec.vm_name}'…")
                self.vm_service.start_vm(rec.vm_name)

            self.progress.emit(100)
            self.stage.emit("Done!")
            self.finished.emit(rec)

        except Exception as e:
            self.error.emit(str(e))


class ISOVMCreateWorker(_BaseWorker):
    """
    Creates a VM from a locally stored ISO (ISO Manager flow).
    Differs from QuickDeployWorker: ISO already on disk — no download step.
    Sets DVD-first boot order so the guest boots straight into the installer.
    """
    stage    = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(object)   # VMRecord
    error    = pyqtSignal(str)

    def __init__(
        self,
        vm_service,
        iso_path:   str,
        os_id:      str,
        os_name:    str,
        os_type_id: str,
        vm_name:    str,
        ram_mb:     int,
        cpu_count:  int,
        disk_gb:    int,
        auto_launch: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self.vm_service  = vm_service
        self.iso_path    = iso_path
        self.os_id       = os_id
        self.os_name     = os_name
        self.os_type_id  = os_type_id
        self.vm_name     = vm_name
        self.ram_mb      = ram_mb
        self.cpu_count   = cpu_count
        self.disk_gb     = disk_gb
        self.auto_launch = auto_launch

    def run(self):
        try:
            from pathlib import Path

            self.stage.emit("Validating ISO file…")
            self.progress.emit(5)
            iso_path = Path(self.iso_path)
            if not iso_path.exists():
                self.error.emit(f"ISO file not found:\n{self.iso_path}")
                return

            logger.info(
                "ISOVMCreateWorker: START  vm='%s'  iso='%s'  "
                "os_type=%s  ram=%d  cpu=%d  disk=%d",
                self.vm_name, self.iso_path,
                self.os_type_id, self.ram_mb, self.cpu_count, self.disk_gb,
            )

            self.stage.emit(f"Creating VM '{self.vm_name}'…")
            self.progress.emit(10)

            stages_log = []
            def _log(msg: str):
                stages_log.append(msg)
                self.stage.emit(msg)
                done = min(75, 10 + len(stages_log) * 9)
                self.progress.emit(done)

            rec = self.vm_service.create_vm(
                os_id        = self.os_id,
                os_name      = self.os_name,
                os_type_id   = self.os_type_id,
                iso_path     = iso_path,
                ram_mb       = self.ram_mb,
                cpu_count    = self.cpu_count,
                disk_gb      = self.disk_gb,
                log_callback = _log,
                vm_name_override = self.vm_name,
            )
            logger.info(
                "ISOVMCreateWorker: create_vm complete  vm='%s'  uuid=%s",
                rec.vm_name, getattr(rec, 'uuid', '?'),
            )

            self.stage.emit("Setting boot order: DVD \u2192 Disk…")
            self.progress.emit(78)
            self.vm_service.vbox.set_boot_order(
                rec.vm_name, boot1="dvd", boot2="disk"
            )
            logger.info("ISOVMCreateWorker: boot order set (dvd, disk) for '%s'", rec.vm_name)

            if self.auto_launch:
                # Give VBox ~1.5 s to release internal locks after disk/ISO ops
                self.stage.emit("Finalising VM configuration…")
                self.progress.emit(82)
                import time as _t; _t.sleep(1.5)

                self.stage.emit(f"Starting '{rec.vm_name}'…")
                self.progress.emit(88)
                logger.info(
                    "ISOVMCreateWorker: calling start_vm for '%s'", rec.vm_name
                )
                self.vm_service.start_vm(rec.vm_name)
                logger.info(
                    "ISOVMCreateWorker: start_vm returned — VM is running: '%s'",
                    rec.vm_name,
                )

            self.progress.emit(100)
            self.stage.emit("VM ready!")
            self.finished.emit(rec)

        except Exception as e:
            logger.error(
                "ISOVMCreateWorker FAILED for vm='%s': %s",
                self.vm_name, e, exc_info=True,
            )
            self.error.emit(str(e))


# ─────────────────────────────────────────────────────────────────────────────
# VM START WORKER (Section 4 — Performance optimised VM launch)
# ─────────────────────────────────────────────────────────────────────────────

class VMStartWorker(_BaseWorker):
    """
    Async VM start worker.

    Optimisations
    -------------
    1. Pre-validate VM state from cached_state (avoids extra VBox call).
    2. Support headless mode for faster startup without GUI overhead.
    3. Full async — UI never freezes.
    4. Emits state updates to vm_state_manager singleton.

    Signals
    -------
    stage(str)       human-readable status line
    finished(str)    vm_name on success
    error(str)       error message on failure
    """
    stage    = pyqtSignal(str)
    finished = pyqtSignal(str)   # vm_name
    error    = pyqtSignal(str)

    def __init__(
        self,
        vm_service,
        vm_name:      str,
        headless:     bool = False,
        cached_state: str  = "",
        parent=None,
    ):
        super().__init__(parent)
        self.vm_service   = vm_service
        self.vm_name      = vm_name
        self.headless     = headless
        self.cached_state = cached_state

    def run(self):
        from ui.state_manager import vm_state_manager

        try:
            vm_state_manager.set_vm_busy(self.vm_name, True)

            # ── 1. Pre-check: use cached state if available ───────────────
            state = self.cached_state or self.vm_service.vbox.get_vm_state(self.vm_name)
            self.stage.emit(f"VM state: {state}")

            if state == "running":
                self.stage.emit(f"'{self.vm_name}' is already running.")
                self.finished.emit(self.vm_name)
                return

            # ── 2. Launch in separate (windowed) or headless mode ─────────
            mode = "headless" if self.headless else "separate"
            self.stage.emit(f"Starting '{self.vm_name}' ({mode} mode)…")

            # Use UUID-first start if uuid is available
            vbox = self.vm_service.vbox
            uuid = None
            if hasattr(self.vm_service, 'vm_repo') and self.vm_service.vm_repo:
                entry = self.vm_service.vm_repo.get_by_name(self.vm_name)
                uuid  = entry.uuid if entry else None

            if uuid:
                logger.info("VMStartWorker: starting by uuid=%s headless=%s", uuid, self.headless)
                vbox.start_vm_by_uuid(uuid, gui=not self.headless)
            else:
                logger.info("VMStartWorker: starting by name='%s' headless=%s", self.vm_name, self.headless)
                vbox.start_vm(self.vm_name, gui=not self.headless, cached_state=state)

            # ── 3. Update state manager ───────────────────────────────────
            vm_state_manager.set_vm_state(self.vm_name, "running")
            self.stage.emit(f"'{self.vm_name}' started successfully.")
            self.finished.emit(self.vm_name)

        except Exception as e:
            logger.error("VMStartWorker error for '%s': %s", self.vm_name, e)
            try:
                from ui.state_manager import vm_state_manager
                vm_state_manager.set_vm_state(self.vm_name, "unknown")
            except Exception:
                pass
            self.error.emit(str(e))
        finally:
            try:
                from ui.state_manager import vm_state_manager
                vm_state_manager.set_vm_busy(self.vm_name, False)
            except Exception:
                pass


class VMStopWorker(_BaseWorker):
    """
    Async VM stop worker.
    Emits state updates to vm_state_manager.
    """
    stage    = pyqtSignal(str)
    finished = pyqtSignal(str)   # vm_name
    error    = pyqtSignal(str)

    def __init__(self, vm_service, vm_name: str, force: bool = False, parent=None):
        super().__init__(parent)
        self.vm_service = vm_service
        self.vm_name    = vm_name
        self.force      = force

    def run(self):
        from ui.state_manager import vm_state_manager
        try:
            vm_state_manager.set_vm_busy(self.vm_name, True)
            self.stage.emit(f"Stopping '{self.vm_name}'…")

            vbox = self.vm_service.vbox
            uuid = None
            if hasattr(self.vm_service, 'vm_repo') and self.vm_service.vm_repo:
                entry = self.vm_service.vm_repo.get_by_name(self.vm_name)
                uuid  = entry.uuid if entry else None

            if uuid:
                vbox.stop_vm_by_uuid(uuid, force=self.force)
            else:
                if self.force:
                    vbox.poweroff_vm(self.vm_name)
                else:
                    vbox.stop_vm(self.vm_name)

            vm_state_manager.set_vm_state(self.vm_name, "stopped")
            self.stage.emit(f"'{self.vm_name}' stopped.")
            self.finished.emit(self.vm_name)

        except Exception as e:
            logger.error("VMStopWorker error for '%s': %s", self.vm_name, e)
            self.error.emit(str(e))
        finally:
            try:
                from ui.state_manager import vm_state_manager
                vm_state_manager.set_vm_busy(self.vm_name, False)
            except Exception:
                pass


# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOT WORKERS
# ─────────────────────────────────────────────────────────────────────────────

class SnapshotCreateWorker(_BaseWorker):
    """
    Takes a VM snapshot in a background thread.

    Retry logic
    -----------
    If VBoxManage returns a "locked" / "busy" error the worker waits 5 s
    and retries once before giving up.
    """
    stage    = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(object)   # SnapshotRecord
    error    = pyqtSignal(str)

    MAX_RETRIES = 2
    RETRY_DELAY = 5   # seconds between retries on lock errors

    def __init__(self, snap_service, rec, parent=None):
        super().__init__(parent)
        self.snap_service = snap_service
        self.rec          = rec

    def run(self):
        rec = self.rec
        self.stage.emit(f"Preparing snapshot '{rec.snapshot_name}'…")
        self.progress.emit(5)

        # ── Validate VM exists ────────────────────────────────────────────
        vbox = self.snap_service.vbox
        try:
            state = vbox.get_vm_state(rec.vm_name)
            self.stage.emit(
                f"VM '{rec.vm_name}' is {state}. "
                f"{'Live snapshot (RAM will be saved).' if rec.has_memory and state=='running' else 'Taking offline snapshot.'}"
            )
            self.progress.emit(15)
        except Exception as e:
            self.error.emit(f"Cannot read VM state: {e}")
            return

        # ── Execute with retry on lock errors ─────────────────────────────
        last_err = None
        for attempt in range(1, self.MAX_RETRIES + 1):
            if attempt > 1:
                self.stage.emit(
                    f"VM appears locked. Retrying in {self.RETRY_DELAY}s… "
                    f"(attempt {attempt}/{self.MAX_RETRIES})"
                )
                time.sleep(self.RETRY_DELAY)

            self.stage.emit(
                "Communicating with VirtualBox… "
                "(live snapshots may take 1–3 minutes)"
            )
            self.progress.emit(30 + attempt * 5)

            try:
                result = self.snap_service.execute_snapshot(rec)
                self.progress.emit(95)
                self.stage.emit("Snapshot saved ✓")
                self.progress.emit(100)
                self.finished.emit(result)
                return

            except RuntimeError as e:
                last_err = str(e)
                err_lower = last_err.lower()
                if "locked" in err_lower or "busy" in err_lower or "in use" in err_lower:
                    continue   # retry
                break          # non-retryable error

            except Exception as e:
                last_err = str(e)
                break

        logger.error("SnapshotCreateWorker failed: %s", last_err)
        self.error.emit(last_err or "Unknown error during snapshot creation")


class SnapshotRestoreWorker(_BaseWorker):
    """
    Restores a VM to a snapshot.
    Powers off the VM first if running, then calls VBoxManage snapshot restore.
    """
    stage    = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(object)   # SnapshotRecord
    error    = pyqtSignal(str)

    def __init__(self, snap_service, snap_id: str,
                 auto_start: bool = True, parent=None):
        super().__init__(parent)
        self.snap_service = snap_service
        self.snap_id      = snap_id
        self.auto_start   = auto_start

    def run(self):
        try:
            rec = self.snap_service.get(self.snap_id)
            if not rec:
                self.error.emit("Snapshot record not found.")
                return

            self.stage.emit(f"Checking VM state for '{rec.vm_name}'…")
            self.progress.emit(10)

            state = self.snap_service.vbox.get_vm_state(rec.vm_name)
            if state == "running":
                self.stage.emit(f"Stopping VM '{rec.vm_name}'…")
                self.progress.emit(20)

            self.stage.emit(f"Restoring to snapshot '{rec.snapshot_name}'…")
            self.progress.emit(40)

            result = self.snap_service.restore(
                self.snap_id, auto_start=self.auto_start
            )

            self.progress.emit(90)
            if self.auto_start:
                self.stage.emit("VM restarted — switching to Console…")
            else:
                self.stage.emit("Restore complete.")
            self.progress.emit(100)
            self.finished.emit(result)

        except Exception as e:
            self.error.emit(str(e))


class SnapshotDeleteWorker(_BaseWorker):
    """
    Deletes a snapshot and merges its disk delta into the parent.
    This can be slow (minutes) for large disks — do NOT run on UI thread.

    Handles:
    - Orphaned snapshots: removes metadata only, no VBox call.
    - VM running: SnapshotService pre-validates and raises VMNotFoundException.
    - Emits error signal on failure so UI can display user-friendly message.
    """
    stage    = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)   # snap_id
    error    = pyqtSignal(str)

    def __init__(self, snap_service, snap_id: str, parent=None):
        super().__init__(parent)
        self.snap_service = snap_service
        self.snap_id      = snap_id

    def run(self):
        try:
            rec = self.snap_service.get(self.snap_id)
            if not rec:
                self.error.emit("Snapshot not found.")
                return

            if rec.status == "orphaned":
                self.stage.emit(f"Removing orphaned metadata for '{rec.snapshot_name}'…")
                self.progress.emit(50)
                # Metadata-only removal — VBox call skipped in SnapshotService.delete()
                self.snap_service.delete(self.snap_id)
                self.progress.emit(100)
                self.stage.emit("Orphaned record removed.")
                self.finished.emit(self.snap_id)
                return

            self.stage.emit(
                f"Deleting '{rec.snapshot_name}' and merging disk delta…\n"
                f"(This may take several minutes for large disks)"
            )
            self.progress.emit(20)

            self.snap_service.delete(self.snap_id)

            self.progress.emit(100)
            self.stage.emit("Snapshot deleted.")
            self.finished.emit(self.snap_id)

        except Exception as e:
            logger.error("SnapshotDeleteWorker failed for snap_id=%s: %s", self.snap_id, e)
            self.error.emit(str(e))


class SnapshotExportWorker(_BaseWorker):
    """
    Exports the VM (with all snapshots) as an OVA file.
    Large VMs may take several minutes.
    """
    stage    = pyqtSignal(str)
    progress = pyqtSignal(int)
    finished = pyqtSignal(str)   # output path
    error    = pyqtSignal(str)

    def __init__(self, snap_service, snap_id: str,
                 output_path: str, parent=None):
        super().__init__(parent)
        self.snap_service = snap_service
        self.snap_id      = snap_id
        self.output_path  = output_path

    def run(self):
        try:
            rec = self.snap_service.get(self.snap_id)
            if not rec:
                self.error.emit("Snapshot not found.")
                return

            self.stage.emit(
                f"Exporting VM '{rec.vm_name}' → {self.output_path}\n"
                f"(This may take several minutes for large VMs…)"
            )
            self.progress.emit(10)

            self.snap_service.export(self.snap_id, self.output_path)

            self.progress.emit(100)
            self.stage.emit("Export complete.")
            self.finished.emit(self.output_path)

        except Exception as e:
            self.error.emit(str(e))
