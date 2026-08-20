"""Canonical key names for record and replay."""

from __future__ import annotations

from pynput.keyboard import Key, KeyCode

SPECIAL = {name: getattr(Key, name) for name in dir(Key) if name[:1].islower()}
ALIASES = {
    "cmd": "cmd",
    "command": "cmd",
    "super": "cmd",
    "win": "cmd",
    "windows": "cmd",
    "control": "ctrl",
    "ctl": "ctrl",
    "option": "alt",
    "return": "enter",
    "esc": "esc",
    "escape": "esc",
    "spacebar": "space",
    "pgup": "page_up",
    "pgdn": "page_down",
    "del": "delete",
    "ins": "insert",
}


def key_to_name(key: Key | KeyCode | None) -> str:
    if key is None:
        return ""
    if isinstance(key, Key):
        return key.name
    if getattr(key, "char", None):
        char = key.char
        if char:
            return char
    vk = getattr(key, "vk", None)
    if vk is not None:
        return f"vk_{vk}"
    return str(key).replace("Key.", "").strip("'")


def name_to_key(name: str) -> Key | KeyCode | None:
    if not name:
        return None
    raw = ALIASES.get(name.lower(), name)
    if raw in SPECIAL:
        return SPECIAL[raw]
    lowered = raw.lower()
    if lowered in SPECIAL:
        return SPECIAL[lowered]
    if raw.startswith("vk_"):
        try:
            return KeyCode.from_vk(int(raw[3:]))
        except ValueError:
            return None
    if len(raw) == 1:
        return KeyCode.from_char(raw)
    return KeyCode.from_char(raw)


HOTKEY_STOP = {"esc"}
HOTKEY_RECORD = {"f9"}
HOTKEY_PLAY = {"f10"}
