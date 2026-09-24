from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from backend.app.database import get_db
from backend.app.models.models import MixPreset
from backend.app.schemas.schemas import MixPresetCreate, MixPresetResponse

router = APIRouter(prefix="/api/mix-presets", tags=["mix-presets"])

@router.get("", response_model=List[MixPresetResponse])
async def list_presets(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(MixPreset).order_by(MixPreset.name))
    return res.scalars().all()

@router.post("", response_model=MixPresetResponse)
async def create_preset(data: MixPresetCreate, db: AsyncSession = Depends(get_db)):
    existing = await db.execute(select(MixPreset).where(MixPreset.name == data.name.strip()))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Preset name already exists")
    preset = MixPreset(name=data.name.strip(), doc=data.doc)
    db.add(preset)
    await db.commit()
    await db.refresh(preset)
    return preset

@router.delete("/{preset_id}")
async def delete_preset(preset_id: int, db: AsyncSession = Depends(get_db)):
    preset = await db.get(MixPreset, preset_id)
    if not preset:
        raise HTTPException(status_code=404, detail="Preset not found")
    await db.delete(preset)
    await db.commit()
    return {"status": "ok"}
