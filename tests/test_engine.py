import random
import sys
from pathlib import Path

from motif.api import _origin_allowed
from motif.example import example_script
from motif.humanize import event_wait_ms, fitts_time_ms, generate_path, scale_ms, travel_ms
from motif.keys import EXIT_COMBO, SKIP_HOTKEYS, exit_combo_label, is_exit_combo, is_skip_hotkey
from motif.models import (
    FINAL_SWIPE_SETTLE_MS,
    SPACE_SETTLE_MS,
    SPEED_PRESETS,
    SWIPE_IGNORE_MOVES_S,
    WALK_MIN_POINTS,
    Event,
    EventType,
    HumanizePreset,
    HumanizeSettings,
    PathStyle,
    Script,
    apply_swipe_direction,
    attach_paths_from_raw,
    control_arrow_for_swipe,
    direction_from_delta,
    event_from_dict,
    event_kind_label,
    is_app_switch,
    opposite_swipe,
    parse_ctrl_arrow,
    rebase_to_origin,
    replay_arrow_for_swipe,
    resolve_space_swipe_direction,
    screen_pos,
    script_from_dict,
    script_to_dict,
    set_loop_count,
    set_recorded_feel,
    shift_origin_to,
    should_auto_align,
    space_fallback_label,
    split_cross_space_moves,
    swipe_shortcut_key,
)
from motif.player import Player, click_release_follows
from motif.screen import RGB, display_scale, matches, parse_hex, set_scale
from motif.storage import load_script, raw_path_for, save_raw_capture, save_script


def test_rebase_makes_selected_event_zero() -> None:
    script = Script()
    script.events = [
        Event(type=EventType.CLICK.value, x=800, y=400, pressed=True),
        Event(type=EventType.CLICK.value, x=900, y=420, pressed=True),
    ]
    rebase_to_origin(script, 800, 400)
    assert script.origin_set
    assert script.origin_x == 800
    assert script.origin_y == 400
    assert (script.events[0].x, script.events[0].y) == (0, 0)
    assert (script.events[1].x, script.events[1].y) == (100, 20)


def test_rebase_again_keeps_relative_shape() -> None:
    script = Script()
    script.events = [
        Event(type=EventType.CLICK.value, x=100, y=50, pressed=True),
        Event(type=EventType.MOVE.value, x=130, y=80),
    ]
    rebase_to_origin(script, 100, 50)
    rebase_to_origin(
        script,
        script.origin_x + script.events[1].x,
        script.origin_y + script.events[1].y,
    )
    assert (script.events[1].x, script.events[1].y) == (0, 0)
    assert (script.events[0].x, script.events[0].y) == (-30, -30)


def test_play_from_cursor_offsets() -> None:
    script = Script(play_mode="from_cursor", origin_x=10, origin_y=10, origin_set=True)
    assert screen_pos(script, 5, 7, cursor=(200, 300)) == (205, 307)


def test_play_absolute_keeps_recorded_display() -> None:
    script = Script(play_mode="absolute", origin_x=1800, origin_y=400, origin_set=True)
    assert screen_pos(script, 10, 20, cursor=(50, 60)) == (1810, 420)


def test_shift_origin_does_not_rewrite_events() -> None:
    script = Script()
    script.events = [Event(type=EventType.CLICK.value, x=12, y=4)]
    rebase_to_origin(script, 100, 100)
    shift_origin_to(script, 500, 500)
    assert script.events[0].x == 12 - 100
    assert script.origin_x == 500


def test_roundtrip_json(tmp_path: Path) -> None:
    script = example_script()
    path = save_script(script, tmp_path / "demo")
    assert str(path).endswith(".motif.json")
    loaded = load_script(path)
    assert loaded.name == script.name
    assert len(loaded.events) == len(script.events)
    assert loaded.events[5].type == EventType.WAIT_PIXEL.value
    clone = script_from_dict(script_to_dict(script))
    assert clone.events[2].x == script.events[2].x


def test_fitts_far_is_slower() -> None:
    near = fitts_time_ms(20, 14, 80, 120, 90, 1400)
    far = fitts_time_ms(800, 14, 80, 120, 90, 1400)
    assert far > near


def test_bezier_ends_on_target() -> None:
    settings = HumanizeSettings()
    settings.enabled = True
    path = generate_path(10, 10, 200, 80, settings, "bezier")
    assert path[-1] == (200, 80)
    assert len(path) >= 6


def test_travel_respects_override() -> None:
    settings = HumanizeSettings()
    assert travel_ms(0, 0, 400, 0, settings, override_ms=250) == 250


def test_new_script_defaults_to_precise() -> None:
    script = Script()
    assert script.humanize.preset == HumanizePreset.PRECISE.value
    assert script.humanize.enabled is False
    assert script.humanize.path == PathStyle.RECORDED.value
    assert script.humanize.speed == 1.0


def test_example_defaults_to_precise() -> None:
    assert example_script().humanize.preset == HumanizePreset.PRECISE.value
    assert example_script().humanize.enabled is False


def test_saved_natural_feel_still_loads() -> None:
    data = script_to_dict(Script())
    data["humanize"] = {
        "preset": HumanizePreset.NATURAL.value,
        "enabled": True,
        "path": PathStyle.BEZIER.value,
        "speed": 1.0,
        "jitter_px": 1.2,
        "click_offset_px": 2.0,
        "dwell_before_click_ms": 55,
    }
    loaded = script_from_dict(data)
    assert loaded.humanize.preset == HumanizePreset.NATURAL.value
    assert loaded.humanize.enabled is True
    assert loaded.humanize.path == PathStyle.BEZIER.value


def test_set_recorded_feel_is_precise_at_1x() -> None:
    script = Script()
    script.humanize.apply_preset(HumanizePreset.NATURAL.value)
    script.humanize.speed = 2.0
    script.loop.count = 0
    script.loop.park_before_cycle = True
    script.loop.return_to_origin = True
    set_recorded_feel(script)
    assert script.humanize.preset == HumanizePreset.PRECISE.value
    assert script.humanize.enabled is False
    assert script.humanize.path == PathStyle.RECORDED.value
    assert script.humanize.speed == 1.0
    assert script.loop.count == 1
    assert script.loop.park_before_cycle is False
    assert script.loop.return_to_origin is False


def test_new_script_replay_is_single_cycle() -> None:
    script = Script()
    assert script.loop.count == 1
    assert script.loop.park_before_cycle is False
    assert script.loop.return_to_origin is False
    assert should_auto_align(script) is False
    assert should_auto_align(script, returning=True) is False


def test_apply_preset_leaves_speed_alone() -> None:
    settings = HumanizeSettings()
    settings.speed = 2.0
    settings.apply_preset(HumanizePreset.PRECISE.value)
    assert settings.speed == 2.0
    settings.apply_preset(HumanizePreset.NATURAL.value)
    assert settings.speed == 2.0


def test_speed_1x_uses_recorded_delays() -> None:
    settings = HumanizeSettings()
    settings.apply_preset(HumanizePreset.PRECISE.value)
    settings.speed = 1.0
    assert scale_ms(200, settings) == 200
    assert event_wait_ms(200, settings) == 200
    waits: list[int] = []
    player = Player()
    player._sleep = lambda ms: waits.append(ms) or True
    script = Script()
    script.humanize = settings
    event = Event(type=EventType.WAIT.value, delay_ms=200)
    assert player._play_event(script, event, random.Random(0), (0, 0))
    assert waits == [200]


def test_speed_2x_halves_waits() -> None:
    settings = HumanizeSettings()
    settings.apply_preset(HumanizePreset.PRECISE.value)
    settings.speed = 2.0
    assert scale_ms(200, settings) == 100
    assert event_wait_ms(200, settings) == 100
    waits: list[int] = []
    player = Player()
    player._sleep = lambda ms: waits.append(ms) or True
    script = Script()
    script.humanize = settings
    event = Event(type=EventType.WAIT.value, delay_ms=200)
    assert player._play_event(script, event, random.Random(0), (0, 0))
    assert waits == [100]
    waits.clear()
    move = Event(
        type=EventType.MOVE.value,
        x=12,
        y=0,
        points=[
            {"x": 0, "y": 0, "t_ms": 0},
            {"x": 6, "y": 0, "t_ms": 40},
            {"x": 12, "y": 0, "t_ms": 80},
        ],
    )
    player.mouse.position = (0, 0)
    assert player._move_to(script, 12, 0, move, random.Random(0), (0, 0))
    assert waits == [0, 20, 20]


def test_precise_does_not_generate_path_when_points_exist(monkeypatch) -> None:
    called: list[int] = []

    def fake_generate(*_args, **_kwargs):
        called.append(1)
        return [(10, 0)]

    monkeypatch.setattr("motif.player.generate_path", fake_generate)
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    event = Event(
        type=EventType.MOVE.value,
        x=10,
        y=0,
        points=[
            {"x": 0, "y": 0, "t_ms": 0},
            {"x": 5, "y": 0, "t_ms": 40},
            {"x": 10, "y": 0, "t_ms": 80},
        ],
    )
    player = Player()
    player._sleep = lambda _ms: True
    player.mouse.position = (0, 0)
    assert player._move_to(script, 10, 0, event, random.Random(0), (0, 0))
    assert called == []


