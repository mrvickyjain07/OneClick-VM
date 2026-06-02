"""
fluent_create_vm.py
====================
Create VM page — Fluent edition.
OS selector, RAM/CPU sliders, disk input, AI recommendation,
progress bar, log console. All in Fluent Design style.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from qfluentwidgets import (
    ScrollArea, CardWidget, SimpleCardWidget,
    TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton,
    ComboBox, Slider, SpinBox, ProgressBar,
    TextEdit, FluentIcon as FIF,
    MessageBox, InfoBar, InfoBarPosition,
    setTheme, Theme,
)

from backend.template_manager import TemplateManager
from frontend.workers.install_worker import InstallWorker

try:
    import psutil
    _RAM_MB  = int(psutil.virtual_memory().total / 1024 / 1024)
    _CORES   = psutil.cpu_count(logical=False) or 2
except ImportError:
    _RAM_MB, _CORES = 8192, 4


def _recommend(os_id, total_ram, cores):
    o = os_id.lower()
    if "fedora" in o:
        return max(2048, int(total_ram * 0.30)), max(2, int(cores * 0.60))
    if "windows" in o:
        return max(4096, int(total_ram * 0.40)), max(2, int(cores * 0.50))
    if "kali" in o or "arch" in o:
        return max(2048, int(total_ram * 0.25)), max(2, int(cores * 0.50))
    return max(2048, int(total_ram * 0.25)), max(2, int(cores * 0.50))


class CreateVMPage(ScrollArea):
    """Create VM page — Fluent edition."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("CreateVMPage")
        self._tmgr = TemplateManager()
        self._tmgr.load_templates()
        self._worker: InstallWorker | None = None

        container = QWidget()
        container.setObjectName("CreateVMContainer")
        self.setWidget(container)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()

        root = QVBoxLayout(container)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(20)

        # ── Header ─────────────────────────────────────────────────────────
        root.addWidget(TitleLabel("Create VM"))
        sub = BodyLabel("One-click install  ·  configure resources before launch")
        sub.setTextColor(QColor("#8B949E"), QColor("#666"))
        root.addWidget(sub)

        # ── Two-column layout ──────────────────────────────────────────────
        cols = QHBoxLayout()
        cols.setSpacing(20)

        # Left column
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addWidget(self._os_card())
        left.addWidget(self._resource_card())
        left.addLayout(self._action_row())
        left.addStretch()
        cols.addLayout(left, 1)

        # Right column (progress + log)
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addLayout(self._progress_section())
        right.addWidget(self._log_card(), 1)
        cols.addLayout(right, 1)

        root.addLayout(cols, 1)

    # ── Sub-widgets ────────────────────────────────────────────────────────────

    def _os_card(self) -> CardWidget:
        card = CardWidget()
        card.setFixedHeight(95)
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 12, 16, 12)
        lay.setSpacing(6)

        lbl = CaptionLabel("OPERATING SYSTEM")
        lbl.setTextColor(QColor("#8B949E"), QColor("#666"))
        lay.addWidget(lbl)

        self.os_combo = ComboBox()
        self.os_combo.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        for t in self._tmgr.list_templates():
            self.os_combo.addItem(f"  {t['os_name']}  ({t['version']})", t["os_id"])
        self.os_combo.currentIndexChanged.connect(lambda _: self.rec_lbl.setText(""))
        lay.addWidget(self.os_combo)
        return card

    def _resource_card(self) -> CardWidget:
        card = CardWidget()
        lay = QVBoxLayout(card)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(14)

        hdr = CaptionLabel("RESOURCE CONFIGURATION")
        hdr.setTextColor(QColor("#8B949E"), QColor("#666"))
        lay.addWidget(hdr)

        # RAM
        ram_row = QHBoxLayout()
        ram_lbl = BodyLabel("RAM")
        ram_lbl.setFixedWidth(50)
        self.ram_slider = Slider(Qt.Horizontal)
        self.ram_slider.setMinimum(512)
        self.ram_slider.setMaximum(_RAM_MB)
        self.ram_slider.setSingleStep(256)
        self.ram_slider.setValue(2048)
        self.ram_val = BodyLabel("2048 MB")
        self.ram_val.setFixedWidth(80)
        self.ram_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.ram_slider.valueChanged.connect(
            lambda v: self.ram_val.setText(f"{v/1024:.1f} GB" if v >= 1024 else f"{v} MB")
        )
        ram_row.addWidget(ram_lbl)
        ram_row.addWidget(self.ram_slider, 1)
        ram_row.addWidget(self.ram_val)
        lay.addLayout(ram_row)

        # CPU
        cpu_row = QHBoxLayout()
        cpu_lbl = BodyLabel("CPU")
        cpu_lbl.setFixedWidth(50)
        self.cpu_slider = Slider(Qt.Horizontal)
        self.cpu_slider.setMinimum(1)
        self.cpu_slider.setMaximum(max(_CORES, 1))
        self.cpu_slider.setValue(min(2, _CORES))
        self.cpu_val = BodyLabel(f"{self.cpu_slider.value()} cores")
        self.cpu_val.setFixedWidth(80)
        self.cpu_val.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.cpu_slider.valueChanged.connect(
            lambda v: self.cpu_val.setText(f"{v} core{'s' if v!=1 else ''}")
        )
        cpu_row.addWidget(cpu_lbl)
        cpu_row.addWidget(self.cpu_slider, 1)
        cpu_row.addWidget(self.cpu_val)
        lay.addLayout(cpu_row)

        # Disk
        disk_row = QHBoxLayout()
        disk_lbl = BodyLabel("Disk")
        disk_lbl.setFixedWidth(50)
        self.disk_spin = SpinBox()
        self.disk_spin.setRange(10, 500)
        self.disk_spin.setValue(30)
        self.disk_spin.setSuffix(" GB")
        disk_row.addWidget(disk_lbl)
        disk_row.addWidget(self.disk_spin, 1)
        lay.addLayout(disk_row)

        # Recommendation output
        self.rec_lbl = CaptionLabel("")
        lay.addWidget(self.rec_lbl)

        return card

    def _action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        self.btn_rec = PushButton(FIF.ROBOT, "AI Recommend")
        self.btn_rec.clicked.connect(self._apply_rec)

        self.btn_install = PrimaryPushButton(FIF.SEND, "One-Click Install")
        self.btn_install.clicked.connect(self._install)

        row.addWidget(self.btn_rec)
        row.addStretch()
        row.addWidget(self.btn_install)
        return row

    def _progress_section(self) -> QVBoxLayout:
        lay = QVBoxLayout()
        lay.setSpacing(4)
        
        status_row = QHBoxLayout()
        self.status_lbl = CaptionLabel("Ready")
        
        self.btn_pause = PushButton(FIF.PAUSE, "")
        self.btn_pause.setFixedSize(28, 28)
        self.btn_pause.hide()
        self.btn_pause.clicked.connect(self._toggle_pause)
        
        status_row.addWidget(self.status_lbl)
        status_row.addStretch()
        status_row.addWidget(self.btn_pause)
        
        self.prog_bar   = ProgressBar()
        self.prog_bar.setValue(0)
        self.prog_bar.setFixedHeight(8)
        
        lay.addLayout(status_row)
        lay.addWidget(self.prog_bar)
        return lay

    def _log_card(self) -> CardWidget:
        card = CardWidget()
        lay  = QVBoxLayout(card)
        lay.setContentsMargins(12, 10, 12, 10)
        lay.setSpacing(4)
        lbl = CaptionLabel("INSTALLATION LOG")
        lbl.setTextColor(QColor("#8B949E"), QColor("#666"))
        lay.addWidget(lbl)
        self.log_box = TextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setStyleSheet(
            "TextEdit { background: #010409; color: #58A6FF;"
            " font-family: Consolas, monospace; font-size: 12px; border: none; }"
        )
        lay.addWidget(self.log_box, 1)
        return card

    # ── Logic ──────────────────────────────────────────────────────────────────

    def _apply_rec(self):
        idx = self.os_combo.currentIndex()
        if idx < 0:
            return
        os_id = self._tmgr.list_templates()[idx]["os_id"]
        ram, cpu = _recommend(os_id, _RAM_MB, _CORES)
        self.ram_slider.setValue(ram)
        self.cpu_slider.setValue(cpu)
        self.rec_lbl.setText(
            f"✅  Recommended: RAM {ram} MB · CPU {cpu} core(s)"
            f"   (Host: {_RAM_MB} MB / {_CORES} cores)"
        )

    def _install(self):
        idx = self.os_combo.currentIndex()
        if idx < 0:
            InfoBar.warning("No OS", "Please select an OS.",
                            duration=3000, position=InfoBarPosition.TOP_RIGHT,
                            parent=self.window())
            return
        os_id = self._tmgr.list_templates()[idx]["os_id"]

        self.btn_install.setEnabled(False)
        self.btn_rec.setEnabled(False)
        self.log_box.clear()
        self.prog_bar.setValue(0)
        self.status_lbl.setText("Initializing…")
        self.btn_pause.setIcon(FIF.PAUSE)
        self.btn_pause.show()

        self._worker = InstallWorker(
            os_id=os_id,
            ram_mb=self.ram_slider.value(),
            cpu_count=self.cpu_slider.value(),
            disk_gb=self.disk_spin.value(),
        )
        self._worker.progress_update.connect(self._progress)
        self._worker.log_update.connect(self._log)
        self._worker.finished.connect(self._done)
        self._worker.error.connect(self._err)
        self._worker.start()

    def _progress(self, d: dict):
        self.prog_bar.setValue(int(d.get("percentage", 0)))
        dl = d.get("downloaded_bytes")
        if dl:
            spd = d.get("speed_mb_s", 0)
            eta = d.get("eta_seconds", "?")
            self.status_lbl.setText(
                f"{dl/1024/1024:.1f} MB  ·  {spd} MB/s  ·  ETA {eta}s"
            )
        else:
            self.status_lbl.setText(d.get("status", "Working…"))

    def _toggle_pause(self):
        if self._worker and self._worker.isRunning():
            if not self._worker.is_paused:
                self._worker.is_paused = True
                self.btn_pause.setIcon(FIF.PLAY)
                self.status_lbl.setText("Paused")
            else:
                self._worker.is_paused = False
                self.btn_pause.setIcon(FIF.PAUSE)
                self.status_lbl.setText("Resuming...")

    def _log(self, text: str):
        self.log_box.append(text)

    def _done(self, r: dict):
        self._reset()
        if r.get("success"):
            self.prog_bar.setValue(100)
            self.status_lbl.setText("✅  Complete!")
            InfoBar.success("VM Created",
                            f"'{r.get('vm_name','')}' launched!",
                            duration=5000, position=InfoBarPosition.TOP_RIGHT,
                            parent=self.window())
        else:
            self.status_lbl.setText("❌  Failed.")
            InfoBar.error("Installation Failed", r.get("message", "")[:100],
                          duration=6000, position=InfoBarPosition.TOP_RIGHT,
                          parent=self.window())

    def _err(self, e: str):
        self._reset()
        self.status_lbl.setText("❌  Error.")
        self.log_box.append(f"ERROR: {e}")
        InfoBar.error("Error", e[:100], duration=6000,
                      position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _reset(self):
        self.btn_install.setEnabled(True)
        self.btn_rec.setEnabled(True)
        self.btn_pause.hide()
