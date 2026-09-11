"""Visual language: the TechUties instrument palette — tokens, themes, one QSS builder.

Motif is a recording instrument, so it is dressed like one: brand navy ground,
hairline rules, one warm amber reserved for the live signal, and tabular digits
wherever a number has to be compared down a column.

Brand tokens come from techuties.com — navy ``#050A1F``, amber ``#FF9A1A``,
Inter first in the type stack.

Three themes ship. Every foreground/background pair in each of them clears
WCAG AA (4.5:1) and almost all clear AAA (7:1); ``tests/test_engine.py`` proves
it rather than trusting this docstring. Text size is a user setting because the
QSS is built in device-independent pixels, which do not follow the OS text-size
control on their own.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from motif.models import EventType


@dataclass(frozen=True)
class Palette:
    """One complete set of colour tokens. Never read raw hex outside this file."""

    name: str
    label: str
    dark: bool

    # Surfaces, back to front
    ground: str
    surface: str
    surface_2: str
    surface_3: str

    # Rules
    line: str
    line_strong: str

    # Type
    text: str
    muted: str
    faint: str

    # Signal
    accent: str
    accent_hover: str
    accent_ink: str
    accent_text: str
    selection: str
    focus: str

    # Transport states
    record: str
    record_ink: str
    record_idle: str
    ok: str
    ok_ink: str

    # Event kinds
    mouse: str
    key: str
    wait: str
    trigger: str
    origin: str
    note: str

    focus_width: int = 2

    def type_colors(self) -> dict[EventType, str]:
        """Swatch / chip colour per event type. Colour is never the only cue."""
        return {
            EventType.MOVE: self.mouse,
            EventType.CLICK: self.mouse,
            EventType.SCROLL: self.mouse,
            EventType.KEY_DOWN: self.key,
            EventType.KEY_UP: self.key,
            EventType.WAIT: self.wait,
            EventType.WAIT_PIXEL: self.trigger,
            EventType.WAIT_PIXEL_CHANGE: self.trigger,
            EventType.GO_ORIGIN: self.origin,
            EventType.COMMENT: self.note,
            EventType.SWIPE: self.key,
        }


DARK = Palette(
    name="night",
    label="TechUties Night",
    dark=True,
    ground="#050A1F",
    surface="#0B1226",
    surface_2="#121B33",
    surface_3="#1B2643",
    line="#223052",
    line_strong="#33456E",
    text="#EEF2FB",
    muted="#9AA7C6",
    # Disabled text has to stay legible on the selection fill too — a skipped
    # step on a selected row is the worst case, and it still clears AA.
    faint="#8B9AC0",
    accent="#FF9A1A",
    accent_hover="#FFB454",
    accent_ink="#050A1F",
    accent_text="#FF9A1A",
    selection="#1E2C50",
    focus="#FF9A1A",
    record="#FF6B7A",
    record_ink="#050A1F",
    record_idle="#6B2E38",
    ok="#37D9A0",
    ok_ink="#050A1F",
    mouse="#6FB4FF",
    key="#FF9A1A",
    wait="#37D9A0",
    trigger="#B98BFF",
    origin="#FFD75E",
    note="#9AA7C6",
)

LIGHT = Palette(
    name="day",
    label="TechUties Day",
    dark=False,
    ground="#F4F7FC",
    surface="#FFFFFF",
    surface_2="#EDF1F8",
    surface_3="#E2E9F5",
    line="#D3DCEC",
    line_strong="#A9B8D4",
    text="#050A1F",
    muted="#4A5878",
    faint="#5C6A90",
    accent="#FF9A1A",
    accent_hover="#FFAE45",
    accent_ink="#050A1F",
    accent_text="#7A4200",
    selection="#FFF0DC",
    focus="#7A4200",
    record="#FF6B7A",
    record_ink="#050A1F",
    record_idle="#E0AEB5",
    ok="#37D9A0",
    ok_ink="#050A1F",
    mouse="#0B5FBF",
    key="#7A4200",
    wait="#08694C",
    trigger="#6B2FBF",
    origin="#6B5300",
    note="#4A5878",
)

CONTRAST = Palette(
    name="contrast",
    label="High Contrast",
    dark=True,
    ground="#000000",
    surface="#000000",
    surface_2="#101010",
    surface_3="#1C1C1C",
    line="#FFFFFF",
    line_strong="#FFFFFF",
    text="#FFFFFF",
    muted="#E8E8E8",
    faint="#C8C8C8",
    accent="#FFB020",
    accent_hover="#FFC65C",
    accent_ink="#000000",
    accent_text="#FFB020",
    selection="#2A2A2A",
    focus="#FFB020",
    record="#FF8492",
    record_ink="#000000",
    record_idle="#FF8492",
    ok="#4DE6A8",
    ok_ink="#000000",
    mouse="#66D9FF",
    key="#FFB020",
    wait="#4DE6A8",
    trigger="#D9A6FF",
    origin="#FFD75E",
    note="#E8E8E8",
    focus_width=3,
)

THEMES: dict[str, Palette] = {p.name: p for p in (DARK, LIGHT, CONTRAST)}
DEFAULT_THEME = DARK.name

# Text size is a first-class accessibility control: QSS px do not follow the OS
# text-size setting. Never below 1.0 — shrinking would shrink hit targets too.
TEXT_SCALES: tuple[float, ...] = (1.0, 1.15, 1.3, 1.5)
TEXT_SCALE_LABELS = {1.0: "Normal", 1.15: "Large", 1.3: "Larger", 1.5: "Largest"}
MIN_SCALE = 1.0
MAX_SCALE = 1.5

# Inter is the TechUties web face; the rest are the platform UI faces it stands
# in for. Real family names only — Qt has no CSS generics and logs a missing
# "Sans Serif" alias for every widget if you hand it one.
FONT_STACK = '"Inter", "SF Pro Text", "Helvetica Neue", "Segoe UI", "Noto Sans", Arial'
MONO_STACK = '"SF Mono", "JetBrains Mono", Menlo, Consolas, "DejaVu Sans Mono", Courier'

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

# Type (px at 100%)
TYPE_BODY = 13
TYPE_TITLE = 19
TYPE_SECTION = 11
TYPE_CHIP = 10
TYPE_HINT = 12

# Chrome. One control height runs through the whole toolbar: a verb button is
# BUTTON_HEIGHT, and a cluster is CHIP_HEIGHT + 2*CLUSTER_PAD + 2px border, which
# comes to the same number (36 + 2*3 = 42). QAbstractSpinBox will not go below
# 35px without crushing its arrows, so CHIP_HEIGHT has to clear that.
BUTTON_HEIGHT = 42
BUTTON_MIN_WIDTH = 104
STOP_MIN_WIDTH = 78
VERB_PAD_H = 14
CHIP_HEIGHT = 36
CHIP_MIN_WIDTH = 46
CYCLE_MIN_WIDTH = 50
CYCLE_SPIN_MIN = 62
SPEED_SPIN_MIN = 70
CLUSTER_PAD = 3
TRANSPORT_MIN_HEIGHT = 48
CARD_PAD_H = 12
CARD_PAD_V = 8
INPUT_MIN_HEIGHT = 36
# Pointer targets never go under this, at any text size.
MIN_TARGET = 28
SPLITTER_MAIN_DEFAULT = [900, 340]
SPLITTER_LEFT_DEFAULT = [480, 120, 220]


_active_palette: Palette = THEMES[DEFAULT_THEME]
_active_scale: float = 1.0


def active() -> Palette:
    """The palette currently painted. Custom-painted widgets must call this."""
    return _active_palette


def active_scale() -> float:
    return _active_scale


def clamp_scale(scale: float) -> float:
    try:
        value = float(scale)
    except (TypeError, ValueError):
        return 1.0
    return max(MIN_SCALE, min(MAX_SCALE, value))


def resolve_theme(name: str) -> Palette:
    return THEMES.get(str(name or "").strip().lower(), THEMES[DEFAULT_THEME])


def scaled(value: int, scale: float | None = None) -> int:
    """Scale a metric with the text size, so hit targets grow with the type."""
    factor = _active_scale if scale is None else clamp_scale(scale)
    return int(round(value * factor))


def set_theme(name: str, scale: float = 1.0) -> str:
    """Make this theme active and return its QSS. Caller applies it to the app."""
    global _active_palette, _active_scale
    _active_palette = resolve_theme(name)
    _active_scale = clamp_scale(scale)
    return build_qss(_active_palette, _active_scale)


def type_color_for(kind: EventType) -> str:
    return _active_palette.type_colors().get(kind, _active_palette.note)


def qt_palette(palette: Palette | None = None):
    """A QPalette matching the theme.

    QSS does not reach everything. Scroll-area viewports, dialogs and item views
    paint from the QPalette, so without this the inspector renders on the host
    OS's window colour — near-white on a light-mode Mac, under near-white text.
    Import Qt lazily so this module stays importable without a QApplication.
    """
    from PySide6.QtGui import QColor, QPalette

    p = palette or _active_palette
    qp = QPalette()
    role = QPalette.ColorRole
    group = QPalette.ColorGroup
    pairs = {
        role.Window: p.ground,
        role.WindowText: p.text,
        role.Base: p.surface_2,
        role.AlternateBase: p.surface,
        role.Text: p.text,
        role.Button: p.surface_2,
        role.ButtonText: p.text,
        role.BrightText: p.accent,
        role.Highlight: p.accent,
        role.HighlightedText: p.accent_ink,
        role.ToolTipBase: p.surface_3,
        role.ToolTipText: p.text,
        role.PlaceholderText: p.faint,
        role.Link: p.accent_text,
    }
    for key, value in pairs.items():
        qp.setColor(key, QColor(value))
    for key in (role.WindowText, role.Text, role.ButtonText):
        qp.setColor(group.Disabled, key, QColor(p.faint))
    return qp


def build_qss(palette: Palette, scale: float = 1.0) -> str:
    """One stylesheet from one palette. Every px passes through the text scale."""
    p = palette
    s = clamp_scale(scale)

    def px(value: int) -> int:
        return int(round(value * s))

    body = px(TYPE_BODY)
    title = px(TYPE_TITLE)
    section = px(TYPE_SECTION)
    chip_type = px(TYPE_CHIP)
    hint = px(TYPE_HINT)
    btn_h = px(BUTTON_HEIGHT)
    btn_w = px(BUTTON_MIN_WIDTH)
    stop_w = px(STOP_MIN_WIDTH)
    chip_h = px(CHIP_HEIGHT)
    chip_w = px(CHIP_MIN_WIDTH)
    cycle_w = px(CYCLE_MIN_WIDTH)
    input_h = px(INPUT_MIN_HEIGHT)
    transport_h = px(TRANSPORT_MIN_HEIGHT)
    pad_v = px(SPACE_SM)
    pad_h = px(SPACE_MD)
    verb_h = px(VERB_PAD_H)
    focus_w = p.focus_width

    return f"""
