"""Pixel sampling with logical-to-physical conversion (Retina / DPI)."""

from __future__ import annotations

import sys
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


def parse_hex(color: str) -> RGB:
    raw = (color or "#000000").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(ch * 2 for ch in raw)
    if len(raw) < 6:
        raw = raw.ljust(6, "0")
    return RGB(int(raw[0:2], 16), int(raw[2:4], 16), int(raw[4:6], 16))


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


def display_scale(logical_width: int | None = None) -> float:
    global _scale_cache
    if _scale_cache is not None and logical_width is None:
        return _scale_cache
    with mss.mss() as sct:
        mon = sct.monitors[1] if len(sct.monitors) > 1 else sct.monitors[0]
        physical_w = float(mon["width"])
    if logical_width and logical_width > 0:
        _scale_cache = physical_w / float(logical_width)
    elif sys.platform == "darwin":
        _scale_cache = 2.0 if physical_w >= 2560 else 1.0
    else:
        _scale_cache = 1.0
    return _scale_cache


def set_scale(ratio: float) -> None:
    global _scale_cache
    if ratio > 0:
        _scale_cache = float(ratio)


def set_logical_size(width: int, height: int) -> None:
    """Prefer set_scale(QScreen.devicePixelRatio()). This path avoids capturing."""
    _ = width, height
    if _scale_cache is None:
        set_scale(2.0 if sys.platform == "darwin" else 1.0)


def grab_pixel(logical_x: int, logical_y: int, scale: float | None = None) -> RGB:
    factor = scale if scale is not None else display_scale()
    sx = int(round(logical_x * factor))
    sy = int(round(logical_y * factor))
    with mss.mss() as sct:
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
    import time

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
