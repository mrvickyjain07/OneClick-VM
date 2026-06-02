"""
vm_action_worker.py
===================
Generic QThread worker for all VM lifecycle operations.
Decouples long-running VBoxManage calls from the UI thread.
"""
from PyQt5.QtCore import QThread, pyqtSignal
from typing import Callable


class VMActionWorker(QThread):
    """
    Runs any callable in a background thread.

    Signals:
        success(message): emitted on successful completion
        error(message):   emitted if an exception is raised
    """
    success = pyqtSignal(str)
    error   = pyqtSignal(str)

    def __init__(self, action_fn: Callable, success_msg: str, parent=None):
        super().__init__(parent)
        self._action_fn   = action_fn
        self._success_msg = success_msg

    def run(self):
        try:
            self._action_fn()
            self.success.emit(self._success_msg)
        except Exception as exc:
            self.error.emit(str(exc))
