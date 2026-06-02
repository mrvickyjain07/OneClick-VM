"""
ui/app.py
=========
Main FluentWindow application shell.
Wires all services, pages, and navigation together.

Startup sequence (order matters)
---------------------------------
1.  Config + directories
2.  VBoxEngine  (shared singleton)
3.  MachinesDB  (legacy cache — kept for widget compat)
4.  VMRepository  (UUID-keyed authoritative cache)  ← NEW
5.  SnapshotRepository
6.  VMService  (lifecycle — UUID-first)
7.  SnapshotService  (snapshot lifecycle — pre-validates VM)
8.  VMStatePoller  (background thread — UUID + name caches)
9.  VMSyncWorker  (one-shot QThread: runs startup sync, then exits)  ← NEW
10. Pages + navigation
"""
import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)

from PyQt5.QtCore    import Qt, QThread, pyqtSignal
from PyQt5.QtGui     import QIcon
from qfluentwidgets  import (
    FluentWindow, NavigationItemPosition, FluentIcon as FIF,
    setTheme, Theme,
)

from backend                     import config
from backend.vbox_engine         import VBoxEngine
from backend.iso_manager         import ISOManager
from backend.iso_repository      import ISORepository
from backend.iso_service         import ISOService
from backend.machines_db         import MachinesDB
from backend.vm_repository       import VMRepository
from backend.vm_service          import VMService
from backend.vm_session_manager  import VMSessionManager
from backend.vm_state_poller     import VMStatePoller
from backend.snapshot_repository import SnapshotRepository
from backend.snapshot_service    import SnapshotService
from backend.vm_sync_service     import VMSyncService, SyncResult
from backend.logger              import get_logger

from ui.pages.dashboard_page    import DashboardPage
from ui.pages.marketplace_page  import MarketplacePage
from ui.pages.machines_page     import MachinesPage
from ui.pages.console_page      import ConsolePage
from ui.pages.settings_page     import SettingsPage
from ui.pages.iso_manager_page  import ISOManagerPage
from ui.pages.snapshots_page    import SnapshotsPage
from ui.notification_manager   import notify
from ui.state_manager          import vm_state_manager

logger = get_logger("App")


# ─────────────────────────────────────────────────────────────────────────────
# Startup sync worker
# ─────────────────────────────────────────────────────────────────────────────

class VMSyncWorker(QThread):
    """
    One-shot background thread: runs VMSyncService.sync() at startup,
    then emits sync_complete and exits.

    This ensures the very first UI render never blocks on VBoxManage.
    """
    sync_complete = pyqtSignal(object)   # SyncResult

    def __init__(self, sync_service: VMSyncService, parent=None):
        super().__init__(parent)
        self._svc = sync_service
        self.setObjectName("VMSyncWorker")

    def run(self):
        logger.info("VMSyncWorker: starting startup sync …")
        result = self._svc.sync()
        logger.info("VMSyncWorker: %s", result.summary())
        self.sync_complete.emit(result)


# ─────────────────────────────────────────────────────────────────────────────
# Main window
# ─────────────────────────────────────────────────────────────────────────────

