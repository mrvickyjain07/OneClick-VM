"""
fluent_marketplace.py  —  Marketplace Highlights Edition
==========================================================
Full redesign:
  ┌─────────────────────────────────────────────────────────┐
  │  [Hero Banner Carousel — auto-advancing, crossfade]     │
  ├─────────────────────────────────────────────────────────┤
  │  ⭐ Recommended for You       [horizontal scroll row]   │
  ├─────────────────────────────────────────────────────────┤
  │  🔥 Popular Templates         [horizontal scroll row]   │
  ├─────────────────────────────────────────────────────────┤
  │  🆕 Recently Added            [horizontal scroll row]   │
  ├─────────────────────────────────────────────────────────┤
  │  Stats row  +  Drop-zone  +  ISO catalog grid           │
  └─────────────────────────────────────────────────────────┘

All data is driven by frontend/data/marketplace.json.
The existing ISO download/install/start/stop machinery is preserved.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from typing import List, Dict

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QScrollArea, QSizePolicy, QFrame
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui  import QColor

from qfluentwidgets import (
    ScrollArea, PrimaryPushButton, SubtitleLabel, TitleLabel, StrongBodyLabel,
    FlowLayout, InfoBar, InfoBarPosition, SimpleCardWidget,
    MessageBox, BodyLabel, FluentIcon as FIF
)

from backend         import config
from backend.vm_registry  import VMRegistry
from backend.vbox_engine  import VBoxEngine
from frontend.workers.iso_worker     import DownloadWorker
from frontend.workers.install_worker import InstallWorker
from frontend.widgets.components     import StatCard, VMCard
from frontend.widgets.marketplace_banner import MarketplaceBanner
from frontend.widgets.template_card      import TemplateCard

import psutil


# ══════════════════════════════════════════════════════════════════════════════
# Data loading
# ══════════════════════════════════════════════════════════════════════════════

def _marketplace_data_path() -> Path:
    """Works in both dev and PyInstaller frozen mode."""
    if getattr(sys, "frozen", False):
        import sys as _s
        base = Path(_s._MEIPASS)                          # type: ignore[attr-defined]
    else:
        base = Path(__file__).resolve().parent.parent.parent
    return base / "frontend" / "data" / "marketplace.json"


def _load_marketplace() -> dict:
    p = _marketplace_data_path()
    if p.is_file():
        with p.open(encoding="utf-8") as f:
            return json.load(f)
    return {"banner": [], "sections": []}


# ══════════════════════════════════════════════════════════════════════════════
# Helpers
# ══════════════════════════════════════════════════════════════════════════════

def _recommend(total_ram_mb: int, cores: int):
    return max(2048, int(total_ram_mb * 0.25)), max(2, int(cores * 0.50))


# Full ISO catalog (kept for the legacy grid below the banner)
ISO_CATALOG: List[dict] = [
    {
        "os_id": "ubuntu_24_04", "os_name": "Ubuntu 24.04.4 LTS", "version": "24.04.4",
        "icon": "🐧",
        "iso_url": "https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso",
        "filename": "ubuntu-24.04.4-desktop-amd64.iso",
        "desc": "Best for beginners and developers",
        "tags": "Dev, Learning", "difficulty": "Easy",
        "ram_mb": 4096, "cpu": 2, "disk_gb": 30,
    },
    {
        "os_id": "fedora_40", "os_name": "Fedora 41 Workstation Live", "version": "41",
        "icon": "🎩",
        "iso_url": (
            "https://download.fedoraproject.org/pub/fedora/linux/releases/41/"
            "Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-41-1.4.iso"
        ),
        "filename": "Fedora-Workstation-Live-x86_64-41-1.4.iso",
        "desc": "Cutting-edge Linux with latest features",
        "tags": "Dev, Latest", "difficulty": "Medium",
        "ram_mb": 4096, "cpu": 2, "disk_gb": 25,
    },
]


# ══════════════════════════════════════════════════════════════════════════════
# Sub-widgets
# ══════════════════════════════════════════════════════════════════════════════

class _SectionLabel(QLabel):
    """Bold section header with an accent underline."""

    def __init__(self, text: str, parent=None):
        super().__init__(text, parent)
        self.setStyleSheet(
            "font-size: 15px; font-weight: 700; color: #e2e8f0; "
            "padding-bottom: 4px; background: transparent;"
        )
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)


class _HScrollRow(QWidget):
    """
    A single horizontally-scrollable row of TemplateCards for one section.
    """

    def __init__(self, section_data: dict, iso_states: dict, parent=None):
        super().__init__(parent)
        self._section = section_data
        self._cards:  Dict[str, TemplateCard] = {}

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # label
        root.addWidget(_SectionLabel(section_data.get("label", "")))

        # scroll area
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFixedHeight(220)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent;")

        inner = QWidget()
        inner.setStyleSheet("background: transparent;")
        row = QHBoxLayout(inner)
        row.setContentsMargins(0, 4, 0, 4)
        row.setSpacing(14)

        for item in section_data.get("items", []):
            os_id = item.get("os_id", "")
            state = iso_states.get(os_id, "not_downloaded")
            card  = TemplateCard(item, state=state)
            self._cards[os_id] = card
            row.addWidget(card)

        row.addStretch()
        scroll.setWidget(inner)
        root.addWidget(scroll)

    def cards(self) -> Dict[str, TemplateCard]:
        return self._cards


class DropZone(SimpleCardWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(120)
        self.setBorderRadius(12)
        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        ic  = TitleLabel("📤")
        ic.setAlignment(Qt.AlignCenter)
        lbl = SubtitleLabel("Drop ISO files here to add them")
        lbl.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)
        lay.addWidget(lbl)


# ══════════════════════════════════════════════════════════════════════════════
# MarketplacePage
# ══════════════════════════════════════════════════════════════════════════════

class MarketplacePage(ScrollArea):
    """
    Full Marketplace Highlights page.

    Layout (top → bottom)
    ─────────────────────
    1. Hero banner carousel
    2. Three TemplateCard horizontal-scroll sections  (from JSON)
    3. Stats row
    4. Drop zone
    5. ISO catalog FlowLayout (legacy VMCard grid)
    """

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("MarketplacePage")
        self._workers:  list = []
        self._registry  = VMRegistry()
        self._vbox      = VBoxEngine()

        # ── scrollable container ───────────────────────────────────────────────
        self._container = QWidget()
        self._container.setObjectName("pageContainer")
        # WA_StyledBackground: tells Qt to paint this widget's background even
        # when it lives inside a qfluentwidgets ScrollArea (which sets
        # WA_TranslucentBackground on its viewport by default).
        self._container.setAttribute(Qt.WA_StyledBackground, True)
        self.setWidget(self._container)
        self.setWidgetResizable(True)
        self.setStyleSheet("background: transparent;")

        self._root = QVBoxLayout(self._container)
        self._root.setContentsMargins(24, 20, 24, 24)
        self._root.setSpacing(24)
        # AlignTop: prevents the layout from vertically stretching the banner
        # to fill the entire scroll-viewport height.
        self._root.setAlignment(Qt.AlignTop)

        # ── load JSON data ─────────────────────────────────────────────────────
        mdata = _load_marketplace()

        # ── compute existing ISO states (once) ────────────────────────────────
        iso_states = self._compute_iso_states()

        # ── 1. Hero Banner ─────────────────────────────────────────────────────
        # Always construct the banner — even when slides=[] the widget will
        # show gradient fallbacks, preventing a silent invisible gap.
        slides = mdata.get("banner", [])
        self._banner = MarketplaceBanner(slides if slides else [
            {"os_name": "OneClickVM Marketplace",
             "tagline": "Discover and install Linux VMs in one click.",
             "tag": "Welcome",
             "accent": "#00C6FF",
             "gradient_start": "#0f2027",
             "gradient_end": "#203a43"}
        ])
        self._banner.install_clicked.connect(self._on_banner_install)
        self._banner.learn_more_clicked.connect(self._on_banner_learn_more)
        self._root.addWidget(self._banner)

        # ── 2. Template sections ───────────────────────────────────────────────
        self._section_rows: List[_HScrollRow] = []
        self._template_cards: Dict[str, TemplateCard] = {}   # os_id → card

        for sec in mdata.get("sections", []):
            row = _HScrollRow(sec, iso_states)
            for os_id, card in row.cards().items():
                card.action_requested.connect(self._on_template_action)
                self._template_cards[os_id] = card
            self._section_rows.append(row)
            self._root.addWidget(row)

        # ── 3. Stats row ───────────────────────────────────────────────────────
        stats_row = QHBoxLayout()
        stats_row.setSpacing(16)
        self.stat_installed  = StatCard("Installed",   "0", "#00C6FF")
        self.stat_downloaded = StatCard("Downloaded",  "0", "#0088ff")
        self.stat_avail      = StatCard("Available",   str(len(ISO_CATALOG)), "#8b949e")
        self.stat_updates    = StatCard("Updates",     "0", "#E3B341")
        for s in (self.stat_installed, self.stat_downloaded,
                  self.stat_avail,     self.stat_updates):
            stats_row.addWidget(s)
        self._root.addLayout(stats_row)

        # ── 4. Drop zone ───────────────────────────────────────────────────────
        self._root.addWidget(DropZone())

        # ── 5. ISO catalog header ──────────────────────────────────────────────
        cat_header = QHBoxLayout()
        cat_header.addWidget(SubtitleLabel("📦  ISO Manager"))
        cat_header.addStretch()
        btn_add = PrimaryPushButton("＋ Add ISO")
        cat_header.addWidget(btn_add)
        self._root.addLayout(cat_header)

        # ── 6. Legacy VMCard grid ──────────────────────────────────────────────
        self.iso_flow = FlowLayout()
        self.iso_flow.setContentsMargins(0, 0, 0, 0)
        self.iso_flow.setHorizontalSpacing(16)
        self.iso_flow.setVerticalSpacing(16)
        self._root.addLayout(self.iso_flow)
        self._root.addStretch()

        self._vmcards: Dict[str, VMCard] = {}
        for it in ISO_CATALOG:
            os_id = it["os_id"]
            state = iso_states.get(os_id, "not_downloaded")
            c = VMCard(it, state=state, parent=self._container)
            c.action_requested.connect(self._handle_vmcard_action)
            self._vmcards[os_id] = c
            self.iso_flow.addWidget(c)

        self._refresh_stats()

    # ── ISO state helper ──────────────────────────────────────────────────────

    def _compute_iso_states(self) -> Dict[str, str]:
        states: Dict[str, str] = {}
        vms = self._registry.list_vms()
        for it in ISO_CATALOG:
            os_id = it["os_id"]
            state = "not_downloaded"
            if (config.ISO_CACHE_DIR / it["filename"]).exists():
                state = "downloaded"
            installed = next((v for v in vms if v.get("os_id") == os_id), None)
            if installed:
                try:
                    if self._vbox.is_virtualbox_installed():
                        vs = self._vbox.get_vm_state(installed["vm_name"])
                        state = "running" if vs == "running" else "installed"
                    else:
                        state = "installed"
                    it["vm_name"] = installed["vm_name"]
                except Exception:
                    state = "installed"
            states[os_id] = state
        return states

    # ── banner interactions ───────────────────────────────────────────────────

    def _on_banner_install(self, data: dict):
        os_id = data.get("os_id", "")
        # Forward to the VMCard if it exists in the catalog
        item = next((it for it in ISO_CATALOG if it["os_id"] == os_id), None)
        if item:
            card = self._vmcards.get(os_id)
            if card:
                self._handle_vmcard_action(os_id, "download")
        else:
            InfoBar.info(
                "Coming Soon",
                f"{data.get('os_name', '')} is not yet in the catalog.",
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window()
            )

    def _on_banner_learn_more(self, data: dict):
        InfoBar.info(
            data.get("os_name", "OS Info"),
            data.get("tagline", ""),
            duration=4000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window()
        )

    # ── template card interactions ────────────────────────────────────────────

    def _on_template_action(self, os_id: str, action: str):
        # Mirror action to the VMCard in the legacy catalog if present
        item = next((it for it in ISO_CATALOG if it["os_id"] == os_id), None)
        if item:
            self._handle_vmcard_action(os_id, action)
        else:
            InfoBar.info(
                "Not in ISO Catalog",
                f"'{os_id}' is shown for preview only — add it to ISO_CATALOG to enable.",
                duration=3500,
                position=InfoBarPosition.TOP_RIGHT,
                parent=self.window()
            )

    # ── legacy VMCard action handler (unchanged logic) ────────────────────────

    def _handle_vmcard_action(self, identifier: str, action: str):
        item = next((it for it in ISO_CATALOG if it["os_id"] == identifier), None)
        if not item:
            return
        card = self._vmcards.get(identifier)
        if not card:
            return

        if action == "download":
            self._start_download(card, item)
        elif action == "install":
            self._start_install(card, item)
        elif action == "start":
            self._run_vm_action(card, item, lambda vm: self._vbox.start_vm(vm))
        elif action == "stop":
            self._run_vm_action(card, item, lambda vm: self._vbox.poweroff_vm(vm))
        elif action == "recommend":
            self._show_recommendation(item)
        elif action == "delete":
            msg = MessageBox("Delete", f"Delete {item['os_name']} completely?", self.window())
            if msg.exec():
                try:
                    (config.ISO_CACHE_DIR / item["filename"]).unlink(missing_ok=True)
                    if "vm_name" in item:
                        self._vbox.delete_vm(item["vm_name"])
                        self._registry.remove_vm(item["vm_name"])
                        del item["vm_name"]
                    card.update_state("not_downloaded")
                    self._sync_template_card(identifier, "not_downloaded")
                    self._refresh_stats()
                except Exception:
                    pass

    # ── download / install / run helpers ─────────────────────────────────────

    def _start_download(self, card: VMCard, item: dict):
        card.update_state("downloading")
        self._sync_template_card(item["os_id"], "downloading")
        w = DownloadWorker(item["iso_url"], str(config.ISO_CACHE_DIR / item["filename"]))
        w.progress.connect(card.update_progress)
        w.success.connect(lambda: self._on_dl_success(card, item["os_id"], w))
        w.error.connect(lambda err: self._on_dl_error(card, item["os_id"], err, w))
        self._workers.append(w)
        w.start()

    def _on_dl_success(self, card: VMCard, os_id: str, w):
        if w in self._workers:
            self._workers.remove(w)
        card.update_state("downloaded")
        self._sync_template_card(os_id, "downloaded")
        self._refresh_stats()
        InfoBar.success("Downloaded", "ISO finished downloading.",
                        position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _on_dl_error(self, card: VMCard, os_id: str, err: str, w):
        if w in self._workers:
            self._workers.remove(w)
        card.update_state("not_downloaded")
        self._sync_template_card(os_id, "not_downloaded")
        InfoBar.error("Failed", str(err),
                      position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _start_install(self, card: VMCard, item: dict):
        card.update_state("installing")
        self._sync_template_card(item["os_id"], "installing")
        w = InstallWorker(
            os_id=item["os_id"],
            ram_mb=item.get("ram_mb"),
            cpu_count=item.get("cpu"),
            disk_gb=item.get("disk_gb"),
        )
        w.finished.connect(lambda r: self._on_install_success(card, item, r, w))
        w.error.connect(lambda err: self._on_install_error(card, item["os_id"], err, w))
        self._workers.append(w)
        w.start()

    def _on_install_success(self, card: VMCard, item: dict, r: dict, w):
        if w in self._workers:
            self._workers.remove(w)
        if r.get("success"):
            item["vm_name"] = r.get("vm_name")
            card.update_state("running")
            self._sync_template_card(item["os_id"], "running")
            self._refresh_stats()
            InfoBar.success("Installed", f"{item['os_name']} installed and launched!",
                            position=InfoBarPosition.TOP_RIGHT, parent=self.window())
        else:
            card.update_state("downloaded")
            self._sync_template_card(item["os_id"], "downloaded")
            InfoBar.error("Install Failed", r.get("message", ""),
                          position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _on_install_error(self, card: VMCard, os_id: str, err: str, w):
        if w in self._workers:
            self._workers.remove(w)
        card.update_state("downloaded")
        self._sync_template_card(os_id, "downloaded")
        InfoBar.error("Install Error", str(err),
                      position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _run_vm_action(self, card: VMCard, item: dict, action_fn):
        vm_name = item.get("vm_name")
        if not vm_name:
            return
        try:
            action_fn(vm_name)
            vs = self._vbox.get_vm_state(vm_name)
            new_state = "running" if vs == "running" else "installed"
            card.update_state(new_state)
            self._sync_template_card(item["os_id"], new_state)
        except Exception as e:
            InfoBar.error("Error", str(e),
                          position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _show_recommendation(self, item: dict):
        try:
            total_ram_mb = int(psutil.virtual_memory().total / 1024 / 1024)
            cores = psutil.cpu_count(logical=False) or 2
        except Exception:
            total_ram_mb, cores = 8192, 4
        rec_ram, rec_cpu = _recommend(total_ram_mb, cores)
        InfoBar.info(
            "Hardware Recommendation",
            f"Host: {total_ram_mb} MB RAM, {cores} Cores\n"
            f"Suggested for {item['os_name']}: {rec_ram} MB RAM · {rec_cpu} Cores",
            duration=6000,
            position=InfoBarPosition.BOTTOM_RIGHT,
            parent=self.window()
        )

    # ── state sync helpers ─────────────────────────────────────────────────────

    def _sync_template_card(self, os_id: str, state: str):
        """Keep TemplateCards in the section rows in sync with VMCard state."""
        card = self._template_cards.get(os_id)
        if card:
            card.update_state(state)

    def _refresh_stats(self):
        installed = sum(
            1 for c in self._vmcards.values()
            if c.state in ("installed", "running", "poweroff")
        )
        downloaded = sum(
            1 for c in self._vmcards.values()
            if c.state in ("downloaded", "installed", "running", "poweroff", "installing")
        )
        self.stat_installed.set_value(installed)
        self.stat_downloaded.set_value(downloaded)
