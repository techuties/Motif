# Motif ship checklist (Pack E)

TinyTask-style recorder — keep packaging light. No Apple Developer cert required.

## macOS — Motif.app

1. From the project root (clean `dev` tree):
   ```bash
   python3 start.py setup          # repair .venv if needed
   python3 start.py test           # pytest must be green
   python3 start.py app            # builds ./Motif.app
   python3 start.py install        # optional: /Applications/Motif.app + bookmark
   ```
2. Open **Motif.app** (project or Applications). Grant **Accessibility**, **Input Monitoring**, and **Screen Recording** to that Motif binary — not Terminal.
3. Smoke: Record (F9) → stop → Replay (F10). Tray: Show / Record / Replay last / Quit.
4. Optional ad-hoc sign only (no Apple cert):
   ```bash
   codesign --force --deep --sign - Motif.app
   ```
   Gatekeeper may still require right-click → Open on unsigned builds.

## Linux — portable tarball

```bash
bash scripts/linux-bundle.sh
# → dist/Motif-linux-<arch>.tar.gz
tar -xzf dist/Motif-linux-*.tar.gz
./Motif-linux-*/run-motif.sh
```

First run creates `.venv` and installs deps. GUI needs a desktop session + the Qt/PySide stack from `requirements.txt`. See README “Linux smoke”.

## Windows

Future: `start.cmd` already launches Motif. A zip/`pyinstaller` one-folder build is planned; not required for this pack.

## Do not

- Require notarization or a paid Apple signing identity for day-to-day builds
- Copy Motif.app in Finder into `/Applications` (use `start.py install`)
- Ship cloud sync or a full scripting runtime (out of product scope)
