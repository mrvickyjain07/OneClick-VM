"""
marketplace_banner.py  —  Image-Based Hero Carousel  (v3 — visibility-fixed)
==============================================================================

Root causes fixed in this version
──────────────────────────────────
1. BannerSlide now sets WA_StyledBackground + WA_OpaquePaintEvent so the
   style engine never skips its paintEvent inside a ScrollArea container.

2. MarketplaceBanner explicitly calls setCurrentIndex(0) + setMinimumHeight()
   so Qt always allocates the correct vertical space on first layout pass.

3. _crossfade() no longer parents QGraphicsOpacityEffect to the slide widget.
   Both effects are parented to the MarketplaceBanner (self) and are deleted
   via DeleteWhenStopped on the animation, eliminating the double-parent
   race condition that kept _animating = True permanently.

4. BannerDataLoader._resolve_pixmap prints a WARNING to the root logger
   (visible in the running terminal) so missing images are easy to spot.

Architecture
────────────
BannerDataLoader   Resolves image_path (relative to project root) → QPixmap.
                   Decoupled from UI for future personalisation / A-B logic.

BannerSlide        QPainter-rendered slide: real image (cover-fill) +
                   left-fade gradient overlay + text layers + CTA buttons.
                   Graceful gradient fallback when image is absent.

DotIndicator       Clickable pill/dot row; active dot animates to a wider pill.

MarketplaceBanner  QStackedWidget + DotIndicator + arrows + auto-timer.
                   Crossfade: fade-out → switch → fade-in (total ≤ 450 ms).

Extensibility hooks (stubs, ready for future use)
──────────────────────────────────────────────────
  BannerDataLoader.personalise(slides, user_ctx)  → reorder by preference
  BannerDataLoader.inject_promoted(slides, promo)  → prepend seasonal banner
  MarketplaceBanner.set_order(indices)             → runtime reorder
  BannerSlide.set_promoted(bool)                   → visual featured badge
"""
from __future__ import annotations

import sys
import logging
from pathlib import Path
from typing  import List, Optional

from PyQt5.QtWidgets import (
    QWidget, QStackedWidget, QVBoxLayout, QHBoxLayout,
    QPushButton, QSizePolicy, QGraphicsOpacityEffect
)
from PyQt5.QtCore    import (Qt, QTimer, QPropertyAnimation,
                              QEasingCurve, QRectF, pyqtSignal)
from PyQt5.QtGui     import (QPainter, QColor, QLinearGradient, QRadialGradient,
                              QBrush, QPen, QFont, QFontMetrics,
                              QPainterPath, QPixmap)

from qfluentwidgets  import PrimaryPushButton

log = logging.getLogger(__name__)

# ── project-root resolution (works dev + PyInstaller) ─────────────────────────
if getattr(sys, "frozen", False):
    _PROJECT_ROOT = Path(sys._MEIPASS)          # type: ignore[attr-defined]
else:
    # this file lives at  <root>/frontend/widgets/marketplace_banner.py
    _PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


# ══════════════════════════════════════════════════════════════════════════════
# BannerDataLoader
# ══════════════════════════════════════════════════════════════════════════════

class BannerDataLoader:
    """
    Resolves image paths and validates assets for banner slides.

    Decoupled from the widget layer so personalisation, A/B testing, or
    remote data sources can be injected by sub-classing.

    Usage
    ─────
        loader = BannerDataLoader()          # auto-detects project root
        slides = loader.load(raw_list)       # enriches with _pixmap key
    """

    def __init__(self, project_root: Optional[str | Path] = None):
        self._root = Path(project_root) if project_root else _PROJECT_ROOT

    # ── public ────────────────────────────────────────────────────────────────

    def load(self, raw: List[dict]) -> List[dict]:
        """
        Return a copy of *raw* where each entry gains a ``_pixmap`` key:
        a valid QPixmap when the image is found, or None (→ gradient fallback).
        """
        result = []
        for entry in raw:
            enriched = dict(entry)
            enriched["_pixmap"] = self._resolve_pixmap(entry.get("image_path", ""))
            result.append(enriched)
        return result

    # ── internal ──────────────────────────────────────────────────────────────

    def _resolve_pixmap(self, rel_path: str) -> Optional[QPixmap]:
        if not rel_path:
            return None
        abs_path = self._root / rel_path
        if not abs_path.is_file():
            log.warning("[BannerDataLoader] image not found: %s", abs_path)
            return None
        px = QPixmap(str(abs_path))
        if px.isNull():
            log.warning("[BannerDataLoader] image corrupt / unreadable: %s", abs_path)
            return None
        log.debug("[BannerDataLoader] loaded: %s (%dx%d)", abs_path, px.width(), px.height())
        return px

    # ── extensibility stubs ───────────────────────────────────────────────────

    def personalise(self, slides: List[dict], user_context: dict) -> List[dict]:
        """Override to reorder/filter slides per user. Default: identity."""
        return slides

    def inject_promoted(self, slides: List[dict], promoted: dict) -> List[dict]:
        """Override to prepend a seasonal/promotional slide. Default: no-op."""
        return slides


