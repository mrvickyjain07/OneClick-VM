import os
from PyQt5.QtCore import Qt, pyqtSignal, QSize
from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget, QSizePolicy, QLabel
from PyQt5.QtGui import QColor

from qfluentwidgets import (
    CardWidget, TitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, ProgressBar, FluentIcon as FIF,
    IconWidget, InfoBadge, InfoBadgePosition
)

# ── Status Colors ──
STATUS_COLORS = {
    "not_installed": "#8B949E",
    "downloading": "#0088ff",
    "installed": "#8B949E", # Stopped
    "running": "#00C6FF",
    "poweroff": "#8B949E",
    "aborted": "#F85149",
    "unknown": "#8B949E"
}

OS_ICONS = {
    "ubuntu":  "🐧", "fedora": "🎩", "debian": "🌀",
    "centos":  "🔴", "arch":   "🏹", "kali":   "🐉",
    "windows": "🪟", "macos":  "🍎",
}

def get_os_icon(os_id: str) -> str:
    for k, v in OS_ICONS.items():
        if k in os_id.lower(): return v
    return "💻"

class StatCard(CardWidget):
    """Component: StatCard
    Displays a title, a large value, and a colored status dot.
    """
    def __init__(self, title: str, value: str, dot_color: str = "#00C6FF", parent=None):
        super().__init__(parent)
        self.setFixedHeight(100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setBorderRadius(12)
        
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 16, 20, 16)
        
        h_layout = QHBoxLayout()
        self.title_lbl = BodyLabel(title)
        
        self.dot = QWidget()
        self.dot.setFixedSize(10, 10)
        self.dot.setStyleSheet(f"background-color: {dot_color}; border-radius: 5px;")
        
        h_layout.addWidget(self.title_lbl)
        h_layout.addStretch(1)
        h_layout.addWidget(self.dot)
        
        self.val_lbl = TitleLabel(str(value))
        
        layout.addLayout(h_layout)
        layout.addStretch(1)
        layout.addWidget(self.val_lbl)

    def set_value(self, val):
        self.val_lbl.setText(str(val))


class VMCard(CardWidget):
    """Component: VMCard
    Universal card for Marketplace and Dashboard.
    States: not_downloaded, downloading, downloaded, installing, installed, running, poweroff
    """
    action_requested = pyqtSignal(str, str) # identifier, action_name

    def __init__(self, item_data: dict, state: str = "not_downloaded", parent=None):
        super().__init__(parent)
        self.item_data = item_data
        self.identifier = item_data.get("vm_name") or item_data.get("os_id", "unknown")
        self.state = state.lower()
        
        self.setFixedHeight(220)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setBorderRadius(12)
        
        self._build_ui()
        self.update_state(self.state)

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # -- Top Row --
        top_row = QHBoxLayout()
        os_id = self.item_data.get("os_id", "")
        self.icon_lbl = TitleLabel(get_os_icon(os_id))
        self.icon_lbl.setFixedSize(48, 48)
        self.icon_lbl.setAlignment(Qt.AlignCenter)
        
        info_col = QVBoxLayout()
        info_col.setSpacing(4)
        
        name = self.item_data.get("vm_name") or self.item_data.get("os_name", "Unknown")
        self.name_lbl = StrongBodyLabel(name)
        self.name_lbl.setWordWrap(True)
        
        # Tags and difficulty
        tags = self.item_data.get("tags", "")
        diff = self.item_data.get("difficulty", "")
        tag_str = f"[{tags}] · {diff}" if tags and diff else ""
        
        desc_text = self.item_data.get("desc") or f"{os_id} · {self.item_data.get('ram_mb', '?')} MB"
        if tag_str: desc_text += f"\n{tag_str}"
        self.desc_lbl = CaptionLabel(desc_text)
        self.desc_lbl.setWordWrap(True)
        
        info_col.addWidget(self.name_lbl)
        info_col.addWidget(self.desc_lbl)
        
        self.status_badge = InfoBadge.info("Status")
        
        top_row.addWidget(self.icon_lbl)
        top_row.addSpacing(12)
        top_row.addLayout(info_col)
        top_row.addStretch(1)
        top_row.addWidget(self.status_badge, alignment=Qt.AlignTop)
        
        layout.addLayout(top_row)
        
        # -- Progress Bar --
        self.progress = ProgressBar()
        self.progress.hide()
        layout.addWidget(self.progress)
        
        layout.addStretch(1)

        # -- Bottom Row (Actions) --
        btn_row = QHBoxLayout()
        
        self.btn_primary = PrimaryPushButton("Action")
        self.btn_primary.setFixedHeight(36)
        self.btn_primary.clicked.connect(self._on_primary)
        
        self.btn_secondary = PushButton(FIF.IOT, "Recommend Hardware")
        self.btn_secondary.setFixedHeight(36)
        self.btn_secondary.clicked.connect(self._on_recommend)
        
        self.btn_icon = PushButton(FIF.SETTING, "")
        self.btn_icon.setFixedSize(36, 36)
        self.btn_icon.clicked.connect(self._on_settings)
        self.btn_icon.hide()

        self.btn_delete = PushButton(FIF.DELETE, "")
        self.btn_delete.setFixedSize(36, 36)
        self.btn_delete.clicked.connect(self._on_delete)
        self.btn_delete.hide()

        btn_row.addWidget(self.btn_primary, stretch=1)
        btn_row.addWidget(self.btn_secondary)
        btn_row.addSpacing(8)
        btn_row.addWidget(self.btn_icon)
        btn_row.addWidget(self.btn_delete)
        
        layout.addLayout(btn_row)

    def update_state(self, state: str):
        self.state = state.lower()
        
        # Defaults
        self.progress.hide()
        self.btn_secondary.hide()
        self.btn_icon.hide()
        self.btn_delete.hide()
        self.btn_primary.setEnabled(True)
        self.status_badge.setText(state.capitalize())

        if self.state == "not_downloaded" or self.state == "not_installed":
            self.status_badge.setText("Available")
            self.btn_primary.setText("Download")
            self.btn_primary.setIcon(FIF.DOWNLOAD)
            
        elif self.state == "downloading":
            self.status_badge.setText("Downloading...")
            self.progress.show()
            self.btn_primary.setText("Downloading")
            self.btn_primary.setEnabled(False)
            
        elif self.state == "downloaded":
            self.status_badge.setText("Ready to Install")
            self.btn_primary.setText("Install")
            self.btn_primary.setIcon(FIF.SEND)
            
        elif self.state == "installing":
            self.status_badge.setText("Installing...")
            self.progress.show()
            self.progress.setRange(0, 0) # Indeterminate
            self.btn_primary.setText("Installing")
            self.btn_primary.setEnabled(False)
            self.btn_secondary.setEnabled(False)
            
        elif self.state in ["installed", "poweroff", "saved", "aborted"]:
            self.progress.setRange(0, 100) # Reset
            self.status_badge.setText("Stopped" if self.state != "saved" else "Saved")
            self.btn_primary.setText("Launch")
            self.btn_primary.setIcon(FIF.PLAY)
            self.btn_icon.show()
            self.btn_delete.show()
            self.btn_secondary.hide()
            
        elif self.state == "running":
            self.progress.setRange(0, 100)
            self.status_badge.setText("Running")
            self.btn_primary.setText("Stop")
            self.btn_primary.setIcon(FIF.POWER_BUTTON)
            self.btn_icon.show()
            self.btn_delete.show()
            self.btn_secondary.hide()
            
        else:
            self.status_badge.setText("Unknown")
            self.btn_primary.setText("Unavailable")
            self.btn_primary.setEnabled(False)
            self.btn_icon.show()
            self.btn_delete.show()

    def update_progress(self, val: int):
        if self.state == "downloading":
            self.progress.setValue(val)

    def _on_primary(self):
        if self.state in ["not_downloaded", "not_installed"]:
            self.action_requested.emit(self.identifier, "download")
        elif self.state == "downloaded":
            self.action_requested.emit(self.identifier, "install")
        elif self.state in ["installed", "poweroff", "saved", "aborted", "unknown"]:
            self.action_requested.emit(self.identifier, "start")
        elif self.state == "running":
            self.action_requested.emit(self.identifier, "stop")

    def _on_recommend(self):
        self.action_requested.emit(self.identifier, "recommend")

    def _on_settings(self):
        self.action_requested.emit(self.identifier, "settings")
        
    def _on_delete(self):
        self.action_requested.emit(self.identifier, "delete")


