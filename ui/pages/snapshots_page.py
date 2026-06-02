"""
ui/pages/snapshots_page.py
Snapshots & History — full-featured snapshot management page.

Section 3 fixes applied:
  • Snapshot delete now properly calls SnapshotDeleteWorker and handles
    VMNotFoundException / orphaned records cleanly.
  • Auto-refresh after every operation (create / restore / delete / export).
  • Busy-lock prevents double-execution of any destructive action.
  • Operation progress card replaces individual spinners — single progress track.
  • "Take Snapshot" button moved to top-right action bar (high visibility).
  • Orphaned snapshot badge + auto-cleanup path.

Signals:
  vm_launched(vm_name: str)  → app.py switches to Console after restore
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QFileDialog, QLabel
)
from qfluentwidgets import (
    ScrollArea, TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel,
    StrongBodyLabel, CardWidget, FluentIcon as FIF,
    PrimaryPushButton, PushButton, SearchLineEdit, ComboBox,
    InfoBar, InfoBarPosition, ProgressBar, MessageBox
)

from backend.snapshot_service    import SnapshotService
from backend.snapshot_repository import SnapshotRecord
from ui.workers import (
    SnapshotCreateWorker, SnapshotRestoreWorker,
    SnapshotDeleteWorker, SnapshotExportWorker,
)
from ui.notification_manager import notify


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_size(b: int) -> str:
    if b <= 0:   return "—"
    if b < 1024: return f"{b} B"
    kb = b / 1024
    if kb < 1024: return f"{kb:.1f} KB"
    mb = kb / 1024
    if mb < 1024: return f"{mb:.1f} MB"
    return f"{mb / 1024:.2f} GB"


_STATUS_COLORS = {
    "completed": ("#22c55e", "rgba(34,197,94,0.12)",   "rgba(34,197,94,0.3)"),
    "creating":  ("#60a5fa", "rgba(96,165,250,0.12)",  "rgba(96,165,250,0.3)"),
    "failed":    ("#ef4444", "rgba(239,68,68,0.12)",   "rgba(239,68,68,0.3)"),
    "orphaned":  ("#f59e0b", "rgba(245,158,11,0.12)",  "rgba(245,158,11,0.3)"),
}


def _badge(status: str) -> QLabel:
    color, bg, border = _STATUS_COLORS.get(
        status, ("#9ca3af", "rgba(156,163,175,0.12)", "rgba(156,163,175,0.3)")
    )
    lbl = QLabel(status.capitalize())
    lbl.setAlignment(Qt.AlignCenter)
    lbl.setFixedHeight(22)
    lbl.setStyleSheet(
        f"color:{color}; background:{bg}; border:1px solid {border};"
        "border-radius:11px; padding:0 10px; font-size:10px; font-weight:700;"
    )
    return lbl


# ── Summary card ──────────────────────────────────────────────────────────────

class _SummCard(CardWidget):
    def __init__(self, icon, label, color="#60a5fa", parent=None):
        super().__init__(parent)
        self.setBorderRadius(12)
        self.setFixedHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 14, 18, 14)
        lay.setSpacing(4)
        top = QHBoxLayout()
        ic  = StrongBodyLabel(icon)
        ic.setStyleSheet(f"font-size:20px; color:{color};")
        lb  = CaptionLabel(label)
        lb.setStyleSheet("color:rgba(255,255,255,0.5);")
        top.addWidget(ic); top.addSpacing(6); top.addWidget(lb); top.addStretch()
        lay.addLayout(top)
        self._val = TitleLabel("0")
        self._val.setStyleSheet(f"font-size:24px; font-weight:800; color:{color};")
        lay.addWidget(self._val)

    def set_value(self, v): self._val.setText(str(v))


# ── Snapshot row card ─────────────────────────────────────────────────────────

class SnapshotRowCard(CardWidget):
    """
    Horizontal list-item card for a snapshot.
    Signals: restore_clicked(id), export_clicked(id), delete_clicked(id)
    """
    restore_clicked = pyqtSignal(str)
    export_clicked  = pyqtSignal(str)
    delete_clicked  = pyqtSignal(str)

    def __init__(self, rec: SnapshotRecord, parent=None):
        super().__init__(parent)
        self.rec = rec
        self.setBorderRadius(12)
        self.setFixedHeight(90)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet("""
            CardWidget {
                background: rgba(24,24,38,0.95);
                border: 1px solid rgba(255,255,255,0.06);
            }
            CardWidget:hover {
                border: 1px solid rgba(96,165,250,0.25);
                background: rgba(30,30,48,0.98);
            }
        """)
        self._build()

    def _build(self):
        rec = self.rec
        lay = QHBoxLayout(self)
        lay.setContentsMargins(18, 12, 14, 12)
        lay.setSpacing(14)

        # ── Camera icon ──
        ic = QLabel("📸")
        ic.setStyleSheet("font-size:26px; background:transparent; border:none;")
        ic.setFixedSize(36, 36)
        ic.setAlignment(Qt.AlignCenter)
        lay.addWidget(ic)

        # ── Name + meta ──
        info = QVBoxLayout()
        info.setSpacing(3)

        name_row = QHBoxLayout()
        name_row.setSpacing(8)
        nm = StrongBodyLabel(rec.snapshot_name[:40])
        nm.setStyleSheet("font-size:13px; font-weight:700; color:#f1f5f9;"
                         "background:transparent; border:none;")
        name_row.addWidget(nm)
        if rec.has_memory:
            ram_badge = QLabel("💾 RAM")
            ram_badge.setStyleSheet(
                "color:#a78bfa; background:rgba(167,139,250,0.12);"
                "border:1px solid rgba(167,139,250,0.3); border-radius:9px;"
                "padding:0 7px; font-size:9px; font-weight:700;"
            )
            name_row.addWidget(ram_badge)
        # Orphaned warning badge
        if rec.status == "orphaned":
            orphan_badge = QLabel("⚠ Orphaned")
            orphan_badge.setStyleSheet(
                "color:#f59e0b; background:rgba(245,158,11,0.12);"
                "border:1px solid rgba(245,158,11,0.3); border-radius:9px;"
                "padding:0 7px; font-size:9px; font-weight:700;"
            )
            name_row.addWidget(orphan_badge)
        name_row.addStretch()
        info.addLayout(name_row)

        sub_row = QHBoxLayout()
        sub_row.setSpacing(12)
        ts = rec.timestamp or ""
        for text, style in [
            (f"🖥 {rec.vm_name}",  "color:rgba(255,255,255,0.5);"),
            (f"📅 {ts[:10]}  🕐 {ts[11:16]}" if len(ts) > 15 else f"📅 {ts}",
             "color:rgba(255,255,255,0.35);"),
            (f"💾 {_fmt_size(rec.size_bytes)}",
             "color:rgba(255,255,255,0.3);"),
        ]:
            lbl = CaptionLabel(text)
            lbl.setStyleSheet(f"{style} background:transparent; border:none; font-size:10px;")
            sub_row.addWidget(lbl)
        sub_row.addStretch()

        if rec.description:
            desc = CaptionLabel(rec.description[:60] + ("…" if len(rec.description) > 60 else ""))
            desc.setStyleSheet("color:rgba(255,255,255,0.28); font-size:10px;"
                               "background:transparent; border:none;")
            info.addWidget(desc)
        info.addLayout(sub_row)
        lay.addLayout(info, stretch=1)

        # ── Status badge ──
        lay.addWidget(_badge(rec.status))

        # ── Action buttons — only for completed (not orphaned / creating) ──
        if rec.status == "completed":
            restore_btn = PrimaryPushButton(FIF.HISTORY, "Restore")
            restore_btn.setFixedHeight(30)
            restore_btn.setToolTip("Restore VM to this snapshot")
            restore_btn.clicked.connect(lambda: self.restore_clicked.emit(rec.id))
            lay.addWidget(restore_btn)

            exp_btn = PushButton(FIF.SHARE, "")
            exp_btn.setFixedSize(30, 30)
            exp_btn.setToolTip("Export VM as OVA")
            exp_btn.clicked.connect(lambda: self.export_clicked.emit(rec.id))
            lay.addWidget(exp_btn)

        # Delete always shown (handles orphaned cleanup too)
        del_btn = PushButton(FIF.DELETE, "")
        del_btn.setFixedSize(30, 30)
        del_btn.setToolTip("Delete snapshot" if rec.status != "orphaned"
                           else "Remove orphaned metadata")
        del_btn.clicked.connect(lambda: self.delete_clicked.emit(rec.id))
        lay.addWidget(del_btn)


# ── Snapshots Page ────────────────────────────────────────────────────────────

class SnapshotsPage(ScrollArea):
    vm_launched = pyqtSignal(str)   # after restore → switch to Console

    def __init__(self, snap_service: SnapshotService, parent=None):
        super().__init__(parent=parent)
        self.snap_service = snap_service
        self._workers: list = []
        self._op_busy = False       # Global op lock — prevents double-execution

        self.setObjectName("SnapshotsPage")
        self.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setObjectName("SnapContainer")
        self.setWidget(container)
        self.setWidgetResizable(True)

        root = QVBoxLayout(container)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(22)

        # ── Title row ── (Take Snapshot button in top-right action bar)
        title_row = QHBoxLayout()
        left = QVBoxLayout(); left.setSpacing(4)
        left.addWidget(TitleLabel("Snapshots & History"))
        sub = BodyLabel("Save and restore VM states — instant rollback, anytime.")
        sub.setStyleSheet("color: rgba(255,255,255,0.45);")
        left.addWidget(sub)
        title_row.addLayout(left)
        title_row.addStretch()

        # ISSUE 2 FIX: "Take Snapshot" as primary button in top-right action bar
        self._snap_btn = PrimaryPushButton(FIF.SAVE, " Take Snapshot")
        self._snap_btn.setFixedHeight(40)
        self._snap_btn.setMinimumWidth(160)
        self._snap_btn.setToolTip("Create a new VM snapshot")
        self._snap_btn.clicked.connect(self._open_take_dialog)
        title_row.addWidget(self._snap_btn)
        root.addLayout(title_row)

        # ── Summary cards ──
        self._s_total     = _SummCard("📸", "Total",     "#60a5fa")
        self._s_completed = _SummCard("✅", "Completed", "#22c55e")
        self._s_creating  = _SummCard("⏳", "Creating",  "#f59e0b")
        self._s_size      = _SummCard("💾", "Total Size", "#a78bfa")

        summ_row = QHBoxLayout()
        summ_row.setSpacing(14)
        for c in (self._s_total, self._s_completed, self._s_creating, self._s_size):
            summ_row.addWidget(c)
        root.addLayout(summ_row)

        # ── Search + VM filter ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)
        self._search = SearchLineEdit()
        self._search.setPlaceholderText("Search snapshots…")
        self._search.setFixedHeight(36)
        self._search.textChanged.connect(self.refresh)
        self._vm_filter = ComboBox()
        self._vm_filter.addItem("All VMs")
        self._vm_filter.setFixedHeight(36)
        self._vm_filter.currentTextChanged.connect(self.refresh)
        filter_row.addWidget(self._search, stretch=1)
        filter_row.addWidget(self._vm_filter)
        root.addLayout(filter_row)

        # ── Operation progress card ──
        self._op_card = CardWidget()
        self._op_card.setBorderRadius(12)
        self._op_card.setStyleSheet(
            "CardWidget { background: rgba(30,30,50,0.98);"
            "border: 1px solid rgba(96,165,250,0.2); }"
        )
        op_lay = QVBoxLayout(self._op_card)
        op_lay.setContentsMargins(18, 12, 18, 12)
        op_lay.setSpacing(6)
        op_hdr = QHBoxLayout()
        self._op_lbl = BodyLabel("Working…")
        self._op_lbl.setStyleSheet("color: #60a5fa;")
        self._op_spinner = CaptionLabel("⏳")
        self._op_spinner.setStyleSheet("font-size: 16px;")
        op_hdr.addWidget(self._op_spinner)
        op_hdr.addWidget(self._op_lbl, stretch=1)
        self._op_bar = ProgressBar()
        self._op_bar.setRange(0, 100)
        op_lay.addLayout(op_hdr)
        op_lay.addWidget(self._op_bar)
        self._op_card.hide()
        root.addWidget(self._op_card)

        # ── List area ──
        self._list_widget = QWidget()
        self._list_layout = QVBoxLayout(self._list_widget)
        self._list_layout.setContentsMargins(0, 0, 0, 0)
        self._list_layout.setSpacing(10)
        root.addWidget(self._list_widget)

        self._empty_lbl = SubtitleLabel(
            "No snapshots yet.\nClick 'Take Snapshot' to create your first save point."
        )
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color: rgba(255,255,255,0.28); margin: 50px 0;")
        root.addWidget(self._empty_lbl)

        root.addStretch()

        QTimer.singleShot(150, self._init_vm_filter)
        QTimer.singleShot(200, self.refresh)

    # ── Init ──────────────────────────────────────────────────────────────────

    def _init_vm_filter(self):
        vms = self.snap_service.vm_names()
        self._vm_filter.clear()
        self._vm_filter.addItem("All VMs")
        self._vm_filter.addItems(vms)

    # ── Busy lock helpers ─────────────────────────────────────────────────────

    def _lock(self, label: str):
        self._op_busy = True
        self._snap_btn.setEnabled(False)
        self._op_lbl.setText(label)
        self._op_bar.setValue(0)
        self._op_card.show()

    def _unlock(self):
        self._op_busy = False
        self._snap_btn.setEnabled(True)
        try:
            self._op_card.hide()
        except RuntimeError:
            pass

    # ── Take Snapshot flow ────────────────────────────────────────────────────

    def _open_take_dialog(self, preselect: str = ""):
        if self._op_busy:
            notify.warning("Busy", "Another snapshot operation is in progress.", parent=self.window())
            return
        from ui.dialogs.take_snapshot_dialog import TakeSnapshotDialog
        vms = self.snap_service.vm_names()
        dlg = TakeSnapshotDialog(vms, preselect_vm=preselect, parent=self.window())
        dlg.snapshot_requested.connect(self._begin_snapshot)
        dlg.exec_()

    def _begin_snapshot(self, vm_name: str, snap_name: str, desc: str, live: bool):
        rec = self.snap_service.begin_snapshot(vm_name, snap_name, desc, live)
        self.refresh()

        worker = SnapshotCreateWorker(self.snap_service, rec, parent=self)
        worker.stage.connect(self._op_lbl.setText)
        worker.progress.connect(self._op_bar.setValue)
        worker.finished.connect(self._on_snap_done)
        worker.error.connect(self._on_snap_error)
        self._workers.append(worker)

        self._lock(f"Creating snapshot '{snap_name}'…")
        worker.start()

    def _on_snap_done(self, rec):
        self._cleanup_workers()
        self._unlock()
        self.refresh()
        notify.success(
            "Snapshot Created! 📸",
            f"'{rec.snapshot_name}' saved for VM '{rec.vm_name}'.",
            parent=self.window(),
        )

    def _on_snap_error(self, msg: str):
        self._cleanup_workers()
        self._unlock()
        self.refresh()
        notify.error("Snapshot Failed", msg, parent=self.window())

    # ── Restore flow ──────────────────────────────────────────────────────────

    def _restore(self, snap_id: str):
        if self._op_busy:
            notify.warning("Busy", "Another operation is in progress.", parent=self.window())
            return
        rec = self.snap_service.get(snap_id)
        if not rec:
            return
        dlg = MessageBox(
            "Restore Snapshot",
            f"Restore VM '{rec.vm_name}' to snapshot:\n'{rec.snapshot_name}'?\n\n"
            "⚠  The VM will be powered off, then reverted to this save point.\n"
            "Any unsaved progress since this snapshot will be lost.",
            self.window()
        )
        if not dlg.exec_():
            return

        worker = SnapshotRestoreWorker(self.snap_service, snap_id, auto_start=True, parent=self)
        worker.stage.connect(self._op_lbl.setText)
        worker.progress.connect(self._op_bar.setValue)
        worker.finished.connect(self._on_restore_done)
        worker.error.connect(self._on_restore_error)
        self._workers.append(worker)

        self._lock(f"Restoring to '{rec.snapshot_name}'…")
        worker.start()

    def _on_restore_done(self, rec):
        self._cleanup_workers()
        self._unlock()
        self.refresh()
        notify.success(
            "Restore Complete! ⏮",
            f"VM '{rec.vm_name}' reverted to '{rec.snapshot_name}'. Switching to Console…",
            duration=6000, parent=self.window(),
        )
        try:
            self.vm_launched.emit(rec.vm_name)
        except RuntimeError:
            pass

    def _on_restore_error(self, msg: str):
        self._cleanup_workers()
        self._unlock()
        notify.error("Restore Failed", msg, parent=self.window())

    # ── Delete flow ───────────────────────────────────────────────────────────

    def _delete(self, snap_id: str):
        if self._op_busy:
            notify.warning("Busy", "Another operation is in progress.", parent=self.window())
            return
        rec = self.snap_service.get(snap_id)
        if not rec:
            notify.error("Not Found", "Snapshot record not found in database.", parent=self.window())
            return

        # For orphaned snapshots, skip confirmation — metadata-only removal
        if rec.status != "orphaned":
            dlg = MessageBox(
                "Delete Snapshot",
                f"Delete snapshot '{rec.snapshot_name}' from VM '{rec.vm_name}'?\n\n"
                "Disk changes will be merged into the parent. This cannot be undone.",
                self.window()
            )
            if not dlg.exec_():
                return

        worker = SnapshotDeleteWorker(self.snap_service, snap_id, parent=self)
        worker.stage.connect(self._op_lbl.setText)
        worker.progress.connect(self._op_bar.setValue)
        worker.finished.connect(self._on_delete_done)
        worker.error.connect(self._on_delete_error)
        self._workers.append(worker)

        label = (
            f"Removing orphaned metadata for '{rec.snapshot_name}'…"
            if rec.status == "orphaned"
            else f"Deleting '{rec.snapshot_name}' and merging disk delta…"
        )
        self._lock(label)
        worker.start()

    def _on_delete_done(self, snap_id: str):
        self._cleanup_workers()
        self._unlock()
        self.refresh()
        notify.success("Snapshot Deleted", "The snapshot has been removed.", parent=self.window())

    def _on_delete_error(self, msg: str):
        self._cleanup_workers()
        self._unlock()
        self.refresh()   # Refresh anyway — state may have changed
        notify.error("Delete Failed", msg, parent=self.window())

    # ── Export flow ───────────────────────────────────────────────────────────

    def _export(self, snap_id: str):
        if self._op_busy:
            notify.warning("Busy", "Another operation is in progress.", parent=self.window())
            return
        rec = self.snap_service.get(snap_id)
        if not rec:
            return
        out, _ = QFileDialog.getSaveFileName(
            self, f"Export '{rec.vm_name}' as OVA", f"{rec.vm_name}.ova",
            "OVA Archive (*.ova);;All Files (*.*)"
        )
        if not out:
            return

        worker = SnapshotExportWorker(self.snap_service, snap_id, out, parent=self)
        worker.stage.connect(self._op_lbl.setText)
        worker.progress.connect(self._op_bar.setValue)
        worker.finished.connect(self._on_export_done)
        worker.error.connect(self._on_export_error)
        self._workers.append(worker)

        self._lock(f"Exporting '{rec.vm_name}'…")
        worker.start()

    def _on_export_done(self, path: str):
        self._cleanup_workers()
        self._unlock()
        notify.success("Export Complete 📦", f"Saved to: {path}", duration=7000, parent=self.window())

    def _on_export_error(self, msg: str):
        self._cleanup_workers()
        self._unlock()
        notify.error("Export Failed", msg, parent=self.window())

    # ── Public API ───────────────────────────────────────────────────────────

    def take_snapshot_for_vm(self, vm_name: str):
        """Open the Take Snapshot dialog pre-filled with a specific VM."""
        self._open_take_dialog(preselect=vm_name)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        query  = self._search.text().strip()
        vm_fil = self._vm_filter.currentText()
        if vm_fil == "All VMs":
            vm_fil = "All"

        snaps = self.snap_service.search(query, vm_fil)

        # Rebuild list
        while self._list_layout.count():
            item = self._list_layout.takeAt(0)
            if item and item.widget():
                item.widget().deleteLater()

        self._empty_lbl.setVisible(len(snaps) == 0)

        for rec in snaps:
            card = SnapshotRowCard(rec)
            card.restore_clicked.connect(self._restore)
            card.export_clicked.connect(self._export)
            card.delete_clicked.connect(self._delete)
            self._list_layout.addWidget(card)

        # Summary counters
        counts = self.snap_service.counts()
        self._s_total.set_value(counts.get("total", 0))
        self._s_completed.set_value(counts.get("completed", 0))
        self._s_creating.set_value(counts.get("creating", 0))
        self._s_size.set_value(_fmt_size(counts.get("size", 0)))

    def _cleanup_workers(self):
        """Prune finished workers from the registry."""
        self._workers = [w for w in self._workers if w.isRunning()]
