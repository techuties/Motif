"""Capture mouse and keyboard into grouped, editable events."""

from __future__ import annotations

import time
from collections.abc import Callable
from threading import Lock

from pynput import keyboard, mouse

from motif.keys import HOTKEY_PLAY, HOTKEY_RECORD, HOTKEY_STOP, key_to_name
from motif.models import Event, EventType, Script, first_spatial_event, rebase_to_origin

ListenerGuard = Callable[[], bool]


class Recorder:
    def __init__(
        self,
        script: Script,
        on_event: Callable[[Event], None] | None = None,
        should_ignore: ListenerGuard | None = None,
        on_hotkey: Callable[[str], None] | None = None,
    ) -> None:
        self.script = script
        self.on_event = on_event
        self.should_ignore = should_ignore
        self.on_hotkey = on_hotkey
        self._lock = Lock()
        self._recording = False
        self._mouse: mouse.Listener | None = None
        self._keyboard: keyboard.Listener | None = None
        self._started = 0.0
        self._last_emit = 0.0
        self._path: list[dict[str, int]] = []
        self._last_move_at = 0.0
        self._pressed_keys: set[str] = set()

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        with self._lock:
            if self._recording:
                return
            self._recording = True
            self._started = time.monotonic()
            self._last_emit = self._started
            self._path.clear()
            self._pressed_keys.clear()
        self._mouse = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        self._keyboard = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mouse.start()
        self._keyboard.start()

    def stop(self) -> None:
        with self._lock:
            self._recording = False
        self._flush_path()
        if self._mouse:
            self._mouse.stop()
            self._mouse = None
        if self._keyboard:
            self._keyboard.stop()
            self._keyboard = None
        self._ensure_origin()

    def _ignored(self) -> bool:
        return bool(self.should_ignore and self.should_ignore())

    def _elapsed(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def _gap(self) -> int:
        now = time.monotonic()
        gap = int((now - self._last_emit) * 1000)
        self._last_emit = now
        return max(0, gap)

    def _rel(self, x: int, y: int) -> tuple[int, int]:
        if self.script.origin_set:
            return x - self.script.origin_x, y - self.script.origin_y
        return x, y

    def _emit(self, event: Event) -> None:
        if not event.name:
            event.name = event.display_name()
        self.script.events.append(event)
        if event.has_position() and not self.script.origin_set:
            rebase_to_origin(self.script, event.x, event.y)
        if self.on_event:
            self.on_event(event)

    def _flush_path(self) -> None:
        with self._lock:
            points = list(self._path)
            self._path.clear()
        if len(points) < 2:
            return
        last = points[-1]
        first_t = points[0]["t_ms"]
        event = Event(
            type=EventType.MOVE.value,
            name="Move",
            delay_ms=self._gap(),
            x=last["x"],
            y=last["y"],
            points=[{"x": p["x"], "y": p["y"], "t_ms": p["t_ms"] - first_t} for p in points],
        )
        self._emit(event)

    def _on_move(self, x: float, y: float) -> None:
        if not self._recording or self._ignored():
            return
        now = time.monotonic()
        if now - self._last_move_at < 0.012:
            return
        self._last_move_at = now
        with self._lock:
            pts = self._path
            if pts:
                last = pts[-1]
                if abs(last["x"] - int(x)) < 3 and abs(last["y"] - int(y)) < 3:
                    return
            rx, ry = self._rel(int(x), int(y))
            pts.append({"x": rx, "y": ry, "t_ms": self._elapsed()})

    def _on_click(self, x: float, y: float, button: mouse.Button, pressed: bool) -> None:
        if not self._recording or self._ignored():
            return
        self._flush_path()
        name = "Click" if pressed else "Release"
        rx, ry = self._rel(int(x), int(y))
        self._emit(
            Event(
                type=EventType.CLICK.value,
                name=f"{button.name.title()} {name.lower()}",
                delay_ms=self._gap(),
                x=rx,
                y=ry,
                button=button.name,
                pressed=pressed,
            )
        )

    def _on_scroll(self, x: float, y: float, dx: int, dy: int) -> None:
        if not self._recording or self._ignored():
            return
        self._flush_path()
        rx, ry = self._rel(int(x), int(y))
        self._emit(
            Event(
                type=EventType.SCROLL.value,
                name="Scroll",
                delay_ms=self._gap(),
                x=rx,
                y=ry,
                dx=int(dx),
                dy=int(dy),
            )
        )

    def _on_press(self, key) -> None:
        name = key_to_name(key)
        if name in HOTKEY_STOP:
            if self.on_hotkey:
                self.on_hotkey("stop")
            return
        if name in HOTKEY_RECORD:
            if self.on_hotkey:
                self.on_hotkey("record")
            return
        if name in HOTKEY_PLAY:
            if self.on_hotkey:
                self.on_hotkey("play")
            return
        if not self._recording or self._ignored():
            return
        if name in self._pressed_keys:
            return
        self._pressed_keys.add(name)
        self._flush_path()
        self._emit(
            Event(
                type=EventType.KEY_DOWN.value,
                name=f"Press {name}",
                delay_ms=self._gap(),
                key=name,
            )
        )

    def _on_release(self, key) -> None:
        name = key_to_name(key)
        if name in HOTKEY_STOP | HOTKEY_RECORD | HOTKEY_PLAY:
            return
        if not self._recording or self._ignored():
            return
        self._pressed_keys.discard(name)
        self._flush_path()
        self._emit(
            Event(
                type=EventType.KEY_UP.value,
                name=f"Release {name}",
                delay_ms=self._gap(),
                key=name,
            )
        )

    def _ensure_origin(self) -> None:
        if self.script.origin_set:
            return
        seed = first_spatial_event(self.script)
        if seed is None:
            return
        rebase_to_origin(self.script, seed.x, seed.y)
