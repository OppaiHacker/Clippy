import re
import shutil
import subprocess
from pathlib import Path
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field, field_validator
from backend.app.config import settings

router = APIRouter(prefix="/api/recorder", tags=["recorder"])

@router.get("/status")
def get_recorder_status():
    script = settings.gsr_script
    if not script.exists():
        return {"status": "unknown", "running": False, "raw": f"Script {script} not found"}

    try:
        res = subprocess.run([str(script), "status"], capture_output=True, text=True, timeout=3)
        out = res.stdout.strip()
        is_running = "running" in out.lower()
        # "running (buffer 300s, 180fps -> …)": the running process, which may predate a config change
        buf, fps = re.search(r"(\d+)s\b", out), re.search(r"(\d+)fps", out)
        return {"status": out, "running": is_running, "raw": out,
                "buffer": int(buf.group(1)) if buf else None, "fps": int(fps.group(1)) if fps else None}
    except Exception as e:
        return {"status": "error", "running": False, "raw": str(e)}

@router.post("/toggle")
def toggle_recorder():
    script = settings.gsr_script
    if not script.exists():
        return {"status": "error", "error": "Script not found"}
    try:
        subprocess.run([str(script), "toggle"], capture_output=True, text=True, timeout=5)
        return get_recorder_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post("/start")
def start_recorder():
    script = settings.gsr_script
    if not script.exists():
        return {"status": "error", "error": "Script not found"}
    try:
        subprocess.run([str(script), "start"], capture_output=True, text=True, timeout=5)
        return get_recorder_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post("/stop")
def stop_recorder():
    script = settings.gsr_script
    if not script.exists():
        return {"status": "error", "error": "Script not found"}
    try:
        subprocess.run([str(script), "stop"], capture_output=True, text=True, timeout=5)
        return get_recorder_status()
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post("/save/{seconds}")
def save_replay(seconds: int):
    """Dump the last N seconds of the RAM buffer to a file (same as the ALT+F10 bind in Hyprland)."""
    if seconds not in (10, 30, 60, 300):
        raise HTTPException(status_code=400, detail="seconds must be 10, 30, 60 or 300")
    script = settings.gsr_script
    if not script.exists():
        raise HTTPException(status_code=500, detail=f"Script {script} not found")
    try:
        res = subprocess.run([str(script), "save", str(seconds)], capture_output=True, text=True, timeout=10)
    except subprocess.TimeoutExpired:
        raise HTTPException(status_code=504, detail="gsr-replay save timed out")
    if res.returncode != 0:
        raise HTTPException(status_code=500, detail=res.stderr.strip() or "gsr-replay save failed")
    return {"saved": seconds}


# One file holds the recorder settings: gsr-replay sources it (FPS, BUFFER) and the Hyprland
# config reads the BIND_* lines, so the hotkeys and the widget always agree.
RECORDER_CONF = Path.home() / ".config/clippy/recorder.env"
BIND_ACTIONS = ("toggle", "save_10", "save_30", "save_60", "save_full")
# "ALT + SHIFT + F10"; the charset also keeps the value safe inside a sourced shell file
KEY_COMBO = r"^$|^[A-Za-z0-9_:]+( \+ [A-Za-z0-9_:]+)*$"


class RecorderConfig(BaseModel):
    fps: int = Field(180, ge=10, le=500)
    buffer: int = Field(300, ge=10, le=1800)
    binds: dict[str, str] = {
        "toggle": "ALT + F9",
        "save_10": "ALT + SUPER + F10",
        "save_30": "ALT + SHIFT + F10",
        "save_60": "ALT + F10",
        "save_full": "ALT + F11",
    }

    @field_validator("binds")
    @classmethod
    def check_binds(cls, v: dict[str, str]) -> dict[str, str]:
        if set(v) != set(BIND_ACTIONS):
            raise ValueError(f"binds must have exactly {', '.join(BIND_ACTIONS)}")
        for action, combo in v.items():
            if not re.match(KEY_COMBO, combo):
                raise ValueError(f"{action}: use keys joined by ' + ', e.g. 'ALT + F10'")
        return v


def read_config() -> RecorderConfig:
    cfg = RecorderConfig()
    if not RECORDER_CONF.exists():
        return cfg
    raw = {}
    for line in RECORDER_CONF.read_text().splitlines():
        key, sep, val = line.partition("=")
        if sep:
            raw[key.strip()] = val.strip().strip('"')
    binds = {a: raw.get(f"BIND_{a.upper()}", cfg.binds[a]) for a in BIND_ACTIONS}
    return RecorderConfig(fps=int(raw.get("FPS", cfg.fps)), buffer=int(raw.get("BUFFER", cfg.buffer)), binds=binds)


@router.get("/config")
def get_recorder_config():
    return read_config()


@router.put("/config")
def put_recorder_config(cfg: RecorderConfig):
    RECORDER_CONF.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"FPS={cfg.fps}", f"BUFFER={cfg.buffer}"]
    lines += [f'BIND_{a.upper()}="{cfg.binds[a]}"' for a in BIND_ACTIONS]
    RECORDER_CONF.write_text("# written by Clippy (sidebar → recorder settings)\n" + "\n".join(lines) + "\n")
    # new hotkeys; no Hyprland (e.g. inside the container) = binds apply on the next login
    if shutil.which("hyprctl"):
        subprocess.run(["hyprctl", "reload"], capture_output=True, timeout=5)
    status = get_recorder_status()
    if status["running"]:
        # new fps/buffer only apply to a fresh process; this drops what is in the buffer now
        subprocess.run([str(settings.gsr_script), "restart"], capture_output=True, text=True, timeout=20)
        status = get_recorder_status()
    return {"config": cfg, "recorder": status}
