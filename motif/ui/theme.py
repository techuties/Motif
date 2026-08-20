"""Visual language: dark, high-contrast, one accent, colour-coded events."""

from motif.models import EventType

BG = "#101218"
SURFACE = "#171B24"
SURFACE_2 = "#1E2430"
SURFACE_3 = "#262D3B"
BORDER = "#31384A"
TEXT = "#E8ECF4"
MUTED = "#8B93A7"
ACCENT = "#F0A05A"
ACCENT_DIM = "#8A5A2E"
RECORD = "#FF5C6C"
OK = "#3DCF9A"
MOUSE = "#6AA6FF"
KEY = "#F0A05A"
WAIT = "#3DCF9A"
TRIGGER = "#C084FC"
ORIGIN = "#E8D26A"
NOTE = "#8B93A7"

TYPE_COLOR = {
    EventType.MOVE: MOUSE,
    EventType.CLICK: MOUSE,
    EventType.SCROLL: MOUSE,
    EventType.KEY_DOWN: KEY,
    EventType.KEY_UP: KEY,
    EventType.WAIT: WAIT,
    EventType.WAIT_PIXEL: TRIGGER,
    EventType.WAIT_PIXEL_CHANGE: TRIGGER,
    EventType.GO_ORIGIN: ORIGIN,
    EventType.COMMENT: NOTE,
}

QSS = f"""
* {{
    font-family: "SF Pro Text", "Segoe UI", "Inter", "Helvetica Neue", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QDialog, QWidget#root {{
    background: {BG};
}}
QMenuBar {{
    background: {BG};
    border-bottom: 1px solid {BORDER};
    padding: 4px 8px;
}}
QMenuBar::item {{
    padding: 6px 10px;
    border-radius: 6px;
}}
QMenuBar::item:selected {{
    background: {SURFACE_2};
}}
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 18px;
    border-radius: 6px;
}}
QMenu::item:selected {{
    background: {SURFACE_3};
}}
QToolBar {{
    background: {BG};
    border: none;
    spacing: 8px;
    padding: 10px 14px 6px 14px;
}}
QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 10px;
    padding: 8px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {SURFACE_3};
}}
QPushButton:pressed {{
    background: {SURFACE};
}}
QPushButton:disabled {{
    color: {MUTED};
}}
QPushButton[kind="primary"] {{
    background: {ACCENT};
    color: #1A1208;
    border: none;
    font-weight: 600;
}}
QPushButton[kind="primary"]:hover {{
    background: #F5B57A;
}}
QPushButton[kind="record"] {{
    background: {RECORD};
    color: white;
    border: none;
    font-weight: 600;
}}
QPushButton[kind="ghost"] {{
    background: transparent;
    border: 1px solid {BORDER};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px 8px;
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QListWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
    padding: 6px;
    outline: none;
}}
QListWidget::item {{
    border-radius: 10px;
    margin: 3px 2px;
    padding: 0;
}}
QListWidget::item:selected {{
    background: {SURFACE_3};
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: 4px 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 28px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QLabel[role="muted"] {{
    color: {MUTED};
}}
QLabel[role="title"] {{
    font-size: 18px;
    font-weight: 650;
}}
QLabel[role="section"] {{
    color: {MUTED};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.6px;
}}
QCheckBox, QRadioButton {{
    spacing: 8px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 16px;
    height: 16px;
    border-radius: 4px;
    border: 1px solid {BORDER};
    background: {SURFACE_2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: 4px;
    background: {SURFACE_3};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: 14px;
    height: 14px;
    margin: -6px 0;
    border-radius: 7px;
    background: {ACCENT};
}}
QGroupBox {{
    border: 1px solid {BORDER};
    border-radius: 12px;
    margin-top: 14px;
    padding: 12px 10px 10px 10px;
    background: {SURFACE};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {MUTED};
}}
QStatusBar {{
    background: {BG};
    border-top: 1px solid {BORDER};
    color: {MUTED};
}}
QSplitter::handle {{
    background: {BG};
    width: 10px;
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: 14px;
}}
"""
