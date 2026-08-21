"""GUI and CLI entry: python -m motif"""

from __future__ import annotations

import argparse
import json
import sys


def _enable_dpi() -> None:
    if sys.platform == "win32":
        try:
            import ctypes

            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
            except Exception:
                pass


def main(argv: list[str] | None = None) -> int:
    _enable_dpi()
    parser = argparse.ArgumentParser(
        prog="motif",
        description="Record, edit, and replay mouse and keyboard motifs.",
    )
    sub = parser.add_subparsers(dest="cmd")
    play = sub.add_parser("play", help="Play a saved motif via the running app, or headless")
    play.add_argument("path")
    play.add_argument("--loops", type=int, default=None)
    play.add_argument("--headless", action="store_true", help="Replay without the GUI")
    sub.add_parser("stop", help="Stop the running Motif app")
    sub.add_parser("status", help="Ask the running Motif app for status")
    sub.add_parser("record", help="Toggle recording in the running Motif app")
    parser.add_argument("--version", action="store_true")
    args = parser.parse_args(argv)

    if args.version:
        from motif import __version__

        print(__version__)
        return 0

    if args.cmd in {"play", "stop", "status", "record"}:
        from motif.api import MotifClient

        client = MotifClient()
        if args.cmd == "status":
            print(json.dumps(client.status(), indent=2))
            return 0
        if args.cmd == "stop":
            print(json.dumps(client.stop(), indent=2))
            return 0
        if args.cmd == "record":
            print(json.dumps(client.record(), indent=2))
            return 0
        if args.cmd == "play" and not args.headless:
            try:
                print(json.dumps(client.play(args.path, args.loops), indent=2))
                return 0
            except ConnectionError:
                print("Motif GUI is not running — replaying headless.", file=sys.stderr)
        if args.cmd == "play":
            from motif.macos import prepare_input_hooks
            from motif.player import Player
            from motif.storage import load_script

            prepare_input_hooks()

            script = load_script(args.path)
            if args.loops is not None:
                script.loop.count = args.loops
            result = Player().play(script)
            print(result)
            return 0 if result == "done" else 1

    from motif.ui.main_window import run_app

    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
