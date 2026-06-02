"""
ui/pages/dashboard_page.py
Dashboard: live stats, Quick Launch strip, system info.
"""
import sys, os, json
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QScrollArea as _QScrollArea, QFrame
)
from qfluentwidgets import (
    ScrollArea, TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel,
    StrongBodyLabel, CardWidget, FluentIcon as FIF,
    PrimaryPushButton, PushButton, InfoBar, InfoBarPosition
)

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:
    _HAS_PSUTIL = False

from models import TEMPLATE_CATALOG
from ui.components.quick_launch_tile import QuickLaunchTile
from ui.dialogs.vm_config_dialog     import VMConfigDialog
from frontend.widgets.marketplace_banner import MarketplaceBanner, BannerSlide


# ── banner data helper (dev + PyInstaller safe) ───────────────────────────
def _load_banner_slides() -> list:
    """Read banner list from marketplace.json.  Returns [] on any error."""
    if getattr(sys, "frozen", False):
        from pathlib import Path
        root = Path(sys._MEIPASS)          # type: ignore[attr-defined]
    else:
        from pathlib import Path
        root = Path(__file__).resolve().parent.parent.parent
    p = root / "frontend" / "data" / "marketplace.json"
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f).get("banner", [])
    except Exception as exc:
        print(f"[DASHBOARD] banner JSON load failed: {exc}")
        return []


# ── Stat card ────────────────────────────────────────────────────────────────

class _StatCard(CardWidget):
    def __init__(self, icon, title: str, value: str, color: str = "#60a5fa", parent=None):
        super().__init__(parent)
        self.setBorderRadius(14)
        self.setFixedHeight(110)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 16, 20, 16)
        lay.setSpacing(6)

        row = QHBoxLayout()
        ic = StrongBodyLabel(icon)
        ic.setStyleSheet(f"font-size: 22px; color: {color};")
        t  = CaptionLabel(title)
        t.setStyleSheet("color: rgba(255,255,255,0.55);")
        row.addWidget(ic); row.addSpacing(8); row.addWidget(t); row.addStretch()
        lay.addLayout(row)

        self.val_lbl = TitleLabel(value)
        self.val_lbl.setStyleSheet(f"font-size: 26px; font-weight: 800; color: {color};")
        lay.addWidget(self.val_lbl)

    def set_value(self, v: str):
        self.val_lbl.setText(v)


# ── Dashboard ─────────────────────────────────────────────────────────────────

