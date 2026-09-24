import logging
import os
import subprocess
from pathlib import Path

from backend.app.config import settings

logger = logging.getLogger("clippy.artifacts")


def is_fresh(out_path: Path, source: Path) -> bool:
    """An artifact is usable when it is non-empty and not older than its source."""
    try:
        st = out_path.stat()
        return st.st_size > 0 and st.st_mtime >= source.stat().st_mtime
    except OSError:
        return False


def tmp_path(out_path: Path) -> Path:
    # the extension stays last, because ffmpeg picks the muxer from it
    return out_path.with_name(f".tmp-{os.getpid()}-{out_path.name}")


def ffmpeg_atomic(args: list[str], out_path: Path) -> Path:
    """
    ffmpeg writes to a temp file, then renames it. An interrupted write leaves no
    half-written file, and an old file (even one owned by someone else, e.g. root)
    is replaced, not overwritten in place.
    """
    tmp = tmp_path(out_path)
    try:
        res = subprocess.run(["ffmpeg", "-v", "error", "-y", *args, str(tmp)], capture_output=True, text=True)
        if res.returncode != 0:
            raise RuntimeError(f"ffmpeg -> {out_path.name} failed ({res.returncode}): {res.stderr.strip()[-400:]}")
        os.replace(tmp, out_path)
    finally:
        tmp.unlink(missing_ok=True)
    return out_path


def purge_artifacts(clip_id: int) -> None:
    """
    Deletes everything generated for a given clip_id. Called for a new DB row:
    ids repeat after a database rebuild, and without this a new clip got the
    thumbnail, sprite and audio of the previous clip with the same id.
    """
    for directory, pattern in (
        (settings.audio_dir, f"{clip_id}_track_*"),
        (settings.audio_dir, f"{clip_id}_imported_*"),
        (settings.waveforms_dir, f"{clip_id}_track_*"),
        (settings.thumbs_dir, f"{clip_id}_thumb.*"),
        (settings.thumbs_dir, f"{clip_id}_sprite.*"),
        (settings.imports_dir, f"{clip_id}_file_*"),
        (settings.imports_dir, f"{clip_id}_voiceover_*"),
    ):
        for artifact in directory.glob(pattern):
            try:
                artifact.unlink()
            except OSError as e:
                logger.warning(f"Could not remove {artifact}: {e}")
