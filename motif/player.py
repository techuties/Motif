"""Replay a script at recorded timing, with optional humanize, loops, and pixel waits."""

from __future__ import annotations

import random
import time
from collections.abc import Callable
from threading import Event as Flag

from pynput.keyboard import Controller as KeyController
from pynput.mouse import Button, Controller as MouseController

from motif.humanize import (
    distance,
    event_wait_ms,
    generate_path,
    gauss_offset,
    prefer_recorded_path,
    precise_travel_ms,
    replay_recorded_points,
    scale_ms,
    step_delays_ms,
    travel_ms,
    vary_ms,
)
from motif.keys import name_to_key
from motif.macos import activate_app, post_space_switch
from motif.models import (
    BRANCH_STOP,
    FINAL_SWIPE_SETTLE_MS,
    MAX_GOTO_JUMPS,
    SPACE_SETTLE_MS,
    Event,
    EventType,
    PathStyle,
    PlayMode,
    Script,
    anchor_offset,
    direction_from_delta,
    is_snap_path,
    label_index_map,
    parse_branch_action,
    parse_ctrl_arrow,
    screen_pos,
    should_auto_align,
)
from motif.screen import grab_pixel, wait_for_image, wait_for_pixel, wait_for_pixel_change
from motif.window_rel import apply_window_relative, resolve_live_window, window_status

BUTTONS = {
    "left": Button.left,
    "right": Button.right,
    "middle": Button.middle,
}


def click_release_follows(event: Event, following: list[Event]) -> bool:
    """True when a matching button-up is recorded after this press (skip notes/waits)."""
    if event.type_enum() != EventType.CLICK or not event.pressed:
        return False
    for nxt in following:
        kind = nxt.type_enum()
        if kind in (EventType.COMMENT, EventType.WAIT):
            continue
        return kind == EventType.CLICK and not nxt.pressed and nxt.button == event.button
    return False


