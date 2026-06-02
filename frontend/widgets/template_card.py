"""
template_card.py
=================
Compact, horizontally-scrollable OS template card for the Marketplace page.

Visual anatomy
──────────────
┌─────────────────────────────────┐
│  [emoji icon]  Name             │  ← top row
│                short desc       │
│                [tag chip] [diff]│
│  ─────────────────────────────  │
│  RAM: 4 GB  · CPU: 2  · 30 GB  │  ← spec row
│  [status pill]   [Action btn]   │  ← bottom row
└─────────────────────────────────┘
"""
from __future__ import annotations

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                              QLabel, QSizePolicy, QFrame)
from PyQt5.QtCore    import Qt, pyqtSignal, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui     import QColor, QPainter, QLinearGradient, QBrush, QPen, QFont

from qfluentwidgets  import (CardWidget, StrongBodyLabel, BodyLabel,
                              CaptionLabel, PrimaryPushButton, PushButton,
                              FluentIcon as FIF)


# ── helpers ────────────────────────────────────────────────────────────────────

_DIFFICULTY_COLORS = {
    "Easy":   "#22c55e",
    "Medium": "#f59e0b",
    "Hard":   "#ef4444",
    "Expert": "#a855f7",
}

_OS_ACCENT = {
    "ubuntu":  "#e95420",
    "fedora":  "#60a5fa",
    "debian":  "#a259f7",
    "kali":    "#00bfff",
    "arch":    "#1793d1",
    "mint":    "#87cf3e",
    "nixos":   "#7ebae4",
    "opensuse":"#73ba25",
    "alpine":  "#0d597f",
}

def _accent_for(os_id: str) -> str:
    for k, v in _OS_ACCENT.items():
        if k in os_id.lower():
            return v
    return "#00C6FF"


_STATE_LABELS = {
    "not_downloaded": ("Available",     "#8b949e"),
    "not_installed":  ("Available",     "#8b949e"),
    "downloading":    ("Downloading…",  "#60a5fa"),
    "downloaded":     ("Ready",         "#f59e0b"),
    "installing":     ("Installing…",   "#a78bfa"),
    "installed":      ("Installed",     "#22c55e"),
    "running":        ("Running",       "#00C6FF"),
    "poweroff":       ("Stopped",       "#8b949e"),
    "aborted":        ("Aborted",       "#ef4444"),
}


# ── StatusPill ─────────────────────────────────────────────────────────────────

class _StatusPill(QLabel):
    def __init__(self, text: str, color: str, parent=None):
        super().__init__(text, parent)
        self._color = color
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(22)
        self._refresh()

    def set_state(self, text: str, color: str):
        self._color = color
        self.setText(text)
        self._refresh()

    def _refresh(self):
        self.setStyleSheet(
            f"QLabel {{ color: {self._color}; background: transparent; "
            f"border: 1px solid {self._color}; border-radius: 11px; "
            "font-size: 10px; font-weight: 600; padding: 0 10px; }}"
        )
        fm = self.fontMetrics()
        self.setFixedWidth(fm.horizontalAdvance(self.text()) + 24)


# ══════════════════════════════════════════════════════════════════════════════
# TemplateCard
# ══════════════════════════════════════════════════════════════════════════════

