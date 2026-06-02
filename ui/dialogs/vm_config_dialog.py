"""
ui/dialogs/vm_config_dialog.py
AI-powered VM configuration modal — Configure and Deploy in one shot.

Features:
  • AI resource recommendation using backend.ai_recommendation
  • Live system spec detection via psutil
  • Interactive RAM / CPU / Disk sliders with dynamic confidence badge
  • Multi-version OS selector (QComboBox) — Section 2 requirement
  • One-click QuickDeployWorker integration
  • Inline progress bar + stage text during deployment
  • Fixed close-button alignment (top-right, no overlap, hover feedback)
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtGui     import QColor
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget,
    QSizePolicy, QGraphicsDropShadowEffect, QLabel, QSlider,
    QCheckBox, QProgressBar, QPushButton
)
from qfluentwidgets import (
    CardWidget, TitleLabel, SubtitleLabel, StrongBodyLabel, BodyLabel,
    CaptionLabel, PrimaryPushButton, PushButton, FluentIcon as FIF,
    InfoBar, InfoBarPosition, ComboBox
)

from backend.ai_recommendation import get_system_specs, recommend_config
from ui.workers import QuickDeployWorker


# ── Version catalog  ─────────────────────────────────────────────────────────
# Maps os_id → list of (label, iso_url, iso_filename, version_str)
# Add new OSes/versions here; catalog is used to populate the QComboBox.

_VERSION_CATALOG: dict[str, list[dict]] = {
    "ubuntu_24_04": [
        {
            "label":        "24.04.4 LTS (Noble) — Latest",
            "version":      "24.04.4 LTS",
            "iso_url":      "https://releases.ubuntu.com/24.04/ubuntu-24.04.4-desktop-amd64.iso",
            "iso_filename": "ubuntu-24.04.4-desktop-amd64.iso",
        },
        {
            "label":        "22.04.4 LTS (Jammy)",
            "version":      "22.04.4 LTS",
            "iso_url":      "https://releases.ubuntu.com/22.04/ubuntu-22.04.4-desktop-amd64.iso",
            "iso_filename": "ubuntu-22.04.4-desktop-amd64.iso",
        },
        {
            "label":        "20.04.6 LTS (Focal)",
            "version":      "20.04.6 LTS",
            "iso_url":      "https://releases.ubuntu.com/20.04/ubuntu-20.04.6-desktop-amd64.iso",
            "iso_filename": "ubuntu-20.04.6-desktop-amd64.iso",
        },
    ],
    "fedora_40": [
        {
            "label":        "Fedora 41 Workstation",
            "version":      "41",
            "iso_url":      "https://download.fedoraproject.org/pub/fedora/linux/releases/41/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-41-1.4.iso",
            "iso_filename": "Fedora-Workstation-Live-x86_64-41-1.4.iso",
        },
        {
            "label":        "Fedora 40 Workstation",
            "version":      "40",
            "iso_url":      "https://archives.fedoraproject.org/pub/archive/fedora/linux/releases/40/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-40-1.14.iso",
            "iso_filename": "Fedora-Workstation-Live-x86_64-40-1.14.iso",
        },
    ],
    "kali": [
        {
            "label":        "Kali Linux 2024.2",
            "version":      "2024.2",
            "iso_url":      "https://cdimage.kali.org/kali-2024.2/kali-linux-2024.2-installer-amd64.iso",
            "iso_filename": "kali-linux-2024.2-installer-amd64.iso",
        },
        {
            "label":        "Kali Linux 2023.4",
            "version":      "2023.4",
            "iso_url":      "https://cdimage.kali.org/kali-2023.4/kali-linux-2023.4-installer-amd64.iso",
            "iso_filename": "kali-linux-2023.4-installer-amd64.iso",
        },
    ],
}

def _get_versions(os_id: str) -> list[dict]:
    """Return version list for an OS, or empty list if none defined."""
    for key, versions in _VERSION_CATALOG.items():
        if key == os_id or os_id.startswith(key) or key in os_id:
            return versions
    return []


# ── helpers ──────────────────────────────────────────────────────────────────

_CONF_STYLE = {
    "Optimal":  ("🟢 Optimal",  "#22c55e", "rgba(34,197,94,0.15)",  "rgba(34,197,94,0.4)"),
    "Balanced": ("🟡 Balanced", "#f59e0b", "rgba(245,158,11,0.15)", "rgba(245,158,11,0.4)"),
    "Low":      ("🔴 Risky",    "#ef4444", "rgba(239,68,68,0.15)",  "rgba(239,68,68,0.4)"),
}

_OS_ICONS = {
    "ubuntu":  "🐧", "fedora":  "🎩", "debian": "🌀",
    "kali":    "🐉", "windows": "🪟", "default": "💻",
}

def _os_icon(os_id: str) -> str:
    for k, v in _OS_ICONS.items():
        if k in os_id.lower():
            return v
    return "💻"


# ── slider row ───────────────────────────────────────────────────────────────

class _SliderRow(QWidget):
    """Labelled QSlider with live value display."""
    valueChanged = pyqtSignal(int)

    def __init__(
        self, label: str, unit: str,
        lo: int, hi: int, step: int, value: int,
        parent=None
    ):
        super().__init__(parent)
        self._step = step
        self._unit = unit

        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(6)

        # Top row: label + current value
        hdr = QHBoxLayout()
        self._label_lbl = BodyLabel(label)
        self._val_lbl   = StrongBodyLabel(f"{value} {unit}")
        self._val_lbl.setStyleSheet("color: #60a5fa; font-weight: 700;")
        hdr.addWidget(self._label_lbl)
        hdr.addStretch()
        hdr.addWidget(self._val_lbl)
        lay.addLayout(hdr)

        # Slider
        self._slider = QSlider(Qt.Horizontal)
        self._slider.setRange(lo // step, hi // step)
        self._slider.setValue(value // step)
        self._slider.setSingleStep(1)
        self._slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 6px; background: rgba(255,255,255,0.12); border-radius: 3px;
            }
            QSlider::sub-page:horizontal {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #06b6d4);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                width: 18px; height: 18px; margin: -6px 0;
                background: #ffffff; border-radius: 9px;
                border: 2px solid #3b82f6;
            }
        """)
        self._slider.valueChanged.connect(self._on_change)
        lay.addWidget(self._slider)

        # Range hint
        rng = CaptionLabel(f"{lo} {unit}  ←  →  {hi} {unit}")
        rng.setStyleSheet("color: rgba(255,255,255,0.35);")
        lay.addWidget(rng)

    def _on_change(self, ticks: int):
        v = ticks * self._step
        self._val_lbl.setText(f"{v} {self._unit}")
        self.valueChanged.emit(v)

    def value(self) -> int:
        return self._slider.value() * self._step

    def set_enabled(self, en: bool):
        self._slider.setEnabled(en)


