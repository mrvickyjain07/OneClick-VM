"""
marketplace_page.py
===================
Phase 2: OS Marketplace — browse, download, and manage ISOs.

Features:
- OS cards (Ubuntu, Fedora, Kali, Debian)
- "Already Downloaded" status per card
- Download button with progress bar per card
- ISO cache system (skips re-download)
- Background download thread (QThread)
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QScrollArea, QFrame, QProgressBar, QSizePolicy, QGridLayout,
    QFileDialog, QMessageBox
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal

from backend import config
from backend.iso_manager import ISOManager


# ── ISO catalog ───────────────────────────────────────────────────────────────
ISO_CATALOG = [
    {
        "os_id":    "ubuntu_24_04",
        "os_name":  "Ubuntu",
        "version":  "24.04 LTS",
        "icon":     "🐧",
        "iso_url":  "https://releases.ubuntu.com/24.04/ubuntu-24.04-live-server-amd64.iso",
        "filename": "ubuntu-24.04-live-server-amd64.iso",
        "size_gb":  "2.7",
        "desc":     "The world's most popular Linux distribution.",
    },
    {
        "os_id":    "fedora_40",
        "os_name":  "Fedora",
        "version":  "40 Workstation",
        "icon":     "🎩",
        "iso_url":  "https://download.fedoraproject.org/pub/fedora/linux/releases/40/Workstation/x86_64/iso/Fedora-Workstation-Live-x86_64-40-1.14.iso",
        "filename": "Fedora-Workstation-Live-x86_64-40-1.14.iso",
        "size_gb":  "2.1",
        "desc":     "Cutting-edge features, GNOME desktop.",
    },
    {
        "os_id":    "debian_12",
        "os_name":  "Debian",
        "version":  "12 Bookworm",
        "icon":     "🌀",
        "iso_url":  "https://cdimage.debian.org/debian-cd/current/amd64/iso-cd/debian-12.6.0-amd64-netinst.iso",
        "filename": "debian-12.6.0-amd64-netinst.iso",
        "size_gb":  "0.7",
        "desc":     "Rock-solid, stable, universal OS.",
    },
    {
        "os_id":    "kali_2024",
        "os_name":  "Kali Linux",
        "version":  "2024.2",
        "icon":     "🐉",
        "iso_url":  "https://cdimage.kali.org/kali-2024.2/kali-linux-2024.2-installer-amd64.iso",
        "filename": "kali-linux-2024.2-installer-amd64.iso",
        "size_gb":  "4.0",
        "desc":     "Penetration testing & security research.",
    },
]


class DownloadWorker(QThread):
    """Background ISO download thread."""
    progress  = pyqtSignal(dict)
    finished  = pyqtSignal(bool, str)   # (success, message)

    def __init__(self, url: str, dest_path: Path, parent=None):
        super().__init__(parent)
        self._url       = url
        self._dest_path = dest_path
        self._mgr       = ISOManager()

    def run(self):
        try:
            self._mgr.download_iso(
                self._url,
                self._dest_path,
                progress_callback=self.progress.emit
            )
            self.finished.emit(True, "Download complete!")
        except Exception as exc:
            self.finished.emit(False, str(exc))


class OSCard(QFrame):
    """Card widget for a single OS in the marketplace."""

    download_requested = pyqtSignal(dict)   # emits catalog entry dict
    import_requested   = pyqtSignal(str)    # emits os_id

    def __init__(self, entry: dict, parent=None):
        super().__init__(parent)
        self.entry    = entry
        self._worker: DownloadWorker | None = None
        self.setObjectName("OSCard")
        self.setFixedHeight(200)
        self._build_ui()
        self.refresh_status()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Top row: icon + name + version
        top = QHBoxLayout()
        icon_lbl = QLabel(self.entry["icon"])
        icon_lbl.setFixedSize(44, 44)
        icon_lbl.setAlignment(Qt.AlignCenter)
        icon_lbl.setStyleSheet(
            "font-size: 28px; background: rgba(88,166,255,0.08); border-radius: 8px;"
        )
        top.addWidget(icon_lbl)

        name_col = QVBoxLayout()
        name_col.setSpacing(2)
        name_lbl = QLabel(self.entry["os_name"])
        name_lbl.setObjectName("VMName")
        ver_lbl  = QLabel(self.entry["version"])
        ver_lbl.setObjectName("VMDetail")
        name_col.addWidget(name_lbl)
        name_col.addWidget(ver_lbl)
        top.addLayout(name_col)
        top.addStretch()

        self.status_badge = QLabel()
        self.status_badge.setFixedHeight(22)
        self.status_badge.setMinimumWidth(100)
        self.status_badge.setAlignment(Qt.AlignCenter)
        top.addWidget(self.status_badge)

        layout.addLayout(top)

        # Description
        desc_lbl = QLabel(self.entry["desc"])
        desc_lbl.setObjectName("VMDetail")
        desc_lbl.setWordWrap(True)
        layout.addWidget(desc_lbl)

        # Size
        size_lbl = QLabel(f"Size: ~{self.entry['size_gb']} GB")
        size_lbl.setObjectName("VMDetail")
        layout.addWidget(size_lbl)

        # Progress bar (hidden by default)
        self.progress_bar = QProgressBar()
        self.progress_bar.setValue(0)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setVisible(False)
        layout.addWidget(self.progress_bar)

        # Button row
        btn_row = QHBoxLayout()
        self.btn_download = QPushButton("⬇  Download")
        self.btn_download.setObjectName("PrimaryButton")
        self.btn_download.setFixedHeight(30)
        self.btn_download.clicked.connect(self._on_download_clicked)

        self.btn_import = QPushButton("📂  Import ISO")
        self.btn_import.setFixedHeight(30)
        self.btn_import.clicked.connect(lambda: self.import_requested.emit(self.entry["os_id"]))

        btn_row.addWidget(self.btn_download)
        btn_row.addWidget(self.btn_import)
        layout.addLayout(btn_row)

    def refresh_status(self):
        """Check if ISO is on disk and update badge + button."""
        dest = config.ISO_CACHE_DIR / self.entry["filename"]
        if dest.exists():
            self.status_badge.setText("✅ Downloaded")
            self.status_badge.setStyleSheet(
                "background: rgba(63,185,80,0.18); color: #3FB950; "
                "border: 1px solid rgba(63,185,80,0.4); border-radius: 4px; padding: 1px 6px;"
            )
            self.btn_download.setText("⟳  Re-download")
            self.btn_download.setObjectName("SuccessButton")
        else:
            self.status_badge.setText("Not downloaded")
            self.status_badge.setStyleSheet(
                "background: rgba(139,148,158,0.15); color: #8B949E; "
                "border: 1px solid rgba(139,148,158,0.3); border-radius: 4px; padding: 1px 6px;"
            )
            self.btn_download.setText("⬇  Download")
            self.btn_download.setObjectName("PrimaryButton")
        # Re-polish
        self.btn_download.style().unpolish(self.btn_download)
        self.btn_download.style().polish(self.btn_download)

    def _on_download_clicked(self):
        dest = config.ISO_CACHE_DIR / self.entry["filename"]
        self.progress_bar.setVisible(True)
        self.progress_bar.setValue(0)
        self.btn_download.setEnabled(False)
        self.btn_import.setEnabled(False)

        self._worker = DownloadWorker(self.entry["iso_url"], dest)
        self._worker.progress.connect(self._on_progress)
        self._worker.finished.connect(self._on_download_finished)
        self._worker.start()

    def _on_progress(self, data: dict):
        self.progress_bar.setValue(int(data.get("percentage", 0)))

    def _on_download_finished(self, success: bool, msg: str):
        self.btn_download.setEnabled(True)
        self.btn_import.setEnabled(True)
        self.progress_bar.setVisible(False)
        if success:
            self.refresh_status()
        else:
            QMessageBox.critical(None, "Download Error", msg)


class MarketplacePage(QWidget):
    """Full marketplace page with a grid of OS cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._iso_mgr = ISOManager()
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)

        # Header
        title    = QLabel("Marketplace")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Download and manage OS images for your virtual machines")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        # ISO storage path info
        path_bar = QHBoxLayout()
        path_lbl = QLabel(f"📁  ISO Storage:  {config.ISO_CACHE_DIR}")
        path_lbl.setObjectName("VMDetail")
        btn_open = QPushButton("Open Folder")
        btn_open.setFixedHeight(28)
        btn_open.clicked.connect(self._open_iso_folder)
        path_bar.addWidget(path_lbl)
        path_bar.addStretch()
        path_bar.addWidget(btn_open)
        root.addLayout(path_bar)

        # Scrollable grid
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)

        container = QWidget()
        grid = QGridLayout(container)
        grid.setSpacing(16)
        grid.setContentsMargins(0, 8, 8, 8)

        for i, entry in enumerate(ISO_CATALOG):
            card = OSCard(entry)
            card.import_requested.connect(self._on_import_requested)
            row, col = divmod(i, 2)
            grid.addWidget(card, row, col)

        # Fill remaining columns
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        scroll.setWidget(container)
        root.addWidget(scroll, stretch=1)

    def _open_iso_folder(self):
        import subprocess, os
        path = str(config.ISO_CACHE_DIR)
        try:
            os.startfile(path)
        except Exception:
            subprocess.Popen(["explorer", path])

    def _on_import_requested(self, os_id: str):
        """Let user pick an ISO file from disk and copy/symlink to cache."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Import ISO File", "", "ISO Images (*.iso);;All Files (*)"
        )
        if not path:
            return
        import shutil
        src  = Path(path)
        dest = config.ISO_CACHE_DIR / src.name
        if dest.exists():
            QMessageBox.information(self, "Already Exists", f"'{src.name}' is already in the ISO cache.")
            return
        try:
            shutil.copy2(src, dest)
            QMessageBox.information(self, "Imported", f"'{src.name}' has been added to the ISO cache.")
        except Exception as exc:
            QMessageBox.critical(self, "Import Error", str(exc))
