export type TrackKind = 'system' | 'app' | 'mic' | 'device' | 'imported';

export interface ClipTag {
  id: number;
  name: string;
  color: string;
  confidence: number;
  source: string;
}

export interface AudioTrack {
  id: number;
  stream_index: number;
  name: string;
  display_name: string;
  kind: TrackKind;
  codec: string;
  channels: number;
  sample_rate: number;
  duration_s: number;
  demuxed_path?: string;
  waveform_path?: string;
}

export interface ImportedTrack {
  id: number;
  source_path: string;
  preview_path: string;
  display_name: string;
  origin: 'file' | 'voiceover';
  duration_s: number;
  created_at: string;
}

export interface AudioEffect {
  type: 'highpass' | 'lowpass' | 'compressor' | 'gate';
  freq?: number;
  threshold?: number;
  ratio?: number;
  attack?: number;
  release?: number;
}

export interface MixTrackSetting {
  stream_index?: number;
  import_id?: number;
  gain: number;
  pan: number;
  mute: boolean;
  solo?: boolean;
  offset: number;
  fade_in: number;
  fade_out: number;
  trim: { start: number; end: number } | null;
  effects: AudioEffect[];
}

export interface MixDocument {
  version: number;
  trim: { start: number; end: number; mode: 'fast' | 'accurate' } | null;
  speed: number;
  crop: { w: number; h: number; x: number; y: number } | null;
  video_fade: { in: number; out: number };
  master: { gain: number; limiter: boolean; normalize_lufs: number | null };
  tracks: MixTrackSetting[];
}

export interface Clip {
  id: number;
  path: string;
  filename: string;
  saved_at: string | null;
  game: string | null;
  window_title: string | null;
  monitor: number | null;
  duration_s: number;
  width: number;
  height: number;
  fps: number;
  video_codec: string;
  size_bytes: number;
  has_sidecar: boolean;
  starred: boolean;
  title: string | null;
  notes: string | null;
  ingested_at: string;
  last_opened_at: string | null;
  deleted_at: string | null;
  thumb_version: number;
  tags: ClipTag[];
  audio_tracks: AudioTrack[];
  imported_tracks: ImportedTrack[];
  mix_document: MixDocument | null;
}

export interface TagItem {
  id: number;
  name: string;
  color: string;
  kind: string;
  count: number;
}

export interface Job {
  id: number;
  clip_id: number | null;
  kind: string;
  preset?: string | null;
  state: 'pending' | 'running' | 'done' | 'error' | 'cancelled';
  progress: number;
  error: string | null;
  created_at: string;
  finished_at: string | null;
}

export interface ExportItem {
  id: number;
  clip_id: number;
  preset: string;
  filename: string;
  path: string;
  size_bytes: number;
  duration_s: number;
  created_at: string;
  exists: boolean;
}

export interface RecorderStatus {
  status: string;
  running: boolean;
  raw: string;
}
