"""Script and event models. Coordinates are stored relative to script.origin."""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field, fields
from enum import Enum
from typing import Any


class EventType(str, Enum):
    MOVE = "move"
    CLICK = "click"
    SCROLL = "scroll"
    KEY_DOWN = "key_down"
    KEY_UP = "key_up"
    WAIT = "wait"
    WAIT_PIXEL = "wait_pixel"
    WAIT_PIXEL_CHANGE = "wait_pixel_change"
    GO_ORIGIN = "go_origin"
    COMMENT = "comment"
    SWIPE = "swipe"


class PlayMode(str, Enum):
    ABSOLUTE = "absolute"
    FROM_CURSOR = "from_cursor"
    FROM_ORIGIN = "from_origin"


class PathStyle(str, Enum):
    RECORDED = "recorded"
    LINEAR = "linear"
    BEZIER = "bezier"
    OVERSHOOT = "overshoot"
    WANDER = "wander"
    SNAP = "snap"  # Advanced: teleport to dest. Default replay always travels.


class HumanizePreset(str, Enum):
    PRECISE = "precise"
    NATURAL = "natural"
    CAUTIOUS = "cautious"
    CUSTOM = "custom"


SPEED_PRESETS = (0.5, 1.0, 1.5, 2.0)
CYCLE_PRESETS = (1, 10, 100)
CYCLE_LABELS = {1: "Once", 10: "10", 100: "100"}


EVENT_LABELS = {
    EventType.MOVE: "Move",
    EventType.CLICK: "Click",
    EventType.SCROLL: "Scroll",
    EventType.KEY_DOWN: "Key down",
    EventType.KEY_UP: "Key up",
    EventType.WAIT: "Wait",
    EventType.WAIT_PIXEL: "When colour",
    EventType.WAIT_PIXEL_CHANGE: "When colour changes",
    EventType.GO_ORIGIN: "Go to origin",
    EventType.COMMENT: "Note",
    EventType.SWIPE: "Space",
}


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class HumanizeSettings:
    preset: str = HumanizePreset.PRECISE.value
    enabled: bool = False
    path: str = PathStyle.RECORDED.value
    travel_a_ms: float = 80.0
    travel_b_ms: float = 120.0
    target_width_px: float = 14.0
    min_travel_ms: int = 90
    max_travel_ms: int = 1400
    jitter_px: float = 0.0
    click_offset_px: float = 0.0
    dwell_before_click_ms: int = 0
    dwell_jitter_ms: int = 0
    click_hold_ms: int = 50
    click_hold_jitter_ms: int = 0
    key_hold_ms: int = 40
    key_hold_jitter_ms: int = 0
    inter_key_ms: int = 20
    inter_key_jitter_ms: int = 0
    timing_jitter: float = 0.0
    overshoot_chance: float = 0.0
    overshoot_px: float = 9.0
    speed: float = 1.0

    def apply_preset(self, name: str) -> None:
        self.preset = name
        if name == HumanizePreset.PRECISE.value:
            self.enabled = False
            self.path = PathStyle.RECORDED.value
            self.jitter_px = 0.0
            self.click_offset_px = 0.0
            self.dwell_before_click_ms = 0
            self.dwell_jitter_ms = 0
            self.click_hold_ms = 50
            self.click_hold_jitter_ms = 0
            self.key_hold_ms = 40
            self.key_hold_jitter_ms = 0
            self.inter_key_ms = 20
            self.inter_key_jitter_ms = 0
            self.timing_jitter = 0.0
            self.overshoot_chance = 0.0
        elif name == HumanizePreset.NATURAL.value:
            self.enabled = True
            self.path = PathStyle.BEZIER.value
            self.travel_a_ms = 80.0
            self.travel_b_ms = 120.0
            self.min_travel_ms = 90
            self.max_travel_ms = 1400
            self.jitter_px = 1.2
            self.click_offset_px = 2.0
            self.dwell_before_click_ms = 55
            self.dwell_jitter_ms = 35
            self.click_hold_ms = 70
            self.click_hold_jitter_ms = 25
            self.key_hold_ms = 70
            self.key_hold_jitter_ms = 30
            self.inter_key_ms = 45
            self.inter_key_jitter_ms = 40
            self.timing_jitter = 0.12
            self.overshoot_chance = 0.18
            self.overshoot_px = 9.0
        elif name == HumanizePreset.CAUTIOUS.value:
            self.enabled = True
            self.path = PathStyle.OVERSHOOT.value
            self.travel_a_ms = 130.0
            self.travel_b_ms = 180.0
            self.min_travel_ms = 160
            self.max_travel_ms = 2200
            self.jitter_px = 2.0
            self.click_offset_px = 3.0
            self.dwell_before_click_ms = 110
            self.dwell_jitter_ms = 60
            self.click_hold_ms = 90
            self.click_hold_jitter_ms = 40
            self.key_hold_ms = 95
            self.key_hold_jitter_ms = 45
            self.inter_key_ms = 80
            self.inter_key_jitter_ms = 70
            self.timing_jitter = 0.22
            self.overshoot_chance = 0.35
            self.overshoot_px = 14.0


