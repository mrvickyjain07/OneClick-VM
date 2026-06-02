"""
ui/components/quick_launch_tile.py
Horizontal OS tile for the Dashboard Quick Launch strip.

Features:
  • Emoji icon + name + version
  • Hover: scale 1.06 + glow border animation via QGraphicsDropShadowEffect
  • Click: emits tile_clicked(template)
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore  import Qt, QPropertyAnimation, QEasingCurve, pyqtSignal, QPoint
from PyQt5.QtGui   import QColor, QCursor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QGraphicsDropShadowEffect, QLabel, QGraphicsOpacityEffect
)
from qfluentwidgets import CaptionLabel, StrongBodyLabel, BodyLabel

_OS_ICONS = {
    "ubuntu":  ("🐧", "#e95420", "#f97316"),
    "fedora":  ("🎩", "#294172", "#60a5fa"),
    "debian":  ("🌀", "#a80030", "#f43f5e"),
    "kali":    ("🐉", "#2578bf", "#38bdf8"),
    "windows": ("🪟", "#0078d4", "#38bdf8"),
    "default": ("💻", "#6366f1", "#818cf8"),
}

def _style(os_id: str):
    for k, v in _OS_ICONS.items():
        if k in os_id.lower():
            return v
    return _OS_ICONS["default"]


class QuickLaunchTile(QWidget):
    tile_clicked = pyqtSignal(object)   # OSTemplate

    def __init__(self, template, parent=None):
        super().__init__(parent)
        self.template = template
        self._icon_char, self._color1, self._color2 = _style(template.os_id)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedSize(140, 140)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        # Drop shadow (glow effect)
        self._shadow = QGraphicsDropShadowEffect(self)
        self._shadow.setBlurRadius(16)
        self._shadow.setOffset(0, 4)
        self._shadow.setColor(QColor(self._color1))
        self.setGraphicsEffect(self._shadow)

        # Base card style
        self._normal_style  = self._build_style(0.10, self._color1)
        self._hover_style   = self._build_style(0.25, self._color2)
        self.setStyleSheet(self._normal_style)
        self.setAttribute(Qt.WA_StyledBackground, True)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 16, 16, 14)
        lay.setSpacing(6)
        lay.setAlignment(Qt.AlignCenter)

        icon_lbl = QLabel(self._icon_char)
        icon_lbl.setStyleSheet("font-size: 38px; background: transparent; border: none;")
        icon_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(icon_lbl)

        name_lbl = StrongBodyLabel(template.os_name)
        name_lbl.setStyleSheet(
            "font-size: 12px; font-weight: 700; color: #f1f5f9;"
            "background: transparent; border: none;"
        )
        name_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(name_lbl)

        ver_lbl = CaptionLabel(template.version)
        ver_lbl.setStyleSheet(
            f"font-size: 10px; color: {self._color2};"
            "background: transparent; border: none;"
        )
        ver_lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(ver_lbl)

    def _build_style(self, opacity: float, color: str) -> str:
        alpha = int(opacity * 255)
        return (
            f"QWidget {{ "
            f"  background: rgba(30,30,46,0.92);"
            f"  border: 1px solid {color};"
            f"  border-radius: 16px; "
            f"}}"
        )

    def enterEvent(self, e):
        self.setStyleSheet(self._hover_style)
        self._shadow.setBlurRadius(28)
        self._shadow.setColor(QColor(self._color2))
        super().enterEvent(e)

    def leaveEvent(self, e):
        self.setStyleSheet(self._normal_style)
        self._shadow.setBlurRadius(16)
        self._shadow.setColor(QColor(self._color1))
        super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton:
            self.tile_clicked.emit(self.template)
        super().mousePressEvent(e)
