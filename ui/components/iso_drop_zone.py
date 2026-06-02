"""
ui/components/iso_drop_zone.py
Drag-and-drop + Browse ISO upload zone for the ISO Manager page.

Behavior:
  • Accepts .iso .img .dmg files by drag-and-drop or Browse button
  • Visual highlight on hover
  • Emits  file_dropped(str path)  on valid drop / selection
  • Emits  invalid_file(str reason)  on rejected files
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from PyQt5.QtCore    import Qt, pyqtSignal, QMimeData
from PyQt5.QtGui     import QDragEnterEvent, QDropEvent, QColor
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QFileDialog,
    QLabel, QSizePolicy, QGraphicsDropShadowEffect
)
from qfluentwidgets import PrimaryPushButton, PushButton, FluentIcon as FIF, BodyLabel, CaptionLabel

ACCEPTED_EXTENSIONS = {".iso", ".img", ".dmg"}


class ISODropZone(QWidget):
    """
    Large upload zone widget.  Emits file_dropped(path) on success.
    """
    file_dropped   = pyqtSignal(str)   # valid file path
    invalid_file   = pyqtSignal(str)   # rejection reason

    _STYLE_NORMAL = """
        QWidget#ISODropZone {
            background: rgba(30, 30, 46, 0.6);
            border: 2px dashed rgba(255, 255, 255, 0.12);
            border-radius: 16px;
        }
    """
    _STYLE_HOVER = """
        QWidget#ISODropZone {
            background: rgba(59, 130, 246, 0.08);
            border: 2px dashed #3b82f6;
            border-radius: 16px;
        }
    """
    _STYLE_ACCEPT = """
        QWidget#ISODropZone {
            background: rgba(34, 197, 94, 0.08);
            border: 2px dashed #22c55e;
            border-radius: 16px;
        }
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ISODropZone")
        self.setAcceptDrops(True)
        self.setFixedHeight(180)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setStyleSheet(self._STYLE_NORMAL)

        lay = QVBoxLayout(self)
        lay.setAlignment(Qt.AlignCenter)
        lay.setSpacing(10)

        icon = QLabel("📀")
        icon.setStyleSheet("font-size: 42px; background: transparent; border: none;")
        icon.setAlignment(Qt.AlignCenter)

        title = BodyLabel("Drag & Drop ISO files here")
        title.setStyleSheet(
            "font-size: 14px; font-weight: 600; color: rgba(255,255,255,0.75);"
            "background: transparent; border: none;"
        )
        title.setAlignment(Qt.AlignCenter)

        sub = CaptionLabel("Supported formats: .iso  .img  .dmg")
        sub.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent; border: none;")
        sub.setAlignment(Qt.AlignCenter)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)

        browse_btn = PrimaryPushButton(FIF.FOLDER_ADD, "Browse Files")
        browse_btn.setFixedHeight(36)
        browse_btn.clicked.connect(self._browse)

        btn_row.addStretch()
        btn_row.addWidget(browse_btn)
        btn_row.addStretch()

        lay.addWidget(icon)
        lay.addWidget(title)
        lay.addWidget(sub)
        lay.addLayout(btn_row)

    # ── Drag handlers ─────────────────────────────────────────────────────────

    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            paths = [u.toLocalFile() for u in event.mimeData().urls()]
            if any(p.lower().endswith(tuple(ACCEPTED_EXTENSIONS)) for p in paths):
                event.acceptProposedAction()
                self.setStyleSheet(self._STYLE_HOVER)
                return
        event.ignore()

    def dragLeaveEvent(self, event):
        self.setStyleSheet(self._STYLE_NORMAL)

    def dropEvent(self, event: QDropEvent):
        self.setStyleSheet(self._STYLE_NORMAL)
        paths = [u.toLocalFile() for u in event.mimeData().urls()]
        for path in paths:
            ext = os.path.splitext(path)[1].lower()
            if ext in ACCEPTED_EXTENSIONS:
                self.setStyleSheet(self._STYLE_ACCEPT)
                self.file_dropped.emit(path)
            else:
                self.invalid_file.emit(
                    f"'{os.path.basename(path)}' is not a supported image format."
                )

    # ── Browse ────────────────────────────────────────────────────────────────

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select ISO / IMG file",
            "",
            "Disk Images (*.iso *.img *.dmg);;All Files (*.*)",
        )
        if path:
            ext = os.path.splitext(path)[1].lower()
            if ext in ACCEPTED_EXTENSIONS:
                self.file_dropped.emit(path)
            else:
                self.invalid_file.emit(
                    f"'{os.path.basename(path)}' is not a supported image format."
                )
