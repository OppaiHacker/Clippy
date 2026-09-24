<div align="center">

<img src=".github/assets/hero.svg" width="100%" alt="Clippy — local gameplay clip vault">

<p>
  <img src="https://img.shields.io/badge/python-3.12+-3776AB?style=for-the-badge&logo=python&logoColor=white" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI">
  <img src="https://img.shields.io/badge/Vue_3-42B883?style=for-the-badge&logo=vuedotjs&logoColor=white" alt="Vue 3">
  <img src="https://img.shields.io/badge/PostgreSQL_17-4169E1?style=for-the-badge&logo=postgresql&logoColor=white" alt="PostgreSQL 17">
  <img src="https://img.shields.io/badge/FFmpeg-007808?style=for-the-badge&logo=ffmpeg&logoColor=white" alt="FFmpeg">
  <img src="https://img.shields.io/badge/license-MIT-8b5cf6?style=for-the-badge" alt="MIT">
</p>

**A local-first web app for browsing, tagging and lightly editing gameplay clips —<br>with a real multi-track audio mixer whose preview matches the export, sample for sample.**

<sub>No cloud. No account. No telemetry. Your clips never leave the machine.</sub>

</div>

---

## Why

`gpu-screen-recorder` in replay mode gives you a 300-second RAM buffer and a hotkey. Press it and a clip lands on disk with **four separate Opus audio tracks** — game, Discord, browser, mic — each named in the MP4 metadata.

Every clip tool then does the same wrong thing: it flattens those tracks into one stereo pair before you get to hear them. Discord screaming over the killshot, forever.

Clippy keeps the tracks separate all the way to the export command.

<div align="center">
<img src=".github/assets/pipeline.svg" width="100%" alt="Pipeline: replay buffer, auto-ingest, tag, per-track mix, ffmpeg export — what you hear is what you get">
</div>

---

## Features

<table>
<tr><td width="50%" valign="top">

### 🎚️ Real audio mixer
Per-track gain, pan, mute, solo and offset. Tracks are demuxed once and played back through the Web Audio API, so the browser preview and the `ffmpeg` render share one mix document — no "sounded fine in the editor" surprises.

### 🔍 Dynamic track detection
Track count is **never assumed**. Names are read from `ffprobe` plus the raw `moov/trak/udta/name` atom that older ffprobe builds skip, then classified by prefix into `system` / `app` / `mic` / `device` / `imported`.

### 🏷️ Tags & auto-tagging
Free tags, merge, rename. Game name resolved from the `steam_app_<id>` sidecar hint via the Steam Store API, with a local override table for everything else.

</td><td width="50%" valign="top">

### ✂️ Mini editor
In/out trim, speed, 9:16 crop, video fade in/out, limiter and LUFS normalization on master. Frame stepping, with keyframes marked on the ruler.

### 📦 Export presets
`Original` (stream-copies the video unless it has to cut or filter it, remixes the audio) · `Discord` (bitrate solved from target size and duration, not guessed) · `YouTube` · `Vertical 9:16` · `Audio only`.

### 👀 Watcher + job queue
A `watchfiles` watcher ingests new clips the moment they hit the directory. Thumbnails, sprite sheets, waveform peaks and keyframe indexes are built by a background worker, never on the request path.

### 🗑️ Safe by design
Source clips are never modified. Delete is a 30-day trash with restore; a file only leaves the disk when the trash is emptied or you delete it permanently. HTTP `Range` streaming means no re-encode just to scrub.

</td></tr>
</table>

---

## Architecture

```mermaid
flowchart LR
    A["🎮 gpu-screen-recorder<br/>replay buffer"] -->|hotkey| B["clip.mp4 + sidecar.json"]
    B --> W["👁️ watchfiles watcher"]
    W --> I["ingest<br/>ffprobe · moov atom"]
    I --> DB[("🐘 PostgreSQL")]
    I --> Q["⚙️ job queue"]
    Q --> T["thumbs · sprites"]
    Q --> V["waveform peaks"]
    Q --> K["keyframe index"]
    DB --> API["⚡ FastAPI"]
    T --> API
    V --> API
    K --> API
    API -->|Range streams| UI["🖥️ Vue 3 + Web Audio"]
    UI -->|mix document| API
    API --> X["🎬 ffmpeg export"]
```

