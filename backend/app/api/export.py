from typing import List, Optional, Dict, Any
from pathlib import Path
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.app.database import get_db
from backend.app.models.models import Export, Job, Clip, MixDocument

router = APIRouter(tags=["exports"])

EXPORT_PRESETS = {"original", "discord", "youtube", "vertical", "audio_only"}

class ExportRequest(BaseModel):
    preset: str = "original"
    mix_doc: Optional[Dict[str, Any]] = None

@router.post("/api/clips/{clip_id}/export")
async def create_export_job(clip_id: int, req: ExportRequest, db: AsyncSession = Depends(get_db)):
    clip = await db.get(Clip, clip_id)
    if not clip:
        raise HTTPException(status_code=404, detail="Clip not found")

    if req.mix_doc:
        # Update mix doc if supplied
        mix = (await db.execute(select(MixDocument).where(MixDocument.clip_id == clip_id))).scalar_one_or_none()
        if not mix:
            mix = MixDocument(clip_id=clip_id, doc=req.mix_doc)
            db.add(mix)
        else:
            mix.doc = req.mix_doc
        await db.commit()

    if req.preset not in EXPORT_PRESETS:
        raise HTTPException(status_code=400, detail=f"Unknown preset {req.preset!r}")

    job = Job(
        clip_id=clip_id,
        kind="export",
        preset=req.preset,
        state="pending",
        progress=0.0
    )
    db.add(job)
    await db.commit()
    await db.refresh(job)

    return {"status": "ok", "job_id": job.id}

@router.get("/api/exports")
async def list_exports(db: AsyncSession = Depends(get_db)):
    query = select(Export).order_by(desc(Export.created_at))
    res = await db.execute(query)
    exports = res.scalars().all()
    out = []
    for exp in exports:
        p = Path(exp.path)
        out.append({
            "id": exp.id,
            "clip_id": exp.clip_id,
            "preset": exp.preset,
            "filename": p.name,
            "path": exp.path,
            "size_bytes": exp.size_bytes,
            "duration_s": exp.duration_s,
            "created_at": exp.created_at,
            "exists": p.exists()
        })
    return out

@router.get("/api/exports/{export_id}/download")
async def download_export(export_id: int, db: AsyncSession = Depends(get_db)):
    exp = await db.get(Export, export_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Export not found")
    p = Path(exp.path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="Export file missing on disk")

    return FileResponse(
        p,
        media_type="application/octet-stream",
        filename=p.name,
        headers={"Content-Disposition": f'attachment; filename="{p.name}"'}
    )

@router.delete("/api/exports/{export_id}")
async def delete_export(export_id: int, db: AsyncSession = Depends(get_db)):
    exp = await db.get(Export, export_id)
    if not exp:
        raise HTTPException(status_code=404, detail="Export not found")
    p = Path(exp.path)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass
    await db.delete(exp)
    await db.commit()
    return {"status": "ok"}
