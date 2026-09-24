import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.concurrency import run_in_threadpool
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models.models import Clip, ImportedTrack, MixDocument
from backend.app.schemas.schemas import ImportedTrackResponse
from backend.app.config import settings

router = APIRouter(tags=["tracks"])

@router.post("/api/clips/{clip_id}/tracks", response_model=ImportedTrackResponse)
async def import_track(
    clip_id: int,
    file: UploadFile = File(...),
    display_name: Optional[str] = Form(None),
    origin: str = Form("file"),  # file | voiceover
    db: AsyncSession = Depends(get_db)
):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if origin not in ("file", "voiceover"):
        raise HTTPException(status_code=400, detail="origin must be file or voiceover")

    # bare file name only (no client-supplied path) + a unique prefix, so two uploads
    # with the same name do not overwrite each other
    clean_filename = Path(file.filename or "audio_track.bin").name or "audio_track.bin"
    name_stem = Path(clean_filename).stem

    if not display_name:
        display_name = name_stem if origin == "file" else "Voiceover"

    dest_source_path = settings.imports_dir / f"{clip_id}_{origin}_{uuid.uuid4().hex[:12]}_{clean_filename}"
    with open(dest_source_path, "wb") as buffer:
        await run_in_threadpool(shutil.copyfileobj, file.file, buffer)

    # Transcode preview to opus/webm for browser playback
    preview_path = settings.audio_dir / f"{clip_id}_imported_{dest_source_path.stem}.webm"
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-y",
        "-i", str(dest_source_path),
        "-c:a", "libopus",
        "-b:a", "192k",
        str(preview_path)
    ]
    # ffmpeg in a thread: inside an async handler it would block the whole server while transcoding
    res = await run_in_threadpool(subprocess.run, cmd, capture_output=True, text=True)
    if res.returncode != 0:
        dest_source_path.unlink(missing_ok=True)
        preview_path.unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=f"Failed to process audio file: {res.stderr.strip()[-300:]}")

    # Probe duration
    dur_cmd = [
        "ffprobe", "-v", "error",
        "-show_entries", "format=duration",
        "-of", "default=noprint_wrappers=1:nokey=1",
        str(dest_source_path)
    ]
    dur_res = await run_in_threadpool(subprocess.run, dur_cmd, capture_output=True, text=True)
    try:
        duration_s = float(dur_res.stdout.strip())
    except Exception:
        duration_s = clip.duration_s

    track = ImportedTrack(
        clip_id=clip_id,
        source_path=str(dest_source_path),
        preview_path=str(preview_path),
        display_name=display_name,
        origin=origin,
        duration_s=duration_s
    )
    db.add(track)
    await db.flush()

    # Update mix document to include this imported track
    mix = (await db.execute(select(MixDocument).where(MixDocument.clip_id == clip_id))).scalar_one_or_none()
    if mix and mix.doc:
        doc = dict(mix.doc)
        tracks = doc.get("tracks", [])
        tracks.append({
            "import_id": track.id,
            "gain": 1.0,
            "pan": 0,
            "mute": False,
            "offset": 0.0,
            "fade_in": 0.0,
            "fade_out": 0.0,
            "trim": None,
            "effects": []
        })
        doc["tracks"] = tracks
        mix.doc = doc

    await db.commit()
    await db.refresh(track)
    return ImportedTrackResponse.model_validate(track)

@router.delete("/api/clips/{clip_id}/tracks/{track_id}")
async def delete_imported_track(clip_id: int, track_id: int, db: AsyncSession = Depends(get_db)):
    track = await db.get(ImportedTrack, track_id)
    if not track or track.clip_id != clip_id:
        raise HTTPException(status_code=404, detail="Track not found")

    Path(track.source_path).unlink(missing_ok=True)
    Path(track.preview_path).unlink(missing_ok=True)

    # Remove from mix doc
    mix = (await db.execute(select(MixDocument).where(MixDocument.clip_id == clip_id))).scalar_one_or_none()
    if mix and mix.doc:
        doc = dict(mix.doc)
        doc["tracks"] = [t for t in doc.get("tracks", []) if t.get("import_id") != track_id]
        mix.doc = doc

    await db.delete(track)
    await db.commit()
    return {"status": "ok"}
