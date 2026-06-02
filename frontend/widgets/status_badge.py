"""
status_badge.py
===============
Reusable colored status badge widget.
Maps VirtualBox VMState strings to colored labels.
"""
from PyQt5.QtWidgets import QLabel
from PyQt5.QtCore import Qt


# VirtualBox state → badge type mapping
_STATE_MAP = {
    "running":          "Running",
    "paused":           "Paused",
    "poweroff":         "Stopped",
    "aborted":          "Stopped",
    "saved":            "Saved",
    "restoring":        "Unknown",
    "saving":           "Unknown",
    "unknown":          "Unknown",
}

# Badge object name → stylesheet id
_BADGE_IDS = {
    "Running": "BadgeRunning",
    "Paused":  "BadgeUnknown",
    "Stopped": "BadgeStopped",
    "Saved":   "BadgeUnknown",
    "Unknown": "BadgeUnknown",
}

# Dot indicator colors
_DOT_COLORS = {
    "Running": "#3FB950",
    "Paused":  "#D29922",
    "Stopped": "#F85149",
    "Saved":   "#D29922",
    "Unknown": "#D29922",
}


class StatusBadge(QLabel):
    """A small colored pill badge showing VM state."""

    def __init__(self, state: str = "unknown", parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self.setFixedHeight(22)
        self.update_state(state)

    def update_state(self, raw_state: str):
        """Update badge to reflect the given VirtualBox state string."""
        raw_state = (raw_state or "unknown").lower().strip()
        label = _STATE_MAP.get(raw_state, "Unknown")
        badge_id = _BADGE_IDS.get(label, "BadgeUnknown")
        dot_color = _DOT_COLORS.get(label, "#D29922")

        # Bullet dot + label text
        self.setText(f"● {label}")
        self.setObjectName(badge_id)

        # Re-apply style (objectName change requires re-polish)
        self.style().unpolish(self)
        self.style().polish(self)
        self.setMinimumWidth(80)
