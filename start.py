#!/usr/bin/env python3
"""First-run manager: create the venv, install Motif, then start or test it."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import sysconfig
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VENV = ROOT / ".venv"
MIN_MINOR = 11


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def in_motif_app() -> bool:
    return os.environ.get("MOTIF_BUNDLE") == "1"


def in_venv() -> bool:
    if in_motif_app():
        return True
    try:
        return Path(sys.prefix).resolve() == VENV.resolve()
    except OSError:
        return False


def die(message: str, code: int = 1) -> None:
    print(message, file=sys.stderr)
    raise SystemExit(code)


def pyside6_plugin_root(search_root: Path | None = None) -> Path | None:
    """Absolute PySide6/Qt/plugins dir, or None if it is not installed yet."""
    candidates: list[Path] = []
    root = search_root if search_root is not None else VENV
    if sys.platform == "win32":
        candidates.append(root / "Lib" / "site-packages" / "PySide6" / "Qt" / "plugins")
    candidates.extend(sorted(root.glob("lib/python*/site-packages/PySide6/Qt/plugins")))
    try:
        candidates.append(Path(sysconfig.get_path("purelib")) / "PySide6" / "Qt" / "plugins")
    except (KeyError, OSError):
        pass
    seen: set[Path] = set()
    for plugins in candidates:
        try:
            resolved = plugins.resolve()
        except OSError:
            continue
        if resolved in seen or not resolved.is_dir():
            continue
        seen.add(resolved)
        return resolved
    return None


def qt_plugin_cache_dir() -> Path:
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "Motif" / "qt-plugins"
    if sys.platform == "win32":
        base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
        return Path(base) / "Motif" / "qt-plugins"
    return Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache")) / "motif" / "qt-plugins"


def plugins_without_spaces(plugins: Path) -> Path:
    """Qt's QFactoryLoader cannot discover plugins when the path contains spaces."""
    if " " not in str(plugins):
        return plugins
    cache = qt_plugin_cache_dir()
    for item in plugins.rglob("*"):
        dest = cache / item.relative_to(plugins)
        if item.is_dir():
            dest.mkdir(parents=True, exist_ok=True)
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        if dest.exists() or dest.is_symlink():
            dest.unlink()
        try:
            dest.symlink_to(item)
        except OSError:
            shutil.copy2(item, dest)
    return cache


def apply_qt_plugin_env(search_root: Path | None = None) -> Path | None:
    """Set absolute Qt plugin env vars before any PySide6 / Qt import."""
    plugins = pyside6_plugin_root(search_root)
    if plugins is None:
        return None
    plugins = plugins_without_spaces(plugins)
    platforms = plugins / "platforms"
    os.environ["QT_PLUGIN_PATH"] = str(plugins)
    if platforms.is_dir():
        os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms)
    if sys.platform == "darwin":
        os.environ.setdefault("QT_QPA_PLATFORM", "cocoa")
    return plugins


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
  python3 start.py app          build Motif.app (macOS)
  python3 start.py install      put Motif.app in /Applications (macOS)
  python3 start.py test         run checks
  python3 start.py play FILE    play a saved motif
  python3 start.py help

Windows: double-click start.cmd
Linux: python3 start.py
Mac: open Motif.app (preferred). Motif.command is a fallback.
Copying Motif.app in Finder to /Applications will break — use install.

F9 record · F10 replay · ⌃⌥Esc stop (Control+Option+Escape)
"""
    )


INFO_PLIST = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleDisplayName</key>
    <string>Motif</string>
    <key>CFBundleExecutable</key>
    <string>Motif</string>
    <key>CFBundleIconFile</key>
    <string>AppIcon</string>
    <key>CFBundleIdentifier</key>
    <string>app.motif.recorder</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundleName</key>
    <string>Motif</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSApplicationCategoryType</key>
    <string>public.app-category.utilities</string>
    <key>LSMinimumSystemVersion</key>
    <string>13.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticTermination</key>
    <false/>
    <key>NSSupportsSuddenTermination</key>
    <false/>
    <key>NSAppleEventsUsageDescription</key>
    <string>Motif only uses Apple Events if a script asks another Mac app to cooperate.</string>
    <key>NSAccessibilityUsageDescription</key>
    <string>Motif records and replays mouse and keyboard. Grant Accessibility to Motif so those events can be captured and sent.</string>
    <key>NSScreenCaptureUsageDescription</key>
    <string>Motif reads pixel colours for wait-until-colour triggers. Grant Screen Recording to Motif if you use that feature.</string>
</dict>
</plist>
"""


