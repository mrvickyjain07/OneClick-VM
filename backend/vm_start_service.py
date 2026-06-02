"""
backend/vm_start_service.py
===========================
Non-blocking VM start orchestration with retry, stale-process cleanup,
and per-VM state polling.

Design
------
- VMStartWorker: QThread that starts a single VM non-blocking, polls its
  state, and emits typed signals back to the UI.
- VMStartService: factory / registry — creates workers, prevents duplicates,
  tracks active starts.

Signal flow (per VM)
--------------------
  start_requested → VMStartWorker created & started
  ↓
  vm_starting(vm_name)          — emitted immediately
  ↓  [subprocess.Popen startvm --type separate]
  ↓  [poll VBoxManage list runningvms every 1 s, timeout 120 s]
  ↓
  vm_running(vm_name)   — success path
  vm_failed(vm_name, reason)  — failure path (all retries exhausted)

Retry logic
-----------
  Max 2 retries on failure.
  Before each retry:
    1. Kill stale VirtualBoxVM.exe / VBoxHeadless.exe processes (Windows).
    2. Wait 2 s.
    3. Re-issue startvm.
"""
import subprocess
import time
import logging
import os

from PyQt5.QtCore import QThread, pyqtSignal

_log = logging.getLogger("VMStartService")

# Windows: suppress console flash
_NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_STALE_PROCESS_NAMES = ["VirtualBoxVM.exe", "VBoxHeadless.exe"]

POLL_INTERVAL_S = 1.0    # seconds between state polls
START_TIMEOUT_S = 120    # seconds before we give up waiting for "running"
MAX_RETRIES     = 2      # retry attempts after first failure


def _find_vboxmanage() -> str:
    """Locate VBoxManage executable."""
    import shutil
    if shutil.which("VBoxManage"):
        return "VBoxManage"
    candidates = [
        r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe",
        r"C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe",
    ]
    for c in candidates:
        if os.path.exists(c):
            return c
    return "VBoxManage"   # will fail loudly if not found


def _kill_stale_vm_processes():
    """
    Kill any lingering VirtualBoxVM.exe / VBoxHeadless.exe processes.
    Best-effort — logs but never raises.
    """
    try:
        import psutil
        killed = []
        for proc in psutil.process_iter(["pid", "name"]):
            try:
                pname = proc.info["name"] or ""
                if pname in _STALE_PROCESS_NAMES:
                    proc.kill()
                    killed.append(pname)
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        if killed:
            _log.warning("Killed stale VM processes: %s", killed)
    except ImportError:
        # psutil not available — fall back to taskkill
        for pname in _STALE_PROCESS_NAMES:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/IM", pname],
                    creationflags=_NO_WINDOW,
                    timeout=5,
                    capture_output=True,
                )
            except Exception:
                pass
    except Exception as exc:
        _log.debug("_kill_stale_vm_processes: %s", exc)


def _is_vm_running(vboxmanage: str, identifier: str) -> bool:
    """
    Return True if identifier (name or uuid) is in `list runningvms`.
    Never raises.
    """
    try:
        result = subprocess.run(
            [vboxmanage, "list", "runningvms"],
            capture_output=True, text=True,
            creationflags=_NO_WINDOW, timeout=5,
        )
        return identifier.lower() in result.stdout.lower()
    except Exception:
        return False


