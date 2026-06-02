"""
ui/components/vm_viewport.py
VM display viewport — embeds the running VirtualBox VM via native Win32 embedding.

Embedding flow:
 1. Poll for VM window using EnumWindows (must match ' - Oracle VirtualBox')
 2. Get HWND.
 3. Use QWindow.fromWinId(hwnd) and QWidget.createWindowContainer(window)
 4. Strip borders using SetWindowLong(hwnd, GWL_STYLE, WS_VISIBLE)
 5. Auto-reconnect if window is lost.
"""
import sys, os, time
import logging

from PyQt5.QtCore    import Qt, QTimer, pyqtSignal, QThread
from PyQt5.QtGui     import QWindow
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QLabel, QStackedWidget, QApplication
)

from qfluentwidgets import (
    CaptionLabel, StrongBodyLabel,
    PushButton, PrimaryPushButton, FluentIcon as FIF, ProgressBar,
)

import ctypes
import ctypes.wintypes as wintypes

_u32 = ctypes.windll.user32

_log = logging.getLogger("VMViewport")

# ── Indeterminate spinner ─────────────────────────────────────────────────────
try:
    from qfluentwidgets import IndeterminateProgressBar as _IndBar
    def _make_spinner(parent=None): return _IndBar(parent)
except ImportError:
    class _BounceBar(ProgressBar):
        def __init__(self, p=None):
            super().__init__(p); self.setRange(0,100)
            self._v, self._d = 0, 4
            t = QTimer(self); t.timeout.connect(self._tick); t.start(25)
        def _tick(self):
            self._v += self._d
            if self._v >= 100: self._d = -4
            if self._v <= 0:   self._d =  4
            self.setValue(self._v)
    def _make_spinner(parent=None): return _BounceBar(parent)

_IDX_IDLE       = 0
_IDX_CONNECTING = 1
_IDX_CONNECTED  = 2
_IDX_ERROR      = 3

# ── Win32 Helpers ─────────────────────────────────────────────────�def find_vm_hwnd(vm_name: str) -> int:
    """
    Find the VirtualBox VM window by title.

    VirtualBox uses several title formats:
      "{vm_name} [Running] - Oracle VM VirtualBox"
      "{vm_name} - Oracle VirtualBox"
      "{vm_name} [Paused] - Oracle VM VirtualBox"

    We accept any visible window whose title contains the vm_name
    AND 'VirtualBox', excluding the Manager window.
    """
    found_hwnd = []
    vm_lower   = vm_name.lower()

    def _cb(hwnd, _lp):
        if not _u32.IsWindowVisible(hwnd):
            return True
        length = _u32.GetWindowTextLengthW(hwnd)
        if length == 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        _u32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value
        title_lower = title.lower()
        if (
            vm_lower in title_lower
            and "virtualbox" in title_lower
            and "manager" not in title_lower
        ):
            found_hwnd.append(hwnd)
            return False   # stop enumerating
        return True

    _u32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found_hwnd[0] if found_hwnd else 0


def _hwnd_has_size(hwnd: int) -> bool:
    """Return True if the window has non-zero client area (rendered at least once)."""
    rect = wintypes.RECT()
    _u32.GetClientRect(hwnd, ctypes.byref(rect))
    return (rect.right - rect.left) > 10 and (rect.bottom - rect.top) > 10


def strip_decorations(hwnd: int):
    """Remove title bar and borders, ensuring it acts as a child."""
    if not hwnd: return
    style = WS_VISIBLE | WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS
    _u32.SetWindowLongW(hwnd, GWL_STYLE, style)
    _u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)


# ── Worker ────────────────────────────────────────────────────────────────────
class WindowFinderWorker(QThread):
    hwnd_found = pyqtSignal(int)
    timed_out  = pyqtSignal()

    # How long to wait for the window to appear and render
    APPEAR_TIMEOUT_S  = 90    # seconds to search for the window
    RENDER_TIMEOUT_S  = 15    # seconds to wait for non-zero client area
    POLL_INTERVAL_S   = 0.5

    def __init__(self, vm_name: str, timeout_s: int = 90, parent=None):
        super().__init__(parent)
        self.vm_name   = vm_name
        self.timeout_s = timeout_s
        self._stop     = False

    def request_stop(self): self._stop = True

    def run(self):
        """Poll for the VM window; once found, confirm it has rendered."""
        deadline = time.time() + self.timeout_s

        # Phase 1: Find the HWND
        hwnd = 0
        while not self._stop and time.time() < deadline:
            hwnd = find_vm_hwnd(self.vm_name)
            if hwnd:
                break
            time.sleep(self.POLL_INTERVAL_S)

        if self._stop or not hwnd:
            if not self._stop:
                _log.warning("WindowFinderWorker: window not found for '%s' in %ds",
                             self.vm_name, self.timeout_s)
                self.timed_out.emit()
            return

        _log.info("WindowFinderWorker: HWND 0x%08X found for '%s' — waiting for render",
                  hwnd, self.vm_name)

        # Phase 2: Wait for the window to have a non-zero client area
        render_deadline = time.time() + self.RENDER_TIMEOUT_S
        while not self._stop and time.time() < render_deadline:
            if _hwnd_has_size(hwnd):
                break
            time.sleep(0.25)

        if self._stop:
            return

        if not _hwnd_has_size(hwnd):
            _log.warning(
                "WindowFinderWorker: HWND 0x%08X still has zero size after %ds — emitting anyway",
                hwnd, self.RENDER_TIMEOUT_S,
            )

        _log.info("WindowFinderWorker: emitting hwnd_found 0x%08X", hwnd)
        self.hwnd_found.emit(hwnd)   while not self._stop and time.time() < deadline:
            hwnd = find_vm_hwnd(self.vm_name)
            if hwnd:
                time.sleep(1.0) # Let VBox finish its first paint
                if not self._stop:
                    self.hwnd_found.emit(hwnd)
                return
            time.sleep(0.5)
        if not self._stop:
            self.timed_out.emit()

