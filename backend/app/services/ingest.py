import datetime
import logging
from pathlib import Path
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from backend.app.models.models import (
    Clip, AudioTrack, MixDocument, Tag, ClipTag, WindowGameMap
)
from backend.app.services.probe import probe_clip
from backend.app.services.sidecar import read_sidecar
from backend.app.services.demux import demux_track
from backend.app.services.thumbs import generate_thumbnail, generate_sprite
from backend.app.services.waveform import generate_waveform
from backend.app.services.steam import steam_app_id, fetch_steam_name
from backend.app.services.artifacts import purge_artifacts

logger = logging.getLogger("clippy.ingest")

def map_game_name(db: Session, raw_class: Optional[str]) -> Optional[str]:
    if not raw_class:
        return None
    mapping = db.execute(
        select(WindowGameMap).where(WindowGameMap.window_class == raw_class)
    ).scalar_one_or_none()
    if mapping:
        return mapping.game_name
    
    # steam_app_730 -> "Counter-Strike 2" (once from the API, then cached in the DB)
    app_id = steam_app_id(raw_class)
    if app_id:
        name = fetch_steam_name(app_id)
        if name:
            db.add(WindowGameMap(window_class=raw_class, game_name=name))
            db.flush()
            return name
        return raw_class

    # Common default game mappings
    clean = raw_class.lower()
    if clean == "cs2":
        return "CS2"
    if clean == "kitty" or clean == "alacritty":
        return "Terminal"
    if clean == "zen" or clean == "zen-alpha":
        return "Zen"
    if clean == "vesktop" or clean == "discord":
        return "Discord"
    return raw_class

def get_or_create_tag(db: Session, tag_name: str, kind: str = "auto", color: str = "#4da3ff") -> Tag:
    tag = db.execute(select(Tag).where(Tag.name == tag_name)).scalar_one_or_none()
    if not tag:
        tag = Tag(name=tag_name, kind=kind, color=color)
        db.add(tag)
        db.flush()
    return tag

def add_clip_tag(db: Session, clip_id: int, tag_id: int, source: str = "sidecar", confidence: float = 1.0):
    existing = db.execute(
        select(ClipTag).where(ClipTag.clip_id == clip_id, ClipTag.tag_id == tag_id)
    ).scalar_one_or_none()
    if not existing:
        db.add(ClipTag(clip_id=clip_id, tag_id=tag_id, source=source, confidence=confidence))

