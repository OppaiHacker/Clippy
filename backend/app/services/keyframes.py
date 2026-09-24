import json
import subprocess
from pathlib import Path
from typing import List

def extract_keyframes(clip_path: Path) -> List[float]:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-select_streams", "v",
        "-skip_frame", "nokey",
        "-show_entries", "frame=pts_time",
        "-print_format", "json",
        str(clip_path)
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    data = json.loads(proc.stdout)
    keyframes = []
    for frame in data.get("frames", []):
        pts_time = frame.get("pts_time")
        if pts_time is not None:
            try:
                keyframes.append(round(float(pts_time), 3))
            except Exception:
                pass
    return sorted(keyframes)