The mix document is the contract. The browser renders it through `AudioContext` nodes; the exporter renders the same JSON into an `ffmpeg` filter graph. One document, two renderers, identical result.

---

## Requirements

<div align="center">
<img src=".github/assets/requirements.svg" width="100%" alt="Minimum and recommended system requirements">
</div>

### Officially supported: Arch Linux

<p>
  <img src="https://img.shields.io/badge/Arch_Linux-supported-1793D1?style=flat-square&logo=archlinux&logoColor=white" alt="Arch Linux — supported">
  <img src="https://img.shields.io/badge/other_distros-untested-6c778f?style=flat-square&logo=linux&logoColor=white" alt="Other distros — untested">
  <img src="https://img.shields.io/badge/Windows_·_macOS-unsupported-3b4557?style=flat-square" alt="Windows and macOS — unsupported">
</p>

Arch is the only distribution this is developed and tested on. Nothing in the code is Arch-specific — it is Python, ffmpeg and Postgres — so any modern Linux with the right package versions will almost certainly work. It is just not verified, and bug reports from elsewhere are handled on a best-effort basis.

Windows and macOS are out of scope: the recorder half of the workflow (`gpu-screen-recorder` in replay mode, driven by Wayland compositor hotkeys) does not exist there.

### Software

| Component | Version | Note |
|---|---|---|
| Python | 3.12+ | `pydantic-settings`, async SQLAlchemy |
| ffmpeg / ffprobe | 7.0+ | 8.0+ reads the `moov/trak/udta/name` atom directly; below that Clippy parses it itself |
| PostgreSQL | 17 | via `docker compose`, image `postgres:17` |
| Bun + Node | Bun 1.x, Node 20+ | frontend build only (`vue-tsc` runs on Node), not needed at runtime |
| gpu-screen-recorder | 6.1+ | replay mode, the recorder half of the workflow |
| Wayland compositor | Hyprland (tested) | for the recorder hotkeys, not for Clippy itself |
| jq, libnotify | any | used by the bundled recorder scripts |
| NVIDIA GPU + driver | NVENC-capable | only for exports that re-encode (`h264_nvenc`) |

### Notes on the numbers

- **RAM is about the replay buffer, not the app.** A 300-second buffer at 1440p60 lives in RAM before it ever hits disk — that is the number that scales. Clippy itself sits comfortably under 500 MB.
- **The GPU only matters for encoding.** Recording works with NVENC or VAAPI. Exports that re-encode are hardwired to `h264_nvenc`, so on AMD or Intel only the stream-copy path works: `Original` with no trim (or a fast keyframe trim) and `Audio only`.
- **Disk is clips, not code.** The checkout is a few hundred kilobytes. Budget for the library: 1440p60 at replay quality runs roughly 1 GB per five minutes.

---

## Quick start

### From source (the tested path)

```bash
git clone https://github.com/OppaiHacker/Clippy.git
cd Clippy
cp .env.example .env              # set CLIPS_DIR, WORK_DIR and GSR_SCRIPT for your machine

docker compose up -d clippy-db    # PostgreSQL 17 on localhost:5434

uv sync                           # or: python -m venv .venv && .venv/bin/pip install -e .
(cd frontend && bun install && bun run build)

uv run uvicorn backend.app.main:app --host 127.0.0.1 --port 8723
```

Open **http://localhost:8723**.

On startup Clippy migrates the database to the latest schema, starts the watcher and scans `CLIPS_DIR` for clips it has not seen yet. **Settings → Rescan directory** or `uv run python -m backend.cli scan` runs the same scan by hand.

For frontend work, `cd frontend && bun run dev` serves the UI on http://localhost:5173 with `/api` proxied to the backend.

### Docker

```bash
cp .env.example .env              # CLIPS_DIR, WORK_DIR and GSR_SCRIPT are required here
docker compose up -d --build
```

Open **http://localhost:8723**. The image builds the frontend itself. Two limits apply inside the container:

