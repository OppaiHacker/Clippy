import json
import struct
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

@dataclass
class AudioStreamInfo:
    stream_index: int     # e.g. 1, 2, 3, 4 (absolute stream index in file)
    audio_index: int      # 0, 1, 2, 3 (index among audio streams)
    name: str             # original TAG:name
    display_name: str     # humanized display name
    kind: str             # system, app, mic, device, imported
    codec: str            # e.g. opus
    channels: int         # 2
    sample_rate: int      # 48000
    duration_s: float     # duration in seconds

@dataclass
class VideoStreamInfo:
    width: int
    height: int
    fps: float
    video_codec: str
    duration_s: float

@dataclass
class ClipProbeResult:
    path: Path
    filename: str
    size_bytes: int
    duration_s: float
    video: VideoStreamInfo
    audio_tracks: List[AudioStreamInfo]

def classify_track_kind(tag_name: str) -> tuple[str, str]:
    """
    Track kind from the TAG:name prefix:
    All applications except: -> kind='system', e.g. "Game + system"
    Applications:           -> kind='app', e.g. "vesktop" -> "Discord"
    Devices: + input        -> kind='mic', e.g. "Microphone"
    Devices: + anything else -> kind='device', e.g. "System audio"
    added track             -> kind='imported'
    """
    raw_name = tag_name.strip()
    if raw_name.startswith("All applications except:"):
        return "system", "Game + system"
    
    if raw_name.startswith("Applications:"):
        app_name = raw_name.replace("Applications:", "").strip()
        # humanize common apps
        if app_name.lower() == "vesktop" or app_name.lower() == "discord":
            return "app", "Discord"
        return "app", app_name
    
    if raw_name.startswith("Devices:"):
        dev_name = raw_name.replace("Devices:", "").strip()
        if "input" in dev_name.lower():
            return "mic", "Microphone"
        return "device", dev_name

    return "imported", raw_name if raw_name else "Audio track"

def _iter_boxes(f, end: int):
    """Iterates over ISO-BMFF boxes: (type, payload_offset, box_end)."""
    while f.tell() < end:
        start = f.tell()
        header = f.read(8)
        if len(header) < 8:
            return
        size, raw_type = struct.unpack(">I4s", header)
        if size == 1:
            size = struct.unpack(">Q", f.read(8))[0]
        elif size == 0:
            size = end - start
        if size < 8 or start + size > end:
            return
        yield raw_type.decode("latin1", "replace"), f.tell(), start + size
        f.seek(start + size)

def mp4_audio_track_names(path: Path) -> List[Optional[str]]:
    """
    Audio track names from the moov/trak/udta/name atoms, in audio track order.
    gpu-screen-recorder writes "Applications: vesktop" etc. there, and ffprobe
    older than 8.0 does not show this atom at all.
    """
    names: List[Optional[str]] = []
    try:
        with open(path, "rb") as f:
            f.seek(0, 2)
            file_end = f.tell()
            f.seek(0)
            for box, body, end in _iter_boxes(f, file_end):
                if box != "moov":
                    continue
                f.seek(body)
                for trak, trak_body, trak_end in _iter_boxes(f, end):
                    if trak != "trak":
                        continue
                    f.seek(trak_body)
                    is_audio = False
                    name = None
                    for inner, inner_body, inner_end in _iter_boxes(f, trak_end):
                        if inner == "mdia":
                            f.seek(inner_body)
                            for mdia, mdia_body, mdia_end in _iter_boxes(f, inner_end):
                                if mdia == "hdlr":
                                    f.seek(mdia_body + 8)
                                    is_audio = f.read(4) == b"soun"
                        elif inner == "udta":
                            f.seek(inner_body)
                            for udta, udta_body, udta_end in _iter_boxes(f, inner_end):
                                if udta == "name":
                                    f.seek(udta_body)
                                    raw = f.read(udta_end - udta_body).split(b"\x00")[0]
                                    name = raw.decode("utf-8", "replace").strip() or None
                    if is_audio:
                        names.append(name)
    except Exception as e:
        print(f"Warning: failed to read mp4 track names from {path}: {e}")
        return []
    return names

def probe_clip(clip_path: Path) -> ClipProbeResult:
    cmd = [
        "ffprobe",
        "-v", "error",
        "-show_format",
        "-show_streams",
        "-print_format", "json",
        str(clip_path)
    ]
    res = subprocess.run(cmd, capture_output=True, text=True, check=True)
    data = json.loads(res.stdout)

    format_info = data.get("format", {})
    duration_s = float(format_info.get("duration", 0.0))
    size_bytes = int(format_info.get("size", clip_path.stat().st_size if clip_path.exists() else 0))

    video_info = None
    audio_tracks: List[AudioStreamInfo] = []
    audio_counter = 0
    box_names = mp4_audio_track_names(clip_path)

    for stream in data.get("streams", []):
        codec_type = stream.get("codec_type")
        if codec_type == "video" and video_info is None:
            width = int(stream.get("width", 2560))
            height = int(stream.get("height", 1440))
            r_frame_rate = stream.get("r_frame_rate", "60/1")
            try:
                num, den = r_frame_rate.split("/")
                fps = round(float(num) / float(den), 2)
            except Exception:
                fps = 60.0
            video_codec = stream.get("codec_name", "h264")
            v_dur = float(stream.get("duration", duration_s))
            video_info = VideoStreamInfo(
                width=width,
                height=height,
                fps=fps,
                video_codec=video_codec,
                duration_s=v_dur
            )
        elif codec_type == "audio":
            stream_idx = int(stream.get("index", 0))
            tags = stream.get("tags", {})
            name = tags.get("name") or tags.get("NAME") or tags.get("title")
            if not name and audio_counter < len(box_names):
                name = box_names[audio_counter]
            if not name:
                name = f"Track {audio_counter + 1}"
            kind, display_name = classify_track_kind(name)
            codec = stream.get("codec_name", "opus")
            channels = int(stream.get("channels", 2))
            sample_rate = int(stream.get("sample_rate", 48000))
            a_dur = float(stream.get("duration", duration_s))

            audio_tracks.append(AudioStreamInfo(
                stream_index=stream_idx,
                audio_index=audio_counter,
                name=name,
                display_name=display_name,
                kind=kind,
                codec=codec,
                channels=channels,
                sample_rate=sample_rate,
                duration_s=a_dur
            ))
            audio_counter += 1

    if video_info is None:
        raise ValueError(f"No video stream found in {clip_path}")

    return ClipProbeResult(
        path=clip_path,
        filename=clip_path.name,
        size_bytes=size_bytes,
        duration_s=duration_s,
        video=video_info,
        audio_tracks=audio_tracks
    )
