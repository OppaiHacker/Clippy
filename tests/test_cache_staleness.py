"""The thumbnail/audio cache is keyed by clip_id, which is not stable across database
rebuilds. An old cache file with the same id must be overwritten, not returned."""
import os
import subprocess
from pathlib import Path

from backend.app.config import settings
from backend.app.services.thumbs import generate_thumbnail


def _make_clip(path: Path, color: str) -> None:
    subprocess.run(
        ["ffmpeg", "-v", "error", "-y", "-f", "lavfi", "-i",
         f"color=c={color}:s=320x240:d=1", "-pix_fmt", "yuv420p", str(path)],
        check=True,
    )


def test_stale_thumb_is_regenerated(tmp_path):
    clip_id = 999999
    stale = settings.thumbs_dir / f"{clip_id}_thumb.jpg"
    clip = tmp_path / "new.mp4"
    _make_clip(clip, "red")

    # cache written before the clip existed = leftover from a previous clip with this id
    stale.write_bytes(b"x" * 1024)
    old = clip.stat().st_mtime - 3600
    os.utime(stale, (old, old))

    try:
        out = generate_thumbnail(clip, clip_id, 1.0)
        assert out.read_bytes()[:2] == b"\xff\xd8", "stale cache returned instead of a new thumbnail"
    finally:
        stale.unlink(missing_ok=True)


def test_fresh_thumb_is_reused(tmp_path):
    clip_id = 999998
    fresh = settings.thumbs_dir / f"{clip_id}_thumb.jpg"
    clip = tmp_path / "new.mp4"
    _make_clip(clip, "blue")

    fresh.write_bytes(b"x" * 1024)
    try:
        assert generate_thumbnail(clip, clip_id, 1.0).read_bytes() == b"x" * 1024
    finally:
        fresh.unlink(missing_ok=True)


def test_unwritable_stale_thumb_is_replaced(tmp_path):
    """Old artifacts can be owned by root (an earlier backend ran in docker): ffmpeg could
    not overwrite them and ingesting a new clip failed. Writing via rename replaces them."""
    clip_id = 999997
    stale = settings.thumbs_dir / f"{clip_id}_thumb.jpg"
    clip = tmp_path / "new.mp4"
    _make_clip(clip, "green")
    stale.write_bytes(b"x" * 1024)
    old = clip.stat().st_mtime - 3600
    os.utime(stale, (old, old))
    stale.chmod(0o444)
    try:
        assert generate_thumbnail(clip, clip_id, 1.0).read_bytes()[:2] == b"\xff\xd8"
    finally:
        stale.unlink(missing_ok=True)


def test_new_clip_id_purges_foreign_artifacts():
    """A new DB row = the id may have belonged to another clip: its files must go,
    even when they are newer than the source (an mtime check would not catch that)."""
    from backend.app.services.artifacts import purge_artifacts
    clip_id = 999996
    files = [
        settings.thumbs_dir / f"{clip_id}_thumb.jpg",
        settings.thumbs_dir / f"{clip_id}_sprite.jpg",
        settings.audio_dir / f"{clip_id}_track_4.webm",
        settings.waveforms_dir / f"{clip_id}_track_4.json",
    ]
    keep = settings.thumbs_dir / f"{clip_id}0_thumb.jpg"
    for f in files + [keep]:
        f.write_bytes(b"x")
    try:
        purge_artifacts(clip_id)
        assert not any(f.exists() for f in files)
        assert keep.exists(), "purge must not touch clip 9999960"
    finally:
        for f in files + [keep]:
            f.unlink(missing_ok=True)
