"""
ui/dialogs/create_vm_from_iso_dialog.py
"Create Virtual Machine from ISO" — full wizard-style modal.

Sections:
  1. Basic Info  — VM name + auto-detected OS type
  2. AI Config   — RAM / CPU / Disk sliders with host-aware recommendation
  3. Boot Source — ISO path (readonly)
  4. Summary     — live recap of settings
  5. Progress    — animated bar + stage label during creation

Emits:
  vm_created(vm_name: str)  — after the worker finishes successfully
"""
import sys, os, uuid
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy,
    QSlider, QSpinBox, QFrame, QScrollArea, QLabel
)

from qfluentwidgets import (
    TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel,
    CardWidget, PrimaryPushButton, PushButton, LineEdit, ComboBox,
    ProgressBar, InfoBar, InfoBarPosition, FluentIcon as FIF,
    ScrollArea as FScrollArea
)

from ui.workers import ISOVMCreateWorker

try:
    from backend.ai_recommendation import recommend_config, get_system_specs
    _HAS_AI = True
except ImportError:
    _HAS_AI = False


# ── OS type mapping ───────────────────────────────────────────────────────────

_OS_TYPES = [
    ("Ubuntu 22.04 LTS",   "ubuntu_22_04",  "Ubuntu_64"),
    ("Ubuntu 20.04 LTS",   "ubuntu_20_04",  "Ubuntu_64"),
    ("Fedora (Latest)",    "fedora_40",     "Fedora_64"),
    ("Debian 12",          "debian_12",     "Debian_64"),
    ("Arch Linux",         "arch",          "ArchLinux_64"),
    ("Kali Linux",         "kali",          "Debian_64"),
    ("Windows 11",         "windows_11",    "Windows11_64"),
    ("Windows 10",         "windows_10",    "Windows10_64"),
    ("Generic Linux 64",   "generic_linux", "Linux_64"),
    ("Custom / Other",     "custom",        "Other_64"),
]

def _detect_os_type(iso_name: str) -> tuple:
    n = iso_name.lower()
    for display, os_id, type_id in _OS_TYPES:
        if any(kw in n for kw in os_id.split("_")[:1]):
            return display, os_id, type_id
    return _OS_TYPES[-1]  # Custom / Other


# ── Slider row helper ─────────────────────────────────────────────────────────

class _SliderRow(QWidget):
    def __init__(self, label, min_v, max_v, step, unit, default, parent=None):
        super().__init__(parent)
        self.unit = unit
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)

        lbl = CaptionLabel(label)
        lbl.setFixedWidth(70)
        lbl.setStyleSheet("color: rgba(255,255,255,0.6); border: none; background: transparent;")

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(min_v, max_v)
        self.slider.setSingleStep(step)
        self.slider.setValue(default)
        self.slider.setStyleSheet("""
            QSlider::groove:horizontal { height:4px; background: rgba(255,255,255,0.1); border-radius:2px; }
            QSlider::handle:horizontal { width:14px; height:14px; background:#60a5fa; border-radius:7px; margin:-5px 0; }
            QSlider::sub-page:horizontal { background:#3b82f6; border-radius:2px; }
        """)

        self.val_lbl = BodyLabel(f"{default} {unit}")
        self.val_lbl.setFixedWidth(80)
        self.val_lbl.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.val_lbl.setStyleSheet("color:#f1f5f9; background:transparent; border:none;")

        self.slider.valueChanged.connect(
            lambda v: self.val_lbl.setText(f"{v} {unit}")
        )

        lay.addWidget(lbl)
        lay.addWidget(self.slider, stretch=1)
        lay.addWidget(self.val_lbl)

    @property
    def value(self) -> int:
        return self.slider.value()


# ── Dialog ────────────────────────────────────────────────────────────────────

