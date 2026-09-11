"""Pixel sampling with logical-to-physical conversion (Retina / DPI / multi-display).

Mouse record/replay uses global logical points (pynput / Qt), including negative
coords on a screen left of the primary. mss captures physical pixels; mixed-DPI
layouts need a per-display scale, not one factor from Motif’s current window.
"""

from __future__ import annotations

import sys
import time
from collections.abc import Sequence
from dataclasses import dataclass

import mss
from PIL import Image

_scale_cache: float | None = None


@dataclass(frozen=True)
class RGB:
    r: int
    g: int
    b: int

    def hex(self) -> str:
        return f"#{self.r:02X}{self.g:02X}{self.b:02X}"

    def luminance(self) -> float:
        return 0.2126 * self.r + 0.7152 * self.g + 0.0722 * self.b


@dataclass(frozen=True)
class Display:
    """One monitor in the global logical desktop (same space as pynput / Qt)."""

    index: int
    x: int
    y: int
    width: int
    height: int
    scale: float = 1.0
    name: str = ""
    phys_x: int = 0
    phys_y: int = 0

    def contains(self, px: int, py: int) -> bool:
        return self.x <= px < self.x + self.width and self.y <= py < self.y + self.height

    def label(self) -> str:
        return f"Display {self.index} · {self.width}×{self.height}"


_displays: list[Display] = []


def parse_hex(color: str) -> RGB:
    raw = (color or "#000000").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) < 6:
        raw = raw.ljust(6, "0")
    raw = raw[:6]
    try:
        return RGB(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))
    except ValueError:
        return RGB(0, 0, 0)


def color_distance(a: RGB, b: RGB) -> float:
    return ((a.r - b.r) ** 2 + (a.g - b.g) ** 2 + (a.b - b.b) ** 2) ** 0.5


def matches(actual: RGB, expected: RGB, tolerance: int, mode: str) -> bool:
    if mode == "is_not":
        return color_distance(actual, expected) > tolerance
    if mode == "brighter":
        return actual.luminance() > expected.luminance() + tolerance * 0.4
    if mode == "darker":
        return actual.luminance() < expected.luminance() - tolerance * 0.4
    return color_distance(actual, expected) <= tolerance


def display_scale() -> float:
    """Fallback logical-to-physical factor for the window’s current screen."""
    global _scale_cache
    if _scale_cache is None:
        _scale_cache = 2.0 if sys.platform == "darwin" else 1.0
    return _scale_cache


def set_scale(ratio: float) -> None:
    global _scale_cache
    if ratio > 0:
        _scale_cache = float(ratio)


def set_displays(displays: Sequence[Display] | None) -> None:
    """Cache the virtual-desktop layout for pixel grabs and Screen History."""
    global _displays
    _displays = list(displays or [])


def current_displays() -> list[Display]:
    return list(_displays)


def virtual_rect(displays: Sequence[Display] | None = None) -> tuple[int, int, int, int]:
    """Union of all screens as (x, y, width, height) in logical points."""
    items = list(displays) if displays is not None else _displays
    if not items:
        return (0, 0, 1920, 1080)
    x1 = min(d.x for d in items)
    y1 = min(d.y for d in items)
    x2 = max(d.x + d.width for d in items)
    y2 = max(d.y + d.height for d in items)
    return (x1, y1, max(1, x2 - x1), max(1, y2 - y1))


def display_at(x: int, y: int, displays: Sequence[Display] | None = None) -> Display | None:
    items = list(displays) if displays is not None else _displays
    for item in items:
        if item.contains(x, y):
            return item
    return None


def nearest_display(x: int, y: int, displays: Sequence[Display] | None = None) -> Display | None:
    items = list(displays) if displays is not None else _displays
    if not items:
        return None

    def dist(item: Display) -> int:
        cx = min(max(x, item.x), item.x + max(item.width, 1) - 1)
        cy = min(max(y, item.y), item.y + max(item.height, 1) - 1)
        return (x - cx) ** 2 + (y - cy) ** 2

    return min(items, key=dist)


