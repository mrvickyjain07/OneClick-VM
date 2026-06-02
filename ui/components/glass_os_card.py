"""
ui/components/glass_os_card.py
Premium glassmorphism OS card — unified component for all Marketplace sections.

Modes
-----
  "default"  — standard discovery card (280 × 290)
  "featured" — larger featured card   (340 × 350)  with star badge + stronger glow
"""
import sys, os
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..")))

from pathlib import Path
from PyQt5.QtCore  import Qt, QRect, QRectF, pyqtSignal
from PyQt5.QtWidgets import QWidget, QLabel
from PyQt5.QtGui   import (
    QPainter, QPixmap, QColor, QLinearGradient,
    QPainterPath, QFont, QFontMetrics, QPen,
)


# ── Path resolver (dev + PyInstaller) ─────────────────────────────────────────

def _resolve_image(rel_path: str) -> QPixmap:
    if not rel_path:
        return QPixmap()
    if getattr(sys, "frozen", False):
        root = Path(sys._MEIPASS)          # type: ignore[attr-defined]
    else:
        root = Path(__file__).resolve().parent.parent.parent
    full = root / rel_path
    if full.exists():
        px = QPixmap(str(full))
        return px if not px.isNull() else QPixmap()
    return QPixmap()


# ── Constants ────────────────────────────────────────────────────────────────

DIFF_COLORS = {
    "Easy":   "#22c55e",
    "Medium": "#f59e0b",
    "Hard":   "#ef4444",
    "Expert": "#a855f7",
}

RADIUS = 14

# Per-mode geometry
_MODE_CFG = {
    "default":  dict(card_w=280, card_h=290, img_h=120, title_pt=13, desc_pt=10, tag_pt=8),
    "featured": dict(card_w=340, card_h=350, img_h=160, title_pt=15, desc_pt=11, tag_pt=9),
}


# ── Unified Card ──────────────────────────────────────────────────────────────