* {{
    font-family: {FONT_STACK};
    font-size: {body}px;
    color: {p.text};
}}
QMainWindow, QDialog, QWidget#root {{
    background: {p.ground};
}}
QToolTip {{
    background: {p.surface_3};
    color: {p.text};
    border: 1px solid {p.line_strong};
    border-radius: {RADIUS_SM}px;
    padding: {px(SPACE_SM)}px {px(SPACE_MD)}px;
}}
QWidget#titleBar, QWidget#header, QWidget#transport {{
    background: {p.ground};
}}
QWidget#transport {{
    min-height: {transport_h}px;
}}
QWidget#cyclesCluster, QWidget#speedCluster {{
    background: {p.surface_2};
    border: 1px solid {p.line};
    border-radius: {RADIUS_MD}px;
}}
QFrame#zoneSeparator {{
    background: {p.line};
    border: none;
}}
QFrame#clusterDivider {{
    background: {p.line};
    border: none;
}}

/* --- Focus: one amber ring, on every control that can take focus ---------- */
QPushButton:focus,
QToolButton:focus,
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus,
QComboBox:focus, QPlainTextEdit:focus,
QCheckBox:focus, QRadioButton:focus,
QListWidget:focus, QAbstractScrollArea:focus,
QWidget#pathCanvas:focus, QWidget#screenHistory:focus {{
    border: {focus_w}px solid {p.focus};
}}
QListWidget::item:focus {{
    border: {focus_w}px solid {p.focus};
}}

