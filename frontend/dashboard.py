from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
    QLabel, QMessageBox, QListWidgetItem
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from backend.vm_registry import VMRegistry
from backend.vbox_engine import VBoxEngine


class VMActionWorker(QThread):
    """Runs a VBoxManage action in a background thread to avoid blocking the UI."""
    success_signal = pyqtSignal(str)   # success message
    error_signal = pyqtSignal(str)     # error message

    def __init__(self, action_fn, success_msg):
        super().__init__()
        self._action_fn = action_fn
        self._success_msg = success_msg

    def run(self):
        try:
            self._action_fn()
            self.success_signal.emit(self._success_msg)
        except Exception as e:
            self.error_signal.emit(str(e))


class Dashboard(QWidget):
    def __init__(self):
        super().__init__()
        self.registry = VMRegistry()
        self.vbox = VBoxEngine()
        self._worker = None  # keep reference to avoid GC
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()

        # Header
        header = QLabel("Active Virtual Machines")
        header.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(header)

        # List
        self.vm_list = QListWidget()
        layout.addWidget(self.vm_list)

        # Status label
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("color: gray; font-style: italic;")
        layout.addWidget(self.status_label)

        # Buttons
        btn_layout = QHBoxLayout()
        self.btn_refresh = QPushButton("Refresh")
        self.btn_start = QPushButton("Start")
        self.btn_stop = QPushButton("Stop")
        self.btn_delete = QPushButton("Delete")

        btn_layout.addWidget(self.btn_refresh)
        btn_layout.addWidget(self.btn_start)
        btn_layout.addWidget(self.btn_stop)
        btn_layout.addWidget(self.btn_delete)
        layout.addLayout(btn_layout)

        # Connections
        self.btn_refresh.clicked.connect(self.refresh_list)
        self.btn_start.clicked.connect(self.start_vm)
        self.btn_stop.clicked.connect(self.stop_vm)
        self.btn_delete.clicked.connect(self.delete_vm)

        self.setLayout(layout)
        self.refresh_list()

    def refresh_list(self):
        self.vm_list.clear()
        vms = self.registry.list_vms()
        for vm in vms:
            # Try to get live state from VirtualBox
            live_state = None
            try:
                live_state = self.vbox.get_vm_state(vm['vm_name'])
            except Exception:
                pass
            display_state = live_state if live_state else vm.get('status', 'Unknown')
            item_text = f"{vm['vm_name']} ({vm['os_id']}) - {display_state}"
            item = QListWidgetItem(item_text)
            item.setData(Qt.UserRole, vm['vm_name'])
            self.vm_list.addItem(item)

    def get_selected_vm(self):
        item = self.vm_list.currentItem()
        if item:
            return item.data(Qt.UserRole)
        return None

    def _set_buttons_enabled(self, enabled):
        self.btn_start.setEnabled(enabled)
        self.btn_stop.setEnabled(enabled)
        self.btn_delete.setEnabled(enabled)
        self.btn_refresh.setEnabled(enabled)

    def _run_action(self, action_fn, busy_msg, success_msg):
        """Runs a VM action in a QThread so the UI stays responsive."""
        self._set_buttons_enabled(False)
        self.status_label.setText(busy_msg)

        self._worker = VMActionWorker(action_fn, success_msg)
        self._worker.success_signal.connect(self._on_action_success)
        self._worker.error_signal.connect(self._on_action_error)
        self._worker.start()

    def _on_action_success(self, msg):
        self._set_buttons_enabled(True)
        self.status_label.setText("")
        QMessageBox.information(self, "Success", msg)
        self.refresh_list()

    def _on_action_error(self, error_msg):
        self._set_buttons_enabled(True)
        self.status_label.setText("")
        QMessageBox.critical(self, "Error", error_msg)

    def start_vm(self):
        vm_name = self.get_selected_vm()
        if not vm_name:
            QMessageBox.warning(self, "No Selection", "Please select a VM first.")
            return
        self._run_action(
            lambda: self.vbox.start_vm(vm_name),
            f"Starting {vm_name}...",
            f"Started {vm_name} successfully."
        )

    def stop_vm(self):
        vm_name = self.get_selected_vm()
        if not vm_name:
            QMessageBox.warning(self, "No Selection", "Please select a VM first.")
            return
        self._run_action(
            lambda: self.vbox.poweroff_vm(vm_name),
            f"Stopping {vm_name}...",
            f"Powered off {vm_name} successfully."
        )

    def delete_vm(self):
        vm_name = self.get_selected_vm()
        if not vm_name:
            QMessageBox.warning(self, "No Selection", "Please select a VM first.")
            return
        reply = QMessageBox.question(
            self, 'Delete VM',
            f"Are you sure you want to delete {vm_name}?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            def _do_delete():
                self.vbox.delete_vm(vm_name)
                self.registry.remove_vm(vm_name)
            self._run_action(
                _do_delete,
                f"Deleting {vm_name}...",
                f"Deleted {vm_name} successfully."
            )
