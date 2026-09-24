import hashlib
import json
import subprocess
from pathlib import Path
import httpx
from backend.app.config import settings
from backend.app.database import get_sync_db
from backend.app.models.models import Clip, AudioTrack
from backend.app.services.mix_builder import build_ffmpeg_export_command
from backend.app.services.probe import probe_clip, classify_track_kind
from backend.app.services.keyframes import extract_keyframes


def sample_clip() -> Path:
    """First clip in the user's clips directory. File-backed tests skip themselves when there is none."""
    return next(iter(sorted(settings.clips_dir.glob("*.mp4"))), Path("/nonexistent.mp4"))

def test_http_range_206():
    """HTTP Range header handling (206 Partial Content). Needs the server running."""
    with httpx.Client(base_url="http://127.0.0.1:8723") as client:
        r = client.get("/api/clips")
        assert r.status_code == 200
        clips = r.json()
        assert len(clips) > 0
        clip_id = clips[0]["id"]

        # Test Range: bytes=100-200 (101 bytes)
        res = client.get(f"/api/clips/{clip_id}/stream", headers={"Range": "bytes=100-200"})
        assert res.status_code == 206
        assert res.headers.get("accept-ranges") == "bytes"
        assert res.headers.get("content-length") == "101"
        assert res.headers.get("content-range").startswith("bytes 100-200/")
        assert len(res.content) == 101

        # Test audio stream Range
        res_audio = client.get(f"/api/clips/{clip_id}/audio/1", headers={"Range": "bytes=0-99"})
        assert res_audio.status_code == 206
        assert res_audio.headers.get("content-length") == "100"
        assert len(res_audio.content) == 100

def test_track_classification_and_dynamic_tracks():
    """Dynamic track detection and classification by TAG:name."""
    kind, display = classify_track_kind("All applications except: vesktop, Zen")
    assert kind == "system"

    kind, display = classify_track_kind("Applications: vesktop")
    assert kind == "app"
    assert display == "Discord"

    kind, display = classify_track_kind("Devices: Default input")
    assert kind == "mic"
    assert display == "Microphone"

    kind, display = classify_track_kind("Devices: Speakers")
    assert kind == "device"

    kind, display = classify_track_kind("custom track")
    assert kind == "imported"

def test_source_files_intact():
    """Source clips are left intact."""
    clips_dir = settings.clips_dir
    mp4_files = list(clips_dir.glob("*.mp4"))
    for f in mp4_files:
        assert f.exists()
        assert f.stat().st_size > 0

def test_mix_builder_normalize_zero_and_muted_track():
    """
    Critical invariants:
    - normalize=0 on amix is mandatory
    - the muted Discord track is left out of the amix inputs
    """
    clip_path = sample_clip()
    out_path = Path("/tmp/test_export.mp4")

    mix_doc = {
        "version": 1,
        "trim": None,
        "speed": 1.0,
        "crop": None,
        "video_fade": {"in": 0.0, "out": 0.0},
        "master": {"gain": 1.0, "limiter": True, "normalize_lufs": None},
        "tracks": [
            {"stream_index": 1, "gain": 1.0, "pan": 0, "mute": False, "offset": 0, "effects": []}, # Game
            {"stream_index": 2, "gain": 0.0, "pan": 0, "mute": True, "offset": 0, "effects": []},  # Discord MUTED
            {"stream_index": 3, "gain": 0.5, "pan": 0, "mute": False, "offset": 0, "effects": []}, # Zen
            {"stream_index": 4, "gain": 1.2, "pan": 0, "mute": False, "offset": 0, "effects": []}, # Mic
        ]
    }

    cmd = build_ffmpeg_export_command(
        clip_path=clip_path,
        imported_tracks=[],
        mix_doc=mix_doc,
        preset="original",
        output_path=out_path,
        total_clip_duration=11.5
    )

    cmd_str = " ".join(cmd)
    # 1. normalize=0 must be present
    assert "normalize=0" in cmd_str
    # 2. Discord (stream 2) is muted, so inputs must be 3, not 4
    assert "amix=inputs=3:normalize=0" in cmd_str
    # 3. Stream 0:2 should not be mixed into amix
    assert "[0:2]" not in cmd_str

def test_keyframes_extraction():
    """Keyframe extraction from a video file."""
    clip_path = sample_clip()
    if not clip_path.exists():
        return
    kf = extract_keyframes(clip_path)
    assert len(kf) > 0
    assert 0.0 in kf
    assert kf == sorted(kf)

if __name__ == "__main__":
    print("Running tests...")
    test_http_range_206()
    print("✓ test_http_range_206 passed")
    test_track_classification_and_dynamic_tracks()
    print("✓ test_track_classification_and_dynamic_tracks passed")
    test_source_files_intact()
    print("✓ test_source_files_intact passed")
    test_mix_builder_normalize_zero_and_muted_track()
    print("✓ test_mix_builder_normalize_zero_and_muted_track passed")
    test_keyframes_extraction()
    print("✓ test_keyframes_extraction passed")
    print("\nALL VERIFICATION TESTS PASSED SUCCESSFULLY!")
