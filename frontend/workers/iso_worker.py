import os
import requests
from PyQt5.QtCore import QThread, pyqtSignal

class DownloadWorker(QThread):
    """
    Background worker for downloading ISO files without blocking the UI thread.
    Emits progress updates during the download.
    """
    progress = pyqtSignal(int)
    success = pyqtSignal()
    error = pyqtSignal(str)

    def __init__(self, url: str, output_path: str, parent=None):
        super().__init__(parent)
        self.url = url
        self.output_path = output_path

    def run(self):
        try:
            # First ensure the parent directory exists
            os.makedirs(os.path.dirname(self.output_path), exist_ok=True)
            
            with requests.get(self.url, stream=True, timeout=10) as r:
                r.raise_for_status()
                total_size = int(r.headers.get('content-length', 0))
                downloaded = 0
                
                with open(self.output_path, 'wb') as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        if not chunk: 
                            continue
                        f.write(chunk)
                        downloaded += len(chunk)
                        if total_size > 0:
                            percent = int(downloaded * 100 / total_size)
                            self.progress.emit(percent)
                            
            self.success.emit()
        except Exception as e:
            # If download fails, try to clean up the partial file
            try:
                if os.path.exists(self.output_path):
                    os.remove(self.output_path)
            except Exception:
                pass
            self.error.emit(str(e))
