# Motif

Record, edit, and replay mouse and keyboard. Visual editor, colour triggers, looping, humanized playback.

## Start

**Mac:** double-click `Motif.command`

**Windows:** double-click `start.cmd`

**Any terminal:**

```bash
python3 start.py
```

The first run creates `.venv`, installs Motif, and opens the window. After that, the same command just starts.

## Manage

```bash
python3 start.py setup           # repair the install
python3 start.py test            # run checks
python3 start.py play FILE       # play a saved motif
python3 start.py help
```

Hotkeys: **F9** record · **F10** play · **Esc** stop

On macOS, grant **Accessibility** and **Screen Recording** to Terminal or Python (Help → Permissions in the app).

## Save / load

Scripts are `.motif.json`. Other programs on this machine can drive a running Motif at `http://127.0.0.1:7842`.
