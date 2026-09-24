import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlsplit
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import inspect, update

from backend.app.config import settings
from backend.app.database import sync_engine, Base
from backend.app.models import *
from backend.app.queue.worker import worker
from backend.app.watcher.clip_watcher import watch_clips_directory
from backend.app.api import clips, tags, recorder, mix_presets, tracks, export, jobs, settings as settings_api

import logging

logger = logging.getLogger("clippy.main")

def _scan_existing():
    from backend.cli import scan_clips
    try:
        scan_clips()
    except Exception as e:
        logger.error(f"Startup scan failed: {e}", exc_info=True)

def _migrate():
    """Keep the schema at head: a fresh DB gets create_all + stamp, an existing one gets upgrade."""
    from alembic import command
    from alembic.config import Config
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).resolve().parents[2] / "alembic"))
    if inspect(sync_engine).has_table("alembic_version"):
        command.upgrade(cfg, "head")
        Base.metadata.create_all(bind=sync_engine)
    else:
        Base.metadata.create_all(bind=sync_engine)
        command.stamp(cfg, "head")

def _fail_orphaned_jobs():
    # a "running" job has no ffmpeg process left after a restart - without this it hangs forever
    from backend.app.database import get_sync_db
    with get_sync_db() as db:
        db.execute(
            update(Job).where(Job.state == "running")
            .values(state="error", error="Interrupted by server restart")
        )
        db.commit()

@asynccontextmanager
async def lifespan(app: FastAPI):
    _migrate()
    _fail_orphaned_jobs()

    # Start background job worker
    worker.start()

    # Trigger background scan of existing clips
    loop = asyncio.get_running_loop()
    loop.run_in_executor(None, _scan_existing)

    # Start watcher task
    watcher_stop_event = asyncio.Event()
    watcher_task = asyncio.create_task(watch_clips_directory(watcher_stop_event))

    yield

    # Teardown
    worker.stop()
    watcher_stop_event.set()
    watcher_task.cancel()
    try:
        await watcher_task
    except asyncio.CancelledError:
        pass

app = FastAPI(title="Clippy API", lifespan=lifespan)

# No CORS: the frontend is served from the same origin or through the vite proxy. On top
# of that, writes from foreign origins are rejected, because a "simple" form POST has no
# preflight and any page open in the browser could otherwise e.g. toggle the recorder.
LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}

@app.middleware("http")
async def reject_foreign_writes(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and urlsplit(origin).hostname not in LOCAL_HOSTS:
        return JSONResponse({"detail": "Forbidden origin"}, status_code=403)
    return await call_next(request)

# Include API routers
app.include_router(clips.router)
app.include_router(tags.router)
app.include_router(recorder.router)
app.include_router(mix_presets.router)
app.include_router(tracks.router)
app.include_router(export.router)
app.include_router(jobs.router)
app.include_router(settings_api.router)

# Mount frontend production build if available
frontend_dist = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
if frontend_dist.exists() and frontend_dist.is_dir():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")
