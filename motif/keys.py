"""Canonical key names for record and replay."""

from __future__ import annotations

import sys
from collections.abc import Callable

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

# Control+Option+Escape on macOS; Control+Alt+Escape elsewhere. Hard to hit by accident.
EXIT_COMBO = "ctrl+alt+esc"
EXIT_MODIFIERS = frozenset({"ctrl", "alt"})
EXIT_TRIGGER = "esc"
SKIP_HOTKEYS = frozenset(HOTKEY_STOP | HOTKEY_RECORD | HOTKEY_PLAY | {EXIT_COMBO})

_MODIFIER_CANON = {
    "ctrl": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
}


def canonical_key(name: str) -> str:
    return _MODIFIER_CANON.get(name, name)


def is_exit_combo(name: str, held: set[str] | frozenset[str] = ()) -> bool:
    mods = {canonical_key(n) for n in held}
    mods.add(canonical_key(name))
    return canonical_key(name) == EXIT_TRIGGER and EXIT_MODIFIERS <= mods


def is_skip_hotkey(name: str, held: set[str] | frozenset[str] = ()) -> bool:
    """True when this press is F9 / F10 / Esc or the exit chord — do not record it."""
    if name in HOTKEY_STOP | HOTKEY_RECORD | HOTKEY_PLAY:
        return True
    return is_exit_combo(name, held)


def exit_combo_label(*, mac: bool | None = None) -> str:
    if mac is None:
        mac = sys.platform == "darwin"
    return "⌃⌥Esc" if mac else "Ctrl+Alt+Esc"


def exit_combo_words(*, mac: bool | None = None) -> str:
    if mac is None:
        mac = sys.platform == "darwin"
    return "Control+Option+Escape" if mac else "Control+Alt+Escape"


def exit_qt_sequence() -> str:
    """Qt: Meta is Control on macOS; Ctrl is Command there."""
    return "Meta+Alt+Esc" if sys.platform == "darwin" else "Ctrl+Alt+Esc"


def pynput_exit_hotkey() -> str:
    return "<ctrl>+<alt>+<esc>"


def normalize_pynput_hotkey(spec: str) -> str:
    """Accept 'f6', '<f6>', 'ctrl+shift+f6' → pynput GlobalHotKeys form."""
    raw = (spec or "").strip().lower().replace(" ", "")
    if not raw:
        return ""
    if raw.startswith("<") and raw.endswith(">"):
        return raw
    parts = [p for p in raw.replace("-", "+").split("+") if p]
    if not parts:
        return ""
    mapped = []
    for part in parts[:-1]:
        if part in {"ctrl", "control", "ctl"}:
            mapped.append("<ctrl>")
        elif part in {"alt", "option"}:
            mapped.append("<alt>")
        elif part in {"shift"}:
            mapped.append("<shift>")
        elif part in {"cmd", "command", "super", "meta", "win"}:
            mapped.append("<cmd>")
        else:
            mapped.append(f"<{part}>")
    last = parts[-1]
    mapped.append(f"<{last}>" if not (last.startswith("<") and last.endswith(">")) else last)
    return "+".join(mapped)


class GlobalHotkeys:
    """pynput GlobalHotKeys — F9/F10/exit plus optional motif library bindings."""

    def __init__(
        self,
        on_hotkey: Callable[[str], None],
        extra: dict[str, str] | None = None,
    ) -> None:
        self.on_hotkey = on_hotkey
        self.extra = dict(extra or {})  # pynput_hotkey -> action name (play_path:…)
        self._listener = None

    def set_extra(self, extra: dict[str, str] | None) -> None:
        self.extra = dict(extra or {})
        self.restart()

    def restart(self) -> None:
        self.stop()
        self.start()

    def start(self) -> None:
        if self._listener is not None:
            return
        try:
            from pynput.keyboard import GlobalHotKeys

            mapping = {
                pynput_exit_hotkey(): lambda: self.on_hotkey("stop"),
                "<f9>": lambda: self.on_hotkey("record"),
                "<f10>": lambda: self.on_hotkey("play"),
            }
            for hotkey, action in self.extra.items():
                key = normalize_pynput_hotkey(hotkey)
                if not key or key in mapping:
                    continue
                # bind action string by default-arg capture
                mapping[key] = (lambda act=action: self.on_hotkey(act))
            self._listener = GlobalHotKeys(mapping)
            self._listener.start()
        except Exception:
            self._listener = None

    def stop(self) -> None:
        listener = self._listener
        self._listener = None
        if listener is None:
            return
        try:
            listener.stop()
        except Exception:
            pass