@dataclass
class LoopSettings:
    count: int = 1  # 0 = forever
    gap_ms: int = 400
    return_to_origin: bool = False
    park_before_cycle: bool = False


REPLAY_X10 = 10
REPLAY_X100 = 100


@dataclass
class Event:
    id: str = field(default_factory=_new_id)
    type: str = EventType.WAIT.value
    name: str = ""
    enabled: bool = True
    delay_ms: int = 0
    x: int = 0
    y: int = 0
    button: str = "left"
    pressed: bool = True
    key: str = ""
    dx: int = 0
    dy: int = 0
    color: str = "#000000"
    tolerance: int = 18
    timeout_ms: int = 10000
    match: str = "is"  # is | is_not | brighter | darker
    poll_ms: int = 40
    duration_ms: int | None = None
    travel_ms: int | None = None
    path: str | None = None
    notes: str = ""
    points: list[dict[str, int]] = field(default_factory=list)
    direction: str = ""
    app: str = ""
    bundle_id: str = ""

    def type_enum(self) -> EventType:
        try:
            return EventType(self.type)
        except ValueError:
            return EventType.COMMENT

    def display_name(self) -> str:
        kind = self.type_enum()
        if kind == EventType.SWIPE:
            custom = self.name.strip()
            if custom and not _generated_switch_name(custom):
                return custom
            return switch_event_title(self)
        if self.name.strip():
            return self.name.strip()
        return EVENT_LABELS.get(kind, self.type.replace("_", " ").title())

    def summary(self) -> str:
        kind = self.type_enum()
        if kind == EventType.MOVE:
            n = len(self.points)
            extra = f" · {n} pts" if n else ""
            return f"To {self.x}, {self.y}{extra}"
        if kind == EventType.CLICK:
            action = "down" if self.pressed else "up"
            return f"{self.button.title()} {action} · {self.x}, {self.y}"
        if kind == EventType.SCROLL:
            return f"Wheel {self.dx}, {self.dy} · {self.x}, {self.y}"
        if kind == EventType.SWIPE:
            return switch_event_summary(self)
        if kind in (EventType.KEY_DOWN, EventType.KEY_UP):
            action = "down" if kind == EventType.KEY_DOWN else "up"
            return f"{self.key or '?'} {action}"
        if kind == EventType.WAIT:
            return f"{self.delay_ms} ms"
        if kind == EventType.WAIT_PIXEL:
            verb = {"is": "is", "is_not": "is not", "brighter": "brighter than", "darker": "darker than"}.get(
                self.match, self.match
            )
            return f"Pixel {self.x}, {self.y} {verb} {self.color}"
        if kind == EventType.WAIT_PIXEL_CHANGE:
            return f"Pixel {self.x}, {self.y} leaves {self.color}"
        if kind == EventType.GO_ORIGIN:
            return "Return to zero ground"
        if kind == EventType.COMMENT:
            return self.notes or "Note"
        return self.type

    def has_position(self) -> bool:
        return self.type_enum() in {
            EventType.MOVE,
            EventType.CLICK,
            EventType.SCROLL,
            EventType.WAIT_PIXEL,
            EventType.WAIT_PIXEL_CHANGE,
        }

    def clone(self) -> Event:
        return event_from_dict(event_to_dict(self))