def _iconset_sizes() -> list[tuple[str, int]]:
    return [
        ("icon_16x16.png", 16),
        ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32),
        ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128),
        ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256),
        ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512),
        ("icon_512x512@2x.png", 1024),
    ]


def build_icns(source: Path, dest: Path) -> None:
    import tempfile

    dest.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="motif-iconset-") as raw:
        iconset = Path(raw) / "Motif.iconset"
        iconset.mkdir()
        for name, size in _iconset_sizes():
            run(["sips", "-z", str(size), str(size), str(source), "--out", str(iconset / name)], quiet=True)
        run(["iconutil", "-c", "icns", str(iconset), "-o", str(dest)])


def build_app() -> int:
    """Compile Motif.app so Accessibility / Input Monitoring attach to Motif."""
    if sys.platform != "darwin":
        die("Motif.app is only built on macOS.")
    src = ROOT / "packaging" / "motif_launcher.m"
    icon = ROOT / "packaging" / "AppIcon.png"
    if not src.is_file():
        die(f"Missing launcher source: {src}")
    if not icon.is_file():
        die(f"Missing app icon: {icon}")

    import sysconfig

    include = sysconfig.get_path("include")
    libdir = sysconfig.get_config_var("LIBDIR") or ""
    ldversion = sysconfig.get_config_var("LDVERSION") or f"{sys.version_info.major}.{sys.version_info.minor}"
    bindir = Path(sysconfig.get_config_var("BINDIR") or sys.base_prefix) / "bin"
    py_config = bindir / f"python{ldversion}-config"
    if not py_config.is_file():
        py_config = bindir / "python3-config"

    app = ROOT / "Motif.app"
    macos = app / "Contents" / "MacOS"
    resources = app / "Contents" / "Resources"
    macos.mkdir(parents=True, exist_ok=True)
    resources.mkdir(parents=True, exist_ok=True)
    (app / "Contents" / "Info.plist").write_text(INFO_PLIST, encoding="utf-8")
    build_icns(icon, resources / "AppIcon.icns")

    exe = macos / "Motif"
    clang: list[str] = [
        "clang",
        "-fobjc-arc",
        "-O2",
        "-DMOTIF_BUILD_PYTHON=" + json.dumps(str(Path(sys.base_prefix) / "bin" / f"python{ldversion}")),
        "-o",
        str(exe),
        str(src),
        f"-I{include}",
    ]
    if py_config.is_file():
        cflags = subprocess.check_output([str(py_config), "--cflags"], text=True).split()
        ldflags = subprocess.check_output([str(py_config), "--embed", "--ldflags"], text=True).split()
        clang.extend(cflags)
        clang.extend(ldflags)
    else:
        clang.extend(
            [
                f"-L{libdir}",
                f"-lpython{ldversion}",
                f"-Wl,-rpath,{libdir}",
                "-ldl",
                "-framework",
                "CoreFoundation",
            ]
        )
    clang.extend(["-framework", "Cocoa"])
    print("Compiling Motif.app…")
    run(clang)
    subprocess.call(["strip", "-x", str(exe)])
    # iCloud Drive leaves Finder info / resource forks that codesign rejects.
    subprocess.call(["xattr", "-cr", str(app)])
    run(
        [
            "codesign",
            "--force",
            "--deep",
            "--sign",
            "-",
            "--identifier",
            "app.motif.recorder",
            str(app),
        ]
    )
    print(f"Built {app}")
    print("Open Motif.app, then grant Accessibility, Input Monitoring, and Screen Recording to Motif.")
    return 0


