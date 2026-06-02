from PyQt5.QtCore import QThread, pyqtSignal
from backend.installer import Installer

class InstallWorker(QThread):
    progress_update = pyqtSignal(dict)
    log_update = pyqtSignal(str)
    finished_signal = pyqtSignal(dict)
    error_signal = pyqtSignal(str)

    def __init__(self, os_id):
        super().__init__()
        self.os_id = os_id
        self.installer = Installer()

    def run(self):
        try:
            result = self.installer.install_os(
                self.os_id,
                progress_callback=self.progress_update.emit,
                log_callback=self.log_update.emit
            )
            self.finished_signal.emit(result)
        except Exception as e:
            self.error_signal.emit(str(e))
