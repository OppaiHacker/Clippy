import json
from datetime import datetime
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class SidecarData:
    file: str
    type: str
    saved_at: Optional[datetime]
    game: Optional[str]
    window_title: Optional[str]
    monitor: Optional[int]
    audio_apps: List[str]

def read_sidecar(clip_path: Path) -> Optional[SidecarData]:
    """
    Looks for a .json file with the same base name next to the clip.
    A missing sidecar is not an error.
    """
    sidecar_path = clip_path.with_suffix(".json")
    if not sidecar_path.exists() or not sidecar_path.is_file():
        return None

    try:
        with open(sidecar_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        saved_at_raw = data.get("saved_at")
        saved_at = None
        if saved_at_raw:
            try:
                saved_at = datetime.fromisoformat(saved_at_raw)
            except Exception:
                pass

        return SidecarData(
            file=data.get("file", clip_path.name),
            type=data.get("type", "replay"),
            saved_at=saved_at,
            game=data.get("game"),
            window_title=data.get("window_title"),
            monitor=data.get("monitor"),
            audio_apps=data.get("audio_apps", [])
        )
    except Exception as e:
        # Never fail the whole ingest because of a broken sidecar
        print(f"Warning: failed to parse sidecar {sidecar_path}: {e}")
        return None
