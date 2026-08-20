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


class HumanizePreset(str, Enum):
    PRECISE = "precise"
    NATURAL = "natural"
    CAUTIOUS = "cautious"
    CUSTOM = "custom"


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
}


def _new_id() -> str:
    return uuid.uuid4().hex[:10]


@dataclass
class Point:
    x: int = 0
    y: int = 0
    t_ms: int = 0


@dataclass
class HumanizeSettings:
    preset: str = HumanizePreset.NATURAL.value
    enabled: bool = True
    path: str = PathStyle.BEZIER.value
    travel_a_ms: float = 80.0
    travel_b_ms: float = 120.0
    target_width_px: float = 14.0
    min_travel_ms: int = 90
    max_travel_ms: int = 1400
    jitter_px: float = 1.2
    click_offset_px: float = 2.0
    dwell_before_click_ms: int = 55
    dwell_jitter_ms: int = 35
    click_hold_ms: int = 70
    click_hold_jitter_ms: int = 25
    key_hold_ms: int = 70
    key_hold_jitter_ms: int = 30
    inter_key_ms: int = 45
    inter_key_jitter_ms: int = 40
    timing_jitter: float = 0.12
    overshoot_chance: float = 0.18
    overshoot_px: float = 9.0
    speed: float = 1.0

    def apply_preset(self, name: str) -> None:
        self.preset = name
        if name == HumanizePreset.PRECISE.value:
            self.enabled = False
            self.path = PathStyle.RECORDED.value
            self.jitter_px = 0.0
            self.click_offset_px = 0.0
            self.dwell_before_click_ms = 20
            self.dwell_jitter_ms = 0
            self.click_hold_ms = 50
            self.click_hold_jitter_ms = 0
            self.key_hold_ms = 40
            self.key_hold_jitter_ms = 0
            self.inter_key_ms = 20
            self.inter_key_jitter_ms = 0
            self.timing_jitter = 0.0
            self.overshoot_chance = 0.0
            self.speed = 1.0
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
            self.speed = 1.0
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
            self.speed = 0.78


@dataclass
class LoopSettings:
    count: int = 1  # 0 = forever
    gap_ms: int = 400
    return_to_origin: bool = True
    park_before_cycle: bool = True


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

    def type_enum(self) -> EventType:
        return EventType(self.type)

    def display_name(self) -> str:
        if self.name.strip():
            return self.name.strip()
        return EVENT_LABELS.get(self.type_enum(), self.type.replace("_", " ").title())

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


def event_from_dict(data: dict[str, Any]) -> Event:
    payload = _filter_known(Event, data)
    points = payload.get("points") or []
    payload["points"] = [
        {"x": int(p.get("x", 0)), "y": int(p.get("y", 0)), "t_ms": int(p.get("t_ms", 0))}
        for p in points
        if isinstance(p, dict)
    ]
    return Event(**payload)


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


def script_from_dict(data: dict[str, Any]) -> Script:
    events = [event_from_dict(e) for e in data.get("events") or []]
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
    mode = script.play_mode
    if mode == PlayMode.FROM_CURSOR.value and cursor is not None:
        return cursor[0] + x, cursor[1] + y
    return script.origin_x + x, script.origin_y + y
