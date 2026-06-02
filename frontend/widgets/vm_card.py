"""
vm_card.py
==========
A rich card widget for displaying a single VM on the dashboard.
Shows: VM name, OS type, status badge, RAM & disk info.
Emits clicked() signal and supports selected state.
"""
from PyQt5.QtWidgets import (
    QFrame, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy
)
from PyQt5.QtCore import pyqtSignal, Qt, QPropertyAnimation, QEasingCurve
from PyQt5.QtGui import QFont

from frontend.widgets.status_badge import StatusBadge


# ── OS type → emoji icon mapping ──────────────────────────────────────────────
OS_ICONS = {
    "ubuntu":  "🐧",
    "fedora":  "🎩",
    "debian":  "🌀",
    "centos":  "🔴",
    "arch":    "🏹",
    "kali":    "🐉",
    "windows": "🪟",
    "macos":   "🍎",
}


def _os_icon(os_id: str) -> str:
    """Returns an emoji icon for the given os_id string."""
    os_id_lower = os_id.lower()
    for key, icon in OS_ICONS.items():
        if key in os_id_lower:
            return icon
    return "💻"


class VMCard(QFrame):
    """
    Card widget representing a single VM.

    Signals:
        clicked(vm_name): emitted when the card is clicked
        action_requested(vm_name, action): emitted from action buttons
            action ∈ {'start', 'stop', 'delete', 'snapshot'}
    """
    clicked = pyqtSignal(str)
    action_requested = pyqtSignal(str, str)

    def __init__(self, vm_data: dict, parent=None):
        super().__init__(parent)
        self.vm_data = vm_data
        self.vm_name = vm_data.get("vm_name", "Unknown")
        self._selected = False

        self.setObjectName("VMCard")
        self.setCursor(Qt.PointingHandCursor)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(100)

        self._build_ui()

    def _build_ui(self):
        outer = QHBoxLayout(self)
        outer.setContentsMargins(16, 14, 16, 14)
        outer.setSpacing(12)

        # ── OS Icon ───────────────────────────────────────────────────────
        os_id = self.vm_data.get("os_id", "")
        icon_label = QLabel(_os_icon(os_id))
        icon_label.setFixedSize(40, 40)
        icon_label.setAlignment(Qt.AlignCenter)
        icon_label.setStyleSheet(
            "font-size: 26px; background-color: rgba(88,166,255,0.08); "
            "border-radius: 8px;"
        )
        outer.addWidget(icon_label)

        # ── VM Info ───────────────────────────────────────────────────────
        info_layout = QVBoxLayout()
        info_layout.setSpacing(3)

        # Name row
        name_row = QHBoxLayout()
        vm_name_label = QLabel(self.vm_name)
        vm_name_label.setObjectName("VMName")
        name_row.addWidget(vm_name_label)
        name_row.addStretch()

        # Status badge
        raw_state = self.vm_data.get("status", "unknown")
        self.badge = StatusBadge(raw_state)
        name_row.addWidget(self.badge)
        info_layout.addLayout(name_row)

        # Detail row: OS, RAM, disk
        os_name = self.vm_data.get("os_id", "Unknown OS")
        ram = self.vm_data.get("ram_mb", "?")
        disk = self.vm_data.get("disk_gb", "?")
        detail_text = f"{os_name}  ·  RAM: {ram} MB  ·  Disk: {disk} GB"
        detail_label = QLabel(detail_text)
        detail_label.setObjectName("VMDetail")
        info_layout.addWidget(detail_label)

        # Created date
        created = self.vm_data.get("created_at", "")
        if created:
            created_label = QLabel(f"Created: {created}")
            created_label.setObjectName("VMDetail")
            info_layout.addWidget(created_label)

        outer.addLayout(info_layout, stretch=1)

        # ── Action Buttons ────────────────────────────────────────────────
        btn_layout = QVBoxLayout()
        btn_layout.setSpacing(6)
        btn_layout.setAlignment(Qt.AlignVCenter)

        self.btn_start = QPushButton("▶ Start")
        self.btn_start.setObjectName("SuccessButton")
        self.btn_start.setFixedWidth(80)
        self.btn_start.clicked.connect(lambda: self.action_requested.emit(self.vm_name, "start"))

        self.btn_stop = QPushButton("■ Stop")
        self.btn_stop.setObjectName("DangerButton")
        self.btn_stop.setFixedWidth(80)
        self.btn_stop.clicked.connect(lambda: self.action_requested.emit(self.vm_name, "stop"))

        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        outer.addLayout(btn_layout)

    def update_state(self, raw_state: str):
        """Refresh the status badge with a new VirtualBox state string."""
        self.vm_data["status"] = raw_state
        self.badge.update_state(raw_state)

    def set_selected(self, selected: bool):
        self._selected = selected
        self.setProperty("selected", "true" if selected else "false")
        self.style().unpolish(self)
        self.style().polish(self)

    # ── Mouse Events ──────────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.vm_name)
        super().mousePressEvent(event)