class _DummyMouse:
    position = (0, 0)

    def press(self, *_args) -> None:
        return None

    def release(self, *_args) -> None:
        return None

    def scroll(self, *_args) -> None:
        return None


class _DummyKeys:
    def press(self, *_args) -> None:
        return None

    def release(self, *_args) -> None:
        return None


def test_precise_move_click_sleeps_recorded_delays_not_path_plus_dwell() -> None:
    waits: list[int] = []
    player = Player()
    player._sleep = lambda ms: waits.append(ms) or True
    player.mouse = _DummyMouse()
    player.keyboard = _DummyKeys()
    script = Script(origin_x=0, origin_y=0, origin_set=True)
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    script.humanize.speed = 1.0
    script.loop.count = 1
    script.loop.park_before_cycle = True
    script.loop.return_to_origin = True
    script.events = [
        Event(
            type=EventType.MOVE.value,
            delay_ms=50,
            x=10,
            y=0,
            points=[
                {"x": 0, "y": 0, "t_ms": 0},
                {"x": 5, "y": 0, "t_ms": 40},
                {"x": 10, "y": 0, "t_ms": 80},
            ],
        ),
        Event(type=EventType.CLICK.value, delay_ms=10, x=10, y=0, pressed=True, button="left"),
        Event(type=EventType.CLICK.value, delay_ms=20, x=10, y=0, pressed=False, button="left"),
    ]
    assert player.play(script) == "done"
    assert waits[0] == 50
    assert waits[-2:] == [10, 20]
    assert sum(waits[1:-2]) == 80
    assert len(waits[1:-2]) >= 2


def test_single_cycle_replay_skips_park_return() -> None:
    parked: list[str] = []
    player = Player()
    player._sleep = lambda _ms: True
    player.mouse = _DummyMouse()
    player._park = lambda *_args, **_kwargs: parked.append("park") or True
    script = Script(origin_x=0, origin_y=0, origin_set=True)
    script.loop.count = 1
    script.loop.park_before_cycle = True
    script.loop.return_to_origin = True
    script.events = [Event(type=EventType.WAIT.value, delay_ms=5)]
    assert player.play(script) == "done"
    assert parked == []
    script.loop.count = 2
    assert player.play(script) == "done"
    assert parked == ["park", "park", "park", "park"]


def test_swipe_direction_helpers() -> None:
    assert direction_from_delta(-3, 0.2) == "left"
    assert direction_from_delta(4, 1) == "right"
    assert direction_from_delta(0, 2) == "up"
    assert direction_from_delta(0, -2) == "down"
    assert control_arrow_for_swipe("left") == "right"
    assert control_arrow_for_swipe("right") == "left"
    assert opposite_swipe("left") == "right"
    assert opposite_swipe("right") == "left"
    event = Event(type=EventType.SWIPE.value, direction="left", notes="inferred from a space change")
    assert event_kind_label(event) == "Space"
    assert "Control+" in event.summary()
    apply_swipe_direction(event, "left", inferred=True)
    assert event.key == "ctrl+left"
    assert space_fallback_label(event) == "Control+Left"
    assert event.summary() == "Control+Left"


def test_swipe_shortcut_uses_space_axis_when_inferred() -> None:
    assert parse_ctrl_arrow("ctrl+right") == "right"
    assert parse_ctrl_arrow("control+left") == "left"
    assert parse_ctrl_arrow("enter") == ""
    assert replay_arrow_for_swipe("right", inferred=True) == "right"
    assert replay_arrow_for_swipe("left", inferred=True) == "left"
    assert replay_arrow_for_swipe("left", inferred=False) == "right"
    assert replay_arrow_for_swipe("right", inferred=False) == "left"
    assert replay_arrow_for_swipe("left", inferred=True, key="ctrl+right") == "right"
    assert swipe_shortcut_key("right", inferred=True) == "ctrl+right"
    assert swipe_shortcut_key("left", inferred=False) == "ctrl+right"
    hinted = Event(type=EventType.SWIPE.value)
    apply_swipe_direction(hinted, "left", inferred=False)
    assert hinted.key == "ctrl+right"
    inferred = Event(type=EventType.SWIPE.value, notes="inferred from a space change")
    apply_swipe_direction(inferred, "right", inferred=True)
    assert inferred.key == "ctrl+right"
    apply_swipe_direction(inferred, "left", inferred=True)
    assert inferred.key == "ctrl+left"


def test_opposite_swipe_directions_use_opposite_keys() -> None:
    from motif.keys import name_to_key
    from motif.macos import post_space_switch

    assert control_arrow_for_swipe("left") != control_arrow_for_swipe("right")
    assert control_arrow_for_swipe("up") != control_arrow_for_swipe("down")
    assert control_arrow_for_swipe("left") == "right"
    assert control_arrow_for_swipe("right") == "left"

    class Rec:
        def __init__(self) -> None:
            self.pressed: list = []

        def press(self, key) -> None:
            self.pressed.append(key)

        def release(self, _key) -> None:
            return None

    left = Rec()
    right = Rec()
    post_space_switch("left", left, native=False)
    post_space_switch("right", right, native=False)
    assert name_to_key("right") in left.pressed
    assert name_to_key("left") in right.pressed
    assert name_to_key("left") not in left.pressed
    assert name_to_key("right") not in right.pressed

    inferred_right = Rec()
    post_space_switch("right", inferred_right, native=False, inferred=True)
    assert name_to_key("right") in inferred_right.pressed
    assert name_to_key("left") not in inferred_right.pressed
    stored = Rec()
    post_space_switch("left", stored, native=False, key="ctrl+right")
    assert name_to_key("right") in stored.pressed
    assert name_to_key("left") not in stored.pressed


def test_two_space_changes_produce_two_swipes() -> None:
    from motif.macos import SwipeCapture

    got: list[tuple[str, bool]] = []
    capture = SwipeCapture(lambda way, inferred: got.append((way, inferred)))
    capture._running = True
    capture.handle_space_change()
    capture.handle_space_change()
    capture._flush_pending_space()
    assert [way for way, _ in got] == ["right", "left"]
    assert got[0][1] and got[1][1]
    capture.stop()
    hinted: list[tuple[str, bool]] = []
    other = SwipeCapture(lambda way, inferred: hinted.append((way, inferred)))
    other._running = True
    other.hint("left")
    other.handle_space_change()
    other.handle_space_change()
    other._flush_pending_space()
    assert [way for way, _ in hinted] == ["left", "right"]
    other.stop()
    assert resolve_space_swipe_direction("", "") == ("right", True)
    assert resolve_space_swipe_direction("left", "") == ("left", False)
    assert resolve_space_swipe_direction("", "left") == ("right", True)
    assert resolve_space_swipe_direction("up", "") == ("right", True)


def test_space_and_activate_are_one_switch(monkeypatch) -> None:
    from motif import macos
    from motif.macos import SwipeCapture

    monkeypatch.setattr(macos, "frontmost_app_info", lambda: ("Motif", "app.motif.recorder"))
    monkeypatch.setattr(
        macos,
        "is_motif_application",
        lambda name="", bundle_id="": (bundle_id or "") == "app.motif.recorder" or (name or "") == "Motif",
    )
    got: list[tuple[str, bool, str, str]] = []
    capture = SwipeCapture(
        lambda way, inferred, app="", bundle_id="": got.append((way, inferred, app, bundle_id))
    )
    capture._running = True
    try:
        capture.handle_space_change()
        assert got == []
        capture.handle_app_activate(name="Safari", bundle_id="com.apple.Safari")
        assert len(got) == 1
        assert got[0][2] == "Safari"
        assert got[0][3] == "com.apple.Safari"
        capture.handle_app_activate(name="Safari", bundle_id="com.apple.Safari")
        assert len(got) == 1
    finally:
        capture.stop()


def test_motif_activate_is_ignored() -> None:
    from motif.macos import SwipeCapture

    got: list = []
    capture = SwipeCapture(lambda *args, **_kwargs: got.append(args))
    capture._running = True
    try:
        capture.handle_app_activate(name="Motif", bundle_id="app.motif.recorder")
        assert got == []
    finally:
        capture.stop()


def test_switch_app_display_helpers() -> None:
    safari = Event(
        type=EventType.SWIPE.value,
        app="Safari",
        bundle_id="com.apple.Safari",
        direction="right",
        key="ctrl+right",
    )
    assert is_app_switch(safari)
    assert event_kind_label(safari) == "Switch app"
    assert safari.display_name() == "Switch to Safari"
    assert safari.summary() == "com.apple.Safari"

    legacy = Event(
        type=EventType.SWIPE.value,
        direction="up",
        name="Swipe up",
        key="ctrl+right",
        notes="Direction inferred from a space change",
    )
    assert not is_app_switch(legacy)
    assert event_kind_label(legacy) == "Space"
    assert legacy.display_name() == "Space"
    assert "swipe" not in legacy.display_name().lower()
    assert "up" not in legacy.summary().lower()
    assert space_fallback_label(legacy) == "Control+Right"
    assert legacy.summary() == "Control+Right"