def with_physical_origins(displays: Sequence[Display]) -> list[Display]:
    """Fill phys_x/phys_y from logical adjacency and each screen’s scale."""
    items = list(displays)
    if not items:
        return []
    phys: list[tuple[int, int] | None] = [None] * len(items)
    start = next((i for i, item in enumerate(items) if item.contains(0, 0)), 0)
    origin = items[start]
    phys[start] = (int(round(origin.x * origin.scale)), int(round(origin.y * origin.scale)))
    changed = True
    while changed:
        changed = False
        for i, item in enumerate(items):
            if phys[i] is not None:
                continue
            for j, other in enumerate(items):
                if phys[j] is None:
                    continue
                ox, oy = phys[j]
                placed: tuple[int, int] | None = None
                if abs(item.x - (other.x + other.width)) <= 1:
                    placed = (
                        ox + int(round(other.width * other.scale)),
                        oy + int(round((item.y - other.y) * item.scale)),
                    )
                elif abs((item.x + item.width) - other.x) <= 1:
                    placed = (
                        ox - int(round(item.width * item.scale)),
                        oy + int(round((item.y - other.y) * item.scale)),
                    )
                elif abs(item.y - (other.y + other.height)) <= 1:
                    placed = (
                        ox + int(round((item.x - other.x) * item.scale)),
                        oy + int(round(other.height * other.scale)),
                    )
                elif abs((item.y + item.height) - other.y) <= 1:
                    placed = (
                        ox + int(round((item.x - other.x) * item.scale)),
                        oy - int(round(item.height * item.scale)),
                    )
                if placed is not None:
                    phys[i] = placed
                    changed = True
                    break
    out: list[Display] = []
    for i, item in enumerate(items):
        px, py = phys[i] if phys[i] is not None else (
            int(round(item.x * item.scale)),
            int(round(item.y * item.scale)),
        )
        out.append(
            Display(
                index=item.index,
                x=item.x,
                y=item.y,
                width=item.width,
                height=item.height,
                scale=item.scale,
                name=item.name,
                phys_x=px,
                phys_y=py,
            )
        )
    return out


def _match_mss_monitor(display: Display, monitors: Sequence[dict]) -> dict | None:
    if len(monitors) < 2:
        return None
    target_w = int(round(display.width * display.scale))
    target_h = int(round(display.height * display.scale))
    best: dict | None = None
    best_score: int | None = None
    for mon in monitors[1:]:
        try:
            mw = int(mon["width"])
            mh = int(mon["height"])
            left = int(mon.get("left", 0))
            top = int(mon.get("top", 0))
        except (KeyError, TypeError, ValueError):
            continue
        score = (abs(mw - target_w) + abs(mh - target_h)) * 1000 + abs(left - display.phys_x) + abs(
            top - display.phys_y
        )
        if best_score is None or score < best_score:
            best_score = score
            best = mon
    return best


def logical_to_physical(
    logical_x: int,
    logical_y: int,
    scale: float | None = None,
    monitors: Sequence[dict] | None = None,
    displays: Sequence[Display] | None = None,
) -> tuple[int, int]:
    """Convert a pynput/Qt logical point to mss physical pixels."""
    items = list(displays) if displays is not None else _displays
    display = display_at(logical_x, logical_y, items) or nearest_display(logical_x, logical_y, items)
    if display is not None and monitors:
        mon = _match_mss_monitor(display, monitors)
        if mon is not None and display.width > 0 and display.height > 0:
            rx = (logical_x - display.x) / display.width
            ry = (logical_y - display.y) / display.height
            rx = min(max(rx, 0.0), 1.0 - 1e-9)
            ry = min(max(ry, 0.0), 1.0 - 1e-9)
            return (
                int(mon["left"] + rx * mon["width"]),
                int(mon["top"] + ry * mon["height"]),
            )
    if display is not None:
        return (
            int(round(display.phys_x + (logical_x - display.x) * display.scale)),
            int(round(display.phys_y + (logical_y - display.y) * display.scale)),
        )
    factor = scale if scale is not None else display_scale()
    return int(round(logical_x * factor)), int(round(logical_y * factor))


def grab_pixel(logical_x: int, logical_y: int, scale: float | None = None) -> RGB:
    with mss.mss() as sct:
        sx, sy = logical_to_physical(logical_x, logical_y, scale, monitors=sct.monitors)
        grab = sct.grab({"left": sx, "top": sy, "width": 1, "height": 1})
        img = Image.frombytes("RGB", grab.size, grab.rgb)
        r, g, b = img.getpixel((0, 0))
    return RGB(int(r), int(g), int(b))


