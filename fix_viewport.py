"""
Regenerate vm_viewport.py with clean ASCII-safe content.
Run from OneClickVM root: python fix_viewport.py
"""
import os

content = '''import sys, os, time
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

try:
    from qfluentwidgets import IndeterminateProgressBar as _IndBar
    def _make_spinner(parent=None): return _IndBar(parent)
except ImportError:
    class _BounceBar(ProgressBar):
        def __init__(self, p=None):
            super().__init__(p); self.setRange(0, 100)
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

WS_VISIBLE      = 0x10000000
WS_CHILD        = 0x40000000
WS_CLIPCHILDREN = 0x02000000
WS_CLIPSIBLINGS = 0x04000000
GWL_STYLE       = -16

WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def find_vm_hwnd(vm_name):
    """Find the VirtualBox VM window by title (case-insensitive, all title formats)."""
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
        t = buf.value.lower()
        if vm_lower in t and "virtualbox" in t and "manager" not in t:
            found_hwnd.append(hwnd)
            return False
        return True

    _u32.EnumWindows(WNDENUMPROC(_cb), 0)
    return found_hwnd[0] if found_hwnd else 0


def _hwnd_has_size(hwnd):
    """Return True if the window has a non-zero client area (rendered)."""
    rect = wintypes.RECT()
    _u32.GetClientRect(hwnd, ctypes.byref(rect))
    return (rect.right - rect.left) > 10 and (rect.bottom - rect.top) > 10


def strip_decorations(hwnd):
    if not hwnd:
        return
    style = WS_VISIBLE | WS_CHILD | WS_CLIPCHILDREN | WS_CLIPSIBLINGS
    _u32.SetWindowLongW(hwnd, GWL_STYLE, style)
    _u32.SetWindowPos(hwnd, 0, 0, 0, 0, 0, 0x0020 | 0x0002 | 0x0001 | 0x0004)


class WindowFinderWorker(QThread):
    """
    Two-phase window finder:
    Phase 1 - poll EnumWindows until HWND appears
    Phase 2 - wait for non-zero client rect (window rendered)
    Prevents embedding a blank loading screen.
    """
    hwnd_found = pyqtSignal(int)
    timed_out  = pyqtSignal()

    RENDER_TIMEOUT_S = 15
    POLL_INTERVAL_S  = 0.5

    def __init__(self, vm_name, timeout_s=90, parent=None):
        super().__init__(parent)
        self.vm_name   = vm_name
        self.timeout_s = timeout_s
        self._stop     = False

    def request_stop(self):
        self._stop = True

    def run(self):
        deadline = time.time() + self.timeout_s
        hwnd = 0
        while not self._stop and time.time() < deadline:
            hwnd = find_vm_hwnd(self.vm_name)
            if hwnd:
                break
            time.sleep(self.POLL_INTERVAL_S)

        if self._stop:
            return
        if not hwnd:
            _log.warning("WindowFinderWorker: window not found for %r in %ds",
                         self.vm_name, self.timeout_s)
            self.timed_out.emit()
            return

        _log.info("WindowFinderWorker: HWND 0x%08X found - waiting for render", hwnd)
        render_deadline = time.time() + self.RENDER_TIMEOUT_S
        while not self._stop and time.time() < render_deadline:
            if _hwnd_has_size(hwnd):
                break
            time.sleep(0.25)

        if self._stop:
            return
        _log.info("WindowFinderWorker: emitting hwnd_found 0x%08X", hwnd)
        self.hwnd_found.emit(hwnd)


class VMViewport(QWidget):
    retry_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._vm_name         = ""
        self._worker          = None
        self._current_hwnd    = 0
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

    def _build_idle_panel(self):
        w = QWidget(); w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(14)
        icon  = QLabel("[VM]"); icon.setStyleSheet("font-size: 36px; color: rgba(255,255,255,0.5); background: transparent;"); icon.setAlignment(Qt.AlignCenter)
        title = StrongBodyLabel("Console Ready"); title.setStyleSheet("font-size: 16px; color: rgba(255,255,255,0.7); background: transparent;"); title.setAlignment(Qt.AlignCenter)
        sub = CaptionLabel("Start a VM from My Machines or ISO Manager.\\nThe live desktop will appear here automatically.")
        sub.setAlignment(Qt.AlignCenter); sub.setWordWrap(True); sub.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent;")
        lay.addWidget(icon); lay.addWidget(title); lay.addWidget(sub)
        return w

    def _build_connecting_panel(self):
        w = QWidget(); w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(18)
        icon = QLabel("[~]"); icon.setStyleSheet("font-size: 36px; color: #60a5fa; background: transparent;"); icon.setAlignment(Qt.AlignCenter)
        self._conn_title = StrongBodyLabel("Connecting..."); self._conn_title.setStyleSheet("font-size: 15px; color: #60a5fa; background: transparent;"); self._conn_title.setAlignment(Qt.AlignCenter)
        self._conn_sub = CaptionLabel("Waiting for VirtualBox window...\\nThis usually takes 5-15 seconds after VM starts."); self._conn_sub.setAlignment(Qt.AlignCenter); self._conn_sub.setWordWrap(True); self._conn_sub.setStyleSheet("color: rgba(255,255,255,0.45); background: transparent;")
        self._spinner = _make_spinner(w); self._spinner.setFixedWidth(280)
        lay.addWidget(icon); lay.addWidget(self._conn_title); lay.addWidget(self._conn_sub); lay.addWidget(self._spinner, alignment=Qt.AlignCenter)
        return w

    def _build_error_panel(self):
        w = QWidget(); w.setStyleSheet("background: transparent;")
        lay = QVBoxLayout(w); lay.setAlignment(Qt.AlignCenter); lay.setSpacing(16)
        icon = QLabel("[!]"); icon.setStyleSheet("font-size: 36px; color: #ef4444; background: transparent;"); icon.setAlignment(Qt.AlignCenter)
        self._err_title = StrongBodyLabel("Connection Failed"); self._err_title.setStyleSheet("font-size: 15px; color: #ef4444; background: transparent;"); self._err_title.setAlignment(Qt.AlignCenter)
        self._err_msg = CaptionLabel(""); self._err_msg.setAlignment(Qt.AlignCenter); self._err_msg.setWordWrap(True); self._err_msg.setStyleSheet("color: rgba(255,255,255,0.45); background: transparent;")
        retry = PrimaryPushButton(FIF.SYNC, "Retry"); retry.setFixedWidth(150); retry.clicked.connect(self.retry_requested)
        idle  = PushButton(FIF.CLOSE, "Back to Idle"); idle.setFixedWidth(150); idle.clicked.connect(lambda: self.disconnect())
        row = QHBoxLayout(); row.setSpacing(12); row.addWidget(retry, alignment=Qt.AlignCenter); row.addWidget(idle, alignment=Qt.AlignCenter)
        lay.addWidget(icon); lay.addWidget(self._err_title); lay.addWidget(self._err_msg); lay.addLayout(row)
        return w

    def connect_vm(self, vm_name):
        """
        Begin connecting to the VM window.
        Delays WindowFinderWorker start by 3 s to give VBox time to open its window.
        """
        self._vm_name = vm_name
        self.disconnect()
        self._conn_title.setText("Connecting to %r..." % vm_name)
        self._conn_sub.setText("Waiting for VirtualBox window...\\nThis usually takes 5-15 seconds after VM starts.")
        self._stack.setCurrentIndex(_IDX_CONNECTING)
        QTimer.singleShot(3000, lambda: self._start_finder(vm_name))

    def _start_finder(self, vm_name):
        if self._vm_name != vm_name:
            return
        _log.info("VMViewport: starting WindowFinderWorker for %r", vm_name)
        self._worker = WindowFinderWorker(vm_name, timeout_s=90, parent=self)
        self._worker.hwnd_found.connect(self._on_hwnd_found)
        self._worker.timed_out.connect(self._on_timeout)
        self._worker.start()

    def _on_hwnd_found(self, hwnd):
        self._current_hwnd = hwnd
        self._stack.setCurrentIndex(_IDX_CONNECTED)
        QApplication.processEvents()
        QTimer.singleShot(300, lambda: self._do_embed(hwnd))

    def _do_embed(self, hwnd):
        if hwnd != self._current_hwnd:
            return
        try:
            window = QWindow.fromWinId(hwnd)
            self._embed_container = QWidget.createWindowContainer(window)
            self._target_layout.addWidget(self._embed_container)
            strip_decorations(hwnd)
            container_hwnd = int(self._embed_container.winId())
            if container_hwnd:
                _u32.SetParent(hwnd, container_hwnd)
                _u32.MoveWindow(hwnd, 0, 0, self._target_area.width(), self._target_area.height(), True)
            self._validation_timer.start()
            _log.info("Embedded HWND 0x%08X", hwnd)
        except Exception as e:
            _log.error("Embedding failed: %s", e)
            self._show_error("Failed to embed VM window:\\n%s" % e)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._current_hwnd and self._embed_container:
            try:
                _u32.MoveWindow(self._current_hwnd, 0, 0,
                                max(self._target_area.width(), 1),
                                max(self._target_area.height(), 1), True)
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
        if not _u32.IsWindow(self._current_hwnd):
            _log.warning("VM window handle dead - reconnecting")
            self._reconnect(); return
        rect = wintypes.RECT()
        _u32.GetWindowRect(self._current_hwnd, ctypes.byref(rect))
        if (rect.right - rect.left) == 0 or (rect.bottom - rect.top) == 0:
            _log.warning("VM window size 0 - reconnecting")
            self._reconnect()

    def _reconnect(self):
        self.disconnect()
        if self._vm_name:
            self.connect_vm(self._vm_name)

    def _on_timeout(self):
        self._show_error(
            "Could not find the VirtualBox window after 90 seconds.\\n\\n"
            "- Confirm the VM is running (check My Machines page)\\n"
            "- The VM may still be booting - click Retry"
        )

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
        self._current_hwnd = 0
        self._stack.setCurrentIndex(_IDX_IDLE)

    def _show_error(self, msg):
        self._err_msg.setText(msg)
        self._stack.setCurrentIndex(_IDX_ERROR)

    @property
    def is_connected(self):
        return self._stack.currentIndex() == _IDX_CONNECTED

    @property
    def current_hwnd(self):
        return self._current_hwnd
'''

dest = os.path.join(os.path.dirname(__file__),
                    '..', 'ui', 'components', 'vm_viewport.py')
dest = os.path.normpath(dest)
with open(dest, 'w', encoding='utf-8') as f:
    f.write(content)
print("Written:", dest)