QMenuBar {{
    background: {p.ground};
    border-bottom: 1px solid {p.line};
    padding: {px(SPACE_XS)}px {px(SPACE_SM)}px;
}}
QMenuBar::item {{
    padding: {px(SPACE_SM)}px {px(10)}px;
    border-radius: {RADIUS_SM}px;
}}
QMenuBar::item:selected {{
    background: {p.surface_2};
    color: {p.text};
}}
QMenu {{
    background: {p.surface};
    border: 1px solid {p.line};
    padding: {px(SPACE_SM)}px;
}}
QMenu::item {{
    padding: {px(7)}px {px(18)}px;
    border-radius: {RADIUS_SM}px;
}}
QMenu::item:selected {{
    background: {p.surface_3};
    color: {p.text};
}}
QMenu::separator {{
    height: 1px;
    background: {p.line};
    margin: {px(SPACE_XS)}px {px(SPACE_SM)}px;
}}
QPushButton {{
    background: {p.surface_2};
    border: 1px solid {p.line};
    border-radius: {RADIUS_LG}px;
    padding: {pad_v}px {pad_h}px;
    min-height: {px(MIN_TARGET) - 2 * pad_v}px;
}}
QPushButton:hover {{
    background: {p.surface_3};
}}
QPushButton:pressed {{
    background: {p.surface};
}}
QPushButton:disabled {{
    color: {p.faint};
    background: {p.surface};
    border: 1px solid {p.line};
}}
/* These carry a fixed height from _lock_chrome, so the box must add up to
   exactly that: content + 1px border each side, no vertical padding. Padding
   on top of a fixed height clips the label instead of growing the button. */
