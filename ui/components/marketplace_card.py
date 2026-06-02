"""
ui/components/marketplace_card.py
Production-grade VM marketplace card — clean QStackedWidget state machine.

One body QStackedWidget, four pages:
  PAGE_DEFAULT  — icon, name, desc, tags, requirements, primary action button
  PAGE_HOVER    — dark glass overlay: Download / Install / Requirements buttons
  PAGE_DOWNLOAD — progress bar, speed label, Pause, Cancel
  PAGE_INSTALL  — indeterminate progress + status text

No floating children. No .raise_(). No manual geometry.
State machine drives everything.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtWidgets import (
    QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy,
    QFrame, QGraphicsDropShadowEffect, QStackedWidget,
    QGraphicsOpacityEffect,
)
from PyQt5.QtGui import QColor

from qfluentwidgets import (
    CardWidget, TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel,
    StrongBodyLabel, PrimaryPushButton, PushButton, ProgressBar,
    FluentIcon as FIF, InfoBadge, SimpleCardWidget,
)

from models import OSTemplate, TemplateState


# ── Constants ─────────────────────────────────────────────────────────────────

PAGE_DEFAULT  = 0
PAGE_HOVER    = 1
PAGE_DOWNLOAD = 2
PAGE_INSTALL  = 3

OS_ICONS = {
    "ubuntu":  "🐧", "fedora":  "🎩", "debian":  "🌀",
    "kali":    "🐉", "arch":    "🏹", "opensuse":"🦎",
    "mint":    "🍃", "nixos":   "❄️", "alpine":  "🏔️", "windows": "🪟",
}

STATE_BADGE = {
    TemplateState.IDLE:        "Available",
    TemplateState.DOWNLOADING: "Downloading",
    TemplateState.DOWNLOADED:  "Ready to Install",
    TemplateState.INSTALLING:  "Installing…",
    TemplateState.READY:       "Installed",
}

TAG_COLORS = {
    "Beginner":    "#22c55e", "Development": "#3b82f6", "Dev":       "#3b82f6",
    "Learning":    "#a855f7", "Advanced":    "#ef4444", "Security":  "#f97316",
    "Hacking":     "#f97316", "Server":      "#64748b", "Stable":    "#10b981",
    "Minimal":     "#94a3b8", "Rolling":     "#f59e0b", "Desktop":   "#8b5cf6",
    "Cutting-Edge":"#06b6d4",
}


def _icon(os_id: str) -> str:
    for k, v in OS_ICONS.items():
        if k in os_id.lower():
            return v
    return "💻"


# ── Tag pill ──────────────────────────────────────────────────────────────────

class _TagPill(QFrame):
    def __init__(self, text: str, parent=None):
        super().__init__(parent)
        col = TAG_COLORS.get(text, "#64748b")
        self.setFixedHeight(22)
        self.setStyleSheet(
            f"background:{col}22;border:1px solid {col}66;"
            f"border-radius:11px;padding:0 8px;"
        )
        lay = QHBoxLayout(self)
        lay.setContentsMargins(8, 0, 8, 0)
        lbl = CaptionLabel(text)
        lbl.setStyleSheet(f"color:{col};border:none;background:transparent;")
        lay.addWidget(lbl)


# ── Requirements panel ────────────────────────────────────────────────────────

class _ReqPanel(QFrame):
    def __init__(self, template: OSTemplate, parent=None):
        super().__init__(parent)
        self.setStyleSheet(
            "background:rgba(255,255,255,0.04);border-radius:8px;"
            "border:1px solid rgba(255,255,255,0.08);"
        )
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 10, 14, 10)
        lay.setSpacing(6)

        def _row(k, v):
            r = QHBoxLayout()
            r.addWidget(CaptionLabel(f"  {k}"))
            r.addStretch()
            r.addWidget(CaptionLabel(v))
            lay.addLayout(r)

        lay.addWidget(StrongBodyLabel("Minimum Requirements"))
        _row("RAM",  f"{template.ram_mb // 1024} GB")
        _row("CPU",  f"{template.cpu_count} cores")
        _row("Disk", f"{template.disk_gb} GB")
        lay.addSpacing(4)
        lay.addWidget(StrongBodyLabel("Recommended"))
        _row("RAM", f"{template.ram_mb * 2 // 1024} GB")
        _row("CPU", f"{template.cpu_count * 2} cores")

        try:
            import psutil
            total_gb = psutil.virtual_memory().total / (1024 ** 3)
            cores    = psutil.cpu_count(logical=False) or 2
            if total_gb >= template.ram_mb / 1024 and cores >= template.cpu_count:
                compat, col = "✅  Compatible", "#22c55e"
            elif total_gb >= (template.ram_mb / 1024) / 2:
                compat, col = "⚠️  Limited", "#f59e0b"
            else:
                compat, col = "❌  Not Recommended", "#ef4444"
        except Exception:
            compat, col = "⚪  Unable to detect", "#94a3b8"

        lay.addSpacing(4)
        clbl = BodyLabel(f"Your system: {compat}")
        clbl.setStyleSheet(f"color:{col};")
        lay.addWidget(clbl)


# ── Pages ─────────────────────────────────────────────────────────────────────

def _make_page_default(template: OSTemplate, req_visible_flag: list,
                        toggle_req_fn, action_fn) -> tuple:
    """
    Returns (widget, badge_ref, req_panel_ref, action_btn_ref)
    Standard idle/downloaded/ready view.
    """
    w   = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(20, 20, 20, 20)
    lay.setSpacing(12)

    # Header
    hdr = QHBoxLayout()
    hdr.setSpacing(12)
    icon_lbl = TitleLabel(_icon(template.os_id))
    icon_lbl.setFixedSize(50, 50)
    icon_lbl.setAlignment(Qt.AlignCenter)
    icon_lbl.setStyleSheet("font-size:30px;")

    meta = QVBoxLayout()
    meta.setSpacing(2)
    name_row = QHBoxLayout()
    name_lbl = StrongBodyLabel(template.os_name)
    name_lbl.setStyleSheet("font-size:15px;font-weight:700;")
    badge = InfoBadge.info(STATE_BADGE[template.state])
    name_row.addWidget(name_lbl)
    name_row.addStretch()
    name_row.addWidget(badge)
    ver_lbl  = CaptionLabel(template.version)
    desc_lbl = BodyLabel(template.description)
    desc_lbl.setWordWrap(True)
    desc_lbl.setStyleSheet("color:rgba(255,255,255,0.65);")
    meta.addLayout(name_row)
    meta.addWidget(ver_lbl)
    meta.addWidget(desc_lbl)
    hdr.addWidget(icon_lbl)
    hdr.addLayout(meta, stretch=1)
    lay.addLayout(hdr)

    # Tags
    tags_row = QHBoxLayout()
    tags_row.setSpacing(6)
    for tag in template.tags:
        tags_row.addWidget(_TagPill(tag))
    tags_row.addStretch()
    lay.addLayout(tags_row)

    # Requirements panel
    req_panel = _ReqPanel(template)
    req_panel.setVisible(req_visible_flag[0])
    lay.addWidget(req_panel)

    # Action button
    action_btn = PrimaryPushButton("Download ISO")
    action_btn.setFixedHeight(40)
    action_btn.setIcon(FIF.DOWNLOAD)
    action_btn.clicked.connect(action_fn)
    lay.addWidget(action_btn)

    return w, badge, req_panel, action_btn


def _make_page_hover(download_fn, install_fn, req_fn) -> QWidget:
    """Dark glass overlay page with three action buttons."""
    w = QWidget()
    w.setStyleSheet("background:rgba(8,10,18,0.88);border-radius:16px;")

    lay = QVBoxLayout(w)
    lay.setContentsMargins(28, 0, 28, 0)
    lay.setSpacing(12)
    lay.addStretch()

    btn_dl = PrimaryPushButton("  ⬇  Download ISO")
    btn_dl.setFixedHeight(44)
    btn_dl.clicked.connect(download_fn)

    btn_in = PushButton("  🚀  Install VM")
    btn_in.setFixedHeight(44)
    btn_in.setStyleSheet(
        "QPushButton{background:rgba(255,255,255,0.10);color:#fff;"
        "border:1px solid rgba(255,255,255,0.20);border-radius:8px;font-weight:600;}"
        "QPushButton:hover{background:rgba(255,255,255,0.18);}"
    )
    btn_in.clicked.connect(install_fn)

    btn_req = PushButton("  📋  Requirements")
    btn_req.setFixedHeight(36)
    btn_req.setStyleSheet(
        "QPushButton{background:transparent;color:rgba(255,255,255,0.55);"
        "border:1px solid rgba(255,255,255,0.12);border-radius:8px;font-size:12px;}"
        "QPushButton:hover{color:#fff;border-color:rgba(255,255,255,0.3);}"
    )
    btn_req.clicked.connect(req_fn)

    lay.addWidget(btn_dl)
    lay.addWidget(btn_in)
    lay.addWidget(btn_req)
    lay.addStretch()

    # Store button refs so caller can show/hide them
    w._btn_dl  = btn_dl
    w._btn_in  = btn_in
    w._btn_req = btn_req
    return w


def _make_page_download(pause_fn, cancel_fn) -> tuple:
    """Downloading/paused page. Returns (widget, prog_bar, pct_lbl, speed_lbl, pause_btn)."""
    w   = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(20, 20, 20, 20)
    lay.setSpacing(10)
    lay.addStretch()

    status_lbl = StrongBodyLabel("Downloading…")
    status_lbl.setStyleSheet("font-size:14px;")
    lay.addWidget(status_lbl)

    prog_bar = ProgressBar()
    prog_bar.setRange(0, 100)
    prog_bar.setValue(0)
    prog_bar.setFixedHeight(8)
    lay.addWidget(prog_bar)

    info_row = QHBoxLayout()
    pct_lbl   = CaptionLabel("0%")
    speed_lbl = CaptionLabel("")
    speed_lbl.setStyleSheet("color:rgba(255,255,255,0.4);font-size:11px;")
    info_row.addWidget(pct_lbl)
    info_row.addStretch()
    info_row.addWidget(speed_lbl)
    lay.addLayout(info_row)

    ctrl_row = QHBoxLayout()
    ctrl_row.setSpacing(8)
    pause_btn = PushButton("⏸  Pause")
    pause_btn.setFixedHeight(34)
    pause_btn.setStyleSheet(
        "QPushButton{background:rgba(255,255,255,0.08);color:rgba(255,255,255,0.75);"
        "border:1px solid rgba(255,255,255,0.15);border-radius:8px;font-size:12px;}"
        "QPushButton:hover{background:rgba(255,255,255,0.15);color:#fff;}"
    )
    pause_btn.clicked.connect(pause_fn)

    cancel_btn = PushButton("✕  Cancel")
    cancel_btn.setFixedHeight(34)
    cancel_btn.setStyleSheet(
        "QPushButton{background:rgba(239,68,68,0.10);color:#ef9999;"
        "border:1px solid rgba(239,68,68,0.3);border-radius:8px;font-size:12px;}"
        "QPushButton:hover{background:rgba(239,68,68,0.25);color:#fff;}"
    )
    cancel_btn.clicked.connect(cancel_fn)

    ctrl_row.addWidget(pause_btn)
    ctrl_row.addWidget(cancel_btn)
    ctrl_row.addStretch()
    lay.addLayout(ctrl_row)
    lay.addStretch()

    w._status_lbl  = status_lbl
    w._prog_bar    = prog_bar
    w._pct_lbl     = pct_lbl
    w._speed_lbl   = speed_lbl
    w._pause_btn   = pause_btn
    return w, prog_bar, pct_lbl, speed_lbl, pause_btn


def _make_page_install() -> tuple:
    """Installing page with indeterminate progress + status text."""
    w   = QWidget()
    lay = QVBoxLayout(w)
    lay.setContentsMargins(20, 20, 20, 20)
    lay.setSpacing(10)
    lay.addStretch()

    title = StrongBodyLabel("Installing VM…")
    title.setStyleSheet("font-size:14px;")
    lay.addWidget(title)

    prog = ProgressBar()
    prog.setRange(0, 0)   # indeterminate
    prog.setFixedHeight(8)
    lay.addWidget(prog)

    stage_lbl = CaptionLabel("Setting up VirtualBox VM…")
    stage_lbl.setStyleSheet("color:rgba(255,255,255,0.55);font-size:11px;")
    lay.addWidget(stage_lbl)
    lay.addStretch()

    w._stage_lbl = stage_lbl
    return w, stage_lbl


# ── Main Card ─────────────────────────────────────────────────────────────────

class MarketplaceCard(CardWidget):
    """
    State-machine marketplace card driven by QStackedWidget.

    Signals
    -------
    action_requested(os_id, action)   action ∈ {'download', 'install', 'launch'}
    """
    action_requested = pyqtSignal(str, str)

    def __init__(self, template: OSTemplate, parent=None):
        super().__init__(parent)
        self.template     = template
        self._worker      = None
        self._is_paused   = False
        self._req_visible = [False]   # mutable flag shared with page_default builder
        self._tm_state    = template.state  # mirror of template.state, drives pages

        self.setMinimumWidth(360)
        self.setMaximumWidth(520)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setBorderRadius(16)
        self.setMouseTracking(True)

        self._build_ui()
        self._apply_shadow()
        self.set_state(template.state)

    # ── Build ─────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self._stack = QStackedWidget(self)
        root.addWidget(self._stack)

        # ── PAGE 0: default (idle / downloaded / ready) ───────────────────────
        (pg_default,
         self._badge,
         self._req_panel,
         self._action_btn) = _make_page_default(
            self.template,
            self._req_visible,
            self._toggle_req,
            self._on_action_default,
        )
        self._stack.addWidget(pg_default)      # index 0 = PAGE_DEFAULT

        # ── PAGE 1: hover overlay ─────────────────────────────────────────────
        pg_hover = _make_page_hover(
            download_fn = lambda: self._emit_and_restore("download"),
            install_fn  = lambda: self._emit_and_restore("install"),
            req_fn      = self._show_req_from_hover,
        )
        self._hover_page = pg_hover
        self._stack.addWidget(pg_hover)        # index 1 = PAGE_HOVER

        # ── PAGE 2: downloading / paused ─────────────────────────────────────
        (pg_dl,
         self._prog_bar,
         self._pct_lbl,
         self._speed_lbl,
         self._pause_btn) = _make_page_download(
            pause_fn  = self._on_pause_resume,
            cancel_fn = self._on_cancel,
        )
        self._dl_page = pg_dl
        self._stack.addWidget(pg_dl)           # index 2 = PAGE_DOWNLOAD

        # ── PAGE 3: installing ────────────────────────────────────────────────
        pg_install, self._stage_lbl = _make_page_install()
        self._stack.addWidget(pg_install)      # index 3 = PAGE_INSTALL

    def _apply_shadow(self):
        sh = QGraphicsDropShadowEffect(self)
        sh.setBlurRadius(28)
        sh.setOffset(0, 6)
        sh.setColor(QColor(0, 0, 0, 90))
        self.setGraphicsEffect(sh)

    # ── State machine ─────────────────────────────────────────────────────────

    def set_state(self, state: TemplateState):
        self._tm_state       = state
        self.template.state  = state
        self._badge.setText(STATE_BADGE.get(state, state.value))

        if state == TemplateState.IDLE:
            self._action_btn.setText("Download ISO")
            self._action_btn.setIcon(FIF.DOWNLOAD)
            self._action_btn.setEnabled(True)
            self._stack.setCurrentIndex(PAGE_DEFAULT)

        elif state == TemplateState.DOWNLOADING:
            self._prog_bar.setRange(0, 100)
            self._prog_bar.setValue(0)
            self._pct_lbl.setText("0%")
            self._speed_lbl.setText("")
            self._dl_page._status_lbl.setText("Downloading…")
            self._pause_btn.setText("⏸  Pause")
            self._is_paused = False
            self._stack.setCurrentIndex(PAGE_DOWNLOAD)

        elif state == TemplateState.DOWNLOADED:
            self._action_btn.setText("Install VM")
            self._action_btn.setIcon(FIF.SEND)
            self._action_btn.setEnabled(True)
            self._stack.setCurrentIndex(PAGE_DEFAULT)

        elif state == TemplateState.INSTALLING:
            self._stack.setCurrentIndex(PAGE_INSTALL)

        elif state == TemplateState.READY:
            self._action_btn.setText("Create & Launch VM")
            self._action_btn.setIcon(FIF.PLAY)
            self._action_btn.setEnabled(True)
            self._stack.setCurrentIndex(PAGE_DEFAULT)

        # Update hover page buttons to match state
        self._sync_hover_buttons()

    def _sync_hover_buttons(self):
        """Show only the contextually correct button(s) on the hover page."""
        hp = self._hover_page
        if self._tm_state == TemplateState.IDLE:
            hp._btn_dl.show()
            hp._btn_in.hide()
        elif self._tm_state == TemplateState.DOWNLOADED:
            hp._btn_dl.hide()
            hp._btn_in.show()
            hp._btn_in.setText("  🚀  Install VM")
        elif self._tm_state == TemplateState.READY:
            hp._btn_dl.hide()
            hp._btn_in.show()
            hp._btn_in.setText("  ▶  Launch VM")
        else:
            hp._btn_dl.hide()
            hp._btn_in.hide()

    # ── Progress ──────────────────────────────────────────────────────────────

    def set_progress(self, pct: int, speed_str: str = ""):
        self._prog_bar.setValue(pct)
        self._pct_lbl.setText(f"{pct}%")
        if speed_str:
            self._speed_lbl.setText(speed_str)

    def set_install_stage(self, msg: str):
        self._stage_lbl.setText(msg)

    # ── Worker binding ────────────────────────────────────────────────────────

    def bind_worker(self, worker):
        self._worker    = worker
        self._is_paused = False

    def unbind_worker(self):
        self._worker    = None
        self._is_paused = False

    # ── Pause / Resume / Cancel ───────────────────────────────────────────────

    def _on_pause_resume(self):
        if not self._worker:
            return
        if not self._is_paused:
            self._worker.pause()
            self._is_paused = True
            self._pause_btn.setText("▶  Resume")
            self._dl_page._status_lbl.setText("Paused")
            self._speed_lbl.setText("")
        else:
            self._worker.resume()
            self._is_paused = False
            self._pause_btn.setText("⏸  Pause")
            self._dl_page._status_lbl.setText("Downloading…")

    def _on_cancel(self):
        if self._worker:
            self._worker.cancel()
        self.unbind_worker()
        self.set_state(TemplateState.IDLE)

    # ── Default page actions ──────────────────────────────────────────────────

    def _on_action_default(self):
        state = self._tm_state
        if state == TemplateState.IDLE:
            self.action_requested.emit(self.template.os_id, "download")
        elif state == TemplateState.DOWNLOADED:
            self.action_requested.emit(self.template.os_id, "install")
        elif state == TemplateState.READY:
            self.action_requested.emit(self.template.os_id, "launch")

    def _emit_and_restore(self, action: str):
        """Emit from hover page, return to default page, then dispatch action."""
        self._stack.setCurrentIndex(PAGE_DEFAULT)
        state = self._tm_state
        if action == "download" and state == TemplateState.IDLE:
            self.action_requested.emit(self.template.os_id, "download")
        elif action == "install":
            if state == TemplateState.DOWNLOADED:
                self.action_requested.emit(self.template.os_id, "install")
            elif state == TemplateState.READY:
                self.action_requested.emit(self.template.os_id, "launch")

    def _show_req_from_hover(self):
        self._req_visible[0] = not self._req_visible[0]
        self._req_panel.setVisible(self._req_visible[0])
        self._stack.setCurrentIndex(PAGE_DEFAULT)

    def _toggle_req(self):
        self._req_visible[0] = not self._req_visible[0]
        self._req_panel.setVisible(self._req_visible[0])

    # ── Hover ─────────────────────────────────────────────────────────────────

    def enterEvent(self, event):
        super().enterEvent(event)
        # Only show hover overlay when card is interactive (not during async ops)
        if self._tm_state not in (TemplateState.DOWNLOADING, TemplateState.INSTALLING):
            self._sync_hover_buttons()
            self._stack.setCurrentIndex(PAGE_HOVER)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        if self._stack.currentIndex() == PAGE_HOVER:
            self._stack.setCurrentIndex(PAGE_DEFAULT)
