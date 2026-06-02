"""
ui/pages/console_page.py
=========================
Tabbed VM console page — supports multiple simultaneous VM sessions.

Layout
------
┌──────────────────────────────────────────────────────────┬──────────────┐
│  [Toolbar: title · Focus · Ctrl+Alt+Del · Disconnect]    │              │
│  ┌────────────────────────────────────────────────────┐  │  Host Stats  │
│  │ [Tab: VM-A ▶] [Tab: VM-B ⏳] [Tab: VM-C ✗]  [+]  │  │  CPU/RAM/Net │
│  │ ┌──────────────────────────────────────────────┐  │  │              │
│  │ │  VMConsoleTab (loading / live / error)       │  │  │  Active Tabs │
│  │ └──────────────────────────────────────────────┘  │  │              │
│  └────────────────────────────────────────────────────┘  │              │
└──────────────────────────────────────────────────────────┴──────────────┘

Public API
----------
  attach_vm(vm_name, vm_uuid="")
      Called from app.py when a VM is launched.
      - If tab exists → switch to it.
      - If VM is already running → open tab + embed immediately.
      - If VM is not running → open tab + start non-blocking.

  detach(vm_name=None)
      Detach one VM tab (or current active tab if vm_name is None).
      Does NOT stop the VM.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

import logging

from PyQt5.QtCore    import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy

from qfluentwidgets import (
    TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel,
    CardWidget, ProgressBar, PushButton, PrimaryPushButton,
    FluentIcon as FIF, InfoBar, InfoBarPosition,
)

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from ui.components.console_tab_manager import ConsoleTabManager, TabState
from backend.vm_start_service          import VMStartService

_log = logging.getLogger("ConsolePage")

# Resolve VM UUID from app's VMRepository if available (injected by app.py)
_global_vm_repo = None


class ConsolePage(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ConsolePage")
        self.setStyleSheet("background: transparent;")

        # ── Services ──────────────────────────────────────────────────────
        self._start_service = VMStartService()

        # ── Root layout ───────────────────────────────────────────────────
        root = QHBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # LEFT COLUMN: toolbar + tab manager
        left_col = QVBoxLayout()
        left_col.setSpacing(8)
        left_col.setContentsMargins(0, 0, 0, 0)

        left_col.addLayout(self._build_toolbar())

        self._tab_manager = ConsoleTabManager()
        self._tab_manager.tab_closed.connect(self._on_tab_closed)
        self._tab_manager.retry_requested.connect(self._on_retry_requested)
        left_col.addWidget(self._tab_manager, stretch=1)

        left_col.addLayout(self._build_status_bar())
        root.addLayout(left_col, stretch=3)

        # RIGHT COLUMN: host stats
        root.addWidget(self._build_stats_panel(), stretch=0)

        # ── Live stats timer ──────────────────────────────────────────────
        self._prev_net  = psutil.net_io_counters() if _HAS_PSUTIL else None
        self._stats_tmr = QTimer(self)
        self._stats_tmr.timeout.connect(self._update_stats)
        self._stats_tmr.start(1500)
        self._update_stats()

        # ── VM UUID cache (name → uuid) ───────────────────────────────────
        self._uuid_cache: dict[str, str] = {}

        self._set_status("Idle", "rgba(255,255,255,0.4)")

    # ── Dependency injection ───────────────────────────────────────────────

    def set_vm_repo(self, vm_repo):
        """Inject VMRepository so we can resolve UUIDs for start requests."""
        global _global_vm_repo
        _global_vm_repo = vm_repo

    # ── Toolbar ───────────────────────────────────────────────────────────

    def _build_toolbar(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(8)

        lay.addWidget(SubtitleLabel("VM Console"))
        lay.addStretch()

        self._focus_btn = PushButton(FIF.ZOOM_IN, "Focus")
        self._focus_btn.setFixedHeight(34)
        self._focus_btn.setToolTip("Give keyboard focus to the active VM window")
        self._focus_btn.clicked.connect(self._focus_vm)
        self._focus_btn.setEnabled(False)

        self._cad_btn = PushButton(FIF.REMOVE, "Ctrl+Alt+Del")
        self._cad_btn.setFixedHeight(34)
        self._cad_btn.setToolTip("Send Ctrl+Alt+Del to the active VM")
        self._cad_btn.clicked.connect(self._send_cad)
        self._cad_btn.setEnabled(False)

        self._disconnect_btn = PushButton(FIF.POWER_BUTTON, "Disconnect Tab")
        self._disconnect_btn.setFixedHeight(34)
        self._disconnect_btn.setToolTip("Close this tab (VM keeps running)")
        self._disconnect_btn.clicked.connect(lambda: self.detach())
        self._disconnect_btn.setEnabled(False)

        for btn in (self._focus_btn, self._cad_btn, self._disconnect_btn):
            lay.addWidget(btn)
        return lay

    # ── Status bar ────────────────────────────────────────────────────────

    def _build_status_bar(self) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(16)

        self._status_dot = CaptionLabel("●")
        self._status_dot.setStyleSheet("font-size: 10px; color: rgba(255,255,255,0.3);")
        self._status_lbl = CaptionLabel("Idle — no VM attached")
        self._status_lbl.setStyleSheet("color: rgba(255,255,255,0.4);")
        self._vm_count_lbl = CaptionLabel("")
        self._vm_count_lbl.setStyleSheet("color: rgba(255,255,255,0.25);")

        lay.addWidget(self._status_dot)
        lay.addWidget(self._status_lbl)
        lay.addStretch()
        lay.addWidget(self._vm_count_lbl)
        return lay

    # ── Stats panel ───────────────────────────────────────────────────────

    def _build_stats_panel(self) -> CardWidget:
        card = CardWidget()
        card.setBorderRadius(16)
        card.setFixedWidth(240)
        card.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Expanding)

        lay = QVBoxLayout(card)
        lay.setContentsMargins(18, 18, 18, 18)
        lay.setSpacing(18)
        lay.addWidget(SubtitleLabel("Host Stats"))

        def _stat(label):
            lay.addWidget(StrongBodyLabel(label))
            bar = ProgressBar()
            bar.setRange(0, 100)
            lay.addWidget(bar)
            val = CaptionLabel("—")
            val.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
            lay.addWidget(val)
            return bar, val

        self._cpu_bar, self._cpu_val = _stat("CPU Usage")
        self._ram_bar, self._ram_val = _stat("RAM Usage")

        lay.addWidget(StrongBodyLabel("Network I/O"))
        self._net_lbl = CaptionLabel("Rx: —  |  Tx: —")
        self._net_lbl.setStyleSheet("color: rgba(255,255,255,0.45); font-size: 11px;")
        lay.addWidget(self._net_lbl)

        lay.addStretch()

        lay.addWidget(StrongBodyLabel("Active Sessions"))
        self._session_list_lbl = CaptionLabel("None")
        self._session_list_lbl.setStyleSheet("color: #60a5fa; font-size: 11px;")
        self._session_list_lbl.setWordWrap(True)
        lay.addWidget(self._session_list_lbl)

        return card

    # ── Public API ────────────────────────────────────────────────────────

    def attach_vm(self, vm_name: str, vm_uuid: str = ""):
        """
        Called by app.py when a VM is launched.

        Flow:
          1. If tab already exists → switch to it (no duplicate).
          2. Open a new tab in LOADING state.
          3. Check if VM is already running (poller cache).
             YES → transition to RUNNING immediately (embed console).
             NO  → start non-blocking via VMStartService.
        """
        _log.info("[%s] attach_vm called  uuid=%s", vm_name, vm_uuid or "(none)")

        # Resolve UUID if not provided
        if not vm_uuid:
            vm_uuid = self._resolve_uuid(vm_name)
        if vm_uuid:
            self._uuid_cache[vm_name] = vm_uuid

        # Prevent duplicate tab creation
        if self._tab_manager.has_tab(vm_name):
            _log.info("[%s] tab already open — switching focus", vm_name)
            self._tab_manager.switch_to_vm(vm_name)
            self._refresh_toolbar()
            return

        # Open tab in loading state
        self._tab_manager.open_vm_tab(vm_name)
        self._tab_manager.set_tab_loading(vm_name, "Checking VM state…")

        # Check if already running (fast path)
        if self._is_vm_running(vm_name, vm_uuid):
            _log.info("[%s] VM already running — embedding console directly", vm_name)
            self._tab_manager.set_tab_running(vm_name)
        else:
            # Start non-blocking
            _log.info("[%s] VM not running — starting via VMStartService", vm_name)
            self._start_service.start_vm(
                vm_name  = vm_name,
                vm_uuid  = vm_uuid,
                on_starting = self._on_vm_starting,
                on_running  = self._on_vm_running,
                on_failed   = self._on_vm_failed,
                on_status   = self._on_vm_status,
                parent      = self,
            )

        self._refresh_toolbar()
        self._refresh_session_list()

    def detach(self, vm_name: str = None):
        """
        Close a VM tab (detach only — VM keeps running).
        If vm_name is None, closes the currently visible tab.
        """
        if vm_name is None:
            vm_name = self._current_tab_vm_name()
        if vm_name:
            _log.info("[%s] detach() called", vm_name)
            self._start_service.cancel(vm_name)
            self._tab_manager.close_tab(vm_name)
            self._refresh_toolbar()
            self._refresh_session_list()

    # ── VMStartService signal handlers ─────────────────────────────────────

    def _on_vm_starting(self, vm_name: str):
        _log.info("[%s] _on_vm_starting", vm_name)
        self._tab_manager.set_tab_loading(vm_name, "Starting VM… please wait")
        self._set_status(f"Starting {vm_name}…", "#60a5fa")

    def _on_vm_running(self, vm_name: str):
        _log.info("[%s] _on_vm_running — transitioning tab to console", vm_name)
        self._tab_manager.set_tab_running(vm_name)
        self._set_status(f"Running: {vm_name}", "#22c55e")
        self._refresh_toolbar()

        # Notify with toast
        try:
            from ui.notification_manager import notify
            notify.info("VM Running", f"'{vm_name}' is now live in its tab.")
        except Exception:
            pass

    def _on_vm_failed(self, vm_name: str, reason: str):
        _log.error("[%s] _on_vm_failed: %s", vm_name, reason)
        self._tab_manager.set_tab_error(vm_name, reason)
        self._set_status(f"Error: {vm_name}", "#ef4444")

        try:
            from ui.notification_manager import notify
            notify.warning("VM Start Failed", f"'{vm_name}': {reason[:80]}")
        except Exception:
            pass

    def _on_vm_status(self, vm_name: str, message: str):
        self._tab_manager.set_tab_status_message(vm_name, message)

    # ── Tab event handlers ────────────────────────────────────────────────

    def _on_tab_closed(self, vm_name: str):
        """User clicked ✕ — cancel any pending start."""
        _log.info("[%s] tab closed by user", vm_name)
        self._start_service.cancel(vm_name)
        self._refresh_toolbar()
        self._refresh_session_list()

    def _on_retry_requested(self, vm_name: str):
        """User clicked Retry on error panel — restart attach flow."""
        _log.info("[%s] retry requested", vm_name)
        # Close old tab and re-open fresh
        self._tab_manager.close_tab(vm_name)
        vm_uuid = self._uuid_cache.get(vm_name, "")
        # Brief delay so UI redraws cleanly
        QTimer.singleShot(200, lambda: self.attach_vm(vm_name, vm_uuid))

    # ── Toolbar helpers ───────────────────────────────────────────────────

    def _focus_vm(self):
        vm_name = self._current_tab_vm_name()
        if not vm_name:
            return
        tab = self._tab_manager._tabs.get(vm_name)
        if tab and tab.viewport and tab.viewport.current_hwnd:
            hwnd = tab.viewport.current_hwnd
            try:
                import ctypes
                ctypes.windll.user32.SetForegroundWindow(hwnd)
                ctypes.windll.user32.SetFocus(hwnd)
            except Exception:
                pass

    def _send_cad(self):
        vm_name = self._current_tab_vm_name()
        if not vm_name:
            return
        tab = self._tab_manager._tabs.get(vm_name)
        if not tab or not tab.viewport or not tab.viewport.is_connected:
            return
        hwnd = tab.viewport.current_hwnd
        if not hwnd:
            return
        try:
            import ctypes
            VK_CONTROL, VK_MENU, VK_DELETE = 0x11, 0x12, 0x2E
            ctypes.windll.user32.SetForegroundWindow(hwnd)
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_MENU,    0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_DELETE,  0, 0, 0)
            ctypes.windll.user32.keybd_event(VK_DELETE,  0, 2, 0)
            ctypes.windll.user32.keybd_event(VK_MENU,    0, 2, 0)
            ctypes.windll.user32.keybd_event(VK_CONTROL, 0, 2, 0)
        except Exception as exc:
            InfoBar.warning(
                "Ctrl+Alt+Del", f"Could not send key: {exc}",
                duration=3000, position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )

    def _refresh_toolbar(self):
        vm_name = self._current_tab_vm_name()
        has_vm  = vm_name is not None
        tab = self._tab_manager._tabs.get(vm_name) if vm_name else None
        is_running = tab and tab.state == TabState.RUNNING and \
                     tab.viewport and tab.viewport.is_connected

        self._focus_btn.setEnabled(bool(is_running))
        self._cad_btn.setEnabled(bool(is_running))
        self._disconnect_btn.setEnabled(has_vm)

    def _refresh_session_list(self):
        names = self._tab_manager.active_vm_names()
        if names:
            self._session_list_lbl.setText("\n".join(f"• {n}" for n in names))
            self._vm_count_lbl.setText(f"{len(names)} active session(s)")
        else:
            self._session_list_lbl.setText("None")
            self._vm_count_lbl.setText("")
            self._set_status("Idle", "rgba(255,255,255,0.4)")

    def _current_tab_vm_name(self) -> str | None:
        """Return the vm_name of the currently visible tab, or None."""
        idx = self._tab_manager._tab_widget.currentIndex()
        tab = self._tab_manager._tab_widget.widget(idx)
        return getattr(tab, "vm_name", None)

    # ── VM state helpers ──────────────────────────────────────────────────

    def _is_vm_running(self, vm_name: str, vm_uuid: str) -> bool:
        """
        Fast check against the global VMStatePoller cache (no subprocess).
        Falls back to False if unavailable.
        """
        try:
            from ui.state_manager import vm_state_manager
            state = vm_state_manager.get_state(vm_name)
            if state == "running":
                return True
        except Exception:
            pass
        return False

    def _resolve_uuid(self, vm_name: str) -> str:
        """Resolve UUID from injected VMRepository, or empty string."""
        if _global_vm_repo:
            try:
                entry = _global_vm_repo.get_by_name(vm_name)
                if entry and entry.uuid:
                    return entry.uuid
            except Exception:
                pass
        return ""

    # ── Status helpers ────────────────────────────────────────────────────

    def _set_status(self, text: str, color: str):
        self._status_dot.setStyleSheet(f"font-size: 10px; color: {color};")
        self._status_lbl.setText(text)
        self._status_lbl.setStyleSheet(f"color: {color};")

    # ── Stats update ──────────────────────────────────────────────────────

    def _update_stats(self):
        if not _HAS_PSUTIL:
            return
        cpu     = int(psutil.cpu_percent(interval=None))
        ram     = psutil.virtual_memory()
        ram_pct = int(ram.percent)
        ram_gb  = ram.used  / (1024 ** 3)
        tot_gb  = ram.total / (1024 ** 3)

        self._cpu_bar.setValue(cpu)
        self._cpu_val.setText(f"{cpu}%")
        self._ram_bar.setValue(ram_pct)
        self._ram_val.setText(f"{ram_gb:.1f} / {tot_gb:.1f} GB ({ram_pct}%)")

        net = psutil.net_io_counters()
        if self._prev_net is not None:
            rx = (net.bytes_recv - self._prev_net.bytes_recv) / 1024
            tx = (net.bytes_sent - self._prev_net.bytes_sent) / 1024
            self._net_lbl.setText(f"↓ {rx:.1f} KB/s  |  ↑ {tx:.1f} KB/s")
        self._prev_net = net

    # ── Shutdown ──────────────────────────────────────────────────────────

    def shutdown(self):
        """Called on app close — drains all active start workers."""
        self._start_service.drain(timeout_ms=3000)
        for vm_name in list(self._tab_manager.active_vm_names()):
            self._tab_manager.close_tab(vm_name)
