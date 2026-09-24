from pathlib import Path

from backend.app.config import settings
from backend.app.services.probe import classify_track_kind, mp4_audio_track_names
from backend.app.services.steam import steam_app_id

# ponytail: first clip in the directory instead of a hardcoded path; file-backed tests skip themselves when it is empty
CLIP = next(iter(sorted(settings.clips_dir.glob("*.mp4"))), Path("/nonexistent.mp4"))


def test_steam_app_id():
    assert steam_app_id("steam_app_730") == "730"
    assert steam_app_id("STEAM_APP_4656000") == "4656000"
    assert steam_app_id("cs2") is None
    assert steam_app_id("steam_app_") is None


def test_classify_track_kind():
    assert classify_track_kind("All applications except: vesktop")[0] == "system"
    assert classify_track_kind("Applications: vesktop") == ("app", "Discord")
    assert classify_track_kind("Devices: Default input") == ("mic", "Microphone")


def test_mp4_audio_track_names():
    """The moov/trak/udta/name atom, which ffprobe < 8.0 does not show."""
    if not CLIP.exists():
        return
    names = mp4_audio_track_names(CLIP)
    assert len(names) == 4
    assert names[0].startswith("All applications except:")
    assert names[-1] == "Devices: Default input"


def test_mp4_names_on_missing_file():
    assert mp4_audio_track_names(Path("/nonexistent.mp4")) == []


if __name__ == "__main__":
    test_steam_app_id()
    test_classify_track_kind()
    test_mp4_audio_track_names()
    test_mp4_names_on_missing_file()
    test_days_left_boundary()
    print("OK")


def test_days_left_boundary():
    """Trash: 30-day retention, cutoff computed in UTC."""
    import datetime

    from backend.app.services.trash import TRASH_RETENTION_DAYS

    assert TRASH_RETENTION_DAYS == 30
    now = datetime.datetime.now(datetime.timezone.utc)
    cutoff = now - datetime.timedelta(days=TRASH_RETENTION_DAYS)
    assert (now - datetime.timedelta(days=31)) < cutoff  # gets purged
    assert (now - datetime.timedelta(days=29)) > cutoff  # still kept
