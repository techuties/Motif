"""Simple in-app motif scheduler (Pack C).

Schedules run only while Motif is open. Persist via settings.json.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4


@dataclass
class ScheduleEntry:
    id: str = field(default_factory=lambda: uuid4().hex[:10])
    path: str = ""
    kind: str = "daily"  # daily | delay
    time_local: str = "09:00"  # HH:MM for daily
    delay_minutes: int = 30  # for delay kind
    enabled: bool = True
    last_fired: str = ""  # ISO date YYYY-MM-DD for daily dedupe
    fire_at_epoch: float = -1.0  # absolute epoch for one-shot delay; <0 means unset

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "path": self.path,
            "kind": self.kind,
            "time_local": self.time_local,
            "delay_minutes": int(self.delay_minutes),
            "enabled": bool(self.enabled),
            "last_fired": self.last_fired,
            "fire_at_epoch": float(self.fire_at_epoch),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScheduleEntry:
        return cls(
            id=str(data.get("id") or uuid4().hex[:10]),
            path=str(data.get("path") or ""),
            kind=str(data.get("kind") or "daily"),
            time_local=str(data.get("time_local") or "09:00"),
            delay_minutes=int(data.get("delay_minutes") or 30),
            enabled=bool(data.get("enabled", True)),
            last_fired=str(data.get("last_fired") or ""),
            fire_at_epoch=float(data["fire_at_epoch"]) if data.get("fire_at_epoch") is not None else -1.0,
        )


def parse_hhmm(text: str) -> tuple[int, int] | None:
    raw = (text or "").strip()
    if not raw or ":" not in raw:
        return None
    try:
        hh_s, mm_s = raw.split(":", 1)
        hh, mm = int(hh_s), int(mm_s)
    except (TypeError, ValueError):
        return None
    if not (0 <= hh <= 23 and 0 <= mm <= 59):
        return None
    return hh, mm


def due_entries(entries: list[ScheduleEntry], *, now: datetime | None = None) -> list[ScheduleEntry]:
    """Return schedules that should fire now (caller marks last_fired / disables delay)."""
    now = now or datetime.now()
    due: list[ScheduleEntry] = []
    for entry in entries:
        if not entry.enabled or not entry.path:
            continue
        if entry.kind == "delay":
            if entry.fire_at_epoch >= 0 and time.time() >= entry.fire_at_epoch:
                due.append(entry)
            continue
        # daily
        hm = parse_hhmm(entry.time_local)
        if hm is None:
            continue
        hh, mm = hm
        if (now.hour, now.minute) != (hh, mm):
            continue
        today = now.strftime("%Y-%m-%d")
        if entry.last_fired == today:
            continue
        due.append(entry)
    return due


def arm_delay(entry: ScheduleEntry, *, minutes: int | None = None, now: float | None = None) -> ScheduleEntry:
    minutes = entry.delay_minutes if minutes is None else minutes
    entry.kind = "delay"
    entry.delay_minutes = max(0, int(minutes))
    entry.fire_at_epoch = (now if now is not None else time.time()) + entry.delay_minutes * 60.0
    entry.enabled = True
    return entry


def mark_fired(entry: ScheduleEntry, *, now: datetime | None = None) -> ScheduleEntry:
    now = now or datetime.now()
    if entry.kind == "daily":
        entry.last_fired = now.strftime("%Y-%m-%d")
    else:
        entry.enabled = False
        entry.fire_at_epoch = -1.0
    return entry


def schedules_from_settings(data: dict[str, Any]) -> list[ScheduleEntry]:
    rows = data.get("schedules") or []
    out: list[ScheduleEntry] = []
    if not isinstance(rows, list):
        return out
    for row in rows:
        if isinstance(row, dict):
            out.append(ScheduleEntry.from_dict(row))
    return out


def schedules_to_settings(entries: list[ScheduleEntry]) -> list[dict[str, Any]]:
    return [e.to_dict() for e in entries]


def next_daily_datetime(time_local: str, *, now: datetime | None = None) -> datetime | None:
    hm = parse_hhmm(time_local)
    if hm is None:
        return None
    now = now or datetime.now()
    hh, mm = hm
    candidate = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if candidate <= now:
        candidate = candidate + timedelta(days=1)
    return candidate