def ingest_clip(clip_path: Path, db: Session) -> Clip:
    probe = probe_clip(clip_path)
    sidecar = read_sidecar(clip_path)

    saved_at = None
    if sidecar and sidecar.saved_at:
        saved_at = sidecar.saved_at
    else:
        mtime = clip_path.stat().st_mtime
        saved_at = datetime.datetime.fromtimestamp(mtime, tz=datetime.timezone.utc)

    raw_game = sidecar.game if sidecar else None
    game_name = map_game_name(db, raw_game)
    window_title = sidecar.window_title if sidecar else None
    monitor = sidecar.monitor if sidecar else None

    # Check if clip exists
    clip = db.execute(select(Clip).where(Clip.path == str(clip_path))).scalar_one_or_none()
    if clip and clip.deleted_at is not None:
        # in the trash: a scan does not resurrect it, only emptying the trash or a restore does
        return clip
    if not clip:
        clip = Clip(
            path=str(clip_path),
            filename=clip_path.name,
            saved_at=saved_at,
            game=game_name,
            window_title=window_title,
            monitor=monitor,
            duration_s=probe.duration_s,
            width=probe.video.width,
            height=probe.video.height,
            fps=probe.video.fps,
            video_codec=probe.video.video_codec,
            size_bytes=probe.size_bytes,
            has_sidecar=bool(sidecar is not None),
            starred=False,
        )
        db.add(clip)
        db.flush()
        # a fresh id may have belonged to another clip before a DB rebuild: drop its files
        purge_artifacts(clip.id)
    else:
        clip.filename = clip_path.name
        clip.saved_at = saved_at
        if game_name:
            clip.game = game_name
        clip.window_title = window_title
        clip.monitor = monitor
        clip.duration_s = probe.duration_s
        clip.width = probe.video.width
        clip.height = probe.video.height
        clip.fps = probe.video.fps
        clip.video_codec = probe.video.video_codec
        clip.size_bytes = probe.size_bytes
        clip.has_sidecar = bool(sidecar is not None)
        db.flush()

    # Audio tracks
    existing_tracks = {t.stream_index: t for t in clip.audio_tracks}
    current_tracks = []
    
    for audio_info in probe.audio_tracks:
        track = existing_tracks.get(audio_info.stream_index)
        if not track:
            track = AudioTrack(
                clip_id=clip.id,
                stream_index=audio_info.stream_index,
                name=audio_info.name,
                display_name=audio_info.display_name,
                kind=audio_info.kind,
                codec=audio_info.codec,
                channels=audio_info.channels,
                sample_rate=audio_info.sample_rate,
                duration_s=audio_info.duration_s,
            )
            db.add(track)
            db.flush()
        else:
            track.name = audio_info.name
            track.display_name = audio_info.display_name
            track.kind = audio_info.kind
            track.codec = audio_info.codec
            track.channels = audio_info.channels
            track.sample_rate = audio_info.sample_rate
            track.duration_s = audio_info.duration_s
            db.flush()

        current_tracks.append(track)

        # one broken track must not block the whole clip
        try:
            demux_file = demux_track(clip_path, clip.id, audio_info.stream_index, audio_info.audio_index)
            track.demuxed_path = str(demux_file)
        except Exception as e:
            track.demuxed_path = None
            track.waveform_path = None
            logger.error(f"Demux failed for clip {clip.id} track {audio_info.stream_index}: {e}")
            continue

        try:
            track.waveform_path = str(generate_waveform(demux_file, clip.id, audio_info.stream_index))
        except Exception as e:
            track.waveform_path = None
            logger.error(f"Waveform failed for clip {clip.id} track {audio_info.stream_index}: {e}")

    # Step 5: Thumbnail and Sprite
    for generate in (generate_thumbnail, generate_sprite):
        try:
            generate(clip_path, clip.id, probe.duration_s)
        except Exception as e:
            logger.error(f"{generate.__name__} failed for clip {clip.id}: {e}")

    # Step 8: Default Mix Document
    if not clip.mix_document:
        doc = {
            "version": 1,
            "trim": None,
            "speed": 1.0,
            "crop": None,
            "video_fade": {"in": 0.0, "out": 0.0},
            "master": {"gain": 1.0, "limiter": True, "normalize_lufs": None},
            "tracks": [
                {
                    "stream_index": t.stream_index,
                    "gain": 1.0,
                    "pan": 0,
                    "mute": False,
                    "offset": 0.0,
                    "fade_in": 0.0,
                    "fade_out": 0.0,
                    "trim": None,
                    "effects": []
                }
                for t in current_tracks
            ]
        }
        mix_doc = MixDocument(clip_id=clip.id, doc=doc)
        db.add(mix_doc)

    # Auto-tagging from sidecar
    if sidecar:
        if game_name:
            tag = get_or_create_tag(db, game_name, kind="auto", color="#4da3ff")
            add_clip_tag(db, clip.id, tag.id, source="sidecar")
        for app in sidecar.audio_apps:
            clean_app = app.strip().lower()
            if clean_app in ["vesktop", "discord"]:
                tag = get_or_create_tag(db, "discord", kind="auto", color="#a78bfa")
                add_clip_tag(db, clip.id, tag.id, source="sidecar")
            elif clean_app in ["zen", "firefox", "chrome"]:
                tag = get_or_create_tag(db, "browser", kind="auto", color="#3ddc97")
                add_clip_tag(db, clip.id, tag.id, source="sidecar")
            elif clean_app in ["spotify"]:
                tag = get_or_create_tag(db, "spotify", kind="auto", color="#1db954")
                add_clip_tag(db, clip.id, tag.id, source="sidecar")
        
        # Check night session (22:00 to 05:00)
        if saved_at:
            h = saved_at.hour
            if h >= 22 or h < 5:
                tag = get_or_create_tag(db, "night-session", kind="auto", color="#ffb454")
                add_clip_tag(db, clip.id, tag.id, source="sidecar")

    db.commit()
    db.refresh(clip)
    return clip
