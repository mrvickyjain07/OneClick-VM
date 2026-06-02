"""
ui/dialogs/take_snapshot_dialog.py
Modal dialog for taking a VM snapshot.

Inputs:
  - VM selector (pre-filled if vm_name passed)
  - Snapshot name
  - Description
  - Include live memory checkbox
"""
import sys, os, uuid
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, pyqtSignal
from PyQt5.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QFrame,
    QCheckBox, QLabel
)

from qfluentwidgets import (
    TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel, StrongBodyLabel,
    PrimaryPushButton, PushButton, LineEdit, ComboBox, TextEdit,
    FluentIcon as FIF, CardWidget, InfoBar, InfoBarPosition
)


class TakeSnapshotDialog(QDialog):
    """
    Emits:
      snapshot_requested(vm_name, snap_name, description, live)
    """
    snapshot_requested = pyqtSignal(str, str, str, bool)

    def __init__(self, vm_names: list, preselect_vm: str = "", parent=None):
        super().__init__(parent)
        self.setWindowTitle("Take Snapshot")
        self.setModal(True)
        self.setMinimumWidth(480)
        self.setStyleSheet("QDialog { background: #13131f; } QLabel { background: transparent; border: none; }")

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 28)
        root.setSpacing(18)

        # ── Header ──
        hdr = QHBoxLayout()
        hdr.setSpacing(14)
        icon = QLabel("📸")
        icon.setStyleSheet("font-size: 34px;")
        icon.setFixedSize(50, 50)
        icon.setAlignment(Qt.AlignCenter)
        text = QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(TitleLabel("Take Snapshot"))
        sub = CaptionLabel("Save the current VM state for instant rollback later.")
        sub.setStyleSheet("color: rgba(255,255,255,0.4);")
        text.addWidget(sub)
        hdr.addWidget(icon)
        hdr.addLayout(text)
        hdr.addStretch()
        root.addLayout(hdr)
        root.addWidget(self._hr())

        # ── VM selector ──
        vm_row = self._row("Virtual Machine")
        self._vm_combo = ComboBox()
        self._vm_combo.addItems(vm_names if vm_names else ["(No VMs)"])
        if preselect_vm and preselect_vm in vm_names:
            self._vm_combo.setCurrentText(preselect_vm)
        vm_row.addWidget(self._vm_combo, stretch=1)
        root.addLayout(vm_row)

        # ── Snapshot name ──
        name_row = self._row("Snapshot Name *")
        self._name_edit = LineEdit()
        self._name_edit.setText(f"Snapshot-{uuid.uuid4().hex[:6].upper()}")
        self._name_edit.setPlaceholderText("e.g.  Before-Update  /  Clean-Install")
        name_row.addWidget(self._name_edit, stretch=1)
        root.addLayout(name_row)

        # ── Description ──
        root.addWidget(self._field_label("Description (optional)"))
        self._desc_edit = TextEdit()
        self._desc_edit.setPlaceholderText("What does this snapshot capture?")
        self._desc_edit.setFixedHeight(72)
        self._desc_edit.setStyleSheet(
            "TextEdit { background: rgba(255,255,255,0.04); border: 1px solid rgba(255,255,255,0.1);"
            "border-radius: 8px; color: #f1f5f9; padding: 8px; }"
        )
        root.addWidget(self._desc_edit)

        # ── Live memory checkbox ──
        self._live_cb = QCheckBox("Include live memory state (live snapshot — VM keeps running)")
        self._live_cb.setStyleSheet(
            "QCheckBox { color: rgba(255,255,255,0.7); font-size: 12px; }"
            "QCheckBox::indicator { width:16px; height:16px; border-radius:4px; "
            "border: 1px solid rgba(255,255,255,0.25); background: rgba(255,255,255,0.05); }"
            "QCheckBox::indicator:checked { background: #3b82f6; border-color: #3b82f6; }"
        )
        self._live_cb.setChecked(True)

        note_card = CardWidget()
        note_card.setBorderRadius(10)
        note_card.setStyleSheet(
            "CardWidget { background: rgba(96,165,250,0.06); border: 1px solid rgba(96,165,250,0.2); }"
        )
        note_lay = QVBoxLayout(note_card)
        note_lay.setContentsMargins(14, 10, 14, 10)
        note_lay.setSpacing(4)
        note_lay.addWidget(self._live_cb)
        note = CaptionLabel(
            "✅ Live = VM stays running, RAM state saved (resume to exact screen).\n"
            "⬜ Non-live = VM pauses briefly, then resumes (no RAM state saved)."
        )
        note.setStyleSheet("color: rgba(255,255,255,0.4); font-size: 10px;")
        note_lay.addWidget(note)
        root.addWidget(note_card)

        root.addWidget(self._hr())

        # ── Buttons ──
        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel = PushButton(FIF.CLOSE, "Cancel")
        cancel.setFixedHeight(38)
        cancel.clicked.connect(self.reject)
        take = PrimaryPushButton(FIF.SAVE, "Take Snapshot")
        take.setFixedHeight(38)
        take.clicked.connect(self._on_take)
        btn_row.addWidget(cancel)
        btn_row.addStretch()
        btn_row.addWidget(take)
        root.addLayout(btn_row)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _hr(self) -> QFrame:
        f = QFrame(); f.setFrameShape(QFrame.HLine)
        f.setStyleSheet("color: rgba(255,255,255,0.07);")
        return f

    def _field_label(self, text: str) -> CaptionLabel:
        l = CaptionLabel(text)
        l.setStyleSheet("color: rgba(255,255,255,0.5); font-size: 11px;")
        return l

    def _row(self, label_text: str) -> QHBoxLayout:
        lay = QHBoxLayout()
        lay.setSpacing(10)
        lbl = self._field_label(label_text)
        lbl.setFixedWidth(130)
        lay.addWidget(lbl)
        return lay

    def _on_take(self):
        vm   = self._vm_combo.currentText().strip()
        name = self._name_edit.text().strip()
        desc = self._desc_edit.toPlainText().strip()
        live = self._live_cb.isChecked()

        if not vm or vm.startswith("(No"):
            InfoBar.warning("No VM selected", "Please select a virtual machine.",
                            duration=3000, position=InfoBarPosition.TOP, parent=self)
            return
        if not name:
            InfoBar.warning("Name required", "Please enter a snapshot name.",
                            duration=3000, position=InfoBarPosition.TOP, parent=self)
            return

        self.snapshot_requested.emit(vm, name, desc, live)
        self.accept()
