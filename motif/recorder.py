"""Capture mouse and keyboard into grouped, editable events.

Listener callbacks must not touch Qt. They only build Event objects and pass
them to on_event / on_hotkey; the GUI marshals those onto the main thread.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

from pynput import keyboard, mouse

from motif.keys import (
    EXIT_MODIFIERS,
    EXIT_TRIGGER,
    HOTKEY_PLAY,
    HOTKEY_RECORD,
    HOTKEY_STOP,
    canonical_key,
    is_exit_combo,
    is_skip_hotkey,
    key_to_name,
)
from motif.macos import (
    RecorderStartError,
    SWIPE_INFERRED_NOTE,
    SWIPE_SHORTCUT_NOTE,
    SWITCH_APP_NOTE,
    SwipeCapture,
    app_from_notification,
    frontmost_app_info,
    listener_start_help,
    prepare_input_hooks,
)
from motif.models import (
    MOVE_IDLE_FLUSH_S,
    SWIPE_IGNORE_MOVES_S,
    Event,
    EventType,
    Script,
    apply_swipe_direction,
    is_space_jump,
    move_travel_ms,
    strip_trailing_space_jumps,
    switch_event_title,
)

ListenerGuard = Callable[[int, int], bool]


def _pump_main_loop() -> None:
    """Let AppKit / Qt deliver a delayed NSWorkspace space-change on stop."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is not None:
            app.processEvents()
            return
    except Exception:
        pass
    if sys.platform != "darwin":
        return
    try:
        from Foundation import NSDate, NSRunLoop

        NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.02))
    except Exception:
        pass


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
        self._last_xy = (0, 0)
        self._pressed_keys: set[str] = set()
        self._mods: set[str] = set()
        self._skip_exit_release = False
        self._swipe: SwipeCapture | None = None
        self._ignore_moves_until = 0.0
        self._raw: list[dict[str, Any]] = []
        self._flushing = False

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
            self._mods.clear()
            self._skip_exit_release = False
            self._ignore_moves_until = 0.0
            self._raw = []
        if sys.platform == "darwin":
            prepare_input_hooks()
            self._swipe = SwipeCapture(self._on_swipe)
            orig_hint = self._swipe.hint
            orig_space = self._swipe.handle_space_change
            orig_activate = self._swipe.handle_app_activate

            def _hint(direction: str) -> None:
                if direction:
                    self._push_raw("gesture", direction=direction, gesture=True)
                orig_hint(direction)

            def _space() -> None:
                name, bundle = frontmost_app_info()
                self._push_raw(
                    "space_change",
                    space=True,
                    app=name or None,
                    bundle_id=bundle or None,
                )
                orig_space()

            def _activate(name: str = "", bundle_id: str = "", notification=None) -> None:
                if notification is not None:
                    note_name, note_bundle = app_from_notification(notification)
                    name = name or note_name
                    bundle_id = bundle_id or note_bundle
                if not name and not bundle_id:
                    name, bundle_id = frontmost_app_info()
                self._push_raw(
                    "app_activate",
                    app=name or None,
                    bundle_id=bundle_id or None,
                )
                orig_activate(name=name, bundle_id=bundle_id, notification=notification)

            self._swipe.hint = _hint  # type: ignore[method-assign]
            self._swipe.handle_space_change = _space  # type: ignore[method-assign]
            self._swipe.handle_app_activate = _activate  # type: ignore[method-assign]
            self._swipe.start()
        self._keyboard = keyboard.Listener(on_press=self._on_press, on_release=self._on_release)
        self._mouse = mouse.Listener(
            on_move=self._on_move,
            on_click=self._on_click,
            on_scroll=self._on_scroll,
        )
        # Keyboard first: its thread used to call TIS off-main (SIGILL). The
        # layout is now cached on this (GUI) thread before either listener runs.
        try:
            self._start_one(self._keyboard, "keyboard")
            self._start_one(self._mouse, "mouse")
        except RecorderStartError:
            self.stop()
            raise
        except Exception as exc:
            self.stop()
            raise RecorderStartError(listener_start_help()) from exc

    def _start_one(self, listener, name: str) -> None:
        listener.start()
        listener.wait()
        if not listener.is_alive() and not listener.running:
            raise RecorderStartError(f"The {name} listener exited immediately.")

    def stop(self) -> None:
        self._flushing = True
        try:
            if self._swipe:
                try:
                    self._swipe.flush_pending(pump=_pump_main_loop)
                except Exception:
                    pass
            self._flush_path()
        finally:
            self._flushing = False
            with self._lock:
                self._recording = False
        if self._swipe:
            try:
                self._swipe.stop()
            except Exception:
                pass
            self._swipe = None
        if self._mouse:
            try:
                self._mouse.stop()
            except Exception:
                pass
            self._mouse = None
        if self._keyboard:
            try:
                self._keyboard.stop()
            except Exception:
                pass
            self._keyboard = None

    def _ignored(self, x: int, y: int) -> bool:
        return bool(self.should_ignore and self.should_ignore(x, y))

    def _elapsed(self) -> int:
        return int((time.monotonic() - self._started) * 1000)

    def _push_raw(self, kind: str, **fields: Any) -> None:
        """Append one raw sample. Entries are never updated after this call."""
        row: dict[str, Any] = {"type": kind, "t_ms": self._elapsed()}
        for key, value in fields.items():
            if value is not None:
                row[key] = value
        with self._lock:
            self._raw.append(row)

    def raw_events(self) -> list[dict[str, Any]]:
        """Shallow copies of the append-only capture, in record order."""
        with self._lock:
            return [dict(row) for row in self._raw]

    def _gap(self) -> int:
        now = time.monotonic()
        gap = int((now - self._last_emit) * 1000)
        self._last_emit = now
        return max(0, gap)

    def _rel(self, x: int, y: int) -> tuple[int, int]:
        """Screen point → origin-relative. First spatial sample becomes origin."""
        if not self.script.origin_set:
            self.script.origin_x = x
            self.script.origin_y = y
            self.script.origin_set = True
            return 0, 0
        return x - self.script.origin_x, y - self.script.origin_y

    def _emit(self, event: Event) -> None:
        if not event.name:
            event.name = event.display_name()
        if self.on_event:
            self.on_event(event)
            return
        with self._lock:
            self.script.events.append(event)

    def _clear_pending(self) -> None:
        with self._lock:
            self._path.clear()

    def _pin_dest(self, rx: int, ry: int) -> None:
        """Ensure the pending path ends on this click target (keep all samples)."""
        t_ms = self._elapsed()
        with self._lock:
            pts = self._path
            dest = {"x": rx, "y": ry, "t_ms": t_ms}
            if not pts:
                pts.append(dest)
                return
            last = pts[-1]
            if last["x"] == rx and last["y"] == ry:
                last["t_ms"] = t_ms
                return
            pts.append(dest)

    def _flush_path(self, *, drop_trailing_jumps: bool = False, required: bool = False) -> None:
        with self._lock:
            points = list(self._path)
            self._path.clear()
            started = self._started
            last_emit = self._last_emit
        if drop_trailing_jumps:
            points = strip_trailing_space_jumps(points)
        if len(points) < 2 and not (required and points):
            return
        last = points[-1]
        first_t = points[0]["t_ms"]
        last_emit_ms = int((last_emit - started) * 1000)
        idle = max(0, first_t - last_emit_ms)
        with self._lock:
            self._last_emit = time.monotonic()
        compact = [
            {"x": p["x"], "y": p["y"], "t_ms": p["t_ms"] - first_t} for p in points
        ]
        if len(compact) == 1:
            compact = []
        event = Event(
            type=EventType.MOVE.value,
            name="Move",
            delay_ms=idle,
            x=last["x"],
            y=last["y"],
            travel_ms=move_travel_ms(points),
            points=compact,
        )
        self._emit(event)

    def _hold_moves(self) -> None:
        with self._lock:
            self._path.clear()
            self._ignore_moves_until = time.monotonic() + SWIPE_IGNORE_MOVES_S

    def _on_swipe(
        self,
        direction: str,
        inferred: bool,
        app: str = "",
        bundle_id: str = "",
    ) -> None:
        if not self._recording and not self._flushing:
            return
        # Own MOVE first — never glue the space-change warp onto this switch.
        self._flush_path(drop_trailing_jumps=True)
        event = Event(
            type=EventType.SWIPE.value,
            delay_ms=self._gap(),
            app=(app or "").strip(),
            bundle_id=(bundle_id or "").strip(),
            points=[],
        )
        if direction:
            apply_swipe_direction(event, direction, inferred=inferred)
            event.points = []
        else:
            event.name = switch_event_title(event)
            event.direction = ""
            event.key = ""
        if event.app or event.bundle_id:
            extra = []
            if event.bundle_id:
                extra.append(f"Bundle {event.bundle_id}.")
            if event.key:
                extra.append(f"Fallback {event.key}.")
            event.notes = SWITCH_APP_NOTE + ((" " + " ".join(extra)) if extra else "")
        else:
            extra = [f"Replay {event.key}."] if event.key else []
            event.notes = (SWIPE_INFERRED_NOTE if inferred else SWIPE_SHORTCUT_NOTE)
            if extra:
                event.notes = f"{event.notes} {' '.join(extra)}"
        self._emit(event)
        self._hold_moves()

    def _on_move(self, x: float, y: float) -> None:
        if not self._recording:
            return
        ix, iy = int(x), int(y)
        self._last_xy = (ix, iy)
        if self._ignored(ix, iy):
            return
        now = time.monotonic()
        with self._lock:
            held = now < self._ignore_moves_until
        if now - self._last_move_at < 0.012:
            return
        self._last_move_at = now
        if held:
            self._push_raw("move", x=ix, y=iy, held=True)
            return
        flush_jump = False
        flush_idle = False
        with self._lock:
            pts = self._path
            rx, ry = self._rel(ix, iy)
            now_ms = self._elapsed()
            if pts:
                last = pts[-1]
                if now_ms - int(last.get("t_ms") or 0) >= int(MOVE_IDLE_FLUSH_S * 1000):
                    flush_idle = True
                elif abs(last["x"] - rx) < 3 and abs(last["y"] - ry) < 3:
                    return
                elif is_space_jump(last["x"], last["y"], rx, ry):
                    flush_jump = True
                else:
                    pts.append({"x": rx, "y": ry, "t_ms": now_ms})
            else:
                pts.append({"x": rx, "y": ry, "t_ms": now_ms})
        if flush_jump:
            # Space warp arrived before the swipe callback: close the old path.
            self._push_raw("move", x=ix, y=iy, space_jump=True)
            self._flush_path()
            self._hold_moves()
            return
        if flush_idle:
            self._flush_path()
            with self._lock:
                self._path.append({"x": rx, "y": ry, "t_ms": self._elapsed()})
            self._push_raw("move", x=ix, y=iy)
            return
        self._push_raw("move", x=ix, y=iy)

    def _on_click(self, x: float, y: float, button: mouse.Button, pressed: bool) -> None:
        if not self._recording:
            return
        ix, iy = int(x), int(y)
        self._last_xy = (ix, iy)
        if self._ignored(ix, iy):
            return
        self._push_raw("click", x=ix, y=iy, button=button.name, pressed=pressed)
        rx, ry = self._rel(ix, iy)
        self._pin_dest(rx, ry)
        if pressed:
            self._flush_path(required=True)
        else:
            with self._lock:
                pending = len(self._path)
            if pending >= 2:
                self._flush_path()
            else:
                self._clear_pending()
        name = "Click" if pressed else "Release"
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
        if not self._recording:
            return
        ix, iy = int(x), int(y)
        self._last_xy = (ix, iy)
        if self._ignored(ix, iy):
            return
        self._push_raw("scroll", x=ix, y=iy, dx=int(dx), dy=int(dy))
        if self._swipe and abs(dx) > abs(dy):
            self._swipe.hint_from_delta(dx, dy)
        self._flush_path()
        rx, ry = self._rel(ix, iy)
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
        canon = canonical_key(name)
        if canon:
            self._mods.add(canon)
        if is_exit_combo(name, self._mods):
            self._skip_exit_release = True
            if self.on_hotkey:
                self.on_hotkey("stop")
            return
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
        if not self._recording or self._ignored(*self._last_xy):
            return
        if name in self._pressed_keys:
            return
        self._pressed_keys.add(name)
        lx, ly = self._last_xy
        self._push_raw("key_down", x=lx, y=ly, key=name)
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
        canon = canonical_key(name)
        skip = is_skip_hotkey(name, self._mods) or (
            self._skip_exit_release and canon in EXIT_MODIFIERS | {EXIT_TRIGGER}
        )
        self._mods.discard(canon)
        if self._skip_exit_release and not (self._mods & EXIT_MODIFIERS):
            self._skip_exit_release = False
        if skip:
            return
        if not self._recording or self._ignored(*self._last_xy):
            return
        self._pressed_keys.discard(name)
        lx, ly = self._last_xy
        self._push_raw("key_up", x=lx, y=ly, key=name)
        self._flush_path()
        self._emit(
            Event(
                type=EventType.KEY_UP.value,
                name=f"Release {name}",
                delay_ms=self._gap(),
                key=name,
            )
        )
