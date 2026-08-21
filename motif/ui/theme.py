"""Visual language: dark amber Motif — one palette, one QSS, named tokens."""

from motif.models import EventType

# Surfaces
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
RECORD_IDLE = "#6E3A42"
OK = "#3DCF9A"
MOUSE = "#6AA6FF"
KEY = "#F0A05A"
WAIT = "#3DCF9A"
TRIGGER = "#C084FC"
ORIGIN = "#E8D26A"
NOTE = "#8B93A7"

# Button / selection language
PRIMARY_TEXT = "#1A1208"
PRIMARY_HOVER = "#F5B57A"
PLAYING_TEXT = "#0A1A14"
RECORDING_EDGE = "#FFD0D4"
DISABLED_TEXT = "#7A8296"
DISABLED_FILL = SURFACE
SELECTED_FILL = "#2A3348"

# Spacing grid
SPACE_XS = 4
SPACE_SM = 8
SPACE_MD = 12
SPACE_LG = 16

# Radii
RADIUS_SM = 6
RADIUS_MD = 8
RADIUS_LG = 10
RADIUS_XL = 14
RADIUS_SWATCH = 5
SWATCH_W = 10
SWATCH_H = 34

# Type (px) — system UI font only; never name a family
TYPE_BODY = 13
TYPE_TITLE = 18
TYPE_SECTION = 11
TYPE_CHIP = 10
TYPE_HINT = 12

# Chrome
BUTTON_HEIGHT = 38
BUTTON_MIN_WIDTH = 104
STOP_MIN_WIDTH = 80
VERB_PAD_H = 18
CHIP_HEIGHT = 28
CHIP_MIN_WIDTH = 44
CYCLE_MIN_WIDTH = 48
CYCLE_SPIN_MIN = 64
SPEED_SPIN_MIN = 72
CLUSTER_PAD = 2
TRANSPORT_MIN_HEIGHT = 48
CARD_PAD_H = 12
CARD_PAD_V = 8
INPUT_MIN_HEIGHT = 28
SPLITTER_MAIN_DEFAULT = [900, 340]
SPLITTER_LEFT_DEFAULT = [480, 120, 220]

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
    EventType.SWIPE: KEY,
}
for _name in ("SWIPE", "SWIPE_4", "FOUR_FINGER_SWIPE", "TRACKPAD_SWIPE"):
    _kind = getattr(EventType, _name, None)
    if _kind is not None:
        TYPE_COLOR.setdefault(_kind, MOUSE)

