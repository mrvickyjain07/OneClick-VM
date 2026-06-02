"""
ui/components/console_tab_manager.py
=====================================
Multi-VM tabbed console manager.

Each running VM gets its own tab containing:
  - An embedded VMViewport (live VirtualBox window)
  - A loading overlay while the VM is starting
  - An error overlay on failure
  - VM name + status indicator in the tab title
  - Close button (detaches UI only — VM keeps running)

Architecture
------------
ConsoleTabManager
  └─ QTabWidget (tabsClosable=True)
       └─ [per VM] VMConsoleTab  (QWidget)
              ├─ QStackedWidget
              │    ├─ Loading panel  (spinner + status text)
              │    ├─ VMViewport     (live console)
              │    └─ Error panel
              └─ internal state: {LOADING, RUNNING, ERROR}

Public API
----------
    open_vm_tab(vm_name, vm_uuid)   → ensure a tab exists, return tab index
    switch_to_vm(vm_name)           → focus an existing tab
    set_tab_loading(vm_name, msg)   → show spinner with message
    set_tab_running(vm_name)        → trigger console embedding
    set_tab_error(vm_name, reason)  → show error overlay
    close_tab(vm_name)              → detach + remove tab
    has_tab(vm_name)                → bool
    active_vm_names()               → list[str]

Signals
-------
    tab_closed(vm_name)             → emitted when user closes a tab
    retry_requested(vm_name)        → emitted from error panel Retry button
"""
import logging
from enum import Enum, auto

from PyQt5.QtCore    import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QStackedWidget, QSizePolicy, QTabWidget
)

from qfluentwidgets import (
    CaptionLabel, StrongBodyLabel, BodyLabel,
    PushButton, PrimaryPushButton, FluentIcon as FIF, ProgressBar,
)

from ui.components.vm_viewport import VMViewport

_log = logging.getLogger("ConsoleTabManager")

# Panel indices inside VMConsoleTab's QStackedWidget
_IDX_LOADING = 0
_IDX_CONSOLE = 1
_IDX_ERROR   = 2


class TabState(Enum):
    LOADING = auto()
    RUNNING = auto()
    ERROR   = auto()


# ─────────────────────────────────────────────────────────────────────────────
# Indeterminate spinner helper
# ─────────────────────────────────────────────────────────────────────────────

try:
    from qfluentwidgets import IndeterminateProgressBar as _IndBar
    def _make_spinner(parent=None): return _IndBar(parent)
except ImportError:
    class _BounceBar(ProgressBar):
        def __init__(self, p=None):
            super().__init__(p)
            self.setRange(0, 100)
            self._v, self._d = 0, 4
            t = QTimer(self)
            t.timeout.connect(self._tick)
            t.start(25)
        def _tick(self):
            self._v += self._d
            if self._v >= 100: self._d = -4
            if self._v <=   0: self._d =  4
            self.setValue(self._v)
    def _make_spinner(parent=None): return _BounceBar(parent)


# ─────────────────────────────────────────────────────────────────────────────
# Single VM Console Tab
# ─────────────────────────────────────────────────────────────────────────────