class GlassOsCard(QWidget):
    """
    Premium glass-effect OS card (QPainter-rendered).

    Parameters
    ----------
    item : dict
        Keys: os_name, desc, tags, difficulty, accent, image_path
    mode : "default" | "featured"
        Controls card size, image height, font sizes, and badge style.

    Signals
    -------
    install_clicked(item_dict)
    """
    install_clicked = pyqtSignal(dict)

    def __init__(self, item: dict, mode: str = "default", parent=None):
        super().__init__(parent)
        self.item  = item
        self.mode  = mode
        self._cfg  = _MODE_CFG.get(mode, _MODE_CFG["default"])
        self._px   = _resolve_image(item.get("image_path", ""))
        self._hover = False

        cw = self._cfg["card_w"]
        ch = self._cfg["card_h"]

        self.setFixedSize(cw, ch)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_StyledBackground, False)
        self.setMouseTracking(True)

        # ── Install button (real QLabel child — catches mouse) ───────────────
        accent = item.get("accent", "#3b82f6")
        btn_label = "★  Install VM" if mode == "featured" else "⬇  Install"
        self._btn = QLabel(btn_label, self)
        self._btn.setAlignment(Qt.AlignCenter)
        self._btn.setFixedHeight(38 if mode == "featured" else 34)
        self._btn.setFixedWidth(cw - 32)
        self._btn.move(16, ch - (38 if mode == "featured" else 34) - 12)
        self._btn.setStyleSheet(
            f"background:{accent};color:#fff;border-radius:10px;"
            f"font-size:{'14' if mode == 'featured' else '13'}px;font-weight:700;"
        )
        self._btn.mousePressEvent = lambda _e: self.install_clicked.emit(self.item)
        self._btn.setCursor(Qt.PointingHandCursor)

    # ── Paint ─────────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        cfg    = self._cfg
        cw, ch = self.width(), self.height()
        img_h  = cfg["img_h"]
        accent = QColor(self.item.get("accent", "#3b82f6"))

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        p.setRenderHint(QPainter.SmoothPixmapTransform)

        # Hover scale transform (featured only)
        if self._hover and self.mode == "featured":
            scale = 1.02
            cx, cy = cw / 2, ch / 2
            p.translate(cx, cy)
            p.scale(scale, scale)
            p.translate(-cx, -cy)

        # ── Full card clip ────────────────────────────────────────────────────
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, cw, ch), RADIUS, RADIUS)
        p.setClipPath(clip)

        # ── Glass background ──────────────────────────────────────────────────
        p.fillRect(0, 0, cw, ch, QColor(18, 22, 30, 230))

        # ── Featured: subtle accent strip at top ──────────────────────────────
        if self.mode == "featured":
            strip = QLinearGradient(0, 0, cw, 0)
            strip.setColorAt(0.0, QColor(accent.red(), accent.green(), accent.blue(), 80))
            strip.setColorAt(0.5, QColor(accent.red(), accent.green(), accent.blue(), 30))
            strip.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 80))
            p.fillRect(0, 0, cw, 3, strip)

        # ── Image fill ────────────────────────────────────────────────────────
        if not self._px.isNull():
            scaled = self._px.scaled(
                cw, img_h, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation
            )
            ox = (scaled.width() - cw) // 2
            oy = (scaled.height() - img_h) // 2
            p.drawPixmap(QRect(0, 0, cw, img_h), scaled, QRect(ox, oy, cw, img_h))
            # Gradient fade image → body
            grad = QLinearGradient(0, 0, 0, img_h)
            grad.setColorAt(0.0, QColor(0, 0, 0, 0))
            grad.setColorAt(0.55, QColor(12, 15, 22, 100))
            grad.setColorAt(1.0, QColor(12, 15, 22, 240))
            p.fillRect(0, 0, cw, img_h, grad)
        else:
            # Fallback gradient
            fb = QLinearGradient(0, 0, cw, img_h)
            fb.setColorAt(0.0, QColor(20, 26, 40))
            fb.setColorAt(1.0, QColor(accent.red(), accent.green(), accent.blue(), 60))
            p.fillRect(0, 0, cw, img_h, fb)

        # ── Featured badge (top-left) ─────────────────────────────────────────
        if self.mode == "featured":
            badge_text = "★  Featured"
            badge_col  = QColor(accent.red(), accent.green(), accent.blue(), 210)
            b_rect = QRectF(10, 10, 90, 24)
            p.setBrush(badge_col)
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(b_rect, 12, 12)
            p.setPen(QColor("#fff"))
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            p.drawText(b_rect, Qt.AlignCenter, badge_text)

        # ── Difficulty badge (top-right) ──────────────────────────────────────
        diff = self.item.get("difficulty", "")
        if diff:
            dc = QColor(DIFF_COLORS.get(diff, "#64748b"))
            d_rect = QRectF(cw - 82, 10, 70, 22)
            p.setBrush(QColor(dc.red(), dc.green(), dc.blue(), 200))
            p.setPen(Qt.NoPen)
            p.drawRoundedRect(d_rect, 11, 11)
            p.setPen(QColor("#fff"))
            p.setFont(QFont("Segoe UI", 9, QFont.Bold))
            p.drawText(d_rect, Qt.AlignCenter, diff)

        p.setClipping(False)

        # ── Separator ─────────────────────────────────────────────────────────
        p.setPen(QPen(QColor(255, 255, 255, 20)))
        p.drawLine(0, img_h, cw, img_h)

        # ── OS Name ───────────────────────────────────────────────────────────
        name_pt = cfg["title_pt"]
        p.setFont(QFont("Segoe UI", name_pt, QFont.Bold))
        p.setPen(QColor("#ffffff"))
        p.drawText(QRectF(14, img_h + 10, cw - 28, name_pt + 10),
                   Qt.AlignLeft | Qt.AlignVCenter,
                   self.item.get("os_name", ""))

        # ── Description ───────────────────────────────────────────────────────
        desc_pt = cfg["desc_pt"]
        desc_font = QFont("Segoe UI", desc_pt)
        p.setFont(desc_font)
        p.setPen(QColor(180, 185, 200, 200))
        desc_y  = img_h + 10 + name_pt + 14
        desc_h  = (desc_pt + 4) * (3 if self.mode == "featured" else 2)
        p.drawText(QRectF(14, desc_y, cw - 28, desc_h),
                   Qt.AlignLeft | Qt.AlignTop | Qt.TextWordWrap,
                   self.item.get("desc", ""))

        # ── Tags ─────────────────────────────────────────────────────────────
        tags_str = self.item.get("tags", "")
        if tags_str:
            tags    = [t.strip() for t in tags_str.split(",") if t.strip()]
            tag_pt  = cfg["tag_pt"]
            tag_font = QFont("Segoe UI", tag_pt, QFont.Medium)
            p.setFont(tag_font)
            tm   = QFontMetrics(tag_font)
            tx   = 14
            ty   = desc_y + desc_h + 6
            for tag in tags[:3]:
                tw = tm.horizontalAdvance(tag) + 16
                tr = QRectF(tx, ty, tw, 18)
                p.setBrush(QColor(accent.red(), accent.green(), accent.blue(), 40))
                p.setPen(QPen(QColor(accent.red(), accent.green(), accent.blue(), 100)))
                p.drawRoundedRect(tr, 9, 9)
                p.setPen(accent.lighter(140))
                p.drawText(tr, Qt.AlignCenter, tag)
                tx += tw + 6

        # ── Glass border ─────────────────────────────────────────────────────
        if self._hover:
            bw    = 2.0 if self.mode == "featured" else 1.5
            bcol  = QColor(accent.red(), accent.green(), accent.blue(),
                           180 if self.mode == "featured" else 120)
        else:
            bw   = 1.2
            bcol = QColor(255, 255, 255, 40)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(bcol, bw))
        border = QPainterPath()
        border.addRoundedRect(QRectF(bw/2, bw/2, cw - bw, ch - bw), RADIUS, RADIUS)
        p.drawPath(border)

        # ── Hover tint ────────────────────────────────────────────────────────
        if self._hover:
            alpha = 20 if self.mode == "featured" else 12
            p.fillRect(0, 0, cw, ch, QColor(accent.red(), accent.green(), accent.blue(), alpha))

        p.end()

    # ── Mouse events ─────────────────────────────────────────────────────────

    def enterEvent(self, _e):
        self._hover = True
        self.update()

    def leaveEvent(self, _e):
        self._hover = False
        self.update()
