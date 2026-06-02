"""
create_vm_page.py
=================
Phase 1 + Phase 3: VM creation page with resource configuration panel.

Features:
- OS selection (from templates)
- RAM slider (512 MB → system max)
- CPU slider (1 → system cores)
- Disk size input
- AI recommendation button (Phase 4 logic, rule-based)
- Progress bar + log console
- Threading via InstallWorker
"""
import sys
import os
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QSlider, QSpinBox, QProgressBar, QTextEdit,
    QFrame, QSizePolicy, QGroupBox, QMessageBox
)
from PyQt5.QtCore import Qt, QTimer

from backend.template_manager  import TemplateManager
from frontend.workers.install_worker import InstallWorker

# ── System detection ──────────────────────────────────────────────────────────
try:
    import psutil
    _TOTAL_RAM_MB  = int(psutil.virtual_memory().total / 1024 / 1024)
    _CPU_CORES     = psutil.cpu_count(logical=False) or 2
except ImportError:
    _TOTAL_RAM_MB  = 8192
    _CPU_CORES     = 4


def _recommend(os_id: str, total_ram: int, cores: int) -> tuple[int, int]:
    """
    Rule-based resource recommendation (Phase 4 logic).
    Returns (ram_mb, cpu_count).
    """
    os_lower = os_id.lower()
    if "fedora" in os_lower:
        ram  = max(2048, int(total_ram * 0.30))
        cpus = max(2, int(cores * 0.60))
    elif "windows" in os_lower:
        ram  = max(4096, int(total_ram * 0.40))
        cpus = max(2, int(cores * 0.50))
    elif "kali" in os_lower or "arch" in os_lower:
        ram  = max(2048, int(total_ram * 0.25))
        cpus = max(2, int(cores * 0.50))
    else:  # ubuntu, debian, etc.
        ram  = max(2048, int(total_ram * 0.25))
        cpus = max(2, int(cores * 0.50))

    # Cap to available
    ram  = min(ram,  total_ram)
    cpus = min(cpus, cores)
    return ram, cpus


