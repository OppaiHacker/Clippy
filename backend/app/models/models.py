from datetime import datetime
from typing import List, Optional
from sqlalchemy import (
    Integer, BigInteger, Float, String, Boolean, Text, DateTime,
    ForeignKey, PrimaryKeyConstraint, func, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from backend.app.database import Base

class Clip(Base):
    __tablename__ = "clips"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    path: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    saved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    game: Mapped[Optional[str]] = mapped_column(String, nullable=True, index=True)
    window_title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    monitor: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    fps: Mapped[float] = mapped_column(Float, nullable=False)
    video_codec: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    has_sidecar: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    title: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    indexed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    last_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # trash: set = clip deleted; after TRASH_RETENTION_DAYS it is purged together with its file
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True, index=True)

    # Relationships
    audio_tracks: Mapped[List["AudioTrack"]] = relationship("AudioTrack", back_populates="clip", cascade="all, delete-orphan", order_by="AudioTrack.stream_index")
    imported_tracks: Mapped[List["ImportedTrack"]] = relationship("ImportedTrack", back_populates="clip", cascade="all, delete-orphan")
    mix_document: Mapped[Optional["MixDocument"]] = relationship("MixDocument", back_populates="clip", uselist=False, cascade="all, delete-orphan")
    clip_tags: Mapped[List["ClipTag"]] = relationship("ClipTag", back_populates="clip", cascade="all, delete-orphan")
    exports: Mapped[List["Export"]] = relationship("Export", back_populates="clip", cascade="all, delete-orphan")
    jobs: Mapped[List["Job"]] = relationship("Job", back_populates="clip", cascade="all, delete-orphan")


class AudioTrack(Base):
    __tablename__ = "audio_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True)
    stream_index: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # system, app, mic, device, imported
    codec: Mapped[str] = mapped_column(String, nullable=False)
    channels: Mapped[int] = mapped_column(Integer, nullable=False)
    sample_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    demuxed_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    waveform_path: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    clip: Mapped["Clip"] = relationship("Clip", back_populates="audio_tracks")


class ImportedTrack(Base):
    __tablename__ = "imported_tracks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True)
    source_path: Mapped[str] = mapped_column(String, nullable=False)
    preview_path: Mapped[str] = mapped_column(String, nullable=False)
    display_name: Mapped[str] = mapped_column(String, nullable=False)
    origin: Mapped[str] = mapped_column(String, nullable=False)  # file | voiceover
    duration_s: Mapped[float] = mapped_column(Float, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clip: Mapped["Clip"] = relationship("Clip", back_populates="imported_tracks")


class MixDocument(Base):
    __tablename__ = "mix_documents"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id", ondelete="CASCADE"), unique=True, nullable=False, index=True)
    doc: Mapped[dict] = mapped_column(JSONB, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    clip: Mapped["Clip"] = relationship("Clip", back_populates="mix_document")


class Tag(Base):
    __tablename__ = "tags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False, index=True)
    color: Mapped[str] = mapped_column(String, default="#4da3ff", nullable=False)
    kind: Mapped[str] = mapped_column(String, default="manual", nullable=False)  # manual | auto

    clip_tags: Mapped[List["ClipTag"]] = relationship("ClipTag", back_populates="tag", cascade="all, delete-orphan")


class ClipTag(Base):
    __tablename__ = "clip_tags"

    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id", ondelete="CASCADE"), nullable=False)
    tag_id: Mapped[int] = mapped_column(Integer, ForeignKey("tags.id", ondelete="CASCADE"), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    source: Mapped[str] = mapped_column(String, default="manual", nullable=False)  # sidecar | manual

    __table_args__ = (
        PrimaryKeyConstraint("clip_id", "tag_id"),
    )

    clip: Mapped["Clip"] = relationship("Clip", back_populates="clip_tags")
    tag: Mapped["Tag"] = relationship("Tag", back_populates="clip_tags")


class MixPreset(Base):
    __tablename__ = "mix_presets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String, unique=True, nullable=False)
    doc: Mapped[dict] = mapped_column(JSONB, nullable=False)


class Export(Base):
    __tablename__ = "exports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[int] = mapped_column(Integer, ForeignKey("clips.id", ondelete="CASCADE"), nullable=False, index=True)
    job_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True)
    preset: Mapped[str] = mapped_column(String, nullable=False)
    path: Mapped[str] = mapped_column(String, nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, default=0, nullable=False)
    duration_s: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    clip: Mapped["Clip"] = relationship("Clip", back_populates="exports")


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    clip_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("clips.id", ondelete="CASCADE"), nullable=True, index=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)  # export
    preset: Mapped[Optional[str]] = mapped_column(String, nullable=True)  # export only
    state: Mapped[str] = mapped_column(String, default="pending", nullable=False, index=True)  # pending | running | done | error
    progress: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    clip: Mapped[Optional["Clip"]] = relationship("Clip", back_populates="jobs")


class WindowGameMap(Base):
    """Editable window class -> game name map (e.g. cs2 -> CS2)"""
    __tablename__ = "window_game_maps"

    window_class: Mapped[str] = mapped_column(String, primary_key=True)
    game_name: Mapped[str] = mapped_column(String, nullable=False)
