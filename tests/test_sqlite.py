"""The Windows build runs on SQLite: schema, UTC datetimes, JSON docs and cascades must survive it."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import Session

from backend.app.database import Base, _sqlite_pragmas
from backend.app.models.models import Clip, MixDocument


def test_sqlite_roundtrip(tmp_path):
    engine = create_engine(f"sqlite:///{(tmp_path / 'clippy.db').as_posix()}")
    event.listen(engine, "connect", _sqlite_pragmas)
    Base.metadata.create_all(engine)

    deleted = datetime(2026, 10, 1, 14, 0, tzinfo=timezone(timedelta(hours=2)))
    with Session(engine) as db:
        clip = Clip(path="/c/a.mp4", filename="a.mp4", duration_s=10, width=1920, height=1080,
                    fps=60, video_codec="h264", size_bytes=1, deleted_at=deleted)
        clip.mix_document = MixDocument(doc={"tracks": [{"gain": 0.5}]})
        db.add(clip)
        db.commit()

    with Session(engine) as db:
        clip = db.scalars(select(Clip)).one()
        # stored as UTC, comes back aware, comparable with now(timezone.utc)
        assert clip.deleted_at == deleted and clip.deleted_at.tzinfo is not None
        assert clip.ingested_at.tzinfo is not None
        assert clip.mix_document.doc == {"tracks": [{"gain": 0.5}]}
        # the trash purge filters in SQL against an aware cutoff
        cutoff = datetime(2026, 10, 1, 12, 30, tzinfo=timezone.utc)
        assert db.scalars(select(Clip).where(Clip.deleted_at < cutoff)).all() == [clip]
        assert db.scalars(select(Clip).where(Clip.filename.ilike("A.MP4"))).all() == [clip]

        db.execute(Clip.__table__.delete())
        db.commit()
        # ON DELETE CASCADE needs PRAGMA foreign_keys
        assert db.scalars(select(MixDocument)).all() == []
