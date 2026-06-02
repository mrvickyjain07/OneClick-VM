"""
sidebar.py
==========
Vertical sidebar navigation widget.
Emits page_changed(index) signal when a nav button is clicked.
"""
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QPushButton, QSizePolicy, QFrame
)
from PyQt5.QtCore import pyqtSignal, Qt
from PyQt5.QtGui import QFont


# ── Navigation items: (label, icon_emoji) ─────────────────────────────────────
NAV_ITEMS = [
    ("  🖥   Dashboard",   0),
    ("  🛒   Marketplace", 1),
    ("  ➕   Create VM",   2),
    ("  📸   Snapshots",   3),
    ("  ⚙   Settings",    4),
]


class SidebarButton(QPushButton):
    """A single nav button in the sidebar."""

    def __init__(self, text: str, index: int, parent=None):
        super().__init__(text, parent)
        self.index = index
        self.setObjectName("SidebarButton")
        self.setCheckable(False)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(44)
        self._set_active(False)

    def _set_active(self, active: bool):
        self.setProperty("active", "true" if active else "false")
        self.style().unpolish(self)
        self.style().polish(self)


class Sidebar(QWidget):
    """Left sidebar with vertical navigation buttons."""

    page_changed = pyqtSignal(int)   # emitted with page index on click

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setFixedWidth(210)
        self._buttons: list[SidebarButton] = []
        self._init_ui()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ── App title / logo area ──────────────────────────────────────────
        from frontend.widgets.logo_widget import SidebarLogoWidget
        self.logo_widget = SidebarLogoWidget()
        self.logo_widget.clicked.connect(lambda: self._on_nav_click(0)) # 0 is Dashboard
        layout.addWidget(self.logo_widget)

        # ── Divider ───────────────────────────────────────────────────────
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setObjectName("SidebarDivider")
        layout.addWidget(line)

        # ── Section label ─────────────────────────────────────────────────
        nav_label = QLabel("NAVIGATION")
        nav_label.setObjectName("SectionLabel")
        nav_label.setContentsMargins(0, 12, 0, 4)
        layout.addWidget(nav_label)

        # ── Nav buttons ───────────────────────────────────────────────────
        for text, index in NAV_ITEMS:
            btn = SidebarButton(text, index)
            btn.clicked.connect(lambda _, i=index: self._on_nav_click(i))
            self._buttons.append(btn)
            layout.addWidget(btn)

        # ── Spacer ────────────────────────────────────────────────────────
        layout.addStretch()

        # ── Bottom version info ───────────────────────────────────────────
        footer = QLabel("VirtualBox Integration")
        footer.setObjectName("AppVersion")
        footer.setContentsMargins(16, 0, 0, 16)
        layout.addWidget(footer)

        # Select first by default
        self._set_active(0)

    def _on_nav_click(self, index: int):
        self._set_active(index)
        self.page_changed.emit(index)

    def _set_active(self, index: int):
        for btn in self._buttons:
            btn._set_active(btn.index == index)

    def set_page(self, index: int):
        """Programmatically select a nav item."""
        self._set_active(index)