QPushButton#recordBtn, QPushButton#replayBtn, QPushButton#stopBtn {{
    min-height: {btn_h - 2}px;
    max-height: {btn_h - 2}px;
    padding: 0 {verb_h}px;
    border-radius: {RADIUS_LG}px;
}}
QPushButton[kind="primary"] {{
    background: {p.accent};
    color: {p.accent_ink};
    border: 1px solid {p.accent};
    font-weight: 600;
    min-width: {btn_w}px;
}}
QPushButton[kind="primary"]:hover {{
    background: {p.accent_hover};
    border: 1px solid {p.accent_hover};
}}
QPushButton[kind="primary"]:pressed {{
    background: {p.accent};
    color: {p.accent_ink};
}}
QPushButton[kind="primary"]:disabled {{
    background: {p.surface_2};
    color: {p.faint};
    border: 1px solid {p.line};
    font-weight: 600;
    min-width: {btn_w}px;
}}
QPushButton[kind="secondary"],
QPushButton[kind="ghost"] {{
    background: transparent;
    border: 1px solid {p.line_strong};
}}
QPushButton[kind="ghost"]:hover {{
    background: {p.surface_2};
}}
QPushButton[kind="ghost"]:pressed {{
    background: {p.surface};
}}
QPushButton[kind="danger"],
QPushButton[kind="record"] {{
    background: transparent;
    color: {p.text};
    border: 1px solid {p.record_idle};
    font-weight: 600;
    min-width: {btn_w}px;
}}
QPushButton[kind="danger"]:hover,
QPushButton[kind="record"]:hover {{
    background: {p.surface_2};
    border: 1px solid {p.record};
}}
QPushButton[kind="danger"]:pressed,
QPushButton[kind="record"]:pressed {{
    background: {p.surface};
    border: 1px solid {p.record};
}}
QPushButton[kind="danger"]:disabled,
QPushButton[kind="record"]:disabled {{
    background: {p.surface};
    color: {p.faint};
    border: 1px solid {p.line};
}}
QPushButton[kind="recording"] {{
    background: {p.record};
    color: {p.record_ink};
    border: 1px solid {p.record};
    font-weight: 700;
    min-width: {btn_w}px;
}}
QPushButton[kind="recording"]:hover,
QPushButton[kind="recording"]:pressed {{
    background: {p.record};
    color: {p.record_ink};
}}
QPushButton[kind="playing"] {{
    background: {p.ok};
    color: {p.ok_ink};
    border: 1px solid {p.ok};
    font-weight: 700;
    min-width: {btn_w}px;
}}
QPushButton[kind="playing"]:hover,
QPushButton[kind="playing"]:pressed {{
    background: {p.ok};
    color: {p.ok_ink};
}}
QPushButton[kind="stop"] {{
    background: {p.surface_3};
    border: 1px solid {p.text};
    color: {p.text};
    font-weight: 600;
    min-width: {stop_w}px;
}}
QPushButton[kind="stop"]:hover {{
    background: {p.text};
    color: {p.ground};
}}
QPushButton[kind="stop"]:pressed {{
    background: {p.muted};
    color: {p.ground};
}}
QPushButton[kind="stop"]:disabled {{
    background: {p.surface};
    color: {p.faint};
    border: 1px solid {p.line};
}}
QPushButton[kind="cycle"],
QPushButton[kind="speed"] {{
    background: transparent;
    border: none;
    border-radius: 0;
    min-width: {chip_w}px;
    /* Chips are fixed-height too — horizontal padding only. */
    min-height: {chip_h}px;
    max-height: {chip_h}px;
    padding: 0 {px(SPACE_SM)}px;
    color: {p.text};
    font-weight: 500;
}}
QPushButton[kind="cycle"] {{
    min-width: {cycle_w}px;
}}
QPushButton[kind="cycle"]:hover,
QPushButton[kind="speed"]:hover {{
    background: {p.surface_3};
}}
QPushButton[kind="cycle"]:pressed,
QPushButton[kind="speed"]:pressed {{
    background: {p.surface};
}}
QPushButton[kind="cycle"]:checked,
QPushButton[kind="speed"]:checked {{
    background: {p.selection};
    color: {p.accent_text};
    border: none;
    font-weight: 700;
}}
QPushButton[kind="cycle"]:focus,
QPushButton[kind="speed"]:focus {{
    border: {focus_w}px solid {p.focus};
    border-radius: {RADIUS_SM}px;
}}
QPushButton[kind="cycle"]:disabled,
QPushButton[kind="speed"]:disabled {{
    color: {p.faint};
    background: transparent;
    border: none;
}}
QPushButton#cycleChip_1 {{
    border-top-left-radius: {RADIUS_MD}px;
    border-bottom-left-radius: {RADIUS_MD}px;
}}
QPushButton#speedChip_0_5 {{
    border-top-left-radius: {RADIUS_MD}px;
    border-bottom-left-radius: {RADIUS_MD}px;
}}
QPushButton#cycleChip_10, QPushButton#cycleChip_100,
QPushButton#speedChip_1_0, QPushButton#speedChip_1_5, QPushButton#speedChip_2_0 {{
    border-left: 1px solid {p.line};
}}
QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox, QPlainTextEdit {{
    background: {p.surface_2};
    border: 1px solid {p.line_strong};
    border-radius: {RADIUS_MD}px;
    padding: {pad_v}px {pad_v}px;
    min-height: {input_h - 2 * pad_v}px;
    selection-background-color: {p.accent};
    selection-color: {p.accent_ink};
}}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled,
QComboBox:disabled, QPlainTextEdit:disabled {{
    color: {p.faint};
    background: {p.surface};
}}
QLineEdit#eventFilter {{
    background: {p.surface_2};
    border: 1px solid {p.line};
    border-radius: {RADIUS_LG}px;
}}
/* The number box is the custom slot of its segmented control, so it drops its
   own border and background and sits inside the cluster's single frame. */
