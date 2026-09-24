from pathlib import Path
from backend.app.config import settings
from backend.app.services.artifacts import is_fresh, ffmpeg_atomic

def demux_track(clip_path: Path, clip_id: int, stream_index: int, audio_index: int) -> Path:
    """
    Demux without re-encoding:
    ffmpeg -v error -y -i clip.mp4 -map 0:a:$audio_index -c:a copy track_$i.webm
    """
    out_path = settings.audio_dir / f"{clip_id}_track_{stream_index}.webm"
    if is_fresh(out_path, clip_path):
        return out_path
    return ffmpeg_atomic(["-i", str(clip_path), "-map", f"0:a:{audio_index}", "-c:a", "copy"], out_path)
