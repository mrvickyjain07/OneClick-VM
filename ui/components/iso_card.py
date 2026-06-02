"""
ui/components/iso_card.py
Polished ISO library card matching the VM Platform Fluent dark theme.

Signals:
  action_requested(iso_id: str, action: str)
    where action ∈ {"mount", "unmount", "delete", "details"}
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtGui     import QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QLabel
)
from qfluentwidgets import (
    CardWidget, BodyLabel, CaptionLabel, StrongBodyLabel,
    PushButton, PrimaryPushButton, FluentIcon as FIF
)
from backend.iso_validator import format_size

# ── Status badge styling ──────────────────────────────────────────────────────

_STATUS_STYLE = {
    "downloaded": ("Downloaded", "#22c55e", "rgba(34,197,94,0.15)",  "rgba(34,197,94,0.4)"),
    "mounted":    ("Mounted",    "#a78bfa", "rgba(167,139,250,0.15)", "rgba(167,139,250,0.4)"),
    "importing":  ("Importing",  "#60a5fa", "rgba(96,165,250,0.15)",  "rgba(96,165,250,0.4)"),
    "error":      ("Error",      "#ef4444", "rgba(239,68,68,0.15)",   "rgba(239,68,68,0.4)"),
    "available":  ("Available",  "#f59e0b", "rgba(245,158,11,0.15)",  "rgba(245,158,11,0.4)"),
}

# ── Category icons ────────────────────────────────────────────────────────────

_CAT_ICONS = {
    "Linux":    "🐧",
    "Windows":  "🪟",
    "Security": "🛡️",
    "Utility":  "🔧",
    "Custom":   "💿",
}


def _cat_icon(category: str) -> str:
    return _CAT_ICONS.get(category, "💿")


# ── Card widget ───────────────────────────────────────────────────────────────

class ISOCard(CardWidget):
    action_requested = pyqtSignal(str, str)   # (iso_id, action)

    def __init__(self, record, parent=None):
        super().__init__(parent)
        self.record = record
        self.setBorderRadius(14)
        # Mounted cards need more vertical space for extra action rows
        self.setFixedSize(310, 250 if record.mount_status == "mounted" else 220)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)
        self.setStyleSheet("""
            CardWidget {
                background: rgba(28, 28, 44, 0.95);
                border: 1px solid rgba(255,255,255,0.06);
            }
            CardWidget:hover {
                border: 1px solid rgba(96,165,250,0.3);
                background: rgba(35, 35, 55, 0.98);
            }
        """)

        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(18)
        shadow.setOffset(0, 5)
        shadow.setColor(QColor(0, 0, 0, 100))
        self.setGraphicsEffect(shadow)

        self._build()

    def _build(self):
        rec = self.record
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 14, 16, 14)
        root.setSpacing(8)

        # ── Header: icon + name + badge ──
        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        icon_lbl = QLabel(_cat_icon(rec.category))
        icon_lbl.setStyleSheet(
            "font-size: 30px; background: transparent; border: none;"
        )
        icon_lbl.setFixedSize(44, 44)
        icon_lbl.setAlignment(Qt.AlignCenter)

        title_col = QVBoxLayout()
        title_col.setSpacing(2)

        name_lbl = StrongBodyLabel(rec.name[:28])
        name_lbl.setStyleSheet(
            "font-size: 13px; font-weight: 700; color: #f1f5f9;"
            "background: transparent; border: none;"
        )

        vendor_lbl = CaptionLabel(rec.vendor or rec.category)
        vendor_lbl.setStyleSheet(
            "color: rgba(255,255,255,0.4); font-size: 10px;"
            "background: transparent; border: none;"
        )

        title_col.addWidget(name_lbl)
        title_col.addWidget(vendor_lbl)

        hdr.addWidget(icon_lbl)
        hdr.addLayout(title_col, stretch=1)

        # Status badge
        self._badge = self._make_badge(rec.status)
        hdr.addWidget(self._badge, alignment=Qt.AlignTop)
        root.addLayout(hdr)

        # ── File info ──
        info_col = QVBoxLayout()
        info_col.setSpacing(3)

        size_lbl = CaptionLabel(f"💾 {format_size(rec.file_size)}")
        size_lbl.setStyleSheet("color: rgba(255,255,255,0.45); background: transparent; border: none;")

        date_lbl = CaptionLabel(f"📅 {rec.added_date}")
        date_lbl.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent; border: none;")

        type_lbl = CaptionLabel(f"🗂 {rec.file_type.upper()}  •  {rec.category}")
        type_lbl.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent; border: none;")

        if rec.mounted_to_vm:
            mount_lbl = CaptionLabel(f"🔌 {rec.mounted_to_vm}")
            mount_lbl.setStyleSheet("color: #a78bfa; font-size: 10px; background: transparent; border: none;")
            info_col.addWidget(mount_lbl)

        info_col.addWidget(size_lbl)
        info_col.addWidget(date_lbl)
        info_col.addWidget(type_lbl)
        root.addLayout(info_col)

        root.addStretch()

        # ── Action buttons ──
        if rec.mount_status == "mounted":
            # ── PRIMARY: Create VM from this ISO ──
            create_btn = PrimaryPushButton(FIF.PLAY, "Create VM")
            create_btn.setFixedHeight(30)
            create_btn.setToolTip("Create a new virtual machine using this ISO as boot media")
            create_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "create_vm"))

            # ── SECONDARY: Attach to existing VM ──
            attach_btn = PushButton(FIF.LINK, "Attach")
            attach_btn.setFixedHeight(30)
            attach_btn.setToolTip("Attach this ISO to an existing stopped VM")
            attach_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "attach"))

            top_row = QHBoxLayout()
            top_row.setSpacing(6)
            top_row.addWidget(create_btn, stretch=1)
            top_row.addWidget(attach_btn)
            root.addLayout(top_row)

            # ── TERTIARY: unmount + util icons ──
            bot_row = QHBoxLayout()
            bot_row.setSpacing(6)
            unmount_btn = PushButton(FIF.REMOVE, "Unmount")
            unmount_btn.setFixedHeight(26)
            unmount_btn.setStyleSheet("font-size: 10px;")
            unmount_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "unmount"))

            del_btn  = PushButton(FIF.DELETE, "")
            del_btn.setFixedSize(26, 26)
            del_btn.setToolTip("Remove from library")
            del_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "delete"))

            info_btn = PushButton(FIF.INFO, "")
            info_btn.setFixedSize(26, 26)
            info_btn.setToolTip("View details")
            info_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "details"))

            bot_row.addWidget(unmount_btn)
            bot_row.addStretch()
            bot_row.addWidget(info_btn)
            bot_row.addWidget(del_btn)
            root.addLayout(bot_row)
        else:
            # ── Not mounted: single Mount button + util icons ──
            btn_row = QHBoxLayout()
            btn_row.setSpacing(6)

            mount_btn = PrimaryPushButton(FIF.LINK, "Mount")
            mount_btn.setFixedHeight(30)
            mount_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "mount"))

            del_btn  = PushButton(FIF.DELETE, "")
            del_btn.setFixedSize(30, 30)
            del_btn.setToolTip("Remove from library")
            del_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "delete"))

            info_btn = PushButton(FIF.INFO, "")
            info_btn.setFixedSize(30, 30)
            info_btn.setToolTip("View details")
            info_btn.clicked.connect(lambda: self.action_requested.emit(rec.id, "details"))

            btn_row.addWidget(mount_btn)
            btn_row.addStretch()
            btn_row.addWidget(info_btn)
            btn_row.addWidget(del_btn)
            root.addLayout(btn_row)


    # ── Helpers ───────────────────────────────────────────────────────────────

    def _make_badge(self, status: str) -> QLabel:
        text, color, bg, border = _STATUS_STYLE.get(
            status, ("Unknown", "#9ca3af", "rgba(156,163,175,0.15)", "rgba(156,163,175,0.4)")
        )
        badge = QLabel(text)
        badge.setAlignment(Qt.AlignCenter)
        badge.setStyleSheet(
            f"color: {color}; background: {bg}; border: 1px solid {border};"
            "border-radius: 10px; padding: 1px 8px; font-size: 10px; font-weight: 700;"
        )
        return badge

    def update_record(self, record):
        """Rebuild the card with a fresh record (after status change)."""
        self.record = record
        # Clear and rebuild layout
        old_layout = self.layout()
        if old_layout:
            while old_layout.count():
                item = old_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()
        self._build()
