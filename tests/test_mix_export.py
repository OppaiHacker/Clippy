"""The export command must match what the preview plays."""
from pathlib import Path

from backend.app.services.mix_builder import build_ffmpeg_export_command


def _cmd(tracks, preset="original", **doc):
    mix = {"speed": 1.0, "master": {"gain": 1.0, "limiter": True}, "tracks": tracks, **doc}
    return " ".join(build_ffmpeg_export_command(
        Path("/c.mp4"), [{"id": 7, "source_path": "/imp.wav"}], mix, preset, Path("/o.mp4"),
        total_clip_duration=60.0,
    ))


def test_solo_limits_export_to_soloed_tracks():
    cmd = _cmd([{"stream_index": 1}, {"stream_index": 4, "solo": True}])
    assert "[0:4]" in cmd and "[0:1]" not in cmd


def test_offsets_both_directions():
    cmd = _cmd([{"stream_index": 1, "offset": 1.5}, {"stream_index": 4, "offset": -2}])
    assert "adelay=delays=1500:all=1" in cmd
    assert "atrim=start=2.000" in cmd


def test_trim_fades_and_speed_use_export_window():
    cmd = _cmd([{"stream_index": 1, "fade_out": 1.0}], speed=2.0,
               trim={"start": 10.0, "end": 20.0}, video_fade={"in": 0.5, "out": 0})
    assert "afade=t=out:st=19.000" in cmd       # end of the trim, not end of the clip
    assert "fade=t=in:st=10.000" in cmd
    assert cmd.index("fade=t=in") < cmd.index("setpts")  # fade in source time
    assert "-ss 5.000 -to 10.000" in cmd        # after the 2x speed-up


def test_audio_only_keeps_imported_inputs():
    cmd = _cmd([{"import_id": 7}], preset="audio_only")
    assert "-i /imp.wav" in cmd and "[1:a:0]" in cmd


def test_vertical_is_really_vertical():
    assert "crop=ih*9/16:ih,scale=1080:1920" in _cmd([{"stream_index": 1}], preset="vertical")


def test_original_copies_video_unless_it_must_cut():
    assert "-c:v copy" in _cmd([{"stream_index": 1}])
    assert "-c:v copy" not in _cmd([{"stream_index": 1}], trim={"start": 2.0, "end": 5.0})