class DashboardPage(ScrollArea):
    vm_launched           = pyqtSignal(str)   # emitted when Quick Launch starts a VM
    navigate_to_marketplace = pyqtSignal()    # request main window to switch to Marketplace
    navigate_to_machines    = pyqtSignal()    # request main window to switch to My Machines
    def __init__(self, vm_service, machines_db, parent=None):
        super().__init__(parent=parent)
        self.vm_service  = vm_service
        self.machines_db = machines_db
        self.setObjectName("DashboardPage")
        self.setStyleSheet("background: transparent; border: none;")

        # Store references for iso_manager (set by app.py after construction)
        self._iso_manager = None

        container = QWidget()
        container.setObjectName("DashContainer")
        self.setWidget(container)
        self.setWidgetResizable(True)

        root = QVBoxLayout(container)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(28)

        # ── Branding Header ───────────────────────────────────────────────
        from frontend.widgets.logo_widget import HeaderLogoWidget
        self.header_logo = HeaderLogoWidget()
        self.header_logo.clicked.connect(self.refresh)
        root.addWidget(self.header_logo)

        # ── Hero Banner Carousel ──────────────────────────────────────────
        slides = _load_banner_slides()
        print(f"[DASHBOARD] banner slides: {len(slides)}")   # diagnostic
        if not slides:
            slides = [{
                "os_name":        "OneClickVM Marketplace",
                "tagline":        "Discover, download, and launch Linux VMs in one click.",
                "tag":            "Explore",
                "accent":         "#00C6FF",
                "gradient_start": "#0f2027",
                "gradient_end":   "#1a3048",
            }]
        self._banner = MarketplaceBanner(slides)
        self._banner.setFixedHeight(BannerSlide.SLIDE_H + 34)
        self._banner.setAttribute(Qt.WA_StyledBackground, True)
        self._banner.setStyleSheet(
            "MarketplaceBanner { background: #0f2027; border-radius: 12px; }"
        )
        # Wire banner CTA signals ───────────────────────────────────────
        # install  → try to launch VMConfigDialog for the slide's OS template
        # learn_more → navigate to Marketplace page
        self._banner.install_clicked.connect(self._on_banner_install)
        self._banner.learn_more_clicked.connect(
            lambda _data: self.navigate_to_marketplace.emit()
        )
        root.addWidget(self._banner)

        # ── Title ──
        title = TitleLabel("Dashboard")
        sub   = BodyLabel("Your virtual machine hub at a glance.")
        sub.setStyleSheet("color: rgba(255,255,255,0.55);")
        root.addWidget(title)
        root.addWidget(sub)

        # ── Stats row ──
        self._stat_installed = _StatCard("🖥️", "Installed VMs",  "—", "#60a5fa")
        self._stat_running   = _StatCard("▶️",  "Running",        "—", "#22c55e")
        self._stat_cpu       = _StatCard("⚡",  "Host CPU Cores", "—", "#a78bfa")
        self._stat_ram       = _StatCard("🧠",  "Host RAM",       "—", "#f59e0b")

        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        for c in (self._stat_installed, self._stat_running,
                  self._stat_cpu, self._stat_ram):
            stats_row.addWidget(c)
        root.addLayout(stats_row)

        # ── Quick Launch strip ──────────────────────────────────────────────
        ql_card = CardWidget()
        ql_card.setBorderRadius(16)
        ql_lay  = QVBoxLayout(ql_card)
        ql_lay.setContentsMargins(24, 20, 24, 24)
        ql_lay.setSpacing(14)

        ql_hdr = QHBoxLayout()
        ql_title = SubtitleLabel("⚡ Quick Launch")
        ql_sub   = CaptionLabel("One-click automated OS installation")
        ql_sub.setStyleSheet("color: rgba(255,255,255,0.45);")
        ql_col = QVBoxLayout()
        ql_col.setSpacing(2)
        ql_col.addWidget(ql_title)
        ql_col.addWidget(ql_sub)
        ql_hdr.addLayout(ql_col)
        ql_hdr.addStretch()
        ql_lay.addLayout(ql_hdr)

        # Horizontal scroll area for tiles
        tile_scroll = _QScrollArea()
        tile_scroll.setFrameShape(QFrame.NoFrame)
        tile_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        tile_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        tile_scroll.setWidgetResizable(True)
        tile_scroll.setFixedHeight(160)
        tile_scroll.setStyleSheet("background: transparent; border: none;")

        tile_container = QWidget()
        tile_container.setStyleSheet("background: transparent;")
        tile_row = QHBoxLayout(tile_container)
        tile_row.setContentsMargins(0, 8, 0, 8)
        tile_row.setSpacing(14)
        tile_row.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)

        for tmpl in TEMPLATE_CATALOG:
            tile = QuickLaunchTile(tmpl)
            tile.tile_clicked.connect(self._open_deploy_dialog)
            tile_row.addWidget(tile)

        tile_row.addStretch()
        tile_scroll.setWidget(tile_container)
        ql_lay.addWidget(tile_scroll)
        root.addWidget(ql_card)

        # ── Quick Actions ───────────────────────────────────────────────
        qa_card = CardWidget()
        qa_card.setBorderRadius(14)
        qa_lay  = QVBoxLayout(qa_card)
        qa_lay.setContentsMargins(24, 20, 24, 20)
        qa_lay.setSpacing(12)
        qa_lay.addWidget(SubtitleLabel("Quick Actions"))

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        self._btn_marketplace = PrimaryPushButton(FIF.CLOUD, "Browse Marketplace")
        self._btn_machines    = PushButton(FIF.IOT, "My Machines")
        self._btn_marketplace.setFixedHeight(40)
        self._btn_machines.setFixedHeight(40)
        # Wire to page-level signals so app.py can intercept navigation
        self._btn_marketplace.clicked.connect(
            lambda: (
                print("[DASHBOARD] Browse Marketplace clicked"),
                self.navigate_to_marketplace.emit(),
            )
        )
        self._btn_machines.clicked.connect(
            lambda: (
                print("[DASHBOARD] My Machines clicked"),
                self.navigate_to_machines.emit(),
            )
        )
        btn_row.addWidget(self._btn_marketplace)
        btn_row.addWidget(self._btn_machines)
        btn_row.addStretch()
        qa_lay.addLayout(btn_row)
        root.addWidget(qa_card)

        # ── System info ──
        sys_card = CardWidget()
        sys_card.setBorderRadius(14)
        sc_lay   = QVBoxLayout(sys_card)
        sc_lay.setContentsMargins(24, 20, 24, 20)
        sc_lay.setSpacing(8)
        sc_lay.addWidget(SubtitleLabel("Host System"))
        self._sys_lbl = BodyLabel("Detecting…")
        sc_lay.addWidget(self._sys_lbl)
        root.addWidget(sys_card)

        root.addStretch()
        QTimer.singleShot(200, self.refresh)

    # ── Public setter called by app.py ────────────────────────────────────

    def set_iso_manager(self, iso_manager):
        self._iso_manager = iso_manager

    # ── Banner CTA handlers ───────────────────────────────────────────────

    def _on_banner_install(self, slide_data: dict):
        """
        'Install' CTA on the hero banner.

        1. Try to match an entry in TEMPLATE_CATALOG by os_id or os_name.
        2. If matched + iso_manager ready → open VMConfigDialog (same as Quick Launch).
        3. Otherwise → navigate to Marketplace so the user can browse manually.
        """
        os_id   = slide_data.get("os_id",   "")
        os_name = slide_data.get("os_name", "")
        print(f"[DASHBOARD] Install clicked: os_id={os_id!r}  os_name={os_name!r}")

        matched = None
        for tmpl in TEMPLATE_CATALOG:
            if (os_id and getattr(tmpl, "os_id", "") == os_id) or \
               (os_name and os_name.lower() in getattr(tmpl, "name", "").lower()):
                matched = tmpl
                break

        if matched and self._iso_manager:
            self._open_deploy_dialog(matched)
        else:
            print(f"[DASHBOARD] No template match for {os_name!r} — navigating to Marketplace")
            self.navigate_to_marketplace.emit()

    # ── Quick Launch handler ──────────────────────────────────────────────

    def _open_deploy_dialog(self, template):
        if not self._iso_manager:
            InfoBar.warning(
                "Not Ready", "ISO manager not initialised yet.",
                duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
            )
            return

        dlg = VMConfigDialog.show_for(
            template    = template,
            iso_manager = self._iso_manager,
            vm_service  = self.vm_service,
            parent      = self.window(),
        )
        dlg.vm_created.connect(self._on_vm_created)
        dlg.exec_()

    def _on_vm_created(self, rec):
        self.refresh()
        InfoBar.success(
            "VM Created! 🎉",
            f"'{rec.vm_name}' is ready. Switching to Console…",
            duration=5000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )
        # Auto-navigate to Console
        self.vm_launched.emit(rec.vm_name)

    # ── Refresh ───────────────────────────────────────────────────────────

    def refresh(self):
        machines = self.machines_db.all()
        running  = sum(1 for m in machines if m.status.value == "running")
        self._stat_installed.set_value(str(len(machines)))
        self._stat_running.set_value(str(running))

        if _HAS_PSUTIL:
            cores  = psutil.cpu_count(logical=False) or psutil.cpu_count()
            ram_gb = psutil.virtual_memory().total / (1024 ** 3)
            self._stat_cpu.set_value(str(cores))
            self._stat_ram.set_value(f"{ram_gb:.1f} GB")
            self._sys_lbl.setText(
                f"CPU: {psutil.cpu_count()} logical cores  •  "
                f"RAM: {ram_gb:.1f} GB  •  "
                f"CPU Usage: {psutil.cpu_percent(interval=None):.0f}%"
            )
        else:
            self._stat_cpu.set_value("N/A")
            self._stat_ram.set_value("N/A")
            self._sys_lbl.setText("Install psutil for live system stats.")