QSS = f"""
* {{
    font-size: {TYPE_BODY}px;
    color: {TEXT};
}}
QMainWindow, QDialog, QWidget#root {{
    background: {BG};
}}
QWidget#titleBar, QWidget#header, QWidget#transport {{
    background: {BG};
}}
QWidget#transport {{
    min-height: {TRANSPORT_MIN_HEIGHT}px;
}}
QWidget#cyclesCluster, QWidget#speedCluster {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
}}
QMenuBar {{
    background: {BG};
    border-bottom: 1px solid {BORDER};
    padding: {SPACE_XS}px {SPACE_SM}px;
}}
QMenuBar::item {{
    padding: {SPACE_SM}px 10px;
    border-radius: {RADIUS_SM}px;
}}
QMenuBar::item:selected {{
    background: {SURFACE_2};
}}
QMenu {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    padding: {SPACE_SM}px;
}}
QMenu::item {{
    padding: 7px 18px;
    border-radius: {RADIUS_SM}px;
}}
QMenu::item:selected {{
    background: {SURFACE_3};
}}
QToolBar {{
    background: {BG};
    border: none;
    spacing: {SPACE_SM}px;
    padding: 10px 14px {SPACE_SM}px 14px;
}}
QPushButton {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_LG}px;
    padding: {SPACE_SM}px 14px;
    min-height: 18px;
}}
QPushButton:hover {{
    background: {SURFACE_3};
}}
QPushButton:pressed {{
    background: {SURFACE};
}}
QPushButton:disabled {{
    color: {DISABLED_TEXT};
    background: {DISABLED_FILL};
    border: 1px solid {BORDER};
}}
QPushButton#recordBtn, QPushButton#replayBtn, QPushButton#stopBtn {{
    min-height: {BUTTON_HEIGHT}px;
    padding: {SPACE_SM}px {VERB_PAD_H}px;
    border-radius: {RADIUS_LG}px;
}}
QPushButton[kind="primary"] {{
    background: {ACCENT};
    color: {PRIMARY_TEXT};
    border: none;
    font-weight: 600;
    min-width: {BUTTON_MIN_WIDTH}px;
}}
QPushButton[kind="primary"]:hover {{
    background: {PRIMARY_HOVER};
}}
QPushButton[kind="primary"]:pressed {{
    background: {ACCENT_DIM};
    color: {TEXT};
}}
QPushButton[kind="primary"]:disabled {{
    background: {SURFACE_2};
    color: #9AA3B8;
    border: 1px solid {BORDER};
    font-weight: 600;
    min-width: {BUTTON_MIN_WIDTH}px;
}}
QPushButton[kind="secondary"],
QPushButton[kind="ghost"] {{
    background: transparent;
    border: 1px solid {BORDER};
}}
QPushButton[kind="ghost"]:hover {{
    background: {SURFACE_2};
}}
QPushButton[kind="ghost"]:pressed {{
    background: {SURFACE};
}}
QPushButton[kind="danger"],
QPushButton[kind="record"] {{
    background: transparent;
    color: {TEXT};
    border: 1px solid {RECORD_IDLE};
    font-weight: 600;
    min-width: {BUTTON_MIN_WIDTH}px;
}}
QPushButton[kind="danger"]:hover,
QPushButton[kind="record"]:hover {{
    background: {SURFACE_2};
    border: 1px solid {RECORD};
}}
QPushButton[kind="danger"]:pressed,
QPushButton[kind="record"]:pressed {{
    background: {SURFACE};
    border: 1px solid {RECORD};
}}
QPushButton[kind="danger"]:disabled,
QPushButton[kind="record"]:disabled {{
    background: {DISABLED_FILL};
    color: {DISABLED_TEXT};
    border: 1px solid {BORDER};
}}
QPushButton[kind="recording"] {{
    background: {RECORD};
    color: white;
    border: 2px solid {RECORDING_EDGE};
    font-weight: 700;
    min-width: {BUTTON_MIN_WIDTH}px;
}}
QPushButton[kind="recording"]:hover,
QPushButton[kind="recording"]:pressed {{
    background: {RECORD};
    color: white;
}}
QPushButton[kind="playing"] {{
    background: {OK};
    color: {PLAYING_TEXT};
    border: none;
    font-weight: 700;
    min-width: {BUTTON_MIN_WIDTH}px;
}}
QPushButton[kind="playing"]:hover,
QPushButton[kind="playing"]:pressed {{
    background: {OK};
    color: {PLAYING_TEXT};
}}
QPushButton[kind="stop"] {{
    background: {SURFACE_3};
    border: 1px solid {TEXT};
    color: {TEXT};
    font-weight: 600;
    min-width: {STOP_MIN_WIDTH}px;
}}
QPushButton[kind="stop"]:hover {{
    background: {TEXT};
    color: {BG};
}}
QPushButton[kind="stop"]:pressed {{
    background: {MUTED};
    color: {BG};
}}
QPushButton[kind="stop"]:disabled {{
    background: {DISABLED_FILL};
    color: {DISABLED_TEXT};
    border: 1px solid {BORDER};
}}
QPushButton[kind="cycle"],
QPushButton[kind="speed"] {{
    background: transparent;
    border: none;
    border-radius: 0;
    min-width: {CHIP_MIN_WIDTH}px;
    padding: {SPACE_XS}px 10px;
    color: {TEXT};
    font-weight: 500;
}}
QPushButton[kind="cycle"] {{
    min-width: {CYCLE_MIN_WIDTH}px;
}}
QPushButton[kind="cycle"]:hover,
QPushButton[kind="speed"]:hover {{
    background: {SURFACE_3};
}}
QPushButton[kind="cycle"]:pressed,
QPushButton[kind="speed"]:pressed {{
    background: {SURFACE};
}}
QPushButton[kind="cycle"]:checked,
QPushButton[kind="speed"]:checked {{
    background: {SELECTED_FILL};
    color: {ACCENT};
    border: none;
    font-weight: 600;
}}
QPushButton[kind="cycle"]:disabled,
QPushButton[kind="speed"]:disabled {{
    color: {DISABLED_TEXT};
    background: transparent;
    border: none;
}}
QPushButton#cycleChip_1 {{
    border-top-left-radius: {RADIUS_MD}px;
    border-bottom-left-radius: {RADIUS_MD}px;
}}
QPushButton#cycleChip_100 {{
    border-top-right-radius: {RADIUS_MD}px;
    border-bottom-right-radius: {RADIUS_MD}px;
}}
QPushButton#speedChip_0_5 {{
    border-top-left-radius: {RADIUS_MD}px;
    border-bottom-left-radius: {RADIUS_MD}px;
}}
QPushButton#speedChip_2_0 {{
    border-top-right-radius: {RADIUS_MD}px;
    border-bottom-right-radius: {RADIUS_MD}px;
}}
QPushButton#cycleChip_10, QPushButton#cycleChip_100,
QPushButton#speedChip_1_0, QPushButton#speedChip_1_5, QPushButton#speedChip_2_0 {{
    border-left: 1px solid {BORDER};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {SURFACE_2};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_MD}px;
    padding: {SPACE_SM}px {SPACE_SM}px;
    min-height: 18px;
    selection-background-color: {ACCENT_DIM};
}}
QSpinBox#cyclesSpin, QDoubleSpinBox#speedSpin {{
    padding: {SPACE_XS}px {SPACE_SM}px;
    min-height: {CHIP_HEIGHT}px;
    max-height: {CHIP_HEIGHT}px;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 22px;
}}
QListWidget {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL}px;
    padding: {SPACE_SM}px;
    outline: none;
}}
QListWidget::item {{
    border-radius: {RADIUS_LG}px;
    margin: 3px 2px;
    padding: 0;
    background: transparent;
    border: 2px solid transparent;
}}
QListWidget::item:selected {{
    background: {SELECTED_FILL};
    border: 2px solid {ACCENT};
}}
QListWidget::item:hover:!selected {{
    background: {SURFACE_2};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
QScrollBar:vertical {{
    background: transparent;
    width: 10px;
    margin: {SPACE_XS}px 2px;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: {SPACE_XS}px;
    min-height: 28px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QLabel[role="muted"] {{
    color: {MUTED};
}}
QLabel[role="hint"] {{
    color: {MUTED};
    font-size: {TYPE_HINT}px;
}}
QLabel[role="title"] {{
    font-size: {TYPE_TITLE}px;
    font-weight: 650;
}}
QLabel[role="section"] {{
    color: {MUTED};
    font-size: {TYPE_SECTION}px;
    font-weight: 600;
    letter-spacing: 0.6px;
}}
QLabel[role="chip"] {{
    font-size: {TYPE_CHIP}px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel[role="empty"] {{
    color: {MUTED};
    font-size: {TYPE_BODY}px;
}}
QLabel#banner[tone="record"] {{
    color: {RECORD};
    font-weight: 600;
    padding: {SPACE_SM}px;
}}
QLabel#banner[tone="ok"] {{
    color: {OK};
    font-weight: 600;
    padding: {SPACE_SM}px;
}}
QCheckBox, QRadioButton {{
    spacing: {SPACE_SM}px;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: {SPACE_LG}px;
    height: {SPACE_LG}px;
    border-radius: {SPACE_XS}px;
    border: 1px solid {BORDER};
    background: {SURFACE_2};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QSlider::groove:horizontal {{
    height: {SPACE_XS}px;
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
    border-radius: {RADIUS_MD}px;
    margin-top: 14px;
    padding: {SPACE_MD}px {SPACE_MD}px {SPACE_SM}px {SPACE_MD}px;
    background: {SURFACE};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {SPACE_MD}px;
    padding: 0 {SPACE_SM}px;
    color: {MUTED};
}}
QStatusBar {{
    background: {BG};
    border-top: 1px solid {BORDER};
    color: {MUTED};
}}
QSplitter::handle {{
    background: {BG};
    width: {SPACE_SM}px;
}}
QSplitter::handle:vertical {{
    height: {SPACE_SM}px;
    width: auto;
}}
QFrame#card {{
    background: {SURFACE};
    border: 1px solid {BORDER};
    border-radius: {RADIUS_XL}px;
}}
QWidget#eventCard {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: {RADIUS_MD}px;
}}
QWidget#eventCard QLabel#eventTitle {{
    font-weight: 600;
}}
QWidget#eventCard QLabel#eventKind {{
    font-size: {TYPE_CHIP}px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QWidget#eventCard QLabel#eventDelay {{
    min-width: 76px;
}}
QWidget#eventCard[selected="true"] {{
    background: {SELECTED_FILL};
    border-radius: {RADIUS_MD}px;
}}
QWidget#eventCard[state="disabled"] QLabel#eventTitle,
QWidget#eventCard[state="disabled"] QLabel#eventKind,
QWidget#eventCard[state="disabled"] QLabel#eventDetail,
QWidget#eventCard[state="disabled"] QLabel#eventDelay {{
    color: {MUTED};
}}
"""
