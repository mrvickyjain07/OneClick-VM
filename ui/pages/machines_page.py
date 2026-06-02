"""
ui/pages/machines_page.py
My Machines: installed VM instances only. Completely separate from Marketplace.

Section 4 & 5 fixes:
  • VM start uses VMStartWorker (async, headless support, pre-state-check).
  • VM stop uses VMStopWorker (async, UUID-first).
  • Buttons disabled while a VM action is running (prevents double-start).
  • State updates go through vm_state_manager (single source of truth).
  • notify() used for all toast messages.
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy
from qfluentwidgets import (
    ScrollArea, TitleLabel, BodyLabel, SubtitleLabel, FlowLayout,
    PrimaryPushButton, MessageBox, FluentIcon as FIF
)

from models import VMRecord, VMStatus
from ui.components.machine_card import MachineCard
from ui.workers import VMStartWorker, VMStopWorker, VMActionWorker
from ui.notification_manager import notify
from ui.state_manager import vm_state_manager


class MachinesPage(ScrollArea):
    vm_launched        = pyqtSignal(str)   # emitted with vm_name when a VM starts
    snapshot_requested = pyqtSignal(str)   # emitted → SnapshotsPage.take_snapshot_for_vm

    def __init__(self, vm_service, machines_db, parent=None):
        super().__init__(parent=parent)
        self.vm_service  = vm_service
        self.machines_db = machines_db
        self.setObjectName("MachinesPage")
        self.setStyleSheet("background: transparent; border: none;")

        self._cards:   dict[str, MachineCard] = {}
        self._workers: list = []

        container = QWidget()
        container.setObjectName("MchContainer")
        self.setWidget(container)
        self.setWidgetResizable(True)

        self._root = QVBoxLayout(container)
        self._root.setContentsMargins(32, 32, 32, 32)
        self._root.setSpacing(24)

        # ── Header ──
        header_row = QHBoxLayout()
        left = QVBoxLayout()
        left.setSpacing(4)
        left.addWidget(TitleLabel("My Machines"))
        sub = BodyLabel("Your installed virtual machines. Launch, stop or delete from here.")
        sub.setStyleSheet("color: rgba(255,255,255,0.55);")
        left.addWidget(sub)
        header_row.addLayout(left)
        header_row.addStretch()

        self._refresh_btn = PrimaryPushButton(FIF.SYNC, "Refresh")
        self._refresh_btn.setFixedHeight(36)
        self._refresh_btn.clicked.connect(self.refresh)
        header_row.addWidget(self._refresh_btn)
        self._root.addLayout(header_row)

        # ── Grid ──
        self._grid = FlowLayout()
        self._grid.setContentsMargins(0, 0, 0, 0)
        self._grid.setHorizontalSpacing(20)
        self._grid.setVerticalSpacing(20)
        self._root.addLayout(self._grid)

        self._empty_lbl = SubtitleLabel(
            "No virtual machines installed yet.\n"
            "Head to the Marketplace to download and install one."
        )
        self._empty_lbl.setAlignment(Qt.AlignCenter)
        self._empty_lbl.setStyleSheet("color: rgba(255,255,255,0.35);")
        self._root.addWidget(self._empty_lbl)

        self._root.addStretch()

        # Subscribe to centralized state changes for real-time card updates
        vm_state_manager.busy_changed.connect(self._on_vm_busy_changed)
        vm_state_manager.state_changed.connect(self._on_vm_state_changed)

        QTimer.singleShot(300, self.refresh)

    # ── Refresh ───────────────────────────────────────────────────────────────

    def refresh(self):
        """Reload machine list from DB and rebuild cards."""
        records = self.machines_db.all()
        self._empty_lbl.setVisible(len(records) == 0)

        current_vms = {rec.vm_name for rec in records}
        existing_vms = set(self._cards.keys())

        # Remove obsolete cards
        for vm_name in existing_vms - current_vms:
            card = self._cards.pop(vm_name)
            self._grid.removeWidget(card)
            card.deleteLater()

        for rec in records:
            vm_name = rec.vm_name
            # Use centralized state if available, otherwise fall back to live query
            state_str = vm_state_manager.get_state(vm_name)
            if state_str == "unknown":
                live = self.vm_service.get_live_status(vm_name)
                self.machines_db.update_status(vm_name, live)
                rec.status = live
            else:
                rec.status = VMStatus(state_str) if state_str in ("running", "stopped") else VMStatus.UNKNOWN

            if vm_name in self._cards:
                self._cards[vm_name].update_status(rec.status)
            else:
                card = MachineCard(rec)
                card.action_requested.connect(self._handle_action)
                self._cards[vm_name] = card
                self._grid.addWidget(card)
                # Register in state manager so poller updates propagate
                vm_state_manager.register(vm_name, str(rec.status))

    # ── Action handler ────────────────────────────────────────────────────────

    def _handle_action(self, vm_name: str, action: str):
        # Prevent double-execution while an action is already running
        if vm_state_manager.is_busy(vm_name):
            notify.warning("Busy", f"'{vm_name}' is already busy.", parent=self.window())
            return

        if action == "start":
            self._start_vm(vm_name)
        elif action == "stop":
            self._stop_vm(vm_name)
        elif action == "snapshot":
            self.snapshot_requested.emit(vm_name)
        elif action == "delete":
            dlg = MessageBox(
                "Delete VM",
                f"Permanently delete '{vm_name}'?\nThis cannot be undone.",
                self.window(),
            )
            if dlg.exec():
                self._delete_vm(vm_name)

    # ── Start VM (Section 4 optimised) ────────────────────────────────────────

    def _start_vm(self, vm_name: str):
        """Launch VM via async VMStartWorker — no UI freeze, pre-checks state."""
        card = self._cards.get(vm_name)
        if card:
            card.set_busy(True)

        # Pass cached state so VMStartWorker skips redundant VBox call
        cached = vm_state_manager.get_state(vm_name)

        w = VMStartWorker(
            vm_service   = self.vm_service,
            vm_name      = vm_name,
            headless     = False,          # set True for background-only VMs
            cached_state = cached,
            parent       = self,
        )
        w.stage.connect(lambda msg: None)  # stage msgs go to state mgr
        w.finished.connect(lambda name, w=w: self._on_start_ok(name, w))
        w.error.connect(lambda err, w=w: self._on_err(vm_name, err, w))
        self._workers.append(w)
        w.start()

    def _on_start_ok(self, vm_name: str, worker):
        self._workers_remove(worker)
        notify.success(f"VM Started ✅", f"'{vm_name}' is now running.", parent=self.window())
        self.vm_launched.emit(vm_name)

    # ── Stop VM ───────────────────────────────────────────────────────────────

    def _stop_vm(self, vm_name: str):
        """Stop VM via async VMStopWorker."""
        card = self._cards.get(vm_name)
        if card:
            card.set_busy(True)

        w = VMStopWorker(
            vm_service = self.vm_service,
            vm_name    = vm_name,
            force      = False,
            parent     = self,
        )
        w.finished.connect(lambda name, w=w: self._on_stop_ok(name, w))
        w.error.connect(lambda err, w=w: self._on_err(vm_name, err, w))
        self._workers.append(w)
        w.start()

    def _on_stop_ok(self, vm_name: str, worker):
        self._workers_remove(worker)
        notify.success(f"VM Stopped", f"'{vm_name}' has been powered off.", parent=self.window())

    # ── Delete VM ─────────────────────────────────────────────────────────────

    def _delete_vm(self, vm_name: str):
        card = self._cards.get(vm_name)
        if card:
            card.set_busy(True)

        w = VMActionWorker(
            fn=lambda: self.vm_service.delete_vm(vm_name),
            success_msg=f"'{vm_name}' deleted.",
            parent=self,
        )
        w.finished.connect(lambda msg, w=w: self._on_delete_ok(vm_name, msg, w))
        w.error.connect(lambda err, w=w: self._on_err(vm_name, err, w))
        self._workers.append(w)
        w.start()

    def _on_delete_ok(self, vm_name, msg, worker):
        self._workers_remove(worker)
        vm_state_manager.unregister(vm_name)
        notify.success("VM Deleted", msg, parent=self.window())
        self.refresh()

    # ── Error handler ─────────────────────────────────────────────────────────

    def _on_err(self, vm_name, err, worker):
        self._workers_remove(worker)
        notify.error("Error", err[:300], parent=self.window())

    # ── Central state manager callbacks ───────────────────────────────────────

    def _on_vm_busy_changed(self, vm_name: str, is_busy: bool):
        """Called by vm_state_manager — update card busy indicator."""
        card = self._cards.get(vm_name)
        if card:
            try:
                card.set_busy(is_busy)
            except RuntimeError:
                pass

    def _on_vm_state_changed(self, vm_name: str, new_state: str):
        """Called by vm_state_manager — update card status badge."""
        card = self._cards.get(vm_name)
        if card:
            try:
                st = VMStatus(new_state) if new_state in ("running", "stopped") else VMStatus.UNKNOWN
                card.update_status(st)
            except (RuntimeError, ValueError):
                pass

    # ── Worker registry ───────────────────────────────────────────────────────

    def _workers_remove(self, w):
        if w in self._workers:
            self._workers.remove(w)
