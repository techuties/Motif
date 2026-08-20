"""Main Motif window: transport, timeline, inspector, external API."""

from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QObject, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QCloseEvent, QCursor, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QFrame,
    QPushButton,
    QScrollArea,
    QSplitter,
    QStatusBar,
    QToolBar,
    QVBoxLayout,
    QWidget,
)

from motif.api import DEFAULT_PORT, MotifAPI
from motif.example import example_script
from motif.models import (
    Event,
    EventType,
    Script,
    first_spatial_event,
    rebase_to_origin,
    script_from_dict,
    script_to_dict,
    shift_origin_to,
)
from motif.player import Player
from motif.recorder import Recorder
from motif.screen import grab_pixel, set_scale
from motif.storage import EXTENSION, load_script, save_script
from motif.ui.theme import BG, QSS, RECORD
from motif.ui.widgets import EventCard, EventList, Inspector, PathCanvas, add_event_of_type


class PlayerWorker(QObject):
    progressed = Signal(int, int, str)
    finished_with = Signal(str)

    def __init__(self, script: Script) -> None:
        super().__init__()
        self.script = script
        self.player = Player(on_progress=self._progress)

    def _progress(self, cycle: int, index: int, name: str) -> None:
        self.progressed.emit(cycle, index, name)

    @Slot()
    def run(self) -> None:
        self.finished_with.emit(self.player.play(self.script))

    def stop(self) -> None:
        self.player.request_stop()