@dataclass
class Script:
    name: str = "Untitled motif"
    version: int = 1
    origin_x: int = 0
    origin_y: int = 0
    origin_set: bool = False
    play_mode: str = PlayMode.ABSOLUTE.value
    events: list[Event] = field(default_factory=list)
    humanize: HumanizeSettings = field(default_factory=HumanizeSettings)
    loop: LoopSettings = field(default_factory=LoopSettings)
    notes: str = ""

    def enabled_events(self) -> list[Event]:
        return [e for e in self.events if e.enabled]


def _filter_known(cls: type, data: dict[str, Any]) -> dict[str, Any]:
    allowed = {f.name for f in fields(cls)}
    return {k: v for k, v in data.items() if k in allowed}


def event_to_dict(event: Event) -> dict[str, Any]:
    return asdict(event)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return default


def event_from_dict(data: dict[str, Any]) -> Event:
    payload = _filter_known(Event, data)
    points = payload.get("points") or []
    payload["points"] = [
        {"x": _as_int(p.get("x")), "y": _as_int(p.get("y")), "t_ms": _as_int(p.get("t_ms"))}
        for p in points
        if isinstance(p, dict)
    ]
    for key in ("x", "y", "delay_ms", "dx", "dy", "tolerance", "timeout_ms", "poll_ms"):
        if key in payload:
            payload[key] = _as_int(payload[key])
    for key in ("duration_ms", "travel_ms"):
        if key in payload and payload[key] is not None:
            payload[key] = _as_int(payload[key])
    return Event(**payload)


def set_loop_count(script: Script, count: int) -> int:
    """Set inspector Cycles / loop.count for a run. 0 means forever."""
    script.loop.count = max(0, int(count))
    return script.loop.count


def set_recorded_feel(script: Script) -> None:
    """Make Replay match the capture: Precise feel at 1.0×, one cycle, no extra parks."""
    script.humanize.apply_preset(HumanizePreset.PRECISE.value)
    script.humanize.speed = 1.0
    script.loop.count = 1
    script.loop.park_before_cycle = False
    script.loop.return_to_origin = False


# Mission Control space animation is ~400–600 ms. Replay waits at least this
# long after every swipe so the next click does not fire mid-transition.
SPACE_SETTLE_MS = 520
# Extra wait after the last swipe so macOS finishes the space change before
# Motif's UI can become key and swallow a trailing Control+Arrow.
FINAL_SWIPE_SETTLE_MS = 360
# Cursor warps this far (or more) when the active space changes. Consecutive
# samples this large are a space boundary, not a real mouse stroke.
SPACE_JUMP_PX = 480
# Drop mouse samples after a swipe so the coordinate jump is not recorded.
SWIPE_IGNORE_MOVES_S = 0.12
# Parked cursor: flush the pending destination as one MOVE, then start a new one.
MOVE_IDLE_FLUSH_S = 0.45
# Replay walks recorded samples when a MOVE has at least this many points.
# Two-point (start+dest) files interpolate so the cursor still travels.
WALK_MIN_POINTS = 3
# Legacy helper: start + destination only. Replay no longer stores just this.
MAX_PROCESSED_MOVE_POINTS = 2
_DEFAULT_SCREEN_W = 1280
_DEFAULT_SCREEN_H = 800


def direction_from_delta(dx: float, dy: float) -> str:
    """Map a swipe/scroll delta to left/right/up/down, or '' if too small."""
    if abs(dx) < 1e-6 and abs(dy) < 1e-6:
        return ""
    if abs(dx) >= abs(dy):
        return "left" if dx < 0 else "right"
    return "up" if dy > 0 else "down"


def opposite_swipe(direction: str) -> str:
    """The swipe that undoes a space change."""
    return {"left": "right", "right": "left", "up": "down", "down": "up"}.get(direction, "left")


def swipe_deltas(direction: str) -> tuple[int, int]:
    return {
        "left": (-1, 0),
        "right": (1, 0),
        "up": (0, 1),
        "down": (0, -1),
    }.get(direction, (1, 0))


