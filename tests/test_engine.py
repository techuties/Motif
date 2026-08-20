from pathlib import Path

from motif.example import example_script
from motif.humanize import fitts_time_ms, generate_path, travel_ms
from motif.models import (
    Event,
    EventType,
    HumanizeSettings,
    Script,
    rebase_to_origin,
    screen_pos,
    script_from_dict,
    script_to_dict,
    shift_origin_to,
)
from motif.screen import RGB, matches, parse_hex
from motif.storage import load_script, save_script


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


def test_pixel_match_tolerance() -> None:
    green = parse_hex("#34C759")
    almost = RGB(green.r + 8, green.g, green.b)
    assert matches(almost, green, 18, "is")
    assert not matches(RGB(255, 0, 0), green, 18, "is")
    assert matches(RGB(255, 0, 0), green, 18, "is_not")
    assert matches(RGB(250, 250, 250), parse_hex("#888888"), 10, "brighter")
