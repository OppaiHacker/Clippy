import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, desc, asc, func
from sqlalchemy.orm import selectinload

from backend.app.database import get_db
from backend.app.models.models import Clip, AudioTrack, MixDocument, Tag, ClipTag, ImportedTrack
from backend.app.schemas.schemas import ClipResponse, ClipUpdate, MixDocumentUpdate, ClipTagItem, AudioTrackResponse, ImportedTrackResponse
from backend.app.services.streaming import send_partial_file
from backend.app.services.keyframes import extract_keyframes
from backend.app.services.trash import TRASH_RETENTION_DAYS, purge_clip_files
from backend.app.config import settings

router = APIRouter(prefix="/api/clips", tags=["clips"])

# always revalidate (ETag), because files behind the same URL can change
NO_CACHE = {"Cache-Control": "no-cache"}

def _thumb_version(clip_id: int) -> int:
    # for the thumbnail URL (?v=...): after a regeneration the browser must not show the cached old one
    try:
        return int((settings.thumbs_dir / f"{clip_id}_sprite.jpg").stat().st_mtime)
    except OSError:
        return 0

def serialize_clip(clip: Clip) -> ClipResponse:
    tags_list = []
    for ct in clip.clip_tags:
        if ct.tag:
            tags_list.append(ClipTagItem(
                id=ct.tag.id,
                name=ct.tag.name,
                color=ct.tag.color,
                confidence=ct.confidence,
                source=ct.source
            ))

    mix_doc = clip.mix_document.doc if clip.mix_document else None

    return ClipResponse(
        id=clip.id,
        path=clip.path,
        filename=clip.filename,
        saved_at=clip.saved_at,
        game=clip.game,
        window_title=clip.window_title,
        monitor=clip.monitor,
        duration_s=clip.duration_s,
        width=clip.width,
        height=clip.height,
        fps=clip.fps,
        video_codec=clip.video_codec,
        size_bytes=clip.size_bytes,
        has_sidecar=clip.has_sidecar,
        starred=clip.starred,
        title=clip.title,
        notes=clip.notes,
        ingested_at=clip.ingested_at,
        last_opened_at=clip.last_opened_at,
        deleted_at=clip.deleted_at,
        thumb_version=_thumb_version(clip.id),
        tags=tags_list,
        audio_tracks=[AudioTrackResponse.model_validate(t) for t in clip.audio_tracks],
        imported_tracks=[ImportedTrackResponse.model_validate(t) for t in clip.imported_tracks],
        mix_document=mix_doc
    )