/* No min/max-height here: QSS heights are content-box, so Qt adds the spin's
   frame on top and the widget ends up taller than the fixed height the code
   sets, which squeezes the arrows. The code owns this height. */
QSpinBox#cyclesSpin, QDoubleSpinBox#speedSpin {{
    padding: 0 {pad_v}px;
    background: transparent;
    border: none;
    border-radius: 0;
}}
QSpinBox#cyclesSpin:focus, QDoubleSpinBox#speedSpin:focus {{
    border: {focus_w}px solid {p.focus};
    border-radius: {RADIUS_SM}px;
}}
QSpinBox#cyclesSpin:hover, QDoubleSpinBox#speedSpin:hover {{
    background: {p.surface_3};
}}
QComboBox::drop-down {{
    border: none;
    width: {px(22)}px;
}}
QComboBox QAbstractItemView {{
    background: {p.surface};
    border: 1px solid {p.line_strong};
    selection-background-color: {p.selection};
    selection-color: {p.text};
    outline: none;
}}
QListWidget {{
    background: {p.surface};
    border: 1px solid {p.line};
    border-radius: {RADIUS_XL}px;
    padding: {px(SPACE_SM)}px;
    outline: none;
}}
QListWidget::item {{
    border-radius: {RADIUS_LG}px;
    margin: {px(3)}px {px(2)}px;
    padding: 0;
    background: transparent;
    border: {focus_w}px solid transparent;
}}
QListWidget::item:selected {{
    background: {p.selection};
    border: {focus_w}px solid {p.accent};
}}
QListWidget::item:hover:!selected {{
    background: {p.surface_2};
}}
QScrollArea {{
    background: transparent;
    border: none;
}}
/* A scroll area's viewport and its content widget paint themselves; without
   these the inspector sits on the host OS window colour. */
