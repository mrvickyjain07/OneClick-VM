"""
app.py  —  Fluent Edition
==========================
Main window using FluentWindow from qfluentwidgets.
Dark mode, Fluent Design sidebar, smooth page transitions.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PyQt5.QtWidgets import QApplication
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon

from qfluentwidgets import (
    FluentWindow, FluentIcon as FIF,
    NavigationItemPosition,
    Theme, setTheme, setThemeColor,
    SplashScreen,
)
from qfluentwidgets import FluentTranslator

from frontend.pages.fluent_dashboard    import DashboardPage
from frontend.pages.fluent_marketplace  import MarketplacePage
from frontend.pages.fluent_create_vm    import CreateVMPage
from frontend.pages.fluent_snapshots    import SnapshotsPage
from frontend.pages.fluent_settings     import SettingsPage
from frontend.pages.fluent_console      import ConsolePage
from backend import config


class OneClickVMWindow(FluentWindow):
    """Main application window — Fluent Design Edition."""

    def __init__(self):
        super().__init__()
        config.ensure_directories()

        # ── Dark theme ─────────────────────────────────────────────────────
        setTheme(Theme.DARK)
        setThemeColor("#00C6FF")    # glowing cyan accent

        # ── Window geometry ────────────────────────────────────────────────
        self.setWindowTitle("OneClick VM Platform")
        self.resize(1280, 800)
        self.setMinimumSize(960, 640)
        
        self.setMicaEffectEnabled(True)
        self.setStyleSheet("background: transparent;")

        # ── Instantiate pages ──────────────────────────────────────────────
        self.dashboard_page   = DashboardPage(self)
        self.vm_settings_page = CreateVMPage(self)  # Map CreateVM to VM Settings for now
        self.iso_manager_page = MarketplacePage(self) # Map Marketplace to ISO Manager
        self.console_page     = ConsolePage(self)
        self.snapshots_page   = SnapshotsPage(self)
        self.settings_page    = SettingsPage(self)

        self._init_navigation()

    def _init_navigation(self):
        nav = self.navigationInterface

        # ── Top-level items ────────────────────────────────────────────────
        self.addSubInterface(
            self.dashboard_page,
            FIF.HOME,
            "Dashboard",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.vm_settings_page,
            FIF.SETTING,
            "VM Settings",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.iso_manager_page,
            FIF.SAVE,
            "ISO Manager",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.console_page,
            FIF.APPLICATION,
            "Console",
            NavigationItemPosition.TOP
        )
        self.addSubInterface(
            self.snapshots_page,
            FIF.CAMERA,
            "Snapshots",
            NavigationItemPosition.TOP
        )

        # ── Bottom items ───────────────────────────────────────────────────
        self.addSubInterface(
            self.settings_page,
            FIF.SETTING,
            "Settings",
            NavigationItemPosition.BOTTOM
        )

        # Wire cross-page refresh
        self.stackedWidget.currentChanged.connect(self._on_page_changed)

    def _on_page_changed(self, index: int):
        """Trigger page-specific data refresh on navigation."""
        widget = self.stackedWidget.widget(index)
        if widget is self.dashboard_page:
            self.dashboard_page.refresh()
        elif widget is self.snapshots_page:
            self.snapshots_page.refresh_vm_list()


def run():
    # Enable HiDPI
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps)

    app = QApplication(sys.argv)
    app.setAttribute(Qt.AA_DontCreateNativeWidgetSiblings)

    translator = FluentTranslator()
    app.installTranslator(translator)

    window = OneClickVMWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    run()