class MainWindow(QMainWindow):
    ui_call = Signal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Motif")
        self.resize(1180, 760)
        self.script = Script()
        self.path: Path | None = None
        self.dirty = False
        self.picking_pixel = False
        self.recorder = Recorder(
            self.script,
            on_event=self._on_recorded,
            should_ignore=self._ignore_self,
            on_hotkey=self._hotkey,
        )
        self.worker: PlayerWorker | None = None
        self.thread: QThread | None = None
        self.api = MotifAPI(handlers=self._api_handlers())
        self.ui_call.connect(self._run_ui)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(10)

        self._build_menu()
        self._build_transport(layout)

        self.path_view = PathCanvas()
        self.path_view.event_clicked.connect(self._select_id)
        self.list = EventList()
        self.list.currentItemChanged.connect(lambda *_: self._sync_selection())
        self.list.order_changed.connect(self._apply_order)
        self.list.delete_requested.connect(self.delete_event)
        self.inspector = Inspector()
        self.inspector.values_changed.connect(self._inspector_changed)
        self.inspector.pick_pixel.connect(self.begin_pixel_pick)
        self.inspector.rebase_requested.connect(self.zero_ground)
        self.inspector.origin_to_cursor.connect(self.origin_to_cursor)

        left = QWidget()
        left_l = QVBoxLayout(left)
        left_l.setContentsMargins(0, 0, 0, 0)
        left_l.setSpacing(8)
        path_label = QLabel("PATH")
        path_label.setProperty("role", "section")
        events_label = QLabel("EVENTS")
        events_label.setProperty("role", "section")
        add_row = QHBoxLayout()
        add_row.addWidget(events_label)
        add_row.addStretch(1)
        self.add_btn = QPushButton("+ Add")
        self.add_menu = QMenu(self)
        for kind in (
            EventType.MOVE,
            EventType.CLICK,
            EventType.KEY_DOWN,
            EventType.WAIT,
            EventType.WAIT_PIXEL,
            EventType.WAIT_PIXEL_CHANGE,
            EventType.GO_ORIGIN,
            EventType.COMMENT,
        ):
            act = self.add_menu.addAction(kind.value.replace("_", " ").title())
            act.triggered.connect(lambda _, k=kind: self.add_event(k))
        self.add_btn.setMenu(self.add_menu)
        add_row.addWidget(self.add_btn)
        left_l.addWidget(path_label)
        left_l.addWidget(self.path_view)
        left_l.addLayout(add_row)
        left_l.addWidget(self.list, 1)

        inspector_scroll = QScrollArea()
        inspector_scroll.setWidget(self.inspector)
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        split = QSplitter(Qt.Orientation.Horizontal)
        split.addWidget(left)
        split.addWidget(inspector_scroll)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([760, 360])
        layout.addWidget(split, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self.refresh()
        QTimer.singleShot(200, self._after_show)

        QShortcut(QKeySequence("Ctrl+N"), self, self.new_script)
        QShortcut(QKeySequence("Ctrl+O"), self, self.open_script)
        QShortcut(QKeySequence("Ctrl+S"), self, self.save_script)
        QShortcut(QKeySequence("Ctrl+Shift+S"), self, self.save_script_as)
        QShortcut(QKeySequence("F9"), self, self.toggle_record)
        QShortcut(QKeySequence("F10"), self, self.toggle_play)
        QShortcut(QKeySequence("Esc"), self, self.stop_all)

        try:
            self.api.start()
            self.status.showMessage(f"Ready · API http://127.0.0.1:{DEFAULT_PORT}")
        except OSError:
            self.status.showMessage("Ready · API port busy — GUI still works")

    def _build_menu(self) -> None:
        file_menu = self.menuBar().addMenu("File")
        file_menu.addAction("New", self.new_script)
        file_menu.addAction("Open…", self.open_script)
        file_menu.addAction("Save", self.save_script)
        file_menu.addAction("Save As…", self.save_script_as)
        file_menu.addSeparator()
        file_menu.addAction("Quit", self.close)
        edit = self.menuBar().addMenu("Edit")
        edit.addAction("Delete event", self.delete_event)
        edit.addAction("Duplicate event", self.duplicate_event)
        edit.addSeparator()
        edit.addAction("Move everything to zero ground", self.zero_ground)
        edit.addAction("Put origin at cursor", self.origin_to_cursor)
        play = self.menuBar().addMenu("Play")
        play.addAction("Record  F9", self.toggle_record)
        play.addAction("Play  F10", self.toggle_play)
        play.addAction("Stop  Esc", self.stop_all)
        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Load example motif", self.load_example)
        help_menu.addAction("Permissions", self.show_permissions)
        help_menu.addAction("External control", self.show_api_help)

    def _build_transport(self, layout: QVBoxLayout) -> None:
        bar = QToolBar()
        bar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
        self.title = QLabel("Untitled motif")
        self.title.setProperty("role", "title")
        bar.addWidget(self.title)
        spacer = QWidget()
        spacer.setSizePolicy(spacer.sizePolicy().horizontalPolicy(), spacer.sizePolicy().verticalPolicy())
        spacer.setMinimumWidth(24)
        bar.addWidget(spacer)
        self.rec_btn = QPushButton("Record")
        self.rec_btn.setProperty("kind", "record")
        self.rec_btn.clicked.connect(self.toggle_record)
        self.play_btn = QPushButton("Play")
        self.play_btn.setProperty("kind", "primary")
        self.play_btn.clicked.connect(self.toggle_play)
        self.stop_btn = QPushButton("Stop")
        self.stop_btn.clicked.connect(self.stop_all)
        for btn in (self.rec_btn, self.play_btn, self.stop_btn):
            bar.addWidget(btn)
        layout.addSpacing(2)
        self.banner = QLabel("")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setVisible(False)
        layout.addWidget(self.banner)

    def _after_show(self) -> None:
        screen = self.screen()
        if screen:
            set_scale(float(screen.devicePixelRatio()))
        if sys.platform == "darwin":
            self.status.showMessage(
                "Ready · Grant Accessibility + Screen Recording to the app running Motif  ·  F9 record  F10 play  Esc stop"
            )

    def _api_handlers(self) -> dict:
        return {
            "GET /health": lambda _: {"ok": True, "app": "motif"},
            "GET /status": lambda _: self._status_payload(),
            "GET /script": lambda _: script_to_dict(self.script),
            "POST /play": lambda body: self._remote("play", body),
            "POST /stop": lambda _: self._remote("stop", {}),
            "POST /record": lambda _: self._remote("record", {}),
            "POST /load": lambda body: self._remote("load", body),
        }

    def _status_payload(self) -> dict:
        return {
            "recording": self.recorder.recording,
            "playing": bool(self.worker),
            "events": len(self.script.events),
            "name": self.script.name,
            "origin": [self.script.origin_x, self.script.origin_y],
        }

    def _remote(self, action: str, body: dict) -> dict:
        done = {"ok": True, "action": action}

        def go() -> None:
            if action == "play":
                path = body.get("path")
                if path:
                    self._load_path(Path(path))
                if body.get("loops") is not None:
                    self.script.loop.count = int(body["loops"])
                self.start_play()
            elif action == "stop":
                self.stop_all()
            elif action == "record":
                self.toggle_record()
            elif action == "load":
                self._load_path(Path(body["path"]))

        self.ui_call.emit(go)
        return done

    @Slot(object)
    def _run_ui(self, fn) -> None:
        fn()

    def _ignore_self(self) -> bool:
        if self.picking_pixel:
            return True
        pos = QCursor.pos()
        return self.frameGeometry().contains(pos)

    def _hotkey(self, name: str) -> None:
        def go() -> None:
            if name == "stop":
                self.stop_all()
            elif name == "record":
                self.toggle_record()
            elif name == "play":
                self.toggle_play()

        self.ui_call.emit(go)

    def _on_recorded(self, event: Event) -> None:
        def go() -> None:
            self.dirty = True
            self.refresh(select_id=event.id)

        self.ui_call.emit(go)

    def current_event(self) -> Event | None:
        eid = self.list.selected_id()
        for event in self.script.events:
            if event.id == eid:
                return event
        return None

    def refresh(self, select_id: str | None = None) -> None:
        selected = select_id or self.list.selected_id()
        self.list.rebuild(self.script, selected)
        event = self.current_event()
        self.inspector.bind(self.script, event)
        self.path_view.set_script(self.script, event.id if event else "")
        mark = " •" if self.dirty else ""
        self.title.setText(self.script.name + mark)
        self.setWindowTitle(f"Motif — {self.script.name}{mark}")
        origin = f"{self.script.origin_x}, {self.script.origin_y}" if self.script.origin_set else "not set"
        self.status.showMessage(
            f"{len(self.script.events)} events  ·  origin {origin}  ·  {self.script.humanize.preset}  ·  "
            f"cycles {self.script.loop.count or '∞'}"
        )

    def _sync_selection(self) -> None:
        event = self.current_event()
        self.inspector.bind(self.script, event)
        self.path_view.set_script(self.script, event.id if event else "")

    def _select_id(self, event_id: str) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == event_id:
                self.list.setCurrentRow(i)
                break

    def _apply_order(self) -> None:
        by_id = {e.id: e for e in self.script.events}
        self.script.events = [by_id[i] for i in self.list.ordered_ids() if i in by_id]
        self.dirty = True
        self.path_view.set_script(self.script, self.list.selected_id())

    def _inspector_changed(self) -> None:
        self.dirty = True
        event = self.current_event()
        self.path_view.set_script(self.script, event.id if event else "")
        item = self.list.currentItem()
        if item and event:
            card = EventCard(event)
            item.setSizeHint(card.sizeHint())
            self.list.setItemWidget(item, card)
        self.title.setText(self.script.name + " •")

    def add_event(self, kind: EventType) -> None:
        event = add_event_of_type(kind)
        idx = self.list.currentRow()
        insert_at = idx + 1 if idx >= 0 else len(self.script.events)
        self.script.events.insert(insert_at, event)
        self.dirty = True
        self.refresh(select_id=event.id)

    def delete_event(self) -> None:
        event = self.current_event()
        if not event:
            return
        self.script.events = [e for e in self.script.events if e.id != event.id]
        self.dirty = True
        self.refresh()

    def duplicate_event(self) -> None:
        event = self.current_event()
        if not event:
            return
        clone = event.clone()
        idx = self.script.events.index(event) + 1
        self.script.events.insert(idx, clone)
        self.dirty = True
        self.refresh(select_id=clone.id)

    def zero_ground(self) -> None:
        event = self.current_event()
        if event is None or not event.has_position():
            event = first_spatial_event(self.script)
        if event is None:
            QMessageBox.information(self, "Zero ground", "Record or add a click first, then set origin.")
            return
        screen_x = self.script.origin_x + event.x if self.script.origin_set else event.x
        screen_y = self.script.origin_y + event.y if self.script.origin_set else event.y
        rebase_to_origin(self.script, screen_x, screen_y)
        self.dirty = True
        self.refresh(select_id=event.id)
        self.status.showMessage("Origin is now that event. Other points shifted with it.")

    def origin_to_cursor(self) -> None:
        pos = QCursor.pos()
        shift_origin_to(self.script, pos.x(), pos.y())
        self.dirty = True
        self.refresh()

    def begin_pixel_pick(self) -> None:
        self.picking_pixel = True
        self.banner.setText("Click any screen pixel — Motif will capture its colour and position")
        self.banner.setStyleSheet(f"color:{RECORD}; font-weight:600; padding:6px;")
        self.banner.setVisible(True)
        self.grabMouse()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.picking_pixel:
            self.releaseMouse()
            self.picking_pixel = False
            self.banner.setVisible(False)
            pos = QCursor.pos()
            color = grab_pixel(pos.x(), pos.y())
            ev = self.current_event()
            if ev:
                if self.script.origin_set:
                    ev.x = pos.x() - self.script.origin_x
                    ev.y = pos.y() - self.script.origin_y
                else:
                    ev.x = pos.x()
                    ev.y = pos.y()
                ev.color = color.hex()
                self.dirty = True
                self.refresh(select_id=ev.id)
            return
        super().mousePressEvent(event)

    def toggle_record(self) -> None:
        if self.worker:
            return
        if self.recorder.recording:
            self.recorder.stop()
            self.rec_btn.setText("Record")
            self.banner.setVisible(False)
            self.dirty = True
            self.refresh()
            return
        self.recorder.script = self.script
        self.recorder.start()
        self.rec_btn.setText("Recording")
        self.banner.setText("Recording every move, click, and key  ·  F9 or Esc to stop")
        self.banner.setStyleSheet(f"color:{RECORD}; font-weight:600; padding:6px;")
        self.banner.setVisible(True)

    def toggle_play(self) -> None:
        if self.worker:
            self.stop_all()
            return
        self.start_play()

    def start_play(self) -> None:
        if self.recorder.recording:
            self.toggle_record()
        if not self.script.enabled_events():
            self.status.showMessage("Nothing to play yet")
            return
        snapshot = script_from_dict(script_to_dict(self.script))
        self.thread = QThread(self)
        self.worker = PlayerWorker(snapshot)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progressed.connect(self._on_progress)
        self.worker.finished_with.connect(self._on_play_done)
        self.thread.start()
        self.play_btn.setText("Playing")
        self.banner.setText("Playing  ·  Esc to stop")
        self.banner.setStyleSheet(f"color:#3DCF9A; font-weight:600; padding:6px;")
        self.banner.setVisible(True)

    def _on_progress(self, cycle: int, index: int, name: str) -> None:
        self.status.showMessage(f"Cycle {cycle}  ·  {index + 1}/{len(self.script.enabled_events())}  ·  {name}")
        enabled = self.script.enabled_events()
        if 0 <= index < len(enabled):
            self._select_id(enabled[index].id)

    def _on_play_done(self, result: str) -> None:
        if self.thread:
            self.thread.quit()
            self.thread.wait(1500)
        self.thread = None
        self.worker = None
        self.play_btn.setText("Play")
        self.banner.setVisible(False)
        labels = {"done": "Finished", "stopped": "Stopped", "failed": "Stopped — a wait timed out"}
        self.status.showMessage(labels.get(result, result))

    def stop_all(self) -> None:
        if self.recorder.recording:
            self.toggle_record()
        if self.worker:
            self.worker.stop()
        if self.picking_pixel:
            self.picking_pixel = False
            self.releaseMouse()
            self.banner.setVisible(False)

    def _confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        box = QMessageBox.question(
            self,
            "Unsaved motif",
            "This motif has unsaved changes. Discard them?",
            QMessageBox.StandardButton.Discard | QMessageBox.StandardButton.Cancel,
        )
        return box == QMessageBox.StandardButton.Discard

    def new_script(self) -> None:
        if not self._confirm_discard():
            return
        self.script = Script()
        self.recorder.script = self.script
        self.path = None
        self.dirty = False
        self.refresh()

    def load_example(self) -> None:
        if not self._confirm_discard():
            return
        self.script = example_script()
        self.recorder.script = self.script
        self.path = None
        self.dirty = True
        self.refresh()

    def open_script(self) -> None:
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Open motif", "", f"Motif (*{EXTENSION} *.json)")
        if filename:
            self._load_path(Path(filename))

    def _load_path(self, path: Path) -> None:
        self.script = load_script(path)
        self.recorder.script = self.script
        self.path = path
        self.dirty = False
        self.refresh()

    def save_script(self) -> None:
        if self.path is None:
            self.save_script_as()
            return
        save_script(self.script, self.path)
        self.dirty = False
        self.refresh()

    def save_script_as(self) -> None:
        filename, _ = QFileDialog.getSaveFileName(self, "Save motif", self.script.name + EXTENSION, f"Motif (*{EXTENSION})")
        if not filename:
            return
        self.path = save_script(self.script, filename)
        self.dirty = False
        self.refresh()

    def show_permissions(self) -> None:
        if sys.platform == "darwin":
            text = (
                "macOS will block record and replay until Motif (or Terminal/Python) has:\n\n"
                "1. System Settings → Privacy & Security → Accessibility\n"
                "2. System Settings → Privacy & Security → Screen Recording  (for colour triggers)\n\n"
                "Then quit and reopen Motif."
            )
        elif sys.platform.startswith("linux"):
            text = (
                "On X11, Motif can record globally.\n"
                "On Wayland, global hooks are restricted — use an X11 session for full record/replay.\n"
                "uinput / input group access may also be required."
            )
        else:
            text = "On Windows, allow Motif through security prompts. High-DPI scaling is handled automatically."
        QMessageBox.information(self, "Permissions", text)

    def show_api_help(self) -> None:
        QMessageBox.information(
            self,
            "External control",
            "Other programs can drive Motif on localhost:\n\n"
            f"curl http://127.0.0.1:{DEFAULT_PORT}/status\n"
            f"curl -X POST http://127.0.0.1:{DEFAULT_PORT}/play\n"
            f"curl -X POST http://127.0.0.1:{DEFAULT_PORT}/stop\n\n"
            "Python:\n"
            "from motif import MotifClient\n"
            "MotifClient().play()\n\n"
            "CLI:\n"
            "python -m motif play script.motif.json --loops 3",
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._confirm_discard():
            event.ignore()
            return
        self.stop_all()
        self.api.stop()
        event.accept()


def configure_qt() -> None:
    import PySide6

    plugins = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
    QCoreApplication.addLibraryPath(str(plugins))
    QCoreApplication.addLibraryPath(str(plugins / "platforms"))


def run_app() -> int:
    configure_qt()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Motif")
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.setStyleSheet(f"background:{BG};")
    window.show()
    return app.exec()
