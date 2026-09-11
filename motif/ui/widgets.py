"""Path canvas, event cards, and inspector — the parts people actually touch."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PySide6.QtWidgets import (
    QAbstractButton,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from motif.models import (
    EVENT_LABELS,
    Event,
    EventType,
    HumanizePreset,
    HumanizeSettings,
    PathStyle,
    PlayMode,
    Script,
    apply_swipe_direction,
    event_kind_label,
    is_app_switch,
    space_fallback_label,
    swipe_shortcut_key,
)
from motif.screen import Display
from motif.ui import theme
from motif.ui.theme import (
    CARD_PAD_H,
    CARD_PAD_V,
    RADIUS_SWATCH,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SWATCH_H,
    SWATCH_W,
    TYPE_CHIP,
)

EMPTY_PANE_COPY = "No events yet\nRecord (F9) or click + Add"

# Extra inspector groups per event type. "event" and "notes" are always shown
# when an event is selected. Add a type here when you add EventType + fields.
INSPECTOR_GROUPS: dict[EventType, frozenset[str]] = {
    EventType.MOVE: frozenset({"pos", "motion"}),
    EventType.CLICK: frozenset({"pos", "click", "motion"}),
    EventType.SCROLL: frozenset({"pos", "scroll"}),
    EventType.KEY_DOWN: frozenset({"key"}),
    EventType.KEY_UP: frozenset({"key"}),
    EventType.WAIT: frozenset(),
    EventType.WAIT_PIXEL: frozenset({"pos", "pixel"}),
    EventType.WAIT_PIXEL_CHANGE: frozenset({"pos", "pixel"}),
    EventType.GO_ORIGIN: frozenset({"motion"}),
    EventType.COMMENT: frozenset(),
    EventType.SWIPE: frozenset({"swipe"}),
}
ALWAYS_EVENT_GROUPS = frozenset({"event", "notes"})


def polish(widget: QWidget) -> None:
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def describe(widget: QWidget, name: str, description: str = "", *, tooltip: bool = True) -> QWidget:
    """Give a control a screen-reader name (and usually the same text as a tooltip).

    Qt exposes accessibleName / accessibleDescription to VoiceOver, Narrator and
    Orca. A tooltip alone reaches neither a screen reader nor a keyboard user, so
    anything worth a tooltip is worth a name.
    """
    widget.setAccessibleName(name)
    if description:
        widget.setAccessibleDescription(description)
    if tooltip:
        widget.setToolTip(description or name)
    return widget


def announce(widget: QWidget, message: str) -> None:
    """Push a live-region style announcement to assistive tech, best effort.

    Status-bar text changes are silent for screen-reader users; an Alert event on
    the widget that changed is the Qt equivalent of aria-live="polite".
    """
    if not message:
        return
    try:
        from PySide6.QtGui import QAccessible, QAccessibleEvent

        if not QAccessible.isActive():
            return
        QAccessible.updateAccessibility(QAccessibleEvent(widget, QAccessible.Event.Alert))
    except Exception:
        # Offscreen / headless platforms have no accessibility bridge.
        return


def separator(*, vertical: bool = True, inset: int = 0) -> QFrame:
    """Hairline rule between toolbar zones.

    Grouping by whitespace alone stops reading as grouping once a row is busy;
    a rule says "these belong together, those do not" without adding weight.
    """
    line = QFrame()
    line.setObjectName("zoneSeparator")
    line.setProperty("role", "sep")
    if vertical:
        line.setFrameShape(QFrame.Shape.VLine)
        line.setFixedWidth(1)
        line.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        if inset:
            line.setContentsMargins(0, inset, 0, inset)
    else:
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFixedHeight(1)
        line.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
    line.setFrameShadow(QFrame.Shadow.Plain)
    line.setFocusPolicy(Qt.FocusPolicy.NoFocus)
    # Decoration only: never announce a rule to a screen reader.
    line.setAccessibleName("")
    return line


def kbd_label(text: str) -> QLabel:
    """A keycap — monospace, boxed, so shortcuts read as shortcuts."""
    label = QLabel(text)
    label.setProperty("role", "kbd")
    label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    return label


def metric_label(text: str = "") -> QLabel:
    """Tabular-figure readout, so digits line up down a column."""
    label = QLabel(text)
    label.setProperty("role", "metric")
    return label


def apply_button_kind(btn: QAbstractButton, kind: str) -> None:
    """primary | secondary/ghost | danger/record | recording | playing | stop | cycle | speed."""
    btn.setProperty("kind", kind)
    polish(btn)


def apply_banner(label: QLabel, text: str = "", tone: str = "") -> None:
    label.setText(text)
    label.setProperty("tone", tone)
    label.setVisible(bool(text))
    polish(label)


def section_header(title: str) -> QLabel:
    label = QLabel(title)
    label.setProperty("role", "section")
    return label


def empty_state_label(text: str) -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "empty")
    return label


def attach_empty_overlay(host: QWidget, text: str = EMPTY_PANE_COPY) -> QLabel:
    label = empty_state_label(text)
    label.setAlignment(Qt.AlignmentFlag.AlignCenter)
    label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    label.setParent(host)
    return label


def layout_empty_overlay(
    label: QLabel,
    rect: QRect,
    *,
    visible: bool,
    pad: int = 24,
    top: int = 16,
) -> None:
    label.setVisible(visible)
    if not visible:
        return
    label.setGeometry(rect.adjusted(pad, top, -pad, -16))
    label.raise_()


def hint_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setWordWrap(True)
    label.setProperty("role", "hint")
    return label


def section_box(title: str) -> tuple[QWidget, QFormLayout]:
    box = QWidget()
    col = QVBoxLayout(box)
    col.setContentsMargins(0, SPACE_SM, 0, SPACE_MD)
    col.setSpacing(SPACE_MD)
    if title:
        col.addWidget(section_header(title))
    form = QFormLayout()
    form.setContentsMargins(0, 0, 0, 0)
    form.setHorizontalSpacing(SPACE_LG)
    form.setVerticalSpacing(SPACE_MD)
    form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
    form.setLabelAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
    form.setFormAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    col.addLayout(form)
    return box, form


def inspector_groups_for(event: Event | None) -> frozenset[str]:
    if event is None:
        return frozenset()
    groups = ALWAYS_EVENT_GROUPS | INSPECTOR_GROUPS.get(event.type_enum(), frozenset())
    if event.has_position():
        groups = groups | {"pos"}
    return groups


def set_visible_groups(boxes: dict[str, QWidget], names: frozenset[str]) -> None:
    for name, widget in boxes.items():
        widget.setVisible(name in names)


def ui_font(widget: QWidget, size: int) -> QFont:
    font = QFont(widget.font())
    if size > 0:
        font.setPointSize(size)
    return font


def apply_swatch(frame: QFrame, color: str) -> None:
    """10×34 rounded type chip — same size on every event card."""
    frame.setFixedSize(SWATCH_W, SWATCH_H)
    frame.setStyleSheet(f"background:{color}; border:none; border-radius:{RADIUS_SWATCH}px;")


def apply_type_tint(label: QLabel, color: str) -> None:
    pal = label.palette()
    pal.setColor(QPalette.ColorRole.WindowText, QColor(color))
    label.setPalette(pal)
    label.setForegroundRole(QPalette.ColorRole.WindowText)


def type_color(event: Event) -> QColor:
    """Type colour from the live palette — the light theme needs darker inks."""
    return QColor(theme.type_color_for(event.type_enum()))


def event_accessible_text(index: int, total: int, event: Event) -> str:
    """One spoken line per row: position, kind, name, detail, timing, state.

    The card shows this as a colour chip plus three labels; a screen reader gets
    no layout, so the row has to read as a sentence.
    """
    parts = [
        f"{index} of {total}",
        event_kind_label(event),
        event.display_name(),
        event.summary(),
        f"{event.delay_ms} milliseconds before",
    ]
    if not event.enabled:
        parts.append("skipped")
    return ", ".join(part for part in parts if part)


def event_screen_xy(script: Script, event: Event) -> tuple[int, int]:
    """Map an event’s stored coords onto the screen (origin + x/y)."""
    if script.origin_set:
        return script.origin_x + event.x, script.origin_y + event.y
    return event.x, event.y


def path_screen_xy(script: Script, x: int, y: int) -> tuple[int, int]:
    if script.origin_set:
        return script.origin_x + x, script.origin_y + y
    return x, y


def fit_screen_rect(screen: QRect, view: QRect, pad: int = 16) -> QRect:
    """Letterbox `screen` inside `view` so the whole display fits."""
    inner = view.adjusted(pad, pad, -pad, -pad)
    if screen.width() <= 0 or screen.height() <= 0 or inner.width() <= 0 or inner.height() <= 0:
        return inner
    scale = min(inner.width() / screen.width(), inner.height() / screen.height())
    width = max(1, int(screen.width() * scale))
    height = max(1, int(screen.height() * scale))
    x = inner.x() + (inner.width() - width) // 2
    y = inner.y() + (inner.height() - height) // 2
    return QRect(x, y, width, height)


def map_screen_point(sx: int, sy: int, screen: QRect, fitted: QRect) -> QPoint:
    """Map a global logical point (pynput / Qt) through a letterboxed desktop rect."""
    if screen.width() <= 0 or screen.height() <= 0:
        return QPoint(fitted.x(), fitted.y())
    nx = (sx - screen.x()) / screen.width()
    ny = (sy - screen.y()) / screen.height()
    return QPoint(
        fitted.x() + int(round(nx * fitted.width())),
        fitted.y() + int(round(ny * fitted.height())),
    )


def map_screen_rect(src: QRect, screen: QRect, fitted: QRect) -> QRect:
    tl = map_screen_point(src.x(), src.y(), screen, fitted)
    br = map_screen_point(src.x() + src.width(), src.y() + src.height(), screen, fitted)
    return QRect(tl.x(), tl.y(), max(1, br.x() - tl.x()), max(1, br.y() - tl.y()))


def displays_union_rect(displays: list[Display]) -> QRect:
    if not displays:
        return QRect(0, 0, 1920, 1080)
    x1 = min(d.x for d in displays)
    y1 = min(d.y for d in displays)
    x2 = max(d.x + d.width for d in displays)
    y2 = max(d.y + d.height for d in displays)
    return QRect(x1, y1, max(1, x2 - x1), max(1, y2 - y1))


def spatial_events(script: Script) -> list[Event]:
    return [e for e in script.events if e.has_position()]


def step_selection(script: Script, current_id: str, delta: int) -> str:
    """Next/previous positioned event — keyboard parity for the click-only canvases."""
    events = spatial_events(script)
    if not events:
        return ""
    ids = [e.id for e in events]
    if current_id in ids:
        index = (ids.index(current_id) + delta) % len(ids)
    else:
        index = 0 if delta >= 0 else len(ids) - 1
    return ids[index]


class CanvasNavigation:
    """Arrow-key selection for the painted views, so they are not mouse-only."""

    event_clicked: Signal
    script: Script
    selected_id: str

    def keyPressEvent(self, event) -> None:  # noqa: N802
        keys_next = (Qt.Key.Key_Right, Qt.Key.Key_Down, Qt.Key.Key_Tab)
        keys_prev = (Qt.Key.Key_Left, Qt.Key.Key_Up)
        if event.key() in keys_next and event.key() != Qt.Key.Key_Tab:
            target = step_selection(self.script, self.selected_id, 1)
        elif event.key() in keys_prev:
            target = step_selection(self.script, self.selected_id, -1)
        elif event.key() in (Qt.Key.Key_Home, Qt.Key.Key_End):
            events = spatial_events(self.script)
            target = "" if not events else (
                events[0].id if event.key() == Qt.Key.Key_Home else events[-1].id
            )
        else:
            super().keyPressEvent(event)
            return
        if target:
            self.event_clicked.emit(target)
        event.accept()

    def _describe_selection(self) -> str:
        events = spatial_events(self.script)
        if not events:
            return "No positioned events yet."
        for i, ev in enumerate(events, 1):
            if ev.id == self.selected_id:
                return event_accessible_text(i, len(events), ev)
        return f"{len(events)} positioned events. Use arrow keys to step through them."


class PathCanvas(CanvasNavigation, QWidget):
    event_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.script = Script()
        self.selected_id = ""
        self.setObjectName("pathCanvas")
        self.setMinimumHeight(118)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.MinimumExpanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        describe(
            self,
            "Path preview",
            "The journey, relative to zero ground. Click a dot or use the arrow "
            "keys to select that event. Origin is the gold cross.",
        )
        self.empty = attach_empty_overlay(self)
        self._sync_empty()

    def set_script(self, script: Script, selected_id: str = "") -> None:
        self.script = script
        self.selected_id = selected_id
        self.setAccessibleDescription(self._describe_selection())
        self._sync_empty()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_empty()

    def _sync_empty(self) -> None:
        layout_empty_overlay(self.empty, self.rect(), visible=not self.script.events)

    def _points(self) -> list[tuple[int, int, Event]]:
        pts: list[tuple[int, int, Event]] = []
        for event in self.script.events:
            if event.has_position():
                pts.append((event.x, event.y, event))
            for raw in event.points[:: max(1, len(event.points) // 24)]:
                pts.append((int(raw["x"]), int(raw["y"]), event))
        return pts

    def _bounds(self) -> tuple[int, int, int, int]:
        xs = [0]
        ys = [0]
        for x, y, _ in self._points():
            xs.append(x)
            ys.append(y)
        return min(xs), min(ys), max(xs), max(ys)

    def _map(self, x: int, y: int) -> QPoint:
        minx, miny, maxx, maxy = self._bounds()
        pad = 28
        w = max(self.width() - pad * 2, 1)
        h = max(self.height() - pad * 2, 1)
        span_x = max(maxx - minx, 40)
        span_y = max(maxy - miny, 40)
        nx = pad + (x - minx) / span_x * w
        ny = pad + (y - miny) / span_y * h
        return QPoint(int(nx), int(ny))

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = theme.active()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(pal.surface))
        edge = QColor(pal.focus) if self.hasFocus() else QColor(pal.line)
        painter.setPen(QPen(edge, pal.focus_width if self.hasFocus() else 1))
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 14, 14)

        if not self.script.events:
            return

        path = QPainterPath()
        first = True
        for ev in self.script.events:
            coords: list[tuple[int, int]] = []
            if ev.points:
                coords.extend((int(p["x"]), int(p["y"])) for p in ev.points)
            elif ev.has_position():
                coords.append((ev.x, ev.y))
            for x, y in coords:
                pt = self._map(x, y)
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
        painter.setPen(QPen(QColor(pal.accent), 2))
        painter.drawPath(path)

        origin = self._map(0, 0)
        painter.setPen(QPen(QColor(pal.origin), 2))
        painter.drawLine(origin.x() - 8, origin.y(), origin.x() + 8, origin.y())
        painter.drawLine(origin.x(), origin.y() - 8, origin.x(), origin.y() + 8)

        for ev in self.script.events:
            if ev.type_enum() == EventType.MOVE and ev.points:
                continue
            if not ev.has_position():
                continue
            pt = self._map(ev.x, ev.y)
            color = type_color(ev)
            selected = ev.id == self.selected_id
            radius = 7 if selected else 5
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt, radius, radius)
            if selected:
                # Shape, not just colour: the selected dot also gets a ring.
                painter.setPen(QPen(QColor(pal.text), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pt, radius + 4, radius + 4)

        painter.setPen(QColor(pal.muted))
        painter.setFont(ui_font(self, TYPE_CHIP))
        # Caption sits bottom-left: at the top it collides with the 0,0 marker
        # whenever the origin maps into the top-left corner.
        painter.drawText(14, self.height() - 12, "Zero ground")
        painter.drawText(origin + QPoint(10, -8), "0,0")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        click = event.position().toPoint()
        best = None
        best_d = 18
        for ev in self.script.events:
            if not ev.has_position():
                continue
            pt = self._map(ev.x, ev.y)
            d = (click - pt).manhattanLength()
            if d < best_d:
                best = ev
                best_d = d
        if best:
            self.event_clicked.emit(best.id)


class ScreenHistoryView(CanvasNavigation, QWidget):
    """Letterboxed virtual desktop with events at their global logical positions."""

    event_clicked = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.script = Script()
        self.selected_id = ""
        self.screen_rect = QRect(0, 0, 1920, 1080)
        self.displays: list[Display] = []
        self.setObjectName("screenHistory")
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        describe(
            self,
            "Screen history",
            "All displays as one desktop. Clicks stay on the monitor where you "
            "recorded them. Click a dot or use the arrow keys to select an event.",
        )
        self.empty = attach_empty_overlay(self)
        self._sync_empty()

    def set_script(self, script: Script, selected_id: str = "") -> None:
        self.script = script
        self.selected_id = selected_id
        self.setAccessibleDescription(self._describe_selection())
        self._sync_empty()
        self.update()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_empty()

    def _sync_empty(self) -> None:
        layout_empty_overlay(self.empty, self._fitted(), visible=not self.script.events, top=40)

    def set_screen_rect(self, rect: QRect) -> None:
        if rect.width() <= 0 or rect.height() <= 0:
            return
        if rect != self.screen_rect or not self.displays:
            self.screen_rect = QRect(rect)
            if not self.displays:
                self.displays = [
                    Display(index=1, x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height())
                ]
            self.update()

    def set_displays(self, displays: list[Display], desktop: QRect | None = None) -> None:
        self.displays = list(displays)
        if desktop is not None and desktop.width() > 0 and desktop.height() > 0:
            self.screen_rect = QRect(desktop)
        elif self.displays:
            self.screen_rect = displays_union_rect(self.displays)
        self.update()

    def _fitted(self) -> QRect:
        return fit_screen_rect(self.screen_rect, self.rect(), pad=18)

    def _map(self, sx: int, sy: int) -> QPoint:
        return map_screen_point(sx, sy, self.screen_rect, self._fitted())

    def _headline(self) -> str:
        if len(self.displays) > 1:
            return "All displays"
        if self.displays:
            return self.displays[0].label()
        screen = self.screen_rect
        return f"Display 1 · {screen.width()}×{screen.height()}"

    def paintEvent(self, event) -> None:  # noqa: N802
        pal = theme.active()
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(pal.ground))
        if self.hasFocus():
            painter.setPen(QPen(QColor(pal.focus), pal.focus_width))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self.rect().adjusted(1, 1, -2, -2), 12, 12)
        fitted = self._fitted()
        screen = self.screen_rect
        many = len(self.displays) > 1

        if many:
            for display in self.displays:
                tile = map_screen_rect(
                    QRect(display.x, display.y, display.width, display.height),
                    screen,
                    fitted,
                )
                painter.setBrush(QColor(pal.surface))
                painter.setPen(QPen(QColor(pal.line), 1))
                painter.drawRoundedRect(tile, 8, 8)
                painter.setPen(QColor(pal.muted))
                painter.setFont(ui_font(self, TYPE_CHIP))
                painter.drawText(
                    tile.adjusted(10, 6, -10, 0),
                    Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
                    display.label(),
                )
        else:
            painter.setBrush(QColor(pal.surface))
            painter.setPen(QPen(QColor(pal.line), 1))
            painter.drawRoundedRect(fitted, 10, 10)

        painter.setPen(QColor(pal.muted))
        painter.setFont(ui_font(self, TYPE_CHIP))
        label_target = fitted if not many else self.rect()
        painter.drawText(
            label_target.adjusted(12, 8, -12, 0),
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop,
            self._headline(),
        )

        if not self.script.events:
            return

        path = QPainterPath()
        first = True
        for ev in self.script.events:
            coords: list[tuple[int, int]] = []
            if ev.points:
                coords.extend(path_screen_xy(self.script, int(p["x"]), int(p["y"])) for p in ev.points)
            elif ev.has_position():
                coords.append(event_screen_xy(self.script, ev))
            for sx, sy in coords:
                pt = self._map(sx, sy)
                if first:
                    path.moveTo(pt)
                    first = False
                else:
                    path.lineTo(pt)
        painter.setPen(QPen(QColor(pal.accent), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        ox, oy = (self.script.origin_x, self.script.origin_y) if self.script.origin_set else (0, 0)
        origin = self._map(ox, oy)
        painter.setPen(QPen(QColor(pal.origin), 2))
        painter.drawLine(origin.x() - 8, origin.y(), origin.x() + 8, origin.y())
        painter.drawLine(origin.x(), origin.y() - 8, origin.x(), origin.y() + 8)
        painter.setPen(QColor(pal.muted))
        painter.drawText(origin + QPoint(10, -8), f"{ox},{oy}")

        for ev in self.script.events:
            if ev.type_enum() == EventType.MOVE and ev.points:
                continue
            if not ev.has_position():
                continue
            sx, sy = event_screen_xy(self.script, ev)
            pt = self._map(sx, sy)
            color = type_color(ev)
            selected = ev.id == self.selected_id
            radius = 8 if selected else 5
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt, radius, radius)
            if selected:
                painter.setPen(QPen(QColor(pal.text), 2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pt, radius + 5, radius + 5)

    def mousePressEvent(self, event) -> None:  # noqa: N802
        click = event.position().toPoint()
        best = None
        best_d = 20
        for ev in self.script.events:
            if not ev.has_position():
                continue
            sx, sy = event_screen_xy(self.script, ev)
            pt = self._map(sx, sy)
            d = (click - pt).manhattanLength()
            if d < best_d:
                best = ev
                best_d = d
        if best:
            self.event_clicked.emit(best.id)


class EventCard(QWidget):
    def __init__(self, event: Event, selected: bool = False, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = event
        self.setObjectName("eventCard")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(CARD_PAD_H, CARD_PAD_V, CARD_PAD_H, CARD_PAD_V)
        layout.setSpacing(SPACE_SM)

        self.swatch = QFrame()
        self.swatch.setObjectName("typeSwatch")
        apply_swatch(self.swatch, theme.type_color_for(event.type_enum()))
        layout.addWidget(self.swatch)

        text = QVBoxLayout()
        text.setSpacing(1)
        head = QHBoxLayout()
        head.setContentsMargins(0, 0, 0, 0)
        head.setSpacing(SPACE_SM)
        kind_label = event_kind_label(event)
        self.kind = QLabel(kind_label.upper())
        self.kind.setObjectName("eventKind")
        self.kind.setProperty("role", "chip")
        self.kind.setWordWrap(False)
        self.kind.setSizePolicy(QSizePolicy.Policy.Maximum, QSizePolicy.Policy.Fixed)
        self.title = QLabel(event.display_name())
        self.title.setObjectName("eventTitle")
        self.title.setWordWrap(False)
        self.title.setMinimumWidth(40)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.title.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        head.addWidget(self.kind)
        head.addWidget(self.title, 1)
        self.detail = QLabel(event.summary())
        self.detail.setObjectName("eventDetail")
        self.detail.setProperty("role", "hint")
        self.detail.setWordWrap(False)
        self.detail.setMinimumWidth(40)
        text.addLayout(head)
        text.addWidget(self.detail)
        layout.addLayout(text, 1)

        delay_text = f"{event.delay_ms} ms"
        if not event.enabled:
            delay_text = f"Off · {delay_text}"
        self.delay = QLabel(delay_text)
        self.delay.setObjectName("eventDelay")
        self.delay.setProperty("role", "muted")
        self.delay.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.delay.setWordWrap(False)
        self.delay.setFixedWidth(76)
        self.delay.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        layout.addWidget(self.delay)
        self.playing = False
        # The card is one thing to a screen reader, not five stray labels.
        self.setAccessibleName(f"{kind_label}, {event.display_name()}")
        self.setAccessibleDescription(event.summary())
        for child in (self.swatch, self.kind, self.title, self.detail, self.delay):
            child.setAccessibleName("")
        self.set_card_state(selected, event.enabled)

    def set_card_state(self, selected: bool, enabled: bool = True) -> None:
        pal = theme.active()
        self.setProperty("selected", "true" if selected else "false")
        self.setProperty("state", "enabled" if enabled else "disabled")
        color = theme.type_color_for(self.model.type_enum()) if enabled else pal.line_strong
        apply_swatch(self.swatch, color)
        apply_type_tint(self.kind, color if enabled else pal.faint)
        polish(self)

    def set_selected(self, selected: bool) -> None:
        self.set_card_state(selected, self.model.enabled)

    def set_playing(self, playing: bool) -> None:
        """Mark the row Replay is on — never by moving focus, which raises Motif."""
        if playing == self.playing:
            return
        self.playing = playing
        self.setProperty("playing", "true" if playing else "false")
        polish(self)

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(360, 58)


def event_matches_filter(event: Event, needle: str) -> bool:
    """Filter across everything visible on the card, not just the name."""
    text = needle.strip().lower()
    if not text:
        return True
    haystack = " ".join(
        (
            event.display_name(),
            event_kind_label(event),
            event.summary(),
            event.key,
            event.app,
            event.bundle_id,
            event.notes,
        )
    ).lower()
    return all(word in haystack for word in text.split())


class EventList(QListWidget):
    order_changed = Signal()
    delete_requested = Signal()
    move_requested = Signal(int)
    toggle_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self.setSpacing(2)
        self.setMinimumHeight(168)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._filter = ""
        describe(
            self,
            "Event list",
            "The recorded steps in order. Alt+Up and Alt+Down move the selected "
            "step, Space skips or restores it, Delete removes it.",
            tooltip=False,
        )
        self.model().rowsMoved.connect(lambda *_: self.order_changed.emit())
        self.itemSelectionChanged.connect(self._sync_card_selection)
        self.empty = attach_empty_overlay(self.viewport())
        self._sync_empty()

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.delete_requested.emit()
            return
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier)
        if alt and event.key() == Qt.Key.Key_Up:
            self.move_requested.emit(-1)
            return
        if alt and event.key() == Qt.Key.Key_Down:
            self.move_requested.emit(1)
            return
        if event.key() == Qt.Key.Key_Space:
            self.toggle_requested.emit()
            return
        super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_empty()

    def _sync_empty(self) -> None:
        layout_empty_overlay(self.empty, self.viewport().rect(), visible=self.count() == 0)

    def set_filter(self, text: str) -> int:
        """Hide non-matching rows. Rows are hidden, never dropped, so reorder is safe."""
        self._filter = text or ""
        shown = 0
        for i in range(self.count()):
            item = self.item(i)
            card = self.itemWidget(item)
            match = True
            if isinstance(card, EventCard):
                match = event_matches_filter(card.model, self._filter)
            item.setHidden(not match)
            shown += 1 if match else 0
        return shown

    def rebuild(self, script: Script, selected_id: str = "") -> None:
        current = selected_id
        total = len(script.events)
        self.blockSignals(True)
        self.clear()
        for i, event in enumerate(script.events, 1):
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, event.id)
            # What VoiceOver reads for the row; the widget below is visual only.
            item.setData(
                Qt.ItemDataRole.AccessibleTextRole, event_accessible_text(i, total, event)
            )
            selected = event.id == current
            card = EventCard(event, selected=selected)
            item.setSizeHint(card.sizeHint())
            self.addItem(item)
            self.setItemWidget(item, card)
            if selected:
                self.setCurrentItem(item)
        self.blockSignals(False)
        if self.currentItem() is None and self.count():
            self.setCurrentRow(0)
        self._sync_card_selection()
        self.set_filter(self._filter)
        self._sync_empty()

    def mark_playing(self, event_id: str) -> None:
        """Highlight the replaying row without selecting it (selection raises Motif)."""
        for i in range(self.count()):
            card = self.itemWidget(self.item(i))
            if isinstance(card, EventCard):
                card.set_playing(bool(event_id) and card.model.id == event_id)

    def _sync_card_selection(self) -> None:
        chosen = set(self.selected_ids())
        current = self.selected_id()
        if current:
            chosen.add(current)
        for i in range(self.count()):
            item = self.item(i)
            card = self.itemWidget(item)
            if isinstance(card, EventCard):
                card.set_selected(item.data(Qt.ItemDataRole.UserRole) in chosen)

    def ordered_ids(self) -> list[str]:
        ids = []
        for i in range(self.count()):
            ids.append(self.item(i).data(Qt.ItemDataRole.UserRole))
        return ids

    def selected_id(self) -> str:
        item = self.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""

    def selected_ids(self) -> list[str]:
        return [item.data(Qt.ItemDataRole.UserRole) for item in self.selectedItems()]


class Inspector(QWidget):
    values_changed = Signal()
    pick_pixel = Signal()
    rebase_requested = Signal()
    origin_to_cursor = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.script = Script()
        self.active: Event | None = None
        self._guard = False
        self.setObjectName("inspector")
        self.setMinimumWidth(280)
        self.setAccessibleName("Inspector")

        root = QVBoxLayout(self)
        root.setContentsMargins(SPACE_LG, 0, SPACE_LG, SPACE_MD)
        root.setSpacing(SPACE_MD)

        root.addWidget(section_header("INSPECTOR"))

        self.empty = empty_state_label("Record (F9) or click + Add, then select an event to edit it.")
        root.addWidget(self.empty)

        self.name_edit = QLineEdit()
        self.enabled_box = QCheckBox("Enabled")
        self.delay = QSpinBox()
        self.delay.setRange(0, 120000)
        self.delay.setSuffix(" ms")
        self.x_box = QSpinBox()
        self.y_box = QSpinBox()
        for box in (self.x_box, self.y_box):
            box.setRange(-20000, 20000)
        self.dx_box = QSpinBox()
        self.dy_box = QSpinBox()
        for box in (self.dx_box, self.dy_box):
            box.setRange(-20000, 20000)
        self.button = QComboBox()
        self.button.addItems(["left", "right", "middle"])
        self.pressed = QComboBox()
        self.pressed.addItems(["down", "up"])
        self.key = QLineEdit()
        self.color = QLineEdit("#34C759")
        # "Swatch" named the decoration, not the action.
        self.pick_color = QPushButton("Colour…")
        apply_button_kind(self.pick_color, "ghost")
        self.pick_screen = QPushButton("Pick pixel")
        apply_button_kind(self.pick_screen, "ghost")
        color_row = QHBoxLayout()
        color_row.setContentsMargins(0, 0, 0, 0)
        color_row.setSpacing(SPACE_SM)
        color_row.addWidget(self.color, 1)
        color_row.addWidget(self.pick_color)
        color_row.addWidget(self.pick_screen)
        self.color_wrap = QWidget()
        self.color_wrap.setLayout(color_row)
        self.tolerance = QSpinBox()
        self.tolerance.setRange(0, 180)
        self.match = QComboBox()
        self.match.addItems(["is", "is_not", "brighter", "darker"])
        self.match_label = QLabel("When")
        self.timeout = QSpinBox()
        self.timeout.setRange(100, 300000)
        self.timeout.setSuffix(" ms")
        self.path = QComboBox()
        self.path.addItems(["(script default)", *[s.value for s in PathStyle]])
        self.travel = QSpinBox()
        self.travel.setRange(-1, 10000)
        self.travel.setSpecialValueText("Auto")
        self.travel.setValue(-1)
        self.notes = QPlainTextEdit()
        self.notes.setFixedHeight(56)
        self.notes.setPlaceholderText("Optional note")

        self.event_box, event_form = section_box("EVENT")
        event_form.addRow("Name", self.name_edit)
        event_form.addRow("", self.enabled_box)
        event_form.addRow("Pause before", self.delay)

        self.pos_box, pos_form = section_box("POSITION")
        pos_form.addRow("X from origin", self.x_box)
        pos_form.addRow("Y from origin", self.y_box)

        self.click_box, click_form = section_box("CLICK")
        click_form.addRow("Button", self.button)
        click_form.addRow("Press", self.pressed)

        self.key_box, key_form = section_box("KEY")
        key_form.addRow("Key", self.key)

        self.scroll_box, scroll_form = section_box("SCROLL")
        scroll_form.addRow("Horizontal", self.dx_box)
        scroll_form.addRow("Vertical", self.dy_box)

        self.direction = QComboBox()
        self.direction.addItems(["left", "right", "up", "down"])
        self.app_name = QLineEdit()
        self.app_name.setPlaceholderText("Frontmost app")
        self.bundle_edit = QLineEdit()
        self.bundle_edit.setPlaceholderText("Bundle id")
        self.swipe_note = hint_label()
        self.swipe_box, swipe_form = section_box("SWITCH")
        swipe_form.addRow("App", self.app_name)
        swipe_form.addRow("Bundle", self.bundle_edit)
        swipe_form.addRow("Fallback", self.direction)
        swipe_form.addRow(self.swipe_note)

        self.pixel_box, pixel_form = section_box("PIXEL")
        pixel_form.addRow("Colour", self.color_wrap)
        pixel_form.addRow("Tolerance", self.tolerance)
        pixel_form.addRow(self.match_label, self.match)
        pixel_form.addRow("Timeout", self.timeout)

        self.motion_box, motion_form = section_box("MOTION")
        motion_form.addRow("Path", self.path)
        motion_form.addRow("Travel", self.travel)

        self.notes_box, notes_form = section_box("NOTES")
        notes_form.addRow(self.notes)

        self.form_box = QWidget()
        form_col = QVBoxLayout(self.form_box)
        form_col.setContentsMargins(0, 0, 0, 0)
        form_col.setSpacing(0)
        self.event_groups = {
            "event": self.event_box,
            "pos": self.pos_box,
            "click": self.click_box,
            "key": self.key_box,
            "scroll": self.scroll_box,
            "swipe": self.swipe_box,
            "pixel": self.pixel_box,
            "motion": self.motion_box,
            "notes": self.notes_box,
        }
        for box in self.event_groups.values():
            form_col.addWidget(box)
        root.addWidget(self.form_box)

        self.loop_box, loop_form = section_box("REPLAY")
        self.play_mode = QComboBox()
        self.play_mode.addItem("Replay at recorded origin", PlayMode.ABSOLUTE.value)
        self.play_mode.addItem("Replay from current cursor", PlayMode.FROM_CURSOR.value)
        self.play_mode.addItem("Always start at origin", PlayMode.FROM_ORIGIN.value)
        self.play_mode.setItemData(
            0,
            "Replay at the same global positions that were recorded. Moving Motif to another display does not move the clicks.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.play_mode.setItemData(
            1,
            "Offset the whole path from wherever the mouse is now. If the cursor is on another display, replay happens there.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.play_mode.setItemData(
            2,
            "Move to zero-ground first, then play relative to that origin — still the recorded display unless you move origin.",
            Qt.ItemDataRole.ToolTipRole,
        )
        self.play_mode.setToolTip(
            "Recorded origin stays on the display(s) you captured. From cursor follows the mouse, including another screen."
        )
        self.loops = QSpinBox()
        self.loops.setRange(0, 100000)
        self.loops.setSpecialValueText("Forever")
        self.gap = QSpinBox()
        self.gap.setRange(0, 60000)
        self.gap.setSuffix(" ms")
        self.return_origin = QCheckBox("Return to zero ground after each cycle")
        self.park = QCheckBox("Park at origin before each cycle")
        loop_form.addRow("Mode", self.play_mode)
        loop_form.addRow("Cycles", self.loops)
        loop_form.addRow("Gap", self.gap)
        loop_form.addRow(self.return_origin)
        loop_form.addRow(self.park)
        loop_form.addRow(
            hint_label(
                "Recorded origin uses the same global coordinates as capture — clicks stay on that display even if Motif moves. "
                "From cursor shifts the path to the mouse, so another display moves replay there."
            )
        )
        root.addWidget(self.loop_box)

        self.feel_box, feel_form = section_box("FEEL")
        self.preset = QComboBox()
        self.preset.addItems([p.value for p in HumanizePreset])
        self.speed = QDoubleSpinBox()
        self.speed.setRange(0.25, 4.0)
        self.speed.setSingleStep(0.25)
        self.speed.setDecimals(2)
        self.speed.setValue(1.0)
        self.speed.setSuffix("×")
        self.speed.setToolTip("1.0× is the recorded timing.")
        self.human_path = QComboBox()
        self.human_path.addItems([p.value for p in PathStyle])
        self.human_path.setToolTip(
            "recorded walks the mouse path from the take. snap jumps to the destination."
        )
        feel_form.addRow("Feel", self.preset)
        feel_form.addRow("Speed", self.speed)
        feel_form.addRow("Default path", self.human_path)
        feel_form.addRow(
            hint_label(
                "Replay uses the Cycles count from the transport (Once by default). Park and return only apply when those boxes are checked."
            )
        )
        root.addWidget(self.feel_box)

        self.origin_box, _origin_form = section_box("ORIGIN")
        origin_col = self.origin_box.layout()
        self.zero = QPushButton("Move everything to zero ground")
        apply_button_kind(self.zero, "primary")
        self.cursor_origin = QPushButton("Put origin at cursor")
        apply_button_kind(self.cursor_origin, "ghost")
        origin_col.addWidget(self.zero)
        origin_col.addWidget(self.cursor_origin)
        origin_col.addWidget(
            hint_label(
                "Zero ground is (0,0) of this motif. A single Replay does not park or return unless you add a Go to origin event."
            )
        )
        root.addWidget(self.origin_box)
        root.addStretch(1)

        widgets = [
            self.name_edit,
            self.enabled_box,
            self.delay,
            self.x_box,
            self.y_box,
            self.dx_box,
            self.dy_box,
            self.direction,
            self.app_name,
            self.bundle_edit,
            self.button,
            self.pressed,
            self.key,
            self.color,
            self.tolerance,
            self.match,
            self.timeout,
            self.path,
            self.travel,
            self.notes,
            self.play_mode,
            self.loops,
            self.gap,
            self.return_origin,
            self.park,
            self.preset,
            self.speed,
            self.human_path,
        ]
        for w in widgets:
            if isinstance(w, QLineEdit):
                w.textChanged.connect(self._commit)
            elif isinstance(w, QPlainTextEdit):
                w.textChanged.connect(self._commit)
            elif isinstance(w, QComboBox):
                w.currentIndexChanged.connect(self._commit)
            elif isinstance(w, (QSpinBox, QDoubleSpinBox)):
                w.valueChanged.connect(self._commit)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self._commit)
        self.pick_color.clicked.connect(self._swatch)
        self.pick_screen.clicked.connect(self.pick_pixel.emit)
        self.zero.clicked.connect(self.rebase_requested.emit)
        self.cursor_origin.clicked.connect(self.origin_to_cursor.emit)
        self._describe_fields()

    def _describe_fields(self) -> None:
        """Screen-reader names for every inspector control.

        A QFormLayout label is not reliably announced as the field's name, and
        several fields here ("X from origin", "Fallback") are meaningless without
        the unit or the coordinate space spelled out.
        """
        for widget, name, description in (
            (self.name_edit, "Step name", "What this step is called in the event list."),
            (self.enabled_box, "Enabled", "Uncheck to skip this step during replay."),
            (self.delay, "Pause before", "Milliseconds to wait before this step runs."),
            (self.x_box, "X from origin", "Horizontal offset in points from zero ground."),
            (self.y_box, "Y from origin", "Vertical offset in points from zero ground."),
            (self.dx_box, "Horizontal scroll", "Scroll wheel steps sideways."),
            (self.dy_box, "Vertical scroll", "Scroll wheel steps up or down."),
            (self.button, "Mouse button", "Which button this click uses."),
            (self.pressed, "Press or release", "Down presses the button, up releases it."),
            (self.key, "Key", "Key name to press or release, for example enter or a."),
            (self.color, "Trigger colour", "Hex colour the pixel is compared against."),
            (self.pick_color, "Choose colour", "Open the colour picker."),
            (self.pick_screen, "Pick pixel from screen", "Click anywhere to sample a pixel."),
            (self.tolerance, "Colour tolerance", "How far the pixel may differ and still match."),
            (self.match, "Colour test", "Whether the pixel must match, differ, or be brighter or darker."),
            (self.timeout, "Timeout", "Milliseconds to wait for the colour before giving up."),
            (self.path, "Path style", "How the cursor travels to this point."),
            (self.travel, "Travel time", "Milliseconds for the move, or Auto."),
            (self.notes, "Notes", "Free text kept with this step."),
            (self.direction, "Space direction", "Fallback Control+Arrow direction for a space change."),
            (self.app_name, "App name", "App that Replay brings forward."),
            (self.bundle_edit, "Bundle id", "macOS bundle identifier of that app."),
            (
                self.play_mode,
                "Replay mode",
                "Recorded origin stays on the display(s) you captured. From cursor "
                "shifts the whole path to the mouse, including another screen.",
            ),
            (self.loops, "Cycles", "How many times to repeat. Zero is forever."),
            (self.gap, "Gap between cycles", "Milliseconds of pause between repeats."),
            (self.return_origin, "Return to zero ground", "Move back to origin after each cycle."),
            (self.park, "Park at origin", "Move to origin before each cycle starts."),
            (self.preset, "Feel preset", "Precise replays the take exactly; the others add human variation."),
            (self.speed, "Playback speed", "1.0 times is the recorded timing."),
            (
                self.human_path,
                "Default path style",
                "Path used by steps that do not set their own. recorded walks the "
                "mouse path from the take; snap jumps to the destination.",
            ),
            (self.zero, "Move everything to zero ground", "Make the selected event the origin."),
            (self.cursor_origin, "Put origin at cursor", "Move zero ground to the mouse position."),
        ):
            describe(widget, name, description)

    def bind(self, script: Script, event: Event | None) -> None:
        self.script = script
        self.active = event
        self._guard = True
        children = self.findChildren(QWidget)
        for child in children:
            child.blockSignals(True)
        try:
            self._bind_values(script, event)
        finally:
            for child in children:
                child.blockSignals(False)
            self._guard = False

    def _bind_values(self, script: Script, event: Event | None) -> None:
        has_events = bool(script.events)
        if event is None:
            self.empty.setText(
                "Record (F9) or click + Add, then select an event to edit it."
                if not has_events
                else "Select an event to rename, move, or change it."
            )
        self.empty.setVisible(event is None)
        self.form_box.setVisible(event is not None)
        self.play_mode.setCurrentIndex(max(0, self.play_mode.findData(script.play_mode)))
        self.loops.setValue(script.loop.count)
        self.gap.setValue(script.loop.gap_ms)
        self.return_origin.setChecked(script.loop.return_to_origin)
        self.park.setChecked(script.loop.park_before_cycle)
        self.preset.setCurrentText(script.humanize.preset)
        self.speed.setValue(float(script.humanize.speed))
        self.human_path.setCurrentText(script.humanize.path)
        groups = inspector_groups_for(event)
        set_visible_groups(self.event_groups, groups)
        if event is None:
            return
        self.name_edit.setText(event.name)
        self.enabled_box.setChecked(event.enabled)
        self.delay.setValue(event.delay_ms)
        self.x_box.setValue(event.x)
        self.y_box.setValue(event.y)
        self.dx_box.setValue(event.dx)
        self.dy_box.setValue(event.dy)
        self.direction.setCurrentText(event.direction or "left")
        self.app_name.setText(event.app)
        self.bundle_edit.setText(event.bundle_id)
        self.button.setCurrentText(event.button)
        self.pressed.setCurrentText("down" if event.pressed else "up")
        self.key.setText(event.key)
        self.color.setText(event.color)
        self.tolerance.setValue(event.tolerance)
        self.match.setCurrentText(event.match)
        self.timeout.setValue(event.timeout_ms)
        self.path.setCurrentText(event.path or "(script default)")
        self.travel.setValue(event.travel_ms if event.travel_ms is not None else -1)
        self.notes.setPlainText(event.notes)
        kind = event.type_enum()
        if kind == EventType.SWIPE:
            self.swipe_note.setText(_swipe_inspector_note(event))
            self.swipe_note.setVisible(True)
        self.match.setVisible(kind == EventType.WAIT_PIXEL)
        self.match_label.setVisible(kind == EventType.WAIT_PIXEL)

    def _swatch(self) -> None:
        color = QColorDialog.getColor(QColor(self.color.text() or "#34C759"), self, "Trigger colour")
        if color.isValid():
            self.color.setText(color.name().upper())

    def _commit(self) -> None:
        if self._guard:
            return
        if self.active:
            self.active.name = self.name_edit.text()
            self.active.enabled = self.enabled_box.isChecked()
            self.active.delay_ms = self.delay.value()
            self.active.x = self.x_box.value()
            self.active.y = self.y_box.value()
            self.active.dx = self.dx_box.value()
            self.active.dy = self.dy_box.value()
            if self.active.type_enum() == EventType.SWIPE:
                self.active.app = self.app_name.text().strip()
                self.active.bundle_id = self.bundle_edit.text().strip()
                apply_swipe_direction(self.active, self.direction.currentText())
                self.swipe_note.setText(_swipe_inspector_note(self.active))
            else:
                self.active.direction = self.direction.currentText()
            self.active.button = self.button.currentText()
            self.active.pressed = self.pressed.currentText() == "down"
            if self.active.type_enum() != EventType.SWIPE:
                self.active.key = self.key.text()
            self.active.color = self.color.text()
            self.active.tolerance = self.tolerance.value()
            self.active.match = self.match.currentText()
            self.active.timeout_ms = self.timeout.value()
            self.active.path = None if self.path.currentText().startswith("(") else self.path.currentText()
            self.active.travel_ms = None if self.travel.value() < 0 else self.travel.value()
            self.active.notes = self.notes.toPlainText()
        self.script.play_mode = self.play_mode.currentData() or PlayMode.ABSOLUTE.value
        self.script.loop.count = self.loops.value()
        self.script.loop.gap_ms = self.gap.value()
        self.script.loop.return_to_origin = self.return_origin.isChecked()
        self.script.loop.park_before_cycle = self.park.isChecked()
        preset = self.preset.currentText()
        self.script.humanize.speed = float(self.speed.value())
        if preset != self.script.humanize.preset:
            self.script.humanize.apply_preset(preset)
            self.script.humanize.speed = float(self.speed.value())
            self._guard = True
            try:
                self.human_path.setCurrentText(self.script.humanize.path)
            finally:
                self._guard = False
        else:
            self.script.humanize.path = self.human_path.currentText()
            if preset != HumanizePreset.CUSTOM.value:
                probe = HumanizeSettings()
                probe.apply_preset(preset)
                if self.script.humanize.path != probe.path:
                    self.script.humanize.preset = HumanizePreset.CUSTOM.value
                    self._guard = True
                    try:
                        self.preset.setCurrentText(HumanizePreset.CUSTOM.value)
                    finally:
                        self._guard = False
        self.values_changed.emit()


def _swipe_inspector_note(event: Event) -> str:
    if is_app_switch(event):
        fallback = space_fallback_label(event) if event.key or event.direction in {"left", "right"} else ""
        if fallback:
            return (
                f"Replay activates {event.app or event.bundle_id}. "
                f"{fallback} is only used if activate fails."
            )
        return f"Replay activates {event.app or event.bundle_id}. That is not a four-finger swipe."
    inferred = "inferred" in (event.notes or "").lower()
    shortcut = event.key or swipe_shortcut_key(event.direction or "right", inferred=inferred)
    body = event.notes or (
        "Replay posts Control+Arrow (System Settings → Keyboard Shortcuts → "
        "Mission Control → Move left/right a space). Inferred right/left is the "
        "space axis. Finger-left is Control+Right. Control+Up is Mission Control. "
        "Flip Direction if Replay goes the wrong way."
    )
    pretty = space_fallback_label(event)
    if pretty.lower() not in body.lower() and shortcut.lower() not in body.lower():
        return f"Replay {pretty}. {body}"
    return body


def add_event_of_type(kind: EventType) -> Event:
    """Factory for + Add. New types: EventType, TYPE_COLOR, INSPECTOR_GROUPS, then defaults here."""
    event = Event(type=kind.value, name=EVENT_LABELS.get(kind, kind.value.replace("_", " ").title()))
    if kind == EventType.WAIT:
        event.delay_ms = 250
    if kind == EventType.WAIT_PIXEL:
        event.color = "#34C759"
        event.match = "is"
    if kind in {EventType.KEY_DOWN, EventType.KEY_UP}:
        event.key = "enter"
    if kind == EventType.CLICK:
        event.duration_ms = 70
    if kind == EventType.SWIPE:
        apply_swipe_direction(event, "left")
    return event
