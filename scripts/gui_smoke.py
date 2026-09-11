#!/usr/bin/env python3
"""Headless/headful Motif GUI smoke: exercise packs A–E UI paths and grab themes."""
from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, default=ROOT / "docs/media/smoke")
    parser.add_argument("--prefix", default="smoke")
    parser.add_argument("--platform", default=os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    os.environ["QT_QPA_PLATFORM"] = args.platform
    # Avoid fighting a live Motif.app for the localhost API port during smoke.
    os.environ.setdefault("MOTIF_GUI_SMOKE", "1")

    results: list[dict] = []

    def step(name: str, fn) -> None:
        try:
            detail = fn() or "ok"
            results.append({"step": name, "ok": True, "detail": detail})
            print(f"PASS {name}: {detail}")
        except Exception as exc:  # noqa: BLE001
            results.append({"step": name, "ok": False, "detail": f"{exc}"})
            print(f"FAIL {name}: {exc}")
            traceback.print_exc()

    from motif.ui.main_window import MainWindow, configure_qt
    from motif.ui import theme
    from motif.models import EventType
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import QTimer

    configure_qt()
    os.environ["QT_QPA_PLATFORM"] = args.platform
    app = QApplication.instance() or QApplication(["motif-gui-smoke"])
    app.setStyle("Fusion")

    win = MainWindow()
    # Don't start real localhost API if already taken — swallow via quiet path.
    try:
        if getattr(win, "api", None) and win.api.running:
            win.api.stop()
    except Exception:
        pass

    win.resize(1100, 720)
    win.show()
    app.processEvents()

    def grab(tag: str) -> str:
        path = args.out / f"{args.prefix}-{tag}.png"
        pix = win.grab()
        pix.save(str(path))
        return str(path)

    step("show_window", lambda: f"visible={win.isVisible()} size={win.width()}x{win.height()}")
    step("load_example", lambda: (win.load_example(), f"events={len(win.script.events)} name={win.script.name}")[1])
    step("grab_night", lambda: grab("night"))

    def themes():
        paths = []
        for name, tag in (("day", "day"), ("high_contrast", "hc"), ("night", "night2")):
            win._set_theme(name)
            app.processEvents()
            paths.append(grab(tag))
        win.cycle_theme()
        app.processEvents()
        return ",".join(Path(p).name for p in paths)

    step("cycle_themes", themes)

    def text_scales():
        for s in (1.0, 1.15, 1.3, 1.0):
            win._set_text_scale(s)
            app.processEvents()
        return f"scale={win.settings.get('text_scale')}"

    step("text_scale", text_scales)

    def inspector_branch():
        # Select first event; add wait_image-like fields via script + refresh
        from motif.models import Event

        ev = Event(
            type=EventType.WAIT_IMAGE.value,
            template="/tmp/motif-template-missing.png",
            threshold=0.8,
            click_on_find=True,
            click_anchor="center",
            on_found="continue",
            on_miss="stop",
            label="img1",
            timeout_ms=500,
        )
        win.script.events.append(ev)
        win.dirty = True
        win.refresh()
        app.processEvents()
        # toggle preserve + window relative on script pane
        insp = win.inspector
        if hasattr(insp, "preserve_jitter"):
            insp.preserve_jitter.setChecked(True)
        if hasattr(insp, "window_relative"):
            insp.window_relative.setChecked(True)
        if hasattr(insp, "_apply_script_fields"):
            insp._apply_script_fields()
        elif hasattr(insp, "apply_script"):
            insp.apply_script()
        win.script.preserve_micro_jitter = True
        win.script.window_relative = True
        return (
            f"wait_image_events={sum(1 for e in win.script.events if e.type==EventType.WAIT_IMAGE.value)} "
            f"jitter={win.script.preserve_micro_jitter} winrel={win.script.window_relative}"
        )

    step("inspector_a_b_fields", inspector_branch)
    step("grab_features", lambda: grab("features"))

    def tray_and_schedule():
        win._settings["tray_enabled"] = True
        win._setup_tray()
        from motif.schedule import ScheduleEntry, schedules_to_settings

        entry = ScheduleEntry(kind="delay", delay_minutes=9999, path="", enabled=False)
        # Prefer public helpers if present
        if hasattr(win, "_schedules"):
            win._schedules.append(entry)
            win._persist_schedules()
        return f"tray={win._tray is not None} schedules={len(getattr(win,'_schedules',[]))}"

    step("tray_schedule", tray_and_schedule)

    def transport_cycle():
        # Cycles / speed widgets
        if hasattr(win, "cycles_spin"):
            win.cycles_spin.setValue(2)
        if hasattr(win, "speed_spin"):
            win.speed_spin.setValue(1.5)
        app.processEvents()
        # Don't start real OS-level record long; call stop_all safety
        win.stop_all()
        return f"cycles={getattr(win,'cycles_spin',None) and win.cycles_spin.value()} speed={win.script.humanize.speed}"

    step("transport", transport_cycle)

    def humanize_presets():
        from motif.models import HumanizePreset

        for preset in (HumanizePreset.PRECISE.value, HumanizePreset.NATURAL.value, HumanizePreset.CAUTIOUS.value):
            win.script.humanize.apply_preset(preset)
        win.script.humanize.apply_preset(HumanizePreset.PRECISE.value)
        win.refresh()
        app.processEvents()
        return f"preset={win.script.humanize.preset}"

    step("humanize", humanize_presets)
    step("grab_final", lambda: grab("final"))

    # close cleanly without discard dialog: mark clean
    win.dirty = False
    win.close()
    app.processEvents()

    summary = {
        "platform": args.platform,
        "prefix": args.prefix,
        "passed": sum(1 for r in results if r["ok"]),
        "failed": sum(1 for r in results if not r["ok"]),
        "results": results,
        "out": str(args.out),
    }
    print(json.dumps(summary, indent=2))
    (args.out / f"{args.prefix}-summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
