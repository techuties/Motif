"""Save and load .motif.json scripts."""

from __future__ import annotations

import json
from pathlib import Path

from motif.models import Script, script_from_dict, script_to_dict

EXTENSION = ".motif.json"


def save_script(script: Script, path: str | Path) -> Path:
    target = Path(path)
    if target.suffix == "":
        target = target.with_suffix(EXTENSION)
    elif not str(target).endswith(EXTENSION) and target.suffix == ".json":
        target = target.with_name(target.stem + EXTENSION if not target.stem.endswith(".motif") else target.name)
    target.write_text(json.dumps(script_to_dict(script), indent=2), encoding="utf-8")
    return target


def load_script(path: str | Path) -> Script:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Script file must contain a JSON object")
    return script_from_dict(data)
