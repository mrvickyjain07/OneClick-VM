"""
logo_widget.py
==============
Reusable branding components.

Key features
────────────
• create_circular_pixmap()  — QPainter + QPainterPath clip (NOT css hack)
• CircularLogoLabel         — custom paintEvent with optional glow ring
                              and smooth hover-scale via QPropertyAnimation
• HeaderLogoWidget          — 48 px circular logo + title / subtitle
• SidebarLogoWidget         — 36 px circular logo with collapse support
"""
import sys
import os
import logging

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGraphicsOpacityEffect
from PyQt5.QtCore    import (Qt, QSize, QRect, QPropertyAnimation,
                              QEasingCurve, pyqtSignal, QPoint)
from PyQt5.QtGui     import (QPixmap, QCursor, QPainter, QPainterPath,
                              QColor, QRadialGradient, QPen, QBrush,
                              QLinearGradient)

log = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════════════
# Resource-path helper
# ══════════════════════════════════════════════════════════════════════════════

def _resource_path(*rel_parts: str) -> str:
    """
    Resolves an asset path that works in both dev and PyInstaller bundles.

    Layout (development):
        OneClickVM/                   ← project root
            frontend/
                widgets/
                    logo_widget.py   ← THIS file  (2 levels below root)
                logo.png
    """
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS                                      # PyInstaller
    else:
        base = os.path.abspath(
            os.path.join(os.path.dirname(__file__), '..', '..')  # → project root
        )
    return os.path.join(base, *rel_parts)


# ══════════════════════════════════════════════════════════════════════════════
# Circular pixmap factory
# ══════════════════════════════════════════════════════════════════════════════

