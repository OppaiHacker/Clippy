import re
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.database import get_sync_db
from backend.app.models.models import Clip, Job, Export
from backend.app.services.mix_builder import build_ffmpeg_export_command, export_window

# Global dictionary of running processes for cancellation
RUNNING_PROCESSES: Dict[int, subprocess.Popen] = {}

def cancel_job(job_id: int) -> bool:
    proc = RUNNING_PROCESSES.get(job_id)
    if proc:
        try:
            proc.terminate()
            time.sleep(0.2)
            if proc.poll() is None:
                proc.kill()
            return True
        except Exception:
            pass
    return False

def run_export_job(job_id: int):
    with get_sync_db() as db:
        job = db.get(Job, job_id)
        if not job or job.state != "pending":
            return

        job.state = "running"
        job.progress = 0.05
        db.commit()

        clip = db.get(Clip, job.clip_id)
        if not clip:
            job.state = "error"
            job.error = "Clip not found"
            db.commit()
            return

        # Fetch mix doc
        mix_doc = clip.mix_document.doc if clip.mix_document else {}
        imported = [
            {"id": imp.id, "source_path": imp.source_path}
            for imp in clip.imported_tracks
        ]

        preset = job.preset or "original"
        # game name comes straight from the window/Steam: strip "/" and other junk from the file name
        game = re.sub(r"[^\w.-]+", "_", clip.game or "Clip").strip("_") or "Clip"
        stamp = clip.saved_at.strftime('%Y%m%d_%H%M%S') if clip.saved_at else 'clip'
        ext = "ogg" if preset == "audio_only" else "mp4"
        output_name = f"{game}_{stamp}_{preset}_{job_id}.{ext}"
        tmp_output_path = settings.exports_dir / f"tmp_{output_name}"
        final_output_path = settings.exports_dir / output_name

        cmd = build_ffmpeg_export_command(
            clip_path=Path(clip.path),
            imported_tracks=imported,
            mix_doc=mix_doc,
            preset=preset,
            output_path=tmp_output_path,
            total_clip_duration=clip.duration_s
        )

        # Add progress pipe
        cmd.extend(["-progress", "pipe:1"])

        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1
            )
            RUNNING_PROCESSES[job_id] = proc

            t0, t1 = export_window(mix_doc, clip.duration_s)
            speed = float(mix_doc.get("speed") or 1.0) or 1.0
            out_duration = (t1 - t0) / speed
            total_dur_us = out_duration * 1_000_000

            for line in proc.stdout:
                line = line.strip()
                if line.startswith("out_time_us="):
                    try:
                        us = int(line.split("=")[1])
                        if total_dur_us > 0:
                            prog = min(0.99, max(0.05, us / total_dur_us))
                            job.progress = round(prog, 2)
                            db.commit()
                    except Exception:
                        pass
                elif line.startswith("progress=") and line.endswith("end"):
                    job.progress = 1.0
                    db.commit()

            proc.wait()
            RUNNING_PROCESSES.pop(job_id, None)

            db.refresh(job)
            if job.state == "cancelled":
                tmp_output_path.unlink(missing_ok=True)
                return

            if proc.returncode == 0 and tmp_output_path.exists():
                tmp_output_path.rename(final_output_path)
                job.state = "done"
                job.progress = 1.0
                job.finished_at = datetime.now(timezone.utc)

                export_entry = Export(
                    clip_id=clip.id,
                    job_id=job.id,
                    preset=preset,
                    path=str(final_output_path),
                    size_bytes=final_output_path.stat().st_size,
                    duration_s=out_duration
                )
                db.add(export_entry)
                db.commit()
            else:
                stderr = proc.stderr.read() if proc.stderr else "FFmpeg execution failed"
                job.state = "error"
                job.error = stderr[-500:] if stderr else "Unknown error"
                job.finished_at = datetime.now(timezone.utc)
                db.commit()
                if tmp_output_path.exists():
                    tmp_output_path.unlink()

        except Exception as e:
            RUNNING_PROCESSES.pop(job_id, None)
            job.state = "error"
            job.error = str(e)
            job.finished_at = datetime.now(timezone.utc)
            db.commit()
            if tmp_output_path.exists():
                tmp_output_path.unlink()
