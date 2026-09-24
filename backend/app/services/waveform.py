import json
import os
import subprocess
from pathlib import Path
import numpy as np
from backend.app.config import settings
from backend.app.services.artifacts import is_fresh, tmp_path

def generate_waveform(demuxed_path: Path, clip_id: int, stream_index: int, target_points: int = 2000) -> Path:
    out_path = settings.waveforms_dir / f"{clip_id}_track_{stream_index}.json"
    if is_fresh(out_path, demuxed_path):
        return out_path

    # Decode audio to mono 8kHz raw signed 16-bit PCM to stdout
    cmd = [
        "ffmpeg",
        "-v", "error",
        "-i", str(demuxed_path),
        "-ac", "1",
        "-ar", "8000",
        "-f", "s16le",
        "-"
    ]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    raw_data = proc.stdout

    samples = np.frombuffer(raw_data, dtype=np.int16)
    total_samples = len(samples)

    if total_samples == 0:
        peaks = [[0.0, 0.0] for _ in range(target_points)]
    else:
        # Divide into target_points chunks
        # Convert to float in range [-1.0, 1.0]
        step = total_samples / target_points
        peaks = []
        for i in range(target_points):
            start = int(i * step)
            end = int((i + 1) * step)
            if start >= total_samples:
                peaks.append([0.0, 0.0])
                continue
            chunk = samples[start:max(end, start + 1)]
            min_val = float(np.min(chunk)) / 32768.0
            max_val = float(np.max(chunk)) / 32768.0
            peaks.append([round(min_val, 4), round(max_val, 4)])

    tmp = tmp_path(out_path)
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"points": target_points, "peaks": peaks}, f)
    os.replace(tmp, out_path)
    return out_path
