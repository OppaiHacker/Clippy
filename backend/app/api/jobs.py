from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, desc
from backend.app.database import get_db
from backend.app.models.models import Job
from backend.app.schemas.schemas import JobResponse
from backend.app.services.export_runner import cancel_job

router = APIRouter(prefix="/api/jobs", tags=["jobs"])

@router.get("", response_model=List[JobResponse])
async def list_jobs(limit: int = 50, db: AsyncSession = Depends(get_db)):
    query = select(Job).order_by(desc(Job.created_at)).limit(limit)
    res = await db.execute(query)
    return res.scalars().all()

@router.delete("/{job_id}")
async def abort_job(job_id: int, db: AsyncSession = Depends(get_db)):
    job = await db.get(Job, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job.state in ("pending", "running"):
        cancel_job(job_id)
        job.state = "cancelled"
        job.error = "Cancelled by user"
        await db.commit()

    return {"status": "ok", "job_id": job_id}
