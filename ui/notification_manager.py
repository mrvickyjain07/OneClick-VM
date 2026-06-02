"""
ui/notification_manager.py
==========================
Centralised toast notification wrapper over qfluentwidgets InfoBar.

Usage
-----
    from ui.notification_manager import notify
    notify.success("VM Started", "Ubuntu is now running.")
    notify.error("Deploy Failed", err_msg, parent=self.window())
"""
from qfluentwidgets import InfoBar, InfoBarPosition


class _NotificationManager:
    """Singleton wrapper — call notify.success / notify.error etc."""

    _default_parent = None   # set once by app.py after window creation

    def set_parent(self, widget):
        self._default_parent = widget

    # ── helpers ──────────────────────────────────────────────────────────────

    def _show(self, level: str, title: str, body: str,
              duration: int = 4000, parent=None):
        p = parent or self._default_parent
        method = getattr(InfoBar, level, InfoBar.info)
        try:
            method(
                title, body,
                duration=duration,
                position=InfoBarPosition.TOP_RIGHT,
                parent=p,
            )
        except RuntimeError:
            pass  # Widget may have been destroyed

    # ── Public API ────────────────────────────────────────────────────────────

    def success(self, title: str, body: str = "", duration: int = 4000, parent=None):
        self._show("success", title, body, duration, parent)

    def error(self, title: str, body: str = "", duration: int = 0, parent=None):
        """duration=0 keeps it open until dismissed."""
        self._show("error", title, body[:300], duration, parent)

    def warning(self, title: str, body: str = "", duration: int = 5000, parent=None):
        self._show("warning", title, body, duration, parent)

    def info(self, title: str, body: str = "", duration: int = 3500, parent=None):
        self._show("info", title, body, duration, parent)


# ── Module-level singleton ────────────────────────────────────────────────────
notify = _NotificationManager()
