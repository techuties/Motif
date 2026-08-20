"""Path canvas, event cards, and inspector — the parts people actually touch."""

from __future__ import annotations

from PySide6.QtCore import QPoint, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
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

from motif.models import EVENT_LABELS, Event, EventType, HumanizePreset, PathStyle, PlayMode, Script
from motif.ui.theme import ACCENT, BG, BORDER, MUTED, ORIGIN, SURFACE, TEXT, TYPE_COLOR


def type_color(event: Event) -> QColor:
    return QColor(TYPE_COLOR.get(event.type_enum(), MUTED))


class PathCanvas(QWidget):
    event_clicked = Signal(str)
    origin_clicked = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.script = Script()
        self.selected_id = ""
        self.setMinimumHeight(168)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setToolTip("The journey. Click a dot to select that event. Origin is the gold cross.")

    def set_script(self, script: Script, selected_id: str = "") -> None:
        self.script = script
        self.selected_id = selected_id
        self.update()

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
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(SURFACE))
        painter.setPen(QPen(QColor(BORDER), 1))
        painter.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 14, 14)

        if not self.script.events:
            painter.setPen(QColor(MUTED))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Record a path to see it here")
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
        painter.setPen(QPen(QColor(ACCENT), 2))
        painter.drawPath(path)

        origin = self._map(0, 0)
        painter.setPen(QPen(QColor(ORIGIN), 2))
        painter.drawLine(origin.x() - 8, origin.y(), origin.x() + 8, origin.y())
        painter.drawLine(origin.x(), origin.y() - 8, origin.x(), origin.y() + 8)

        for ev in self.script.events:
            if not ev.has_position() or ev.type_enum() == EventType.MOVE and ev.points:
                if ev.type_enum() != EventType.CLICK:
                    continue
            pt = self._map(ev.x, ev.y)
            color = type_color(ev)
            radius = 7 if ev.id == self.selected_id else 5
            painter.setBrush(color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(pt, radius, radius)
            if ev.id == self.selected_id:
                painter.setPen(QPen(QColor(TEXT), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawEllipse(pt, radius + 4, radius + 4)

        painter.setPen(QColor(MUTED))
        painter.setFont(QFont(self.font().family(), 10))
        painter.drawText(14, 20, "Zero ground")
        painter.drawText(origin + QPoint(10, -8), "0,0")

    def mousePressEvent(self, event) -> None:  # noqa: N802
        click = event.position().toPoint()
        origin = self._map(0, 0)
        if (click - origin).manhattanLength() < 14:
            self.origin_clicked.emit()
            return
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


class EventCard(QWidget):
    def __init__(self, event: Event, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.model = event
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 8, 10, 8)
        layout.setSpacing(10)

        self.swatch = QFrame()
        self.swatch.setFixedSize(10, 34)
        self.swatch.setStyleSheet(f"background:{TYPE_COLOR.get(event.type_enum(), MUTED)}; border-radius:3px;")
        layout.addWidget(self.swatch)

        text = QVBoxLayout()
        text.setSpacing(1)
        self.title = QLabel(event.display_name())
        self.title.setStyleSheet("font-weight:600;")
        self.detail = QLabel(event.summary())
        self.detail.setProperty("role", "muted")
        self.detail.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        text.addWidget(self.title)
        text.addWidget(self.detail)
        layout.addLayout(text, 1)

        self.delay = QLabel(f"{event.delay_ms} ms")
        self.delay.setProperty("role", "muted")
        self.delay.setStyleSheet(f"color:{MUTED};")
        layout.addWidget(self.delay)

        if not event.enabled:
            self.title.setStyleSheet("font-weight:600; color:#667088;")

    def sizeHint(self) -> QSize:  # noqa: N802
        return QSize(360, 54)


class EventList(QListWidget):
    order_changed = Signal()
    delete_requested = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setDragDropMode(QListWidget.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.setSpacing(2)
        self.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.model().rowsMoved.connect(lambda *_: self.order_changed.emit())

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete):
            self.delete_requested.emit()
            return
        super().keyPressEvent(event)

    def rebuild(self, script: Script, selected_id: str = "") -> None:
        current = selected_id
        self.blockSignals(True)
        self.clear()
        for event in script.events:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, event.id)
            card = EventCard(event)
            item.setSizeHint(card.sizeHint())
            self.addItem(item)
            self.setItemWidget(item, card)
            if event.id == current:
                self.setCurrentItem(item)
        self.blockSignals(False)
        if self.currentItem() is None and self.count():
            self.setCurrentRow(0)

    def ordered_ids(self) -> list[str]:
        ids = []
        for i in range(self.count()):
            ids.append(self.item(i).data(Qt.ItemDataRole.UserRole))
        return ids

    def selected_id(self) -> str:
        item = self.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else ""


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

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        head = QLabel("INSPECTOR")
        head.setProperty("role", "section")
        root.addWidget(head)

        self.empty = QLabel("Select an event to rename, move, or change it.")
        self.empty.setWordWrap(True)
        self.empty.setProperty("role", "muted")
        root.addWidget(self.empty)

        self.form_box = QFrame()
        form = QFormLayout(self.form_box)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(8)
        self.name_edit = QLineEdit()
        self.enabled_box = QCheckBox("Enabled")
        self.delay = QSpinBox()
        self.delay.setRange(0, 120000)
        self.delay.setSuffix(" ms")
        self.x_box = QSpinBox()
        self.y_box = QSpinBox()
        for box in (self.x_box, self.y_box):
            box.setRange(-20000, 20000)
        self.button = QComboBox()
        self.button.addItems(["left", "right", "middle"])
        self.pressed = QComboBox()
        self.pressed.addItems(["down", "up"])
        self.key = QLineEdit()
        self.color = QLineEdit("#34C759")
        self.pick_color = QPushButton("Swatch")
        self.pick_screen = QPushButton("Pick pixel")
        color_row = QHBoxLayout()
        color_row.addWidget(self.color, 1)
        color_row.addWidget(self.pick_color)
        color_row.addWidget(self.pick_screen)
        self.color_wrap = QWidget()
        self.color_wrap.setLayout(color_row)
        self.tolerance = QSpinBox()
        self.tolerance.setRange(0, 180)
        self.match = QComboBox()
        self.match.addItems(["is", "is_not", "brighter", "darker"])
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
        self.notes.setFixedHeight(64)
        form.addRow("Name", self.name_edit)
        form.addRow("", self.enabled_box)
        form.addRow("Pause before", self.delay)
        form.addRow("X from origin", self.x_box)
        form.addRow("Y from origin", self.y_box)
        form.addRow("Button", self.button)
        form.addRow("Click", self.pressed)
        form.addRow("Key", self.key)
        form.addRow("Colour", self.color_wrap)
        form.addRow("Tolerance", self.tolerance)
        form.addRow("When", self.match)
        form.addRow("Timeout", self.timeout)
        form.addRow("Path", self.path)
        form.addRow("Travel", self.travel)
        form.addRow("Notes", self.notes)
        root.addWidget(self.form_box)

        script_title = QLabel("SCRIPT")
        script_title.setProperty("role", "section")
        root.addWidget(script_title)

        sform = QFormLayout()
        self.play_mode = QComboBox()
        self.play_mode.addItem("Play at recorded origin", PlayMode.ABSOLUTE.value)
        self.play_mode.addItem("Play from current cursor", PlayMode.FROM_CURSOR.value)
        self.play_mode.addItem("Always start at origin", PlayMode.FROM_ORIGIN.value)
        self.loops = QSpinBox()
        self.loops.setRange(0, 100000)
        self.loops.setSpecialValueText("Forever")
        self.gap = QSpinBox()
        self.gap.setRange(0, 60000)
        self.gap.setSuffix(" ms")
        self.return_origin = QCheckBox("Return to zero ground after each cycle")
        self.park = QCheckBox("Park at origin before each cycle")
        self.preset = QComboBox()
        self.preset.addItems([p.value for p in HumanizePreset])
        self.speed = QComboBox()
        self.speed.addItems(["0.5", "0.75", "1.0", "1.25", "1.5", "2.0"])
        self.speed.setCurrentText("1.0")
        self.human_path = QComboBox()
        self.human_path.addItems([p.value for p in PathStyle])
        self.zero = QPushButton("Move everything to zero ground")
        self.zero.setProperty("kind", "primary")
        self.cursor_origin = QPushButton("Put origin at cursor")
        sform.addRow("Play", self.play_mode)
        sform.addRow("Cycles", self.loops)
        sform.addRow("Gap", self.gap)
        sform.addRow(self.return_origin)
        sform.addRow(self.park)
        sform.addRow("Feel", self.preset)
        sform.addRow("Speed", self.speed)
        sform.addRow("Default path", self.human_path)
        root.addLayout(sform)
        root.addWidget(self.zero)
        root.addWidget(self.cursor_origin)
        hint = QLabel("Zero ground is (0,0) of this motif. Cycles start and end there so loops stay aligned.")
        hint.setWordWrap(True)
        hint.setProperty("role", "muted")
        hint.setStyleSheet(f"color:{MUTED}; font-size:12px;")
        root.addWidget(hint)
        root.addStretch(1)

        widgets = [
            self.name_edit,
            self.enabled_box,
            self.delay,
            self.x_box,
            self.y_box,
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
            elif isinstance(w, QSpinBox):
                w.valueChanged.connect(self._commit)
            elif isinstance(w, QCheckBox):
                w.toggled.connect(self._commit)
        self.pick_color.clicked.connect(self._swatch)
        self.pick_screen.clicked.connect(self.pick_pixel.emit)
        self.zero.clicked.connect(self.rebase_requested.emit)
        self.cursor_origin.clicked.connect(self.origin_to_cursor.emit)

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
        self.empty.setVisible(event is None)
        self.form_box.setVisible(event is not None)
        self.play_mode.setCurrentIndex(max(0, self.play_mode.findData(script.play_mode)))
        self.loops.setValue(script.loop.count)
        self.gap.setValue(script.loop.gap_ms)
        self.return_origin.setChecked(script.loop.return_to_origin)
        self.park.setChecked(script.loop.park_before_cycle)
        self.preset.setCurrentText(script.humanize.preset)
        self.speed.setCurrentText(str(script.humanize.speed) if str(script.humanize.speed) in {"0.5", "0.75", "1.0", "1.25", "1.5", "2.0"} else "1.0")
        self.human_path.setCurrentText(script.humanize.path)
        if event:
            self.name_edit.setText(event.name)
            self.enabled_box.setChecked(event.enabled)
            self.delay.setValue(event.delay_ms)
            self.x_box.setValue(event.x)
            self.y_box.setValue(event.y)
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
            spatial = event.has_position()
            self.x_box.setEnabled(spatial)
            self.y_box.setEnabled(spatial)
            clickish = kind == EventType.CLICK
            self.button.setEnabled(clickish)
            self.pressed.setEnabled(clickish)
            keyish = kind in {EventType.KEY_DOWN, EventType.KEY_UP}
            self.key.setEnabled(keyish)
            pixelish = kind in {EventType.WAIT_PIXEL, EventType.WAIT_PIXEL_CHANGE}
            self.color.setEnabled(pixelish)
            self.pick_color.setEnabled(pixelish)
            self.pick_screen.setEnabled(True)
            self.tolerance.setEnabled(pixelish)
            self.match.setEnabled(kind == EventType.WAIT_PIXEL)
            self.timeout.setEnabled(pixelish)

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
            self.active.button = self.button.currentText()
            self.active.pressed = self.pressed.currentText() == "down"
            self.active.key = self.key.text()
            self.active.color = self.color.text()
            self.active.tolerance = self.tolerance.value()
            self.active.match = self.match.currentText()
            self.active.timeout_ms = self.timeout.value()
            self.active.path = None if self.path.currentText().startswith("(") else self.path.currentText()
            self.active.travel_ms = None if self.travel.value() < 0 else self.travel.value()
            self.active.notes = self.notes.toPlainText()
        self.script.play_mode = self.play_mode.currentData()
        self.script.loop.count = self.loops.value()
        self.script.loop.gap_ms = self.gap.value()
        self.script.loop.return_to_origin = self.return_origin.isChecked()
        self.script.loop.park_before_cycle = self.park.isChecked()
        preset = self.preset.currentText()
        if preset != self.script.humanize.preset:
            self.script.humanize.apply_preset(preset)
        self.script.humanize.speed = float(self.speed.currentText())
        self.script.humanize.path = self.human_path.currentText()
        if preset != HumanizePreset.CUSTOM.value and (
            self.human_path.currentText() != self.script.humanize.path
        ):
            self.script.humanize.preset = HumanizePreset.CUSTOM.value
        self.values_changed.emit()


def add_event_of_type(kind: EventType) -> Event:
    event = Event(type=kind.value, name=EVENT_LABELS[kind])
    if kind == EventType.WAIT:
        event.delay_ms = 250
    if kind == EventType.WAIT_PIXEL:
        event.color = "#34C759"
        event.match = "is"
    if kind == EventType.KEY_DOWN:
        event.key = "enter"
    return event