class CreateVMFromISODialog(QDialog):
    vm_created = pyqtSignal(str)   # vm_name

    def __init__(self, iso_record, vm_service, machines_db, parent=None):
        super().__init__(parent)
        self.iso_record  = iso_record
        self.vm_service  = vm_service
        self.machines_db = machines_db
        self._worker     = None

        # Auto-detect OS from ISO name
        disp, self._os_id, self._type_id = _detect_os_type(iso_record.name)

        # Auto-generate VM name
        self._default_vm_name = f"{iso_record.name[:18]}_{uuid.uuid4().hex[:6]}"

        self.setWindowTitle("Create Virtual Machine")
        self.setModal(True)
        self.setMinimumSize(560, 680)
        self.setMaximumWidth(660)
        self.setStyleSheet("""
            QDialog { background: #13131f; }
            QLabel  { background: transparent; border: none; }
        """)

        # Outer scroll so it works on small screens
        scroll = FScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("background: transparent; border: none;")
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        scroll.setWidget(container)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

        root = QVBoxLayout(container)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(20)

        # ── Header ──
        hdr = QHBoxLayout()
        hdr.setSpacing(14)
        iso_icon = QLabel("💿")
        iso_icon.setStyleSheet("font-size: 36px;")
        iso_icon.setFixedSize(52, 52)
        iso_icon.setAlignment(Qt.AlignCenter)
        hdr_text = QVBoxLayout()
        hdr_text.setSpacing(2)
        hdr_text.addWidget(TitleLabel("Create Virtual Machine"))
        sub = CaptionLabel(f"Using: {iso_record.name}{iso_record.file_type}")
        sub.setStyleSheet("color: rgba(255,255,255,0.4);")
        hdr_text.addWidget(sub)
        hdr.addWidget(iso_icon)
        hdr.addLayout(hdr_text)
        hdr.addStretch()
        root.addLayout(hdr)

        root.addWidget(self._hr())

        # ── SECTION 1: Basic Info ──
        root.addWidget(self._section_label("⚙  Basic Configuration"))

        vm_row = QHBoxLayout()
        vm_row.setSpacing(10)
        name_lbl = CaptionLabel("VM Name")
        name_lbl.setFixedWidth(70)
        name_lbl.setStyleSheet("color: rgba(255,255,255,0.6);")
        self._name_edit = LineEdit()
        self._name_edit.setText(self._default_vm_name)
        self._name_edit.setPlaceholderText("Virtual machine name…")
        self._name_edit.textChanged.connect(self._update_summary)
        vm_row.addWidget(name_lbl)
        vm_row.addWidget(self._name_edit, stretch=1)
        root.addLayout(vm_row)

        os_row = QHBoxLayout()
        os_row.setSpacing(10)
        os_lbl = CaptionLabel("OS Type")
        os_lbl.setFixedWidth(70)
        os_lbl.setStyleSheet("color: rgba(255,255,255,0.6);")
        self._os_combo = ComboBox()
        for display, os_id, type_id in _OS_TYPES:
            self._os_combo.addItem(display)
        # Pre-select detected OS
        detected_idx = next(
            (i for i, (d, _, _) in enumerate(_OS_TYPES) if d == disp), 0
        )
        self._os_combo.setCurrentIndex(detected_idx)
        self._os_combo.currentIndexChanged.connect(self._on_os_changed)
        os_row.addWidget(os_lbl)
        os_row.addWidget(self._os_combo, stretch=1)
        root.addLayout(os_row)

        root.addWidget(self._hr())

        # ── SECTION 2: AI Resource Config ──
        root.addWidget(self._section_label("🤖  Resources"))

        # Get AI recommendation
        rec_ram, rec_cpu, rec_disk = self._get_ai_defaults()

        self._ram_slider  = _SliderRow("RAM",  512,  32768, 256, "MB", rec_ram)
        self._cpu_slider  = _SliderRow("CPU",  1,    16,    1,   "cores", rec_cpu)
        self._disk_slider = _SliderRow("Disk", 10,   500,   5,   "GB", rec_disk)

        for slider in (self._ram_slider, self._cpu_slider, self._disk_slider):
            root.addWidget(slider)
            slider.slider.valueChanged.connect(self._update_summary)

        if _HAS_AI:
            ai_note = CaptionLabel("✨ Resources auto-tuned based on host capacity and OS profile.")
            ai_note.setStyleSheet("color: #60a5fa; font-size: 10px;")
            root.addWidget(ai_note)

        root.addWidget(self._hr())

        # ── SECTION 3: Boot Source ──
        root.addWidget(self._section_label("💿  Boot Source (ISO)"))

        iso_path_card = CardWidget()
        iso_path_card.setBorderRadius(10)
        iso_path_card.setStyleSheet("CardWidget { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.08); }")
        ip_lay = QVBoxLayout(iso_path_card)
        ip_lay.setContentsMargins(14, 10, 14, 10)
        ip_lay.setSpacing(4)
        ip_name = StrongBodyLabel(f"{iso_record.name}{iso_record.file_type}")
        ip_name.setStyleSheet("color: #f1f5f9; font-size: 12px;")
        ip_path = CaptionLabel(iso_record.file_path)
        ip_path.setStyleSheet("color: rgba(255,255,255,0.35); font-size: 10px;")
        ip_path.setWordWrap(True)
        boot_note = CaptionLabel("🔃 Boot order: DVD (ISO) → Disk — OS installer will start automatically.")
        boot_note.setStyleSheet("color: #a78bfa; font-size: 10px;")
        ip_lay.addWidget(ip_name)
        ip_lay.addWidget(ip_path)
        ip_lay.addWidget(boot_note)
        root.addWidget(iso_path_card)

        root.addWidget(self._hr())

        # ── SECTION 4: Summary ──
        root.addWidget(self._section_label("📋  Summary"))

        self._summary_card = CardWidget()
        self._summary_card.setBorderRadius(10)
        self._summary_card.setStyleSheet("CardWidget { background: rgba(96,165,250,0.06); border: 1px solid rgba(96,165,250,0.18); }")
        self._sum_lay = QVBoxLayout(self._summary_card)
        self._sum_lay.setContentsMargins(16, 12, 16, 12)
        self._sum_lay.setSpacing(5)
        self._sum_rows: list[QLabel] = []
        for _ in range(5):
            lbl = CaptionLabel("")
            lbl.setStyleSheet("color: rgba(255,255,255,0.65); font-size: 11px;")
            self._sum_rows.append(lbl)
            self._sum_lay.addWidget(lbl)
        root.addWidget(self._summary_card)
        self._update_summary()

        root.addWidget(self._hr())

        # ── Progress area (hidden until worker starts) ──
        self._prog_card = CardWidget()
        self._prog_card.setBorderRadius(10)
        prog_lay = QVBoxLayout(self._prog_card)
        prog_lay.setContentsMargins(14, 12, 14, 12)
        prog_lay.setSpacing(6)
        self._stage_lbl = BodyLabel("Starting…")
        self._stage_lbl.setStyleSheet("color: #60a5fa;")
        self._prog_bar = ProgressBar()
        self._prog_bar.setRange(0, 100)
        prog_lay.addWidget(self._stage_lbl)
        prog_lay.addWidget(self._prog_bar)
        self._prog_card.hide()
        root.addWidget(self._prog_card)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self._cancel_btn = PushButton(FIF.CLOSE, "Cancel")
        self._cancel_btn.setFixedHeight(40)
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._create_btn = PrimaryPushButton(FIF.PLAY, "Create & Start VM")
        self._create_btn.setFixedHeight(40)
        self._create_btn.setFixedWidth(200)
        self._create_btn.clicked.connect(self._on_create)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._create_btn)
        root.addLayout(btn_row)

        root.addStretch()

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _hr(self) -> QFrame:
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setStyleSheet("color: rgba(255,255,255,0.08);")
        return line

    def _section_label(self, text: str) -> BodyLabel:
        lbl = BodyLabel(text)
        lbl.setStyleSheet("font-size: 12px; font-weight: 700; color: rgba(255,255,255,0.7);")
        return lbl

    def _get_ai_defaults(self) -> tuple:
        if _HAS_AI:
            try:
                specs = get_system_specs()
                cfg   = recommend_config(self._os_id, specs)
                return cfg.get("ram_mb", 2048), cfg.get("cpu", 2), cfg.get("disk_gb", 25)
            except Exception:
                pass
        return 2048, 2, 25

    def _on_os_changed(self, idx: int):
        _, self._os_id, self._type_id = _OS_TYPES[idx]
        # Re-run AI recommendation for new OS
        r, c, d = self._get_ai_defaults()
        self._ram_slider.slider.setValue(r)
        self._cpu_slider.slider.setValue(c)
        self._disk_slider.slider.setValue(d)
        self._update_summary()

    def _update_summary(self):
        vm_name = self._name_edit.text().strip() or self._default_vm_name
        os_type = self._os_combo.currentText()
        ram     = self._ram_slider.value
        cpu     = self._cpu_slider.value
        disk    = self._disk_slider.value
        iso     = f"{self.iso_record.name}{self.iso_record.file_type}"
        lines   = [
            f"  📛  VM Name:   {vm_name}",
            f"  🖥  OS Type:   {os_type}",
            f"  💾  RAM:       {ram} MB",
            f"  ⚡  CPU:       {cpu} core(s)",
            f"  🗄  Disk:      {disk} GB",
            f"  💿  ISO:       {iso}",
        ]
        for i, row in enumerate(self._sum_rows):
            row.setText(lines[i] if i < len(lines) else "")

    # ── Main actions ──────────────────────────────────────────────────────────

    def _on_create(self):
        vm_name = self._name_edit.text().strip() or self._default_vm_name
        if not vm_name:
            InfoBar.warning("Missing VM name", "Please enter a name for the VM.",
                            duration=3000, position=InfoBarPosition.TOP, parent=self)
            return

        self._create_btn.setEnabled(False)
        self._cancel_btn.setEnabled(False)
        self._prog_card.show()
        self._prog_bar.setValue(0)

        _, os_id, type_id = _OS_TYPES[self._os_combo.currentIndex()]

        self._worker = ISOVMCreateWorker(
            vm_service        = self.vm_service,
            iso_path          = self.iso_record.file_path,
            os_id             = os_id,
            os_name           = self._os_combo.currentText(),
            os_type_id        = type_id,
            vm_name           = vm_name,
            ram_mb            = self._ram_slider.value,
            cpu_count         = self._cpu_slider.value,
            disk_gb           = self._disk_slider.value,
            auto_launch       = True,
            parent            = self,
        )
        self._worker.stage.connect(self._stage_lbl.setText)
        self._worker.progress.connect(self._prog_bar.setValue)
        self._worker.finished.connect(self._on_worker_done)
        self._worker.error.connect(self._on_worker_error)
        self._worker.start()

    def _on_worker_done(self, rec):
        self._prog_bar.setValue(100)
        self._prog_card.hide()
        self.vm_created.emit(rec.vm_name)
        self.accept()

    def _on_worker_error(self, msg: str):
        # Reset progress UI so the user isn't left staring at a stuck spinner
        self._prog_card.hide()
        self._prog_bar.setValue(0)
        self._stage_lbl.setText("")
        self._create_btn.setEnabled(True)
        self._cancel_btn.setEnabled(True)
        InfoBar.error(
            "VM Creation Failed", msg[:320],
            duration=0, position=InfoBarPosition.TOP, parent=self
        )

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.terminate()
            self._worker.wait(2000)
        self.reject()