class CreateVMPage(QWidget):
    """VM creation form with resource configuration."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.template_manager = TemplateManager()
        self.template_manager.load_templates()
        self._worker: InstallWorker | None = None
        self._build_ui()

    # ──────────────────────────────────────────────────────────────────────────
    # UI Construction
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)

        # ── Page Header ───────────────────────────────────────────────────
        title = QLabel("Create VM")
        title.setObjectName("PageTitle")
        subtitle = QLabel("One-click install — configure resources before launch")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        # ── Two-column layout (config | log) ──────────────────────────────
        columns = QHBoxLayout()
        columns.setSpacing(20)

        # Left: config panel
        left = QVBoxLayout()
        left.setSpacing(16)
        left.addLayout(self._build_os_selector())
        left.addWidget(self._build_resource_panel())
        left.addLayout(self._build_action_row())
        left.addStretch()
        columns.addLayout(left, stretch=1)

        # Right: progress + log
        right = QVBoxLayout()
        right.setSpacing(8)
        right.addLayout(self._build_progress_section())
        right.addWidget(self._build_log_console(), stretch=1)
        columns.addLayout(right, stretch=1)

        root.addLayout(columns, stretch=1)

    def _build_os_selector(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(6)
        lbl = QLabel("Operating System")
        lbl.setObjectName("SectionLabel")
        self.os_combo = QComboBox()
        self.os_combo.setFixedHeight(36)
        templates = self.template_manager.list_templates()
        for t in templates:
            self.os_combo.addItem(f"  {t['os_name']}  ({t['version']})", t["os_id"])
        self.os_combo.currentIndexChanged.connect(self._on_os_changed)
        layout.addWidget(lbl)
        layout.addWidget(self.os_combo)
        return layout

    def _build_resource_panel(self) -> QGroupBox:
        box = QGroupBox("Resource Configuration")
        box.setStyleSheet(
            "QGroupBox { font-size: 13px; font-weight: 600; color: #8B949E; "
            "border: 1px solid #30363D; border-radius: 8px; margin-top: 8px; padding: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        layout = QVBoxLayout(box)
        layout.setSpacing(14)

        # RAM slider
        ram_row = QHBoxLayout()
        ram_label = QLabel("RAM")
        ram_label.setFixedWidth(50)
        self.ram_slider = QSlider(Qt.Horizontal)
        self.ram_slider.setMinimum(512)
        self.ram_slider.setMaximum(_TOTAL_RAM_MB)
        self.ram_slider.setSingleStep(256)
        self.ram_slider.setValue(2048)
        self.ram_slider.valueChanged.connect(self._update_ram_label)
        self.ram_value_label = QLabel("2048 MB")
        self.ram_value_label.setFixedWidth(80)
        self.ram_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        ram_row.addWidget(ram_label)
        ram_row.addWidget(self.ram_slider, stretch=1)
        ram_row.addWidget(self.ram_value_label)

        # CPU slider
        cpu_row = QHBoxLayout()
        cpu_label = QLabel("CPU")
        cpu_label.setFixedWidth(50)
        self.cpu_slider = QSlider(Qt.Horizontal)
        self.cpu_slider.setMinimum(1)
        self.cpu_slider.setMaximum(max(_CPU_CORES, 1))
        self.cpu_slider.setValue(min(2, _CPU_CORES))
        self.cpu_slider.valueChanged.connect(self._update_cpu_label)
        self.cpu_value_label = QLabel(f"{self.cpu_slider.value()} core(s)")
        self.cpu_value_label.setFixedWidth(80)
        self.cpu_value_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        cpu_row.addWidget(cpu_label)
        cpu_row.addWidget(self.cpu_slider, stretch=1)
        cpu_row.addWidget(self.cpu_value_label)

        # Disk input
        disk_row = QHBoxLayout()
        disk_lbl = QLabel("Disk")
        disk_lbl.setFixedWidth(50)
        self.disk_spin = QSpinBox()
        self.disk_spin.setMinimum(10)
        self.disk_spin.setMaximum(500)
        self.disk_spin.setValue(30)
        self.disk_spin.setSuffix(" GB")
        self.disk_spin.setFixedHeight(32)
        disk_row.addWidget(disk_lbl)
        disk_row.addWidget(self.disk_spin, stretch=1)

        # Recommendation labels
        self.rec_label = QLabel("")
        self.rec_label.setObjectName("VMDetail")
        self.rec_label.setWordWrap(True)

        layout.addLayout(ram_row)
        layout.addLayout(cpu_row)
        layout.addLayout(disk_row)
        layout.addWidget(self.rec_label)

        return box

    def _build_action_row(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(10)

        self.btn_recommend = QPushButton("🤖  AI Recommend")
        self.btn_recommend.setToolTip(
            "Auto-fill sliders with AI-recommended settings based on your host hardware"
        )
        self.btn_recommend.clicked.connect(self._apply_recommendation)

        self.btn_install = QPushButton("🚀  One-Click Install")
        self.btn_install.setObjectName("PrimaryButton")
        self.btn_install.clicked.connect(self._start_install)

        row.addWidget(self.btn_recommend)
        row.addStretch()
        row.addWidget(self.btn_install)
        return row

    def _build_progress_section(self) -> QVBoxLayout:
        layout = QVBoxLayout()
        layout.setSpacing(6)
        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("VMDetail")
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(10)
        layout.addWidget(self.status_label)
        layout.addWidget(self.progress_bar)
        return layout

    def _build_log_console(self) -> QTextEdit:
        self.log_console = QTextEdit()
        self.log_console.setObjectName("LogConsole")
        self.log_console.setReadOnly(True)
        self.log_console.setMinimumHeight(200)
        return self.log_console

    # ──────────────────────────────────────────────────────────────────────────
    # Callbacks
    # ──────────────────────────────────────────────────────────────────────────

    def _on_os_changed(self):
        self.rec_label.setText("")

    def _update_ram_label(self, value: int):
        if value >= 1024:
            self.ram_value_label.setText(f"{value / 1024:.1f} GB")
        else:
            self.ram_value_label.setText(f"{value} MB")

    def _update_cpu_label(self, value: int):
        self.cpu_value_label.setText(f"{value} core{'s' if value != 1 else ''}")

    def _apply_recommendation(self):
        os_id = self.os_combo.currentData()
        if not os_id:
            return
        ram, cpus = _recommend(os_id, _TOTAL_RAM_MB, _CPU_CORES)
        self.ram_slider.setValue(ram)
        self.cpu_slider.setValue(cpus)
        self.rec_label.setText(
            f"✅  Recommended:  RAM {ram} MB  ·  CPU {cpus} core(s)  "
            f"(Host: {_TOTAL_RAM_MB} MB RAM, {_CPU_CORES} cores)"
        )

    def _start_install(self):
        os_id = self.os_combo.currentData()
        if not os_id:
            QMessageBox.warning(self, "No OS Selected", "Please select an OS first.")
            return

        self.btn_install.setEnabled(False)
        self.btn_recommend.setEnabled(False)
        self.log_console.clear()
        self.progress_bar.setValue(0)
        self.status_label.setText("Initializing…")

        self._worker = InstallWorker(
            os_id=os_id,
            ram_mb=self.ram_slider.value(),
            cpu_count=self.cpu_slider.value(),
            disk_gb=self.disk_spin.value(),
        )
        self._worker.progress_update.connect(self._on_progress)
        self._worker.log_update.connect(self._append_log)
        self._worker.finished.connect(self._on_install_finished)
        self._worker.error.connect(self._on_install_error)
        self._worker.start()

    def _on_progress(self, data: dict):
        self.progress_bar.setValue(int(data.get("percentage", 0)))
        downloaded = data.get("downloaded_bytes")
        if downloaded is not None:
            speed = data.get("speed_mb_s", 0)
            eta   = data.get("eta_seconds", "?")
            status = (
                f"Downloaded: {downloaded / 1024 / 1024:.1f} MB  |  "
                f"Speed: {speed} MB/s  |  ETA: {eta}s"
            )
        else:
            status = data.get("status", "Working…")
        self.status_label.setText(status)

    def _append_log(self, text: str):
        self.log_console.append(text)

    def _on_install_finished(self, result: dict):
        self._reset_controls()
        if result.get("success"):
            self.status_label.setText("✅  Installation complete!")
            self.progress_bar.setValue(100)
            QMessageBox.information(
                self, "Success",
                f"VM '{result.get('vm_name', '')}' launched successfully!"
            )
        else:
            self.status_label.setText("❌  Installation failed.")
            QMessageBox.critical(self, "Failure", result.get("message", "Unknown error"))

    def _on_install_error(self, error_msg: str):
        self._reset_controls()
        self.status_label.setText("❌  Error occurred.")
        self.log_console.append(f"CRITICAL ERROR: {error_msg}")
        QMessageBox.critical(self, "Error", error_msg)

    def _reset_controls(self):
        self.btn_install.setEnabled(True)
        self.btn_recommend.setEnabled(True)
