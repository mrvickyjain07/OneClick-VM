"""
settings_page.py
================
Phase 7: Application settings page.

Persists to: cache/settings.json
Settings:
- Default VM folder
- ISO storage path  
- Default RAM / CPU
- Log level (Info / Debug)
"""
import sys
import json
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QSpinBox, QComboBox, QFileDialog, QMessageBox,
    QGroupBox, QFormLayout, QSlider
)
from PyQt5.QtCore import Qt

from backend import config


SETTINGS_FILE = config.CACHE_DIR / "settings.json"

DEFAULT_SETTINGS = {
    "vm_folder":       str(config.VM_DATA_DIR),
    "iso_folder":      str(config.ISO_CACHE_DIR),
    "default_ram_mb":  2048,
    "default_cpu":     2,
    "default_disk_gb": 30,
    "log_level":       "Info",
}


def load_settings() -> dict:
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r") as f:
                return {**DEFAULT_SETTINGS, **json.load(f)}
        except Exception:
            pass
    return dict(DEFAULT_SETTINGS)


def save_settings(settings: dict):
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w") as f:
        json.dump(settings, f, indent=4)


class SettingsPage(QWidget):
    """Application settings page with JSON persistence."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._settings = load_settings()
        self._build_ui()
        self._populate()

    # ──────────────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(20)

        title    = QLabel("Settings")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Configure default paths and resource allocation")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        # ── Paths group ───────────────────────────────────────────────────
        root.addWidget(self._build_paths_group())

        # ── Defaults group ────────────────────────────────────────────────
        root.addWidget(self._build_defaults_group())

        # ── Logging group ─────────────────────────────────────────────────
        root.addWidget(self._build_logging_group())

        root.addStretch()

        # Save button
        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_save = QPushButton("💾  Save Settings")
        self.btn_save.setObjectName("PrimaryButton")
        self.btn_save.setFixedWidth(160)
        self.btn_save.clicked.connect(self._save)
        self.btn_reset = QPushButton("Reset to Defaults")
        self.btn_reset.clicked.connect(self._reset)
        btn_row.addWidget(self.btn_reset)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.btn_save)
        root.addLayout(btn_row)

    def _make_group(self, title: str) -> tuple[QGroupBox, QFormLayout]:
        box = QGroupBox(title)
        box.setStyleSheet(
            "QGroupBox { font-size: 13px; font-weight: 600; color: #8B949E; "
            "border: 1px solid #30363D; border-radius: 8px; margin-top: 8px; padding: 12px; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 4px; }"
        )
        form = QFormLayout(box)
        form.setSpacing(12)
        form.setLabelAlignment(Qt.AlignRight)
        return box, form

    def _browse_btn(self, line_edit: QLineEdit) -> QPushButton:
        btn = QPushButton("Browse…")
        btn.setFixedWidth(80)
        btn.clicked.connect(lambda: self._pick_folder(line_edit))
        return btn

    def _path_row(self, line_edit: QLineEdit) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(6)
        row.addWidget(line_edit)
        row.addWidget(self._browse_btn(line_edit))
        return row

    def _build_paths_group(self) -> QGroupBox:
        box, form = self._make_group("Paths")

        self.vm_folder_edit  = QLineEdit()
        self.vm_folder_edit.setPlaceholderText("Default VM storage folder")
        self.iso_folder_edit = QLineEdit()
        self.iso_folder_edit.setPlaceholderText("ISO cache directory")

        form.addRow("VM Folder:",  self._path_row(self.vm_folder_edit))
        form.addRow("ISO Folder:", self._path_row(self.iso_folder_edit))
        return box

    def _build_defaults_group(self) -> QGroupBox:
        box, form = self._make_group("Default Resources")

        self.ram_spin = QSpinBox()
        self.ram_spin.setRange(512, 65536)
        self.ram_spin.setSingleStep(256)
        self.ram_spin.setSuffix(" MB")
        self.ram_spin.setFixedHeight(32)

        self.cpu_spin = QSpinBox()
        self.cpu_spin.setRange(1, 64)
        self.cpu_spin.setSuffix(" core(s)")
        self.cpu_spin.setFixedHeight(32)

        self.disk_spin = QSpinBox()
        self.disk_spin.setRange(5, 1000)
        self.disk_spin.setSuffix(" GB")
        self.disk_spin.setFixedHeight(32)

        form.addRow("Default RAM:",  self.ram_spin)
        form.addRow("Default CPU:",  self.cpu_spin)
        form.addRow("Default Disk:", self.disk_spin)
        return box

    def _build_logging_group(self) -> QGroupBox:
        box, form = self._make_group("Logging")
        self.log_combo = QComboBox()
        self.log_combo.addItems(["Info", "Debug", "Warning", "Error"])
        self.log_combo.setFixedHeight(32)
        form.addRow("Log Level:", self.log_combo)

        log_path = QLineEdit(str(config.LOG_DIR))
        log_path.setReadOnly(True)
        form.addRow("Log Directory:", log_path)
        return box

    # ──────────────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────────────

    def _populate(self):
        s = self._settings
        self.vm_folder_edit.setText(s.get("vm_folder", ""))
        self.iso_folder_edit.setText(s.get("iso_folder", ""))
        self.ram_spin.setValue(s.get("default_ram_mb", 2048))
        self.cpu_spin.setValue(s.get("default_cpu", 2))
        self.disk_spin.setValue(s.get("default_disk_gb", 30))
        idx = self.log_combo.findText(s.get("log_level", "Info"))
        if idx >= 0:
            self.log_combo.setCurrentIndex(idx)

    def _pick_folder(self, edit: QLineEdit):
        folder = QFileDialog.getExistingDirectory(self, "Select Folder", edit.text())
        if folder:
            edit.setText(folder)

    def _save(self):
        self._settings.update({
            "vm_folder":       self.vm_folder_edit.text(),
            "iso_folder":      self.iso_folder_edit.text(),
            "default_ram_mb":  self.ram_spin.value(),
            "default_cpu":     self.cpu_spin.value(),
            "default_disk_gb": self.disk_spin.value(),
            "log_level":       self.log_combo.currentText(),
        })
        try:
            save_settings(self._settings)
            QMessageBox.information(self, "Saved", "Settings saved successfully.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", f"Failed to save settings:\n{exc}")

    def _reset(self):
        reply = QMessageBox.question(
            self, "Reset Settings",
            "Reset all settings to defaults?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._settings = dict(DEFAULT_SETTINGS)
            self._populate()