PROJECT_BOOKMARK = "MotifProject"
BUNDLE_ID = "app.motif.recorder"


def project_app() -> Path:
    return ROOT / "Motif.app"


def applications_app() -> Path:
    return Path("/Applications/Motif.app")


def is_motif_bundle(path: Path) -> bool:
    plist = path / "Contents" / "Info.plist"
    if not plist.is_file():
        return False
    try:
        return BUNDLE_ID in plist.read_text(encoding="utf-8", errors="ignore")
    except OSError:
        return False


def write_project_bookmark(app: Path, project: Path) -> Path:
    dest = app / "Contents" / "Resources" / PROJECT_BOOKMARK
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(str(project.resolve()) + "\n", encoding="utf-8")
    return dest


def read_project_bookmark(app: Path) -> Path | None:
    path = app / "Contents" / "Resources" / PROJECT_BOOKMARK
    if not path.is_file():
        return None
    try:
        line = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    if not line or not line[0].strip():
        return None
    return Path(line[0].strip())


def _codesign_app(app: Path) -> None:
    subprocess.call(["xattr", "-cr", str(app)])
    run(
        [
            "codesign",
            "--force",
            "--deep",
            "--sign",
            "-",
            "--identifier",
            BUNDLE_ID,
            str(app),
        ]
    )


def install_app_bundle(src: Path, dest: Path, project: Path, *, sign: bool = True) -> Path:
    """Copy a Motif.app and write a bookmark so it still runs this project."""
    if not src.is_dir():
        raise OSError(f"Missing Motif.app at {src}")
    dest = Path(dest)
    if dest.exists():
        if dest.is_dir() and is_motif_bundle(dest):
            shutil.rmtree(dest)
        else:
            raise OSError(f"{dest} already exists and is not Motif.")
    shutil.copytree(src, dest, symlinks=True)
    write_project_bookmark(dest, project)
    if sign and sys.platform == "darwin":
        _codesign_app(dest)
    return dest


def _app_needs_rebuild(app: Path) -> bool:
    exe = app / "Contents" / "MacOS" / "Motif"
    src = ROOT / "packaging" / "motif_launcher.m"
    if not exe.is_file():
        return True
    if src.is_file() and src.stat().st_mtime > exe.stat().st_mtime:
        return True
    return False


def install_to_applications(dest: Path | None = None) -> Path:
    """Rebuild Motif.app if needed and install a launcher into /Applications."""
    if sys.platform != "darwin":
        raise OSError("Install to Applications is only available on macOS.")
    dest = Path(dest) if dest is not None else applications_app()
    src = project_app()
    if _app_needs_rebuild(src):
        build_app()
    if not (src / "Contents" / "MacOS" / "Motif").is_file():
        raise OSError(f"Could not build Motif.app at {src}")
    return install_app_bundle(src, dest, ROOT, sign=True)


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    cmd = argv[0] if argv else "start"

    if cmd in {"-h", "--help", "help"}:
        usage()
        return 0

    check_host_python()
    if not in_venv():
        ensure_install(force=(cmd == "setup"))
        apply_qt_plugin_env(VENV)
        if cmd == "setup":
            print(f"Using {venv_python()}")
            return 0
        return relaunch_in_venv(argv)

    apply_qt_plugin_env(VENV)
    if cmd == "setup":
        ensure_install(force=True)
        return 0
    if cmd == "app":
        return build_app()
    if cmd == "install":
        try:
            dest = install_to_applications()
        except OSError as exc:
            die(str(exc))
        print(f"Installed {dest}")
        print(f"It still runs this project: {ROOT}")
        print("Grant Accessibility, Input Monitoring, and Screen Recording to that Motif.")
        return 0
    if cmd == "test":
        py = str(venv_python()) if in_motif_app() else sys.executable
        return subprocess.call([py, "-m", "pytest", str(ROOT / "tests"), "-q"], cwd=ROOT)
    from motif.__main__ import main as app_main

    return app_main([] if cmd == "start" else argv)


if __name__ == "__main__":
    raise SystemExit(main())