QScrollArea > QWidget > QWidget {{
    background: {p.ground};
}}
QWidget#inspector {{
    background: {p.ground};
}}
QWidget#inspector QLabel {{
    background: transparent;
}}
QScrollBar:vertical {{
    background: transparent;
    width: {px(12)}px;
    margin: {px(SPACE_XS)}px {px(2)}px;
}}
QScrollBar::handle:vertical {{
    background: {p.line_strong};
    border-radius: {px(SPACE_XS)}px;
    min-height: {px(32)}px;
}}
QScrollBar::handle:vertical:hover {{
    background: {p.muted};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QLabel[role="muted"] {{
    color: {p.muted};
}}
QLabel[role="hint"] {{
    color: {p.muted};
    font-size: {hint}px;
}}
QLabel[role="title"] {{
    font-size: {title}px;
    font-weight: 650;
}}
QLabel[role="section"] {{
    color: {p.muted};
    font-size: {section}px;
    font-weight: 700;
    letter-spacing: 0.8px;
}}
QLabel[role="chip"] {{
    font-size: {chip_type}px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QLabel[role="empty"] {{
    color: {p.muted};
    font-size: {body}px;
}}
QLabel[role="metric"] {{
    color: {p.muted};
    font-family: {MONO_STACK};
    font-size: {hint}px;
}}
QLabel[role="kbd"] {{
    color: {p.text};
    background: {p.surface_2};
    border: 1px solid {p.line_strong};
    border-radius: {RADIUS_SM}px;
    padding: {px(2)}px {px(SPACE_SM)}px;
    font-family: {MONO_STACK};
    font-size: {hint}px;
}}
QLabel#banner {{
    border-radius: {RADIUS_MD}px;
    padding: {pad_v}px;
    font-weight: 600;
}}
QLabel#banner[tone="record"] {{
    color: {p.record};
    background: {p.surface};
    border: 1px solid {p.record_idle};
}}
QLabel#banner[tone="ok"] {{
    color: {p.ok};
    background: {p.surface};
    border: 1px solid {p.line};
}}
QCheckBox, QRadioButton {{
    spacing: {px(SPACE_SM)}px;
    padding: {px(2)}px 0;
}}
QCheckBox::indicator, QRadioButton::indicator {{
    width: {px(SPACE_LG)}px;
    height: {px(SPACE_LG)}px;
    border-radius: {SPACE_XS}px;
    border: 1px solid {p.line_strong};
    background: {p.surface_2};
}}
QCheckBox::indicator:checked {{
    background: {p.accent};
    border-color: {p.accent};
}}
QCheckBox:focus, QRadioButton:focus {{
    border: {focus_w}px solid {p.focus};
    border-radius: {RADIUS_SM}px;
}}
QSlider::groove:horizontal {{
    height: {px(SPACE_XS)}px;
    background: {p.surface_3};
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    width: {px(16)}px;
    height: {px(16)}px;
    margin: {px(-6)}px 0;
    border-radius: {px(8)}px;
    background: {p.accent};
}}
QGroupBox {{
    border: 1px solid {p.line};
    border-radius: {RADIUS_MD}px;
    margin-top: {px(14)}px;
    padding: {pad_h}px {pad_h}px {pad_v}px {pad_h}px;
    background: {p.surface};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: {pad_h}px;
    padding: 0 {pad_v}px;
    color: {p.muted};
}}
QStatusBar {{
    background: {p.ground};
    border-top: 1px solid {p.line};
    color: {p.muted};
}}
QStatusBar::item {{
    border: none;
}}
QSplitter::handle {{
    background: {p.ground};
    width: {px(SPACE_SM)}px;
}}
QSplitter::handle:hover {{
    background: {p.line};
}}
QSplitter::handle:vertical {{
    height: {px(SPACE_SM)}px;
    width: auto;
}}
QFrame#card {{
    background: {p.surface};
    border: 1px solid {p.line};
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
    font-size: {chip_type}px;
    font-weight: 700;
    letter-spacing: 0.5px;
}}
QWidget#eventCard QLabel#eventDelay {{
    font-family: {MONO_STACK};
    font-size: {hint}px;
    min-width: {px(76)}px;
}}
QWidget#eventCard QLabel#eventDetail {{
    font-family: {MONO_STACK};
    font-size: {hint}px;
}}
QWidget#eventCard[selected="true"] {{
    background: {p.selection};
    border-radius: {RADIUS_MD}px;
}}
QWidget#eventCard[playing="true"] {{
    background: {p.selection};
    border: 1px solid {p.ok};
    border-radius: {RADIUS_MD}px;
}}
QWidget#eventCard[state="disabled"] QLabel#eventTitle,
QWidget#eventCard[state="disabled"] QLabel#eventKind,
QWidget#eventCard[state="disabled"] QLabel#eventDetail,
QWidget#eventCard[state="disabled"] QLabel#eventDelay {{
    color: {p.faint};
}}
"""


# --- Back-compat aliases -----------------------------------------------------
# Existing call sites import these names directly. They track the default theme;
# anything that has to follow a live theme switch calls active() instead.
BG = DARK.ground
SURFACE = DARK.surface
SURFACE_2 = DARK.surface_2
SURFACE_3 = DARK.surface_3
BORDER = DARK.line
TEXT = DARK.text
MUTED = DARK.muted
ACCENT = DARK.accent
ACCENT_DIM = DARK.accent_hover
RECORD = DARK.record
RECORD_IDLE = DARK.record_idle
OK = DARK.ok
MOUSE = DARK.mouse
KEY = DARK.key
WAIT = DARK.wait
TRIGGER = DARK.trigger
ORIGIN = DARK.origin
NOTE = DARK.note
PRIMARY_TEXT = DARK.accent_ink
PRIMARY_HOVER = DARK.accent_hover
PLAYING_TEXT = DARK.ok_ink
RECORDING_EDGE = DARK.record
DISABLED_TEXT = DARK.faint
DISABLED_FILL = DARK.surface
SELECTED_FILL = DARK.selection

TYPE_COLOR = DARK.type_colors()

QSS = build_qss(DARK, 1.0)