# ── Close button (Issue 1 fix) ────────────────────────────────────────────────

class _CloseButton(QPushButton):
    """Properly styled close button — hover + click feedback, no absolute pos."""

    def __init__(self, parent=None):
        super().__init__("✕", parent)
        self.setFixedSize(32, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setToolTip("Close")
        self._apply_normal()

    def _apply_normal(self):
        self.setStyleSheet("""
            QPushButton {
                background: rgba(255,255,255,0.06);
                color: rgba(255,255,255,0.6);
                border: 1px solid rgba(255,255,255,0.1);
                border-radius: 8px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover {
                background: rgba(239,68,68,0.85);
                color: #ffffff;
                border: 1px solid rgba(239,68,68,0.9);
            }
            QPushButton:pressed {
                background: rgba(220,38,38,0.95);
            }
        """)


# ── main dialog ──────────────────────────────────────────────────────────────

class VMConfigDialog(QDialog):
    """
    AI-powered VM configuration + one-click deploy modal.
    Call show_for(template, iso_manager, vm_service, parent) to open.
    """
    vm_created = pyqtSignal(object)   # VMRecord on success

    def __init__(self, template, iso_manager, vm_service, parent=None):
        super().__init__(parent)
        self.template    = template
        self.iso_manager = iso_manager
        self.vm_service  = vm_service
        self._worker     = None
        self._versions   = _get_versions(template.os_id)
        self._sel_ver_idx = 0   # currently selected version index

        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setModal(True)
        self.setMinimumWidth(600)

        self._build_ui()
        self._load_recommendation()

    # ── Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)

        card = CardWidget(self)
        card.setBorderRadius(20)
        card.setStyleSheet("""
            CardWidget {
                background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                    stop:0 rgba(30,30,46,0.98), stop:1 rgba(20,20,35,0.98));
                border: 1px solid rgba(255,255,255,0.08);
            }
        """)
        shadow = QGraphicsDropShadowEffect(card)
        shadow.setBlurRadius(50); shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 140))
        card.setGraphicsEffect(shadow)
        outer.addWidget(card)

        root = QVBoxLayout(card)
        root.setContentsMargins(36, 28, 36, 32)
        root.setSpacing(18)

        # ── Header (FIXED: close button top-right via stretch, no overlap) ──
        hdr = QHBoxLayout()
        hdr.setSpacing(12)
        hdr.setAlignment(Qt.AlignTop)

        icon_lbl = StrongBodyLabel(_os_icon(self.template.os_id))
        icon_lbl.setStyleSheet("font-size: 42px;")
        icon_lbl.setFixedSize(60, 60)
        hdr.addWidget(icon_lbl, 0, Qt.AlignTop)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = TitleLabel(f"Configure {self.template.os_name}")
        title.setStyleSheet("font-size: 22px; font-weight: 800;")
        sub   = BodyLabel(f"{self.template.version}  •  AI-assisted setup")
        sub.setStyleSheet("color: rgba(255,255,255,0.5);")
        text_col.addWidget(title)
        text_col.addWidget(sub)
        hdr.addLayout(text_col, stretch=1)

        # ── FIXED: close button pinned to top-right with AlignTop ──────────
        self._close_btn = _CloseButton()
        self._close_btn.clicked.connect(self.reject)
        hdr.addWidget(self._close_btn, 0, Qt.AlignTop | Qt.AlignRight)

        root.addLayout(hdr)

        _divider(root)

        # ── Version selector (NEW: Section 2) ─────────────────────────────
        if self._versions:
            ver_row = QHBoxLayout()
            ver_lbl = StrongBodyLabel("Version:")
            ver_lbl.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 13px;")
            ver_lbl.setFixedWidth(70)
            ver_row.addWidget(ver_lbl)

            self._ver_combo = ComboBox()
            for v in self._versions:
                self._ver_combo.addItem(v["label"])
            self._ver_combo.setFixedHeight(36)
            self._ver_combo.currentIndexChanged.connect(self._on_version_changed)
            ver_row.addWidget(self._ver_combo, stretch=1)
            root.addLayout(ver_row)

        # ── System specs row ──
        self._specs_lbl = CaptionLabel("Detecting system…")
        self._specs_lbl.setStyleSheet("color: rgba(255,255,255,0.45);")
        root.addWidget(self._specs_lbl)

        # ── AI confidence badge ──
        self._conf_badge = QLabel("🟡 Detecting…")
        self._conf_badge.setFixedHeight(28)
        self._conf_badge.setAlignment(Qt.AlignCenter)
        self._conf_badge.setStyleSheet(
            "color: #f59e0b; background: rgba(245,158,11,0.12);"
            "border: 1px solid rgba(245,158,11,0.4); border-radius: 12px;"
            "padding: 2px 14px; font-size: 12px; font-weight: 600;"
        )
        root.addWidget(self._conf_badge, alignment=Qt.AlignLeft)

        self._conf_reason = CaptionLabel("")
        self._conf_reason.setStyleSheet("color: rgba(255,255,255,0.45);")
        root.addWidget(self._conf_reason)

        _divider(root)

        # ── Sliders ──
        self._ram_slider  = None
        self._cpu_slider  = None
        self._disk_slider = None
        self._slider_container = QVBoxLayout()
        self._slider_container.setSpacing(16)
        root.addLayout(self._slider_container)

        # ── Auto-launch checkbox ──
        self._launch_chk = QCheckBox("Launch VM immediately after creation")
        self._launch_chk.setStyleSheet("color: rgba(255,255,255,0.7); font-size: 12px;")
        self._launch_chk.setChecked(True)
        root.addWidget(self._launch_chk)

        _divider(root)

        # ── Progress area (hidden until deploy) ──
        self._prog_bar = QProgressBar()
        self._prog_bar.setRange(0, 100)
        self._prog_bar.setValue(0)
        self._prog_bar.setTextVisible(False)
        self._prog_bar.setFixedHeight(6)
        self._prog_bar.setStyleSheet("""
            QProgressBar { background: rgba(255,255,255,0.08); border-radius: 3px; }
            QProgressBar::chunk {
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #3b82f6, stop:1 #06b6d4);
                border-radius: 3px;
            }
        """)
        self._prog_bar.hide()
        root.addWidget(self._prog_bar)

        self._stage_lbl = BodyLabel("")
        self._stage_lbl.setStyleSheet("color: rgba(255,255,255,0.6); font-size: 12px;")
        self._stage_lbl.hide()
        root.addWidget(self._stage_lbl)

        # ── Action buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        self._cancel_btn = PushButton(FIF.CLOSE, "Cancel")
        self._cancel_btn.setFixedHeight(42)
        self._cancel_btn.clicked.connect(self._on_cancel)

        self._deploy_btn = PrimaryPushButton(FIF.SEND, "🚀  Create & Launch VM")
        self._deploy_btn.setFixedHeight(42)
        self._deploy_btn.setEnabled(False)   # enabled after recommendation loads
        self._deploy_btn.clicked.connect(self._on_deploy)

        btn_row.addWidget(self._cancel_btn)
        btn_row.addStretch()
        btn_row.addWidget(self._deploy_btn)
        root.addLayout(btn_row)

    # ── Version selector ──────────────────────────────────────────────────

    def _on_version_changed(self, idx: int):
        """Update template ISO url/filename when user picks a different version."""
        self._sel_ver_idx = idx
        if not self._versions:
            return
        ver = self._versions[idx]
        self.template.iso_url      = ver["iso_url"]
        self.template.iso_filename = ver["iso_filename"]
        # Update subtitle label
        try:
            sub_text = f"{ver['version']}  •  AI-assisted setup"
            # The sub label is inside text_col — update via stored reference
            if hasattr(self, "_ver_sub_lbl"):
                self._ver_sub_lbl.setText(sub_text)
        except Exception:
            pass

    def _selected_version(self) -> dict | None:
        if self._versions and 0 <= self._sel_ver_idx < len(self._versions):
            return self._versions[self._sel_ver_idx]
        return None

    # ── Recommendation ────────────────────────────────────────────────────

    def _load_recommendation(self):
        from PyQt5.QtCore import QTimer
        QTimer.singleShot(100, self._do_load)

    def _do_load(self):
        specs = get_system_specs()
        rec   = recommend_config(self.template.os_id, specs)

        # Update specs label
        self._specs_lbl.setText(
            f"Host: {specs.total_ram_mb // 1024} GB RAM  •  "
            f"{specs.total_cores} logical cores  •  "
            f"{specs.disk_free_gb} GB disk free"
        )

        # Update confidence badge
        conf_text, conf_col, conf_bg, conf_border = _CONF_STYLE[rec.confidence]
        self._conf_badge.setText(conf_text)
        self._conf_badge.setStyleSheet(
            f"color: {conf_col}; background: {conf_bg};"
            f"border: 1px solid {conf_border}; border-radius: 12px;"
            "padding: 2px 14px; font-size: 12px; font-weight: 600;"
        )
        self._conf_reason.setText(rec.reason)

        # Build sliders with AI-recommended defaults
        ram_max  = min(specs.total_ram_mb, 32768)
        cpu_max  = specs.total_cores
        disk_max = max(rec.disk_gb + 20, min(specs.disk_free_gb - 2, 500))

        self._ram_slider  = _SliderRow("RAM",  "MB",  2048,  ram_max,  512,  rec.ram_mb)
        self._cpu_slider  = _SliderRow("CPU",  "cores", 1,   cpu_max,  1,    rec.cpu_count)
        self._disk_slider = _SliderRow("Disk", "GB",   20,   disk_max, 5,    rec.disk_gb)

        self._ram_slider.valueChanged.connect(self._update_confidence_live)
        self._cpu_slider.valueChanged.connect(self._update_confidence_live)
        self._disk_slider.valueChanged.connect(self._update_confidence_live)

        self._slider_container.addWidget(self._ram_slider)
        self._slider_container.addWidget(self._cpu_slider)
        self._slider_container.addWidget(self._disk_slider)

        self._deploy_btn.setEnabled(True)
        self._specs = specs

    def _update_confidence_live(self):
        """Recalculate confidence badge as user moves sliders."""
        if not (self._ram_slider and self._specs):
            return
        ram  = self._ram_slider.value()
        disk = self._disk_slider.value()

        if (self._specs.available_ram_mb >= ram * 2
                and self._specs.disk_free_gb >= disk + 20):
            conf = "Optimal"
        elif (self._specs.available_ram_mb >= ram
                and self._specs.disk_free_gb >= disk + 5):
            conf = "Balanced"
        else:
            conf = "Low"

        conf_text, conf_col, conf_bg, conf_border = _CONF_STYLE[conf]
        self._conf_badge.setText(conf_text)
        self._conf_badge.setStyleSheet(
            f"color: {conf_col}; background: {conf_bg};"
            f"border: 1px solid {conf_border}; border-radius: 12px;"
            "padding: 2px 14px; font-size: 12px; font-weight: 600;"
        )

    # ── Deploy ────────────────────────────────────────────────────────────

    def _on_deploy(self):
        self._set_busy(True)

        # Apply selected version metadata to template before deploy
        sel = self._selected_version()
        if sel:
            self.template.iso_url      = sel["iso_url"]
            self.template.iso_filename = sel["iso_filename"]

        self._worker = QuickDeployWorker(
            template    = self.template,
            iso_manager = self.iso_manager,
            vm_service  = self.vm_service,
            ram_mb      = self._ram_slider.value()  if self._ram_slider  else 4096,
            cpu_count   = self._cpu_slider.value()  if self._cpu_slider  else 2,
            disk_gb     = self._disk_slider.value() if self._disk_slider else 40,
            auto_launch = self._launch_chk.isChecked(),
        )
        self._worker.stage.connect(self._on_stage)
        self._worker.progress.connect(self._prog_bar.setValue)
        self._worker.finished.connect(self._on_finished)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_stage(self, text: str):
        self._stage_lbl.setText(text)

    def _on_finished(self, rec):
        self._set_busy(False)
        self._prog_bar.setValue(100)
        self.vm_created.emit(rec)
        self.accept()

    def _on_error(self, err: str):
        self._set_busy(False)
        InfoBar.error(
            "Deployment Failed", err[:300],
            duration=8000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.parent() or self,
        )

    def _on_cancel(self):
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        self.reject()

    def _set_busy(self, busy: bool):
        self._deploy_btn.setEnabled(not busy)
        self._cancel_btn.setEnabled(not busy)
        self._close_btn.setEnabled(not busy)
        self._launch_chk.setEnabled(not busy)
        if hasattr(self, "_ver_combo"):
            self._ver_combo.setEnabled(not busy)
        if self._ram_slider:  self._ram_slider.set_enabled(not busy)
        if self._cpu_slider:  self._cpu_slider.set_enabled(not busy)
        if self._disk_slider: self._disk_slider.set_enabled(not busy)
        self._prog_bar.setVisible(busy)
        self._stage_lbl.setVisible(busy)
        if busy:
            self._deploy_btn.setText("Deploying…")
        else:
            self._deploy_btn.setText("🚀  Create & Launch VM")

    # ── Factory helper ────────────────────────────────────────────────────

    @staticmethod
    def show_for(template, iso_manager, vm_service, parent=None):
        dlg = VMConfigDialog(template, iso_manager, vm_service, parent)
        return dlg


# ── utility ──────────────────────────────────────────────────────────────────

def _divider(layout: QVBoxLayout):
    line = QWidget()
    line.setFixedHeight(1)
    line.setStyleSheet("background: rgba(255,255,255,0.07);")
    layout.addWidget(line)
