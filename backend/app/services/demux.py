from pathlib import Path
from backend.app.config import settings
from backend.app.services.artifacts import is_fresh, ffmpeg_atomic

def demux_track(clip_path: Path, clip_id: int, stream_index: int, audio_index: int, codec: str = "opus") -> Path:
    """
    Demux one audio track to webm for the browser. Opus/Vorbis are copied as they are,
    anything else (AAC from the Windows recorder or other tools) is encoded to Opus.
    """
    out_path = settings.audio_dir / f"{clip_id}_track_{stream_index}.webm"
    if is_fresh(out_path, clip_path):
        return out_path
    audio = ["-c:a", "copy"] if codec in ("opus", "vorbis") else ["-c:a", "libopus", "-b:a", "192k"]
    return ffmpeg_atomic(["-i", str(clip_path), "-map", f"0:a:{audio_index}", *audio], out_path)
