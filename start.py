#!/usr/bin/env python3
"""First-run manager: create the venv, install Motif, then start or test it."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
MIN_MINOR = 11


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def in_venv() -> bool:
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except OSError:
        return False


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def check_host_python() -> None:
    if sys.version_info < (3, MIN_MINOR):
        die(f"Motif needs Python 3.{MIN_MINOR}+. This is {sys.version.split()[0]}.")


def run(cmd: list[str], quiet: bool = False) -> None:
    try:
        subprocess.check_call(cmd, cwd=ROOT, stdout=subprocess.DEVNULL if quiet else None)
    except subprocess.CalledProcessError as exc:
        die(f"Command failed ({exc.returncode}): {' '.join(cmd)}")


def ensure_install(force: bool = False) -> None:
    py = venv_python()
    if not py.exists():
        print("First run — creating .venv and installing Motif…")
        run([sys.executable, "-m", "venv", str(VENV)])
        force = True
    if force or not _motif_importable(py):
        if not force:
            print("Installing Motif into .venv…")
        run([str(py), "-m", "pip", "install", "-q", "--upgrade", "pip"], quiet=True)
        run([str(py), "-m", "pip", "install", "-q", "-e", f"{ROOT}[dev]"])
        print("Ready.")


def _motif_importable(py: Path) -> bool:
    probe = subprocess.run(
        [str(py), "-c", "import motif, PySide6, pynput"],
        cwd=ROOT,
        capture_output=True,
        check=False,
    )
    return probe.returncode == 0


def relaunch_in_venv(argv: list[str]) -> int:
    py = venv_python()
    return subprocess.call([str(py), str(ROOT / "start.py"), *argv], cwd=ROOT)


def usage() -> None:
    print(
        """Motif — record, edit, replay mouse and keyboard.

  python3 start.py              start the app
  python3 start.py setup        repair the install
  python3 start.py test         run checks
  python3 start.py play FILE    play a saved motif
  python3 start.py help

Mac: double-click Motif.command
Windows: double-click start.cmd

F9 record · F10 play · Esc stop
"""
    )


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "start"

    if cmd in {"-h", "--help", "help"}:
        usage()
        return 0

    check_host_python()
    if not in_venv():
        ensure_install(force=(cmd == "setup"))
        if cmd == "setup":
            print(f"Using {venv_python()}")
            return 0
        return relaunch_in_venv(argv)

    if cmd == "setup":
        ensure_install(force=True)
        return 0
    if cmd == "test":
        return subprocess.call([sys.executable, "-m", "pytest", str(ROOT / "tests"), "-q"], cwd=ROOT)
    if cmd == "start":
        from motif.__main__ import main as app_main

        return app_main([])
    from motif.__main__ import main as app_main

    return app_main(argv)


if __name__ == "__main__":
    raise SystemExit(main())