def event_app_name(event: Event) -> str:
    return (event.app or "").strip()


def is_app_switch(event: Event) -> bool:
    """True when Replay should try to bring a recorded app forward."""
    if event.type_enum() != EventType.SWIPE:
        return False
    return bool(event_app_name(event) or (event.bundle_id or "").strip())


def event_kind_label(event: Event) -> str:
    """List chip: Switch app / Space, never Swipe."""
    kind = event.type_enum()
    if kind == EventType.SWIPE:
        return "Switch app" if is_app_switch(event) else "Space"
    return EVENT_LABELS.get(kind, event.type.replace("_", " ").title())


def _generated_switch_name(name: str) -> bool:
    text = (name or "").strip()
    if not text:
        return True
    if text.startswith("Swipe ") or text.startswith("Switch to "):
        return True
    return text in {"Space", "Switch app", "Swipe"}


def switch_event_title(event: Event) -> str:
    app = event_app_name(event)
    if app:
        return f"Switch to {app}"
    return "Space"


def space_fallback_label(event: Event) -> str:
    """Honest Control+Arrow label — never an invented Swipe up."""
    arrow = parse_ctrl_arrow(event.key)
    if arrow in {"up", "down"}:
        arrow = ""
    if not arrow:
        inferred = "inferred" in (event.notes or "").lower()
        way = event.direction if event.direction in {"left", "right"} else ""
        if way:
            arrow = replay_arrow_for_swipe(way, inferred=inferred, key=event.key)
    if arrow in {"left", "right"}:
        return f"Control+{arrow.title()}"
    return "Control+Right"


def switch_event_summary(event: Event) -> str:
    if is_app_switch(event):
        bundle = (event.bundle_id or "").strip()
        if bundle:
            return bundle
        if parse_ctrl_arrow(event.key) or event.direction in {"left", "right"}:
            return f"{space_fallback_label(event)} fallback"
        return "Activate app"
    return space_fallback_label(event)


def apply_swipe_direction(event: Event, direction: str, *, inferred: bool | None = None) -> Event:
    """Set direction, deltas, name, and the Control+Arrow Motif will replay."""
    way = direction or "right"
    event.direction = way
    event.dx, event.dy = swipe_deltas(way)
    if not event.name or _generated_switch_name(event.name):
        event.name = switch_event_title(event)
    if inferred is None:
        inferred = "inferred" in (event.notes or "").lower()
    event.key = swipe_shortcut_key(way, inferred=inferred)
    return event


def parse_ctrl_arrow(key: str) -> str:
    """'ctrl+right' / 'control+left' → arrow name, or '' if not a swipe shortcut."""
    raw = (key or "").strip().lower().replace(" ", "").replace("-", "+")
    if not raw:
        return ""
    parts = [part for part in raw.split("+") if part]
    if not any(part in {"ctrl", "control"} for part in parts):
        return ""
    for name in ("left", "right", "up", "down"):
        if name in parts:
            return name
    return ""


def replay_arrow_for_swipe(direction: str, *, inferred: bool = False, key: str = "") -> str:
    """Arrow to hold with Control when replaying a swipe.

    A stored key wins. Inferred space changes use the space axis (right means
    Move right a space). Hinted gestures keep natural-scrolling finger mapping.
    """
    stored = parse_ctrl_arrow(key)
    if stored:
        return stored
    way = direction or "right"
    if inferred and way in {"left", "right"}:
        return way
    return control_arrow_for_swipe(way)


def swipe_shortcut_key(direction: str, *, inferred: bool = False) -> str:
    """Persist the Mission Control shortcut so replay and the inspector agree."""
    return f"ctrl+{replay_arrow_for_swipe(direction, inferred=inferred)}"


def control_arrow_for_swipe(direction: str) -> str:
    """Mission Control shortcut for a finger swipe (natural scrolling).

    Finger-left reveals the space to the right, so the OS shortcut is Control+Right.
    Fullscreen apps are spaces on that same left/right axis — Control+Up is Mission
    Control, not a space switch.
    """
    return {"left": "right", "right": "left", "up": "up", "down": "down"}.get(direction, "right")


