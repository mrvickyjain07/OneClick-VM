"""
fluent_snapshots.py
====================
Snapshot management — Fluent edition.
Take, restore, delete snapshots per VM.
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor

from qfluentwidgets import (
    ScrollArea, CardWidget,
    TitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton,
    ComboBox, FluentIcon as FIF,
    MessageBox, InfoBar, InfoBarPosition,
    MessageBoxBase, SubtitleLabel, LineEdit
)

from backend.vm_registry import VMRegistry
from backend.vbox_engine  import VBoxEngine
from frontend.workers.vm_action_worker import VMActionWorker


class InputDialog(MessageBoxBase):
    """Custom input dialog for snapshot names using MessageBoxBase."""
    def __init__(self, title, placeholder, parent=None):
        super().__init__(parent)
        self.titleLabel = SubtitleLabel(title)
        self.lineEdit = LineEdit()
        self.lineEdit.setPlaceholderText(placeholder)
        self.lineEdit.setClearButtonEnabled(True)

        # add to viewLayout
        self.viewLayout.addWidget(self.titleLabel)
        self.viewLayout.addWidget(self.lineEdit)

        self.widget.setMinimumWidth(350)
        self.lineEdit.setFocus()

    def get_text(self):
        return self.lineEdit.text()



class SnapshotsPage(ScrollArea):
    """Snapshot management page — Fluent edition."""

    def __init__(self, parent=None):
        super().__init__(parent=parent)
        self.setObjectName("SnapshotsPage")
        self.registry = VMRegistry()
        self.vbox     = VBoxEngine()
        self._worker: VMActionWorker | None = None

        container = QWidget()
        container.setObjectName("SnapshotsContainer")
        self.setWidget(container)
        self.setWidgetResizable(True)
        self.enableTransparentBackground()

        root = QVBoxLayout(container)
        root.setContentsMargins(36, 32, 36, 32)
        root.setSpacing(16)

        # ── Header ─────────────────────────────────────────────────────────
        root.addWidget(TitleLabel("Snapshots"))
        sub = BodyLabel("Save and restore VM states at any point in time")
        sub.setTextColor(QColor("#8B949E"), QColor("#666"))
        root.addWidget(sub)

        # ── VM selector ────────────────────────────────────────────────────
        sel_row = QHBoxLayout()
        sel_lbl = BodyLabel("Virtual Machine:")
        sel_lbl.setFixedWidth(140)
        self.vm_combo = ComboBox()
        self.vm_combo.setSizePolicy(
            __import__("PyQt5.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Expanding,
            __import__("PyQt5.QtWidgets", fromlist=["QSizePolicy"]).QSizePolicy.Fixed
        )
        self.vm_combo.currentIndexChanged.connect(self._refresh_snaps)
        btn_ref = PushButton(FIF.SYNC, "Refresh")
        btn_ref.clicked.connect(self._refresh_snaps)
        sel_row.addWidget(sel_lbl)
        sel_row.addWidget(self.vm_combo, 1)
        sel_row.addWidget(btn_ref)
        root.addLayout(sel_row)

        self.status_lbl = CaptionLabel("")
        root.addWidget(self.status_lbl)

        # ── Snapshot list card ─────────────────────────────────────────────
        list_card = CardWidget()
        list_lay  = QVBoxLayout(list_card)
        list_lay.setContentsMargins(12, 10, 12, 10)
        list_lay.setSpacing(6)
        lbl_h = CaptionLabel("SNAPSHOTS")
        lbl_h.setTextColor(QColor("#8B949E"), QColor("#666"))
        list_lay.addWidget(lbl_h)

        self.snap_list = QListWidget()
        self.snap_list.setStyleSheet("""
            QListWidget {
                background: transparent;
                border: none;
                outline: none;
            }
            QListWidget::item {
                padding: 10px 12px;
                color: #E6EDF3;
                border-radius: 6px;
            }
            QListWidget::item:selected {
                background: rgba(31,111,235,0.25);
                color: #58A6FF;
            }
            QListWidget::item:hover {
                background: rgba(255,255,255,0.05);
            }
        """)
        self.snap_list.setMinimumHeight(280)
        list_lay.addWidget(self.snap_list)
        root.addWidget(list_card, 1)

        # ── Action buttons ─────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self.btn_take    = PrimaryPushButton(FIF.CAMERA, "Take Snapshot")
        self.btn_restore = PushButton(FIF.HISTORY, "Restore")
        self.btn_delete  = PushButton(FIF.DELETE, "Delete Snapshot")

        self.btn_take.clicked.connect(self._take)
        self.btn_restore.clicked.connect(self._restore)
        self.btn_delete.clicked.connect(self._delete)

        btn_row.addWidget(self.btn_take)
        btn_row.addWidget(self.btn_restore)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_delete)
        root.addLayout(btn_row)

        self._load_vms()

    # ── Data ───────────────────────────────────────────────────────────────────

    def _load_vms(self):
        self.vm_combo.clear()
        for vm in self.registry.list_vms():
            self.vm_combo.addItem(vm["vm_name"], vm["vm_name"])
        self._refresh_snaps()

    def _refresh_snaps(self):
        self.snap_list.clear()
        name = self.vm_combo.currentData()
        if not name:
            return
        try:
            snaps = self.vbox.list_snapshots(name)
            if not snaps:
                item = QListWidgetItem("  No snapshots found for this VM.")
                item.setFlags(item.flags() & ~Qt.ItemIsEnabled)
                self.snap_list.addItem(item)
            else:
                for s in snaps:
                    it = QListWidgetItem(f"  📸  {s}")
                    it.setData(Qt.UserRole, s)
                    self.snap_list.addItem(it)
            self.status_lbl.setText(f"{len(snaps)} snapshot(s)")
        except Exception as e:
            self.snap_list.addItem(f"  Error: {e}")
            self.status_lbl.setText("")

    # ── Actions ────────────────────────────────────────────────────────────────

    def _take(self):
        name = self.vm_combo.currentData()
        if not name:
            InfoBar.warning("No VM", "Select a VM first.",
                            duration=3000, position=InfoBarPosition.TOP_RIGHT,
                            parent=self.window())
            return
        
        w = InputDialog("Snapshot Name", "Enter a name for this snapshot", self.window())
        if w.exec():
            snap_name = w.get_text()
            if not snap_name.strip():
                return
            self._run(lambda: self.vbox.take_snapshot(name, snap_name.strip()),
                      f"Taking snapshot '{snap_name}'…",
                      f"Snapshot '{snap_name}' created.")

    def _restore(self):
        name = self.vm_combo.currentData()
        snap = self._sel_snap()
        if not snap:
            InfoBar.warning("No Snapshot", "Select a snapshot to restore.",
                            duration=3000, position=InfoBarPosition.TOP_RIGHT,
                            parent=self.window())
            return
        msg = MessageBox("Restore Snapshot",
                         f"Restore '{name}' to '{snap}'?\nCurrent state will be lost.",
                         self.window())
        if msg.exec():
            self._run(lambda: self.vbox.restore_snapshot(name, snap),
                      f"Restoring '{snap}'…", f"Restored to '{snap}'.")

    def _delete(self):
        name = self.vm_combo.currentData()
        snap = self._sel_snap()
        if not snap:
            InfoBar.warning("No Snapshot", "Select a snapshot to delete.",
                            duration=3000, position=InfoBarPosition.TOP_RIGHT,
                            parent=self.window())
            return
        msg = MessageBox("Delete Snapshot", f"Delete snapshot '{snap}'?", self.window())
        if msg.exec():
            self._run(lambda: self.vbox.delete_snapshot(name, snap),
                      f"Deleting '{snap}'…", f"Snapshot '{snap}' deleted.")

    def _sel_snap(self) -> str | None:
        item = self.snap_list.currentItem()
        return item.data(Qt.UserRole) if item else None

    def _run(self, fn, busy: str, done: str):
        if not self.vbox.is_virtualbox_installed():
            self.status_lbl.setText("⚠  VirtualBox not found.")
            return
        self.status_lbl.setText(busy)
        self._set_enabled(False)
        self._worker = VMActionWorker(fn, done)
        self._worker.success.connect(lambda m: self._done(m))
        self._worker.error.connect(lambda e: self._err(e))
        self._worker.start()

    def _done(self, msg: str):
        self._set_enabled(True)
        self.status_lbl.setText(msg)
        self._refresh_snaps()

    def _err(self, err: str):
        self._set_enabled(True)
        self.status_lbl.setText("")
        InfoBar.error("Error", err[:100], duration=5000,
                      position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _set_enabled(self, v: bool):
        self.btn_take.setEnabled(v)
        self.btn_restore.setEnabled(v)
        self.btn_delete.setEnabled(v)
        self.vm_combo.setEnabled(v)

    def refresh_vm_list(self):
        self._load_vms()
