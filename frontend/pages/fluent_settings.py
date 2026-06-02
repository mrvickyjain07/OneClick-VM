"""
fluent_settings.py
===================
Settings page — Fluent edition.
Manage app configuration (paths, defaults) with JSON persistence.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QFileDialog
from PyQt5.QtCore import Qt

from qfluentwidgets import (
    ScrollArea, ExpandLayout, SettingCardGroup, PushSettingCard,
    FluentIcon as FIF, PrimaryPushSettingCard, InfoBar, InfoBarPosition,
    LineEdit, BodyLabel, TitleLabel
)

from backend import config


class SettingsPage(ScrollArea):
    """Settings page — Fluent edition."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("SettingsPage")
        
        self.scrollWidget = QWidget()
        self.scrollWidget.setObjectName("SettingsContainer")
        self.expandLayout = ExpandLayout(self.scrollWidget)
        
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()
        
        self._init_ui()
        self._load_settings()

    def _init_ui(self):
        self.expandLayout.setContentsMargins(36, 32, 36, 32)
        self.expandLayout.setSpacing(28)
        
        # Header
        self.title_label = TitleLabel("Settings")
        self.expandLayout.addWidget(self.title_label)

        # ── Storage Group ──────────────────────────────────────────────────
        self.storageGroup = SettingCardGroup("Storage Locations", self.scrollWidget)
        
        # VM Data Dir
        self.vm_dir_card = PushSettingCard(
            "Change",
            FIF.FOLDER,
            "Virtual Machine Data Path",
            "Where virtual disks (.vdi) and logs are stored",
            self.storageGroup
        )
        self.vm_dir_card.clicked.connect(self._change_vm_dir)
        self.storageGroup.addSettingCard(self.vm_dir_card)

        # ISO Cache Dir
        self.iso_dir_card = PushSettingCard(
            "Change",
            FIF.DOCUMENT,
            "ISO Cache Path",
            "Where downloaded OS installation media are cached",
            self.storageGroup
        )
        self.iso_dir_card.clicked.connect(self._change_iso_dir)
        self.storageGroup.addSettingCard(self.iso_dir_card)

        self.expandLayout.addWidget(self.storageGroup)

        # ── System Integration ─────────────────────────────────────────────
        self.systemGroup = SettingCardGroup("System Integration", self.scrollWidget)
        
        # VirtualBox Path
        self.vbox_path_card = PushSettingCard(
            "Locate",
            FIF.SETTING,
            "VBoxManage Executable Path",
            "Path to VirtualBox CLI (VBoxManage.exe). Leave empty to use system PATH.",
            self.systemGroup
        )
        self.vbox_path_card.clicked.connect(self._change_vbox_path)
        self.systemGroup.addSettingCard(self.vbox_path_card)

        self.expandLayout.addWidget(self.systemGroup)

    def _load_settings(self):
        """Load currently active settings from config module."""
        c = config.load_config()
        self.vm_dir_card.setContent(str(c.get("vm_data_dir", config.VM_DATA_DIR)))
        self.iso_dir_card.setContent(str(c.get("iso_cache_dir", config.ISO_CACHE_DIR)))
        vpath = c.get("vboxmanage_path", "")
        self.vbox_path_card.setContent(vpath if vpath else "Auto-detect (System PATH)")

    def _change_vm_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select VM Data Directory", str(config.VM_DATA_DIR))
        if path:
            self._save_setting("vm_data_dir", path)
            self.vm_dir_card.setContent(path)
            config.VM_DATA_DIR = Path(path)

    def _change_iso_dir(self):
        path = QFileDialog.getExistingDirectory(self, "Select ISO Cache Directory", str(config.ISO_CACHE_DIR))
        if path:
            self._save_setting("iso_cache_dir", path)
            self.iso_dir_card.setContent(path)
            config.ISO_CACHE_DIR = Path(path)

    def _change_vbox_path(self):
        path, _ = QFileDialog.getOpenFileName(self, "Select VBoxManage Executable", "", "Executable (*.exe);;All Files (*)")
        if path:
            self._save_setting("vboxmanage_path", path)
            self.vbox_path_card.setContent(path)
            
    def _save_setting(self, key: str, value: str):
        c = config.load_config()
        c[key] = value
        config.save_config(c)
        InfoBar.success(
            "Settings Saved",
            f"Updated {key.replace('_', ' ').title()}",
            duration=2000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window()
        )
