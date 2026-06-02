from PyQt5.QtWidgets import QVBoxLayout, QHBoxLayout, QWidget
from PyQt5.QtCore import Qt
from qfluentwidgets import (
    ScrollArea, CardWidget, SubtitleLabel
)

from frontend.widgets.components import ActionBar, InfoPanel

class ConsolePage(ScrollArea):
    """Console Page
    Layout:
    Top: ActionBar
    Main: Split layout -> Left (VM Display Panel), Right (InfoPanel)
    """
    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("ConsolePage")
        self.view = QWidget(self)
        self.view.setObjectName("pageContainer")
        self.setWidget(self.view)
        self.setWidgetResizable(True)
        self.setStyleSheet("background: transparent;")

        self.vBoxLayout = QVBoxLayout(self.view)
        self.vBoxLayout.setContentsMargins(24, 24, 24, 24)
        self.vBoxLayout.setSpacing(24)

        self._build_ui()

    def _build_ui(self):
        # Top: ActionBar
        self.action_bar = ActionBar(self)
        self.vBoxLayout.addWidget(self.action_bar)

        # Main: Split Layout
        self.main_h_layout = QHBoxLayout()
        self.main_h_layout.setSpacing(24)
        
        # LEFT: VM Display Panel (70%)
        self.vm_display_panel = CardWidget(self)
        self.vm_display_panel.setMinimumHeight(400)
        display_layout = QVBoxLayout(self.vm_display_panel)
        display_layout.setAlignment(Qt.AlignCenter)
        
        self.screen_lbl = SubtitleLabel("Select a VM to connect", self)
        self.screen_lbl.setAlignment(Qt.AlignCenter)
        display_layout.addWidget(self.screen_lbl)
        
        self.main_h_layout.addWidget(self.vm_display_panel, stretch=7)

        # RIGHT: InfoPanel (30%)
        self.info_panel = InfoPanel(self)
        self.main_h_layout.addWidget(self.info_panel, stretch=3)

        self.vBoxLayout.addLayout(self.main_h_layout)
        self.vBoxLayout.addStretch(1)

    def set_vm(self, vm_name):
        self.screen_lbl.setText(f"Connected to {vm_name}")
        # In a real app we'd attach a VNC/RDP widget here.
