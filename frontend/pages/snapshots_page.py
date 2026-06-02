"""
snapshots_page.py
=================
Phase 5: Snapshot management for virtual machines.

Features:
- VM selector dropdown
- Snapshot list per VM
- Take Snapshot button
- Restore Snapshot button
- Delete Snapshot button
- All operations run in background threads
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QComboBox, QListWidget, QListWidgetItem, QInputDialog,
    QMessageBox, QFrame
)
from PyQt5.QtCore import Qt

from backend.vm_registry import VMRegistry
from backend.vbox_engine  import VBoxEngine
from frontend.workers.vm_action_worker import VMActionWorker


class SnapshotsPage(QWidget):
    """Snapshot management page."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.registry = VMRegistry()
        self.vbox     = VBoxEngine()
        self._worker: VMActionWorker | None = None
        self._build_ui()
        self._load_vm_list()

    # ──────────────────────────────────────────────────────────────────────────
    # UI
    # ──────────────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(32, 28, 32, 28)
        root.setSpacing(16)

        title    = QLabel("Snapshots")
        title.setObjectName("PageTitle")
        subtitle = QLabel("Save and restore VM states at any point in time")
        subtitle.setObjectName("PageSubtitle")
        root.addWidget(title)
        root.addWidget(subtitle)

        # VM selector
        sel_row = QHBoxLayout()
        sel_row.setSpacing(10)
        vm_lbl = QLabel("Virtual Machine:")
        vm_lbl.setFixedWidth(130)
        self.vm_combo = QComboBox()
        self.vm_combo.setFixedHeight(34)
        self.vm_combo.currentIndexChanged.connect(self._refresh_snapshots)
        btn_refresh = QPushButton("⟳  Refresh")
        btn_refresh.clicked.connect(self._refresh_snapshots)
        sel_row.addWidget(vm_lbl)
        sel_row.addWidget(self.vm_combo, stretch=1)
        sel_row.addWidget(btn_refresh)
        root.addLayout(sel_row)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setObjectName("VMDetail")
        root.addWidget(self.status_label)

        # Snapshot list
        snap_lbl = QLabel("Snapshots")
        snap_lbl.setObjectName("SectionLabel")
        root.addWidget(snap_lbl)

        self.snap_list = QListWidget()
        self.snap_list.setStyleSheet(
            "QListWidget { background: #161B22; border: 1px solid #30363D; border-radius: 6px; }"
            "QListWidget::item { padding: 8px 12px; color: #E6EDF3; }"
            "QListWidget::item:selected { background: #21262D; color: #58A6FF; }"
            "QListWidget::item:hover { background: #21262D; }"
        )
        root.addWidget(self.snap_list, stretch=1)

        # Action buttons
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        self.btn_take = QPushButton("📸  Take Snapshot")
        self.btn_take.setObjectName("PrimaryButton")
        self.btn_take.clicked.connect(self._take_snapshot)

        self.btn_restore = QPushButton("⏮  Restore")
        self.btn_restore.clicked.connect(self._restore_snapshot)

        self.btn_delete = QPushButton("🗑  Delete Snapshot")
        self.btn_delete.setObjectName("DangerButton")
        self.btn_delete.clicked.connect(self._delete_snapshot)

        btn_row.addWidget(self.btn_take)
        btn_row.addWidget(self.btn_restore)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_delete)
        root.addLayout(btn_row)

    # ──────────────────────────────────────────────────────────────────────────
    # Data
    # ──────────────────────────────────────────────────────────────────────────

    def _load_vm_list(self):
        self.vm_combo.clear()
        for vm in self.registry.list_vms():
            self.vm_combo.addItem(vm["vm_name"], vm["vm_name"])
        self._refresh_snapshots()

    def _refresh_snapshots(self):
        self.snap_list.clear()
        vm_name = self.vm_combo.currentData()
        if not vm_name:
            return
        try:
            snapshots = self.vbox.list_snapshots(vm_name)
            if not snapshots:
                self.snap_list.addItem("  No snapshots found for this VM.")
            else:
                for snap in snapshots:
                    item = QListWidgetItem(f"  📸  {snap}")
                    item.setData(Qt.UserRole, snap)
                    self.snap_list.addItem(item)
            self.status_label.setText(f"{len(snapshots)} snapshot(s)")
        except Exception as exc:
            self.snap_list.addItem(f"  Error: {exc}")
            self.status_label.setText("")

    # ──────────────────────────────────────────────────────────────────────────
    # Actions
    # ──────────────────────────────────────────────────────────────────────────

    def _take_snapshot(self):
        vm_name = self.vm_combo.currentData()
        if not vm_name:
            QMessageBox.warning(self, "No VM", "Please select a virtual machine.")
            return
        snap_name, ok = QInputDialog.getText(
            self, "Snapshot Name", "Enter a name for this snapshot:"
        )
        if not ok or not snap_name.strip():
            return
        snap_name = snap_name.strip()
        self._run(
            lambda: self.vbox.take_snapshot(vm_name, snap_name),
            f"Taking snapshot '{snap_name}'…",
            f"Snapshot '{snap_name}' created."
        )

    def _restore_snapshot(self):
        vm_name = self.vm_combo.currentData()
        snap_name = self._selected_snapshot()
        if not snap_name:
            QMessageBox.warning(self, "No Snapshot Selected", "Please select a snapshot to restore.")
            return
        reply = QMessageBox.question(
            self, "Restore Snapshot",
            f"Restore VM '{vm_name}' to snapshot '{snap_name}'?\n"
            "The current state will be discarded.",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._run(
                lambda: self.vbox.restore_snapshot(vm_name, snap_name),
                f"Restoring '{snap_name}'…",
                f"Restored to snapshot '{snap_name}'."
            )

    def _delete_snapshot(self):
        vm_name = self.vm_combo.currentData()
        snap_name = self._selected_snapshot()
        if not snap_name:
            QMessageBox.warning(self, "No Snapshot Selected", "Please select a snapshot to delete.")
            return
        reply = QMessageBox.question(
            self, "Delete Snapshot",
            f"Delete snapshot '{snap_name}' from '{vm_name}'?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._run(
                lambda: self.vbox.delete_snapshot(vm_name, snap_name),
                f"Deleting snapshot '{snap_name}'…",
                f"Snapshot '{snap_name}' deleted."
            )

    def _selected_snapshot(self) -> str | None:
        item = self.snap_list.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def _run(self, fn, busy_msg: str, success_msg: str):
        self.status_label.setText(busy_msg)
        self._set_enabled(False)
        self._worker = VMActionWorker(fn, success_msg)
        self._worker.success.connect(self._on_success)
        self._worker.error.connect(self._on_error)
        self._worker.start()

    def _on_success(self, msg: str):
        self._set_enabled(True)
        self.status_label.setText(msg)
        self._refresh_snapshots()

    def _on_error(self, err: str):
        self._set_enabled(True)
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", err)

    def _set_enabled(self, enabled: bool):
        self.btn_take.setEnabled(enabled)
        self.btn_restore.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)
        self.vm_combo.setEnabled(enabled)

    def refresh_vm_list(self):
        """Called from MainWindow when a new VM is created."""
        self._load_vm_list()
