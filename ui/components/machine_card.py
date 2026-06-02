"""
ui/components/machine_card.py
Card for My Machines page - shows installed VM instances.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QSizePolicy, QGraphicsDropShadowEffect
from PyQt5.QtGui import QColor

from PyQt5.QtWidgets import QLabel
from qfluentwidgets import (
    CardWidget, StrongBodyLabel, BodyLabel, CaptionLabel,
    PrimaryPushButton, PushButton, FluentIcon as FIF
)

from models import VMRecord, VMStatus

OS_ICONS = {"ubuntu": "🐧", "fedora": "🎩", "debian": "🌀", "kali": "🐉"}

def _icon(os_id: str) -> str:
    for k, v in OS_ICONS.items():
        if k in os_id.lower(): return v
    return "💻"


class MachineCard(CardWidget):
    """
    action_requested(vm_name, action) where action ∈ {'start','stop','delete'}
    """
    action_requested = pyqtSignal(str, str)

    def __init__(self, record: VMRecord, parent=None):
        super().__init__(parent)
        self.record = record
        self.setMinimumWidth(340)
        self.setMaximumWidth(500)
        self.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        self.setBorderRadius(16)
        self._build_ui()
        self._apply_shadow()
        self.update_status(record.status)

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(20, 20, 20, 20)
        root.setSpacing(12)

        # Header
        header = QHBoxLayout()
        icon = StrongBodyLabel(_icon(self.record.os_id))
        icon.setStyleSheet("font-size: 28px;")
        icon.setFixedSize(44, 44)

        info = QVBoxLayout()
        info.setSpacing(2)
        self._name_lbl = StrongBodyLabel(self.record.vm_name)
        self._name_lbl.setStyleSheet("font-size: 13px; font-weight: 700;")
        self._os_lbl   = CaptionLabel(self.record.os_name)
        self._badge    = QLabel("● Stopped")
        info.addWidget(self._name_lbl)
        info.addWidget(self._os_lbl)

        header.addWidget(icon)
        header.addLayout(info, stretch=1)
        header.addWidget(self._badge, alignment=Qt.AlignTop)
        root.addLayout(header)

        # Meta
        created = CaptionLabel(f"Created: {self.record.created_at}")
        created.setStyleSheet("color: rgba(255,255,255,0.4);")
        root.addWidget(created)

        specs_row = QHBoxLayout()
        for label in [
            f"RAM {self.record.ram_mb // 1024} GB",
            f"CPU {self.record.cpu_count}c",
            f"Disk {self.record.disk_gb} GB",
        ]:
            lbl = CaptionLabel(label)
            lbl.setStyleSheet(
                "color: #60a5fa; background: rgba(59,130,246,0.12);"
                "border-radius: 6px; padding: 2px 8px; border: none;"
            )
            specs_row.addWidget(lbl)
        specs_row.addStretch()
        root.addLayout(specs_row)

        # Actions
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)
        self._start_btn  = PrimaryPushButton(FIF.PLAY, "Start")
        self._stop_btn   = PushButton(FIF.POWER_BUTTON, "Stop")
        self._delete_btn = PushButton(FIF.DELETE, "Delete")
        self._start_btn.setFixedHeight(36)
        self._stop_btn.setFixedHeight(36)
        self._delete_btn.setFixedHeight(36)

        self._start_btn.clicked.connect(lambda: self.action_requested.emit(self.record.vm_name, "start"))
        self._stop_btn.clicked.connect(lambda: self.action_requested.emit(self.record.vm_name, "stop"))
        self._delete_btn.clicked.connect(lambda: self.action_requested.emit(self.record.vm_name, "delete"))

        self._snap_btn = PushButton(FIF.SAVE, "")
        self._snap_btn.setFixedSize(30, 30)
        self._snap_btn.setToolTip("Take Snapshot")
        self._snap_btn.clicked.connect(lambda: self.action_requested.emit(self.record.vm_name, "snapshot"))

        btn_row.addWidget(self._start_btn)
        btn_row.addWidget(self._stop_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._snap_btn)
        btn_row.addWidget(self._delete_btn)
        root.addLayout(btn_row)

    def _apply_shadow(self):
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 70))
        self.setGraphicsEffect(shadow)

    def update_status(self, status: VMStatus):
        self.record.status = status
        # Swap badge by hiding old one and inserting new
        # We stored badge in self._badge_container layout position
        if status == VMStatus.RUNNING:
            self._badge.setText("● Running")
            self._badge.setStyleSheet(
                "color: #22c55e; background: rgba(34,197,94,0.15);"
                "border: 1px solid rgba(34,197,94,0.4); border-radius: 10px;"
                "padding: 2px 10px; font-size: 11px;"
            )
            self._start_btn.setEnabled(False)
            self._stop_btn.setEnabled(True)
        elif status == VMStatus.STOPPED:
            self._badge.setText("● Stopped")
            self._badge.setStyleSheet(
                "color: #f59e0b; background: rgba(245,158,11,0.12);"
                "border: 1px solid rgba(245,158,11,0.35); border-radius: 10px;"
                "padding: 2px 10px; font-size: 11px;"
            )
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)
        else:
            self._badge.setText("● Unknown")
            self._badge.setStyleSheet(
                "color: #94a3b8; background: rgba(148,163,184,0.1);"
                "border: 1px solid rgba(148,163,184,0.3); border-radius: 10px;"
                "padding: 2px 10px; font-size: 11px;"
            )
            self._start_btn.setEnabled(True)
            self._stop_btn.setEnabled(False)

    def set_busy(self, busy: bool):
        try:
            self._start_btn.setEnabled(not busy)
            self._stop_btn.setEnabled(not busy)
            self._snap_btn.setEnabled(not busy)
            self._delete_btn.setEnabled(not busy)
        except RuntimeError:
            pass
