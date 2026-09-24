from datetime import datetime
from typing import List, Optional, Any, Dict
from pydantic import BaseModel, ConfigDict

class TagBase(BaseModel):
    name: str
    color: str = "#4da3ff"
    kind: str = "manual"

class TagResponse(TagBase):
    id: int
    count: Optional[int] = 0
    model_config = ConfigDict(from_attributes=True)

class ClipTagItem(BaseModel):
    id: int
    name: str
    color: str
    confidence: float
    source: str

class AudioTrackResponse(BaseModel):
    id: int
    stream_index: int
    name: str
    display_name: str
    kind: str
    codec: str
    channels: int
    sample_rate: int
    duration_s: float
    demuxed_path: Optional[str] = None
    waveform_path: Optional[str] = None
    model_config = ConfigDict(from_attributes=True)

class ImportedTrackResponse(BaseModel):
    id: int
    source_path: str
    preview_path: str
    display_name: str
    origin: str
    duration_s: float
    created_at: datetime
    model_config = ConfigDict(from_attributes=True)

class ClipResponse(BaseModel):
    id: int
    path: str
    filename: str
    saved_at: Optional[datetime]
    game: Optional[str]
    window_title: Optional[str]
    monitor: Optional[int]
    duration_s: float
    width: int
    height: int
    fps: float
    video_codec: str
    size_bytes: int
    has_sidecar: bool
    starred: bool
    title: Optional[str]
    notes: Optional[str]
    ingested_at: datetime
    last_opened_at: Optional[datetime]
    deleted_at: Optional[datetime] = None
    thumb_version: int = 0
    tags: List[ClipTagItem] = []
    audio_tracks: List[AudioTrackResponse] = []
    imported_tracks: List[ImportedTrackResponse] = []
    mix_document: Optional[Dict[str, Any]] = None

    model_config = ConfigDict(from_attributes=True)

class ClipUpdate(BaseModel):
    title: Optional[str] = None
    notes: Optional[str] = None
    starred: Optional[bool] = None
    game: Optional[str] = None

class MixDocumentUpdate(BaseModel):
    doc: Dict[str, Any]

class MixPresetCreate(BaseModel):
    name: str
    doc: Dict[str, Any]

class MixPresetResponse(BaseModel):
    id: int
    name: str
    doc: Dict[str, Any]
    model_config = ConfigDict(from_attributes=True)

class JobResponse(BaseModel):
    id: int
    clip_id: Optional[int]
    kind: str
    preset: Optional[str] = None
    state: str
    progress: float
    error: Optional[str]
    created_at: datetime
    finished_at: Optional[datetime]
    model_config = ConfigDict(from_attributes=True)