class VMStartWorker(QThread):
    """
    QThread that starts a single VM non-blocking, polls its state,
    and emits signals.

    Signals
    -------
    vm_starting(vm_name)        — fired immediately, before startvm
    vm_running(vm_name)         — VM reached 'running' state
    vm_failed(vm_name, reason)  — all retries exhausted
    status_update(vm_name, msg) — human-readable progress messages
    """
    vm_starting    = pyqtSignal(str)          # vm_name
    vm_running     = pyqtSignal(str)          # vm_name
    vm_failed      = pyqtSignal(str, str)     # vm_name, reason
    status_update  = pyqtSignal(str, str)     # vm_name, message

    def __init__(self, vm_name: str, vm_uuid: str = "", parent=None):
        super().__init__(parent)
        self.vm_name     = vm_name
        self.vm_uuid     = vm_uuid          # UUID preferred for startvm
        self._stop       = False
        self._vboxmanage = _find_vboxmanage()
        self.setObjectName(f"VMStartWorker-{vm_name}")

    def request_stop(self):
        self._stop = True

    # ── QThread entry ─────────────────────────────────────────────────────

    def run(self):
        _log.info("[%s] VMStartWorker starting", self.vm_name)
        self.vm_starting.emit(self.vm_name)
        self._emit_status("Initializing VM start…")

        identifier = self.vm_uuid or self.vm_name
        last_error = "Unknown error"

        for attempt in range(1, MAX_RETRIES + 2):   # 1 initial + 2 retries
            if self._stop:
                _log.info("[%s] stop requested — aborting", self.vm_name)
                return

            if attempt > 1:
                self._emit_status(f"Retry {attempt - 1}/{MAX_RETRIES} — cleaning stale processes…")
                _log.warning("[%s] Retry %d — killing stale VM processes", self.vm_name, attempt - 1)
                _kill_stale_vm_processes()
                time.sleep(2)

            # ── Issue startvm (non-blocking Popen) ────────────────────
            self._emit_status("Issuing startvm command…")
            _log.info("[%s] startvm (attempt %d) identifier=%s", self.vm_name, attempt, identifier)

            try:
                proc = subprocess.Popen(
                    [self._vboxmanage, "startvm", identifier, "--type", "separate"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    creationflags=_NO_WINDOW,
                )
            except Exception as exc:
                last_error = f"Failed to launch VBoxManage: {exc}"
                _log.error("[%s] %s", self.vm_name, last_error)
                continue   # retry

            # Wait for startvm process to exit (fast — separate mode exits quickly)
            try:
                stdout, stderr = proc.communicate(timeout=30)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.communicate()
                last_error = "startvm process timed out after 30s"
                _log.error("[%s] %s", self.vm_name, last_error)
                continue

            if proc.returncode != 0:
                last_error = stderr.strip() or f"startvm rc={proc.returncode}"
                _log.error("[%s] startvm rc=%d: %s", self.vm_name, proc.returncode, last_error)
                continue

            _log.info("[%s] startvm rc=0 — polling for running state…", self.vm_name)
            self._emit_status("VM launching… polling for running state")

            # ── Poll for 'running' state ───────────────────────────────
            if self._poll_until_running(identifier):
                _log.info("[%s] VM reached 'running' state ✓", self.vm_name)
                self._emit_status("VM is running!")
                self.vm_running.emit(self.vm_name)
                return

            last_error = f"VM did not reach 'running' state within {START_TIMEOUT_S}s"
            _log.warning("[%s] %s", self.vm_name, last_error)
            # Loop → retry

        # All retries exhausted
        _log.error("[%s] All attempts failed. Last error: %s", self.vm_name, last_error)
        self.vm_failed.emit(self.vm_name, last_error)

    # ── Helpers ───────────────────────────────────────────────────────────

    def _poll_until_running(self, identifier: str) -> bool:
        """Poll `list runningvms` until VM is running or timeout."""
        deadline = time.time() + START_TIMEOUT_S
        elapsed  = 0
        while not self._stop and time.time() < deadline:
            if _is_vm_running(self._vboxmanage, identifier):
                return True
            time.sleep(POLL_INTERVAL_S)
            elapsed += POLL_INTERVAL_S
            if int(elapsed) % 10 == 0:
                self._emit_status(f"Waiting for VM to start… ({int(elapsed)}s)")
        return False

    def _emit_status(self, msg: str):
        self.status_update.emit(self.vm_name, msg)


# ─────────────────────────────────────────────────────────────────────────────
# Service (factory + registry)
# ─────────────────────────────────────────────────────────────────────────────

class VMStartService:
    """
    Factory and registry for VMStartWorker instances.

    Prevents duplicate start workers for the same VM.
    All created workers are tracked so callers can check if a start is in
    progress and so the application can drain them on shutdown.
    """

    def __init__(self):
        # vm_name → VMStartWorker (only while running)
        self._active: dict[str, VMStartWorker] = {}

    def is_starting(self, vm_name: str) -> bool:
        """Return True if a start worker is currently active for this VM."""
        w = self._active.get(vm_name)
        return w is not None and w.isRunning()

    def start_vm(
        self,
        vm_name: str,
        vm_uuid: str = "",
        on_starting=None,
        on_running=None,
        on_failed=None,
        on_status=None,
        parent=None,
    ) -> VMStartWorker:
        """
        Start a VM asynchronously.

        If a worker for this VM is already running, returns the existing one
        (no duplicate starts).

        Parameters
        ----------
        vm_name   : display name
        vm_uuid   : VBox UUID (preferred over name for startvm)
        on_starting : callable(vm_name) — called immediately
        on_running  : callable(vm_name) — called when running
        on_failed   : callable(vm_name, reason)
        on_status   : callable(vm_name, message)
        parent      : QObject parent for the worker thread

        Returns
        -------
        VMStartWorker
        """
        # Reuse existing worker if still running
        existing = self._active.get(vm_name)
        if existing and existing.isRunning():
            _log.info("[%s] Start already in progress — reusing worker", vm_name)
            return existing

        _log.info("[%s] VMStartService.start_vm uuid=%s", vm_name, vm_uuid or "(none)")
        worker = VMStartWorker(vm_name, vm_uuid, parent=parent)

        if on_starting:
            worker.vm_starting.connect(on_starting)
        if on_running:
            worker.vm_running.connect(on_running)
        if on_failed:
            worker.vm_failed.connect(on_failed)
        if on_status:
            worker.status_update.connect(on_status)

        # Auto-cleanup on finish
        worker.finished.connect(lambda: self._on_worker_finished(vm_name))

        self._active[vm_name] = worker
        worker.start()
        return worker

    def cancel(self, vm_name: str):
        """Request stop for an active start worker."""
        w = self._active.get(vm_name)
        if w and w.isRunning():
            _log.info("[%s] VMStartService: cancelling start", vm_name)
            w.request_stop()

    def drain(self, timeout_ms: int = 3000):
        """Wait for all active workers to finish (called on app shutdown)."""
        for vm_name, w in list(self._active.items()):
            if w.isRunning():
                w.request_stop()
                w.wait(timeout_ms)

    def _on_worker_finished(self, vm_name: str):
        self._active.pop(vm_name, None)
        _log.debug("[%s] VMStartWorker finished and removed from registry", vm_name)