def wait_for_pixel(
    logical_x: int,
    logical_y: int,
    color: str,
    tolerance: int,
    timeout_ms: int,
    mode: str,
    poll_ms: int,
    should_stop,
    scale: float | None = None,
) -> bool:
    expected = parse_hex(color)
    deadline = time.monotonic() + max(timeout_ms, 1) / 1000.0
    interval = max(poll_ms, 10) / 1000.0
    while time.monotonic() < deadline:
        if should_stop():
            return False
        actual = grab_pixel(logical_x, logical_y, scale)
        if matches(actual, expected, tolerance, mode):
            return True
        time.sleep(interval)
    return False


def wait_for_pixel_change(
    logical_x: int,
    logical_y: int,
    baseline: str,
    tolerance: int,
    timeout_ms: int,
    poll_ms: int,
    should_stop,
    scale: float | None = None,
) -> bool:
    return wait_for_pixel(
        logical_x,
        logical_y,
        baseline,
        tolerance,
        timeout_ms,
        "is_not",
        poll_ms,
        should_stop,
        scale,
    )


def grab_region(logical_x: int, logical_y: int, width: int, height: int, scale: float | None = None) -> Image.Image:
    """Grab a logical rectangle as an RGB PIL image."""
    width = max(1, int(width))
    height = max(1, int(height))
    with mss.mss() as sct:
        x0, y0 = logical_to_physical(logical_x, logical_y, scale, monitors=sct.monitors)
        x1, y1 = logical_to_physical(
            logical_x + width - 1, logical_y + height - 1, scale, monitors=sct.monitors
        )
        left = min(x0, x1)
        top = min(y0, y1)
        w = max(1, abs(x1 - x0) + 1)
        h = max(1, abs(y1 - y0) + 1)
        grab = sct.grab({"left": left, "top": top, "width": w, "height": h})
        return Image.frombytes("RGB", grab.size, grab.rgb)


def _pixels(img: Image.Image) -> list[int]:
    if hasattr(img, "get_flattened_data"):
        return list(img.get_flattened_data())
    return list(img.getdata())


def template_score(haystack: Image.Image, needle: Image.Image) -> float:
    """Return best score in 0..1 via mean absolute difference (1 = identical)."""
    hay = haystack.convert("L")
    need = needle.convert("L")
    if need.width > hay.width or need.height > hay.height:
        return 0.0
    best = 0.0
    hw, hh = hay.size
    nw, nh = need.size
    need_px = _pixels(need)
    step_y = max(1, nh // 6)
    step_x = max(1, nw // 6)
    denom = float(len(need_px) * 255.0) or 1.0
    for y in range(0, hh - nh + 1, step_y):
        for x in range(0, hw - nw + 1, step_x):
            crop = _pixels(hay.crop((x, y, x + nw, y + nh)))
            diff = sum(abs(a - b) for a, b in zip(crop, need_px)) / denom
            best = max(best, 1.0 - diff)
    return best


def match_template_file(
    template_path: str,
    *,
    logical_x: int = 0,
    logical_y: int = 0,
    width: int = 0,
    height: int = 0,
    haystack: Image.Image | None = None,
) -> float:
    """Score template against a screen region or provided haystack image."""
    from pathlib import Path

    path = Path(template_path)
    if not path.is_file():
        return 0.0
    needle = Image.open(path).convert("RGB")
    if haystack is None:
        if width <= 0 or height <= 0:
            # full virtual desktop grab is expensive; require region or haystack in tests
            displays = current_displays()
            vx, vy, vw, vh = virtual_rect(displays)
            logical_x, logical_y, width, height = vx, vy, vw, vh
        haystack = grab_region(logical_x, logical_y, width, height)
    return template_score(haystack, needle)


def wait_for_image(
    template_path: str,
    tolerance_or_threshold: float,
    timeout_ms: int,
    poll_ms: int,
    should_stop,
    *,
    logical_x: int = 0,
    logical_y: int = 0,
    width: int = 0,
    height: int = 0,
    haystack_factory=None,
) -> bool:
    """Poll until template score >= threshold (0..1) or tolerance/100 if >1."""
    threshold = float(tolerance_or_threshold)
    if threshold > 1.0:
        threshold = threshold / 100.0
    threshold = max(0.05, min(1.0, threshold))
    deadline = time.monotonic() + max(timeout_ms, 1) / 1000.0
    interval = max(poll_ms, 10) / 1000.0
    while time.monotonic() < deadline:
        if should_stop():
            return False
        hay = haystack_factory() if haystack_factory else None
        score = match_template_file(
            template_path,
            logical_x=logical_x,
            logical_y=logical_y,
            width=width,
            height=height,
            haystack=hay,
        )
        if score >= threshold:
            return True
        time.sleep(interval)
    return False
