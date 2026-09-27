from pathlib import Path
from backend.app.config import settings
from backend.app.services.artifacts import is_fresh, ffmpeg_atomic

def generate_thumbnail(clip_path: Path, clip_id: int, duration_s: float) -> Path:
    out_path = settings.thumbs_dir / f"{clip_id}_thumb.jpg"
    if is_fresh(out_path, clip_path):
        return out_path

    seek_time = max(0.5, duration_s / 2.0)
    return ffmpeg_atomic(
        ["-ss", str(seek_time), "-i", str(clip_path), "-frames:v", "1", "-q:v", "2", "-update", "1"],
        out_path,
    )

def generate_sprite(clip_path: Path, clip_id: int, duration_s: float) -> Path:
    out_path = settings.thumbs_dir / f"{clip_id}_sprite.jpg"
    if is_fresh(out_path, clip_path):
        return out_path

    dur = max(duration_s, 1.0)
    # fps=40/dur takes 40 evenly distributed frames, scales them to 480px wide, and packs into 8x5 grid.
    # 480px keeps a 250-500px card sharp on a HiDPI screen; 160px looked pixelated.
    vf = f"fps=40/{dur},scale=480:-2:flags=lanczos,tile=8x5"
    return ffmpeg_atomic(
        ["-i", str(clip_path), "-vf", vf, "-frames:v", "1", "-q:v", "3", "-update", "1"],
        out_path,
    )