- **No GPU.** The compose file does not pass a GPU through, so exports that re-encode (`h264_nvenc`) fail. Add an NVIDIA device reservation and the NVIDIA Container Toolkit if you need them.
- **The recorder cannot be started from the UI.** The container shares the host PID namespace, so status, save and stop reach the host's `gpu-screen-recorder`, but start has to happen on the host (hotkey or `gsr-replay start`).

---

## Recorder setup

Clippy ingests any `.mp4` that lands in `CLIPS_DIR`, so the recorder is optional. The workflow it was built for uses the two scripts in [`scripts/`](scripts):

| Script | Job |
|---|---|
| `gsr-replay` | Starts `gpu-screen-recorder` as a 300-second RAM replay buffer with four separate audio tracks, and saves clips (`save 10\|30\|60\|300`). Also backs the sidebar widget through `GSR_SCRIPT`. |
| `gsr-saved` | Runs after every save and writes a sidecar `.json` next to the clip: the focused window (the game), its title, the monitor and the apps that were playing audio. |

Install them and point Clippy at the first one:

```bash
ln -s "$PWD/scripts/gsr-replay" "$PWD/scripts/gsr-saved" ~/.local/bin/
# .env
GSR_SCRIPT=/home/you/.local/bin/gsr-replay
```

Edit the `AUDIO=(...)` block in `gsr-replay` to match your voice chat and browser (`gpu-screen-recorder --list-application-audio` lists what is playing). The script records the first monitor unless `GSR_MONITOR` names one, and saves to `CLIPS_DIR` (default `~/Videos/clips`). Hyprland does not read `.env`, so set both in the Hyprland config:

```ini
# ~/.config/hypr/hyprland.conf
env = CLIPS_DIR,/home/you/Videos/clips
env = GSR_MONITOR,DP-2

bind = ALT,       F9,  exec, ~/.local/bin/gsr-replay toggle
bind = ALT,       F10, exec, ~/.local/bin/gsr-replay save 60
bind = ALT SHIFT, F10, exec, ~/.local/bin/gsr-replay save 30
bind = ALT SUPER, F10, exec, ~/.local/bin/gsr-replay save 10
bind = ALT,       F11, exec, ~/.local/bin/gsr-replay save 300
```

A sidecar looks like this. Every field is optional, and a clip without a sidecar is ingested all the same:

```json
{
  "file": "Replay_2026-09-24_21-14-03.mp4",
  "type": "replay",
  "saved_at": "2026-09-24T21:14:03+02:00",
  "game": "steam_app_730",
  "window_title": "Counter-Strike 2",
  "monitor": "DP-2",
  "audio_apps": ["vesktop", "Zen"]
}
```

`game` becomes the clip's game (a `steam_app_<id>` class is resolved through the Steam Store API; **Tags → Window map** overrides anything else) and an auto-tag. `audio_apps` adds `discord`, `browser` or `spotify` auto-tags, and clips saved between 22:00 and 05:00 get `night-session`.

---

## Configuration

Everything is env-driven through `pydantic-settings`: set it in `.env` or in the environment.

| Variable | Default | What it is |
|---|---|---|
| `CLIPS_DIR` | `~/Videos/clips` | Where the recorder drops clips. Clips are never modified; files are only deleted when the trash is emptied. |
| `WORK_DIR` | `~/.local/share/clippy` | Thumbnails, sprites, waveforms, demuxed audio, imports and exports. |
| `GSR_SCRIPT` | `~/.local/bin/gsr-replay` | Recorder control script for the sidebar widget. Missing script = widget shows the recorder as unknown. |
| `DATABASE_URL` | `postgresql+asyncpg://clippy:clippy@localhost:5434/clippy` | Async engine for the API. |
| `SYNC_DATABASE_URL` | `postgresql+psycopg2://clippy:clippy@localhost:5434/clippy` | Watcher, worker and migrations. |

The listen address and port are `uvicorn` flags (`--host`, `--port`), not settings. Clippy has no authentication, so keep it on `127.0.0.1`.

---

## API