@router.get("", response_model=List[ClipResponse])
async def list_clips(
    q: Optional[str] = None,
    game: Optional[str] = None,
    tags: Optional[str] = None,
    tag_mode: str = "or",  # and | or
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    min_dur: Optional[float] = None,
    max_dur: Optional[float] = None,
    has_mic: Optional[bool] = None,
    starred: Optional[bool] = None,
    trash: bool = False,
    sort: str = "date_desc",
    limit: int = 5000,  # the library filters client-side: a limit of 100 cut off older clips
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    query = select(Clip).options(
        selectinload(Clip.audio_tracks),
        selectinload(Clip.imported_tracks),
        selectinload(Clip.mix_document),
        selectinload(Clip.clip_tags).selectinload(ClipTag.tag)
    )

    conditions = [Clip.deleted_at.is_not(None) if trash else Clip.deleted_at.is_(None)]

    if q:
        search_pattern = f"%{q.strip()}%"
        query = query.outerjoin(Clip.clip_tags).outerjoin(ClipTag.tag)
        conditions.append(or_(
            Clip.filename.ilike(search_pattern),
            Clip.title.ilike(search_pattern),
            Clip.notes.ilike(search_pattern),
            Clip.game.ilike(search_pattern),
            Tag.name.ilike(search_pattern)
        ))

    if game:
        conditions.append(Clip.game == game)

    if starred is not None:
        conditions.append(Clip.starred == starred)

    if from_date:
        conditions.append(Clip.saved_at >= from_date)

    if to_date:
        conditions.append(Clip.saved_at <= to_date)

    if min_dur is not None:
        conditions.append(Clip.duration_s >= min_dur)

    if max_dur is not None:
        conditions.append(Clip.duration_s <= max_dur)

    if has_mic is not None:
        # Check if clip has an audio track with kind='mic'
        mic_subquery = select(AudioTrack.clip_id).where(AudioTrack.kind == "mic")
        if has_mic:
            conditions.append(Clip.id.in_(mic_subquery))
        else:
            conditions.append(~Clip.id.in_(mic_subquery))

    if tags:
        tag_names = [t.strip() for t in tags.split(",") if t.strip()]
        if tag_names:
            if tag_mode.lower() == "and":
                for tag_name in tag_names:
                    tag_sub = select(ClipTag.clip_id).join(Tag).where(Tag.name.ilike(tag_name))
                    conditions.append(Clip.id.in_(tag_sub))
            else:
                tag_sub = select(ClipTag.clip_id).join(Tag).where(Tag.name.in_(tag_names))
                conditions.append(Clip.id.in_(tag_sub))

    if conditions:
        query = query.where(and_(*conditions))

    # Distinct because of joins
    query = query.distinct()

    # Sorting
    if sort == "date_asc":
        query = query.order_by(asc(Clip.saved_at))
    elif sort == "dur_desc":
        query = query.order_by(desc(Clip.duration_s))
    elif sort == "dur_asc":
        query = query.order_by(asc(Clip.duration_s))
    elif sort == "size_desc":
        query = query.order_by(desc(Clip.size_bytes))
    elif sort == "last_opened":
        query = query.order_by(desc(Clip.last_opened_at.nulls_last()), desc(Clip.saved_at))
    elif trash:
        query = query.order_by(desc(Clip.deleted_at))
    else:  # date_desc
        query = query.order_by(desc(Clip.saved_at))

    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    clips = result.scalars().all()

    return [serialize_clip(c) for c in clips]

@router.get("/{clip_id}", response_model=ClipResponse)
async def get_clip(clip_id: int, db: AsyncSession = Depends(get_db)):
    query = select(Clip).options(
        selectinload(Clip.audio_tracks),
        selectinload(Clip.imported_tracks),
        selectinload(Clip.mix_document),
        selectinload(Clip.clip_tags).selectinload(ClipTag.tag)
    ).where(Clip.id == clip_id)

    # populate_existing: without it an object already in the identity map (e.g. loaded
    # by db.get in update/restore) misses the eager loads, and serialization
    # tries a lazy load in an async session -> MissingGreenlet
    result = await db.execute(query.execution_options(populate_existing=True))
    clip = result.scalar_one_or_none()
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.last_opened_at = datetime.now(timezone.utc)
    await db.commit()

    return serialize_clip(clip)

@router.patch("/{clip_id}", response_model=ClipResponse)
async def update_clip(clip_id: int, update: ClipUpdate, db: AsyncSession = Depends(get_db)):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if update.title is not None:
        clip.title = update.title
    if update.notes is not None:
        clip.notes = update.notes
    if update.starred is not None:
        clip.starred = update.starred
    if update.game is not None:
        clip.game = update.game

    await db.commit()
    return await get_clip(clip_id, db)

@router.delete("/{clip_id}")
async def delete_clip(clip_id: int, permanent: bool = False, db: AsyncSession = Depends(get_db)):
    """
    Moves to the trash by default. Deleting the row alone is not enough: the file
    stays on disk and the next directory scan would ingest the clip again, so the
    delete is soft and only emptying the trash removes the file.
    """
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if permanent:
        if not purge_clip_files(clip.id, clip.path):
            raise HTTPException(status_code=500, detail="Failed to delete source file")
        await db.delete(clip)
        await db.commit()
        return {"status": "ok", "clip_id": clip_id, "permanent": True}

    if clip.deleted_at is None:
        clip.deleted_at = datetime.now(timezone.utc)
        await db.commit()

    return {
        "status": "ok",
        "clip_id": clip_id,
        "permanent": False,
        "deleted_at": clip.deleted_at,
        "purge_after_days": TRASH_RETENTION_DAYS,
    }

@router.post("/{clip_id}/restore", response_model=ClipResponse)
async def restore_clip(clip_id: int, db: AsyncSession = Depends(get_db)):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    clip.deleted_at = None
    await db.commit()
    return await get_clip(clip_id, db)

@router.get("/{clip_id}/stream")
async def stream_video(clip_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    return send_partial_file(Path(clip.path), request, "video/mp4")

@router.get("/{clip_id}/audio/imported_{import_id}")
async def stream_imported_track(clip_id: int, import_id: int, request: Request, db: AsyncSession = Depends(get_db)):
    track = await db.get(ImportedTrack, import_id)
    if not track or track.clip_id != clip_id:
        raise HTTPException(status_code=404, detail="Imported track not found")
    return send_partial_file(Path(track.preview_path), request, "audio/webm")

@router.get("/{clip_id}/audio/{stream_index}")
async def stream_audio_track(clip_id: int, stream_index: int, request: Request, db: AsyncSession = Depends(get_db)):
    query = select(AudioTrack).where(AudioTrack.clip_id == clip_id, AudioTrack.stream_index == stream_index)
    res = await db.execute(query)
    track = res.scalar_one_or_none()
    if not track or not track.demuxed_path:
        raise HTTPException(status_code=404, detail="Audio track not found or not demuxed")
    return send_partial_file(Path(track.demuxed_path), request, "audio/webm")

@router.get("/{clip_id}/thumb")
async def get_clip_thumb(clip_id: int):
    thumb_path = settings.thumbs_dir / f"{clip_id}_thumb.jpg"
    if not thumb_path.exists():
        raise HTTPException(status_code=404, detail="Thumbnail not found")
    return FileResponse(thumb_path, media_type="image/jpeg", headers=NO_CACHE)

@router.get("/{clip_id}/sprite")
async def get_clip_sprite(clip_id: int):
    sprite_path = settings.thumbs_dir / f"{clip_id}_sprite.jpg"
    if not sprite_path.exists():
        raise HTTPException(status_code=404, detail="Sprite sheet not found")
    return FileResponse(sprite_path, media_type="image/jpeg", headers=NO_CACHE)

@router.get("/{clip_id}/waveform/{track_id}")
async def get_track_waveform(clip_id: int, track_id: int, db: AsyncSession = Depends(get_db)):
    track = await db.get(AudioTrack, track_id)
    if not track or not track.waveform_path or not Path(track.waveform_path).exists():
        raise HTTPException(status_code=404, detail="Waveform not found")
    with open(track.waveform_path, "r", encoding="utf-8") as f:
        return json.load(f)

@router.get("/{clip_id}/keyframes")
async def get_clip_keyframes(clip_id: int, db: AsyncSession = Depends(get_db)):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")
    if not Path(clip.path).exists():
        raise HTTPException(status_code=404, detail="Clip file missing on disk")
    # ffprobe over the whole file takes seconds: run it in a thread, not on the event loop
    keyframes = await run_in_threadpool(extract_keyframes, Path(clip.path))
    return {"clip_id": clip_id, "keyframes": keyframes}

@router.get("/{clip_id}/mix")
async def get_mix_document(clip_id: int, db: AsyncSession = Depends(get_db)):
    query = select(MixDocument).where(MixDocument.clip_id == clip_id)
    res = await db.execute(query)
    mix = res.scalar_one_or_none()
    if not mix:
        raise HTTPException(status_code=404, detail="Mix document not found")
    return mix.doc

@router.put("/{clip_id}/mix")
async def update_mix_document(clip_id: int, update: MixDocumentUpdate, db: AsyncSession = Depends(get_db)):
    query = select(MixDocument).where(MixDocument.clip_id == clip_id)
    res = await db.execute(query)
    mix = res.scalar_one_or_none()
    if not mix:
        mix = MixDocument(clip_id=clip_id, doc=update.doc)
        db.add(mix)
    else:
        mix.doc = update.doc
    await db.commit()
    return {"status": "ok", "doc": mix.doc}

@router.post("/{clip_id}/tags")
async def add_tag_to_clip(clip_id: int, tag_name: str = Query(...), db: AsyncSession = Depends(get_db)):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    tag_res = await db.execute(select(Tag).where(Tag.name == tag_name.strip()))
    tag = tag_res.scalar_one_or_none()
    if not tag:
        tag = Tag(name=tag_name.strip(), kind="manual", color="#4da3ff")
        db.add(tag)
        await db.flush()

    ct_res = await db.execute(select(ClipTag).where(ClipTag.clip_id == clip_id, ClipTag.tag_id == tag.id))
    ct = ct_res.scalar_one_or_none()
    if not ct:
        ct = ClipTag(clip_id=clip_id, tag_id=tag.id, source="manual", confidence=1.0)
        db.add(ct)
        await db.commit()

    return await get_clip(clip_id, db)

@router.delete("/{clip_id}/tags/{tag_id}")
async def remove_tag_from_clip(clip_id: int, tag_id: int, db: AsyncSession = Depends(get_db)):
    ct_res = await db.execute(select(ClipTag).where(ClipTag.clip_id == clip_id, ClipTag.tag_id == tag_id))
    ct = ct_res.scalar_one_or_none()
    if ct:
        await db.delete(ct)
        await db.commit()
    return {"status": "ok"}
