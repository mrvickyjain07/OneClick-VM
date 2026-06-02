"""
ui/pages/settings_page.py
Settings: ISO cache path, VM data path, VirtualBox path.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QFileDialog
from qfluentwidgets import (
    ScrollArea, TitleLabel, BodyLabel, SubtitleLabel, CardWidget,
    LineEdit, PushButton, PrimaryPushButton, InfoBar, InfoBarPosition,
    FluentIcon as FIF
)
from backend import config


class SettingsPage(ScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("SettingsPage")
        self.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        self.setWidget(container)
        self.setWidgetResizable(True)

        root = QVBoxLayout(container)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(28)

        root.addWidget(TitleLabel("Settings"))
        sub = BodyLabel("Configure paths and preferences for the VM Platform.")
        sub.setStyleSheet("color: rgba(255,255,255,0.55);")
        root.addWidget(sub)

        # ── Paths card ──
        paths_card = CardWidget()
        paths_card.setBorderRadius(14)
        pc_lay = QVBoxLayout(paths_card)
        pc_lay.setContentsMargins(24, 20, 24, 24)
        pc_lay.setSpacing(16)
        pc_lay.addWidget(SubtitleLabel("Storage Paths"))

        def _path_row(label, current_path, browse_fn):
            pc_lay.addWidget(BodyLabel(label))
            row = QHBoxLayout()
            edit = LineEdit()
            edit.setText(str(current_path))
            edit.setReadOnly(True)
            btn  = PushButton(FIF.FOLDER_ADD, "Browse")
            btn.setFixedWidth(100)
            btn.clicked.connect(lambda: browse_fn(edit))
            row.addWidget(edit, stretch=1)
            row.addWidget(btn)
            pc_lay.addLayout(row)
            return edit

        self._iso_edit = _path_row(
            "ISO Cache Directory",
            config.ISO_CACHE_DIR,
            lambda e: self._browse_dir(e),
        )
        self._vm_edit  = _path_row(
            "VM Data Directory",
            config.VM_DATA_DIR,
            lambda e: self._browse_dir(e),
        )

        save_btn = PrimaryPushButton(FIF.ACCEPT, "Save Settings")
        save_btn.setFixedHeight(40)
        save_btn.clicked.connect(self._save)
        pc_lay.addWidget(save_btn)
        root.addWidget(paths_card)

        # ── About card ──
        about_card = CardWidget()
        about_card.setBorderRadius(14)
        ab_lay = QVBoxLayout(about_card)
        ab_lay.setContentsMargins(24, 20, 24, 20)
        ab_lay.setSpacing(8)
        ab_lay.addWidget(SubtitleLabel("About"))
        ab_lay.addWidget(BodyLabel("VM Marketplace  v2.0"))
        ab_lay.addWidget(BodyLabel("Built with PyQt5 + QFluentWidgets"))
        root.addWidget(about_card)

        root.addStretch()

    def _browse_dir(self, edit):
        d = QFileDialog.getExistingDirectory(self, "Select Directory", edit.text())
        if d:
            edit.setText(d)

    def _save(self):
        cfg = config.load_config()
        cfg["iso_cache_dir"] = self._iso_edit.text()
        cfg["vm_data_dir"]   = self._vm_edit.text()
        config.save_config(cfg)
        InfoBar.success(
            "Saved",
            "Settings saved. Restart the app for changes to take effect.",
            duration=4000,
            position=InfoBarPosition.TOP_RIGHT,
            parent=self.window(),
        )
