# Motif — mouse & keyboard recorder, auto clicker, and macro recorder for Mac

Motif records, edits, and replays mouse movement, clicks, and keystrokes. It is a Mac-first auto clicker and mouse recorder (also Windows and Linux): capture a take, edit the event list, replay it. Visual timeline, colour-pixel triggers, looping, and humanized playback — TinyTask-style record and replay, not a Keyboard Maestro clone.

Also known as a Mac auto clicker, keyboard recorder, click recorder, mouse macro, or input recorder.

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

## External trigger / Local API

Local control is **off by default** so macOS does not prompt for Local Network access. Recording and replay work without it.

**Motif.app must be running.** Then turn on **Motif → Enable Local Control (localhost)** (or Preferences). Other programs on this machine can call:

```
http://127.0.0.1:7842
```

There is **no authentication**. The server binds to localhost only. Do not expose that port (no reverse proxy, no `0.0.0.0`). Browser pages from other origins are rejected; `curl` and local scripts (no `Origin` header) are the intended clients.

| Method | Path | What it does |
| --- | --- | --- |
| GET | `/health` | `{ok, app}` |
| GET | `/status` | recording / playing, event count, current motif name |
| GET | `/script` | current motif JSON (includes recorded key names) |
| POST | `/play` | play the loaded motif; optional JSON `path` and `loops` |
| POST | `/stop` | stop play or record |
| POST | `/record` | toggle recording |
| POST | `/load` | load a file (`{"path":"…"}`) without playing |

There is **no play-by-name**. `/status` reports the current motif `name`; `POST /play` only accepts `path` and `loops`.

```bash
# currently loaded motif
curl -X POST http://127.0.0.1:7842/play

# a file (loads it, then plays)
curl -X POST http://127.0.0.1:7842/play \
  -H "Content-Type: application/json" \
  -d '{"path":"/absolute/path/to/script.motif.json"}'

# stop
curl -X POST http://127.0.0.1:7842/stop

# optional: loops, or load without playing
curl -X POST http://127.0.0.1:7842/play \
  -H "Content-Type: application/json" \
  -d '{"loops":3}'
curl -X POST http://127.0.0.1:7842/load \
  -H "Content-Type: application/json" \
  -d '{"path":"/absolute/path/to/script.motif.json"}'
```

**Keyboard Maestro / Shortcuts:** add a Run Shell Script action and paste one of the `curl` lines. Motif.app must already be open with local control on.

**CLI** (same machine): `motif play FILE` or `python3 start.py play FILE` talks to the running app when local control is on; if the GUI is not reachable it falls back to headless replay. `motif play FILE --headless` skips the API. `motif stop`, `motif status`, and `motif record` also hit the local server.

```python
from motif import MotifClient
MotifClient().play()
MotifClient().play("/absolute/path/to/script.motif.json", loops=3)
```

When you trigger through the API, Accessibility / Input Monitoring / Screen Recording belong to **Motif.app**. Headless `motif play` (no GUI) attributes those to Terminal or Python instead.