# ── Main Widget ───────────────────────────────────────────────────────────────
class VMViewport(QWidget):
    retry_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_name      = ""
        self._worker       = None
        self._current_hwnd = 0
        self._embed_container = None

        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        self.setMinimumSize(640, 400)
        self.setStyleSheet("VMViewport { background: #08080f; border-radius: 10px; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        self._stack.setContentsMargins(0, 0, 0, 0)
        root.addWidget(self._stack)

        self._stack.addWidget(self._build_idle_panel())
        self._stack.addWidget(self._build_connecting_panel())

        # The embed target area
        self._target_area = QWidget()
        self._target_area.setStyleSheet("background: #000000;")
        self._target_layout = QVBoxLayout(self._target_area)
        self._target_layout.setContentsMargins(0, 0, 0, 0)
        self._target_layout.setSpacing(0)
        
        self._stack.addWidget(self._target_area)
        self._stack.addWidget(self._build_error_panel())
        self._stack.setCurrentIndex(_IDX_IDLE)

        self._validation_timer = QTimer(self)
        self._validation_timer.setInterval(1000)
        self._validation_timer.timeout.connect(self._validate_window_state)

    # ── Panels ──
    def _build_idle_panel(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(14)
        icon = QLabel("🖥️"); icon.setStyleSheet("font-size: 72px; background: transparent;"); icon.setAlignment(Qt.AlignCenter)
        title = StrongBodyLabel("Console Ready"); title.setStyleSheet("font-size: 16px; color: rgba(255,255,255,0.7); background: transparent;"); title.setAlignment(Qt.AlignCenter)
        sub = CaptionLabel("Start a VM from My Machines or ISO Manager.\nThe live desktop will appear here automatically.")
        sub.setAlignment(Qt.AlignCenter); sub.setWordWrap(True); sub.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent;")
        lay.addWidget(icon); lay.addWidget(title); lay.addWidget(sub)
        return w

    def _build_connecting_panel(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(18)
        icon = QLabel("⚡"); icon.setStyleSheet("font-size: 56px; background: transparent;"); icon.setAlignment(Qt.AlignCenter)
        self._conn_title = StrongBodyLabel("Connecting…"); self._conn_title.setStyleSheet("font-size: 15px; color: #60a5fa; background: transparent;"); self._conn_title.setAlignment(Qt.AlignCenter)
        self._conn_sub = CaptionLabel("Waiting for VirtualBox window to appear…\nThis usually takes a few seconds."); self._conn_sub.setAlignment(Qt.AlignCenter); self._conn_sub.setWordWrap(True); self._conn_sub.setStyleSheet("color: rgba(255,255,255,0.45); background: transparent;")
        self._spinner = _make_spinner(w); self._spinner.setFixedWidth(280)
        lay.addWidget(icon); lay.addWidget(self._conn_title); lay.addWidget(self._conn_sub); lay.addWidget(self._spinner, alignment=Qt.AlignCenter)
        return w

    def _build_error_panel(self) -> QWidget:
        w = QWidget(); w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(16)
        icon = QLabel("⚠️"); icon.setStyleSheet("font-size: 56px; background: transparent;"); icon.setAlignment(Qt.AlignCenter)
        self._err_title = StrongBodyLabel("Connection Failed"); self._err_title.setStyleSheet("font-size: 15px; color: #ef4444; background: transparent;"); self._err_title.setAlignment(Qt.AlignCenter)
        self._err_msg = CaptionLabel(""); self._err_msg.setAlignment(Qt.AlignCenter); self._err_msg.setWordWrap(True); self._err_msg.setStyleSheet("color: rgba(255,255,255,0.45); background: transparent;")
        retry = PrimaryPushButton(FIF.SYNC, "Retry"); retry.setFixedWidth(150); retry.clicked.connect(self.retry_requested)
        idle = PushButton(FIF.CLOSE, "Back to Idle"); idle.setFixedWidth(150); idle.clicked.connect(lambda: self.disconnect())
        row = QHBoxLayout(); row.setSpacing(12); row.addWidget(retry, alignment=Qt.AlignCenter); row.addWidget(idle,  alignment=Qt.AlignCenter)
        lay.addWidget(icon); lay.addWidget(self._err_title); lay.addWidget(self._err_msg); lay.addLayout(row)
        return w

    # ── API ──
    def connect_vm(self, vm_name: str):
        self._vm_name = vm_name
        self.disconnect() # Reset state
        
        self._conn_title.setText(f"Connecting to '{vm_name}'…")
        self._stack.setCurrentIndex(_IDX_CONNECTING)
        
        self._worker = WindowFinderWorker(vm_name, timeout_s=60, parent=self)
        self._worker.hwnd_found.connect(self._on_hwnd_found)
        self._worker.timed_out.connect(self._on_timeout)
        self._worker.start()

    def _on_hwnd_found(self, hwnd: int):
        self._current_hwnd = hwnd
        self._stack.setCurrentIndex(_IDX_CONNECTED)
        QApplication.processEvents()
        QTimer.singleShot(500, lambda: self._do_embed(hwnd))

    def _do_embed(self, hwnd: int):
        if hwnd != self._current_hwnd: return
        
        try:
            # 1. Create Qt Window wrapper
            window = QWindow.fromWinId(hwnd)
            
            # 2. Create container widget
            self._embed_container = QWidget.createWindowContainer(window)
            self._target_layout.addWidget(self._embed_container)
            
            # 3. Strip borders from the HWND
            strip_decorations(hwnd)
            
            # 4. Optional: Force explicit parent + move to ensure zero offset
            # This combats VBox's attempts to offset its client area
            container_hwnd = int(self._embed_container.winId())
            if container_hwnd:
                _u32.SetParent(hwnd, container_hwnd)
                _u32.MoveWindow(hwnd, 0, 0, self._target_area.width(), self._target_area.height(), True)

            self._validation_timer.start()
            _log.info(f"Successfully embedded HWND 0x{hwnd:08X} via createWindowContainer")
        except Exception as e:
            _log.error(f"Embedding failed: {e}")
            self._show_error(f"Failed to embed VM window:\n{e}")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # If the container resize isn't perfectly syncing with VBox, explicitly force MoveWindow
        if self._current_hwnd and self._embed_container:
            try:
                w = max(self._target_area.width(), 1)
                h = max(self._target_area.height(), 1)
                _u32.MoveWindow(self._current_hwnd, 0, 0, w, h, True)
            except Exception:
                pass

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self._current_hwnd and self._stack.currentIndex() == _IDX_CONNECTED:
            try:
                _u32.SetForegroundWindow(self._current_hwnd)
                _u32.SetFocus(self._current_hwnd)
            except Exception:
                pass

    def _validate_window_state(self):
        if not self._current_hwnd or self._stack.currentIndex() != _IDX_CONNECTED:
            return
            
        # If window died or became totally invisible
        if not _u32.IsWindow(self._current_hwnd):
            _log.warning("VM window handle is dead. Attempting to reconnect...")
            self._reconnect()
            return
            
        # Detect blank size
        rect = wintypes.RECT()
        _u32.GetWindowRect(self._current_hwnd, ctypes.byref(rect))
        w = rect.right - rect.left
        h = rect.bottom - rect.top
        
        if w == 0 or h == 0:
            _log.warning("VM window size is 0. Attempting to reconnect...")
            self._reconnect()

    def _reconnect(self):
        self.disconnect()
        if self._vm_name:
            self.connect_vm(self._vm_name)

    def _on_timeout(self):
        self._show_error(
            "Could not find the VirtualBox window after 60 seconds.\n\n"
            "• Confirm the VM is running\n"
            "• Click Retry to try again")

    def disconnect(self):
        self._validation_timer.stop()
        if self._worker:
            self._worker.request_stop()
            self._worker.wait(1000)
            self._worker = None
            
        if self._embed_container:
            self._target_layout.removeWidget(self._embed_container)
            self._embed_container.deleteLater()
            self._embed_container = None
            
        # We don't restore the window style here because we are abandoning it
        # or the VM is shutting down.
        self._current_hwnd = 0
        self._stack.setCurrentIndex(_IDX_IDLE)

    def _show_error(self, msg: str):
        self._err_msg.setText(msg)
        self._stack.setCurrentIndex(_IDX_ERROR)

    @property
    def is_connected(self) -> bool:
        return self._stack.currentIndex() == _IDX_CONNECTED

    @property
    def current_hwnd(self) -> "int | None":
        return self._current_hwnd
