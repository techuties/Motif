"""Window-relative coordinates (Pack B).

Store motif points relative to a target window; map back into the live window
on replay. macOS prefers Quartz window bounds; Linux/Windows degrade with a
clear status string.
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from typing import Any

from motif.models import Event, Script, script_from_dict, script_to_dict


@dataclass(frozen=True)
class WindowFrame:
    title: str
    x: int
    y: int
    width: int
    height: int
    bundle_id: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "x": int(self.x),
            "y": int(self.y),
            "width": int(self.width),
            "height": int(self.height),
            "bundle_id": self.bundle_id or "",
        }


def abs_to_rel(abs_x: int, abs_y: int, frame: WindowFrame) -> tuple[int, int]:
    """Absolute screen point → window-relative."""
    return int(abs_x) - int(frame.x), int(abs_y) - int(frame.y)


def rel_to_abs(rel_x: int, rel_y: int, frame: WindowFrame) -> tuple[int, int]:
    """Window-relative → absolute screen point."""
    return int(frame.x) + int(rel_x), int(frame.y) + int(rel_y)


def scale_rel(
    rel_x: int,
    rel_y: int,
    recorded: WindowFrame,
    live: WindowFrame,
) -> tuple[int, int]:
    """Scale relative coords when the live window was resized."""
    sx = (live.width / recorded.width) if recorded.width else 1.0
    sy = (live.height / recorded.height) if recorded.height else 1.0
    return int(round(rel_x * sx)), int(round(rel_y * sy))


def frame_from_dict(data: dict[str, Any] | None) -> WindowFrame | None:
    if not isinstance(data, dict) or not data:
        return None
    try:
        w = int(data.get("width") or 0)
        h = int(data.get("height") or 0)
    except (TypeError, ValueError):
        return None
    if w <= 0 or h <= 0:
        return None
    return WindowFrame(
        title=str(data.get("title") or ""),
        x=int(data.get("x") or 0),
        y=int(data.get("y") or 0),
        width=w,
        height=h,
        bundle_id=str(data.get("bundle_id") or ""),
    )


def window_status(script: Script, live: WindowFrame | None) -> str | None:
    """Human warning when the target window is missing or resized."""
    if not script.window_relative:
        return None
    recorded = frame_from_dict(script.window_bounds)
    if live is None:
        title = script.window_title or script.window_title_pattern or "target"
        return f"Window-relative: target window missing ({title}). Replaying in absolute coords."
    if recorded and (abs(live.width - recorded.width) > 8 or abs(live.height - recorded.height) > 8):
        return (
            f"Window-relative: window resized "
            f"({recorded.width}×{recorded.height} → {live.width}×{live.height})."
        )
    return None


def frontmost_window_frame() -> WindowFrame | None:
    """Best-effort frontmost window bounds. macOS preferred."""
    if sys.platform == "darwin":
        return _frontmost_macos()
    return _frontmost_fallback()


def find_window_by_title(pattern: str) -> WindowFrame | None:
    """Find an on-screen window whose title matches pattern (regex or substring)."""
    pat = (pattern or "").strip()
    if not pat:
        return frontmost_window_frame()
    if sys.platform == "darwin":
        return _find_macos(pat)
    return None


def resolve_live_window(script: Script) -> tuple[WindowFrame | None, str | None]:
    """Resolve live window for a window-relative script."""
    if not script.window_relative:
        return None, None
    pattern = (script.window_title_pattern or script.window_title or "").strip()
    live = find_window_by_title(pattern) if pattern else frontmost_window_frame()
    return live, window_status(script, live)


def apply_window_relative(script: Script, live: WindowFrame) -> Script:
    """Return a shallow-mapped script with origin shifted into the live window.

    Event coords stay relative to origin. We move origin to live window top-left
    (plus recorded origin offset inside the recorded window when present).
    """
    recorded = frame_from_dict(script.window_bounds)
    data = script_to_dict(script)
    clone = script_from_dict(data)
    if recorded is not None:
        # origin was absolute during capture; express origin offset inside window
        ox = script.origin_x - recorded.x
        oy = script.origin_y - recorded.y
        if recorded.width and live.width and (
            abs(live.width - recorded.width) > 8 or abs(live.height - recorded.height) > 8
        ):
            ox, oy = scale_rel(ox, oy, recorded, live)
        clone.origin_x = live.x + ox
        clone.origin_y = live.y + oy
    else:
        clone.origin_x = live.x
        clone.origin_y = live.y
    clone.origin_set = True
    return clone


def capture_window_metadata(script: Script, *, title_pattern: str = "") -> str | None:
    """Persist frontmost (or matched) window onto script. Returns status or None."""
    frame = find_window_by_title(title_pattern) if title_pattern else frontmost_window_frame()
    if frame is None:
        return "Window capture unavailable on this platform (macOS preferred)."
    script.window_relative = True
    script.window_title = frame.title
    script.window_title_pattern = title_pattern or frame.title
    script.window_bounds = frame.as_dict()
    return None


def _frontmost_macos() -> WindowFrame | None:
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:
        return None
    try:
        windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    except Exception:
        return None
    for window in windows:
        try:
            layer = int(window.get("kCGWindowLayer") or 0)
        except (TypeError, ValueError):
            layer = 0
        if layer != 0:
            continue
        bounds = window.get("kCGWindowBounds") or {}
        try:
            w = int(bounds.get("Width") or 0)
            h = int(bounds.get("Height") or 0)
            x = int(bounds.get("X") or 0)
            y = int(bounds.get("Y") or 0)
        except (TypeError, ValueError):
            continue
        if w < 50 or h < 50:
            continue
        title = str(window.get("kCGWindowName") or "")
        owner = str(window.get("kCGWindowOwnerName") or "")
        label = title or owner
        if not label or owner in {"Motif", "Window Server"}:
            continue
        return WindowFrame(title=label, x=x, y=y, width=w, height=h)
    return None


def _find_macos(pattern: str) -> WindowFrame | None:
    try:
        rx = re.compile(pattern, re.I)
    except re.error:
        rx = None
    try:
        from Quartz import (
            CGWindowListCopyWindowInfo,
            kCGNullWindowID,
            kCGWindowListOptionOnScreenOnly,
        )
    except Exception:
        return None
    try:
        windows = CGWindowListCopyWindowInfo(kCGWindowListOptionOnScreenOnly, kCGNullWindowID) or []
    except Exception:
        return None
    needle = pattern.lower()
    for window in windows:
        title = str(window.get("kCGWindowName") or "")
        owner = str(window.get("kCGWindowOwnerName") or "")
        label = title or owner
        if not label:
            continue
        ok = bool(rx.search(label)) if rx is not None else (needle in label.lower())
        if not ok:
            continue
        bounds = window.get("kCGWindowBounds") or {}
        try:
            w = int(bounds.get("Width") or 0)
            h = int(bounds.get("Height") or 0)
            x = int(bounds.get("X") or 0)
            y = int(bounds.get("Y") or 0)
        except (TypeError, ValueError):
            continue
        if w < 20 or h < 20:
            continue
        return WindowFrame(title=label, x=x, y=y, width=w, height=h)
    return None


def _frontmost_fallback() -> WindowFrame | None:
    """Linux/Windows: no reliable dependency-free API — report unavailable."""
    return None


def platform_window_support() -> str:
    if sys.platform == "darwin":
        return "ok"
    if sys.platform.startswith("linux"):
        return "degraded: window-relative capture needs macOS (Quartz); Linux replay is absolute-only unless bounds are embedded."
    if sys.platform == "win32":
        return "degraded: window-relative capture is macOS-first; Windows support is planned."
    return "unavailable"
