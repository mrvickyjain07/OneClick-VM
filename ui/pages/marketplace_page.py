"""
ui/pages/marketplace_page.py
Premium Marketplace — banner + filters + featured + stats + grid + discovery.
"""
import sys, os, json, copy
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from pathlib import Path
from PyQt5.QtCore    import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QScrollArea as _SA,
    QFrame, QLabel, QPushButton as _QPB, QButtonGroup,
)
from PyQt5.QtGui import QColor
from qfluentwidgets import (
    ScrollArea, TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel,
    StrongBodyLabel, SearchLineEdit, CardWidget, SimpleCardWidget,
    PrimaryPushButton, PushButton, FlowLayout,
    InfoBar, InfoBarPosition, FluentIcon as FIF,
)

from models import OSTemplate, TemplateState, TEMPLATE_CATALOG
from ui.components.marketplace_card import MarketplaceCard
from ui.components.glass_os_card    import GlassOsCard
from ui.dialogs.vm_config_dialog    import VMConfigDialog
from ui.workers import DownloadWorker, InstallWorker
from frontend.widgets.marketplace_banner import MarketplaceBanner, BannerSlide


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_json() -> dict:
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)            # type: ignore
    else:
        root = Path(__file__).resolve().parent.parent.parent
    p = root / "frontend" / "data" / "marketplace.json"
    try:
        with p.open(encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _sep(parent=None) -> QFrame:
    line = QFrame(parent)
    line.setFrameShape(QFrame.HLine)
    line.setStyleSheet("border: none; background: rgba(255,255,255,0.08);")
    line.setFixedHeight(1)
    return line


# ── Category chip ─────────────────────────────────────────────────────────────

class _Chip(_QPB):
    def __init__(self, label: str, parent=None):
        super().__init__(label, parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(32)
        self._update_style()
        self.toggled.connect(lambda _: self._update_style())

    def _update_style(self):
        if self.isChecked():
            self.setStyleSheet(
                "QPushButton{background:#3b82f6;color:#fff;border-radius:16px;"
                "padding:0 14px;font-weight:600;border:none;}"
                "QPushButton:hover{background:#2563eb;}"
            )
        else:
            self.setStyleSheet(
                "QPushButton{background:rgba(255,255,255,0.07);color:rgba(255,255,255,0.7);"
                "border-radius:16px;padding:0 14px;border:1px solid rgba(255,255,255,0.1);}"
                "QPushButton:hover{background:rgba(255,255,255,0.12);color:#fff;}"
            )


# ── Stat mini-card ────────────────────────────────────────────────────────────

class _StatMini(SimpleCardWidget):
    def __init__(self, icon: str, label: str, value: str, color: str, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(4)
        top = QHBoxLayout()
        ic = QLabel(icon)
        ic.setStyleSheet(f"font-size:18px;color:{color};")
        lbl = CaptionLabel(label)
        lbl.setStyleSheet("color:rgba(255,255,255,0.5);")
        top.addWidget(ic); top.addSpacing(6); top.addWidget(lbl); top.addStretch()
        lay.addLayout(top)
        self._val = StrongBodyLabel(value)
        self._val.setStyleSheet(f"font-size:20px;font-weight:800;color:{color};")
        lay.addWidget(self._val)

    def set_value(self, v: str):
        self._val.setText(v)


# ── Premium Discovery Section (glass cards in responsive FlowLayout grid) ────

class _PremiumDiscoverySection(QWidget):
    """
    Section: title + optional subtitle + GlassOsCard grid (wraps on wide screens).
    """
    install_clicked = pyqtSignal(dict)

    def __init__(self, section: dict, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        title_lbl = SubtitleLabel(section.get("label", ""))
        title_lbl.setStyleSheet("font-size:17px;font-weight:700;")
        lay.addWidget(title_lbl)

        sub_text = section.get("subtitle", "")
        if sub_text:
            sub_lbl = CaptionLabel(sub_text)
            sub_lbl.setStyleSheet("color:rgba(255,255,255,0.45);font-size:11px;")
            lay.addWidget(sub_lbl)

        lay.addSpacing(6)

        flow_host = QWidget()
        flow_host.setStyleSheet("background:transparent;")
        flow = FlowLayout(flow_host)
        flow.setHorizontalSpacing(16)
        flow.setVerticalSpacing(16)
        flow.setContentsMargins(0, 0, 0, 0)

        for item in section.get("items", []):
            card = GlassOsCard(item)
            card.install_clicked.connect(self.install_clicked)
            flow.addWidget(card)

        lay.addWidget(flow_host)


# ── Main page ─────────────────────────────────────────────────────────────────

CATEGORIES = ["All", "Recommended", "Beginner", "Development", "Security",
              "Lightweight", "Enterprise", "Rolling"]

TAG_MAP = {
    "Recommended":  ["Beginner", "Learning", "Development"],
    "Beginner":     ["Beginner", "Learning", "Desktop"],
    "Development":  ["Development", "Dev", "Latest"],
    "Security":     ["Security", "Hacking"],
    "Lightweight":  ["Server", "Minimal"],
    "Enterprise":   ["Server", "Stable"],
    "Rolling":      ["Rolling", "DIY"],
}


class MarketplacePage(ScrollArea):
    def __init__(self, iso_manager, vm_service, parent=None):
        super().__init__(parent=parent)
        self.iso_manager = iso_manager
        self.vm_service  = vm_service
        self.setObjectName("MarketplacePage")
        self.setStyleSheet("background: transparent; border: none;")

        self._templates: dict[str, OSTemplate] = {
            t.os_id: copy.deepcopy(t) for t in TEMPLATE_CATALOG
        }
        self._cards:   dict[str, MarketplaceCard] = {}
        self._workers: list = []
        self._active_cat = "All"
        self._search_text = ""

        self._data = _load_json()

        container = QWidget()
        container.setObjectName("MktContainer")
        container.setAttribute(Qt.WA_StyledBackground, True)
        self.setWidget(container)
        self.setWidgetResizable(True)

        root = QVBoxLayout(container)
        root.setContentsMargins(32, 28, 32, 32)
        root.setSpacing(0)

        self._build_header(root)
        self._build_banner(root)
        self._build_search(root)
        self._build_filters(root)
        self._build_stats(root)
        root.addSpacing(8)
        root.addWidget(_sep())
        root.addSpacing(20)
        self._build_featured(root)       # GlassOsCard featured cards
        root.addSpacing(8)
        root.addWidget(_sep())
        root.addSpacing(20)
        self._build_all_templates(root)  # MarketplaceCard full grid
        root.addSpacing(8)
        root.addWidget(_sep())
        root.addSpacing(20)
        self._build_discovery(root)
        root.addStretch()

        self._init_cards()
        self._restore_download_state()

    # ── Section builders ─────────────────────────────────────────────────────

    def _build_header(self, root):
        title = TitleLabel("Marketplace")
        sub   = BodyLabel("Browse, download and install virtual machine templates.")
        sub.setWordWrap(True)
        sub.setStyleSheet("color:rgba(255,255,255,0.55);")
        root.addWidget(title)
        root.addSpacing(4)
        root.addWidget(sub)
        root.addSpacing(20)

    def _build_banner(self, root):
        slides = self._data.get("banner", [])
        if not slides:
            slides = [{"os_name": "OneClickVM Marketplace",
                       "tagline": "Discover and launch Linux VMs in one click.",
                       "tag": "Explore", "accent": "#00C6FF",
                       "gradient_start": "#0f2027", "gradient_end": "#1a3048"}]
        self._banner = MarketplaceBanner(slides)
        self._banner.setFixedHeight(BannerSlide.SLIDE_H + 34)
        self._banner.setAttribute(Qt.WA_StyledBackground, True)
        self._banner.setStyleSheet("MarketplaceBanner{background:#0f2027;border-radius:12px;}")
        self._banner.install_clicked.connect(self._on_banner_install)
        self._banner.learn_more_clicked.connect(
            lambda d: InfoBar.info("Learn More", d.get("os_name",""), duration=2500,
                                   position=InfoBarPosition.TOP_RIGHT, parent=self.window())
        )
        root.addWidget(self._banner)
        root.addSpacing(24)

    def _build_search(self, root):
        self._search = SearchLineEdit()
        self._search.setPlaceholderText("Search OS templates (Ubuntu, Fedora, Kali…)")
        self._search.setFixedHeight(42)
        self._search.setMaximumWidth(560)
        self._search.textChanged.connect(self._on_search)
        root.addWidget(self._search)
        root.addSpacing(16)

    def _build_filters(self, root):
        row = QHBoxLayout()
        row.setSpacing(8)
        self._chip_group = QButtonGroup(self)
        self._chip_group.setExclusive(True)
        for cat in CATEGORIES:
            chip = _Chip(cat)
            if cat == "All":
                chip.setChecked(True)
            chip.clicked.connect(lambda _, c=cat: self._on_category(c))
            self._chip_group.addButton(chip)
            row.addWidget(chip)
        row.addStretch()
        root.addLayout(row)
        root.addSpacing(20)

    def _build_stats(self, root):
        self._stat_total    = _StatMini("📦", "Total Templates",     str(len(TEMPLATE_CATALOG)), "#60a5fa")
        self._stat_installed= _StatMini("✅", "Installed",           "0",  "#22c55e")
        self._stat_popular  = _StatMini("🔥", "Most Popular",        "Ubuntu", "#f59e0b")
        self._stat_new      = _StatMini("🆕", "Recently Added",      str(len(self._data.get("sections",[{}])[-1].get("items",[]) if self._data.get("sections") else [])), "#a855f7")

        row = QHBoxLayout()
        row.setSpacing(16)
        for s in (self._stat_total, self._stat_installed, self._stat_popular, self._stat_new):
            row.addWidget(s)
        root.addLayout(row)

    def _build_featured(self, root):
        """Premium GlassOsCard grid — featured items from marketplace.json."""
        featured_items = self._data.get("featured", [])

        # Section header
        hdr = SubtitleLabel("⭐  Featured Templates")
        hdr.setStyleSheet("font-size:17px;font-weight:700;")
        root.addWidget(hdr)
        sub = CaptionLabel("Handpicked OS distributions for every use case")
        sub.setStyleSheet("color:rgba(255,255,255,0.45);font-size:11px;")
        root.addWidget(sub)
        root.addSpacing(16)

        if not featured_items:
            # Fallback: first 4 TEMPLATE_CATALOG items
            import copy as _copy
            featured_items = [
                {
                    "os_id":      t.os_id,
                    "os_name":    t.os_name,
                    "desc":       t.description,
                    "tags":       ", ".join(t.tags),
                    "difficulty": t.tags[0] if t.tags else "Medium",
                    "accent":     "#3b82f6",
                    "image_path": "",
                }
                for t in list(TEMPLATE_CATALOG)[:4]
            ]

        flow_host = QWidget()
        flow_host.setStyleSheet("background:transparent;")
        flow = FlowLayout(flow_host)
        flow.setHorizontalSpacing(24)
        flow.setVerticalSpacing(24)
        flow.setContentsMargins(0, 0, 0, 0)

        for item in featured_items:
            card = GlassOsCard(item, mode="featured")
            card.install_clicked.connect(self._on_discovery_install)
            flow.addWidget(card)

        root.addWidget(flow_host)

    def _build_all_templates(self, root):
        """Standard MarketplaceCard grid — full catalog, filterable."""
        hdr = SubtitleLabel("📦  Browse All Templates")
        hdr.setStyleSheet("font-size:17px;font-weight:700;")
        root.addWidget(hdr)
        sub = CaptionLabel("Full catalog — download ISO and create your VM")
        sub.setStyleSheet("color:rgba(255,255,255,0.45);font-size:11px;")
        root.addWidget(sub)
        root.addSpacing(16)

        self._grid = FlowLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(20)
        self._grid.setVerticalSpacing(20)
        root.addLayout(self._grid)

    def _build_discovery(self, root):
        sections = self._data.get("sections", [])
        for sec in sections:
            if not sec.get("items"):
                continue
            section_widget = _PremiumDiscoverySection(sec)
            section_widget.install_clicked.connect(self._on_discovery_install)
            root.addWidget(section_widget)
            root.addSpacing(24)

    # ── Card init ────────────────────────────────────────────────────────────

    def _init_cards(self):
        for tmpl in self._templates.values():
            card = MarketplaceCard(tmpl)
            card.action_requested.connect(self._handle_action)
            self._cards[tmpl.os_id] = card
            self._grid.addWidget(card)

    def _restore_download_state(self):
        installed = 0
        for os_id, tmpl in self._templates.items():
            if self.iso_manager.is_downloaded(tmpl.iso_filename):
                self._cards[os_id].set_state(TemplateState.DOWNLOADED)
                installed += 1
        self._stat_installed.set_value(str(installed))

    # ── Filtering ────────────────────────────────────────────────────────────

    def _on_category(self, cat: str):
        self._active_cat = cat
        self._apply_filter()

    def _on_search(self, text: str):
        self._search_text = text.lower()
        self._apply_filter()

    def _apply_filter(self):
        required_tags = TAG_MAP.get(self._active_cat, [])
        for os_id, card in self._cards.items():
            tmpl = self._templates[os_id]
            # Search match
            if self._search_text:
                search_ok = (
                    self._search_text in tmpl.os_name.lower()
                    or self._search_text in tmpl.version.lower()
                    or any(self._search_text in t.lower() for t in tmpl.tags)
                )
            else:
                search_ok = True
            # Category match
            if self._active_cat == "All":
                cat_ok = True
            else:
                cat_ok = any(rt.lower() in (t.lower() for t in tmpl.tags) for rt in required_tags)
            card.setVisible(search_ok and cat_ok)

    # ── Banner CTA ───────────────────────────────────────────────────────────

    def _on_banner_install(self, slide_data: dict):
        os_id   = slide_data.get("os_id", "")
        os_name = slide_data.get("os_name", "")
        tmpl = self._templates.get(os_id)
        if not tmpl:
            for t in self._templates.values():
                if os_name.lower() in t.os_name.lower():
                    tmpl = t
                    break
        if tmpl:
            self._handle_action(tmpl.os_id, "download")
        else:
            InfoBar.warning("Not Found", f"No template found for {os_name}.",
                            duration=3000, position=InfoBarPosition.TOP_RIGHT,
                            parent=self.window())

    def _on_discovery_install(self, item: dict):
        """Called when a GlassOsCard Install button is clicked."""
        os_id   = item.get("os_id", "")
        os_name = item.get("os_name", "")
        tmpl = self._templates.get(os_id)
        if not tmpl:
            for t in self._templates.values():
                if os_name.lower() in t.os_name.lower():
                    tmpl = t
                    break
        if tmpl:
            self._handle_action(tmpl.os_id, "download")
        else:
            InfoBar.info(
                "Browse Catalog",
                f"{os_name} is not in the active catalog yet. Use the cards above to install.",
                duration=4000, position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )


    # ── Action dispatch (unchanged) ──────────────────────────────────────────

    def _handle_action(self, os_id: str, action: str):
        tmpl = self._templates.get(os_id)
        card = self._cards.get(os_id)
        if not tmpl or not card:
            return
        if action == "download":
            self._start_download(tmpl, card)
        elif action == "install":
            self._start_install(tmpl, card)
        elif action == "launch":
            self._launch(tmpl)

    def _start_download(self, tmpl, card):
        # Guard: don't start a second download for the same template
        if tmpl.state == TemplateState.DOWNLOADING:
            return
        card.set_state(TemplateState.DOWNLOADING)
        worker = DownloadWorker(tmpl, self.iso_manager)
        card.bind_worker(worker)

        # Progress: pct + optional speed string
        self._dl_bytes = {}  # track per-worker accumulated bytes for speed calc
        import time as _time
        _start = [_time.monotonic()]

        def _on_progress(pct: int):
            elapsed = _time.monotonic() - _start[0]
            if elapsed > 0 and hasattr(tmpl, 'disk_gb'):
                speed_str = ""
                try:
                    # Estimate speed from progress delta
                    total_bytes = tmpl.disk_gb * 1024 * 1024 * 1024 if tmpl.disk_gb else 0
                    done_bytes  = total_bytes * pct / 100
                    bps = done_bytes / max(elapsed, 1)
                    if bps > 1_000_000:
                        speed_str = f"{bps/1_000_000:.1f} MB/s"
                    elif bps > 1_000:
                        speed_str = f"{bps/1_000:.0f} KB/s"
                except Exception:
                    speed_str = ""
                card.set_progress(pct, speed_str)
            else:
                card.set_progress(pct)

        worker.progress.connect(_on_progress)
        worker.finished.connect(lambda path: self._on_dl_done(tmpl, card, path, worker))
        worker.error.connect(lambda err: self._on_dl_err(tmpl, card, err, worker))
        self._workers.append(worker)
        worker.start()

    def _on_dl_done(self, tmpl, card, path, worker):
        self._remove_worker(worker)
        card.unbind_worker()
        card.set_state(TemplateState.DOWNLOADED)
        self._refresh_installed_count()
        InfoBar.success("Download Complete",
                        f"{tmpl.os_name} {tmpl.version} is ready to install.",
                        duration=4000, position=InfoBarPosition.TOP_RIGHT,
                        parent=self.window())

    def _on_dl_err(self, tmpl, card, err, worker):
        self._remove_worker(worker)
        card.unbind_worker()
        card.set_state(TemplateState.IDLE)
        InfoBar.error("Download Failed", err[:200], duration=6000,
                      position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _start_install(self, tmpl, card):
        """Open VM config dialog; VMConfigDialog runs the QuickDeployWorker internally."""
        dlg = VMConfigDialog(tmpl, self.iso_manager, self.vm_service, parent=self.window())

        def _on_vm_created(rec):
            card.set_state(TemplateState.READY)
            self._refresh_installed_count()
            InfoBar.success(
                "VM Created",
                f"'{rec.vm_name}' is ready. Visit My Machines to launch it.",
                duration=6000, position=InfoBarPosition.TOP_RIGHT,
                parent=self.window(),
            )

        dlg.vm_created.connect(_on_vm_created)
        card.set_state(TemplateState.INSTALLING)
        dlg.exec_()
        # If user cancelled without deploying, revert state to DOWNLOADED
        if tmpl.state == TemplateState.INSTALLING:
            card.set_state(TemplateState.DOWNLOADED)


    def _on_install_done(self, tmpl, card, rec, worker):
        self._remove_worker(worker)
        card.set_state(TemplateState.READY)
        self._refresh_installed_count()
        InfoBar.success("VM Created",
                        f"'{rec.vm_name}' is ready. Visit My Machines to launch it.",
                        duration=6000, position=InfoBarPosition.TOP_RIGHT,
                        parent=self.window())

    def _on_install_err(self, tmpl, card, err, worker):
        self._remove_worker(worker)
        card.set_state(TemplateState.DOWNLOADED)
        InfoBar.error("Install Failed", err[:300], duration=7000,
                      position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _launch(self, tmpl):
        InfoBar.info("My Machines",
                     "The VM is ready. Use My Machines to start it.",
                     duration=4000, position=InfoBarPosition.TOP_RIGHT,
                     parent=self.window())

    def _remove_worker(self, w):
        if w in self._workers:
            self._workers.remove(w)

    def _refresh_installed_count(self):
        count = sum(
            1 for os_id, tmpl in self._templates.items()
            if self.iso_manager.is_downloaded(tmpl.iso_filename)
        )
        self._stat_installed.set_value(str(count))