def resolve_space_swipe_direction(hint: str, last_direction: str) -> tuple[str, bool]:
    """Direction for a desktop/fullscreen space change.

    Spaces (including fullscreen) are horizontal. A leftover up/down hint from the
    green-button or a scroll is ignored. A later space change without a new hint
    is the return — opposite of the last swipe. The first unhinted change is
    'right' on the space axis (Move right a space), not a finger-right swipe.
    Returns (direction, inferred).
    """
    if hint in {"left", "right"}:
        return hint, False
    if last_direction:
        axis = last_direction if last_direction in {"left", "right"} else "right"
        return opposite_swipe(axis), True
    return "right", True


def should_auto_align(script: Script, *, returning: bool = False) -> bool:
    """Park/return extras: honor inspector on multi-cycle, skip a single Replay."""
    flag = script.loop.return_to_origin if returning else script.loop.park_before_cycle
    if not flag or not script.origin_set:
        return False
    if script.loop.count == 1 and not any(e.type_enum() == EventType.GO_ORIGIN for e in script.enabled_events()):
        return False
    return True


def humanize_from_dict(data: dict[str, Any] | None) -> HumanizeSettings:
    if not data:
        return HumanizeSettings()
    return HumanizeSettings(**_filter_known(HumanizeSettings, data))


def loop_from_dict(data: dict[str, Any] | None) -> LoopSettings:
    if not data:
        return LoopSettings()
    return LoopSettings(**_filter_known(LoopSettings, data))


def script_to_dict(script: Script) -> dict[str, Any]:
    return {
        "name": script.name,
        "version": script.version,
        "origin_x": script.origin_x,
        "origin_y": script.origin_y,
        "origin_set": script.origin_set,
        "play_mode": script.play_mode,
        "events": [event_to_dict(e) for e in script.events],
        "humanize": asdict(script.humanize),
        "loop": asdict(script.loop),
        "notes": script.notes,
        "kind": "motif",
    }


def is_space_jump(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    threshold: int = SPACE_JUMP_PX,
) -> bool:
    """True when two samples are too far apart to be one mouse stroke."""
    return abs(int(x1) - int(x0)) >= threshold or abs(int(y1) - int(y0)) >= threshold


def strip_trailing_space_jumps(
    points: list[dict[str, int]],
    threshold: int = SPACE_JUMP_PX,
) -> list[dict[str, int]]:
    """Keep the path before the last space-warp (cursor jump after a swipe)."""
    for i in range(len(points) - 1, 0, -1):
        prev, cur = points[i - 1], points[i]
        if is_space_jump(prev["x"], prev["y"], cur["x"], cur["y"], threshold):
            return list(points[:i])
    return list(points)


def click_centric_points(points: list[dict[str, int]]) -> list[dict[str, int]]:
    """Start + destination only. Kept for old tests / summaries, not for Replay."""
    if len(points) <= MAX_PROCESSED_MOVE_POINTS:
        return list(points)
    return [points[0], points[-1]]


def is_snap_path(settings: HumanizeSettings, event: Event | None = None) -> bool:
    """True when Feel is the advanced teleport (snap). Default replay never snaps."""
    style = (event.path if event is not None and event.path else None) or settings.path
    return style == PathStyle.SNAP.value


def attach_paths_from_raw(script: Script, raw_events: list[dict[str, Any]]) -> int:
    """Copy raw mouse samples onto MOVE events that only have a hop (start+dest).

    The event list stays click-centric. Replay uses these points as the path.
    Raw rows are absolute screen pixels; stored points stay origin-relative.
    Returns how many MOVE events gained a polyline.
    """
    if not raw_events or not script.origin_set:
        return 0
    segments = _raw_move_segments(raw_events, script.origin_x, script.origin_y)
    updated = 0
    next_seg = 0
    for event in script.events:
        if event.type_enum() != EventType.MOVE:
            continue
        if len(event.points) >= WALK_MIN_POINTS:
            continue
        match_i = None
        for i in range(next_seg, len(segments)):
            last = segments[i][-1]
            if abs(int(last["x"]) - event.x) <= 24 and abs(int(last["y"]) - event.y) <= 24:
                match_i = i
                break
        if match_i is None:
            continue
        chosen = segments[match_i]
        event.points = _renorm_points(chosen)
        span = move_travel_ms(chosen)
        if span is not None:
            event.travel_ms = span
        updated += 1
        next_seg = match_i + 1
    return updated


