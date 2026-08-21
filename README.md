# Motif — mouse & keyboard recorder, auto-clicker, and macro replay

Motif records, edits, and replays mouse and keyboard input on macOS, Windows, and Linux. Use it as a mouse recorder, keyboard recorder, auto-clicker, or macro recorder: visual timeline, colour-pixel triggers, looping, and humanized playback.

Also called: auto clicker, input recorder, macro replay, input replay, desktop automation.

GitHub topics (paste when you publish): `motif` `auto-clicker` `autoclicker` `mouse-recorder` `keyboard-recorder` `macro-recorder` `input-recorder` `input-replay` `automation` `pynput` `macos`

## Start

**Mac:** open `Motif.app` (preferred — permissions attach to Motif). If it is missing, run `python3 start.py app` once, then open `Motif.app`. `Motif.command` is a fallback and will open `Motif.app` when it exists.

**Windows:** double-click `start.cmd`

**Any terminal:**

```bash
python3 start.py
```

Requires **Python 3.11+**. The first run creates `.venv`, installs Motif, and opens the window. After that, the same command just starts. A terminal start on Mac still attributes Accessibility to Terminal/Python — use `Motif.app` for recording.

## Motif.app and Applications

The project copy lives next to this README:

```
<this folder>/Motif.app
```

That stub is tied to this project’s `.venv`. A Finder copy into `/Applications` will not work.

To put Motif in Applications while still running this project:

```bash
python3 start.py install
```

or **Motif → Install to Applications** in the app.

That rebuilds the project `Motif.app` if needed, then installs `/Applications/Motif.app` with a bookmark back to this folder. After install, grant Accessibility, Input Monitoring, and Screen Recording to **that** Motif (`/Applications/Motif.app`), then open it from Applications.

- Project: `<this folder>/Motif.app` — fine to open while developing
- Applications: `/Applications/Motif.app` — same project, permissions attach to the Applications copy

## Manage

```bash
python3 start.py setup           # repair the install
python3 start.py app             # build Motif.app (macOS)
python3 start.py install         # install /Applications/Motif.app (macOS)
python3 start.py test            # run checks
python3 start.py play FILE       # play a saved motif
python3 start.py help
```

Hotkeys: **F9** record · **F10** replay · **⌃⌥Esc** stop (Control+Option+Escape on Mac, Control+Alt+Escape elsewhere). Esc still stops when Motif is focused.

## Permissions

On **macOS**, grant these to **the Motif you opened** (project `Motif.app` or `/Applications/Motif.app` — not Terminal, Motif.command, or Python):

1. **Accessibility** — required to record and replay
2. **Input Monitoring** — required for global keyboard/mouse taps on recent macOS
3. **Screen Recording** — only for colour-pixel triggers

**Local Network is not required.** Motif does not start its localhost control server unless you turn that on.

Open Motif.app first so it appears in those lists. Use Help → Permissions in the app. Then **quit Motif and open the same Motif.app again** so the new rights apply.

If you previously allowed Terminal or Python, you can leave those on; Motif.app still needs its own ticks.

On **Linux**, global hooks work on X11. Wayland restricts them; use an X11 session for full record/replay.

On **Windows**, allow Motif through security prompts. High-DPI scaling is handled automatically.

## Scripts

Motifs are saved as `.motif.json`. Coordinates are stored relative to a **zero-ground origin** so loops stay aligned if you move that origin. Values are **global logical points** on the whole virtual desktop (extra monitors included, Retina points not physical pixels).

**Replay at recorded origin** (default) plays back on the same display(s) you recorded, even if the Motif window is on another screen. **Replay from current cursor** shifts the whole path to wherever the mouse is — if you click Replay on a second monitor, that is where it runs.

## External control

Local control is **off by default** so macOS does not prompt for Local Network access. Recording and replay work without it.

To let other programs on this machine call Motif, turn on **Motif → Enable Local Control (localhost)** (or Preferences). Then they can use `http://127.0.0.1:7842`.

There is **no authentication**. The server binds to localhost only. Do not expose that port (no reverse proxy, no `0.0.0.0`). `GET /script` returns the current motif, including recorded key names.

```bash
curl http://127.0.0.1:7842/status
curl -X POST http://127.0.0.1:7842/play
curl -X POST http://127.0.0.1:7842/stop
```

```python
from motif import MotifClient
MotifClient().play()
```

```bash
python3 start.py play script.motif.json --loops 3
```