class TemplateCard(CardWidget):
    """
    Compact card used in horizontal scroll sections.

    Signals
    ───────
    action_requested(os_id: str, action: str)
        action ∈ {"download", "install", "start", "stop"}
    """

    action_requested = pyqtSignal(str, str)

    _CARD_W = 230
    _CARD_H = 195

    def __init__(self, item: dict, state: str = "not_downloaded", parent=None):
        super().__init__(parent)
        self._item   = item
        self._os_id  = item.get("os_id", "unknown")
        self._accent = QColor(_accent_for(self._os_id))
        self.state   = state.lower()

        self.setFixedSize(self._CARD_W, self._CARD_H)
        self.setBorderRadius(12)
        self.setAttribute(Qt.WA_StyledBackground, True)

        self._build_ui()
        self.update_state(self.state)

    # ── construction ──────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 12)
        root.setSpacing(0)

        # ── top: icon + name/desc ─────────────────────────────────────────────
        top = QHBoxLayout()
        top.setSpacing(10)

        self._icon = QLabel(self._item.get("icon", "💻"))
        self._icon.setFixedSize(44, 44)
        self._icon.setAlignment(Qt.AlignCenter)
        self._icon.setStyleSheet(
            f"font-size: 26px; background: rgba(255,255,255,0.06); "
            "border-radius: 10px;"
        )

        info = QVBoxLayout()
        info.setSpacing(2)

        self._name = StrongBodyLabel(self._item.get("os_name", "Unknown"))
        self._name.setWordWrap(False)
        fnt = self._name.font()
        fnt.setPointSize(10)
        self._name.setFont(fnt)

        self._desc = CaptionLabel(self._item.get("desc", ""))
        self._desc.setWordWrap(True)
        self._desc.setStyleSheet("color: rgba(255,255,255,0.50);")

        # difficulty chip
        diff = self._item.get("difficulty", "")
        diff_color = _DIFFICULTY_COLORS.get(diff, "#8b949e")
        self._diff_lbl = QLabel(diff)
        self._diff_lbl.setStyleSheet(
            f"color: {diff_color}; font-size: 9px; font-weight: 700; "
            "background: transparent;"
        )

        info.addWidget(self._name)
        info.addWidget(self._desc)
        info.addWidget(self._diff_lbl)

        top.addWidget(self._icon)
        top.addLayout(info, 1)
        root.addLayout(top)

        root.addSpacing(10)

        # ── spec row ─────────────────────────────────────────────────────────
        spec_row = QHBoxLayout()
        spec_row.setSpacing(0)

        ram_gb = self._item.get("ram_mb", 0) // 1024
        cpu    = self._item.get("cpu", 1)
        disk   = self._item.get("disk_gb", 0)
        spec_text = f"RAM {ram_gb}G · CPU {cpu} · {disk}G"

        self._spec = CaptionLabel(spec_text)
        self._spec.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 9px;")
        spec_row.addWidget(self._spec)
        spec_row.addStretch()
        root.addLayout(spec_row)

        # ── divider ───────────────────────────────────────────────────────────
        root.addSpacing(8)
        div = QFrame()
        div.setFrameShape(QFrame.HLine)
        div.setStyleSheet("background: rgba(255,255,255,0.07); max-height: 1px;")
        root.addWidget(div)
        root.addSpacing(8)

        # ── bottom: status + action ───────────────────────────────────────────
        bottom = QHBoxLayout()
        bottom.setSpacing(8)

        self._status = _StatusPill("Available", "#8b949e")

        self._btn = PrimaryPushButton("Download")
        self._btn.setFixedHeight(30)
        self._btn.clicked.connect(self._on_action)
        fnt2 = self._btn.font()
        fnt2.setPointSize(9)
        self._btn.setFont(fnt2)

        bottom.addWidget(self._status)
        bottom.addStretch()
        bottom.addWidget(self._btn)
        root.addLayout(bottom)

        root.addStretch()

    # ── accent bar painted on top border ─────────────────────────────────────

    def paintEvent(self, e):
        super().paintEvent(e)
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        c = QColor(self._accent); c.setAlpha(130)
        p.setBrush(c)
        # top accent strip
        p.drawRoundedRect(0, 0, self.width(), 3, 1, 1)
        p.end()

    # ── state machine ─────────────────────────────────────────────────────────

    def update_state(self, state: str):
        self.state = state.lower()
        label, color = _STATE_LABELS.get(self.state, ("Unknown", "#8b949e"))
        self._status.set_state(label, color)

        if self.state in ("not_downloaded", "not_installed"):
            self._btn.setText("Download")
            self._btn.setEnabled(True)
        elif self.state == "downloading":
            self._btn.setText("…")
            self._btn.setEnabled(False)
        elif self.state == "downloaded":
            self._btn.setText("Install")
            self._btn.setEnabled(True)
        elif self.state == "installing":
            self._btn.setText("…")
            self._btn.setEnabled(False)
        elif self.state in ("installed", "poweroff", "aborted"):
            self._btn.setText("Launch")
            self._btn.setEnabled(True)
        elif self.state == "running":
            self._btn.setText("Stop")
            self._btn.setEnabled(True)
        else:
            self._btn.setText("N/A")
            self._btn.setEnabled(False)

    # ── signal routing ────────────────────────────────────────────────────────

    def _on_action(self):
        mapping = {
            "not_downloaded": "download",
            "not_installed":  "download",
            "downloaded":     "install",
            "installed":      "start",
            "poweroff":       "start",
            "aborted":        "start",
            "running":        "stop",
        }
        action = mapping.get(self.state)
        if action:
            self.action_requested.emit(self._os_id, action)

    # ── hover animation ───────────────────────────────────────────────────────

    def enterEvent(self, e):
        self.setStyleSheet(
            "CardWidget { border: 1px solid rgba(0,198,255,0.25); "
            "background: rgba(255,255,255,0.04); }"
        )
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setStyleSheet("")
        super().leaveEvent(e)