class VMConsoleTab(QWidget):
    """
    A single tab pane containing loading / console / error states.
    """
    retry_requested = pyqtSignal(str)   # vm_name

    def __init__(self, vm_name: str, parent=None):
        super().__init__(parent)
        self.vm_name    = vm_name
        self._state     = TabState.LOADING
        self._viewport  = None          # created lazily when running

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setStyleSheet("background: #08080f;")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget()
        self._stack.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._stack)

        # ── Loading panel ─────────────────────────────────────────────
        self._loading_panel  = self._build_loading_panel()
        self._console_panel  = QWidget()          # placeholder; viewport added later
        self._console_layout = QVBoxLayout(self._console_panel)
        self._console_layout.setContentsMargins(0, 0, 0, 0)
        self._error_panel    = self._build_error_panel()

        self._stack.addWidget(self._loading_panel)   # _IDX_LOADING
        self._stack.addWidget(self._console_panel)   # _IDX_CONSOLE
        self._stack.addWidget(self._error_panel)     # _IDX_ERROR
        self._stack.setCurrentIndex(_IDX_LOADING)

    # ── Panel builders ────────────────────────────────────────────────────

    def _build_loading_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(20)

        icon = QLabel("⚙")
        icon.setStyleSheet("font-size: 52px; color: #60a5fa; background: transparent;")
        icon.setAlignment(Qt.AlignCenter)

        self._loading_title = StrongBodyLabel(f"Starting '{self.vm_name}'…")
        self._loading_title.setStyleSheet(
            "font-size: 16px; color: #60a5fa; background: transparent;"
        )
        self._loading_title.setAlignment(Qt.AlignCenter)

        self._loading_msg = CaptionLabel("Initializing…")
        self._loading_msg.setAlignment(Qt.AlignCenter)
        self._loading_msg.setWordWrap(True)
        self._loading_msg.setStyleSheet(
            "color: rgba(255,255,255,0.45); background: transparent; font-size: 12px;"
        )

        self._spinner = _make_spinner(w)
        self._spinner.setFixedWidth(300)

        lay.addWidget(icon)
        lay.addWidget(self._loading_title)
        lay.addWidget(self._loading_msg)
        lay.addWidget(self._spinner, alignment=Qt.AlignCenter)
        return w

    def _build_error_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(16)

        icon = QLabel("✗")
        icon.setStyleSheet("font-size: 52px; color: #ef4444; background: transparent;")
        icon.setAlignment(Qt.AlignCenter)

        self._err_title = StrongBodyLabel("VM Failed to Start")
        self._err_title.setStyleSheet(
            "font-size: 15px; color: #ef4444; background: transparent;"
        )
        self._err_title.setAlignment(Qt.AlignCenter)

        self._err_msg = CaptionLabel("")
        self._err_msg.setAlignment(Qt.AlignCenter)
        self._err_msg.setWordWrap(True)
        self._err_msg.setStyleSheet(
            "color: rgba(255,255,255,0.45); background: transparent; max-width: 480px;"
        )

        retry_btn = PrimaryPushButton(FIF.SYNC, "Retry")
        retry_btn.setFixedWidth(160)
        retry_btn.clicked.connect(lambda: self.retry_requested.emit(self.vm_name))

        row = QHBoxLayout()
        row.setSpacing(12)
        row.addWidget(retry_btn, alignment=Qt.AlignCenter)

        lay.addWidget(icon)
        lay.addWidget(self._err_title)
        lay.addWidget(self._err_msg)
        lay.addLayout(row)
        return w

    # ── Public state transitions ──────────────────────────────────────────

    def show_loading(self, message: str = ""):
        """Transition to the loading/spinner state."""
        self._state = TabState.LOADING
        if message:
            self._loading_msg.setText(message)
        self._stack.setCurrentIndex(_IDX_LOADING)
        _log.debug("[%s] tab → LOADING", self.vm_name)

    def update_loading_message(self, message: str):
        """Update spinner subtitle without changing state."""
        self._loading_msg.setText(message)

    def show_console(self):
        """
        Transition to the live console state.
        Creates the VMViewport lazily and starts window finding.
        """
        self._state = TabState.RUNNING

        if self._viewport is None:
            self._viewport = VMViewport()
            self._viewport.retry_requested.connect(
                lambda: self.retry_requested.emit(self.vm_name)
            )
            self._console_layout.addWidget(self._viewport)

        self._stack.setCurrentIndex(_IDX_CONSOLE)
        # Trigger window search
        self._viewport.connect_vm(self.vm_name)
        _log.debug("[%s] tab → RUNNING (viewport connecting)", self.vm_name)

    def show_error(self, reason: str):
        """Transition to the error state with a human-readable reason."""
        self._state = TabState.ERROR
        self._err_msg.setText(reason)
        self._stack.setCurrentIndex(_IDX_ERROR)
        _log.debug("[%s] tab → ERROR: %s", self.vm_name, reason)

    def detach(self):
        """
        Cleanly disconnect the viewport (does NOT kill the VM).
        Called when the tab is closed.
        """
        if self._viewport:
            self._viewport.disconnect()
        _log.info("[%s] tab detached", self.vm_name)

    @property
    def state(self) -> TabState:
        return self._state

    @property
    def viewport(self):
        return self._viewport


