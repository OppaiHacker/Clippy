import asyncio
import logging
import time
from pathlib import Path
from watchfiles import awatch, Change

from backend.app.config import settings
from backend.app.database import get_sync_db
from backend.app.services.ingest import ingest_clip
from backend.app.services.trash import trash_missing

logger = logging.getLogger("clippy.watcher")

async def wait_for_file_settled(file_path: Path, debounce_seconds: float = 2.0, max_wait: float = 120.0) -> bool:
    """
    The recorder writes the file gradually. Wait until its size stays unchanged for 2 s.
    """
    start = time.time()
    last_size = -1
    stable_since = None

    while time.time() - start < max_wait:
        if not file_path.exists():
            return False
        try:
            current_size = file_path.stat().st_size
        except OSError:
            current_size = -1

        if current_size > 0 and current_size == last_size:
            if stable_since is None:
                stable_since = time.time()
            elif time.time() - stable_since >= debounce_seconds:
                return True
        else:
            stable_since = None
            last_size = current_size

        await asyncio.sleep(0.5)

    return False

def _clip_for(path: Path) -> Path | None:
    """The mp4 to (re)ingest for a changed file: the clip itself or the clip next to a sidecar."""
    suffix = path.suffix.lower()
    if suffix == ".mp4":
        return path
    if suffix == ".json":
        clip = path.with_suffix(".mp4")
        return clip if clip.exists() else None
    return None

async def _handle_batch(changes: set) -> None:
    loop = asyncio.get_running_loop()
    to_ingest: set[Path] = set()
    vanished = False
    for change, path_str in changes:
        path = Path(path_str)
        if path.name.startswith("."):
            continue
        if change == Change.deleted:
            vanished |= path.suffix.lower() == ".mp4"
            continue
        clip = _clip_for(path)
        if clip:
            to_ingest.add(clip)

    # gsr-saved writes the sidecar after the clip, so clip + sidecar = one ingest
    for clip in sorted(to_ingest):
        logger.info(f"Detected new or modified clip: {clip.name}. Waiting for write to finish...")
        if not await wait_for_file_settled(clip):
            logger.warning(f"{clip.name} never settled, skipping")
            continue
        try:
            await loop.run_in_executor(None, _run_sync_ingest, clip)
            logger.info(f"Successfully ingested {clip.name}")
        except Exception as e:
            logger.error(f"Error ingesting {clip.name}: {e}", exc_info=True)

    if vanished:
        await loop.run_in_executor(None, _run_sync_trash_missing)

async def watch_clips_directory(stop_event: asyncio.Event):
    clips_dir = settings.clips_dir
    # the watcher must not die for good because of an unmounted drive or a single exception
    while not stop_event.is_set():
        if not clips_dir.is_dir():
            logger.warning(f"Clips directory {clips_dir} does not exist yet. Watcher waiting...")
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=10)
            except asyncio.TimeoutError:
                pass
            continue

        logger.info(f"Starting clip watcher on {clips_dir}")
        try:
            async for changes in awatch(clips_dir, stop_event=stop_event, recursive=False):
                await _handle_batch(changes)
        except asyncio.CancelledError:
            logger.info("Clip watcher task cancelled")
            return
        except Exception as e:
            logger.error(f"Clip watcher crashed, restarting: {e}", exc_info=True)
            await asyncio.sleep(5)

def _run_sync_ingest(clip_path: Path):
    with get_sync_db() as db:
        ingest_clip(clip_path, db)

def _run_sync_trash_missing():
    with get_sync_db() as db:
        trash_missing(db)
