"""
ui/pages/iso_manager_page.py
ISO Manager — full-featured local ISO library page.

Layout:
  Title + subtitle + "Add ISO" button
  ── Summary row (Downloaded / Importing / Mounted / Errors) ──
  ── Search + category filter ──
  ── Drop zone ──
  ── ISO card grid ──
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, QThread, pyqtSignal, QTimer
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy,
    QFileDialog, QDialog
)
from qfluentwidgets import (
    ScrollArea, TitleLabel, SubtitleLabel, BodyLabel, CaptionLabel,
    StrongBodyLabel, CardWidget, FluentIcon as FIF,
    PrimaryPushButton, PushButton, SearchLineEdit,
    ComboBox, InfoBar, InfoBarPosition, FlowLayout,
    MessageBox, ProgressBar
)

from backend.iso_service       import ISOService
from backend.machines_db       import MachinesDB
from backend.vm_service        import VMService
from ui.components.iso_card      import ISOCard
from ui.components.iso_drop_zone import ISODropZone


# ── Background import worker ──────────────────────────────────────────────────

class ISOImportWorker(QThread):
    progress = pyqtSignal(int)    # 0-100
    finished = pyqtSignal(object) # ISORecord
    error    = pyqtSignal(str)

    def __init__(self, iso_service: ISOService, source_path: str, parent=None):
        super().__init__(parent)
        self.iso_service = iso_service
        self.source_path = source_path
        self._cancelled  = False

    def cancel(self): self._cancelled = True

    def run(self):
        try:
            rec = self.iso_service.import_iso(
                self.source_path,
                progress_callback = self.progress.emit,
                cancel_check      = lambda: self._cancelled,
            )
            self.finished.emit(rec)
        except InterruptedError:
            self.error.emit("Import cancelled.")
        except Exception as e:
            self.error.emit(str(e))


# ── Mount VM picker dialog ────────────────────────────────────────────────────

class _MountDialog(QDialog):
    """Simple dialog to pick a VM name to mount the ISO to."""

    def __init__(self, vm_names: list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Mount ISO to VM")
        self.setMinimumWidth(360)
        self._selected = None

        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 24, 24, 24)
        lay.setSpacing(14)

        lay.addWidget(SubtitleLabel("Select a Virtual Machine"))
        lay.addWidget(CaptionLabel("The ISO will be attached to the selected VM's DVD drive."))

        self._combo = ComboBox()
        if vm_names:
            self._combo.addItems(vm_names)
        else:
            self._combo.addItem("(No VMs registered)")
        lay.addWidget(self._combo)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        cancel = PushButton(FIF.CLOSE, "Cancel")
        ok     = PrimaryPushButton(FIF.LINK, "Mount")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self._accept)
        btn_row.addStretch()
        btn_row.addWidget(cancel)
        btn_row.addWidget(ok)
        lay.addLayout(btn_row)

    def _accept(self):
        self._selected = self._combo.currentText()
        self.accept()

    def selected_vm(self) -> str:
        return self._selected or ""


# ── Summary card ──────────────────────────────────────────────────────────────

class _SummaryCard(CardWidget):
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
        ic.setStyleSheet(f"font-size: 20px; color: {color};")
        lbl = CaptionLabel(label)
        lbl.setStyleSheet("color: rgba(255,255,255,0.5);")
        top.addWidget(ic); top.addSpacing(6); top.addWidget(lbl); top.addStretch()
        lay.addLayout(top)

        self._val = TitleLabel("0")
        self._val.setStyleSheet(f"font-size: 24px; font-weight: 800; color: {color};")
        lay.addWidget(self._val)

    def set_value(self, v: int): self._val.setText(str(v))


# ── ISO Manager page ──────────────────────────────────────────────────────────

class ISOManagerPage(ScrollArea):
    vm_launched = pyqtSignal(str)   # emitted → app.py switches to Console

    def __init__(
        self,
        iso_service:  ISOService,
        machines_db:  MachinesDB,
        vm_service:   VMService,
        parent=None,
    ):
        super().__init__(parent=parent)
        self.iso_service  = iso_service
        self.machines_db  = machines_db
        self.vm_service   = vm_service
        self._cards: dict[str, ISOCard] = {}
        self._workers: list = []

        self.setObjectName("ISOManagerPage")
        self.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        container.setObjectName("ISOContainer")
        self.setWidget(container)
        self.setWidgetResizable(True)

        root = QVBoxLayout(container)
        root.setContentsMargins(32, 32, 32, 32)
        root.setSpacing(24)

        # ── Title row ──
        title_row = QHBoxLayout()
        left_text = QVBoxLayout(); left_text.setSpacing(4)
        left_text.addWidget(TitleLabel("ISO Manager"))
        sub = BodyLabel("Manage your operating system images and installation media.")
        sub.setStyleSheet("color: rgba(255,255,255,0.5);")
        left_text.addWidget(sub)
        title_row.addLayout(left_text)
        title_row.addStretch()

        add_btn = PrimaryPushButton(FIF.FOLDER_ADD, "Add ISO")
        add_btn.setFixedHeight(38)
        add_btn.clicked.connect(self._browse_iso)
        title_row.addWidget(add_btn)
        root.addLayout(title_row)

        # ── Summary cards ──
        self._card_downloaded = _SummaryCard("💾", "Downloaded", "#22c55e")
        self._card_importing  = _SummaryCard("⬇️", "Importing",  "#60a5fa")
        self._card_mounted    = _SummaryCard("🔌", "Mounted",    "#a78bfa")
        self._card_errors     = _SummaryCard("⚠️", "Errors",     "#ef4444")

        summary_row = QHBoxLayout()
        summary_row.setSpacing(14)
        for c in (self._card_downloaded, self._card_importing,
                  self._card_mounted, self._card_errors):
            summary_row.addWidget(c)
        root.addLayout(summary_row)

        # ── Search + filter row ──
        filter_row = QHBoxLayout()
        filter_row.setSpacing(12)

        self._search = SearchLineEdit()
        self._search.setPlaceholderText("Search ISO files…")
        self._search.setFixedHeight(36)
        self._search.textChanged.connect(self._apply_filter)

        self._cat_filter = ComboBox()
        self._cat_filter.addItems(["All", "Linux", "Windows", "Security", "Utility", "Custom"])
        self._cat_filter.setFixedHeight(36)
        self._cat_filter.currentTextChanged.connect(self._apply_filter)

        filter_row.addWidget(self._search, stretch=1)
        filter_row.addWidget(self._cat_filter)
        root.addLayout(filter_row)

        # ── Drop zone ──
        self._drop_zone = ISODropZone()
        self._drop_zone.file_dropped.connect(self._begin_import)
        self._drop_zone.invalid_file.connect(self._on_invalid)
        root.addWidget(self._drop_zone)

        # ── Import progress bar (hidden until active) ──
        self._prog_card  = CardWidget()
        self._prog_card.setBorderRadius(12)
        prog_lay = QVBoxLayout(self._prog_card)
        prog_lay.setContentsMargins(20, 14, 20, 14)
        prog_lay.setSpacing(6)
        self._prog_lbl   = BodyLabel("Importing…")
        self._prog_lbl.setStyleSheet("color: #60a5fa;")
        self._prog_bar   = ProgressBar()
        self._prog_bar.setRange(0, 100)

        cancel_btn = PushButton(FIF.CLOSE, "Cancel")
        cancel_btn.setFixedHeight(28)
        cancel_btn.clicked.connect(self._cancel_import)
        phdr = QHBoxLayout()
        phdr.addWidget(self._prog_lbl, stretch=1)
        phdr.addWidget(cancel_btn)
        prog_lay.addLayout(phdr)
        prog_lay.addWidget(self._prog_bar)
        self._prog_card.hide()
        root.addWidget(self._prog_card)

        # ── ISO card grid ──
        self._grid_wrap = QWidget()
        self._grid = FlowLayout(self._grid_wrap)
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(16)
        self._grid.setVerticalSpacing(16)
        root.addWidget(self._grid_wrap)

        self._empty_lbl = SubtitleLabel(
            "No ISO images yet.\n"
            "Drag-and-drop an ISO or click 'Add ISO' to get started."
        )
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color: rgba(255,255,255,0.3); margin: 40px 0;")
        root.addWidget(self._empty_lbl)

        root.addStretch()

        # Initial load
        QTimer.singleShot(100, self.refresh)

    # ── Import flow ───────────────────────────────────────────────────────────

    def _browse_iso(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Select ISO / IMG file", "",
            "Disk Images (*.iso *.img *.dmg);;All Files (*.*)"
        )
        if path:
            self._begin_import(path)

    def _begin_import(self, path: str):
        self._prog_lbl.setText(f"Importing  {os.path.basename(path)}…")
        self._prog_bar.setValue(0)
        self._prog_card.show()

        worker = ISOImportWorker(self.iso_service, path, parent=self)
        worker.progress.connect(self._prog_bar.setValue)
        worker.finished.connect(self._on_import_done)
        worker.error.connect(self._on_import_error)
        self._workers.append(worker)
        worker.start()

    def _cancel_import(self):
        for w in self._workers:
            if hasattr(w, "cancel"):
                w.cancel()

    def _on_import_done(self, rec):
        self._prog_card.hide()
        self._workers = [w for w in self._workers if w.isRunning()]
        self.refresh()
        InfoBar.success(
            "ISO Imported",
            f"'{rec.name}' added to your library.",
            duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
        )

    def _on_import_error(self, msg: str):
        self._prog_card.hide()
        self._workers = [w for w in self._workers if w.isRunning()]
        InfoBar.error(
            "Import Failed", msg[:280],
            duration=7000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
        )

    def _on_invalid(self, reason: str):
        InfoBar.warning(
            "Unsupported File", reason,
            duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
        )

    # ── Card actions ──────────────────────────────────────────────────────────

    def _handle_action(self, iso_id: str, action: str):
        if action == "mount":
            self._mount_iso(iso_id)
        elif action == "unmount":
            self._unmount_iso(iso_id)
        elif action == "create_vm":
            self._create_vm_from_iso(iso_id)
        elif action == "attach":
            self._attach_to_vm(iso_id)
        elif action == "delete":
            self._delete_iso(iso_id)
        elif action == "details":
            self._show_details(iso_id)

    def _mount_iso(self, iso_id: str):
        vms = [r.vm_name for r in self.machines_db.all()]
        dlg = _MountDialog(vms, parent=self.window())
        if dlg.exec_() and dlg.selected_vm():
            vm_name = dlg.selected_vm()
            try:
                self.iso_service.mount_to_vm(iso_id, vm_name)
                self.refresh()
                InfoBar.success(
                    "ISO Mounted",
                    f"Attached to VM '{vm_name}'.\nNow click 'Create VM' on the card to boot from it.",
                    duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
                )
            except Exception as e:
                InfoBar.error(
                    "Mount Failed", str(e)[:250],
                    duration=6000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
                )

    def _create_vm_from_iso(self, iso_id: str):
        """Open the Create VM wizard for this ISO."""
        rec = self.iso_service.repo.get(iso_id)
        if not rec:
            return
        from ui.dialogs.create_vm_from_iso_dialog import CreateVMFromISODialog
        dlg = CreateVMFromISODialog(
            iso_record   = rec,
            vm_service   = self.vm_service,
            machines_db  = self.machines_db,
            parent       = self.window(),
        )
        dlg.vm_created.connect(self._on_vm_created)
        dlg.exec_()

    def _on_vm_created(self, vm_name: str):
        """VM was created and started — navigate to Console."""
        self.refresh()
        InfoBar.success(
            "VM Launched! 🚀",
            f"'{vm_name}' is booting from ISO. Switching to Console…",
            duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
        )
        self.vm_launched.emit(vm_name)

    def _attach_to_vm(self, iso_id: str):
        """Reattach this ISO to a (possibly different) existing VM."""
        rec = self.iso_service.repo.get(iso_id)
        if not rec:
            return
        vms = [r.vm_name for r in self.machines_db.all()]
        dlg = _MountDialog(vms, parent=self.window())
        dlg.setWindowTitle("Attach ISO to VM")
        if dlg.exec_() and dlg.selected_vm():
            vm_name = dlg.selected_vm()
            # Detach from current VM first if different
            if rec.mounted_to_vm and rec.mounted_to_vm != vm_name:
                try:
                    self.iso_service.unmount_from_vm(iso_id)
                except Exception:
                    pass
            try:
                self.iso_service.mount_to_vm(iso_id, vm_name)
                self.refresh()
                InfoBar.success(
                    "ISO Attached",
                    f"ISO re-attached to VM '{vm_name}'.",
                    duration=4000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
                )
            except Exception as e:
                InfoBar.error(
                    "Attach Failed", str(e)[:250],
                    duration=6000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
                )

    def _unmount_iso(self, iso_id: str):
        rec = self.iso_service.iso_service_repo_get(iso_id) if hasattr(
            self.iso_service, "iso_service_repo_get"
        ) else self.iso_service.repo.get(iso_id)
        vm = rec.mounted_to_vm if rec else "?"
        dlg = MessageBox(
            "Unmount ISO",
            f"Detach ISO from VM '{vm}'?",
            self.window()
        )
        if dlg.exec_():
            try:
                self.iso_service.unmount_from_vm(iso_id)
                self.refresh()
                InfoBar.success(
                    "ISO Unmounted", "DVD drive cleared.",
                    duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
                )
            except Exception as e:
                InfoBar.error("Unmount Failed", str(e)[:250],
                              duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _delete_iso(self, iso_id: str):
        dlg = MessageBox(
            "Delete ISO",
            "Remove this ISO from the library?\nThe file on disk will also be deleted.",
            self.window()
        )
        if dlg.exec_():
            try:
                self.iso_service.delete_iso(iso_id, delete_file=True)
                self.refresh()
                InfoBar.success(
                    "ISO Removed", "Deleted from library.",
                    duration=3000, position=InfoBarPosition.TOP_RIGHT, parent=self.window()
                )
            except Exception as e:
                InfoBar.error("Delete Failed", str(e)[:250],
                              duration=5000, position=InfoBarPosition.TOP_RIGHT, parent=self.window())

    def _show_details(self, iso_id: str):
        rec = self.iso_service.repo.get(iso_id)
        if not rec:
            return
        from backend.iso_validator import format_size
        text = (
            f"Name:       {rec.name}\n"
            f"Vendor:     {rec.vendor}\n"
            f"Category:   {rec.category}\n"
            f"Size:       {format_size(rec.file_size)}\n"
            f"Type:       {rec.file_type}\n"
            f"Added:      {rec.added_date}\n"
            f"Status:     {rec.status}\n"
            f"Mounted to: {rec.mounted_to_vm or '—'}\n"
            f"Path:       {rec.file_path}"
        )
        dlg = MessageBox("ISO Details", text, self.window())
        dlg.exec_()

    # ── Filter + Refresh ─────────────────────────────────────────────────────

    def _apply_filter(self):
        self.refresh()

    def refresh(self):
        query = self._search.text().strip() if hasattr(self._search, "text") else ""
        cat   = self._cat_filter.currentText() if hasattr(self._cat_filter, "currentText") else "All"
        isos  = self.iso_service.search(query, cat)

        # Clear grid
        while self._grid.count():
            item = self._grid.takeAt(0)
            if item:
                w = item.widget() if hasattr(item, "widget") else item
                if w:
                    w.deleteLater()
        self._cards.clear()

        self._empty_lbl.setVisible(len(isos) == 0)

        for rec in isos:
            card = ISOCard(rec)
            card.action_requested.connect(self._handle_action)
            self._cards[rec.id] = card
            self._grid.addWidget(card)

        # Update summary
        counts = self.iso_service.counts()
        self._card_downloaded.set_value(counts.get("downloaded", 0))
        self._card_importing.set_value(counts.get("importing",   0))
        self._card_mounted.set_value(counts.get("mounted",       0))
        self._card_errors.set_value(counts.get("error",          0))
