import json
import shutil
import subprocess
import time
from types import SimpleNamespace

import pytest

from backend.app.recorder.engine import Engine
from backend.app.recorder.hotkeys import parse_combo
from backend.app.services.probe import classify_track_kind, mp4_audio_track_names
from backend.app.recorder.ring import PKT, Ring


def _pkt(pid, pusi=False, rai=False, payload=b""):
    h = bytes([0x47, (0x40 if pusi else 0) | pid >> 8, pid & 0xFF, 0x30 if rai else 0x10])
    body = (bytes([7, 0x40 if rai else 0]) + b"\xff" * 6 if rai else b"") + payload
    return h + body + b"\xff" * (PKT - len(h) - len(body))


PAT = _pkt(0, True, payload=bytes([0, 0, 0xB0, 13, 0, 1, 0xC1, 0, 0, 0, 1, 0xE1, 0x00, 0, 0, 0, 0]))
PMT = _pkt(0x100, True, payload=bytes([0, 2, 0xB0, 18, 0, 1, 0xC1, 0, 0, 0xE1, 1, 0xF0, 0, 0x1B, 0xE1, 1, 0xF0, 0, 0, 0, 0, 0]))
KEY, DELTA = _pkt(0x101, rai=True), _pkt(0x101)


def test_ring_trims_by_age_and_starts_on_keyframe():
    r = Ring(5)
    r.feed(PAT + PMT, 0)
    r.feed(DELTA, 0)  # before the first keyframe: dropped
    for t in range(10):
        r.feed(KEY + DELTA, t)
    assert r.video_pid == 0x101
    # chunk 5 (t=5) is the oldest one still needed to cover 5 s at t=9; the keyframe packet leads
    assert [t for t, _ in r.chunks] == [4, 5, 6, 7, 8, 9]
    assert all(c[0] == 0x47 and c[3] & 0x20 for _, c in r.chunks)
    snap = r.snapshot(2, now=9)
    assert snap.startswith(PAT + PMT + KEY) and len(snap) == 2 * PKT + 3 * 2 * PKT  # keyframes at 7, 8, 9
    assert len(r.snapshot(None, now=9)) == 2 * PKT + 6 * 2 * PKT
    assert len(r.snapshot(100, now=9)) == 2 * PKT + 6 * 2 * PKT  # asks for more than we have: everything


def test_ring_partial_packets():
    r = Ring(5)
    blob = PAT + PMT + KEY + DELTA
    for i in range(0, len(blob), 100):
        r.feed(blob[i:i + 100], 0)
    assert len(r.chunks) == 1 and len(r.chunks[0][1]) == 2 * PKT


def test_parse_combo():
    assert parse_combo("ALT + SHIFT + F10") == (1 | 4, 0x79)
    assert parse_combo("SUPER + CTRL + s") == (8 | 2, ord("S"))
    assert parse_combo("ALT + Prior") == (1, 0x21)
    assert parse_combo("") is None
    with pytest.raises(ValueError):
        parse_combo("HYPER + F1")
    with pytest.raises(ValueError):
        parse_combo("ALT + F99")


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_engine_saves_multitrack_clip(tmp_path):
    titles = ["All applications except: Discord.exe", "Applications: Discord.exe",
              "Applications: chrome.exe", "Devices: default_input"]
    video = ["-re", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10"]
    audio = [["-re", "-f", "lavfi", "-i", f"sine=frequency={220 * (i + 1)}:sample_rate=48000"] for i in range(4)]
    eng = Engine(inputs=(video, audio, titles))
    assert eng.status() == "stopped"
    status = eng.start(SimpleNamespace(fps=10, buffer=30))
    try:
        assert status.startswith("running (buffer 30s, 10fps -> ")
        time.sleep(4.5)
        clip = eng.save(2, tmp_path)
        again = eng.save(2, tmp_path)  # same second: must not overwrite the first clip
    finally:
        eng.stop()
    assert clip.suffix == ".mp4" and clip.exists() and not list(tmp_path.glob(".*"))
    assert again != clip and again.exists() and json.loads(again.with_suffix(".json").read_text())["file"] == again.name
    side = json.loads(clip.with_suffix(".json").read_text())
    assert side["file"] == clip.name and side["type"] == "replay" and side["monitor"] is None

    probe = json.loads(subprocess.run(
        ["ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", str(clip)],
        capture_output=True, text=True, check=True).stdout)
    streams = probe["streams"]
    assert [s["codec_type"] for s in streams] == ["video"] + ["audio"] * 4
    assert mp4_audio_track_names(clip) == titles  # what the app reads; ffprobe < 8 hides this atom
    assert 1.8 <= float(probe["format"]["duration"]) <= 3.6
    assert [classify_track_kind(t)[0] for t in titles] == ["system", "app", "app", "mic"]
    assert classify_track_kind("Applications: Discord.exe") == ("app", "Discord")
    # first frame decodes (the cut starts on a keyframe)
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(clip), "-frames:v", "1", "-f", "null", "-"], check=True)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_engine_saves_without_audio(tmp_path):
    # no clippy-audio = no audio inputs; the remux must not demand an audio stream
    eng = Engine(inputs=(["-re", "-f", "lavfi", "-i", "testsrc2=size=320x240:rate=10"], [], []))
    eng.start(SimpleNamespace(fps=10, buffer=30))
    try:
        time.sleep(2.5)
        clip = eng.save(None, tmp_path)
    finally:
        eng.stop()
    assert clip.exists()


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="needs ffmpeg")
def test_engine_restarts_ffmpeg_that_quits(monkeypatch):
    # ddagrab gives up on a resolution change or a UAC prompt; the buffer must come back by itself
    monkeypatch.setattr(Engine, "RESTART_AFTER", 0)
    eng = Engine(inputs=(["-re", "-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10:duration=1"], [], []))
    eng.start(SimpleNamespace(fps=10, buffer=30))
    first = eng.proc
    try:
        for _ in range(50):
            time.sleep(0.1)
            if eng.proc is not first and eng.running:
                break
        assert eng.proc is not first and eng.running
    finally:
        eng.stop()
    time.sleep(2.5)  # the run stopped by hand must not come back
    assert not eng.running and eng.proc is None


def test_engine_does_not_start_after_close():
    eng = Engine(inputs=(["-f", "lavfi", "-i", "testsrc2=size=64x64:rate=10"], [], []))
    eng.close()
    eng.start(SimpleNamespace(fps=10, buffer=30))
    assert eng.proc is None