def test_replay_activates_when_app_set(monkeypatch) -> None:
    activated: list[tuple[str, str]] = []
    posted: list = []
    monkeypatch.setattr(
        "motif.player.activate_app",
        lambda bundle_id="", name="": activated.append((bundle_id, name)) or True,
    )
    monkeypatch.setattr(
        "motif.player.post_space_switch",
        lambda *args, **_kwargs: posted.append(args) or "shortcut",
    )
    waits: list[int] = []
    player = Player()
    player._sleep = lambda ms: waits.append(ms) or True
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    event = Event(
        type=EventType.SWIPE.value,
        delay_ms=0,
        app="Safari",
        bundle_id="com.apple.Safari",
        direction="right",
        key="ctrl+right",
    )
    assert player._play_event(script, event, random.Random(0), (0, 0))
    assert activated == [("com.apple.Safari", "Safari")]
    assert posted == []
    assert waits == [SPACE_SETTLE_MS]


def test_replay_falls_back_when_activate_fails(monkeypatch) -> None:
    monkeypatch.setattr("motif.player.activate_app", lambda *_args, **_kwargs: False)
    posted: list[str] = []
    monkeypatch.setattr(
        "motif.player.post_space_switch",
        lambda way, _keyboard, **_kwargs: posted.append(way) or "shortcut",
    )
    player = Player()
    player._sleep = lambda _ms: True
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    event = Event(
        type=EventType.SWIPE.value,
        delay_ms=0,
        app="Safari",
        bundle_id="com.apple.Safari",
        direction="right",
        key="ctrl+right",
    )
    assert player._play_event(script, event, random.Random(0), (0, 0))
    assert posted == ["right"]


def test_recorder_stores_switch_app() -> None:
    import time

    from motif.macos import SWITCH_APP_NOTE
    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._on_swipe("right", True, "Photos", "com.apple.Photos")
    assert len(received) == 1
    event = received[0]
    assert event.type == EventType.SWIPE.value
    assert event.app == "Photos"
    assert event.bundle_id == "com.apple.Photos"
    assert event.display_name() == "Switch to Photos"
    assert event_kind_label(event) == "Switch app"
    assert SWITCH_APP_NOTE in event.notes


def test_recorder_space_and_activate_one_event(monkeypatch) -> None:
    import time

    from motif import macos
    from motif.macos import SwipeCapture
    from motif.recorder import Recorder

    monkeypatch.setattr(macos, "frontmost_app_info", lambda: ("Motif", "app.motif.recorder"))
    monkeypatch.setattr(
        macos,
        "is_motif_application",
        lambda name="", bundle_id="": (bundle_id or "") == "app.motif.recorder" or (name or "") == "Motif",
    )
    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    capture = SwipeCapture(rec._on_swipe)
    capture._running = True
    rec._swipe = capture
    try:
        capture.handle_space_change()
        capture.handle_app_activate(name="Safari", bundle_id="com.apple.Safari")
        swipes = [event for event in received if event.type == EventType.SWIPE.value]
        assert len(swipes) == 1
        assert swipes[0].app == "Safari"
        assert swipes[0].bundle_id == "com.apple.Safari"
        assert event_kind_label(swipes[0]) == "Switch app"
    finally:
        capture.stop()


def test_swipe_replay_sleeps_recorded_delay() -> None:
    waits: list[int] = []
    player = Player()
    player._sleep = lambda ms: waits.append(ms) or True
    player.keyboard = _DummyKeys()
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    event = Event(type=EventType.SWIPE.value, delay_ms=40, direction="left")
    assert player._play_event(script, event, random.Random(0), (0, 0))
    assert waits == [40, SPACE_SETTLE_MS]


def test_player_replays_inferred_file_on_space_axis() -> None:
    from motif.keys import name_to_key

    class Rec:
        def __init__(self) -> None:
            self.pressed: list = []

        def press(self, key) -> None:
            self.pressed.append(key)

        def release(self, _key) -> None:
            return None

    player = Player()
    player._sleep = lambda _ms: True
    player.keyboard = Rec()
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    # Latest take: inferred right/left, empty key — must Move right a space, not Control+Left.
    event = Event(
        type=EventType.SWIPE.value,
        delay_ms=0,
        direction="right",
        notes="Direction inferred from a space change — macOS does not deliver four-finger",
    )
    assert player._play_event(script, event, random.Random(0), (0, 0))
    assert name_to_key("right") in player.keyboard.pressed
    assert name_to_key("left") not in player.keyboard.pressed


def test_swipe_replay_waits_settle_even_when_delay_is_zero() -> None:
    waits: list[int] = []
    player = Player()
    player._sleep = lambda ms: waits.append(ms) or True
    player.keyboard = _DummyKeys()
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    swipe = Event(type=EventType.SWIPE.value, delay_ms=0, direction="right")
    click = Event(type=EventType.CLICK.value, delay_ms=10, x=4, y=4, pressed=True)
    player.mouse = _DummyMouse()
    player.mouse.position = (4, 4)
    assert player._play_event(script, swipe, random.Random(0), (0, 0))
    assert player._play_event(script, click, random.Random(0), (0, 0))
    assert waits == [SPACE_SETTLE_MS, 10]


def test_player_executes_last_swipe_in_list() -> None:
    posted: list[str] = []
    player = Player()
    player._sleep = lambda _ms: True
    player.mouse = _DummyMouse()
    player.keyboard = _DummyKeys()
    import motif.player as player_mod

    original = player_mod.post_space_switch

    def capture(way: str, _keyboard, **_kwargs) -> str:
        posted.append(way)
        return "shortcut"

    player_mod.post_space_switch = capture  # type: ignore[method-assign]
    try:
        script = Script()
        script.humanize.apply_preset(HumanizePreset.PRECISE.value)
        script.loop.count = 1
        script.events = [
            Event(type=EventType.WAIT.value, delay_ms=0),
            Event(type=EventType.SWIPE.value, delay_ms=0, direction="right", enabled=True),
            Event(type=EventType.SWIPE.value, delay_ms=0, direction="left", enabled=True),
        ]
        assert player.play(script) == "done"
        assert posted == ["right", "left"]
        assert player.index == -1
    finally:
        player_mod.post_space_switch = original


def test_consecutive_end_swipes_both_play() -> None:
    posted: list[str] = []
    waits: list[int] = []
    player = Player()
    player._sleep = lambda ms: waits.append(ms) or True
    player.mouse = _DummyMouse()
    player.keyboard = _DummyKeys()
    import motif.player as player_mod

    original = player_mod.post_space_switch
    player_mod.post_space_switch = lambda way, _kb, **_kw: posted.append(way) or "shortcut"  # type: ignore[method-assign]
    try:
        script = Script()
        script.humanize.apply_preset(HumanizePreset.PRECISE.value)
        script.loop.count = 1
        script.loop.return_to_origin = False
        script.loop.park_before_cycle = False
        script.events = [
            Event(type=EventType.CLICK.value, delay_ms=0, x=1, y=1, pressed=True),
            Event(type=EventType.SWIPE.value, delay_ms=0, direction="right"),
            Event(type=EventType.SWIPE.value, delay_ms=0, direction="left"),
        ]
        assert player.play(script) == "done"
        assert posted == ["right", "left"]
        assert waits[-2] == SPACE_SETTLE_MS
        assert waits[-1] == SPACE_SETTLE_MS + FINAL_SWIPE_SETTLE_MS
    finally:
        player_mod.post_space_switch = original


def test_stop_flushes_pending_space_change() -> None:
    import time

    from motif.macos import SwipeCapture
    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    capture = SwipeCapture(rec._on_swipe)
    capture._running = True
    rec._swipe = capture
    capture.hint("left")
    rec.stop()
    swipes = [event for event in received if event.type == EventType.SWIPE.value]
    assert len(swipes) == 1
    assert swipes[0].direction == "left"
    assert rec._swipe is None
    assert rec.recording is False


def test_stop_flushes_last_swipe_after_click() -> None:
    import time

    from pynput.mouse import Button

    from motif.macos import SwipeCapture
    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._last_move_at = 0.0
    rec._on_move(10.0, 12.0)
    rec._last_move_at = 0.0
    rec._on_move(40.0, 18.0)
    rec._on_click(40.0, 18.0, Button.left, True)
    rec._on_click(40.0, 18.0, Button.left, False)
    capture = SwipeCapture(rec._on_swipe)
    capture._running = True
    rec._swipe = capture
    capture.hint("right")
    rec.stop()
    kinds = [event.type for event in received]
    assert EventType.MOVE.value in kinds
    assert EventType.CLICK.value in kinds
    swipes = [event for event in received if event.type == EventType.SWIPE.value]
    assert len(swipes) == 1
    assert swipes[0].direction == "right"
    assert swipes[0].points == []
    assert kinds[-1] == EventType.SWIPE.value


def test_recorder_swipe_marks_inferred() -> None:
    import time

    from motif.macos import SWIPE_INFERRED_NOTE
    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._on_swipe("left", True)
    assert received[0].type == EventType.SWIPE.value
    assert received[0].direction == "left"
    assert received[0].dx == -1
    assert received[0].key == "ctrl+left"
    assert SWIPE_INFERRED_NOTE in received[0].notes
    rec._on_swipe("left", False)
    assert received[1].key == "ctrl+right"


def test_click_after_path_is_one_destination_move() -> None:
    import time

    from pynput.mouse import Button

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    for i in range(12):
        rec._last_move_at = 0.0
        rec._on_move(10.0 + i * 8, 20.0 + i * 2)
    rec._on_click(10.0 + 11 * 8, 20.0 + 11 * 2, Button.left, True)
    assert [event.type for event in received] == [EventType.MOVE.value, EventType.CLICK.value]
    move, click = received
    assert rec.script.origin_set
    assert (rec.script.origin_x, rec.script.origin_y) == (10, 20)
    assert len(move.points) >= WALK_MIN_POINTS
    assert (move.x, move.y) == (click.x, click.y)
    assert (click.x, click.y) == (88, 22)


