"""
dashboard_page.py
=================
Main dashboard page showing all registered VMs as rich cards.
Replaces the old QListWidget-based dashboard.py.

Features:
- VM cards with status badges
- Refresh (live state query from VirtualBox)
- Start / Stop / Delete via background threads
- Loading overlay while actions run
- Delete confirmation dialog
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QMessageBox, QSizePolicy, QSpacerItem
)
from PyQt5.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve

from backend.vm_registry import VMRegistry
from backend.vbox_engine  import VBoxEngine
from frontend.widgets.vm_card         import VMCard
from frontend.workers.vm_action_worker import VMActionWorker
from frontend.widgets.marketplace_banner import MarketplaceBanner


# ── banner data loader (safe for dev + PyInstaller) ───────────────────────────
def _load_banner_slides() -> list:
    """Load banner entries from marketplace.json.  Returns [] on any failure."""
    if getattr(sys, "frozen", False):
        import sys as _s
        root = Path(_s._MEIPASS)          # type: ignore[attr-defined]
    else:
        root = Path(__file__).resolve().parent.parent.parent
    p = root / "frontend" / "data" / "marketplace.json"
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f).get("banner", [])
    except Exception:
        return []


class DashboardPage(QWidget):
    """Dashboard page — displays VM cards with live status."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry = VMRegistry()
        self.vbox     = VBoxEngine()
        self._workers: list[VMActionWorker] = []  # prevent GC
        self._cards:   dict[str, VMCard]    = {}
        self._selected_vm: str | None       = None
        self._build_ui()
        self.refresh()

    # ──────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(0)

        # ── Branding Header ───────────────────────────────────────────────
        from frontend.widgets.logo_widget import HeaderLogoWidget
        self.header_logo = HeaderLogoWidget()
        self.header_logo.clicked.connect(self.refresh)
        root.addWidget(self.header_logo)
        root.addSpacing(20)

        # ── Hero Banner Carousel ──────────────────────────────────────────
        # Reuses MarketplaceBanner + BannerDataLoader unchanged.
        # The banner auto-slides, crossfades, and loads real images from
        # frontend/assets/banners/ via the JSON catalog.
        slides = _load_banner_slides()
        if not slides:
            # Fallback slide when JSON is missing / empty
            slides = [{
                "os_name":        "OneClickVM Marketplace",
                "tagline":        "Discover, download, and launch Linux VMs in one click.",
                "tag":            "Explore",
                "accent":         "#00C6FF",
                "gradient_start": "#0f2027",
                "gradient_end":   "#1a3048",
            }]
        self._dashboard_banner = MarketplaceBanner(slides)
        # Intercept banner CTA — navigate to Marketplace page when clicked
        self._dashboard_banner.install_clicked.connect(
            lambda data: self._on_banner_action(data, "install")
        )
        self._dashboard_banner.learn_more_clicked.connect(
            lambda data: self._on_banner_action(data, "learn_more")
        )
        root.addWidget(self._dashboard_banner)
        root.addSpacing(24)

        # ── Page header ───────────────────────────────────────────────────
        header = QHBoxLayout()

        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Manage your virtual machines")
        subtitle.setObjectName("PageSubtitle")
        title_col.addWidget(title)
        title_col.addWidget(subtitle)
        header.addLayout(title_col)
        header.addStretch()

        # Action buttons
        self.btn_refresh = QPushButton("⟳  Refresh")
        self.btn_refresh.clicked.connect(self.refresh)

        self.btn_delete = QPushButton("🗑  Delete")
        self.btn_delete.setObjectName("DangerButton")
        self.btn_delete.clicked.connect(self._delete_selected)
        self.btn_delete.setEnabled(False)

        header.addWidget(self.btn_refresh)
        header.addSpacing(8)
        header.addWidget(self.btn_delete)
        root.addLayout(header)
        root.addSpacing(20)

        # ── Status bar ────────────────────────────────────────────────────
        self.status_label = QLabel("")
        self.status_label.setObjectName("VMDetail")
        root.addWidget(self.status_label)
        root.addSpacing(8)

        # ── Scrollable VM card list ───────────────────────────────────────
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        self._card_container = QWidget()
        self._card_layout = QVBoxLayout(self._card_container)
        self._card_layout.setSpacing(10)
        self._card_layout.setAlignment(Qt.AlignTop)
        self._card_layout.setContentsMargins(0, 0, 8, 0)

        scroll.setWidget(self._card_container)
        root.addWidget(scroll, stretch=1)

    # ──────────────────────────────────────────────────────────────────────────
    # Banner CTA handler
    # ──────────────────────────────────────────────────────────────────────────

    def _on_banner_action(self, data: dict, action: str):
        """
        Called when a banner button is clicked on the Dashboard.
        Tries to signal the main window to switch to the Marketplace page.
        Fails silently if the navigation signal is not available.
        """
        try:
            main_win = self.window()
            if hasattr(main_win, "navigate_to"):
                main_win.navigate_to("marketplace")
            elif hasattr(main_win, "switch_to_marketplace"):
                main_win.switch_to_marketplace()
        except Exception:
            pass

    # ──────────────────────────────────────────────────────────────────────────
    # Data Loading
    # ──────────────────────────────────────────────────────────────────────────

    def refresh(self):
        """Reload VM list from registry and live-query VirtualBox states."""
        self.status_label.setText("Refreshing...")
        self.btn_refresh.setEnabled(False)
        QTimer.singleShot(0, self._do_refresh)

    def _do_refresh(self):
        # Clear existing cards
        self._cards.clear()
        self._selected_vm = None
        self.btn_delete.setEnabled(False)

        while self._card_layout.count():
            item = self._card_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        vms = self.registry.list_vms()

        if not vms:
            empty = QLabel("No virtual machines found.\nCreate one from the 'Create VM' page.")
            empty.setAlignment(Qt.AlignCenter)
            empty.setObjectName("PageSubtitle")
            empty.setContentsMargins(0, 40, 0, 0)
            self._card_layout.addWidget(empty)
        else:
            for vm in vms:
                # Live state query (fast, synchronous — acceptable for list refresh)
                try:
                    live_state = self.vbox.get_vm_state(vm["vm_name"])
                except Exception:
                    live_state = vm.get("status", "unknown")

                vm["status"] = live_state
                card = VMCard(vm)
                card.clicked.connect(self._on_card_clicked)
                card.action_requested.connect(self._on_action_requested)
                self._card_layout.addWidget(card)
                self._cards[vm["vm_name"]] = card

        vm_count = len(vms)
        self.status_label.setText(f"{vm_count} virtual machine{'s' if vm_count != 1 else ''}")
        self.btn_refresh.setEnabled(True)

    # ──────────────────────────────────────────────────────────────────────────
    # Card Interaction
    # ──────────────────────────────────────────────────────────────────────────

    def _on_card_clicked(self, vm_name: str):
        # Deselect previous
        if self._selected_vm and self._selected_vm in self._cards:
            self._cards[self._selected_vm].set_selected(False)

        self._selected_vm = vm_name
        self._cards[vm_name].set_selected(True)
        self.btn_delete.setEnabled(True)

    def _on_action_requested(self, vm_name: str, action: str):
        if action == "start":
            self._run_vm_action(
                vm_name,
                lambda: self.vbox.start_vm(vm_name),
                f"Starting {vm_name}…",
                f"Started {vm_name} successfully."
            )
        elif action == "stop":
            self._run_vm_action(
                vm_name,
                lambda: self.vbox.poweroff_vm(vm_name),
                f"Stopping {vm_name}…",
                f"Powered off {vm_name}."
            )

    # ──────────────────────────────────────────────────────────────────────────
    # VM Actions
    # ──────────────────────────────────────────────────────────────────────────

    def _delete_selected(self):
        vm_name = self._selected_vm
        if not vm_name:
            return
        reply = QMessageBox.question(
            self, "Delete VM",
            f"Are you sure you want to permanently delete\n'{vm_name}'?\n\n"
            "This will remove all disks and snapshots.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            def _do_delete():
                self.vbox.delete_vm(vm_name)
                self.registry.remove_vm(vm_name)
            self._run_vm_action(
                vm_name, _do_delete,
                f"Deleting {vm_name}…",
                f"Deleted {vm_name}."
            )

    def _run_vm_action(self, vm_name: str, fn, busy_msg: str, success_msg: str):
        """Run a VM action in a QThread, update status, refresh on complete."""
        self.status_label.setText(busy_msg)
        self._set_controls_enabled(False)

        # Update card badge to show in-progress
        if vm_name in self._cards:
            self._cards[vm_name].update_state("saving")

        worker = VMActionWorker(fn, success_msg)
        worker.success.connect(lambda msg: self._on_action_success(msg))
        worker.error.connect(lambda err: self._on_action_error(err))
        self._workers.append(worker)
        worker.finished.connect(lambda: self._workers.remove(worker) if worker in self._workers else None)
        worker.start()

    def _on_action_success(self, msg: str):
        self._set_controls_enabled(True)
        self.status_label.setText(msg)
        QTimer.singleShot(1500, self.refresh)   # auto-refresh after 1.5 s

    def _on_action_error(self, error_msg: str):
        self._set_controls_enabled(True)
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", error_msg)
        self.refresh()

    def _set_controls_enabled(self, enabled: bool):
        self.btn_refresh.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled and bool(self._selected_vm))