class Player:
    def __init__(self, on_progress: Callable[[int, int, str], None] | None = None) -> None:
        self.mouse = MouseController()
        self.keyboard = KeyController()
        self.on_progress = on_progress
        self.stop_flag = Flag()
        self.busy = False
        self.cycle = 0
        self.index = -1
        self._held_buttons: set = set()
        self._held_keys: set = set()
        self._branch_goto = ""

    def request_stop(self) -> None:
        self.stop_flag.set()
        self._release_held()

    def _release_held(self) -> None:
        for button in list(self._held_buttons):
            try:
                self.mouse.release(button)
            except Exception:
                pass
        self._held_buttons.clear()
        for key in list(self._held_keys):
            try:
                self.keyboard.release(key)
            except Exception:
                pass
        self._held_keys.clear()

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
        # Snap is the only teleport. Default Precise/Natural walk the take.
        if is_snap_path(settings, event):
            hop = precise_travel_ms(event)
            if hop and not self._sleep(scale_ms(hop, settings)):
                return False
            self.mouse.position = (sx, sy)
            return True
        if prefer_recorded_path(settings, event):
            jitter = settings.jitter_px if settings.enabled else 0.0
            for px, py, wait in replay_recorded_points(event.points, jitter, rng):
                ax, ay = self._abs(script, px, py, cursor0)
                self.mouse.position = (ax, ay)
                if not self._sleep(scale_ms(wait, settings)):
                    return False
            self.mouse.position = (sx, sy)
            return True

        if distance(cx, cy, sx, sy) < 1.5:
            self.mouse.position = (sx, sy)
            return True

        # Two-point / empty path: interpolate so Replay is never a silent hop.
        style = event.path or settings.path
        if style in {PathStyle.RECORDED.value, PathStyle.SNAP.value}:
            style = PathStyle.LINEAR.value
        path = generate_path(cx, cy, sx, sy, settings, style, rng)
        total = travel_ms(cx, cy, sx, sy, settings, event.travel_ms, rng)
        delays = step_delays_ms(total, len(path), rng)
        for (px, py), wait in zip(path, delays):
            self.mouse.position = (px, py)
            if not self._sleep(wait):
                return False
        self.mouse.position = (sx, sy)
        return True

    def _park(self, script: Script, rng: random.Random, cursor0: tuple[int, int], name: str) -> bool:
        park = Event(type=EventType.GO_ORIGIN.value, name=name)
        return self._move_to(script, 0, 0, park, rng, cursor0)

    def _play_event(
        self,
        script: Script,
        event: Event,
        rng: random.Random,
        cursor0: tuple[int, int],
        following: list[Event] | None = None,
    ) -> bool:
        settings = script.humanize
        kind = event.type_enum()
        wait = event_wait_ms(event.delay_ms, settings, rng)
        if wait and not self._sleep(wait):
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
            if settings.enabled:
                dwell = vary_ms(settings.dwell_before_click_ms, settings.dwell_jitter_ms, settings, rng)
                if dwell and not self._sleep(dwell):
                    return False
            button = BUTTONS.get(event.button, Button.left)
            hold: int | None
            if event.duration_ms is not None:
                hold = event_wait_ms(event.duration_ms, settings, rng)
            elif settings.enabled:
                hold = vary_ms(settings.click_hold_ms, settings.click_hold_jitter_ms, settings, rng)
            else:
                hold = None
            if event.pressed:
                self.mouse.press(button)
                self._held_buttons.add(button)
                if hold is not None:
                    if not self._sleep(hold):
                        self.mouse.release(button)
                        self._held_buttons.discard(button)
                        return False
                if event.duration_ms is not None or not click_release_follows(event, following or []):
                    self.mouse.release(button)
                    self._held_buttons.discard(button)
            else:
                self.mouse.release(button)
                self._held_buttons.discard(button)
            return True

        if kind == EventType.SCROLL:
            if not self._move_to(script, event.x, event.y, event, rng, cursor0):
                return False
            self.mouse.scroll(event.dx, event.dy)
            return True

        if kind == EventType.SWIPE:
            inferred = "inferred" in (event.notes or "").lower()
            activated = False
            if event.bundle_id or event.app:
                activated = activate_app(event.bundle_id, event.app)
            if not activated:
                way = event.direction or direction_from_delta(event.dx, event.dy) or ""
                if way or parse_ctrl_arrow(event.key):
                    post_space_switch(way or "right", self.keyboard, key=event.key, inferred=inferred)
            # Space animation is ~0.4–0.6s. Wait it out even when delay_ms was 0.
            # Non-swipe events keep their recorded timing only. Delay 0 never drops
            # a swipe — consecutive end swipes each post and settle.
            settle = SPACE_SETTLE_MS
            if following is not None and not any(nxt.type_enum() == EventType.SWIPE for nxt in following):
                settle += FINAL_SWIPE_SETTLE_MS
            if not self._sleep(settle):
                return False
            return True

        if kind in (EventType.KEY_DOWN, EventType.KEY_UP):
            key = name_to_key(event.key)
            if key is None:
                return True
            if kind == EventType.KEY_DOWN:
                self.keyboard.press(key)
                self._held_keys.add(key)
                if event.duration_ms:
                    if not self._sleep(event_wait_ms(event.duration_ms, settings, rng)):
                        self.keyboard.release(key)
                        self._held_keys.discard(key)
                        return False
                    self.keyboard.release(key)
                    self._held_keys.discard(key)
            else:
                self.keyboard.release(key)
                self._held_keys.discard(key)
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
            if self.stop_flag.is_set():
                return False
            return self._after_wait_branch(script, event, ok, ax, ay, 1, 1, rng, cursor0)

        if kind == EventType.WAIT_IMAGE:
            ax, ay = self._abs(script, event.x, event.y, cursor0)
            # width/height encoded in dx/dy when set; else full search region fallback
            w = int(event.dx) if event.dx else 0
            h = int(event.dy) if event.dy else 0
            threshold = float(event.threshold) if event.threshold else max(0.5, (event.tolerance or 82) / 100.0)
            hit = wait_for_image(
                event.template,
                threshold,
                event.timeout_ms,
                event.poll_ms,
                self.stop_flag.is_set,
                logical_x=ax,
                logical_y=ay,
                width=w,
                height=h,
                locate=True,
            )
            if self.stop_flag.is_set():
                return False
            found = hit is not None and getattr(hit, "score", 0) > 0
            mx = int(getattr(hit, "x", ax)) if found else ax
            my = int(getattr(hit, "y", ay)) if found else ay
            mw = int(getattr(hit, "width", 1) or 1) if found else 1
            mh = int(getattr(hit, "height", 1) or 1) if found else 1
            return self._after_wait_branch(script, event, found, mx, my, mw, mh, rng, cursor0)

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

    def _after_wait_branch(
        self,
        script: Script,
        event: Event,
        found: bool,
        match_x: int,
        match_y: int,
        match_w: int,
        match_h: int,
        rng: random.Random,
        cursor0: tuple[int, int],
    ) -> bool:
        """Click-on-find + on_found/on_miss. Sets self._branch_goto on goto."""
        action = event.on_found if found else event.on_miss
        kind, label = parse_branch_action(action)
        if found and event.click_on_find:
            ox, oy = anchor_offset(match_w, match_h, event.click_anchor)
            # match coords are absolute screen; convert to origin-relative for _move_to
            rel_x = int(match_x + ox) - script.origin_x
            rel_y = int(match_y + oy) - script.origin_y
            if script.play_mode == PlayMode.FROM_CURSOR.value:
                rel_x = int(match_x + ox) - cursor0[0]
                rel_y = int(match_y + oy) - cursor0[1]
            click = Event(
                type=EventType.CLICK.value,
                x=rel_x,
                y=rel_y,
                pressed=True,
                button="left",
                duration_ms=50,
            )
            if not self._play_event(script, click, rng, cursor0, []):
                return False
        if kind == BRANCH_STOP:
            return False
        if kind == "goto" and label:
            self._branch_goto = label
            return True
        return True

    def play(self, script: Script) -> str:
        self.stop_flag.clear()
        self.busy = True
        self.cycle = 0
        self.index = -1
        self._branch_goto = ""
        rng = random.Random()
        loops = script.loop.count
        forever = loops <= 0
        # Pack B: map origin/coords into live window when requested
        play_script = script
        if script.window_relative:
            live, status = resolve_live_window(script)
            if status:
                # Soft warning only — still try absolute if window missing
                pass
            if live is not None:
                play_script = apply_window_relative(script, live)
        try:
            while forever or self.cycle < loops:
                if self.stop_flag.is_set():
                    return "stopped"
                self.cycle += 1
                cursor0 = self._cursor()
                if play_script.play_mode == PlayMode.FROM_ORIGIN.value:
                    cursor0 = (play_script.origin_x, play_script.origin_y)
                if should_auto_align(play_script, returning=False):
                    if not self._park(play_script, rng, cursor0, "Park"):
                        return "stopped"
                    if play_script.play_mode == PlayMode.FROM_CURSOR.value:
                        cursor0 = self._cursor()
                events = play_script.enabled_events()
                labels = label_index_map(events)
                i = 0
                goto_jumps = 0
                while i < len(events):
                    if self.stop_flag.is_set():
                        return "stopped"
                    event = events[i]
                    self.index = i
                    self._branch_goto = ""
                    if self.on_progress:
                        self.on_progress(self.cycle, i, event.display_name())
                    ok = self._play_event(play_script, event, rng, cursor0, events[i + 1 :])
                    if not ok:
                        return "stopped" if self.stop_flag.is_set() else "failed"
                    if self._branch_goto:
                        target = labels.get(self._branch_goto.strip())
                        self._branch_goto = ""
                        if target is None:
                            return "failed"
                        goto_jumps += 1
                        if goto_jumps > MAX_GOTO_JUMPS:
                            return "failed"
                        i = target
                        continue
                    i += 1
                if should_auto_align(play_script, returning=True):
                    if not self._park(play_script, rng, cursor0, "Return"):
                        return "stopped"
                if not forever and self.cycle >= loops:
                    break
                if not self._sleep(scale_ms(play_script.loop.gap_ms, play_script.humanize)):
                    return "stopped"
            return "done"
        finally:
            self._release_held()
            self.busy = False
            self.index = -1