def test_recorder_attaches_full_path_on_record() -> None:
    import time

    from pynput.mouse import Button

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    for i in range(16):
        rec._last_move_at = 0.0
        rec._on_move(20.0 + i * 6, 30.0 + i)
    rec._on_click(20.0 + 15 * 6, 30.0 + 15, Button.left, True)
    moves = [event for event in received if event.type == EventType.MOVE.value]
    assert len(moves) == 1
    assert len(moves[0].points) >= WALK_MIN_POINTS
    assert len(moves[0].points) >= 10
    xs = [p["x"] for p in moves[0].points]
    assert xs[0] == 0
    assert xs[-1] == moves[0].x
    assert any(0 < x < moves[0].x for x in xs)


def test_player_emits_multiple_move_samples() -> None:
    event = Event(
        type=EventType.MOVE.value,
        x=40,
        y=8,
        points=[
            {"x": 0, "y": 0, "t_ms": 0},
            {"x": 10, "y": 2, "t_ms": 20},
            {"x": 22, "y": 5, "t_ms": 40},
            {"x": 40, "y": 8, "t_ms": 70},
        ],
    )
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    player = Player()
    player._sleep = lambda _ms: True
    player.mouse = TrackingMouse()
    assert player._move_to(script, event.x, event.y, event, random.Random(0), (0, 0))
    assert len(player.mouse.steps) >= 4
    assert player.mouse.steps[0] != player.mouse.steps[-1]
    assert player.mouse.steps[-1] == (40, 8)


def test_attach_paths_from_raw_fills_two_point_moves() -> None:
    script = Script(origin_x=100, origin_y=200, origin_set=True)
    script.events = [
        Event(
            type=EventType.MOVE.value,
            x=40,
            y=10,
            points=[{"x": 0, "y": 0, "t_ms": 0}, {"x": 40, "y": 10, "t_ms": 80}],
        ),
        Event(type=EventType.CLICK.value, x=40, y=10, pressed=True),
        Event(
            type=EventType.SWIPE.value,
            app="Safari",
            bundle_id="com.apple.Safari",
        ),
        Event(
            type=EventType.MOVE.value,
            x=8,
            y=4,
            points=[{"x": 40, "y": 10, "t_ms": 0}, {"x": 8, "y": 4, "t_ms": 40}],
        ),
    ]
    raw = [
        {"type": "move", "t_ms": 0, "x": 100, "y": 200},
        {"type": "move", "t_ms": 20, "x": 110, "y": 204},
        {"type": "move", "t_ms": 40, "x": 125, "y": 208},
        {"type": "move", "t_ms": 80, "x": 140, "y": 210},
        {"type": "click", "t_ms": 90, "x": 140, "y": 210, "pressed": True},
        {"type": "app_activate", "t_ms": 120, "app": "Safari"},
        {"type": "move", "t_ms": 200, "x": 140, "y": 210},
        {"type": "move", "t_ms": 220, "x": 120, "y": 206},
        {"type": "move", "t_ms": 240, "x": 108, "y": 204},
    ]
    assert attach_paths_from_raw(script, raw) == 2
    first, second = script.events[0], script.events[3]
    assert len(first.points) >= WALK_MIN_POINTS
    assert [p["x"] for p in first.points] == [0, 10, 25, 40]
    assert len(second.points) >= WALK_MIN_POINTS
    assert second.points[-1]["x"] == 8
    assert script.events[2].points == []
    assert event_kind_label(script.events[2]) == "Switch app"


def test_load_script_recovers_path_from_sidecar(tmp_path: Path) -> None:
    processed = tmp_path / "take.motif.json"
    script = Script(name="take", origin_x=50, origin_y=60, origin_set=True)
    script.events = [
        Event(
            type=EventType.MOVE.value,
            x=20,
            y=0,
            points=[{"x": 0, "y": 0, "t_ms": 0}, {"x": 20, "y": 0, "t_ms": 50}],
        )
    ]
    save_script(script, processed)
    save_raw_capture(
        [
            {"type": "move", "t_ms": 0, "x": 50, "y": 60},
            {"type": "move", "t_ms": 15, "x": 58, "y": 60},
            {"type": "move", "t_ms": 30, "x": 64, "y": 61},
            {"type": "move", "t_ms": 50, "x": 70, "y": 60},
        ],
        raw_path_for(processed),
        script=script,
    )
    loaded = load_script(processed)
    assert len(loaded.events[0].points) >= WALK_MIN_POINTS
    assert [p["x"] for p in loaded.events[0].points] == [0, 8, 14, 20]


def test_swipe_between_clicks_does_not_span_one_move() -> None:
    import time

    from pynput.mouse import Button

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._last_move_at = 0.0
    rec._on_move(10.0, 14.0)
    rec._last_move_at = 0.0
    rec._on_move(40.0, 16.0)
    rec._on_click(40.0, 16.0, Button.left, True)
    rec._on_click(40.0, 16.0, Button.left, False)
    rec._last_move_at = 0.0
    rec._on_move(50.0, 16.0)
    rec._last_move_at = 0.0
    rec._on_move(60.0, 16.0)
    rec._on_swipe("right", True)
    rec._ignore_moves_until = 0.0
    rec._last_move_at = 0.0
    rec._on_move(20.0, 22.0)
    rec._last_move_at = 0.0
    rec._on_move(28.0, 24.0)
    rec._on_click(28.0, 24.0, Button.left, True)
    kinds = [event.type for event in received]
    assert EventType.SWIPE.value in kinds
    swipe_at = kinds.index(EventType.SWIPE.value)
    assert kinds[swipe_at - 1] == EventType.MOVE.value
    assert kinds[swipe_at + 1] == EventType.MOVE.value
    assert kinds[swipe_at + 2] == EventType.CLICK.value
    assert received[swipe_at].points == []
    assert rec.script.origin_set
    assert (rec.script.origin_x, rec.script.origin_y) == (10, 14)
    assert received[swipe_at - 1].x == 50
    assert (received[swipe_at + 1].x, received[swipe_at + 1].y) == (18, 10)
    assert received[swipe_at - 1].points
    assert received[swipe_at + 1].points


class TrackingMouse:
    def __init__(self, start: tuple[int, int] = (0, 0)) -> None:
        self._pos = start
        self.steps: list[tuple[int, int]] = []

    @property
    def position(self):
        return self._pos

    @position.setter
    def position(self, value) -> None:
        self._pos = (int(value[0]), int(value[1]))
        self.steps.append(self._pos)


def test_precise_walks_recorded_waypoints() -> None:
    points = [{"x": i * 2, "y": 0, "t_ms": i * 8} for i in range(47)]
    event = Event(type=EventType.MOVE.value, x=92, y=0, points=points)
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    player = Player()
    player._sleep = lambda _ms: True
    player.mouse = TrackingMouse()
    assert player._move_to(script, event.x, event.y, event, random.Random(0), (0, 0))
    assert len(player.mouse.steps) >= WALK_MIN_POINTS
    assert player.mouse.steps[-1] == (92, 0)
    assert (2, 0) in player.mouse.steps
    assert (20, 0) in player.mouse.steps


def test_snap_path_still_hops() -> None:
    points = [{"x": i * 2, "y": 0, "t_ms": i * 8} for i in range(12)]
    event = Event(type=EventType.MOVE.value, x=22, y=0, points=points, path=PathStyle.SNAP.value)
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    script.humanize.path = PathStyle.SNAP.value
    player = Player()
    player._sleep = lambda _ms: True
    player.mouse = TrackingMouse()
    assert player._move_to(script, event.x, event.y, event, random.Random(0), (0, 0))
    assert player.mouse.steps == [(22, 0)]


def test_old_two_point_file_still_moves() -> None:
    event = Event(
        type=EventType.MOVE.value,
        x=80,
        y=0,
        travel_ms=120,
        points=[{"x": 0, "y": 0, "t_ms": 0}, {"x": 80, "y": 0, "t_ms": 120}],
    )
    script = Script()
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    player = Player()
    player._sleep = lambda _ms: True
    player.mouse = TrackingMouse()
    assert player._move_to(script, event.x, event.y, event, random.Random(0), (0, 0))
    assert len(player.mouse.steps) >= 6
    assert player.mouse.steps[-1] == (80, 0)
    xs = [x for x, _y in player.mouse.steps]
    assert any(0 < x < 80 for x in xs)


def test_flush_path_delay_is_idle_before_motion() -> None:
    import time

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = time.monotonic() - 1.0
    rec._last_emit = rec._started + 0.2
    rec._path = [
        {"x": 0, "y": 0, "t_ms": 400},
        {"x": 12, "y": 0, "t_ms": 700},
    ]
    rec._flush_path()
    assert len(received) == 1
    assert abs(received[0].delay_ms - 200) <= 2
    assert received[0].travel_ms == 300
    assert len(received[0].points) == 2
    assert received[0].points[0]["t_ms"] == 0
    assert received[0].points[-1]["t_ms"] == 300
    assert received[0].x == 12
    rec._path = [{"x": i, "y": 0, "t_ms": 800 + i * 10} for i in range(12)]
    rec._flush_path()
    assert len(received) == 2
    assert len(received[1].points) == 12
    assert received[1].x == 11
    assert received[1].points[0]["x"] == 0
    assert received[1].travel_ms == 110