# ─────────────────────────────────────────────────────────────────────────────
# Tab Manager
# ─────────────────────────────────────────────────────────────────────────────

class ConsoleTabManager(QWidget):
    """
    Multi-VM tabbed console host.

    Wraps a QTabWidget and provides a clean API for opening, updating,
    and closing per-VM console tabs.

    Signals
    -------
    tab_closed(vm_name)        user clicked ✕ on a tab
    retry_requested(vm_name)   user clicked Retry on the error panel
    """
    tab_closed       = pyqtSignal(str)   # vm_name
    retry_requested  = pyqtSignal(str)   # vm_name

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs: dict[str, VMConsoleTab] = {}   # vm_name → VMConsoleTab

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._tab_widget = QTabWidget()
        self._tab_widget.setTabsClosable(True)
        self._tab_widget.setMovable(True)
        self._tab_widget.setDocumentMode(True)
        self._tab_widget.tabCloseRequested.connect(self._on_close_requested)
        self._tab_widget.setStyleSheet(self._tab_style())
        root.addWidget(self._tab_widget)

        # Empty state placeholder (shown when no tabs are open)
        self._empty = self._build_empty_panel()
        self._tab_widget.addTab(self._empty, " No active consoles")
        self._tab_widget.setTabsClosable(False)   # hide ✕ on placeholder

    # ── Empty state ───────────────────────────────────────────────────────

    def _build_empty_panel(self) -> QWidget:
        w = QWidget()
        w.setStyleSheet("background: #08080f;")
        lay = QVBoxLayout(w)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(14)

        icon = QLabel("🖥")
        icon.setStyleSheet("font-size: 56px; background: transparent;")
        icon.setAlignment(Qt.AlignCenter)

        title = StrongBodyLabel("No VMs Running")
        title.setStyleSheet(
            "font-size: 18px; color: rgba(255,255,255,0.7); background: transparent;"
        )
        title.setAlignment(Qt.AlignCenter)

        sub = CaptionLabel(
            "Start a VM from My Machines or ISO Manager.\n"
            "Each running VM will appear as a tab here."
        )
        sub.setAlignment(Qt.AlignCenter)
        sub.setWordWrap(True)
        sub.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent;")

        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(sub)
        return w

    def _remove_empty_tab(self):
        """Remove placeholder tab once a real tab is added."""
        idx = self._tab_widget.indexOf(self._empty)
        if idx != -1:
            self._tab_widget.removeTab(idx)
            self._tab_widget.setTabsClosable(True)

    def _add_empty_tab_if_needed(self):
        """Re-add placeholder tab when all real tabs are gone."""
        if self._tab_widget.count() == 0:
            self._tab_widget.addTab(self._empty, " No active consoles")
            self._tab_widget.setTabsClosable(False)

    # ── Public API ────────────────────────────────────────────────────────

    def has_tab(self, vm_name: str) -> bool:
        return vm_name in self._tabs

    def open_vm_tab(self, vm_name: str) -> int:
        """
        Open a new tab for vm_name in LOADING state (if not already open).
        Returns the tab index.
        """
        if vm_name in self._tabs:
            _log.info("[%s] tab already exists — switching focus", vm_name)
            return self.switch_to_vm(vm_name)

        _log.info("[%s] opening new console tab", vm_name)
        self._remove_empty_tab()

        tab = VMConsoleTab(vm_name)
        tab.retry_requested.connect(self.retry_requested)
        self._tabs[vm_name] = tab

        idx = self._tab_widget.addTab(tab, f"⏳  {vm_name}")
        self._tab_widget.setCurrentIndex(idx)
        _log.info("[%s] tab created at index %d", vm_name, idx)
        return idx

    def switch_to_vm(self, vm_name: str) -> int:
        """Bring an existing tab to focus. Returns tab index or -1."""
        tab = self._tabs.get(vm_name)
        if not tab:
            return -1
        idx = self._tab_widget.indexOf(tab)
        self._tab_widget.setCurrentIndex(idx)
        return idx

    def set_tab_loading(self, vm_name: str, message: str = ""):
        """Update a tab's loading message without changing state."""
        tab = self._tabs.get(vm_name)
        if tab:
            tab.update_loading_message(message)

    def set_tab_running(self, vm_name: str):
        """
        Transition a tab to RUNNING state — shows the live VMViewport
        which will embed the VirtualBox window automatically.
        """
        tab = self._tabs.get(vm_name)
        if not tab:
            _log.warning("[%s] set_tab_running: no tab found", vm_name)
            return
        tab.show_console()
        idx = self._tab_widget.indexOf(tab)
        self._tab_widget.setTabText(idx, f"▶  {vm_name}")
        _log.info("[%s] tab set to RUNNING state", vm_name)

    def set_tab_error(self, vm_name: str, reason: str):
        """Transition a tab to ERROR state."""
        tab = self._tabs.get(vm_name)
        if not tab:
            return
        tab.show_error(reason)
        idx = self._tab_widget.indexOf(tab)
        self._tab_widget.setTabText(idx, f"✗  {vm_name}")
        _log.info("[%s] tab set to ERROR: %s", vm_name, reason)

    def set_tab_status_message(self, vm_name: str, message: str):
        """Update the spinner subtitle text while in LOADING state."""
        tab = self._tabs.get(vm_name)
        if tab and tab.state == TabState.LOADING:
            tab.update_loading_message(message)

    def close_tab(self, vm_name: str):
        """Programmatically close a VM tab (detach only — VM keeps running)."""
        tab = self._tabs.pop(vm_name, None)
        if not tab:
            return
        tab.detach()
        idx = self._tab_widget.indexOf(tab)
        if idx != -1:
            self._tab_widget.removeTab(idx)
        tab.deleteLater()
        self._add_empty_tab_if_needed()
        _log.info("[%s] tab closed", vm_name)

    def active_vm_names(self) -> list:
        return list(self._tabs.keys())

    # ── Close button handler ──────────────────────────────────────────────

    def _on_close_requested(self, index: int):
        """User clicked the ✕ on a tab."""
        tab = self._tab_widget.widget(index)
        vm_name = getattr(tab, "vm_name", None)
        if not vm_name:
            return
        _log.info("[%s] user requested tab close", vm_name)
        self.close_tab(vm_name)
        self.tab_closed.emit(vm_name)

    # ── Stylesheet ────────────────────────────────────────────────────────

    @staticmethod
    def _tab_style() -> str:
        return """
        QTabWidget::pane {
            border: none;
            background: #08080f;
        }
        QTabWidget::tab-bar {
            alignment: left;
        }
        QTabBar {
            background: #0d0d1a;
        }
        QTabBar::tab {
            background: #0d0d1a;
            color: rgba(255, 255, 255, 0.55);
            padding: 8px 18px;
            min-width: 140px;
            max-width: 240px;
            border: none;
            border-bottom: 2px solid transparent;
            font-size: 12px;
        }
        QTabBar::tab:selected {
            background: #131325;
            color: #60a5fa;
            border-bottom: 2px solid #60a5fa;
        }
        QTabBar::tab:hover:!selected {
            background: #111122;
            color: rgba(255, 255, 255, 0.75);
        }
        QTabBar::close-button {
            image: none;
            subcontrol-position: right;
        }
        QTabBar::close-button:hover {
            background: rgba(239, 68, 68, 0.25);
            border-radius: 3px;
        }
        """
