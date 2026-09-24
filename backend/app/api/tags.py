from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update, delete
from backend.app.database import get_db
from backend.app.models.models import Tag, ClipTag, Clip, WindowGameMap
from backend.app.schemas.schemas import TagResponse

router = APIRouter(tags=["tags"])

class TagCreate(BaseModel):
    name: str
    color: str = "#4da3ff"
    kind: str = "manual"

class TagUpdate(BaseModel):
    name: Optional[str] = None
    color: Optional[str] = None

class TagMerge(BaseModel):
    source_tag_id: int
    target_tag_id: int

class GameMappingCreate(BaseModel):
    window_class: str
    game_name: str

@router.get("/api/tags", response_model=List[TagResponse])
async def list_tags(db: AsyncSession = Depends(get_db)):
    query = (
        select(Tag, func.count(ClipTag.clip_id).label("count"))
        .outerjoin(ClipTag, Tag.id == ClipTag.tag_id)
        .group_by(Tag.id)
        .order_by(func.count(ClipTag.clip_id).desc(), Tag.name.asc())
    )
    res = await db.execute(query)
    results = []
    for tag, count in res.all():
        results.append(TagResponse(
            id=tag.id,
            name=tag.name,
            color=tag.color,
            kind=tag.kind,
            count=count
        ))
    return results

@router.post("/api/tags", response_model=TagResponse)
async def create_tag(data: TagCreate, db: AsyncSession = Depends(get_db)):
    clean_name = data.name.strip()
    existing = await db.execute(select(Tag).where(Tag.name == clean_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Tag already exists")

    tag = Tag(name=clean_name, color=data.color, kind=data.kind)
    db.add(tag)
    await db.commit()
    await db.refresh(tag)
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, kind=tag.kind, count=0)

@router.patch("/api/tags/{tag_id}", response_model=TagResponse)
async def update_tag(tag_id: int, data: TagUpdate, db: AsyncSession = Depends(get_db)):
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    if data.name and data.name.strip() != tag.name:
        clash = await db.execute(select(Tag).where(Tag.name == data.name.strip()))
        if clash.scalar_one_or_none():
            raise HTTPException(status_code=400, detail="Tag with that name exists, use merge")
        tag.name = data.name.strip()
    if data.color:
        tag.color = data.color
    await db.commit()
    await db.refresh(tag)
    return TagResponse(id=tag.id, name=tag.name, color=tag.color, kind=tag.kind)

@router.delete("/api/tags/{tag_id}")
async def delete_tag(tag_id: int, db: AsyncSession = Depends(get_db)):
    tag = await db.get(Tag, tag_id)
    if not tag:
        raise HTTPException(status_code=404, detail="Tag not found")
    await db.delete(tag)
    await db.commit()
    return {"status": "ok"}

@router.post("/api/tags/merge")
async def merge_tags(data: TagMerge, db: AsyncSession = Depends(get_db)):
    if data.source_tag_id == data.target_tag_id:
        raise HTTPException(status_code=400, detail="Cannot merge tag into itself")

    source = await db.get(Tag, data.source_tag_id)
    target = await db.get(Tag, data.target_tag_id)
    if not source or not target:
        raise HTTPException(status_code=404, detail="Tag not found")

    # Get all clips associated with source
    source_clips = (await db.execute(select(ClipTag).where(ClipTag.tag_id == source.id))).scalars().all()
    for sc in source_clips:
        # Check if already tagged with target
        exists = (await db.execute(
            select(ClipTag).where(ClipTag.clip_id == sc.clip_id, ClipTag.tag_id == target.id)
        )).scalar_one_or_none()
        if not exists:
            db.add(ClipTag(clip_id=sc.clip_id, tag_id=target.id, confidence=sc.confidence, source="manual"))
        await db.delete(sc)

    await db.delete(source)
    await db.commit()
    return {"status": "ok"}

@router.get("/api/games")
async def list_games(db: AsyncSession = Depends(get_db)):
    query = (
        select(Clip.game, func.count(Clip.id))
        .where(Clip.game.isnot(None))
        .group_by(Clip.game)
        .order_by(func.count(Clip.id).desc())
    )
    res = await db.execute(query)
    return [{"game": g, "count": c} for g, c in res.all()]

@router.get("/api/games/mappings")
async def list_game_mappings(db: AsyncSession = Depends(get_db)):
    res = await db.execute(select(WindowGameMap))
    return [{"window_class": m.window_class, "game_name": m.game_name} for m in res.scalars().all()]

@router.post("/api/games/mappings")
async def save_game_mapping(data: GameMappingCreate, db: AsyncSession = Depends(get_db)):
    mapping = await db.get(WindowGameMap, data.window_class)
    if not mapping:
        mapping = WindowGameMap(window_class=data.window_class, game_name=data.game_name)
        db.add(mapping)
    else:
        mapping.game_name = data.game_name
    await db.commit()
    return {"status": "ok"}