def test_swipe_flushes_move_and_keeps_swipe_pointless() -> None:
    import time

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._path = [
        {"x": 10, "y": 14, "t_ms": 80},
        {"x": 12, "y": 14, "t_ms": 100},
        {"x": 18, "y": -1188, "t_ms": 120},
        {"x": 20, "y": -1190, "t_ms": 140},
    ]
    rec._on_swipe("right", True)
    assert [event.type for event in received] == [EventType.MOVE.value, EventType.SWIPE.value]
    move, swipe = received
    assert [p["y"] for p in move.points] == [14, 14]
    assert swipe.points == []
    assert swipe.key == "ctrl+right"
    assert rec._path == []
    assert rec._ignore_moves_until > time.monotonic()


def test_moves_after_swipe_start_a_new_path() -> None:
    import time

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(origin_x=0, origin_y=0, origin_set=True), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._path = [{"x": 4, "y": 4, "t_ms": 20}, {"x": 8, "y": 6, "t_ms": 40}]
    rec._on_swipe("left", True)
    rec._last_move_at = 0.0
    rec._on_move(400.0, 50.0)
    rec._flush_path()
    assert [event.type for event in received] == [EventType.MOVE.value, EventType.SWIPE.value]
    rec._ignore_moves_until = 0.0
    rec._last_move_at = 0.0
    rec._on_move(20.0, 22.0)
    rec._last_move_at = 0.0
    rec._on_move(28.0, 24.0)
    rec._flush_path()
    types = [event.type for event in received]
    assert types == [EventType.MOVE.value, EventType.SWIPE.value, EventType.MOVE.value]
    assert received[1].points == []
    assert received[2].points[0]["x"] == 20
    assert received[2].x == 28
    assert SWIPE_IGNORE_MOVES_S >= 0.08


def test_recorder_raw_is_append_only_before_grouping() -> None:
    import time

    from pynput.mouse import Button

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._last_move_at = 0.0
    rec._on_move(10.0, 20.0)
    rec._last_move_at = 0.0
    rec._on_move(40.0, 24.0)
    rec._on_click(40.0, 24.0, Button.left, True)
    rec._push_raw("gesture", direction="left", gesture=True)
    rec._push_raw("space_change", space=True)
    rec._on_swipe("right", True)
    raw = rec.raw_events()
    assert [row["type"] for row in raw] == ["move", "move", "click", "gesture", "space_change"]
    assert raw[0]["x"] == 10 and raw[0]["y"] == 20
    assert raw[2]["button"] == "left" and raw[2]["pressed"] is True
    assert raw[3]["gesture"] is True
    assert raw[4]["space"] is True
    assert all("t_ms" in row for row in raw)
    snapshot = rec.raw_events()
    snapshot.append({"type": "fake"})
    snapshot[0]["x"] = 999
    stored = rec.raw_events()
    assert [row["type"] for row in stored] == ["move", "move", "click", "gesture", "space_change"]
    assert stored[0]["x"] == 10
    assert [event.type for event in received] == [EventType.MOVE.value, EventType.CLICK.value, EventType.SWIPE.value]


def test_load_splits_move_that_spans_a_swipe() -> None:
    script = script_from_dict(
        {
            "events": [
                {
                    "type": "move",
                    "x": 12,
                    "y": -1190,
                    "points": [
                        {"x": 0, "y": 14, "t_ms": 0},
                        {"x": 4, "y": 14, "t_ms": 20},
                        {"x": 10, "y": -1188, "t_ms": 40},
                        {"x": 12, "y": -1190, "t_ms": 60},
                    ],
                },
                {
                    "type": "swipe",
                    "direction": "right",
                    "notes": "inferred from a space change",
                    "points": [{"x": 99, "y": 99, "t_ms": 0}],
                },
            ]
        }
    )
    assert [event.type for event in script.events] == [
        EventType.MOVE.value,
        EventType.SWIPE.value,
        EventType.MOVE.value,
    ]
    assert [p["y"] for p in script.events[0].points] == [14, 14]
    assert script.events[0].y == 14
    assert script.events[1].points == []
    assert script.events[1].key == "ctrl+right"
    assert [p["y"] for p in script.events[2].points] == [-1188, -1190]
    assert script.events[2].y == -1190
    local = split_cross_space_moves(
        [
            Event(
                type=EventType.MOVE.value,
                x=80,
                y=10,
                points=[{"x": 0, "y": 0, "t_ms": 0}, {"x": 80, "y": 10, "t_ms": 40}],
            ),
            Event(type=EventType.SWIPE.value, direction="left"),
        ]
    )
    assert [event.type for event in local] == [EventType.MOVE.value, EventType.SWIPE.value]


def test_pixel_match_tolerance() -> None:
    green = parse_hex("#34C759")
    almost = RGB(green.r + 8, green.g, green.b)
    assert matches(almost, green, 18, "is")
    assert not matches(RGB(255, 0, 0), green, 18, "is")
    assert matches(RGB(255, 0, 0), green, 18, "is_not")
    assert matches(RGB(250, 250, 250), parse_hex("#888888"), 10, "brighter")


def test_parse_hex_invalid_is_black() -> None:
    assert parse_hex("not-a-color") == RGB(0, 0, 0)
    assert parse_hex("#fff") == RGB(255, 255, 255)


def test_event_coords_coerced_from_strings() -> None:
    event = event_from_dict({"type": "click", "x": "12", "y": "4.0", "delay_ms": "30"})
    assert (event.x, event.y, event.delay_ms) == (12, 4, 30)
    assert event_from_dict({"type": "nope"}).type_enum() == EventType.COMMENT


def test_click_release_follows_skips_notes() -> None:
    press = Event(type=EventType.CLICK.value, pressed=True, button="left")
    note = Event(type=EventType.COMMENT.value, notes="gap")
    release = Event(type=EventType.CLICK.value, pressed=False, button="left")
    assert click_release_follows(press, [note, release])
    assert not click_release_follows(press, [Event(type=EventType.MOVE.value, x=1, y=1)])
    assert not click_release_follows(press, [])


def test_origin_csrf_blocks_foreign_pages() -> None:
    assert _origin_allowed("", "127.0.0.1", 7842)
    assert _origin_allowed("http://127.0.0.1:7842", "127.0.0.1", 7842)
    assert not _origin_allowed("https://evil.example", "127.0.0.1", 7842)


def test_display_scale_uses_cache() -> None:
    set_scale(1.5)
    assert display_scale() == 1.5


