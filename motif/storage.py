"""Save and load .motif.json scripts, plus small app settings."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from motif.models import Script, attach_paths_from_raw, script_from_dict, script_to_dict

EXTENSION = ".motif.json"
RAW_EXTENSION = ".raw.motif.json"

SETTINGS_DEFAULTS: dict[str, Any] = {
    "api_enabled": False,
    "show_path": True,
    "show_screen_history": True,
    "split_main": [900, 340],
    "split_left": [480, 120, 220],
}


def save_script(script: Script, path: str | Path) -> Path:
    target = Path(path)
    if target.suffix == "":
        target = target.with_suffix(EXTENSION)
    elif not str(target).endswith(EXTENSION) and target.suffix == ".json":
        target = target.with_name(target.stem + EXTENSION if not target.stem.endswith(".motif") else target.name)
    target.write_text(json.dumps(script_to_dict(script), indent=2), encoding="utf-8")
    return target


def project_dir() -> Path:
    """Repo / launch folder: next to start.py when running from source."""
    here = Path(__file__).resolve()
    root = here.parents[1]
    if (root / "start.py").is_file():
        return root
    cwd = Path.cwd()
    if (cwd / "start.py").is_file():
        return cwd
    return cwd


def raw_path_for(processed: str | Path) -> Path:
    """`name.motif.json` → `name.raw.motif.json` in the same folder."""
    target = Path(processed)
    text = str(target)
    if text.endswith(EXTENSION):
        return Path(text[: -len(EXTENSION)] + RAW_EXTENSION)
    return target.with_name(target.name + RAW_EXTENSION)


def save_raw_capture(
    events: list[dict[str, Any]],
    path: str | Path,
    *,
    script: Script | None = None,
) -> Path:
    """Write the chronological raw capture sidecar (Replay can recover paths from it)."""
    payload: dict[str, Any] = {
        "kind": "motif-raw",
        "events": events,
    }
    if script is not None:
        payload["name"] = script.name
        payload["origin_x"] = script.origin_x
        payload["origin_y"] = script.origin_y
        payload["origin_set"] = script.origin_set
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return target


def load_script(path: str | Path) -> Script:
    target = Path(path)
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Script file must contain a JSON object")
    script = script_from_dict(data)
    sidecar = raw_path_for(target)
    if sidecar.is_file() and sidecar.resolve() != target.resolve():
        try:
            raw = json.loads(sidecar.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            return script
        rows = raw.get("events") if isinstance(raw, dict) else raw
        if isinstance(rows, list):
            attach_paths_from_raw(script, rows)
    return script


def config_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Motif"
    if sys.platform == "win32":
        base = Path.home() / "AppData" / "Local"
        return base / "Motif"
    return Path.home() / ".config" / "motif"


def settings_file() -> Path:
    return config_dir() / "settings.json"


def load_settings() -> dict[str, Any]:
    data = dict(SETTINGS_DEFAULTS)
    path = settings_file()
    if not path.is_file():
        return data
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return data
    if not isinstance(raw, dict):
        return data
    for key, default in SETTINGS_DEFAULTS.items():
        if key not in raw:
            continue
        value = raw[key]
        if isinstance(default, bool):
            data[key] = bool(value)
        elif isinstance(default, list):
            if isinstance(value, list) and value and all(isinstance(x, (int, float)) for x in value):
                data[key] = [int(x) for x in value]
        else:
            data[key] = value
    return data


def save_settings(updates: dict[str, Any]) -> dict[str, Any]:
    merged = load_settings()
    for key in SETTINGS_DEFAULTS:
        if key in updates:
            merged[key] = updates[key]
    path = settings_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(merged, indent=2) + "\n", encoding="utf-8")
    return merged
