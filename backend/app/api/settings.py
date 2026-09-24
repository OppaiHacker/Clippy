import shutil
import asyncio
from pathlib import Path
from fastapi import APIRouter, BackgroundTasks
from backend.app.config import settings
from backend.app.database import get_sync_db
from backend.cli import scan_clips

router = APIRouter(prefix="/api/settings", tags=["settings"])

def get_dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total

@router.get("")
def get_system_settings():
    clips_exists = settings.clips_dir.exists()
    free_bytes = 0
    total_bytes = 0
    if clips_exists:
        stat = shutil.disk_usage(settings.clips_dir)
        free_bytes = stat.free
        total_bytes = stat.total

    return {
        "clips_dir": str(settings.clips_dir),
        "work_dir": str(settings.work_dir),
        "clips_exists": clips_exists,
        "disk_free_gb": round(free_bytes / (1024**3), 2),
        "disk_total_gb": round(total_bytes / (1024**3), 2),
        "audio_size_mb": round(get_dir_size(settings.audio_dir) / (1024**2), 2),
        "thumbs_size_mb": round(get_dir_size(settings.thumbs_dir) / (1024**2), 2),
        "waveforms_size_mb": round(get_dir_size(settings.waveforms_dir) / (1024**2), 2),
        "exports_size_mb": round(get_dir_size(settings.exports_dir) / (1024**2), 2),
        "imports_size_mb": round(get_dir_size(settings.imports_dir) / (1024**2), 2),
    }

@router.post("/rescan")
def trigger_rescan(background_tasks: BackgroundTasks):
    background_tasks.add_task(scan_clips)
    return {"status": "ok", "message": "Scan started in background"}