def test_qt_plugin_env_uses_absolute_paths() -> None:
    import os
    import sys

    import start

    plugins = start.apply_qt_plugin_env(start.VENV)
    assert plugins is not None
    assert plugins.is_absolute()
    assert plugins.is_dir()
    assert " " not in str(plugins)
    assert Path(os.environ["QT_PLUGIN_PATH"]) == plugins
    platforms = Path(os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"])
    assert platforms.is_absolute()
    assert " " not in str(platforms)
    assert platforms == plugins / "platforms"
    assert platforms.is_dir()
    if sys.platform == "darwin":
        assert (platforms / "libqcocoa.dylib").exists()
        assert os.environ.get("QT_QPA_PLATFORM") == "cocoa"


def test_recorder_emits_without_appending() -> None:
    import time

    from pynput.mouse import Button

    from motif.recorder import Recorder

    received: list = []
    script = Script()
    rec = Recorder(script, on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._on_click(40, 80, Button.left, True)
    assert script.events == []
    assert script.origin_set
    assert (script.origin_x, script.origin_y) == (40, 80)
    assert [event.type for event in received] == [EventType.MOVE.value, EventType.CLICK.value]
    assert (received[0].x, received[0].y) == (0, 0)
    assert (received[1].x, received[1].y) == (0, 0)
    assert received[1].pressed is True


def test_recorder_ignores_points_inside_rect() -> None:
    import time

    from pynput.mouse import Button

    from motif.recorder import Recorder

    received: list = []
    rec = Recorder(
        Script(),
        on_event=received.append,
        should_ignore=lambda x, y: 0 <= x <= 100 and 0 <= y <= 50,
    )
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._on_click(10, 20, Button.left, True)
    rec._on_click(500, 400, Button.left, True)
    clicks = [event for event in received if event.type == EventType.CLICK.value]
    assert len(clicks) == 1
    assert (clicks[0].x, clicks[0].y) == (0, 0)
    assert rec.script.origin_set
    assert (rec.script.origin_x, rec.script.origin_y) == (500, 400)


def test_permissions_help_names_motif() -> None:
    from motif.macos import listener_start_help, permissions_help

    text = permissions_help()
    assert "Motif" in text
    if sys.platform == "darwin":
        assert "Accessibility" in text
        assert "Input Monitoring" in text
        assert "Screen Recording" in text
        assert "Motif.app" in text
        assert "Motif.app" in listener_start_help()
    elif sys.platform.startswith("linux"):
        assert "X11" in text
        assert "Wayland" in text
        assert "X11" in listener_start_help()
    else:
        assert "Windows" in text
        assert "Windows" in listener_start_help()


def test_macos_helpers_stub_off_darwin(monkeypatch) -> None:
    """AppKit / Spaces / TCC stay no-ops when the process is not macOS."""
    from motif import macos

    monkeypatch.setattr(macos.sys, "platform", "win32")
    macos.prepare_input_hooks()
    macos.prompt_os_permission_dialogs()
    assert macos.can_monitor_input() is True
    assert macos.frontmost_app_info() == ("", "")
    assert macos.current_app_identity() == ("", "")
    assert macos.app_from_notification(None) == ("", "")
    assert macos.activate_app("com.apple.Safari", "Safari") is False
    assert "Windows" in macos.permissions_help()
    assert "Windows" in macos.listener_start_help()
    capture = macos.SwipeCapture(lambda *_args, **_kwargs: None)
    capture.start()
    assert capture._running is False
    capture.stop()
    assert capture._monitors == []
    assert capture._observer is None

    monkeypatch.setattr(macos.sys, "platform", "linux")
    assert "X11" in macos.permissions_help()
    assert "X11" in macos.listener_start_help()
    linux_capture = macos.SwipeCapture(lambda *_args, **_kwargs: None)
    linux_capture.start()
    assert linux_capture._running is False
    linux_capture.stop()


def test_is_motif_app_follows_bundle_flag(monkeypatch) -> None:
    from motif.macos import is_motif_app

    monkeypatch.setenv("MOTIF_BUNDLE", "1")
    assert is_motif_app()
    monkeypatch.setenv("MOTIF_BUNDLE", "0")
    monkeypatch.setattr(sys, "argv", ["start.py"])
    monkeypatch.setattr(sys, "executable", sys.executable)
    assert not is_motif_app()


def test_settings_api_off_by_default(tmp_path, monkeypatch) -> None:
    from motif import storage

    monkeypatch.setattr(storage, "config_dir", lambda: tmp_path)
    assert storage.SETTINGS_DEFAULTS["api_enabled"] is False
    loaded = storage.load_settings()
    assert loaded["api_enabled"] is False
    assert loaded["show_path"] is True
    assert loaded["show_screen_history"] is True
    assert loaded["split_main"] == [900, 340]
    assert loaded["split_left"] == [480, 120, 220]
    storage.save_settings({"api_enabled": True})
    assert storage.load_settings()["api_enabled"] is True


def test_fit_screen_letterbox_and_map() -> None:
    from PySide6.QtCore import QRect

    from motif.ui.widgets import event_screen_xy, fit_screen_rect, map_screen_point

    screen = QRect(0, 0, 1920, 1080)
    view = QRect(0, 0, 800, 800)
    fitted = fit_screen_rect(screen, view, pad=0)
    assert fitted.width() == 800
    assert fitted.height() == 450
    assert fitted.x() == 0
    assert fitted.y() == (800 - 450) // 2
    center = map_screen_point(960, 540, screen, fitted)
    assert center.x() == 400
    assert center.y() == fitted.y() + 225
    script = Script(origin_x=100, origin_y=40, origin_set=True)
    event = Event(type=EventType.CLICK.value, x=20, y=10)
    assert event_screen_xy(script, event) == (120, 50)


def test_history_maps_second_screen_point() -> None:
    """A click on monitor 2 must land inside that screen’s letterboxed tile, not off-canvas."""
    from PySide6.QtCore import QRect

    from motif.screen import Display, logical_to_physical, set_displays, virtual_rect, with_physical_origins
    from motif.ui.widgets import displays_union_rect, fit_screen_rect, map_screen_point, map_screen_rect

    left = Display(index=1, x=0, y=0, width=1280, height=1080, scale=1.0)
    right = Display(index=2, x=1280, y=0, width=1920, height=1080, scale=1.0)
    displays = [left, right]
    desktop = displays_union_rect(displays)
    assert desktop == QRect(0, 0, 3200, 1080)
    assert virtual_rect(displays) == (0, 0, 3200, 1080)

    view = QRect(0, 0, 640, 216)
    fitted = fit_screen_rect(desktop, view, pad=0)
    assert fitted == view
    # x=2000 is 720px into the 1920-wide second screen.
    point = map_screen_point(2000, 540, desktop, fitted)
    assert point.x() == int(round(2000 / 3200 * 640))
    assert point.y() == int(round(540 / 1080 * 216))
    second = map_screen_rect(QRect(right.x, right.y, right.width, right.height), desktop, fitted)
    assert second.x() <= point.x() <= second.x() + second.width()
    assert second.y() <= point.y() <= second.y() + second.height()
    # Mapping onto only the Motif window’s screen would put x=2000 past the right edge.
    first_only = QRect(0, 0, 1280, 1080)
    wrong = map_screen_point(2000, 540, first_only, fitted)
    assert wrong.x() > fitted.x() + fitted.width()

    # Screen to the left of primary uses negative x — still inside the union.
    left_ext = Display(index=1, x=-1920, y=0, width=1920, height=1080, scale=1.0)
    primary = Display(index=2, x=0, y=0, width=1280, height=1080, scale=1.0)
    span = displays_union_rect([left_ext, primary])
    assert span == QRect(-1920, 0, 3200, 1080)
    fitted_span = fit_screen_rect(span, view, pad=0)
    left_pt = map_screen_point(-100, 540, span, fitted_span)
    left_tile = map_screen_rect(QRect(-1920, 0, 1920, 1080), span, fitted_span)
    assert left_tile.x() <= left_pt.x() <= left_tile.x() + left_tile.width()

    try:
        set_displays(with_physical_origins(displays))
        px, py = logical_to_physical(2000, 100)
        assert px == 2000
        assert py == 100
    finally:
        set_displays([])


def test_logical_to_physical_mixed_dpi_second_display() -> None:
    from motif.screen import Display, logical_to_physical, set_displays, with_physical_origins

    laptop = Display(index=1, x=0, y=0, width=1280, height=800, scale=2.0)
    external = Display(index=2, x=1280, y=0, width=1920, height=1080, scale=1.0)
    try:
        set_displays(with_physical_origins([laptop, external]))
        # 720 logical points into the 1× screen whose physical origin is 2560.
        px, py = logical_to_physical(2000, 40)
        assert px == 2560 + 720
        assert py == 40
        monitors = [
            {"left": 0, "top": 0, "width": 4480, "height": 2160},
            {"left": 0, "top": 0, "width": 2560, "height": 1600},
            {"left": 2560, "top": 0, "width": 1920, "height": 1080},
        ]
        mx, my = logical_to_physical(2000, 40, monitors=monitors)
        assert mx == 2560 + int(720 / 1920 * 1920)
        assert my == int(40 / 1080 * 1080)
    finally:
        set_displays([])


def test_api_does_not_listen_until_start() -> None:
    from motif.api import MotifAPI, MotifClient

    api = MotifAPI(port=17842, handlers={"GET /health": lambda _: {"ok": True}})
    assert api.running is False
    try:
        MotifClient(port=17842).health()
        raise AssertionError("localhost control should be off until start()")
    except ConnectionError:
        pass
    try:
        api.start()
        assert api.running is True
        assert MotifClient(port=17842).health()["ok"] is True
    finally:
        api.stop()
    assert api.running is False


def test_install_bookmark(tmp_path) -> None:
    import start

    src = tmp_path / "src" / "Motif.app"
    (src / "Contents" / "MacOS").mkdir(parents=True)
    (src / "Contents" / "Resources").mkdir(parents=True)
    (src / "Contents" / "Info.plist").write_text(
        '<?xml version="1.0"?><plist><dict>'
        "<key>CFBundleIdentifier</key><string>app.motif.recorder</string>"
        "</dict></plist>",
        encoding="utf-8",
    )
    dest = tmp_path / "Applications" / "Motif.app"
    project = tmp_path / "project"
    project.mkdir()
    start.install_app_bundle(src, dest, project, sign=False)
    assert start.read_project_bookmark(dest) == project.resolve()
    assert (dest / "Contents" / "Resources" / "MotifProject").read_text(encoding="utf-8").startswith(str(project.resolve()))
    assert start.is_motif_bundle(dest)


def test_tis_guard_is_safe_off_main_thread() -> None:
    import sys
    import threading

    if sys.platform != "darwin":
        return
    from motif.macos import prepare_input_hooks

    prepare_input_hooks()
    from pynput._util.darwin import keycode_context

    captured: list = []
    error: list = []

    def worker() -> None:
        try:
            with keycode_context() as ctx:
                captured.append(ctx)
        except Exception as exc:  # pragma: no cover
            error.append(exc)

    thread = threading.Thread(target=worker)
    thread.start()
    thread.join(timeout=2)
    assert not thread.is_alive()
    assert error == []
    assert captured
    assert captured[0] is not None


def test_inspector_hides_inapplicable_fields() -> None:
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from motif.ui.widgets import Inspector

    app = QApplication.instance() or QApplication(["motif-test"])
    _ = app
    inspector = Inspector()
    script = Script()
    move = Event(type=EventType.MOVE.value, x=8, y=4, name="Approach")
    inspector.bind(script, move)
    assert inspector.click_box.isHidden()
    assert inspector.key_box.isHidden()
    assert inspector.pixel_box.isHidden()
    assert inspector.swipe_box.isHidden()
    assert not inspector.pos_box.isHidden()
    assert not inspector.motion_box.isHidden()
    click = Event(type=EventType.CLICK.value, x=1, y=1)
    inspector.bind(script, click)
    assert not inspector.click_box.isHidden()
    assert inspector.key_box.isHidden()
    key = Event(type=EventType.KEY_DOWN.value, key="enter")
    inspector.bind(script, key)
    assert inspector.click_box.isHidden()
    assert not inspector.key_box.isHidden()
    assert inspector.pos_box.isHidden()
    swipe = Event(type=EventType.SWIPE.value, direction="left")
    inspector.bind(script, swipe)
    assert not inspector.swipe_box.isHidden()
    assert inspector.click_box.isHidden()
    assert inspector.pixel_box.isHidden()
    assert inspector.pos_box.isHidden()
    assert inspector.direction.isEnabled()
    assert inspector.app_name.isEnabled()
    inspector.direction.setCurrentText("right")
    inspector._commit()
    assert swipe.direction == "right"
    assert swipe.dx == 1
    assert swipe.key == "ctrl+left"
    safari = Event(type=EventType.SWIPE.value, app="Safari", bundle_id="com.apple.Safari")
    inspector.bind(script, safari)
    assert inspector.app_name.text() == "Safari"
    assert inspector.bundle_edit.text() == "com.apple.Safari"
    inspector.bind(script, None)
    assert inspector.form_box.isHidden()
    inspector.deleteLater()


def test_event_card_says_switch_app() -> None:
    from motif.ui.widgets import EventCard

    app = _offscreen_app()
    safari = Event(type=EventType.SWIPE.value, app="Mail", bundle_id="com.apple.mail")
    card = EventCard(safari)
    assert card.kind.text() == "SWITCH APP"
    assert card.title.text() == "Switch to Mail"
    assert card.detail.text() == "com.apple.mail"
    legacy = Event(type=EventType.SWIPE.value, direction="up", name="Swipe up", key="ctrl+right")
    card2 = EventCard(legacy)
    assert card2.kind.text() == "SPACE"
    assert card2.title.text() == "Space"
    assert card2.detail.text() == "Control+Right"
    card.deleteLater()
    card2.deleteLater()
    _ = app


def _offscreen_app():
    import os

    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication

    from motif.ui.theme import QSS

    app = QApplication.instance() or QApplication(["motif-test"])
    app.setStyleSheet(QSS)
    return app


def _close_window(win) -> None:
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QApplication

    win.dirty = False
    for timer in win.findChildren(QTimer):
        timer.stop()
    win.api.stop()
    win.close()
    win.deleteLater()
    app = QApplication.instance()
    if app is not None:
        app.processEvents()


def test_transport_idle_with_events_shows_replay() -> None:
    from PySide6.QtWidgets import QSizePolicy

    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.events = [Event(type=EventType.CLICK.value, x=1, y=1)]
        win.script.humanize.speed = 1.0
        win.refresh()
        assert win.replay_btn.parentWidget() is win.transport
        assert win.rec_btn.parentWidget() is win.transport
        assert win.stop_btn.parentWidget() is win.transport
        assert win.title.parentWidget() is win.title_bar
        assert win.title_bar is not win.transport
        row = win.transport.layout()
        assert row.itemAt(0).widget() is win.rec_btn
        assert row.itemAt(1).widget() is win.replay_btn
        assert row.itemAt(2).widget() is win.stop_btn
        assert row.itemAt(3).widget() is win.exit_hint
        assert row.itemAt(5).widget() is win.cycles_label
        assert row.itemAt(6).widget() is win.cycles_cluster
        assert row.itemAt(7).widget() is win.cycles_spin
        assert row.itemAt(9).widget() is win.speed_label
        assert row.itemAt(10).widget() is win.speed_cluster
        assert row.itemAt(11).widget() is win.speed_spin
        assert not win.replay_btn.isHidden()
        assert win.replay_btn.isEnabled()
        assert win.replay_btn.text() == "Replay"
        assert exit_combo_label() in win.exit_hint.text()
        assert exit_combo_label() in win.stop_btn.toolTip()
        assert win.replay_btn.property("kind") == "primary"
        assert win.replay_btn.minimumWidth() >= 104
        assert win.replay_btn.sizePolicy().horizontalPolicy() == QSizePolicy.Policy.Fixed
        assert win.replay_btn.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Fixed
        assert not win.rec_btn.isHidden()
        assert win.rec_btn.isEnabled()
        assert win.rec_btn.text() == "Record"
        assert win.rec_btn.property("kind") == "record"
        assert not win.stop_btn.isHidden()
        assert not win.stop_btn.isEnabled()
        assert list(win.cycle_buttons) == [1, 10, 100]
        assert win.cycle_buttons[1].text() == "Once"
        assert win.cycle_buttons[10].text() == "10"
        assert win.cycle_buttons[100].text() == "100"
        assert win.cycle_buttons[1].parentWidget() is win.cycles_cluster
        assert win.cycle_buttons[1].isChecked()
        assert not win.cycle_buttons[10].isChecked()
        assert win.cycles_spin.value() == 1
        assert list(win.speed_buttons) == list(SPEED_PRESETS)
        assert 1.0 in win.speed_buttons
        assert win.speed_buttons[1.0].parentWidget() is win.speed_cluster
        assert win.speed_buttons[1.0].text() == "1.0×"
        assert not win.speed_buttons[1.0].isHidden()
        assert win.speed_buttons[1.0].isChecked()
        assert not win.speed_buttons[0.5].isChecked()
        assert abs(win.speed_spin.value() - 1.0) < 1e-6
        win.replay_btn.hide()
        win.cycle_buttons[100].hide()
        win.refresh_transport()
        assert not win.replay_btn.isHidden()
        assert not win.cycle_buttons[100].isHidden()
    finally:
        _close_window(win)
        _ = app


def test_transport_no_events_disables_replay() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.refresh()
        assert not win.replay_btn.isHidden()
        assert not win.replay_btn.isEnabled()
        assert win.replay_btn.toolTip() == "Record first"
        assert win.rec_btn.isEnabled()
        assert not win.stop_btn.isEnabled()
        assert win.cycle_buttons[100].isEnabled()
        assert not win.cycle_buttons[100].isHidden()
        assert win.cycle_buttons[1].isChecked()
    finally:
        _close_window(win)
        _ = app


def test_transport_recording_and_playing_styles() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.events = [Event(type=EventType.CLICK.value, x=1, y=1)]
        win.recorder._recording = True
        win._sync_transport()
        assert not win.replay_btn.isHidden()
        assert not win.replay_btn.isEnabled()
        assert win.rec_btn.text() == "Recording"
        assert win.rec_btn.property("kind") == "recording"
        assert win.rec_btn.isEnabled()
        assert win.stop_btn.isEnabled()

        win.recorder._recording = False
        win.worker = object()
        win._sync_transport()
        assert not win.replay_btn.isHidden()
        assert win.replay_btn.text() == "Playing"
        assert win.replay_btn.property("kind") == "playing"
        assert not win.replay_btn.isEnabled()
        assert not win.rec_btn.isEnabled()
        assert win.stop_btn.isEnabled()

        win.worker = None
        win.refresh()
        assert not win.replay_btn.isHidden()
        assert win.replay_btn.isEnabled()
        assert win.replay_btn.text() == "Replay"
        assert not win.stop_btn.isEnabled()
    finally:
        _close_window(win)
        _ = app


def test_finish_recording_enables_replay_and_clears_banner() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.events = [Event(type=EventType.CLICK.value, x=1, y=1)]
        win.recorder._recording = True
        win.banner.setText("Recording")
        win.banner.setVisible(True)
        win._finish_recording()
        assert not win.recorder.recording
        assert not win.banner.isVisible()
        assert not win.replay_btn.isHidden()
        assert win.replay_btn.isEnabled()
        assert win.replay_btn.text() == "Replay"
        assert win.replay_btn.property("kind") == "primary"
        assert win.rec_btn.property("kind") == "record"
        assert not win.stop_btn.isEnabled()
        assert win.speed_buttons[1.0].isChecked()
        assert abs(win.speed_spin.value() - 1.0) < 1e-6
    finally:
        _close_window(win)
        _ = app


def test_origin_relative_click_after_rebase() -> None:
    """First spatial sample is origin; later clicks stay relative after UI append."""
    import time

    from pynput.mouse import Button

    from motif.recorder import Recorder
    from motif.ui.main_window import MainWindow

    received: list = []
    rec = Recorder(Script(), on_event=received.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._on_click(800, 400, Button.left, True)
    rec._on_click(800, 400, Button.left, False)
    rec._on_click(900, 420, Button.left, True)
    assert rec.script.origin_set
    assert (rec.script.origin_x, rec.script.origin_y) == (800, 400)
    clicks = [event for event in received if event.type == EventType.CLICK.value]
    assert (clicks[0].x, clicks[0].y) == (0, 0)
    assert (clicks[-1].x, clicks[-1].y) == (100, 20)
    assert all(event.has_position() is False or abs(event.x) < 500 for event in received)

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.origin_x = rec.script.origin_x
        win.script.origin_y = rec.script.origin_y
        win.script.origin_set = True
        for event in received:
            win._append_recorded(event)
        stored = [event for event in win.script.events if event.type == EventType.CLICK.value]
        assert (stored[0].x, stored[0].y) == (0, 0)
        assert (stored[-1].x, stored[-1].y) == (100, 20)
        assert (win.script.origin_x, win.script.origin_y) == (800, 400)
    finally:
        _close_window(win)
        _ = app


def test_raw_path_for_sits_beside_processed() -> None:
    assert raw_path_for(Path("/tmp/Untitled motif.motif.json")) == Path("/tmp/Untitled motif.raw.motif.json")


def test_dual_save_helpers_write_sidecars(tmp_path: Path) -> None:
    import json

    script = Script(name="take")
    script.events = [Event(type=EventType.CLICK.value, x=1, y=1)]
    processed = tmp_path / "take.motif.json"
    save_script(script, processed)
    save_raw_capture(
        [{"type": "move", "t_ms": 10, "x": 1, "y": 2}, {"type": "space_change", "t_ms": 40, "space": True}],
        raw_path_for(processed),
        script=script,
    )
    raw = tmp_path / "take.raw.motif.json"
    assert processed.is_file()
    assert raw.is_file()
    data = json.loads(raw.read_text(encoding="utf-8"))
    assert data["kind"] == "motif-raw"
    assert [event["type"] for event in data["events"]] == ["move", "space_change"]
    loaded = load_script(processed)
    assert loaded.events[0].x == 1


def test_finish_recording_dual_saves_sidecar(tmp_path: Path) -> None:
    import json
    import time

    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.path = tmp_path / "take.motif.json"
        win.script.events = [Event(type=EventType.CLICK.value, x=1, y=1)]
        win.recorder._recording = True
        win.recorder._started = time.monotonic()
        win.recorder._push_raw("move", x=10, y=20)
        win.recorder._push_raw("space_change", space=True)
        win._finish_recording()
        assert win.path.is_file()
        raw = tmp_path / "take.raw.motif.json"
        assert raw.is_file()
        data = json.loads(raw.read_text(encoding="utf-8"))
        assert data["kind"] == "motif-raw"
        assert [event["type"] for event in data["events"]] == ["move", "space_change"]
        assert not win.dirty
    finally:
        _close_window(win)
        _ = app


def test_play_done_keeps_replay_visible() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.events = [Event(type=EventType.CLICK.value, x=1, y=1)]
        win.worker = object()
        win.banner.setText("Replaying")
        win.banner.setVisible(True)
        win.refresh_transport()
        win._on_play_done("done")
        assert win.worker is None
        assert not win.banner.isVisible()
        assert not win.replay_btn.isHidden()
        assert win.replay_btn.isEnabled()
        assert win.replay_btn.text() == "Replay"
        assert "Finished" in win.status.currentMessage()
        assert "1 event" in win.status.currentMessage()
        assert "Replay" in win.status.currentMessage()
    finally:
        _close_window(win)
        _ = app


def test_replay_snapshot_is_one_cycle_unless_cycles_set() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.events = [Event(type=EventType.WAIT.value, delay_ms=1)]
        win.script.loop.count = 1
        win._cycles_custom = False
        assert win._replay_snapshot().loop.count == 1
        win.script.loop.count = 4
        win._cycles_custom = False
        assert win._replay_snapshot().loop.count == 1
        win._cycles_custom = True
        assert win._replay_snapshot().loop.count == 4
        win.script.loop.count = 0
        assert win._replay_snapshot().loop.count == 0
    finally:
        _close_window(win)
        _ = app


def test_speed_chips_follow_script_speed() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win._set_playback_speed(0.5)
        assert win.speed_buttons[0.5].isChecked()
        assert not win.speed_buttons[1.0].isChecked()
        assert abs(win.speed_spin.value() - 0.5) < 1e-6
        win._set_playback_speed(1.0)
        assert win.speed_buttons[1.0].isChecked()
        assert not win.speed_buttons[0.5].isChecked()
        assert not win.speed_buttons[1.5].isChecked()
        assert abs(win.speed_spin.value() - 1.0) < 1e-6
        assert abs(win.script.humanize.speed - 1.0) < 1e-6
    finally:
        _close_window(win)
        _ = app


def test_ui_patterns_and_inspector_groups() -> None:
    from PySide6.QtWidgets import QFrame, QPushButton

    from motif.ui.theme import SWATCH_H, SWATCH_W
    from motif.ui.widgets import (
        apply_button_kind,
        apply_swatch,
        empty_state_label,
        inspector_groups_for,
        section_header,
    )

    app = _offscreen_app()
    btn = QPushButton("Replay")
    apply_button_kind(btn, "primary")
    assert btn.property("kind") == "primary"
    apply_button_kind(btn, "ghost")
    assert btn.property("kind") == "ghost"
    head = section_header("EVENTS")
    assert head.property("role") == "section"
    assert head.text() == "EVENTS"
    empty = empty_state_label("No events yet")
    assert empty.property("role") == "empty"
    chip = QFrame()
    apply_swatch(chip, "#6AA6FF")
    assert chip.width() == SWATCH_W
    assert chip.height() == SWATCH_H
    click = Event(type=EventType.CLICK.value, x=1, y=1)
    assert inspector_groups_for(click) == frozenset({"event", "notes", "pos", "click", "motion"})
    wait = Event(type=EventType.WAIT.value)
    assert inspector_groups_for(wait) == frozenset({"event", "notes"})
    assert inspector_groups_for(None) == frozenset()
    btn.deleteLater()
    head.deleteLater()
    empty.deleteLater()
    chip.deleteLater()
    _ = app


def test_recording_menu_uses_replay() -> None:
    from PySide6.QtGui import QAction

    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        texts = [act.text() for act in win.menuBar().findChildren(QAction)]
        assert "Replay" in texts
        assert "Replay Once" in texts
        assert "Replay ×10" in texts
        assert "Replay ×100" in texts
        assert "Replay Forever" in texts
        assert f"Stop ({exit_combo_label()})" in texts
        assert "Play Once" not in texts
        assert "Play" not in texts
        assert win.replay_act.text() == "Replay"
    finally:
        _close_window(win)
        _ = app


def test_set_loop_count_100() -> None:
    script = Script()
    assert script.loop.count == 1
    assert set_loop_count(script, 100) == 100
    assert script.loop.count == 100
    assert set_loop_count(script, 0) == 0
    assert script.loop.count == 0


def test_exit_combo_is_in_skip_hotkey_set() -> None:
    assert EXIT_COMBO in SKIP_HOTKEYS
    assert "f9" in SKIP_HOTKEYS
    assert "f10" in SKIP_HOTKEYS
    assert "esc" in SKIP_HOTKEYS
    assert is_exit_combo("esc", {"ctrl", "alt"})
    assert is_skip_hotkey("esc", {"ctrl", "alt"})
    assert is_skip_hotkey("f10")
    assert not is_exit_combo("esc", {"ctrl"})
    assert not is_skip_hotkey("a", {"ctrl", "alt"})


def test_replay_x100_updates_inspector_cycles() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.events = [Event(type=EventType.WAIT.value, delay_ms=1)]
        win.refresh()
        win._replay_count(100, play=False)
        assert win.script.loop.count == 100
        assert win.inspector.loops.value() == 100
        assert win._cycles_custom is True
        assert win._replay_snapshot().loop.count == 100
        assert win.cycle_buttons[100].isChecked()
        assert not win.cycle_buttons[1].isChecked()
        assert win.cycles_spin.value() == 100
        assert "100 times" in win.replay_btn.toolTip()
        win._play_total = 100
        win._on_progress(3, 0, "Wait")
        assert win.status.currentMessage().startswith("Cycle 3 / 100")
    finally:
        _close_window(win)
        _ = app


def test_cycle_presets_set_count_without_playing() -> None:
    from motif.ui.main_window import MainWindow

    app = _offscreen_app()
    win = MainWindow()
    try:
        win.script.events = [Event(type=EventType.WAIT.value, delay_ms=1)]
        win.refresh()
        win.cycle_buttons[10].click()
        assert win.script.loop.count == 10
        assert win.inspector.loops.value() == 10
        assert win._cycles_custom is True
        assert win.worker is None
        assert win.cycle_buttons[10].isChecked()
        assert not win.cycle_buttons[1].isChecked()
        win.cycle_buttons[1].click()
        assert win.script.loop.count == 1
        assert win._cycles_custom is False
        assert win.cycle_buttons[1].isChecked()
        assert "once" in win.replay_btn.toolTip()
        win.inspector.loops.setValue(0)
        win._inspector_changed()
        assert win.cycles_spin.value() == 0
        assert not win.cycle_buttons[1].isChecked()
        assert not win.cycle_buttons[10].isChecked()
        assert not win.cycle_buttons[100].isChecked()
        assert win._cycles_custom is True
    finally:
        _close_window(win)
        _ = app


def test_recorder_skips_exit_combo() -> None:
    import time

    from pynput.keyboard import Key

    from motif.recorder import Recorder

    received: list = []
    hotkeys: list = []
    rec = Recorder(Script(), on_event=received.append, on_hotkey=hotkeys.append)
    rec._recording = True
    rec._started = rec._last_emit = time.monotonic()
    rec._on_press(Key.ctrl)
    rec._on_press(Key.alt)
    rec._on_press(Key.esc)
    rec._on_release(Key.esc)
    rec._on_release(Key.alt)
    rec._on_release(Key.ctrl)
    assert hotkeys == ["stop"]
    assert all(event.key != "esc" for event in received)
