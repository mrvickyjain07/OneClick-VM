"""
theme.py
========
Global dark theme stylesheet for OneClick VM.
All colors, fonts, and spacing are defined here for easy customization.
"""

# ── Design Tokens ─────────────────────────────────────────────────────────────
COLORS = {
    "bg":           "#0D1117",   # main background
    "surface":      "#161B22",   # card / panel background
    "surface_alt":  "#21262D",   # hover / alternate surface
    "border":       "#30363D",   # dividers and borders
    "primary":      "#58A6FF",   # blue accent
    "primary_dark": "#1F6FEB",   # pressed / active blue
    "success":      "#3FB950",   # running VMs
    "warning":      "#D29922",   # unknown / paused VMs
    "danger":       "#F85149",   # stopped / error VMs
    "text":         "#E6EDF3",   # primary text
    "text_secondary":"#8B949E",  # secondary / muted text
    "sidebar_bg":   "#010409",   # sidebar (darkest)
    "sidebar_hover":"#161B22",   # sidebar hover
    "sidebar_active":"#1F6FEB",  # sidebar selected item
}

FONT_FAMILY = "Segoe UI, Arial, sans-serif"

# ── Main Application Stylesheet ────────────────────────────────────────────────
MAIN_STYLESHEET = f"""
/* ── Global ── */
QWidget {{
    background-color: {COLORS['bg']};
    color: {COLORS['text']};
    font-family: {FONT_FAMILY};
    font-size: 13px;
}}

QMainWindow {{
    background-color: {COLORS['bg']};
}}

/* ── Sidebar ── */
#Sidebar {{
    background-color: {COLORS['sidebar_bg']};
    border-right: 1px solid {COLORS['border']};
}}

#SidebarButton {{
    background-color: transparent;
    color: {COLORS['text_secondary']};
    border: none;
    text-align: left;
    padding: 12px 20px;
    font-size: 13px;
    font-weight: 500;
    border-radius: 0px;
}}
#SidebarButton:hover {{
    background-color: {COLORS['sidebar_hover']};
    color: {COLORS['text']};
}}
#SidebarButton[active="true"] {{
    background-color: {COLORS['surface']};
    color: {COLORS['primary']};
    border-left: 3px solid {COLORS['primary']};
    font-weight: 600;
}}

#AppTitle {{
    font-size: 16px;
    font-weight: 700;
    color: {COLORS['primary']};
    padding: 20px 16px 10px 16px;
    letter-spacing: 1px;
}}
#AppVersion {{
    font-size: 10px;
    color: {COLORS['text_secondary']};
    padding: 0px 16px 20px 20px;
}}

/* ── Content Area ── */
#ContentStack {{
    background-color: {COLORS['bg']};
}}

/* ── Page Headers ── */
#PageTitle {{
    font-size: 22px;
    font-weight: 700;
    color: {COLORS['text']};
}}
#PageSubtitle {{
    font-size: 13px;
    color: {COLORS['text_secondary']};
}}

/* ── VM Card ── */
#VMCard {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 8px;
    padding: 0px;
}}
#VMCard:hover {{
    border: 1px solid {COLORS['primary']};
    background-color: {COLORS['surface_alt']};
}}
#VMCard[selected="true"] {{
    border: 1.5px solid {COLORS['primary']};
    background-color: {COLORS['surface_alt']};
}}

#VMName {{
    font-size: 14px;
    font-weight: 600;
    color: {COLORS['text']};
}}
#VMDetail {{
    font-size: 11px;
    color: {COLORS['text_secondary']};
}}

/* ── OS Card (Marketplace) ── */
#OSCard {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 10px;
}}
#OSCard:hover {{
    border: 1px solid {COLORS['primary']};
    background-color: {COLORS['surface_alt']};
}}

/* ── Status Badge ── */
#BadgeRunning {{
    background-color: rgba(63, 185, 80, 0.18);
    color: {COLORS['success']};
    border: 1px solid rgba(63, 185, 80, 0.4);
    border-radius: 4px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 600;
}}
#BadgeStopped {{
    background-color: rgba(248, 81, 73, 0.18);
    color: {COLORS['danger']};
    border: 1px solid rgba(248, 81, 73, 0.4);
    border-radius: 4px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 600;
}}
#BadgeUnknown {{
    background-color: rgba(210, 153, 34, 0.18);
    color: {COLORS['warning']};
    border: 1px solid rgba(210, 153, 34, 0.4);
    border-radius: 4px;
    padding: 1px 8px;
    font-size: 11px;
    font-weight: 600;
}}

/* ── Buttons ── */
QPushButton {{
    background-color: {COLORS['surface_alt']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 7px 16px;
    font-size: 13px;
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: {COLORS['border']};
    border: 1px solid {COLORS['primary']};
}}
QPushButton:pressed {{
    background-color: {COLORS['primary_dark']};
    color: white;
}}
QPushButton:disabled {{
    background-color: {COLORS['surface']};
    color: {COLORS['text_secondary']};
    border: 1px solid {COLORS['border']};
}}

#PrimaryButton {{
    background-color: {COLORS['primary_dark']};
    color: white;
    border: none;
    border-radius: 6px;
    padding: 9px 20px;
    font-size: 13px;
    font-weight: 600;
}}
#PrimaryButton:hover {{
    background-color: {COLORS['primary']};
}}
#PrimaryButton:pressed {{
    background-color: #0d5fcb;
}}
#PrimaryButton:disabled {{
    background-color: #1a2d4a;
    color: {COLORS['text_secondary']};
}}

#DangerButton {{
    background-color: rgba(248, 81, 73, 0.15);
    color: {COLORS['danger']};
    border: 1px solid rgba(248, 81, 73, 0.4);
    border-radius: 6px;
    padding: 7px 16px;
}}
#DangerButton:hover {{
    background-color: rgba(248, 81, 73, 0.3);
}}

#SuccessButton {{
    background-color: rgba(63, 185, 80, 0.15);
    color: {COLORS['success']};
    border: 1px solid rgba(63, 185, 80, 0.4);
    border-radius: 6px;
    padding: 7px 16px;
}}
#SuccessButton:hover {{
    background-color: rgba(63, 185, 80, 0.3);
}}

/* ── Inputs ── */
QLineEdit, QTextEdit, QPlainTextEdit {{
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 7px 10px;
    selection-background-color: {COLORS['primary']};
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 1px solid {COLORS['primary']};
}}
QComboBox {{
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 7px 10px;
}}
QComboBox:focus {{
    border: 1px solid {COLORS['primary']};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    selection-background-color: {COLORS['surface_alt']};
}}

/* ── Sliders ── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {COLORS['border']};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {COLORS['primary']};
    border: none;
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}
QSlider::sub-page:horizontal {{
    background: {COLORS['primary']};
    border-radius: 2px;
}}

/* ── Progress Bar ── */
QProgressBar {{
    background-color: {COLORS['surface']};
    border: 1px solid {COLORS['border']};
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    background-color: {COLORS['primary']};
    border-radius: 4px;
}}

/* ── Scroll Bars ── */
QScrollBar:vertical {{
    background: {COLORS['bg']};
    width: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:vertical {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::handle:vertical:hover {{
    background: {COLORS['text_secondary']};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}
QScrollBar:horizontal {{
    background: {COLORS['bg']};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {COLORS['border']};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

/* ── Message Boxes ── */
QMessageBox {{
    background-color: {COLORS['surface']};
}}
QMessageBox QPushButton {{
    min-width: 80px;
}}

/* ── Labels ── */
QLabel {{
    color: {COLORS['text']};
    background: transparent;
}}

/* ── Separators ── */
QFrame[frameShape="4"], QFrame[frameShape="5"] {{
    color: {COLORS['border']};
}}

/* ── Spinbox ── */
QSpinBox {{
    background-color: {COLORS['surface']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
    padding: 7px 10px;
}}
QSpinBox:focus {{
    border: 1px solid {COLORS['primary']};
}}
QSpinBox::up-button, QSpinBox::down-button {{
    background-color: {COLORS['surface_alt']};
    border: none;
    width: 16px;
}}

/* ── Log Console ── */
#LogConsole {{
    background-color: #010409;
    color: #58A6FF;
    font-family: "Consolas", "Courier New", monospace;
    font-size: 12px;
    border: 1px solid {COLORS['border']};
    border-radius: 6px;
}}

/* ── Divider Labels ── */
#SectionLabel {{
    font-size: 11px;
    font-weight: 600;
    color: {COLORS['text_secondary']};
    text-transform: uppercase;
    letter-spacing: 1px;
    padding: 0px 16px 4px 20px;
}}

/* ── Tooltip ── */
QToolTip {{
    background-color: {COLORS['surface_alt']};
    color: {COLORS['text']};
    border: 1px solid {COLORS['border']};
    padding: 5px 8px;
    border-radius: 4px;
}}
"""
