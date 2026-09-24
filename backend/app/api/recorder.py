import subprocess
from fastapi import APIRouter, HTTPException
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
        return {"status": out, "running": is_running, "raw": out}
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