class VMPlatformWindow(FluentWindow):
    def __init__(self):
        super().__init__()
        setTheme(Theme.DARK)

        self.setWindowTitle("VM Platform — Marketplace")
        self.setMinimumSize(1100, 720)
        self.resize(1280, 800)

        # Global worker registry — prevents GC and enables graceful shutdown
        self._active_workers: list = []

        # Wire notification manager so toast parent is always this window
        notify.set_parent(self)

        # ── 1. Config ────────────────────────────────────────────────────
        config.ensure_directories()

        # ── 2. Shared VBoxEngine singleton ───────────────────────────────
        self._vbox = VBoxEngine()
        if not self._vbox.is_virtualbox_installed():
            logger.warning("VirtualBox not detected — VM operations will fail gracefully.")

        # ── 3. Legacy MachinesDB (kept for widget backward compat) ────────
        self._machines_db = MachinesDB(config.CACHE_DIR / "machines.json")

        # ── 4. VMRepository — UUID-keyed authoritative cache ─────────────
        self._vm_repo = VMRepository(config.VM_REPO_PATH)

        # ── 5. SnapshotRepository ─────────────────────────────────────────
        _snap_repo = SnapshotRepository(config.SNAPSHOT_DB_PATH)

        # ── 6. VMService — UUID-first lifecycle ───────────────────────────
        self._vm_service = VMService(
            machines_db = self._machines_db,
            vm_data_dir = config.VM_DATA_DIR,
            vm_repo     = self._vm_repo,
        )

        # ── 7. SnapshotService — pre-validates VM before every VBox call ──
        self._snap_service = SnapshotService(
            repo        = _snap_repo,
            machines_db = self._machines_db,
            vm_repo     = self._vm_repo,
        )

        # ── 8. VMStatePoller — UUID-aware background state tracker ────────
        self._state_poller = VMStatePoller(
            self._vbox, self._machines_db, parent=self
        )
        # Inject poller into VMService so start/stop can do optimistic updates
        self._vm_service.set_poller(self._state_poller)

        self._state_poller.states_updated.connect(self._on_states_updated)
        self._state_poller.vm_missing_detected.connect(self._on_vms_missing)
        self._state_poller.start()

        # ── 9. Startup sync (background, non-blocking) ────────────────────
        _sync_svc = VMSyncService(
            vbox        = self._vbox,
            repo        = self._vm_repo,
            snap_repo   = _snap_repo,
            machines_db = self._machines_db,
        )
        self._sync_worker = VMSyncWorker(_sync_svc, parent=self)
        self._sync_worker.sync_complete.connect(self._on_startup_sync_complete)
        self._sync_worker.start()

        # ── ISO services ──────────────────────────────────────────────────
        self._iso_manager = ISOManager(config.ISO_CACHE_DIR)
        _iso_repo         = ISORepository(config.ISO_DB_PATH)
        self._iso_service = ISOService(_iso_repo, config.ISO_LIBRARY_DIR)

        # ── 10. Pages ─────────────────────────────────────────────────────
        self._dashboard        = DashboardPage(self._vm_service, self._machines_db)
        self._marketplace      = MarketplacePage(self._iso_manager, self._vm_service)
        self._machines         = MachinesPage(self._vm_service, self._machines_db)
        self._console          = ConsolePage()
        self._console.set_vm_repo(self._vm_repo)
        self._iso_manager_page = ISOManagerPage(
            self._iso_service, self._machines_db, self._vm_service,
        )
        self._snapshots_page   = SnapshotsPage(self._snap_service)
        self._settings         = SettingsPage()

        # Give dashboard access to iso_manager for Quick Launch
        self._dashboard.set_iso_manager(self._iso_manager)

        # ── Signal wiring ─────────────────────────────────────────────────
        self._machines.vm_launched.connect(self._on_vm_launched)
        self._dashboard.vm_launched.connect(self._on_vm_launched)
        self._iso_manager_page.vm_launched.connect(self._on_vm_launched)
        self._snapshots_page.vm_launched.connect(self._on_vm_launched)

        # Dashboard navigation shortcuts (banner CTAs + Quick Action buttons)
        self._dashboard.navigate_to_marketplace.connect(
            lambda: self.switchTo(self._marketplace)
        )
        self._dashboard.navigate_to_machines.connect(
            lambda: self.switchTo(self._machines)
        )

        self._machines.snapshot_requested.connect(
            lambda vm: (
                self.switchTo(self._snapshots_page),
                self._snapshots_page.take_snapshot_for_vm(vm),
            )
        )

        # ── Object names (for testing) ────────────────────────────────────
        self._dashboard.setObjectName("DashboardPage")
        self._marketplace.setObjectName("MarketplacePage")
        self._machines.setObjectName("MachinesPage")
        self._console.setObjectName("ConsolePage")
        self._iso_manager_page.setObjectName("ISOManagerPage")
        self._snapshots_page.setObjectName("SnapshotsPage")
        self._settings.setObjectName("SettingsPage")

        # ── Navigation ────────────────────────────────────────────────────
        self.addSubInterface(self._dashboard,        FIF.HOME,           "Dashboard")
        self.addSubInterface(self._marketplace,      FIF.CLOUD,          "Marketplace")
        self.addSubInterface(self._machines,         FIF.IOT,            "My Machines")
        self.addSubInterface(self._console,          FIF.COMMAND_PROMPT, "Console")
        self.addSubInterface(self._iso_manager_page, FIF.FOLDER,         "ISO Manager")
        self.addSubInterface(self._snapshots_page,   FIF.HISTORY,        "Snapshots")

        self.navigationInterface.addSeparator()
        self.addSubInterface(
            self._settings, FIF.SETTING, "Settings",
            position=NavigationItemPosition.BOTTOM,
        )

    # ── Signal handlers ───────────────────────────────────────────────────────

    def _on_vm_launched(self, vm_name: str):
        """Called when any page launches a VM — switch to Console and attach."""
        self.switchTo(self._console)
        # Resolve UUID so the non-blocking start worker uses it
        vm_uuid = ""
        try:
            entry = self._vm_repo.get_by_name(vm_name)
            if entry:
                vm_uuid = entry.uuid or ""
        except Exception:
            pass
        self._console.attach_vm(vm_name, vm_uuid=vm_uuid)

    def _on_states_updated(self, states: dict):
        """
        Called by VMStatePoller when VM states change.
        Updates:
          1. Central vm_state_manager (single source of truth)
          2. Legacy MachinesDB + VMRepository for backward compat
          3. Refreshes pages if anything changed

        states: {vm_name: "running" | "stopped" | "missing" | "unknown"}
        """
        from models import VMStatus, VMState

        # 1. Push into central state manager (broadcast to all listeners)
        vm_state_manager.bulk_update(states)

        changed = False

        for vm_name, state_str in states.items():
            # Map to legacy VMStatus
            if state_str == "running":
                st = VMStatus.RUNNING
            elif state_str == "stopped":
                st = VMStatus.STOPPED
            else:
                st = VMStatus.UNKNOWN

            rec = self._machines_db.get(vm_name)
            if rec and rec.status != st:
                self._machines_db.update_status(vm_name, st)
                changed = True

            # Also update VMRepository with precise state
            entry = self._vm_repo.get_by_name(vm_name)
            if entry:
                try:
                    new_state = VMState(state_str)
                except ValueError:
                    new_state = VMState.UNKNOWN
                if entry.vm_state != new_state:
                    self._vm_repo.update_state(entry.uuid, new_state)
                    changed = True

        if changed:
            if hasattr(self._dashboard, "refresh"):
                self._dashboard.refresh()
            if hasattr(self._machines, "refresh"):
                self._machines.refresh()

    def _on_vms_missing(self, missing_names: list):
        """
        Called by VMStatePoller when VMs are absent from VirtualBox.
        Updates repository state and optionally shows a UI warning.
        """
        logger.warning("VMs detected as MISSING: %s", missing_names)
        from models import VMState
        for vm_name in missing_names:
            entry = self._vm_repo.get_by_name(vm_name)
            if entry and entry.vm_state != VMState.MISSING:
                self._vm_repo.mark_missing(entry.uuid)

        # Refresh pages so MISSING badge appears
        if hasattr(self._machines, "refresh"):
            self._machines.refresh()
        if hasattr(self._dashboard, "refresh"):
            self._dashboard.refresh()

    def _on_startup_sync_complete(self, result: SyncResult):
        """
        Called when the startup VMSyncWorker finishes.
        Triggers a UI refresh so pages reflect fresh state.
        """
        logger.info("Startup sync complete: %s", result.summary())
        if result.missing_count > 0:
            logger.warning(
                "%d VM(s) are MISSING from VirtualBox — "
                "they may have been deleted outside this application.",
                result.missing_count,
            )
        if result.orphan_snaps:
            logger.warning(
                "%d snapshot(s) orphaned (parent VMs missing).",
                len(result.orphan_snaps),
            )

        # Refresh all pages with the synced state
        for page in (self._dashboard, self._machines, self._snapshots_page):
            if hasattr(page, "refresh"):
                page.refresh()

    # ── Shutdown ──────────────────────────────────────────────────────────────

    def closeEvent(self, event):
        """Ensure all background threads are stopped cleanly before exit."""
        logger.info("Shutting down …")

        # Stop poller first (it references VBox engine)
        if hasattr(self, "_state_poller"):
            self._state_poller.stop()
            self._state_poller.wait(3000)

        # Sync worker is one-shot — just wait for it to finish
        if hasattr(self, "_sync_worker") and self._sync_worker.isRunning():
            self._sync_worker.wait(5000)

        # Drain console page start workers and detach viewports
        if hasattr(self, "_console"):
            self._console.shutdown()

        # Cancel and drain all active action workers
        for worker in list(self._active_workers):
            try:
                if hasattr(worker, 'cancel'):
                    worker.cancel()
                if worker.isRunning():
                    worker.wait(2000)
            except RuntimeError:
                pass
        self._active_workers.clear()

        super().closeEvent(event)


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def run():
    import ctypes
    # Fix for Windows Taskbar icon showing default Python logo instead of ours
    try:
        myappid = "oneclick.vm.platform.1.0"
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
    except Exception as e:
        logger.warning("Could not set explicit AppUserModelID: %s", e)

    from PyQt5.QtWidgets import QApplication
    # Enable High DPI scaling
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    # Resolve logo/favicon paths seamlessly (allowing either location)
    icon_path = "assets/favicon.ico"
    if not os.path.exists(icon_path):
        icon_path = "frontend/favicon/favicon.ico"
    if not os.path.exists(icon_path):
        icon_path = "frontend/logo.png"

    # Set globally
    app_icon = QIcon(icon_path)
    app.setWindowIcon(app_icon)

    window = VMPlatformWindow()
    window.setWindowIcon(app_icon)
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    run()