def _raw_move_segments(
    raw_events: list[dict[str, Any]],
    origin_x: int,
    origin_y: int,
) -> list[list[dict[str, int]]]:
    """Origin-relative polylines between clicks / keys / space changes."""
    segments: list[list[dict[str, int]]] = []
    current: list[dict[str, int]] = []
    for row in raw_events:
        if not isinstance(row, dict):
            continue
        kind = row.get("type")
        if kind == "move":
            if row.get("held") or row.get("space_jump"):
                if len(current) >= 2:
                    segments.append(current)
                current = []
                continue
            current.append(
                {
                    "x": _as_int(row.get("x")) - origin_x,
                    "y": _as_int(row.get("y")) - origin_y,
                    "t_ms": _as_int(row.get("t_ms")),
                }
            )
            continue
        if current:
            if len(current) >= 2:
                segments.append(current)
            current = []
    if len(current) >= 2:
        segments.append(current)
    return segments


def move_travel_ms(points: list[dict[str, int]]) -> int | None:
    """Duration of a click-centric stroke, or None when there is no travel."""
    if len(points) < 2:
        return None
    span = int(points[-1].get("t_ms") or 0) - int(points[0].get("t_ms") or 0)
    return span if span > 0 else None


def largest_space_jump_index(
    points: list[dict[str, int]],
    threshold: int = SPACE_JUMP_PX,
) -> int | None:
    """Index of the first point after the largest space-sized jump, or None."""
    best_i: int | None = None
    best_d = threshold - 1
    for i in range(1, len(points)):
        dx = abs(int(points[i]["x"]) - int(points[i - 1]["x"]))
        dy = abs(int(points[i]["y"]) - int(points[i - 1]["y"]))
        distance = max(dx, dy)
        if distance > best_d:
            best_d = distance
            best_i = i
    return best_i


def _renorm_points(points: list[dict[str, int]]) -> list[dict[str, int]]:
    first_t = int(points[0].get("t_ms") or 0)
    return [
        {"x": int(p["x"]), "y": int(p["y"]), "t_ms": int(p.get("t_ms") or 0) - first_t}
        for p in points
    ]


def _point_span(points: list[dict[str, int]]) -> tuple[int, int]:
    xs = [int(p["x"]) for p in points]
    ys = [int(p["y"]) for p in points]
    return max(xs) - min(xs), max(ys) - min(ys)


def _move_from_points(template: Event, points: list[dict[str, int]], delay_ms: int) -> Event:
    last = points[-1]
    return Event(
        type=EventType.MOVE.value,
        name=template.name or "Move",
        delay_ms=delay_ms,
        x=int(last["x"]),
        y=int(last["y"]),
        points=_renorm_points(points),
    )


def _repair_swipe_event(event: Event) -> Event:
    """Standalone space/switch row: no mouse path. App-only rows keep no fake key."""
    event.points = []
    if is_app_switch(event) and not event.direction and not parse_ctrl_arrow(event.key):
        if not event.name or _generated_switch_name(event.name):
            event.name = switch_event_title(event)
        return event
    way = event.direction or direction_from_delta(event.dx, event.dy) or "right"
    if not event.direction:
        event.direction = way
    if not parse_ctrl_arrow(event.key):
        apply_swipe_direction(event, way)
    return event