# ══════════════════════════════════════════════════════════════════════════════
# BannerSlide
# ══════════════════════════════════════════════════════════════════════════════

class BannerSlide(QWidget):
    """
    Single hero slide: image background (cover-fill) + gradient overlay +
    QPainter text layers + interactive CTA buttons as real child widgets.

    Visibility fixes applied
    ────────────────────────
    • WA_StyledBackground  — forces style engine to honour paintEvent inside
                             ScrollArea containers (qfluentwidgets-specific).
    • WA_OpaquePaintEvent  — tells Qt this widget redraws its entire area,
                             so it will never be skipped as "transparent".
    • setFixedHeight()     — guarantees nonzero vertical allocation.
    """

    install_clicked    = pyqtSignal(dict)
    learn_more_clicked = pyqtSignal(dict)

    SLIDE_H = 240   # px — public so MarketplaceBanner can read it

    _F_TITLE   = QFont("Segoe UI", 24, QFont.Bold)
    _F_TAG     = QFont("Segoe UI",  9, QFont.Bold)
    _F_TAGLINE = QFont("Segoe UI", 12)

    def __init__(self, data: dict, parent=None):
        super().__init__(parent)
        self._data   = data
        self._accent = QColor(data.get("accent",         "#00C6FF"))
        self._g0     = QColor(data.get("gradient_start", "#0f2027"))
        self._g1     = QColor(data.get("gradient_end",   "#1a3048"))
        self._px: Optional[QPixmap] = data.get("_pixmap")

        # ── visibility attributes (critical) ──────────────────────────────────
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setFixedHeight(self.SLIDE_H)

        # ── CTA buttons ───────────────────────────────────────────────────────
        primary_label   = data.get("primary_action",   "Install")
        secondary_label = data.get("secondary_action", "Learn More")

        self.btn_primary = PrimaryPushButton(f"⚡  {primary_label}")
        self.btn_primary.setFixedHeight(36)
        self.btn_primary.clicked.connect(lambda: self.install_clicked.emit(self._data))

        self.btn_secondary = QPushButton(f"{secondary_label}  →")
        self.btn_secondary.setFixedHeight(36)
        self.btn_secondary.setCursor(Qt.PointingHandCursor)
        self.btn_secondary.setStyleSheet(
            "QPushButton {"
            "  color: rgba(255,255,255,0.82);"
            "  border: 1px solid rgba(255,255,255,0.24);"
            "  border-radius: 6px; padding: 0 16px;"
            "  background: rgba(255,255,255,0.08);"
            "  font-size: 12px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(255,255,255,0.17); color: white;"
            "}"
        )
        self.btn_secondary.clicked.connect(
            lambda: self.learn_more_clicked.emit(self._data)
        )

        btn_row = QHBoxLayout()
        btn_row.setSpacing(10)
        btn_row.setContentsMargins(0, 0, 0, 0)
        btn_row.addWidget(self.btn_primary)
        btn_row.addWidget(self.btn_secondary)
        btn_row.addStretch()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(36, 0, 36, 26)
        outer.addStretch()
        outer.addLayout(btn_row)

    # ── painting ──────────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        w, h = self.width(), self.height()
        if w <= 0 or h <= 0:
            return

        p = QPainter(self)
        p.setRenderHints(
            QPainter.Antialiasing |
            QPainter.TextAntialiasing |
            QPainter.SmoothPixmapTransform
        )

        # ── rounded clip region ───────────────────────────────────────────────
        clip = QPainterPath()
        clip.addRoundedRect(QRectF(0, 0, w, h), 12, 12)
        p.setClipPath(clip)

        # ── layer 1: background (image or gradient) ───────────────────────────
        if self._px and not self._px.isNull():
            self._draw_image_bg(p, w, h)
        else:
            self._draw_gradient_bg(p, w, h)

        # ── layer 2: left-fade overlay so text is always readable ─────────────
        overlay = QLinearGradient(0, 0, w, 0)
        r, g, b = self._g0.red(), self._g0.green(), self._g0.blue()
        overlay.setColorAt(0.00, QColor(r, g, b, 235))
        overlay.setColorAt(0.45, QColor(r, g, b, 155))
        overlay.setColorAt(0.70, QColor(r, g, b,   0))
        p.setBrush(QBrush(overlay))
        p.setPen(Qt.NoPen)
        p.drawRect(0, 0, w, h)

        # ── layer 3: accent radial glow (right side) ──────────────────────────
        glow_x = int(w * 0.75)
        glow = QRadialGradient(glow_x, h // 2, h * 0.65)
        ca = QColor(self._accent); ca.setAlpha(48)
        cb = QColor(self._accent); cb.setAlpha(0)
        glow.setColorAt(0.0, ca); glow.setColorAt(1.0, cb)
        p.setBrush(QBrush(glow))
        p.drawRect(0, 0, w, h)

        # ── layer 4: tag chip ─────────────────────────────────────────────────
        tag = self._data.get("tag", "")
        if tag:
            p.setFont(self._F_TAG)
            fm  = QFontMetrics(self._F_TAG)
            tw  = fm.horizontalAdvance(tag) + 22
            chip = QRectF(36, 28, tw, 22)
            chip_bg = QColor(self._accent); chip_bg.setAlpha(42)
            p.setBrush(chip_bg)
            p.setPen(QPen(self._accent, 1.0))
            p.drawRoundedRect(chip, 11, 11)
            p.setPen(self._accent)
            p.drawText(chip, Qt.AlignCenter, tag)

        # ── layer 5: OS title ─────────────────────────────────────────────────
        p.setFont(self._F_TITLE)
        p.setPen(QColor(255, 255, 255, 245))
        p.drawText(
            QRectF(36, 60, w * 0.58, 54),
            Qt.AlignVCenter | Qt.AlignLeft,
            self._data.get("os_name", "")
        )

        # ── layer 6: tagline ──────────────────────────────────────────────────
        p.setFont(self._F_TAGLINE)
        p.setPen(QColor(255, 255, 255, 172))
        p.drawText(
            QRectF(36, 118, w * 0.55, 54),
            Qt.AlignTop | Qt.AlignLeft | Qt.TextWordWrap,
            self._data.get("tagline", "")
        )

        p.end()

    # ── background helpers ────────────────────────────────────────────────────

    def _draw_image_bg(self, p: QPainter, w: int, h: int):
        """Scale-to-cover the banner image (centre-crop)."""
        scaled = self._px.scaled(
            w, h,
            Qt.KeepAspectRatioByExpanding,
            Qt.SmoothTransformation
        )
        ox = (scaled.width()  - w) // 2
        oy = (scaled.height() - h) // 2
        p.drawPixmap(0, 0, scaled, ox, oy, w, h)

    def _draw_gradient_bg(self, p: QPainter, w: int, h: int):
        """Gradient fallback when image is unavailable."""
        grad = QLinearGradient(0, 0, w, 0)
        grad.setColorAt(0.0, self._g0)
        grad.setColorAt(1.0, self._g1)
        p.setBrush(QBrush(grad))
        p.setPen(Qt.NoPen)
        p.drawRect(0, 0, w, h)

    # ── extensibility ─────────────────────────────────────────────────────────

    def set_promoted(self, promoted: bool):
        """Override to add a featured-slide visual badge."""
        pass


# ══════════════════════════════════════════════════════════════════════════════
# DotIndicator
# ══════════════════════════════════════════════════════════════════════════════

class DotIndicator(QWidget):
    """Clickable pill-dot row. Active dot expands to a wider pill shape."""

    jumped = pyqtSignal(int)

    _GAP    = 14   # centre-to-centre spacing
    _DOT_D  = 7
    _PIL_W  = 18
    _PIL_H  = 7

    def __init__(self, count: int, parent=None):
        super().__init__(parent)
        self._count  = count
        self._active = 0
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(14)
        # width: (n-1) gaps + active pill + (n-1) dots
        self.setMinimumWidth(count * self._GAP + self._PIL_W)

    def set_active(self, idx: int):
        self._active = max(0, min(idx, self._count - 1))
        self.update()

    def paintEvent(self, _e):
        if self._count == 0:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)

        # total rendered width so we can centre it
        total = (self._count - 1) * self._GAP + self._PIL_W
        x0    = max(0, (self.width() - total) // 2)
        cy    = self.height() // 2

        for i in range(self._count):
            cx = x0 + i * self._GAP
            if i == self._active:
                p.setBrush(QColor("#00C6FF"))
                p.setPen(Qt.NoPen)
                p.drawRoundedRect(cx, cy - self._PIL_H // 2,
                                  self._PIL_W, self._PIL_H, 3, 3)
            else:
                p.setBrush(QColor(255, 255, 255, 55))
                p.setPen(Qt.NoPen)
                d  = self._DOT_D
                cx2 = cx + (self._PIL_W - d) // 2
                p.drawEllipse(cx2, cy - d // 2, d, d)
        p.end()

    def mousePressEvent(self, ev):
        total = (self._count - 1) * self._GAP + self._PIL_W
        x0    = max(0, (self.width() - total) // 2)
        for i in range(self._count):
            cx = x0 + i * self._GAP + self._PIL_W // 2
            if abs(ev.x() - cx) < 12:
                self.jumped.emit(i)
                break


# ══════════════════════════════════════════════════════════════════════════════
# MarketplaceBanner
# ══════════════════════════════════════════════════════════════════════════════

class MarketplaceBanner(QWidget):
    """
    Full-width hero banner carousel.

    Visibility fixes applied
    ────────────────────────
    • setMinimumHeight(SLIDE_H + 34)  — prevents layout from allocating 0 px.
    • setAttribute(WA_StyledBackground) — same as BannerSlide.
    • _stack.setCurrentIndex(0) called explicitly after all slides are added.
    • _crossfade() parents both QGraphicsOpacityEffects to `self` (not to the
      slide), so they are never double-owned and _animating resets correctly.

    Signals
    ───────
    install_clicked(dict)       primary CTA button on active slide
    learn_more_clicked(dict)    secondary CTA button on active slide

    Public API
    ──────────
    go_to(idx)          jump with crossfade (resets auto-timer)
    next() / prev()     advance / go back
    set_order(indices)  reorder for personalisation
    """

    install_clicked    = pyqtSignal(dict)
    learn_more_clicked = pyqtSignal(dict)

    _INTERVAL_MS  = 4500   # auto-advance period
    _FADE_OUT_MS  = 180    # opacity 1→0
    _FADE_IN_MS   = 240    # opacity 0→1

    def __init__(self, slides_data: List[dict], parent=None):
        super().__init__(parent)

        # ── visibility attributes ─────────────────────────────────────────────
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # ── load & enrich ─────────────────────────────────────────────────────
        loader   = BannerDataLoader()
        enriched = loader.load(slides_data)

        self._slides_data = enriched
        self._current     = 0
        self._count       = max(len(enriched), 1)   # guard against empty
        self._animating   = False

        # ── layout ────────────────────────────────────────────────────────────
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(8)

        # ── stacked slides ────────────────────────────────────────────────────
        self._stack = QStackedWidget()
        self._stack.setAttribute(Qt.WA_StyledBackground, True)
        self._stack.setFixedHeight(BannerSlide.SLIDE_H)
        self._slides: List[BannerSlide] = []

        for d in enriched:
            slide = BannerSlide(d)
            slide.install_clicked.connect(self.install_clicked)
            slide.learn_more_clicked.connect(self.learn_more_clicked)
            self._stack.addWidget(slide)
            self._slides.append(slide)

        # explicitly show slide 0 — crucial for first-paint inside ScrollArea
        self._stack.setCurrentIndex(0)

        # ── guarantee minimum height so layout never collapses ────────────────
        self.setMinimumHeight(BannerSlide.SLIDE_H + 34)

        # ── nav row: ‹  •••  › ───────────────────────────────────────────────
        nav = QHBoxLayout()
        nav.setContentsMargins(4, 0, 4, 0)
        nav.setSpacing(8)

        self._btn_prev = self._arrow_btn("‹")
        self._btn_next = self._arrow_btn("›")
        self._dots     = DotIndicator(self._count)

        self._dots.jumped.connect(self.go_to)
        self._btn_prev.clicked.connect(self.prev)
        self._btn_next.clicked.connect(self.next)

        nav.addWidget(self._btn_prev)
        nav.addStretch()
        nav.addWidget(self._dots)
        nav.addStretch()
        nav.addWidget(self._btn_next)

        root.addWidget(self._stack)
        root.addLayout(nav)

        # ── auto-advance timer ────────────────────────────────────────────────
        self._timer = QTimer(self)
        self._timer.setInterval(self._INTERVAL_MS)
        self._timer.timeout.connect(self.next)
        self._timer.start()

    # ── helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def _arrow_btn(label: str) -> QPushButton:
        btn = QPushButton(label)
        btn.setFixedSize(28, 28)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet("""
            QPushButton {
                font-size: 17px;
                color: rgba(255,255,255,0.55);
                background: rgba(255,255,255,0.06);
                border: 1px solid rgba(255,255,255,0.10);
                border-radius: 14px;
            }
            QPushButton:hover {
                background: rgba(255,255,255,0.14);
                color: white;
            }
        """)
        return btn

    # ── public API ────────────────────────────────────────────────────────────

    def go_to(self, idx: int):
        if idx == self._current or self._animating or self._count < 2:
            return
        self._timer.stop()
        self._crossfade(idx)
        self._timer.start()

    def next(self):
        self.go_to((self._current + 1) % self._count)

    def prev(self):
        self.go_to((self._current - 1) % self._count)

    def set_order(self, indices: List[int]):
        """Reorder slides for personalisation. Must be a permutation of 0..n-1."""
        if sorted(indices) != list(range(self._count)):
            log.warning("[MarketplaceBanner] set_order: invalid indices, ignored.")
            return
        self._slides_data = [self._slides_data[i] for i in indices]
        for s in self._slides:
            self._stack.removeWidget(s)
            s.deleteLater()
        self._slides.clear()
        for d in self._slides_data:
            s = BannerSlide(d)
            s.install_clicked.connect(self.install_clicked)
            s.learn_more_clicked.connect(self.learn_more_clicked)
            self._stack.addWidget(s)
            self._slides.append(s)
        self._current = 0
        self._dots.set_active(0)
        self._stack.setCurrentIndex(0)

    # ── crossfade transition ──────────────────────────────────────────────────

    def _crossfade(self, idx: int):
        """
        Fade out → switch → fade in.

        Both QGraphicsOpacityEffect objects are parented to `self`, NOT to the
        slide widgets.  This prevents double-ownership crashes and ensures
        _animating is always reset after anim_in finishes.
        """
        self._animating   = True
        outgoing = self._slides[self._current]
        incoming = self._slides[idx]

        # ── fade OUT ──────────────────────────────────────────────────────────
        eff_out = QGraphicsOpacityEffect(self)      # owned by carousel, not slide
        outgoing.setGraphicsEffect(eff_out)

        anim_out = QPropertyAnimation(eff_out, b"opacity", self)
        anim_out.setDuration(self._FADE_OUT_MS)
        anim_out.setStartValue(1.0)
        anim_out.setEndValue(0.0)
        anim_out.setEasingCurve(QEasingCurve.InQuad)

        def _on_fade_out_done():
            # switch the visible slide
            self._stack.setCurrentIndex(idx)
            self._current = idx
            self._dots.set_active(idx)

            # remove outgoing effect safely
            outgoing.setGraphicsEffect(None)

            # ── fade IN ───────────────────────────────────────────────────────
            eff_in = QGraphicsOpacityEffect(self)   # owned by carousel
            incoming.setGraphicsEffect(eff_in)

            anim_in = QPropertyAnimation(eff_in, b"opacity", self)
            anim_in.setDuration(self._FADE_IN_MS)
            anim_in.setStartValue(0.0)
            anim_in.setEndValue(1.0)
            anim_in.setEasingCurve(QEasingCurve.OutQuad)

            def _on_fade_in_done():
                incoming.setGraphicsEffect(None)   # remove effect — full opacity
                self._animating = False            # unlock for next transition

            anim_in.finished.connect(_on_fade_in_done)
            anim_in.start(QPropertyAnimation.DeleteWhenStopped)

        anim_out.finished.connect(_on_fade_out_done)
        anim_out.start(QPropertyAnimation.DeleteWhenStopped)

    # ── hover: pause auto-timer ───────────────────────────────────────────────

    def enterEvent(self, e):
        self._timer.stop()
        super().enterEvent(e)

    def leaveEvent(self, e):
        if not self._animating:
            self._timer.start()
        super().leaveEvent(e)
