"""
install_worker.py
=================
QThread worker for the full VM installation pipeline.
Wraps backend.installer.Installer and relays all signals to the UI.
"""
from PyQt5.QtCore import QThread, pyqtSignal
from backend.installer import Installer


class InstallWorker(QThread):
    """
    Runs a full VM install in a background thread.

    Signals:
        progress_update(dict): progress data from ISOManager download
        log_update(str):       log message to append to the console
        finished(dict):        result dict with 'success', 'vm_name', 'message'
        error(str):            raised exception message
    """
    progress_update = pyqtSignal(dict)
    log_update      = pyqtSignal(str)
    finished        = pyqtSignal(dict)
    error           = pyqtSignal(str)

    def __init__(self, os_id: str, ram_mb: int = None,
                 cpu_count: int = None, disk_gb: int = None, parent=None):
        super().__init__(parent)
        self.os_id     = os_id
        self.ram_mb    = ram_mb
        self.cpu_count = cpu_count
        self.disk_gb   = disk_gb
        self._installer = Installer()
        self.is_paused = False

    def run(self):
        try:
            kwargs = dict(
                progress_callback=self.progress_update.emit,
                log_callback=self.log_update.emit,
                pause_check_callback=lambda: self.is_paused
            )
            # Pass overrides only if provided (None → Installer uses template defaults)
            if self.ram_mb    is not None: kwargs["ram_mb"]    = self.ram_mb
            if self.cpu_count is not None: kwargs["cpu_count"] = self.cpu_count
            if self.disk_gb   is not None: kwargs["disk_gb"]   = self.disk_gb

            result = self._installer.install_os(self.os_id, **kwargs)
            self.finished.emit(result)
        except Exception as exc:
            self.error.emit(str(exc))