def split_cross_space_moves(
    events: list[Event],
    screen_width: int = _DEFAULT_SCREEN_W,
    screen_height: int = _DEFAULT_SCREEN_H,
) -> list[Event]:
    """Unstick a MOVE that recorded both sides of a swipe (load-time migration).

    If a move next to a swipe spans more than one screen and has a space-sized
    jump, keep the pre-jump stroke before the swipe and the post-jump stroke
    after it. Swipe events never keep mouse points.
    """
    out: list[Event] = []
    pending_after: Event | None = None
    count = len(events)
    for i, event in enumerate(events):
        if pending_after is not None:
            if event.type_enum() == EventType.SWIPE:
                out.append(_repair_swipe_event(event))
                out.append(pending_after)
                pending_after = None
                continue
            out.append(pending_after)
            pending_after = None

        if event.type_enum() == EventType.SWIPE:
            out.append(_repair_swipe_event(event))
            continue

        next_swipe = i + 1 < count and events[i + 1].type_enum() == EventType.SWIPE
        prev_swipe = bool(out) and out[-1].type_enum() == EventType.SWIPE
        if event.type_enum() != EventType.MOVE or not event.points or not (next_swipe or prev_swipe):
            out.append(event)
            continue
        span_w, span_h = _point_span(event.points)
        if span_w <= screen_width and span_h <= screen_height:
            out.append(event)
            continue
        cut = largest_space_jump_index(event.points)
        if cut is None:
            out.append(event)
            continue
        before = event.points[:cut]
        after = event.points[cut:]
        if next_swipe:
            if len(before) >= 2:
                event.points = _renorm_points(before)
                event.x = int(before[-1]["x"])
                event.y = int(before[-1]["y"])
                out.append(event)
            if len(after) >= 2:
                pending_after = _move_from_points(event, after, 0)
            continue
        if len(after) >= 2:
            event.points = _renorm_points(after)
            event.x = int(after[-1]["x"])
            event.y = int(after[-1]["y"])
        elif len(before) >= 2:
            event.points = _renorm_points(before)
            event.x = int(before[-1]["x"])
            event.y = int(before[-1]["y"])
        out.append(event)
    if pending_after is not None:
        out.append(pending_after)
    return out


def script_from_dict(data: dict[str, Any]) -> Script:
    events = split_cross_space_moves([event_from_dict(e) for e in data.get("events") or []])
    return Script(
        name=str(data.get("name") or "Untitled motif"),
        version=int(data.get("version") or 1),
        origin_x=int(data.get("origin_x") or 0),
        origin_y=int(data.get("origin_y") or 0),
        origin_set=bool(data.get("origin_set")),
        play_mode=str(data.get("play_mode") or PlayMode.ABSOLUTE.value),
        events=events,
        humanize=humanize_from_dict(data.get("humanize")),
        loop=loop_from_dict(data.get("loop")),
        notes=str(data.get("notes") or ""),
    )


def rebase_to_origin(script: Script, origin_x: int, origin_y: int) -> None:
    """Make (origin_x, origin_y) the zero ground. Event coords become relative to it."""
    dx = origin_x - script.origin_x
    dy = origin_y - script.origin_y
    if script.origin_set and dx == 0 and dy == 0:
        script.origin_x = origin_x
        script.origin_y = origin_y
        return
    for event in script.events:
        if event.has_position():
            if script.origin_set:
                event.x -= dx
                event.y -= dy
                for point in event.points:
                    point["x"] -= dx
                    point["y"] -= dy
            else:
                event.x -= origin_x
                event.y -= origin_y
                for point in event.points:
                    point["x"] -= origin_x
                    point["y"] -= origin_y
    script.origin_x = origin_x
    script.origin_y = origin_y
    script.origin_set = True


def shift_origin_to(script: Script, screen_x: int, screen_y: int) -> None:
    """Keep relative event coords, move where zero-ground lives on screen."""
    script.origin_x = screen_x
    script.origin_y = screen_y
    script.origin_set = True


def first_spatial_event(script: Script) -> Event | None:
    for event in script.events:
        if event.has_position() and event.type_enum() in {EventType.MOVE, EventType.CLICK}:
            return event
    for event in script.events:
        if event.has_position():
            return event
    return None


def screen_pos(script: Script, x: int, y: int, cursor: tuple[int, int] | None = None) -> tuple[int, int]:
    """Map origin-relative coords to global logical points (same space as pynput).

    absolute: origin + (x, y) — the recorded display, even if Motif moved.
    from_cursor: current cursor + (x, y) — follows the mouse, including another display.
    from_origin: same mapping as absolute after parking at origin.
    """
    mode = script.play_mode
    if mode == PlayMode.FROM_CURSOR.value and cursor is not None:
        return cursor[0] + x, cursor[1] + y
    return script.origin_x + x, script.origin_y + y
