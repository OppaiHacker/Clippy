import datetime
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.app.config import settings
from backend.app.models.models import Clip
from backend.app.services.artifacts import purge_artifacts

logger = logging.getLogger("clippy.trash")

TRASH_RETENTION_DAYS = 30

def purge_clip_files(clip_id: int, clip_path: str) -> bool:
    """
    Deletes the source file, the sidecar and the artifacts (demuxes, waveforms, thumbnails).
    False = the file is still there, so keep the DB row and try again later.
    """
    source = Path(clip_path)
    for path in (source, source.with_suffix(".json")):
        try:
            path.unlink(missing_ok=True)
        except OSError as e:
            logger.error(f"Could not delete {path}: {e}")
            return False

    purge_artifacts(clip_id)
    return True

def trash_missing(db: Session) -> int:
    """
    A clip whose file is gone from disk goes to the trash instead of lingering in
    the library as a ghost. Trash, not DELETE: title, tags and mix survive in case
    the file comes back (e.g. after a drive is remounted) - then a restore is enough.
    """
    # an unmounted drive would look like "every file vanished"
    if not settings.clips_dir.is_dir() or not any(settings.clips_dir.iterdir()):
        return 0
    now = datetime.datetime.now(datetime.timezone.utc)
    trashed = 0
    for clip in db.execute(select(Clip).where(Clip.deleted_at.is_(None))).scalars():
        if not Path(clip.path).exists():
            clip.deleted_at = now
            trashed += 1
    db.commit()
    if trashed:
        logger.info(f"Trash: {trashed} clip(s) whose file vanished from disk")
    return trashed

def purge_expired(db: Session, retention_days: int = TRASH_RETENTION_DAYS) -> int:
    """Permanently deletes clips that have been in the trash longer than retention_days."""
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=retention_days)
    expired = db.execute(
        select(Clip).where(Clip.deleted_at.is_not(None), Clip.deleted_at < cutoff)
    ).scalars().all()

    purged = 0
    for clip in expired:
        try:
            if not purge_clip_files(clip.id, clip.path):
                continue
            db.delete(clip)
            db.commit()
            purged += 1
        except Exception as e:
            db.rollback()
            logger.error(f"Failed to purge clip {clip.id}: {e}")

    if purged:
        logger.info(f"Trash: purged {purged} clip(s) older than {retention_days} days")
    return purged
