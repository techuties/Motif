"""Human-like travel, paths, and timing. Tunable; never a guarantee against detectors."""

from __future__ import annotations

import math
import random
from typing import Iterable

from motif.models import (
    WALK_MIN_POINTS,
    Event,
    EventType,
    HumanizeSettings,
    PathStyle,
    is_snap_path,
)


def _clamp(value: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, value))


def distance(x0: float, y0: float, x1: float, y1: float) -> float:
    return math.hypot(x1 - x0, y1 - y0)


def fitts_time_ms(
    dist: float,
    width: float,
    a_ms: float,
    b_ms: float,
    lo: int,
    hi: int,
) -> int:
    ident = math.log2(1.0 + dist / max(width, 1.0))
    return int(_clamp(a_ms + b_ms * ident, lo, hi))


def jittered(base: float, spread: float, rng: random.Random | None = None) -> float:
    roll = (rng or random).uniform(-1.0, 1.0)
    return base + roll * spread


def gauss_offset(sigma: float, rng: random.Random | None = None) -> tuple[int, int]:
    if sigma <= 0:
        return 0, 0
    r = rng or random
    return int(round(r.gauss(0, sigma))), int(round(r.gauss(0, sigma)))


def _smoothstep(t: float) -> float:
    t = _clamp(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def _smootherstep(t: float) -> float:
    t = _clamp(t, 0.0, 1.0)
    return t * t * t * (t * (t * 6.0 - 15.0) + 10.0)


def _bezier(p0: complex, p1: complex, p2: complex, p3: complex, t: float) -> complex:
    u = 1.0 - t
    return (u**3) * p0 + 3 * (u**2) * t * p1 + 3 * u * (t**2) * p2 + (t**3) * p3


def _control_points(
    start: complex,
    end: complex,
    rng: random.Random,
    wander: float,
) -> tuple[complex, complex]:
    delta = end - start
    dist = abs(delta) or 1.0
    normal = complex(-delta.imag, delta.real) / dist
    along = delta / dist
    c1 = start + along * dist * rng.uniform(0.22, 0.42) + normal * rng.uniform(-wander, wander)
    c2 = start + along * dist * rng.uniform(0.58, 0.82) + normal * rng.uniform(-wander, wander)
    return c1, c2


def generate_path(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    settings: HumanizeSettings,
    style: str | None = None,
    rng: random.Random | None = None,
) -> list[tuple[int, int]]:
    rng = rng or random.Random()
    style = style or (settings.path if settings.enabled else PathStyle.LINEAR.value)
    dist = distance(x0, y0, x1, y1)
    if dist < 1.5:
        return [(x1, y1)]

    steps = max(6, min(96, int(dist / 7)))
    start = complex(x0, y0)
    end = complex(x1, y1)
    jitter = settings.jitter_px if settings.enabled else 0.0

    if style == PathStyle.RECORDED.value:
        style = PathStyle.LINEAR.value

    if style == PathStyle.LINEAR.value:
        points = []
        for i in range(1, steps + 1):
            t = i / steps
            p = start + (end - start) * t
            jx, jy = gauss_offset(jitter * 0.4, rng) if jitter else (0, 0)
            points.append((int(round(p.real + jx)), int(round(p.imag + jy))))
        points[-1] = (x1, y1)
        return points

    wander = max(8.0, dist * (0.22 if style == PathStyle.WANDER.value else 0.12))
    if style == PathStyle.WANDER.value:
        wander *= 1.7
    c1, c2 = _control_points(start, end, rng, wander)

    overshoot = settings.enabled and (
        style == PathStyle.OVERSHOOT.value or rng.random() < settings.overshoot_chance
    )
    target = end
    if overshoot and dist > 40:
        direction = (end - start) / (abs(end - start) or 1)
        target = end + direction * rng.uniform(settings.overshoot_px * 0.4, settings.overshoot_px)

    mid_steps = steps if target == end else max(5, steps - 8)
    points: list[tuple[int, int]] = []
    for i in range(1, mid_steps + 1):
        t = _smootherstep(i / mid_steps)
        p = _bezier(start, c1, c2, target, t)
        jx, jy = gauss_offset(jitter, rng) if jitter else (0, 0)
        points.append((int(round(p.real + jx)), int(round(p.imag + jy))))

    if target != end:
        fix_steps = max(4, int(abs(end - target) / 3))
        current = complex(*points[-1]) if points else target
        for i in range(1, fix_steps + 1):
            t = _smoothstep(i / fix_steps)
            p = current + (end - current) * t
            points.append((int(round(p.real)), int(round(p.imag))))

    points[-1] = (x1, y1)
    return points


def playback_speed(settings: HumanizeSettings) -> float:
    return max(float(settings.speed), 0.05)


def scale_ms(base: int | float, settings: HumanizeSettings) -> int:
    """Scale a recorded duration by playback speed. 1.0× is unchanged."""
    return max(0, int(round(float(base) / playback_speed(settings))))


def prefer_recorded_path(settings: HumanizeSettings, event: Event) -> bool:
    """True when Replay should walk the take's polyline (TinyTask / JitBit).

    A MOVE with three or more samples is the recorded path. Precise walks it
    too — teleport is only Path style snap. Two-point hops interpolate instead.
    """
    if is_snap_path(settings, event):
        return False
    return len(event.points) >= WALK_MIN_POINTS


def precise_travel_ms(event: Event) -> int:
    """Single wait before a Precise hop: stored travel_ms, else last point t_ms."""
    if event.travel_ms is not None:
        return max(0, int(event.travel_ms))
    if event.type_enum() == EventType.MOVE and event.points:
        return max(0, int(event.points[-1].get("t_ms") or 0))
    return 0


def event_wait_ms(
    delay_ms: int,
    settings: HumanizeSettings,
    rng: random.Random | None = None,
) -> int:
    """Pause before an event: recorded delay, optional humanize jitter, then speed."""
    if delay_ms <= 0:
        return 0
    if settings.enabled:
        return vary_ms(delay_ms, int(delay_ms * settings.timing_jitter), settings, rng)
    return scale_ms(delay_ms, settings)


def travel_ms(
    x0: int,
    y0: int,
    x1: int,
    y1: int,
    settings: HumanizeSettings,
    override_ms: int | None = None,
    rng: random.Random | None = None,
) -> int:
    if override_ms is not None:
        return scale_ms(max(0, override_ms), settings)
    dist = distance(x0, y0, x1, y1)
    if not settings.enabled:
        return scale_ms(max(8, int(dist * 2)), settings)
    base = fitts_time_ms(
        dist,
        settings.target_width_px,
        settings.travel_a_ms,
        settings.travel_b_ms,
        settings.min_travel_ms,
        settings.max_travel_ms,
    )
    noise = jittered(0, base * settings.timing_jitter, rng)
    scaled = (base + noise) / playback_speed(settings)
    return int(_clamp(scaled, 1, settings.max_travel_ms * 2))


def step_delays_ms(total_ms: int, count: int, rng: random.Random | None = None) -> list[int]:
    if count <= 0:
        return []
    if count == 1:
        return [max(1, total_ms)]
    rng = rng or random.Random()
    weights = []
    for i in range(count):
        t = i / (count - 1)
        # Bell-shaped velocity: more time at ends, less in the middle.
        ease = 1.35 - math.sin(t * math.pi) * 0.85
        weights.append(max(0.15, ease * rng.uniform(0.85, 1.15)))
    total_w = sum(weights)
    raw = [total_ms * w / total_w for w in weights]
    delays = [max(1, int(round(v))) for v in raw]
    drift = total_ms - sum(delays)
    delays[-1] = max(1, delays[-1] + drift)
    return delays


def vary_ms(base: int, spread: int, settings: HumanizeSettings, rng: random.Random | None = None) -> int:
    if not settings.enabled or spread <= 0:
        return scale_ms(base, settings)
    value = jittered(base, spread, rng) / playback_speed(settings)
    return max(0, int(round(value)))


def replay_recorded_points(
    points: Iterable[dict[str, int]],
    jitter_px: float,
    rng: random.Random | None = None,
) -> list[tuple[int, int, int]]:
    rng = rng or random.Random()
    out: list[tuple[int, int, int]] = []
    last_t = 0
    for point in points:
        jx, jy = gauss_offset(jitter_px, rng) if jitter_px else (0, 0)
        t = int(point.get("t_ms", 0))
        out.append((int(point["x"]) + jx, int(point["y"]) + jy, max(0, t - last_t)))
        last_t = t
    return out