class ActionBar(CardWidget):
    """Component: ActionBar
    Used in Console: Pause, Stop, Restart, Snapshot
    """
    action_requested = pyqtSignal(str) # 'pause', 'stop', 'restart', 'snapshot'

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(64)
        self.setBorderRadius(12)
        
        layout = QHBoxLayout(self)
        layout.setContentsMargins(16, 8, 16, 8)
        layout.setSpacing(12)

        self.btn_pause = PushButton(FIF.PAUSE, "Pause")
        self.btn_stop = PrimaryPushButton(FIF.POWER_BUTTON, "Stop")
        self.btn_restart = PushButton(FIF.SYNC, "Restart")
        self.btn_snapshot = PushButton(FIF.CAMERA, "Snapshot")

        self.btn_pause.clicked.connect(lambda: self.action_requested.emit("pause"))
        self.btn_stop.clicked.connect(lambda: self.action_requested.emit("stop"))
        self.btn_restart.clicked.connect(lambda: self.action_requested.emit("restart"))
        self.btn_snapshot.clicked.connect(lambda: self.action_requested.emit("snapshot"))

        layout.addWidget(self.btn_pause)
        layout.addWidget(self.btn_stop)
        layout.addWidget(self.btn_restart)
        layout.addWidget(self.btn_snapshot)
        layout.addStretch(1)


class InfoPanel(CardWidget):
    """Component: InfoPanel
    Used in Console (right side stats): CPU, RAM, Network
    """
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setBorderRadius(12)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(16)

        title = TitleLabel("System Stats")
        layout.addWidget(title)

        # CPU
        layout.addWidget(StrongBodyLabel("CPU Usage"))
        self.cpu_bar = ProgressBar()
        layout.addWidget(self.cpu_bar)

        # RAM
        layout.addWidget(StrongBodyLabel("RAM Usage"))
        self.ram_bar = ProgressBar()
        layout.addWidget(self.ram_bar)

        # Network
        layout.addWidget(StrongBodyLabel("Network Activity"))
        self.net_lbl = BodyLabel("Rx: 0 KB/s | Tx: 0 KB/s")
        layout.addWidget(self.net_lbl)
        
        layout.addStretch(1)

    def update_stats(self, cpu: int, ram: int, rx: str, tx: str):
        self.cpu_bar.setValue(cpu)
        self.ram_bar.setValue(ram)
        self.net_lbl.setText(f"Rx: {rx} | Tx: {tx}")