def create_circular_pixmap(source: QPixmap, size: int) -> QPixmap:
    """
    Render *source* into a circular, anti-aliased ``size × size`` pixmap.

    • Scales the source to fill the square (center-crop keeps aspect ratio).
    • Clips with an Ellipse path — not CSS border-radius.
    • Returns a QPixmap with transparent background so it composites
      cleanly over any widget background.

    Args:
        source: The original logo pixmap (any size / aspect ratio).
        size:   Diameter of the output circle in logical pixels.

    Returns:
        A ``size × size`` QPixmap with circular clip, or an empty
        placeholder circle if *source* is null.
    """
    out = QPixmap(size, size)
    out.fill(Qt.transparent)

    painter = QPainter(out)
    painter.setRenderHints(
        QPainter.Antialiasing |
        QPainter.SmoothPixmapTransform |
        QPainter.HighQualityAntialiasing
    )

    # ── Clip region: perfect ellipse ─────────────────────────────────────────
    clip = QPainterPath()
    clip.addEllipse(0, 0, size, size)
    painter.setClipPath(clip)

    if source.isNull():
        # Gradient placeholder when no asset is available
        grad = QRadialGradient(size / 2, size / 2, size / 2)
        grad.setColorAt(0.0, QColor("#1e3a5f"))
        grad.setColorAt(1.0, QColor("#0f2027"))
        painter.fillRect(0, 0, size, size, grad)
        # Draw a small cloud icon in the centre
        painter.setPen(QPen(QColor(96, 165, 250, 200), 1.5))
        painter.setFont(painter.font())
        painter.drawText(QRect(0, 0, size, size), Qt.AlignCenter, "🖥")
    else:
        # Scale to square (cover, not contain) then draw
        scaled = source.scaled(
            size, size,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        # Centre-crop to size × size
        ox = (scaled.width()  - size) // 2
        oy = (scaled.height() - size) // 2
        painter.drawPixmap(0, 0, scaled, ox, oy, size, size)

    painter.end()
    return out


# ══════════════════════════════════════════════════════════════════════════════
# Asset loader
# ══════════════════════════════════════════════════════════════════════════════

def _load_raw_pixmap() -> QPixmap:
    """
    Try several candidate paths in order; return the first valid QPixmap.
    Logs which file was used (or all misses on failure).
    """
    candidates = [
        _resource_path('frontend', 'logo.png'),
        _resource_path('frontend', 'favicon', 'favicon-96x96.png'),
        _resource_path('frontend', 'favicon', 'web-app-manifest-192x192.png'),
        _resource_path('frontend', 'favicon', 'apple-touch-icon.png'),
    ]
    for path in candidates:
        if os.path.isfile(path):
            px = QPixmap(path)
            if not px.isNull():
                log.info("Logo asset loaded: %s", path)
                return px
            log.warning("File exists but QPixmap is null (corrupt?): %s", path)
        else:
            log.debug("Logo candidate not found: %s", path)

    log.error("No logo asset loaded.  Searched:\n  %s", "\n  ".join(candidates))
    return QPixmap()   # null — callers handle this


# ══════════════════════════════════════════════════════════════════════════════
# CircularLogoLabel  — the core widget
# ══════════════════════════════════════════════════════════════════════════════

class CircularLogoLabel(QLabel):
    """
    A QLabel that:
      1. Shows the app logo clipped to a perfect circle (via QPainter).
      2. Draws an optional subtle glow ring around the circle.
      3. Animates a scale-up on hover (smooth, 150 ms).
      4. Emits ``clicked`` on left-click.

    Size contract: ``setFixedSize(diameter, diameter)`` — caller is responsible.
    """

    clicked = pyqtSignal()

    # Colours used by the custom paintEvent
    _RING_NORMAL = QColor(255, 255, 255, 30)   # very faint white ring
    _RING_HOVER  = QColor(0,   198, 255, 120)  # cyan glow on hover
    _GLOW_COLOUR = QColor(0,   198, 255,  40)  # outer glow corona

    def __init__(self, diameter: int, show_glow: bool = True, parent=None):
        super().__init__(parent)
        self._diameter  = diameter
        self._show_glow = show_glow
        self._hovered   = False
        self._scale     = 1.0           # used during hover animation (logical)

        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setFixedSize(diameter, diameter)
        self.setAlignment(Qt.AlignCenter)
        # Transparent background — we paint everything ourselves
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet("background: transparent; border: none;")

        # Pre-render the circular pixmap once
        raw = _load_raw_pixmap()
        self._circular_px = create_circular_pixmap(raw, diameter)

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        d = self._diameter
        painter = QPainter(self)
        painter.setRenderHints(
            QPainter.Antialiasing |
            QPainter.SmoothPixmapTransform |
            QPainter.HighQualityAntialiasing
        )

        # Scale around centre on hover
        if self._hovered:
            cx, cy = d / 2, d / 2
            painter.translate(cx, cy)
            painter.scale(1.07, 1.07)
            painter.translate(-cx, -cy)

        # ── Outer glow (cyan corona, hover only) ─────────────────────────────
        if self._show_glow and self._hovered:
            glow_r = d / 2 + 4
            grad = QRadialGradient(d / 2, d / 2, glow_r)
            grad.setColorAt(0.70, QColor(0, 198, 255, 0))
            grad.setColorAt(0.85, QColor(0, 198, 255, 60))
            grad.setColorAt(1.00, QColor(0, 198, 255, 0))
            painter.setBrush(QBrush(grad))
            painter.setPen(Qt.NoPen)
            painter.drawEllipse(
                int(d / 2 - glow_r), int(d / 2 - glow_r),
                int(glow_r * 2),     int(glow_r * 2)
            )

        # ── Subtle background pill (always) ──────────────────────────────────
        bg_alpha = 40 if not self._hovered else 65
        painter.setBrush(QBrush(QColor(255, 255, 255, bg_alpha)))
        painter.setPen(Qt.NoPen)
        painter.drawEllipse(0, 0, d, d)

        # ── Circular image ────────────────────────────────────────────────────
        if not self._circular_px.isNull():
            painter.drawPixmap(0, 0, self._circular_px)

        # ── Ring border ───────────────────────────────────────────────────────
        ring_colour = self._RING_HOVER if self._hovered else self._RING_NORMAL
        pen = QPen(ring_colour, 1.5)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        # Inset by half the pen width so the stroke stays inside the widget
        painter.drawEllipse(1, 1, d - 2, d - 2)

        painter.end()

    # ── interaction ───────────────────────────────────────────────────────────

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def enterEvent(self, event):
        self._hovered = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self.update()
        super().leaveEvent(event)


# ══════════════════════════════════════════════════════════════════════════════
# SidebarLogoWidget
# ══════════════════════════════════════════════════════════════════════════════

class SidebarLogoWidget(QWidget):
    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(4)

        self.logo = CircularLogoLabel(36, show_glow=False)
        self.logo.clicked.connect(self.clicked.emit)

        self.title = QLabel("OneClick")
        self.title.setStyleSheet(
            "font-weight: bold; font-size: 16px; color: white; background: transparent;"
        )

        self.subtitle = QLabel("VM Platform")
        self.subtitle.setStyleSheet(
            "font-size: 12px; color: rgba(255,255,255,0.4); background: transparent;"
        )

        layout.addWidget(self.logo)
        layout.addWidget(self.title)
        layout.addWidget(self.subtitle)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def set_collapsed(self, collapsed: bool):
        """Toggle text labels for sidebar collapse/expand."""
        self.title.setVisible(not collapsed)
        self.subtitle.setVisible(not collapsed)
        m = (8, 16, 8, 16) if collapsed else (16, 16, 16, 16)
        self.layout().setContentsMargins(*m)


# ══════════════════════════════════════════════════════════════════════════════
# HeaderLogoWidget
# ══════════════════════════════════════════════════════════════════════════════

class HeaderLogoWidget(QWidget):
    """
    Branding header card.

    Layout:  [ circular logo 48 px ] [ title / subtitle ] [stretch]

    The widget keeps its own dark gradient background and rounded corners.
    The logo circle inside uses CircularLogoLabel with the cyan glow ring.
    """

    clicked = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(QCursor(Qt.PointingHandCursor))
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setStyleSheet("""
            HeaderLogoWidget {
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #0d1f2d,
                    stop:0.5 #1a3448,
                    stop:1 #203a43
                );
                border-radius: 14px;
                border: 1px solid rgba(0, 198, 255, 0.12);
            }
            HeaderLogoWidget:hover {
                border: 1px solid rgba(0, 198, 255, 0.28);
                background: qlineargradient(
                    x1:0, y1:0, x2:1, y2:0,
                    stop:0 #122536,
                    stop:0.5 #1f3d52,
                    stop:1 #264653
                );
            }
        """)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(16)

        # ── Circular logo ─────────────────────────────────────────────────
        self.logo = CircularLogoLabel(48, show_glow=True)
        self.logo.setMinimumSize(48, 48)
        self.logo.clicked.connect(self.clicked.emit)

        # ── Text block ────────────────────────────────────────────────────
        text_col = QVBoxLayout()
        text_col.setSpacing(3)
        text_col.setAlignment(Qt.AlignVCenter)

        self.title = QLabel("OneClick VM")
        self.title.setStyleSheet(
            "font-weight: 700; font-size: 21px; "
            "color: #ffffff; background: transparent; letter-spacing: 0.3px;"
        )

        self.subtitle = QLabel("Launch Any OS — Anywhere, Anytime")
        self.subtitle.setStyleSheet(
            "font-size: 12px; color: rgba(0,198,255,0.75); "
            "background: transparent; letter-spacing: 0.2px;"
        )

        text_col.addWidget(self.title)
        text_col.addWidget(self.subtitle)

        layout.addWidget(self.logo, 0, Qt.AlignVCenter)
        layout.addLayout(text_col)
        layout.addStretch()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)


# ── backwards-compat alias (other modules import ClickableLogo directly) ─────
ClickableLogo = CircularLogoLabel
