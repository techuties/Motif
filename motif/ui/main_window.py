"""Main Motif window: transport, timeline, inspector, external API."""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path
from threading import Lock

from PySide6.QtCore import QCoreApplication, QObject, QRect, Qt, QThread, QTimer, Signal, Slot
from PySide6.QtGui import QAction, QCloseEvent, QCursor, QFontDatabase, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMenu,
    QMessageBox,
    QFrame,
    QLayout,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QSplitter,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from motif.api import DEFAULT_PORT, MotifAPI
from motif.example import example_script
from motif.keys import (
    GlobalHotkeys,
    exit_combo_label,
    exit_combo_words,
    exit_qt_sequence,
)
from motif.models import (
    CYCLE_LABELS,
    CYCLE_PRESETS,
    EVENT_LABELS,
    REPLAY_X10,
    REPLAY_X100,
    SPEED_PRESETS,
    Event,
    EventType,
    Script,
    first_spatial_event,
    rebase_to_origin,
    script_from_dict,
    script_to_dict,
    set_loop_count,
    set_recorded_feel,
    shift_origin_to,
)
from motif.macos import RecorderStartError, can_monitor_input, permissions_help, prepare_input_hooks
from motif.player import Player
from motif.recorder import Recorder
from motif.screen import Display, grab_pixel, set_displays, set_scale, virtual_rect, with_physical_origins
from motif.storage import (
    EXTENSION,
    load_script,
    load_settings,
    project_dir,
    raw_path_for,
    save_raw_capture,
    save_script,
    save_settings,
)
from motif.ui.theme import (
    BUTTON_HEIGHT,
    BUTTON_MIN_WIDTH,
    CHIP_HEIGHT,
    CHIP_MIN_WIDTH,
    CLUSTER_PAD,
    CYCLE_MIN_WIDTH,
    CYCLE_SPIN_MIN,
    QSS,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPEED_SPIN_MIN,
    SPLITTER_LEFT_DEFAULT,
    SPLITTER_MAIN_DEFAULT,
    STOP_MIN_WIDTH,
    TRANSPORT_MIN_HEIGHT,
)
from motif.ui.widgets import (
    EventCard,
    EventList,
    Inspector,
    PathCanvas,
    ScreenHistoryView,
    add_event_of_type,
    apply_banner,
    apply_button_kind,
    hint_label,
    polish,
    section_header,
)


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
    event_captured = Signal(object)
    hotkey_pressed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("Motif")
        self.setMinimumSize(1040, 700)
        self.resize(1280, 860)
        self.script = Script()
        self.path: Path | None = None
        self.dirty = False
        self.picking_pixel = False
        self._ignore_lock = Lock()
        self._ignore_rect = (0, 0, 0, 0)
        self._ignore_picking = False
        self._undo: list[dict] = []
        self.settings = load_settings()
        self.recorder = Recorder(
            self.script,
            on_event=self.event_captured.emit,
            should_ignore=self._ignore_at,
            on_hotkey=self.hotkey_pressed.emit,
        )
        self.worker: PlayerWorker | None = None
        self.thread: QThread | None = None
        self._hotkey_until = 0.0
        self._cycles_custom = False
        self._play_total = 1
        self._hotkeys = GlobalHotkeys(self.hotkey_pressed.emit)
        self.api = MotifAPI(handlers=self._api_handlers())
        self.ui_call.connect(self._run_ui, Qt.ConnectionType.QueuedConnection)
        self.event_captured.connect(self._append_recorded, Qt.ConnectionType.QueuedConnection)
        self.hotkey_pressed.connect(self._on_hotkey, Qt.ConnectionType.QueuedConnection)

        root = QWidget()
        root.setObjectName("root")
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(SPACE_LG, SPACE_MD, SPACE_LG, SPACE_MD)
        layout.setSpacing(SPACE_MD)

        self._build_menu()
        self._build_transport(layout)

        self.screen_view = ScreenHistoryView()
        self.screen_view.event_clicked.connect(self._select_id)
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

        self.screen_box = QWidget()
        screen_l = QVBoxLayout(self.screen_box)
        screen_l.setContentsMargins(0, 0, 0, 0)
        screen_l.setSpacing(SPACE_SM)
        screen_l.addWidget(section_header("SCREEN HISTORY"))
        screen_l.addWidget(self.screen_view, 1)

        self.path_box = QWidget()
        path_l = QVBoxLayout(self.path_box)
        path_l.setContentsMargins(0, 0, 0, 0)
        path_l.setSpacing(SPACE_SM)
        path_l.addWidget(section_header("PATH"))
        path_l.addWidget(self.path_view, 1)

        events_box = QWidget()
        events_l = QVBoxLayout(events_box)
        events_l.setContentsMargins(0, 0, 0, 0)
        events_l.setSpacing(SPACE_SM)
        events_label = section_header("EVENTS")
        add_row = QHBoxLayout()
        add_row.setContentsMargins(0, 0, 0, 0)
        add_row.addWidget(events_label)
        add_row.addStretch(1)
        self.add_btn = QPushButton("+ Add")
        apply_button_kind(self.add_btn, "ghost")
        self.add_menu = QMenu(self)
        for kind in EventType:
            act = self.add_menu.addAction(EVENT_LABELS.get(kind, kind.value.replace("_", " ").title()))
            act.triggered.connect(lambda _, k=kind: self.add_event(k))
        self.add_btn.setMenu(self.add_menu)
        add_row.addWidget(self.add_btn)
        events_l.addLayout(add_row)
        events_l.addWidget(self.list, 1)

        self.screen_box.setMinimumHeight(200)
        self.path_box.setMinimumHeight(118)
        events_box.setMinimumHeight(168)
        self.left_split = QSplitter(Qt.Orientation.Vertical)
        self.left_split.addWidget(self.screen_box)
        self.left_split.addWidget(self.path_box)
        self.left_split.addWidget(events_box)
        self.left_split.setStretchFactor(0, 5)
        self.left_split.setStretchFactor(1, 1)
        self.left_split.setStretchFactor(2, 2)
        self.left_split.setChildrenCollapsible(False)

        inspector_scroll = QScrollArea()
        inspector_scroll.setWidget(self.inspector)
        inspector_scroll.setWidgetResizable(True)
        inspector_scroll.setFrameShape(QFrame.Shape.NoFrame)
        inspector_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        inspector_scroll.setMinimumWidth(280)

        self.main_split = QSplitter(Qt.Orientation.Horizontal)
        self.main_split.addWidget(self.left_split)
        self.main_split.addWidget(inspector_scroll)
        self.main_split.setStretchFactor(0, 3)
        self.main_split.setStretchFactor(1, 2)
        self.main_split.setChildrenCollapsible(False)
        self._restore_splitters()
        layout.addWidget(self.main_split, 1)

        self.status = QStatusBar()
        self.setStatusBar(self.status)
        self._apply_view_settings()
        self.refresh()
        QTimer.singleShot(200, self._after_show)

        for key, slot, app_wide in (
            ("Ctrl+N", self.new_script, False),
            ("Ctrl+O", self.open_script, False),
            ("Ctrl+S", self.save_script, False),
            ("Ctrl+Shift+S", self.save_script_as, False),
            ("Ctrl+Z", self.undo, False),
            ("Ctrl+D", self.duplicate_event, False),
            ("F9", self.toggle_record, True),
            ("F10", self.toggle_play, True),
            ("Esc", self.stop_all, True),
            (exit_qt_sequence(), self.stop_all, True),
        ):
            shortcut = QShortcut(QKeySequence(key), self, slot)
            if app_wide:
                shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        self._ignore_timer = QTimer(self)
        self._ignore_timer.setInterval(200)
        self._ignore_timer.timeout.connect(self._sync_ignore_region)
        if self.settings.get("api_enabled"):
            self._set_api_enabled(True, persist=False, quiet=True)
        else:
            self.status.showMessage(
                f"Ready  ·  F9 record  ·  F10 replay  ·  {exit_combo_label()} stop"
            )

    def _build_menu(self) -> None:
        motif = self.menuBar().addMenu("Motif")
        about = QAction("About Motif", self)
        about.setMenuRole(QAction.MenuRole.AboutRole)
        about.triggered.connect(self.show_about)
        prefs = QAction("Preferences…", self)
        prefs.setMenuRole(QAction.MenuRole.PreferencesRole)
        prefs.triggered.connect(self.show_preferences)
        quit_act = QAction("Quit Motif", self)
        quit_act.setMenuRole(QAction.MenuRole.QuitRole)
        quit_act.setShortcut(QKeySequence.StandardKey.Quit)
        quit_act.triggered.connect(self.close)
        motif.addAction(about)
        motif.addAction(prefs)
        motif.addSeparator()
        self.api_act = QAction("Enable Local Control (localhost)", self)
        self.api_act.setCheckable(True)
        self.api_act.setChecked(bool(self.settings.get("api_enabled")))
        self.api_act.triggered.connect(self._on_api_menu)
        motif.addAction(self.api_act)
        if sys.platform == "darwin":
            install = QAction("Install to Applications", self)
            install.triggered.connect(self.install_to_applications)
            motif.addAction(install)
        motif.addSeparator()
        motif.addAction(quit_act)

        file_menu = self.menuBar().addMenu("File")
        new_act = file_menu.addAction("New", self.new_script)
        new_act.setShortcut(QKeySequence.StandardKey.New)
        open_act = file_menu.addAction("Open…", self.open_script)
        open_act.setShortcut(QKeySequence.StandardKey.Open)
        save_act = file_menu.addAction("Save", self.save_script)
        save_act.setShortcut(QKeySequence.StandardKey.Save)
        save_as = file_menu.addAction("Save As…", self.save_script_as)
        save_as.setShortcut(QKeySequence.StandardKey.SaveAs)

        edit = self.menuBar().addMenu("Edit")
        self.undo_act = QAction("Undo", self)
        self.undo_act.setShortcut(QKeySequence.StandardKey.Undo)
        self.undo_act.triggered.connect(self.undo)
        self.undo_act.setEnabled(False)
        edit.addAction(self.undo_act)
        edit.addSeparator()
        delete_act = edit.addAction("Delete", self.delete_event)
        delete_act.setShortcut(QKeySequence.StandardKey.Delete)
        dup = edit.addAction("Duplicate", self.duplicate_event)
        dup.setShortcut(QKeySequence("Ctrl+D"))
        select = edit.addAction("Select All", self.select_all_events)
        select.setShortcut(QKeySequence.StandardKey.SelectAll)

        recording = self.menuBar().addMenu("Recording")
        self.record_act = recording.addAction("Record", self.toggle_record)
        self.replay_act = recording.addAction("Replay", self.toggle_play)
        self.stop_act = recording.addAction(f"Stop ({exit_combo_label()})", self.stop_all)
        recording.addSeparator()
        self.loop_forever_act = QAction("Loop Forever", self)
        self.loop_forever_act.setCheckable(True)
        self.loop_forever_act.triggered.connect(self._set_loop_forever)
        recording.addAction(self.loop_forever_act)
        recording.addAction("Replay Once", self._set_play_once)
        recording.addAction("Replay ×10", lambda: self._replay_count(REPLAY_X10))
        recording.addAction("Replay ×100", lambda: self._replay_count(REPLAY_X100))

        replay_menu = self.menuBar().addMenu("Replay")
        replay_menu.addAction("Replay", self.toggle_play)
        replay_menu.addAction("Replay ×10", lambda: self._replay_count(REPLAY_X10))
        replay_menu.addAction("Replay ×100", lambda: self._replay_count(REPLAY_X100))
        replay_menu.addAction("Replay Forever", lambda: self._replay_count(0))
        replay_menu.addSeparator()
        replay_menu.addAction(f"Stop ({exit_combo_label()})", self.stop_all)

        view = self.menuBar().addMenu("View")
        self.path_view_act = QAction("Path Preview", self)
        self.path_view_act.setCheckable(True)
        self.path_view_act.setChecked(bool(self.settings.get("show_path", True)))
        self.path_view_act.triggered.connect(self._toggle_path_view)
        self.screen_view_act = QAction("Screen History", self)
        self.screen_view_act.setCheckable(True)
        self.screen_view_act.setChecked(bool(self.settings.get("show_screen_history", True)))
        self.screen_view_act.triggered.connect(self._toggle_screen_view)
        view.addAction(self.path_view_act)
        view.addAction(self.screen_view_act)

        help_menu = self.menuBar().addMenu("Help")
        help_menu.addAction("Load Example Motif", self.load_example)
        help_menu.addAction("Permissions", self.show_permissions)
        help_menu.addAction("External Control", self.show_api_help)

    def _lock_chrome(self, widget: QWidget, min_width: int, height: int = BUTTON_HEIGHT) -> None:
        widget.setMinimumWidth(min_width)
        widget.setFixedHeight(height)
        widget.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        widget.setFocusPolicy(Qt.FocusPolicy.NoFocus)

    def _cluster_label(self, text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "muted")
        label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return label

    def _build_transport(self, layout: QVBoxLayout) -> None:
        header = QWidget()
        header.setObjectName("header")
        header.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        header_col = QVBoxLayout(header)
        header_col.setContentsMargins(0, 0, 0, 0)
        header_col.setSpacing(SPACE_SM)

        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        title_row = QHBoxLayout(self.title_bar)
        title_row.setContentsMargins(0, 0, 0, 0)
        title_row.setSpacing(0)
        self.title = QLabel("Untitled motif")
        self.title.setProperty("role", "title")
        self.title.setMinimumWidth(80)
        self.title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        title_row.addWidget(self.title, 1)
        header_col.addWidget(self.title_bar)

        self.transport = QWidget()
        self.transport.setObjectName("transport")
        self.transport.setMinimumHeight(TRANSPORT_MIN_HEIGHT)
        self.transport.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        row = QHBoxLayout(self.transport)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(SPACE_SM)
        row.setAlignment(Qt.AlignmentFlag.AlignVCenter)
        row.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        self.rec_btn = QPushButton("Record")
        self.rec_btn.setObjectName("recordBtn")
        apply_button_kind(self.rec_btn, "record")
        self._lock_chrome(self.rec_btn, BUTTON_MIN_WIDTH)
        self.rec_btn.setToolTip("Record mouse and keys  ·  F9")
        self.rec_btn.clicked.connect(self.toggle_record)

        self.replay_btn = QPushButton("Replay")
        self.replay_btn.setObjectName("replayBtn")
        apply_button_kind(self.replay_btn, "primary")
        self._lock_chrome(self.replay_btn, BUTTON_MIN_WIDTH)
        self.replay_btn.setToolTip("Replay this motif once  ·  F10")
        self.replay_btn.clicked.connect(self.toggle_play)

        self.stop_btn = QPushButton("Stop")
        self.stop_btn.setObjectName("stopBtn")
        apply_button_kind(self.stop_btn, "ghost")
        self._lock_chrome(self.stop_btn, STOP_MIN_WIDTH)
        self.stop_btn.setToolTip(f"Stop recording or replay  ·  {exit_combo_label()}")
        self.stop_btn.clicked.connect(self.stop_all)

        self.exit_hint = QLabel(exit_combo_label())
        self.exit_hint.setProperty("role", "muted")
        self.exit_hint.setToolTip(
            f"{exit_combo_words()} always stops recording or replay, even if Motif is not focused."
        )

        row.addWidget(self.rec_btn)
        row.addWidget(self.replay_btn)
        row.addWidget(self.stop_btn)
        row.addWidget(self.exit_hint)
        row.addStretch(1)

        self.cycles_label = self._cluster_label("Cycles")
        row.addWidget(self.cycles_label)

        self.cycles_cluster = QWidget()
        self.cycles_cluster.setObjectName("cyclesCluster")
        self.cycles_cluster.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        cycles_row = QHBoxLayout(self.cycles_cluster)
        cycles_row.setContentsMargins(CLUSTER_PAD, CLUSTER_PAD, CLUSTER_PAD, CLUSTER_PAD)
        cycles_row.setSpacing(0)
        cycles_row.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.cycle_group = QButtonGroup(self)
        self.cycle_group.setExclusive(False)
        self.cycle_buttons: dict[int, QPushButton] = {}
        cycle_tips = {
            1: "Once — Replay plays a single pass",
            10: "10 cycles — Replay uses this count",
            100: "100 cycles — Replay uses this count",
        }
        for value in CYCLE_PRESETS:
            btn = QPushButton(CYCLE_LABELS[value])
            btn.setObjectName(f"cycleChip_{value}")
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            apply_button_kind(btn, "cycle")
            self._lock_chrome(btn, CYCLE_MIN_WIDTH, CHIP_HEIGHT)
            btn.setToolTip(cycle_tips[value])
            btn.clicked.connect(lambda _, v=value: self._set_cycle_count(v))
            self.cycle_group.addButton(btn)
            self.cycle_buttons[value] = btn
            cycles_row.addWidget(btn)
        self.cycles_spin = QSpinBox()
        self.cycles_spin.setObjectName("cyclesSpin")
        self.cycles_spin.setRange(0, 100000)
        self.cycles_spin.setSpecialValueText("∞")
        self.cycles_spin.setValue(1)
        self.cycles_spin.setMinimumWidth(CYCLE_SPIN_MIN)
        self.cycles_spin.setFixedHeight(CHIP_HEIGHT)
        self.cycles_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.cycles_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.cycles_spin.setToolTip("Custom cycle count. 0 is forever.")
        self.cycles_spin.valueChanged.connect(self._set_cycle_count)
        row.addWidget(self.cycles_cluster)
        row.addWidget(self.cycles_spin)
        row.addSpacing(SPACE_MD)

        self.speed_label = self._cluster_label("Speed")
        row.addWidget(self.speed_label)

        self.speed_cluster = QWidget()
        self.speed_cluster.setObjectName("speedCluster")
        self.speed_cluster.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        speed_row = QHBoxLayout(self.speed_cluster)
        speed_row.setContentsMargins(CLUSTER_PAD, CLUSTER_PAD, CLUSTER_PAD, CLUSTER_PAD)
        speed_row.setSpacing(0)
        speed_row.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        self.speed_group = QButtonGroup(self)
        self.speed_group.setExclusive(False)
        self.speed_buttons: dict[float, QPushButton] = {}
        for value in SPEED_PRESETS:
            btn = QPushButton(f"{value:.1f}×")
            btn.setObjectName(f"speedChip_{value:.1f}".replace(".", "_"))
            btn.setCheckable(True)
            btn.setAutoExclusive(False)
            apply_button_kind(btn, "speed")
            self._lock_chrome(btn, CHIP_MIN_WIDTH, CHIP_HEIGHT)
            btn.setToolTip("Playback speed. 1.0× is the recorded timing.")
            btn.clicked.connect(lambda _, v=value: self._set_playback_speed(v))
            self.speed_group.addButton(btn)
            self.speed_buttons[value] = btn
            speed_row.addWidget(btn)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setObjectName("speedSpin")
        self.speed_spin.setRange(0.25, 4.0)
        self.speed_spin.setSingleStep(0.25)
        self.speed_spin.setDecimals(2)
        self.speed_spin.setValue(1.0)
        self.speed_spin.setSuffix("×")
        self.speed_spin.setMinimumWidth(SPEED_SPIN_MIN)
        self.speed_spin.setFixedHeight(CHIP_HEIGHT)
        self.speed_spin.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.speed_spin.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.speed_spin.setToolTip("Playback speed. 1.0× is the recorded timing.")
        self.speed_spin.valueChanged.connect(self._set_playback_speed)
        row.addWidget(self.speed_cluster)
        row.addWidget(self.speed_spin)

        header_col.addWidget(self.transport)
        layout.addWidget(header)
        self.banner = QLabel("")
        self.banner.setObjectName("banner")
        self.banner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.banner.setVisible(False)
        layout.addWidget(self.banner)
        self._sync_cycles_controls()
        self._sync_speed_controls()

    def _after_show(self) -> None:
        import os

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            self._sync_transport()
            return
        self._sync_screen_view()
        handle = self.windowHandle()
        if handle is not None:
            handle.screenChanged.connect(lambda *_: self._sync_screen_view())
        app = QApplication.instance()
        if app is not None:
            app.screenAdded.connect(lambda *_: self._sync_screen_view())
            app.screenRemoved.connect(lambda *_: self._sync_screen_view())
        if sys.platform == "darwin":
            from motif.macos import prompt_os_permission_dialogs

            prompt_os_permission_dialogs()
            extra = "  ·  local control on" if self.api.running else ""
            start = "Record (F9) to start" if not self.script.events else "F9 record"
            self.status.showMessage(
                "Ready  ·  Grant Accessibility + Input Monitoring to Motif  ·  "
                f"{start}  ·  F10 replay  ·  {exit_combo_label()} stop{extra}"
            )
        self._hotkeys.start()
        self._sync_ignore_region()
        self._sync_transport()

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
                    self._cycles_custom = True
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

    def _ignore_at(self, x: int, y: int) -> bool:
        """Called from pynput threads — must not touch Qt widgets."""
        with self._ignore_lock:
            picking = self._ignore_picking
            x1, y1, x2, y2 = self._ignore_rect
        if picking:
            return True
        return x1 <= x <= x2 and y1 <= y <= y2

    def _sync_ignore_region(self) -> None:
        geo = self.frameGeometry()
        with self._ignore_lock:
            self._ignore_rect = (geo.x(), geo.y(), geo.x() + geo.width(), geo.y() + geo.height())
            self._ignore_picking = self.picking_pixel

    def moveEvent(self, event) -> None:  # noqa: N802
        super().moveEvent(event)
        self._sync_ignore_region()

    def resizeEvent(self, event) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_ignore_region()
        self._sync_screen_view()

    @Slot(str)
    def _on_hotkey(self, name: str) -> None:
        if name == "stop":
            self.stop_all()
        elif name == "record":
            self.toggle_record()
        elif name == "play":
            self.toggle_play()

    @Slot(object)
    def _append_recorded(self, event: Event) -> None:
        if not event.name:
            event.name = event.display_name()
        self.script.events.append(event)
        # Recorder already stores origin-relative coords and sets origin on the
        # first spatial sample. Only rebase leftover absolute events.
        if event.has_position() and not self.script.origin_set:
            rebase_to_origin(self.script, event.x, event.y)
        self.dirty = True
        self.refresh(select_id=event.id)

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
        eid = event.id if event else ""
        self.path_view.set_script(self.script, eid)
        self.screen_view.set_script(self.script, eid)
        self._sync_screen_view()
        self._sync_title()
        if self.loop_forever_act:
            self.loop_forever_act.blockSignals(True)
            self.loop_forever_act.setChecked(self.script.loop.count == 0)
            self.loop_forever_act.blockSignals(False)
        self.refresh_transport()
        self._sync_cycles_controls()
        self._sync_speed_controls()
        if not self.worker:
            self.status.showMessage(self._idle_status())

    def _sync_title(self) -> None:
        mark = " •" if self.dirty else ""
        self.title.setText(self.script.name + mark)
        self.setWindowModified(self.dirty)
        self.setWindowTitle(f"Motif — {self.script.name}[*]")

    def _idle_status(self) -> str:
        api = f"  ·  localhost:{DEFAULT_PORT}" if self.api.running else ""
        if not self.script.events:
            return (
                f"No events yet  ·  Record (F9) or + Add  ·  F10 replay  ·  "
                f"{exit_combo_label()} stop{api}"
            )
        origin = f"{self.script.origin_x}, {self.script.origin_y}" if self.script.origin_set else "not set"
        return (
            f"{len(self.script.events)} events  ·  origin {origin}  ·  {self.script.humanize.preset}  ·  "
            f"{self.script.humanize.speed:g}×  ·  cycles {self.script.loop.count or '∞'}{api}"
        )

    def _sync_selection(self) -> None:
        event = self.current_event()
        self.inspector.bind(self.script, event)
        eid = event.id if event else ""
        self.path_view.set_script(self.script, eid)
        self.screen_view.set_script(self.script, eid)

    def _select_id(self, event_id: str, *, steal_focus: bool = True) -> None:
        for i in range(self.list.count()):
            if self.list.item(i).data(Qt.ItemDataRole.UserRole) == event_id:
                if steal_focus:
                    self.list.setCurrentRow(i)
                else:
                    self.list.blockSignals(True)
                    self.list.setCurrentRow(i)
                    self.list.blockSignals(False)
                    event = self.current_event()
                    eid = event.id if event else ""
                    self.path_view.set_script(self.script, eid)
                    self.screen_view.set_script(self.script, eid)
                break

    def _apply_order(self) -> None:
        by_id = {e.id: e for e in self.script.events}
        ordered = [by_id[i] for i in self.list.ordered_ids() if i in by_id]
        if [e.id for e in ordered] == [e.id for e in self.script.events]:
            return
        self._push_undo()
        self.script.events = ordered
        self.dirty = True
        eid = self.list.selected_id()
        self.path_view.set_script(self.script, eid)
        self.screen_view.set_script(self.script, eid)

    def _inspector_changed(self) -> None:
        self.dirty = True
        event = self.current_event()
        eid = event.id if event else ""
        self.path_view.set_script(self.script, eid)
        self.screen_view.set_script(self.script, eid)
        item = self.list.currentItem()
        if item and event:
            card = EventCard(event, selected=True)
            item.setSizeHint(card.sizeHint())
            self.list.setItemWidget(item, card)
        self._cycles_custom = self.script.loop.count != 1
        self._sync_title()
        if self.loop_forever_act:
            self.loop_forever_act.blockSignals(True)
            self.loop_forever_act.setChecked(self.script.loop.count == 0)
            self.loop_forever_act.blockSignals(False)
        self._sync_cycles_controls()
        self._sync_speed_controls()
        self.refresh_transport()

    def add_event(self, kind: EventType) -> None:
        self._push_undo()
        event = add_event_of_type(kind)
        idx = self.list.currentRow()
        insert_at = idx + 1 if idx >= 0 else len(self.script.events)
        self.script.events.insert(insert_at, event)
        self.dirty = True
        self.refresh(select_id=event.id)

    def delete_event(self) -> None:
        ids = set(self.list.selected_ids())
        if not ids:
            event = self.current_event()
            if event:
                ids.add(event.id)
        if not ids:
            return
        self._push_undo()
        self.script.events = [e for e in self.script.events if e.id not in ids]
        self.dirty = True
        self.refresh()

    def duplicate_event(self) -> None:
        event = self.current_event()
        if not event:
            return
        self._push_undo()
        clone = event.clone()
        idx = self.script.events.index(event) + 1
        self.script.events.insert(idx, clone)
        self.dirty = True
        self.refresh(select_id=clone.id)

    def select_all_events(self) -> None:
        focus = QApplication.focusWidget()
        if isinstance(focus, (QWidget,)) and focus is not self.list:
            from PySide6.QtWidgets import QLineEdit, QPlainTextEdit

            if isinstance(focus, (QLineEdit, QPlainTextEdit)):
                focus.selectAll()
                return
        self.list.selectAll()

    def zero_ground(self) -> None:
        event = self.current_event()
        if event is None or not event.has_position():
            event = first_spatial_event(self.script)
        if event is None:
            QMessageBox.information(self, "Zero ground", "Record or add a click first, then set origin.")
            return
        self._push_undo()
        screen_x = self.script.origin_x + event.x if self.script.origin_set else event.x
        screen_y = self.script.origin_y + event.y if self.script.origin_set else event.y
        rebase_to_origin(self.script, screen_x, screen_y)
        self.dirty = True
        self.refresh(select_id=event.id)
        self.status.showMessage("Origin is now that event. Other points shifted with it.")

    def origin_to_cursor(self) -> None:
        self._push_undo()
        pos = QCursor.pos()
        shift_origin_to(self.script, pos.x(), pos.y())
        self.dirty = True
        self.refresh()

    def begin_pixel_pick(self) -> None:
        self.picking_pixel = True
        self._sync_ignore_region()
        apply_banner(self.banner, "Click any screen pixel — Motif will capture its colour and position", "record")
        self.grabMouse()

    def mousePressEvent(self, event) -> None:  # noqa: N802
        if self.picking_pixel:
            self.releaseMouse()
            self.picking_pixel = False
            apply_banner(self.banner)
            self._sync_ignore_region()
            pos = QCursor.pos()
            try:
                color = grab_pixel(pos.x(), pos.y())
            except Exception:
                QMessageBox.warning(
                    self,
                    "Pixel",
                    "Could not read that pixel. Grant Screen Recording (Help → Permissions) and try again.",
                )
                return
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

    def _hotkey_busy(self) -> bool:
        return time.monotonic() < self._hotkey_until

    def _arm_hotkey_guard(self, ms: int = 140) -> None:
        self._hotkey_until = time.monotonic() + ms / 1000.0

    def _finish_recording(self) -> None:
        self.recorder.stop()
        self._ignore_timer.stop()
        QApplication.processEvents()
        set_recorded_feel(self.script)
        self._cycles_custom = False
        self.dirty = True
        self._dual_save_recording()
        apply_banner(self.banner)
        self.refresh()
        self.refresh_transport()

    def _dual_save_recording(self) -> None:
        """Write processed + raw sidecars so a take can be compared later."""
        raw = self.recorder.raw_events()
        if not raw:
            return
        if self.path is not None:
            processed = self.path
        else:
            name = (self.script.name or "Untitled motif").strip() or "Untitled motif"
            processed = project_dir() / f"{name}{EXTENSION}"
        self.path = save_script(self.script, processed)
        save_raw_capture(raw, raw_path_for(self.path), script=self.script)
        self.dirty = False
        self.status.showMessage(f"Saved {self.path.name} and {raw_path_for(self.path).name}")

    def toggle_record(self) -> None:
        if self._hotkey_busy():
            return
        self._arm_hotkey_guard()
        if self.worker:
            return
        if self.recorder.recording:
            self._finish_recording()
            return
        self.recorder.script = self.script
        self._sync_ignore_region()
        try:
            self.recorder.start()
        except RecorderStartError as exc:
            QMessageBox.warning(self, "Recording", str(exc))
            apply_banner(self.banner)
            self.refresh_transport()
            return
        self._ignore_timer.start()
        if sys.platform == "darwin" and not can_monitor_input():
            apply_banner(
                self.banner,
                "Recording — if nothing is captured, grant Accessibility + Input Monitoring to Motif (Help → Permissions) and reopen",
                "record",
            )
            QMessageBox.warning(self, "Permissions", permissions_help())
        else:
            apply_banner(
                self.banner,
                f"Recording every move, click, and key  ·  F9 or {exit_combo_label()} to stop",
                "record",
            )
        self.refresh_transport()

    def toggle_play(self) -> None:
        if self._hotkey_busy():
            return
        self._arm_hotkey_guard()
        if self.worker:
            self.stop_all()
            return
        self.start_play()

    def _replay_snapshot(self) -> Script:
        """One recorded cycle unless the user set Cycles / Forever."""
        snapshot = script_from_dict(script_to_dict(self.script))
        if not self._cycles_custom:
            snapshot.loop.count = 1
        return snapshot

    def start_play(self) -> None:
        if self.worker or self.recorder.recording:
            return
        if not self.script.enabled_events():
            self.status.showMessage("Nothing to replay — press Record (F9) or + Add first")
            self.refresh_transport()
            return
        snapshot = self._replay_snapshot()
        self._play_total = snapshot.loop.count
        self.thread = QThread(self)
        self.worker = PlayerWorker(snapshot)
        self.worker.moveToThread(self.thread)
        self.thread.started.connect(self.worker.run)
        self.worker.progressed.connect(self._on_progress)
        self.worker.finished_with.connect(self._on_play_done)
        self.thread.start()
        apply_banner(self.banner, f"Replaying  ·  {exit_combo_label()} to stop", "ok")
        self.status.showMessage(f"Replaying  ·  {exit_combo_label()} stop")
        self.refresh_transport()

    def _on_progress(self, cycle: int, index: int, name: str) -> None:
        total = self._play_total
        denom = "∞" if total <= 0 else str(total)
        count = len(self.script.enabled_events())
        self.status.showMessage(
            f"Cycle {cycle} / {denom}  ·  {index + 1}/{count}  ·  {name}  ·  {exit_combo_label()} stop"
        )
        # Do not select rows during replay. setCurrentRow can raise Motif and
        # macOS then swallows the last Control+Arrow space swipe.

    def _on_play_done(self, result: str) -> None:
        thread = self.thread
        self.thread = None
        self.worker = None
        # Last swipe already settled in the player. Do not activateWindow /
        # raise_ here — becoming key cancels a trailing Control+Arrow.
        apply_banner(self.banner)
        self.refresh_transport()
        labels = {"done": "Finished", "stopped": "Stopped", "failed": "Stopped — a wait timed out"}
        count = len(self.script.events)
        noun = "event" if count == 1 else "events"
        self.status.showMessage(
            f"{labels.get(result, result)}  ·  {count} {noun}  ·  Replay (F10) or Record (F9)"
        )
        if thread is not None:
            thread.quit()
            thread.wait(1500)

    def stop_all(self) -> None:
        if self.recorder.recording:
            self._finish_recording()
        if self.worker:
            self.worker.stop()
        if self.picking_pixel:
            self.picking_pixel = False
            self.releaseMouse()
            self._sync_ignore_region()
        if not self.recorder.recording and not self.worker:
            apply_banner(self.banner)
        self.refresh_transport()

    def _replay_tooltip(self, *, playing: bool, has_events: bool) -> str:
        if playing:
            return f"Replaying  ·  {exit_combo_label()} to stop"
        if not has_events:
            return "Record first"
        count = self.script.loop.count
        if count == 0:
            return "Replay this motif forever  ·  F10"
        if count == 1:
            return "Replay this motif once  ·  F10"
        return f"Replay this motif {count} times  ·  F10"

    def refresh_transport(self) -> None:
        """Record / Replay / Stop stay visible. Replay is never hidden."""
        playing = bool(self.worker)
        recording = self.recorder.recording
        has_events = bool(self.script.enabled_events())
        for widget in (
            self.rec_btn,
            self.replay_btn,
            self.stop_btn,
            self.exit_hint,
            self.cycles_cluster,
            self.cycles_spin,
            *self.cycle_buttons.values(),
            self.speed_cluster,
            self.speed_spin,
            *self.speed_buttons.values(),
        ):
            widget.show()
        for widget in (
            self.cycles_spin,
            *self.cycle_buttons.values(),
            self.speed_spin,
            *self.speed_buttons.values(),
        ):
            widget.setEnabled(True)
        self._lock_chrome(self.rec_btn, BUTTON_MIN_WIDTH)
        self._lock_chrome(self.replay_btn, BUTTON_MIN_WIDTH)
        self._lock_chrome(self.stop_btn, STOP_MIN_WIDTH)
        for value, btn in self.cycle_buttons.items():
            self._lock_chrome(btn, CYCLE_MIN_WIDTH, CHIP_HEIGHT)
        for btn in self.speed_buttons.values():
            self._lock_chrome(btn, CHIP_MIN_WIDTH, CHIP_HEIGHT)
        self.rec_btn.setEnabled(not playing)
        self.rec_btn.setText("Recording" if recording else "Record")
        apply_button_kind(self.rec_btn, "recording" if recording else "record")
        self.rec_btn.setToolTip("Stop recording  ·  F9" if recording else "Record mouse and keys  ·  F9")
        can_replay = has_events and not recording and not playing
        self.replay_btn.setEnabled(can_replay)
        self.replay_btn.setText("Playing" if playing else "Replay")
        if playing:
            apply_button_kind(self.replay_btn, "playing")
        elif has_events:
            apply_button_kind(self.replay_btn, "primary")
        else:
            apply_button_kind(self.replay_btn, "ghost")
        self.replay_btn.setToolTip(self._replay_tooltip(playing=playing, has_events=has_events))
        busy = playing or recording or self.picking_pixel
        self.stop_btn.setEnabled(busy)
        apply_button_kind(self.stop_btn, "stop" if busy else "ghost")
        self.stop_btn.setToolTip(f"Stop recording or replay  ·  {exit_combo_label()}")
        if hasattr(self, "record_act"):
            self.record_act.setEnabled(not playing)
            self.record_act.setText("Stop Recording" if recording else "Record")
            self.replay_act.setEnabled(can_replay)
            self.replay_act.setText("Stop Replay" if playing else "Replay")
            self.stop_act.setText(f"Stop ({exit_combo_label()})")
            self.stop_act.setEnabled(busy)
        if hasattr(self, "undo_act"):
            self.undo_act.setEnabled(bool(self._undo))

    def _sync_transport(self) -> None:
        self.refresh_transport()

    def _set_playback_speed(self, speed: float) -> None:
        speed = max(0.25, min(4.0, float(speed)))
        changed = abs(float(self.script.humanize.speed) - speed) > 1e-6
        self.script.humanize.speed = speed
        self._sync_speed_controls()
        if changed:
            self.dirty = True
            self.inspector.bind(self.script, self.current_event())
            self._sync_title()
            if not self.worker:
                self.status.showMessage(self._idle_status())

    def _sync_speed_controls(self) -> None:
        if not hasattr(self, "speed_spin") or not hasattr(self, "speed_buttons"):
            return
        speed = float(self.script.humanize.speed)
        self.speed_spin.blockSignals(True)
        self.speed_spin.setValue(speed)
        self.speed_spin.blockSignals(False)
        self.speed_group.setExclusive(False)
        for value, btn in self.speed_buttons.items():
            btn.setAutoExclusive(False)
            btn.blockSignals(True)
            btn.setChecked(abs(value - speed) < 1e-6)
            btn.blockSignals(False)
            polish(btn)

    def _sync_cycles_controls(self) -> None:
        if not hasattr(self, "cycles_spin") or not hasattr(self, "cycle_buttons"):
            return
        count = int(self.script.loop.count)
        self.cycles_spin.blockSignals(True)
        self.cycles_spin.setValue(count)
        self.cycles_spin.blockSignals(False)
        self.cycle_group.setExclusive(False)
        for value, btn in self.cycle_buttons.items():
            btn.setAutoExclusive(False)
            btn.blockSignals(True)
            btn.setChecked(value == count)
            btn.blockSignals(False)
            polish(btn)

    def _set_cycle_count(self, count: int) -> None:
        previous = int(self.script.loop.count)
        count = set_loop_count(self.script, count)
        self._cycles_custom = count != 1
        self.loop_forever_act.blockSignals(True)
        self.loop_forever_act.setChecked(count == 0)
        self.loop_forever_act.blockSignals(False)
        self._sync_cycles_controls()
        self.inspector.bind(self.script, self.current_event())
        self.refresh_transport()
        if count != previous:
            self.dirty = True
            self._sync_title()
            if not self.worker:
                self.status.showMessage(self._idle_status())

    def _sync_screen_view(self) -> None:
        app = QApplication.instance()
        screens = list(app.screens()) if app is not None else []
        displays: list[Display] = []
        for i, screen in enumerate(screens, 1):
            geo = screen.geometry()
            displays.append(
                Display(
                    index=i,
                    x=int(geo.x()),
                    y=int(geo.y()),
                    width=int(geo.width()),
                    height=int(geo.height()),
                    scale=float(screen.devicePixelRatio() or 1.0),
                    name=str(screen.name() or ""),
                )
            )
        displays = with_physical_origins(displays)
        set_displays(displays)
        window_screen = self.screen()
        if window_screen is not None:
            set_scale(float(window_screen.devicePixelRatio() or 1.0))
        if displays:
            x, y, width, height = virtual_rect(displays)
            self.screen_view.set_displays(displays, QRect(x, y, width, height))
        elif window_screen is not None:
            self.screen_view.set_screen_rect(window_screen.geometry())

    def _sane_sizes(self, values: object, fallback: list[int], mins: list[int]) -> list[int]:
        if not isinstance(values, list) or len(values) != len(fallback):
            return list(fallback)
        out = []
        for raw, floor, default in zip(values, mins, fallback):
            try:
                out.append(max(floor, int(raw)))
            except (TypeError, ValueError):
                out.append(default)
        return out

    def _restore_splitters(self) -> None:
        self.left_split.setSizes(
            self._sane_sizes(self.settings.get("split_left"), SPLITTER_LEFT_DEFAULT, [200, 118, 168])
        )
        self.main_split.setSizes(
            self._sane_sizes(self.settings.get("split_main"), SPLITTER_MAIN_DEFAULT, [480, 280])
        )

    def _persist_splitters(self) -> None:
        import os

        if os.environ.get("QT_QPA_PLATFORM") == "offscreen":
            return
        if not hasattr(self, "left_split") or not hasattr(self, "main_split"):
            return
        self.settings = save_settings(
            {
                "split_left": self.left_split.sizes(),
                "split_main": self.main_split.sizes(),
            }
        )

    def _apply_view_settings(self) -> None:
        self.screen_box.setVisible(bool(self.settings.get("show_screen_history", True)))
        self.path_box.setVisible(bool(self.settings.get("show_path", True)))

    def _toggle_path_view(self, checked: bool) -> None:
        self.settings = save_settings({"show_path": checked})
        self.path_box.setVisible(checked)

    def _toggle_screen_view(self, checked: bool) -> None:
        self.settings = save_settings({"show_screen_history": checked})
        self.screen_box.setVisible(checked)

    def _set_loop_forever(self, checked: bool) -> None:
        self._set_cycle_count(0 if checked else 1)

    def _set_play_once(self) -> None:
        self._set_cycle_count(1)

    def _replay_count(self, count: int, *, play: bool = True) -> None:
        if play and (self.worker or self.recorder.recording):
            return
        self._set_cycle_count(count)
        if play:
            self.start_play()

    def _push_undo(self) -> None:
        self._undo.append(script_to_dict(self.script))
        if len(self._undo) > 30:
            self._undo.pop(0)
        if hasattr(self, "undo_act"):
            self.undo_act.setEnabled(True)

    def undo(self) -> None:
        if not self._undo:
            return
        data = self._undo.pop()
        self.script = script_from_dict(data)
        self.recorder.script = self.script
        self.dirty = True
        self.refresh()

    def _on_api_menu(self, checked: bool) -> None:
        self._set_api_enabled(checked)

    def _set_api_enabled(self, enabled: bool, *, persist: bool = True, quiet: bool = False) -> None:
        if enabled:
            try:
                self.api.start()
            except OSError:
                self.api_act.blockSignals(True)
                self.api_act.setChecked(False)
                self.api_act.blockSignals(False)
                if persist:
                    self.settings = save_settings({"api_enabled": False})
                if not quiet:
                    QMessageBox.warning(
                        self,
                        "Local control",
                        f"Could not start localhost control on port {DEFAULT_PORT}. Another Motif may be using it.",
                    )
                return
        else:
            self.api.stop()
        if persist:
            self.settings = save_settings({"api_enabled": enabled})
        self.api_act.blockSignals(True)
        self.api_act.setChecked(self.api.running)
        self.api_act.blockSignals(False)
        if not quiet:
            if self.api.running:
                self.status.showMessage(f"Local control on  ·  http://127.0.0.1:{DEFAULT_PORT}")
            else:
                self.status.showMessage("Local control off")

    def show_about(self) -> None:
        from motif import __version__

        QMessageBox.about(
            self,
            "About Motif",
            f"<b>Motif</b> {__version__}<br><br>"
            "Record, edit, and replay mouse and keyboard.",
        )

    def show_preferences(self) -> None:
        dialog = QDialog(self)
        dialog.setWindowTitle("Preferences")
        form = QFormLayout(dialog)
        api_box = QCheckBox("Enable local control (localhost)")
        api_box.setChecked(self.api.running)
        api_box.setToolTip("Off by default. Only needed for scripts that call Motif over HTTP.")
        form.addRow(api_box)
        form.addRow(
            hint_label(
                "Local control is not required for recording or replay. "
                "Turn it on only if another program on this machine should drive Motif."
            )
        )
        if sys.platform == "darwin":
            perm = QPushButton("Permissions…")
            perm.clicked.connect(self.show_permissions)
            install = QPushButton("Install to Applications")
            install.clicked.connect(self.install_to_applications)
            form.addRow(perm)
            form.addRow(install)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._set_api_enabled(api_box.isChecked())

    def install_to_applications(self) -> None:
        if sys.platform != "darwin":
            QMessageBox.information(self, "Install", "Install to Applications is only available on macOS.")
            return
        try:
            root = Path(__file__).resolve().parents[2]
            if str(root) not in sys.path:
                sys.path.insert(0, str(root))
            import start as start_mod

            dest = start_mod.install_to_applications()
        except SystemExit as exc:
            QMessageBox.warning(self, "Install", f"Could not install Motif to Applications.\n\n{exc}")
            return
        except OSError as exc:
            QMessageBox.warning(self, "Install", str(exc))
            return
        QMessageBox.information(
            self,
            "Install",
            f"Installed {dest}.\n\n"
            "Grant Accessibility, Input Monitoring, and Screen Recording to that Motif, "
            "then open it from Applications.",
        )

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
        self._undo.clear()
        self.script = Script()
        self.recorder.script = self.script
        self.path = None
        self.dirty = False
        self._cycles_custom = False
        self.refresh()

    def load_example(self) -> None:
        if not self._confirm_discard():
            return
        self.script = example_script()
        self.recorder.script = self.script
        self.path = None
        self.dirty = True
        self._cycles_custom = self.script.loop.count != 1
        self.refresh()

    def open_script(self) -> None:
        if not self._confirm_discard():
            return
        filename, _ = QFileDialog.getOpenFileName(self, "Open motif", "", f"Motif (*{EXTENSION} *.json)")
        if filename:
            self._load_path(Path(filename))

    def _load_path(self, path: Path) -> None:
        try:
            loaded = load_script(path)
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
            QMessageBox.warning(self, "Open motif", f"Could not load:\n{path}\n\n{exc}")
            return
        self.script = loaded
        self.recorder.script = self.script
        self.path = path
        self.dirty = False
        self._cycles_custom = self.script.loop.count != 1
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
        QMessageBox.information(self, "Permissions", permissions_help())

    def show_api_help(self) -> None:
        state = "on" if self.api.running else "off"
        QMessageBox.information(
            self,
            "External control",
            "Local control is off by default. Recording and replay do not need it.\n\n"
            "Turn it on from Motif → Enable Local Control (localhost) or "
            f"Motif → Preferences. It is currently {state}.\n\n"
            "When on, other programs on this machine can drive Motif at 127.0.0.1 "
            f"(port {DEFAULT_PORT}). There is no password. Do not expose that port.\n\n"
            f"curl http://127.0.0.1:{DEFAULT_PORT}/status\n"
            f"curl -X POST http://127.0.0.1:{DEFAULT_PORT}/play\n"
            f"curl -X POST http://127.0.0.1:{DEFAULT_PORT}/stop\n\n"
            "Python:\n"
            "from motif import MotifClient\n"
            "MotifClient().play()\n\n"
            "CLI:\n"
            "python3 start.py play script.motif.json --loops 3",
        )

    def closeEvent(self, event: QCloseEvent) -> None:  # noqa: N802
        if not self._confirm_discard():
            event.ignore()
            return
        self._persist_splitters()
        self.stop_all()
        self._hotkeys.stop()
        self.api.stop()
        event.accept()


def configure_qt() -> None:
    import os

    import PySide6

    plugins = Path(PySide6.__file__).resolve().parent / "Qt" / "plugins"
    platforms = plugins / "platforms"
    if plugins.is_dir():
        os.environ.setdefault("QT_PLUGIN_PATH", str(plugins))
        if platforms.is_dir():
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms))
        if sys.platform == "darwin":
            os.environ.setdefault("QT_QPA_PLATFORM", "cocoa")
    QCoreApplication.addLibraryPath(str(plugins))
    QCoreApplication.addLibraryPath(str(platforms))


def run_app() -> int:
    configure_qt()
    prepare_input_hooks()
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName("Motif")
    app.setApplicationDisplayName("Motif")
    app.setOrganizationName("Motif")
    app.setStyle("Fusion")
    app.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont))
    app.setStyleSheet(QSS)
    window = MainWindow()
    window.show()
    return app.exec()