<details>
<summary><b>Endpoints</b> (click to expand)</summary>

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/api/clips` | List clips (`?trash=true` for the trash) |
| `GET` `PATCH` `DELETE` | `/api/clips/{id}` | Read, edit, trash (`?permanent=true` deletes the file) |
| `POST` | `/api/clips/{id}/restore` | Undo trash |
| `GET` | `/api/clips/{id}/stream` | Video, HTTP `Range` |
| `GET` | `/api/clips/{id}/audio/{stream}` | One demuxed track, HTTP `Range` (`imported_{id}` for imports) |
| `GET` | `/api/clips/{id}/thumb` · `/sprite` | Poster and scrub sprite sheet |
| `GET` | `/api/clips/{id}/waveform/{track}` | Peak data for the canvas |
| `GET` | `/api/clips/{id}/keyframes` | Keyframe timestamps |
| `GET` `PUT` | `/api/clips/{id}/mix` | The mix document |
| `POST` | `/api/clips/{id}/tags` | Tag a clip |
| `DELETE` | `/api/clips/{id}/tags/{tag_id}` | Untag a clip |
| `POST` | `/api/clips/{id}/tracks` | Import an audio file or a voiceover |
| `DELETE` | `/api/clips/{id}/tracks/{track_id}` | Drop an imported track |
| `GET` `POST` | `/api/tags` | List, create |
| `PATCH` `DELETE` | `/api/tags/{id}` | Rename, recolour, delete |
| `POST` | `/api/tags/merge` | Merge tags |
| `GET` | `/api/games` | Games in the library |
| `GET` `POST` | `/api/games/mappings` | Window class → game name overrides |
| `GET` `POST` | `/api/mix-presets` | Saved mixer presets (`DELETE /{id}` removes one) |
| `POST` | `/api/clips/{id}/export` | Queue a render |
| `GET` | `/api/exports` | Finished renders |
| `GET` | `/api/exports/{id}/download` | Download a render |
| `DELETE` | `/api/exports/{id}` | Delete a render |
| `GET` | `/api/jobs` | Job queue |
| `DELETE` | `/api/jobs/{id}` | Cancel a job |
| `GET` `POST` | `/api/recorder/*` | `status` · `start` · `stop` · `toggle` · `save/{seconds}` |
| `GET` | `/api/settings` | Paths and disk usage |
| `POST` | `/api/settings/rescan` | Rescan `CLIPS_DIR` |

Interactive docs live at **http://localhost:8723/docs**.

</details>

---

## Keyboard

<details>
<summary><b>Shortcuts</b> (click to expand)</summary>

**Anywhere**: `?` or `F1` shortcut cheat sheet · `/` search

**Library**: `Enter` open the selected clip · `Ctrl+A` select all · `Esc` clear selection · `Delete` trash (in the trash: delete for good)

**Editor**

| Key | Action | Key | Action |
|---|---|---|---|
| `Space` | play / pause | `1…9` | mute track *n* |
| `J` / `L` | −10 s / +10 s | `Shift+1…9` | solo track *n* |
| `←` / `→` | −5 s / +5 s | `M` | mute master |
| `,` / `.` | frame back / forward | `P` | loop in–out |
| `Home` / `End` | start / end | `Ctrl+S` | save mix (it also autosaves) |
| `I` / `O` | set in / out | `Ctrl+Z` | undo |
| `Shift+I` / `Shift+O` | jump to in / out | `Ctrl+Y` / `Ctrl+Shift+Z` | redo |

</details>

---

## Tests

```bash
uv run pytest tests/
```

The tests need `ffmpeg` on the `PATH` and use the `.env` configuration. File-backed tests take the first clip in `CLIPS_DIR` and pass without checking anything when it is empty. `tests/test_clippy.py::test_http_range_206` talks to a running server on port 8723 and needs at least one clip.

---

## Deliberately not here

Timeline with multiple video clips · transitions · colour grading · uploads to anything · user accounts · a cloud. It is a vault for your own clips on your own disk, and it stays that way.

---

<div align="center">
<sub>MIT · built for a single machine, shared because it might fit yours</sub>
</div>
