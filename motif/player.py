"""Replay a script with humanized motion, loops, and pixel waits."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from threading import Event as Flag

from pynput.keyboard import Controller as KeyController
from pynput.mouse import Button, Controller as MouseController

from motif.humanize import generate_path, gauss_offset, replay_recorded_points, step_delays_ms, travel_ms, vary_ms
from motif.keys import name_to_key
from motif.models import Event, EventType, PathStyle, PlayMode, Script, screen_pos
from motif.screen import grab_pixel, wait_for_pixel, wait_for_pixel_change

BUTTONS = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}


class Player:
    def __init__(self, on_progress: Callable[[int, int, str], None] | None = None) -> None:
        self.mouse = MouseController()
        self.keyboard = KeyController()
        self.on_progress = on_progress
        self.stop_flag = Flag()
        self.busy = False
        self.cycle = 0
        self.index = -1

    def request_stop(self) -> None:
        self.stop_flag.set()

    def _sleep(self, ms: int) -> bool:
        if ms <= 0:
            return not self.stop_flag.is_set()
        deadline = time.monotonic() + ms / 1000.0
        while time.monotonic() < deadline:
            if self.stop_flag.is_set():
                return False
            time.sleep(min(0.02, max(0.0, deadline - time.monotonic())))
        return True

    def _cursor(self) -> tuple[int, int]:
        pos = self.mouse.position
        return int(pos[0]), int(pos[1])

    def _abs(self, script: Script, x: int, y: int, cursor0: tuple[int, int]) -> tuple[int, int]:
        return screen_pos(script, x, y, cursor0)

    def _move_to(
        self,
        script: Script,
        x: int,
        y: int,
        event: Event,
        rng: random.Random,
        cursor0: tuple[int, int],
    ) -> bool:
        sx, sy = self._abs(script, x, y, cursor0)
        cx, cy = self._cursor()
        settings = script.humanize
        style = event.path or (settings.path if settings.enabled else PathStyle.LINEAR.value)
        if style == PathStyle.RECORDED.value and event.points:
            jitter = settings.jitter_px if settings.enabled else 0.0
            for px, py, wait in replay_recorded_points(event.points, jitter, rng):
                ax, ay = self._abs(script, px, py, cursor0)
                self.mouse.position = (ax, ay)
                if not self._sleep(max(1, int(wait / max(settings.speed, 0.05)))):
                    return False
            self.mouse.position = (sx, sy)
            return True

        path = generate_path(cx, cy, sx, sy, settings, style, rng)
        total = travel_ms(cx, cy, sx, sy, settings, event.travel_ms, rng)
        delays = step_delays_ms(total, len(path), rng)
        for (px, py), wait in zip(path, delays):
            self.mouse.position = (px, py)
            if not self._sleep(wait):
                return False
        self.mouse.position = (sx, sy)
        return True

    def _play_event(self, script: Script, event: Event, rng: random.Random, cursor0: tuple[int, int]) -> bool:
        settings = script.humanize
        kind = event.type_enum()
        if event.delay_ms:
            extra = vary_ms(event.delay_ms, int(event.delay_ms * settings.timing_jitter), settings, rng)
            if not self._sleep(extra if settings.enabled else event.delay_ms):
                return False

        if kind == EventType.COMMENT:
            return True

        if kind == EventType.WAIT:
            return True

        if kind == EventType.GO_ORIGIN:
            return self._move_to(script, 0, 0, event, rng, cursor0)

        if kind == EventType.MOVE:
            return self._move_to(script, event.x, event.y, event, rng, cursor0)

        if kind == EventType.CLICK:
            ox, oy = gauss_offset(settings.click_offset_px, rng) if settings.enabled else (0, 0)
            if not self._move_to(script, event.x + ox, event.y + oy, event, rng, cursor0):
                return False
            dwell = vary_ms(settings.dwell_before_click_ms, settings.dwell_jitter_ms, settings, rng)
            if not self._sleep(dwell):
                return False
            button = BUTTONS.get(event.button, Button.left)
            hold = event.duration_ms
            if hold is None:
                hold = vary_ms(settings.click_hold_ms, settings.click_hold_jitter_ms, settings, rng)
            if event.pressed:
                self.mouse.press(button)
                if event.duration_ms is not None or settings.enabled:
                    if not self._sleep(hold):
                        self.mouse.release(button)
                        return False
                    # Pairing: if the next recorded event is the matching release, we still
                    # release here only when this click is stored as a full tap.
            else:
                self.mouse.release(button)
            return True

        if kind == EventType.SCROLL:
            if not self._move_to(script, event.x, event.y, event, rng, cursor0):
                return False
            self.mouse.scroll(event.dx, event.dy)
            return True

        if kind in (EventType.KEY_DOWN, EventType.KEY_UP):
            key = name_to_key(event.key)
            if key is None:
                return True
            if kind == EventType.KEY_DOWN:
                self.keyboard.press(key)
                if event.duration_ms:
                    if not self._sleep(event.duration_ms):
                        self.keyboard.release(key)
                        return False
                    self.keyboard.release(key)
            else:
                self.keyboard.release(key)
            return True

        if kind == EventType.WAIT_PIXEL:
            ax, ay = self._abs(script, event.x, event.y, cursor0)
            ok = wait_for_pixel(
                ax,
                ay,
                event.color,
                event.tolerance,
                event.timeout_ms,
                event.match,
                event.poll_ms,
                self.stop_flag.is_set,
            )
            return ok and not self.stop_flag.is_set()

        if kind == EventType.WAIT_PIXEL_CHANGE:
            ax, ay = self._abs(script, event.x, event.y, cursor0)
            baseline = event.color
            if not baseline or baseline == "#000000":
                baseline = grab_pixel(ax, ay).hex()
            ok = wait_for_pixel_change(
                ax,
                ay,
                baseline,
                event.tolerance,
                event.timeout_ms,
                event.poll_ms,
                self.stop_flag.is_set,
            )
            return ok and not self.stop_flag.is_set()

        return True

    def play(self, script: Script) -> str:
        self.stop_flag.clear()
        self.busy = True
        self.cycle = 0
        self.index = -1
        rng = random.Random()
        loops = script.loop.count
        forever = loops <= 0
        try:
            while forever or self.cycle < loops:
                if self.stop_flag.is_set():
                    return "stopped"
                self.cycle += 1
                cursor0 = self._cursor()
                if script.play_mode == PlayMode.FROM_ORIGIN.value:
                    cursor0 = (script.origin_x, script.origin_y)
                if script.loop.park_before_cycle and script.origin_set:
                    park = Event(type=EventType.GO_ORIGIN.value, name="Park")
                    if not self._move_to(script, 0, 0, park, rng, cursor0):
                        return "stopped"
                    if script.play_mode == PlayMode.FROM_CURSOR.value:
                        cursor0 = self._cursor()
                events = script.enabled_events()
                for i, event in enumerate(events):
                    if self.stop_flag.is_set():
                        return "stopped"
                    self.index = i
                    if self.on_progress:
                        self.on_progress(self.cycle, i, event.display_name())
                    if not self._play_event(script, event, rng, cursor0):
                        return "stopped" if self.stop_flag.is_set() else "failed"
                if script.loop.return_to_origin and script.origin_set:
                    park = Event(type=EventType.GO_ORIGIN.value, name="Return")
                    if not self._move_to(script, 0, 0, park, rng, cursor0):
                        return "stopped"
                if not forever and self.cycle >= loops:
                    break
                if not self._sleep(script.loop.gap_ms):
                    return "stopped"
            return "done"
        finally:
            self.busy = False
            self.index = -1
