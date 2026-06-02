"""
fluent_dashboard.py
====================
Dashboard page using reusable QFluentWidgets components.
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel
from PyQt5.QtCore import Qt, QTimer

from qfluentwidgets import (
    ScrollArea, TitleLabel, SubtitleLabel, SearchLineEdit,
    FlowLayout, InfoBar, InfoBarPosition, MessageBox, SimpleCardWidget,
    BodyLabel
)

from backend.vm_registry import VMRegistry
from backend.vbox_engine import VBoxEngine
from frontend.workers.vm_action_worker import VMActionWorker
from frontend.widgets.components import StatCard, VMCard, get_os_icon
from frontend.widgets.marketplace_banner import MarketplaceBanner


# ── banner data helper (dev + PyInstaller safe) ──────────────────────────
def _load_banner_slides() -> list:
    """Return the banner list from marketplace.json, or [] on any error."""
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)          # type: ignore[attr-defined]
    else:
        root = Path(__file__).resolve().parent.parent.parent
    p = root / "frontend" / "data" / "marketplace.json"
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f).get("banner", [])
    except Exception:
        return []

class QuickLaunchCard(SimpleCardWidget):
    def __init__(self, name, icon_char, parent=None):
        super().__init__(parent)
        self.setFixedSize(160, 90)
        cl = QVBoxLayout(self)
        cl.setAlignment(Qt.AlignCenter)
        cl.setSpacing(6)
        
        ic_lbl = TitleLabel(icon_char)
        ic_lbl.setAlignment(Qt.AlignCenter)
        
        nm_lbl = BodyLabel(name)
        nm_lbl.setAlignment(Qt.AlignCenter)
        nm_lbl.setWordWrap(True)
        
        cl.addWidget(ic_lbl)
        cl.addWidget(nm_lbl)

class DashboardPage(ScrollArea):
    """Dashboard page — Refactored to Component Architecture."""
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("DashboardPage")
        self.registry = VMRegistry()
        self.vbox     = VBoxEngine()
        self._workers = []
        self._cards   = {}

        self._container = QWidget()
        self._container.setObjectName("pageContainer")
        # WA_StyledBackground: prevents qfluentwidgets ScrollArea from
        # treating this container as transparent and skipping child paints.
        self._container.setAttribute(Qt.WA_StyledBackground, True)
        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setStyleSheet("background: transparent;")

        self._root = QVBoxLayout(self._container)
        self._root.setContentsMargins(24, 24, 24, 24)
        self._root.setSpacing(24)
        self._root.setAlignment(Qt.AlignTop)

        # ─ Build order: banner first, then rest ─────────────────────────────
        self._build_banner()
        self._build_header()
        self._build_search_and_ql()

        # -- VM Grid --
        self.vm_flow = FlowLayout()
        self.vm_flow.setContentsMargins(0, 0, 0, 0)
        self.vm_flow.setHorizontalSpacing(16)
        self.vm_flow.setVerticalSpacing(16)
        self._root.addLayout(self.vm_flow)

        QTimer.singleShot(200, self.refresh)

    def _build_banner(self):
        """Mount the image carousel at the top of the dashboard."""
        print("[DASHBOARD] _build_banner() called")   # diagnostic — remove after confirming
        slides = _load_banner_slides()
        print(f"[DASHBOARD] slides loaded: {len(slides)}")
        if not slides:
            slides = [{
                "os_name":        "OneClickVM Marketplace",
                "tagline":        "Discover, download, and launch Linux VMs in one click.",
                "tag":            "Explore Now",
                "accent":         "#00C6FF",
                "gradient_start": "#0f2027",
                "gradient_end":   "#1a3048",
            }]
        self._banner = MarketplaceBanner(slides)
        # Force a fixed height so the layout cannot collapse the widget.
        # The banner internally uses setMinimumHeight; setFixedHeight here
        # overrides any ScrollArea layout constraint.
        from frontend.widgets.marketplace_banner import BannerSlide
        self._banner.setFixedHeight(BannerSlide.SLIDE_H + 34)
        # Explicit background so the widget is never treated as transparent
        # by the qfluentwidgets ScrollArea viewport.
        self._banner.setStyleSheet(
            "MarketplaceBanner { background: #0f2027; border-radius: 12px; }"
        )
        self._banner.install_clicked.connect(
            lambda d: self._on_banner_action(d, "install")
        )
        self._banner.learn_more_clicked.connect(
            lambda d: self._on_banner_action(d, "learn_more")
        )
        self._root.addWidget(self._banner)
        print(f"[DASHBOARD] banner added to layout, fixed height={self._banner.height()}")

    def _on_banner_action(self, data: dict, action: str):
        """Forward banner CTA clicks to the main window navigator."""
        try:
            win = self.window()
            if hasattr(win, "navigate_to"):
                win.navigate_to("marketplace")
            elif hasattr(win, "switch_to_marketplace"):
                win.switch_to_marketplace()
        except Exception:
            pass

    def _build_header(self):
        # 1. Stats Row
        self.stats_layout = QHBoxLayout()
        self.stats_layout.setSpacing(16)

        self.stat_installed = StatCard("Installed", "0", "#00C6FF")
        self.stat_down = StatCard("Downloading", "0", "#0088ff")
        self.stat_avail = StatCard("Available", "0", "#8b949e")
        self.stat_total = StatCard("Total VMs", "0", "#ffffff")

        self.stats_layout.addWidget(self.stat_installed)
        self.stats_layout.addWidget(self.stat_down)
        self.stats_layout.addWidget(self.stat_avail)
        self.stats_layout.addWidget(self.stat_total)
        self._root.addLayout(self.stats_layout)

    def _build_search_and_ql(self):
        # 2. Search Bar
        self.search_input = SearchLineEdit()
        self.search_input.setPlaceholderText("Search virtual machines...")
        self.search_input.setFixedHeight(40)
        self._root.addWidget(self.search_input)
        
        # 3. Quick Launch
        ql_lbl = SubtitleLabel("Quick Launch")
        self._root.addWidget(ql_lbl)
        
        ql_layout = QHBoxLayout()
        ql_layout.setSpacing(16)
        mock_os = [("Ubuntu 22.04", "🐧"), ("Windows 11", "🪟"), ("Fedora 39", "🎩"), ("Debian 12", "🌀"), ("Kali Linux", "🐉")]
        
        for name, ic in mock_os:
            ql_layout.addWidget(QuickLaunchCard(name, ic))
            
        ql_layout.addStretch(1)
        self._root.addLayout(ql_layout)

    def refresh(self):
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self):
        self._cards.clear()
        
        while self.vm_flow.count():
            item = self.vm_flow.takeAt(0)
            if item is not None and getattr(item, 'widget', None):
                w = item.widget()
                if w: w.deleteLater()

        vms = self.registry.list_vms()
        self.stat_installed.set_value(len(vms))
        self.stat_total.set_value(len(vms))
        self.stat_avail.set_value(3) # Mocked available templates

        if not vms:
            empty = SubtitleLabel("No virtual machines found. Quick Launch one to start.")
            self.vm_flow.addWidget(empty)
        else:
            for vm in vms:
                try:
                    if self.vbox.is_virtualbox_installed():
                        state = self.vbox.get_vm_state(vm["vm_name"])
                    else:
                        state = "unknown"
                except Exception:
                    state = "unknown"
                
                card = VMCard(vm, state=state, parent=self._container)
                card.action_requested.connect(self._handle_vm_action)
                
                self.vm_flow.addWidget(card)
                self._cards[vm["vm_name"]] = card

    def _handle_vm_action(self, vm_name: str, action: str):
        if action == "start":
            self._run_vm_action(lambda: self.vbox.start_vm(vm_name), f"Starting {vm_name}...", f"Started {vm_name}")
        elif action == "stop":
            self._run_vm_action(lambda: self.vbox.poweroff_vm(vm_name), f"Stopping {vm_name}...", f"Stopped {vm_name}")
        elif action == "delete":
            msg = MessageBox("Delete VM", f"Permanently delete '{vm_name}'?", self.window())
            if msg.exec():
                from backend.vm_registry import VMRegistry as _R
                reg = _R()
                self._run_vm_action(lambda: (self.vbox.delete_vm(vm_name), reg.remove_vm(vm_name)), f"Deleting {vm_name}...", f"Deleted {vm_name}")
        elif action == "settings":
            InfoBar.info("Settings", f"Open settings for {vm_name}", parent=self.window())

    def _run_vm_action(self, fn, busy_msg: str, done_msg: str):
        if not self.vbox.is_virtualbox_installed():
            InfoBar.error("Error", "VirtualBox not found.", parent=self.window())
            return
            
        InfoBar.info("Working", busy_msg, parent=self.window())
        
        w = VMActionWorker(fn, done_msg)
        w.success.connect(lambda msg: self._on_action_done(msg, w))
        w.error.connect(lambda err: self._on_action_error(err, w))
        self._workers.append(w)
        w.start()

    def _on_action_done(self, msg: str, worker):
        if worker in self._workers: self._workers.remove(worker)
        InfoBar.success("Success", msg, duration=2000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())
        self.refresh()

    def _on_action_error(self, err: str, worker):
        if worker in self._workers: self._workers.remove(worker)
        InfoBar.error("Error", err, duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())
