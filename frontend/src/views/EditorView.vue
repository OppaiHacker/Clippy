<script setup lang="ts">
import { ref, reactive, computed, onMounted, onUnmounted, watch, nextTick } from 'vue';
import {
  Play, Pause, SkipBack, SkipForward, Scissors, Repeat, ArrowLeft,
  Gauge, Crop, Sparkles, Tag as TagIcon, Download, Mic, Plus, Trash2,
  Check, Undo2, Redo2, Radio, RefreshCw, AlertTriangle, X
} from 'lucide-vue-next';
import { Clip, MixDocument, MixTrackSetting, TrackKind } from '../types';
import { AudioGraph } from '../audio/AudioGraph';
import { SyncEngine, TrackAudioBinding } from '../audio/SyncEngine';
import WaveformCanvas from '../components/WaveformCanvas.vue';
import { updateMixDocument, startExportJob, uploadTrack, deleteImportedTrack, addTagToClip, removeTagFromClip } from '../api/client';
import { plural } from '../format';

const props = defineProps<{
  clip: Clip;
}>();

const emit = defineEmits<{
  (e: 'back'): void;
  (e: 'refresh'): void;
  (e: 'goto-downloads'): void;
}>();

const videoRef = ref<HTMLVideoElement | null>(null);
const audioRefs = ref<Record<string, HTMLAudioElement>>({});
const audioGraph = new AudioGraph();
const syncEngine = new SyncEngine();

const isPlaying = ref(false);
const currentTime = ref(0);
const duration = ref(props.clip.duration_s || 10);
const playbackRate = ref(1.0);
const activeToolTab = ref<'trim' | 'speed' | 'crop' | 'effects' | 'tags' | 'export'>('trim');
const loopTrim = ref(false);
const keyframes = ref<number[]>([]);
const newTagName = ref('');

// Drift testing
const isDriftTestRunning = ref(false);
const driftTestSecondsLeft = ref(30);
const maxDriftResultMs = ref<number | null>(null);
let driftTestTimer: any = null;

// Voiceover recording
const isRecordingVoiceover = ref(false);
const voiceoverSeconds = ref(0);
let voiceoverTimer: any = null;
let mediaRecorder: MediaRecorder | null = null;
let recordedChunks: Blob[] = [];

// VU Meter values (0..1)
const vuLevels = reactive<Record<string, number>>({});
let vuRafId: any = null;

// Undo / Redo history
const history = ref<MixDocument[]>([]);
const historyIndex = ref(-1);

// Initialize Mix Document
const currentMix = ref<MixDocument>(props.clip.mix_document ? JSON.parse(JSON.stringify(props.clip.mix_document)) : {
  version: 1,
  trim: null,
  speed: 1.0,
  crop: null,
  video_fade: { in: 0, out: 0 },
  master: { gain: 1.0, limiter: true, normalize_lufs: null },
  tracks: []
});

// Sync tracks in mix document with clip tracks
const initializeTracks = () => {
  const existingMap = new Map<string, MixTrackSetting>();
  currentMix.value.tracks.forEach(t => {
    if (t.stream_index !== undefined) existingMap.set(`stream_${t.stream_index}`, t);
    else if (t.import_id !== undefined) existingMap.set(`import_${t.import_id}`, t);
  });

  const updatedTracks: MixTrackSetting[] = [];

  // Source audio tracks
  props.clip.audio_tracks.forEach(t => {
    const key = `stream_${t.stream_index}`;
    const existing = existingMap.get(key);
    if (existing) {
      updatedTracks.push(existing);
    } else {
      updatedTracks.push({
        stream_index: t.stream_index,
        gain: 1.0,
        pan: 0,
        mute: false,
        solo: false,
        offset: 0,
        fade_in: 0,
        fade_out: 0,
        trim: null,
        effects: [],
      });
    }
  });

  // Imported tracks
  props.clip.imported_tracks.forEach(t => {
    const key = `import_${t.id}`;
    const existing = existingMap.get(key);
    if (existing) {
      updatedTracks.push(existing);
    } else {
      updatedTracks.push({
        import_id: t.id,
        gain: 1.0,
        pan: 0,
        mute: false,
        solo: false,
        offset: 0,
        fade_in: 0,
        fade_out: 0,
        trim: null,
        effects: [],
      });
    }
  });

  currentMix.value.tracks = updatedTracks;
};

initializeTracks();

// Save state to undo history
const pushHistory = () => {
  const clone = JSON.parse(JSON.stringify(currentMix.value));
  if (historyIndex.value < history.value.length - 1) {
    history.value = history.value.slice(0, historyIndex.value + 1);
  }
  history.value.push(clone);
  if (history.value.length > 50) history.value.shift();
  historyIndex.value = history.value.length - 1;
};

pushHistory();

const undo = () => {
  if (historyIndex.value > 0) {
    historyIndex.value--;
    currentMix.value = JSON.parse(JSON.stringify(history.value[historyIndex.value]));
    applyMixToGraph();
  }
};

const redo = () => {
  if (historyIndex.value < history.value.length - 1) {
    historyIndex.value++;
    currentMix.value = JSON.parse(JSON.stringify(history.value[historyIndex.value]));
    applyMixToGraph();
  }
};

const KIND_BG: Record<TrackKind, string> = {
  system: 'bg-trk-system',
  app: 'bg-trk-app',
  mic: 'bg-trk-mic',
  device: 'bg-trk-device',
  imported: 'bg-trk-imported',
};

// canvas does not resolve var(), so the waveform colour is read from the :root token
const canvasColor = (kind: TrackKind) =>
  `rgb(${getComputedStyle(document.documentElement).getPropertyValue(`--trk-${kind}`).trim()})`;

const trackMeta = (t: MixTrackSetting) => {
  if (t.stream_index !== undefined) {
    const src = props.clip.audio_tracks.find(a => a.stream_index === t.stream_index);
    return { name: src?.display_name ?? `Track ${t.stream_index}`, kind: src?.kind ?? 'device' as TrackKind, importId: null };
  }
  const imp = props.clip.imported_tracks.find(i => i.id === t.import_id);
  return { name: imp?.display_name ?? 'Import', kind: 'imported' as TrackKind, importId: t.import_id ?? null };
};

const anySolo = computed(() => currentMix.value.tracks.some(t => t.solo));
const isAudible = (t: MixTrackSetting | undefined) => !!t && !t.mute && (!anySolo.value || !!t.solo);
const settingForStream = (streamIndex: number) => currentMix.value.tracks.find(t => t.stream_index === streamIndex);

const setAudioRef = (key: string, el: HTMLAudioElement | null) => {
  if (el) audioRefs.value[key] = el;
  else delete audioRefs.value[key];
};

const trackKey = (t: MixTrackSetting) =>
  t.stream_index !== undefined ? `stream_${t.stream_index}` : `import_${t.import_id}`;

const applyMixToGraph = () => {
  const anySolo = currentMix.value.tracks.some(t => t.solo);
  currentMix.value.tracks.forEach(setting => {
    audioGraph.updateTrackSettings(trackKey(setting), setting, anySolo);
  });
  audioGraph.setMasterGain(currentMix.value.master.gain);

  // a positive offset delays the DelayNode in AudioGraph, a negative one starts the track earlier;
  // the sync used to add the offset on top of the delay and the two cancelled out
  const bindings: TrackAudioBinding[] = [];
  currentMix.value.tracks.forEach(t => {
    const el = audioRefs.value[trackKey(t)];
    if (el) bindings.push({ key: trackKey(t), audio: el, offsetSeconds: Math.max(0, -(t.offset || 0)) });
  });
  syncEngine.setAudioTracks(bindings);
};

const saveState = ref<'saved' | 'saving' | 'error'>('saved');
let saveTimer: ReturnType<typeof setTimeout> | null = null;

const saveMix = async () => {
  if (saveTimer) { clearTimeout(saveTimer); saveTimer = null; }
  saveState.value = 'saving';
  try {
    await updateMixDocument(props.clip.id, currentMix.value);
    saveState.value = 'saved';
  } catch (e) {
    saveState.value = 'error';
    console.error('Failed to save mix document', e);
  }
};

// Autosave: every mix change (trim, speed, crop, fade, sliders, undo) goes to the server.
// Trim/crop/fade used to be lost on leaving the editor unless someone pressed Ctrl+S.
watch(currentMix, () => {
  if (saveTimer) clearTimeout(saveTimer);
  saveState.value = 'saving';
  saveTimer = setTimeout(saveMix, 600);
}, { deep: true });

onMounted(async () => {
  // Fetch keyframes
  try {
    const kfRes = await fetch(`/api/clips/${props.clip.id}/keyframes`);
    if (kfRes.ok) {
      const kfData = await kfRes.json();
      keyframes.value = kfData.keyframes || [];
    }
  } catch (e) {}

  await nextTick();

  if (videoRef.value) {
    syncEngine.attachVideo(videoRef.value);
  }

  currentMix.value.tracks.forEach(t => {
    const el = audioRefs.value[trackKey(t)];
    if (el) audioGraph.registerTrack(trackKey(t), el);
  });

  syncEngine.setOnTimeUpdate((time) => {
    currentTime.value = time;
  });

  applyMixToGraph();

  // VU Meter update loop
  const updateVU = () => {
    currentMix.value.tracks.forEach(t => {
      const key = t.stream_index !== undefined ? `stream_${t.stream_index}` : `import_${t.import_id}`;
      vuLevels[key] = audioGraph.getTrackPeak(key);
    });
    vuRafId = requestAnimationFrame(updateVU);
  };
  vuRafId = requestAnimationFrame(updateVU);

  // Keyboard shortcuts
  window.addEventListener('keydown', handleKeydown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', handleKeydown);
  if (saveTimer) saveMix(); // unsaved change from the last 600 ms
  if (vuRafId) cancelAnimationFrame(vuRafId);
  syncEngine.detachVideo();
  audioGraph.destroy();
  if (driftTestTimer) clearInterval(driftTestTimer);
  if (voiceoverTimer) clearInterval(voiceoverTimer);
});

const togglePlay = () => {
  audioGraph.getContext(); // ensure AudioContext is resumed
  if (isPlaying.value) {
    syncEngine.pause();
    isPlaying.value = false;
  } else {
    syncEngine.play();
    isPlaying.value = true;
  }
};

const handleSeek = (time: number) => {
  currentTime.value = Math.max(0, Math.min(duration.value, time));
  syncEngine.seek(currentTime.value);
};

// Scrubbing: click or drag on the timeline
const scrubTo = (e: PointerEvent) => {
  const rect = (e.currentTarget as HTMLElement).getBoundingClientRect();
  handleSeek(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)) * duration.value);
};
const onScrubStart = (e: PointerEvent) => {
  (e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);
  scrubTo(e);
};
const onScrubMove = (e: PointerEvent) => {
  if (e.buttons & 1) scrubTo(e);
};

// Ruler: about 12 labelled ticks regardless of clip length
const rulerMarks = computed(() => {
  const step = [1, 2, 5, 10, 15, 30, 60].find(s => duration.value / s <= 12) ?? 120;
  const marks: number[] = [];
  for (let t = 0; t < duration.value - step / 3; t += step) marks.push(t);
  return marks;
});
const pct = (t: number) => `${(t / duration.value) * 100}%`;

const setInPoint = () => {
  const cur = currentTime.value;
  const existingEnd = currentMix.value.trim?.end ?? duration.value;
  currentMix.value.trim = {
    start: cur,
    end: Math.min(duration.value, Math.max(cur + 0.5, existingEnd)),
    mode: currentMix.value.trim?.mode || 'accurate',
  };
  updateTrimSync();
  pushHistory();
};

const setOutPoint = () => {
  const cur = currentTime.value;
  const existingStart = currentMix.value.trim?.start ?? 0;
  currentMix.value.trim = {
    start: Math.max(0, Math.min(cur - 0.5, existingStart)),
    end: cur,
    mode: currentMix.value.trim?.mode || 'accurate',
  };
  updateTrimSync();
  pushHistory();
};

const clearTrim = () => {
  currentMix.value.trim = null;
  updateTrimSync();
  pushHistory();
};

const updateTrimSync = () => {
  if (currentMix.value.trim) {
    syncEngine.setTrimRange(currentMix.value.trim.start, currentMix.value.trim.end, loopTrim.value);
  } else {
    syncEngine.setTrimRange(0, duration.value, false);
  }
};

const toggleLoopTrim = () => {
  loopTrim.value = !loopTrim.value;
  updateTrimSync();
};

// Track mixer adjustments
const toggleMute = (track: MixTrackSetting) => {
  track.mute = !track.mute;
  applyMixToGraph();
  pushHistory();
};

const toggleSolo = (track: MixTrackSetting) => {
  track.solo = !track.solo;
  applyMixToGraph();
  pushHistory();
};

const setTrackGain = (track: MixTrackSetting, val: number) => {
  track.gain = val;
  applyMixToGraph();
};

const onGainCommitted = () => {
  pushHistory();
};

const resetGain = (track: MixTrackSetting) => {
  track.gain = 1.0;
  applyMixToGraph();
  pushHistory();
};

// Keyboard bindings
const handleKeydown = (e: KeyboardEvent) => {
  if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

  if (e.code === 'Space') {
    e.preventDefault();
    togglePlay();
  } else if (e.key === 'j' || e.key === 'J') {
    handleSeek(currentTime.value - 10);
  } else if (e.key === 'l' || e.key === 'L') {
    handleSeek(currentTime.value + 10);
  } else if (e.key === 'ArrowLeft') {
    handleSeek(currentTime.value - 5);
  } else if (e.key === 'ArrowRight') {
    handleSeek(currentTime.value + 5);
  } else if (e.key === ',') {
    handleSeek(currentTime.value - (1 / props.clip.fps));
  } else if (e.key === '.') {
    handleSeek(currentTime.value + (1 / props.clip.fps));
  } else if (e.key === 'Home') {
    handleSeek(0);
  } else if (e.key === 'End') {
    handleSeek(duration.value);
  } else if (e.key === 'i' || e.key === 'I') {
    if (e.shiftKey) handleSeek(currentMix.value.trim?.start || 0);
    else setInPoint();
  } else if (e.key === 'o' || e.key === 'O') {
    if (e.shiftKey) handleSeek(currentMix.value.trim?.end || duration.value);
    else setOutPoint();
  } else if (e.key === 'p' || e.key === 'P') {
    toggleLoopTrim();
  } else if (e.key === 'm' || e.key === 'M') {
    currentMix.value.master.gain = currentMix.value.master.gain > 0 ? 0 : 1.0;
    applyMixToGraph();
  } else if (e.key === 's' || e.key === 'S') {
    if (e.ctrlKey) {
      e.preventDefault();
      saveMix();
    }
  } else if (e.ctrlKey && (e.key === 'z' || e.key === 'Z')) {
    e.preventDefault();
    if (e.shiftKey) redo();
    else undo();
  } else if (e.ctrlKey && (e.key === 'y' || e.key === 'Y')) {
    e.preventDefault();
    redo();
  } else if (/^Digit[1-9]$/.test(e.code)) {
    // e.code, not e.key: with Shift the key is "!", "@"... depending on the layout
    const idx = parseInt(e.code.slice(5), 10) - 1;
    if (idx < currentMix.value.tracks.length) {
      const track = currentMix.value.tracks[idx];
      if (e.shiftKey) toggleSolo(track);
      else toggleMute(track);
    }
  }
};

// Format timecode
const formatTimecode = (sec: number): string => {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  const ms = Math.floor((sec % 1) * 1000);
  return `${m}:${s.toString().padStart(2, '0')}.${ms.toString().padStart(3, '0')}`;
};

// Drift Test Execution
const runDriftTest = async () => {
  if (isDriftTestRunning.value) return;
  isDriftTestRunning.value = true;
  driftTestSecondsLeft.value = 30;
  maxDriftResultMs.value = null;
  syncEngine.resetDriftStats();

  handleSeek(0);
  syncEngine.play();
  isPlaying.value = true;

  driftTestTimer = setInterval(() => {
    driftTestSecondsLeft.value--;
    if (driftTestSecondsLeft.value <= 0) {
      clearInterval(driftTestTimer);
      syncEngine.pause();
      isPlaying.value = false;
      isDriftTestRunning.value = false;
      maxDriftResultMs.value = syncEngine.getMaxObservedDriftMs();
    }
  }, 1000);
};

const setSpeed = (s: number) => {
  currentMix.value.speed = s;
  syncEngine.setPlaybackRate(s);
  pushHistory();
};

// 9:16 from the centre of the frame, computed from the clip size (a hardcoded 810x1440 broke 1080p clips)
const setVerticalCrop = (vertical: boolean) => {
  const { width, height } = props.clip;
  const w = Math.round((height * 9) / 16 / 2) * 2;
  currentMix.value.crop = vertical ? { w, h: height, x: Math.round((width - w) / 2), y: 0 } : null;
  pushHistory();
};

// Export Trigger
const isExporting = ref(false);
const exportPreset = ref<'original' | 'discord' | 'youtube' | 'vertical' | 'audio_only'>('original');
const EXPORT_PRESETS = [
  { id: 'original', label: 'Original', hint: 'video copy, new mix' },
  { id: 'discord', label: 'Discord', hint: 'up to 25 MB' },
  { id: 'youtube', label: 'YouTube', hint: '1440p60, high quality' },
  { id: 'vertical', label: 'Vertical 9:16', hint: 'Shorts / TikTok' },
  { id: 'audio_only', label: 'Audio only', hint: 'Opus' },
] as const;

const TOOLS = [
  { id: 'trim', label: 'Trim', icon: Scissors },
  { id: 'speed', label: 'Speed', icon: Gauge },
  { id: 'crop', label: 'Crop', icon: Crop },
  { id: 'effects', label: 'Fades', icon: Sparkles },
  { id: 'tags', label: 'Tags', icon: TagIcon },
  { id: 'export', label: 'Export', icon: Download },
] as const;

const LUFS_OPTIONS = [
  { value: null, label: 'No normalization' },
  { value: -14, label: '−14 LUFS (YouTube, Spotify)' },
  { value: -16, label: '−16 LUFS (podcast)' },
  { value: -23, label: '−23 LUFS (EBU R128)' },
];

const triggerExport = async () => {
  isExporting.value = true;
  try {
    await saveMix();
    await startExportJob(props.clip.id, exportPreset.value, currentMix.value);
    emit('goto-downloads');
  } catch (e) {
    alert('Could not start the export: ' + e);
  } finally {
    isExporting.value = false;
  }
};

// Import file audio
const fileInputRef = ref<HTMLInputElement | null>(null);
const handleFileImport = async (e: Event) => {
  const target = e.target as HTMLInputElement;
  if (!target.files || !target.files[0]) return;
  const file = target.files[0];
  target.value = '';
  try {
    // the editor reloads with the mix from the server: push unsaved changes first
    await saveMix();
    await uploadTrack(props.clip.id, file, 'file', file.name);
    emit('refresh');
  } catch (err) {
    alert('Could not import the audio file: ' + err);
  }
};

// Voiceover recording
const toggleVoiceover = async () => {
  if (isRecordingVoiceover.value) {
    if (mediaRecorder && mediaRecorder.state !== 'inactive') {
      mediaRecorder.stop();
    }
    syncEngine.pause();
    isPlaying.value = false;
    isRecordingVoiceover.value = false;
    clearInterval(voiceoverTimer);
  } else {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      recordedChunks = [];
      mediaRecorder = new MediaRecorder(stream, { mimeType: 'audio/webm' });
      mediaRecorder.ondataavailable = e => {
        if (e.data.size > 0) recordedChunks.push(e.data);
      };
      mediaRecorder.onstop = async () => {
        // without this the mic stays in use (red dot) until the tab is closed
        stream.getTracks().forEach(tr => tr.stop());
        const blob = new Blob(recordedChunks, { type: 'audio/webm' });
        try {
          await saveMix();
          await uploadTrack(props.clip.id, blob, 'voiceover', `Voiceover ${new Date().toLocaleTimeString()}`);
          emit('refresh');
        } catch (e) {
          alert('Could not save the voiceover: ' + e);
        }
      };

      mediaRecorder.start();
      isRecordingVoiceover.value = true;
      voiceoverSeconds.value = 0;
      voiceoverTimer = setInterval(() => {
        voiceoverSeconds.value++;
      }, 1000);

      // Play video in sync while speaking
      syncEngine.play();
      isPlaying.value = true;
    } catch (err) {
      alert('Could not access the microphone: ' + err);
    }
  }
};

// Tag management in editor
const addTag = async () => {
  if (!newTagName.value.trim()) return;
  try {
    await addTagToClip(props.clip.id, newTagName.value.trim());
    newTagName.value = '';
    emit('refresh');
  } catch (e) {}
};

const removeTag = async (tagId: number) => {
  try {
    await removeTagFromClip(props.clip.id, tagId);
    emit('refresh');
  } catch (e) {}
};

const removeImport = async (importId: number, name: string) => {
  if (!confirm(`Remove track "${name}"?`)) return;
  try {
    await saveMix();
    await deleteImportedTrack(props.clip.id, importId);
    emit('refresh');
  } catch (e) {
    alert('Could not remove the track: ' + e);
  }
};
</script>

<template>
  <div class="flex-1 min-w-0 flex flex-col overflow-hidden bg-bg">
    <!-- Hidden audio elements: every track plays separately through AudioGraph -->
    <template v-for="t in clip.audio_tracks" :key="t.id">
      <audio
        :ref="(el) => setAudioRef(`stream_${t.stream_index}`, el as HTMLAudioElement)"
        :src="`/api/clips/${clip.id}/audio/${t.stream_index}`"
        preload="auto"
      />
    </template>
    <template v-for="imp in clip.imported_tracks" :key="imp.id">
      <audio
        :ref="(el) => setAudioRef(`import_${imp.id}`, el as HTMLAudioElement)"
        :src="`/api/clips/${clip.id}/audio/imported_${imp.id}`"
        preload="auto"
      />
    </template>

    <!-- Header -->
    <header class="h-14 px-4 flex items-center justify-between gap-4 border-b border-border bg-surface/40 shrink-0 text-xs">
      <div class="flex items-center gap-3 min-w-0">
        <button
          @click="emit('back')"
          class="h-8 w-8 shrink-0 rounded-lg flex items-center justify-center text-text-2 hover:text-text hover:bg-surface-2 cursor-pointer"
          title="Back to library"
        >
          <ArrowLeft :size="16" />
        </button>
        <div class="min-w-0">
          <div class="flex items-center gap-2 min-w-0">
            <span class="text-[15px] font-semibold tracking-tight text-text truncate">{{ clip.title || clip.filename }}</span>
            <span class="shrink-0 px-2 py-0.5 rounded-full bg-accent/15 text-accent text-[11px] font-medium">{{ clip.game || 'Other' }}</span>
          </div>
          <div class="text-[11px] text-text-3 mono-num mt-0.5">
            {{ clip.width }}×{{ clip.height }} · {{ Math.round(clip.fps) }} fps · {{ formatTimecode(duration) }} · {{ currentMix.tracks.length }} audio {{ plural(currentMix.tracks.length, 'track') }}
          </div>
        </div>
      </div>

      <div class="flex items-center gap-1.5 shrink-0">
        <span
          class="flex items-center gap-1.5 px-2 text-[11px] mr-1"
          :class="saveState === 'error' ? 'text-danger' : 'text-text-3'"
          :title="saveState === 'error' ? 'Click to retry' : 'The mix saves automatically'"
          @click="saveState === 'error' && saveMix()"
        >
          <RefreshCw v-if="saveState === 'saving'" :size="12" class="animate-spin" />
          <AlertTriangle v-else-if="saveState === 'error'" :size="12" />
          <Check v-else :size="12" class="text-success" />
          {{ saveState === 'saving' ? 'Saving…' : saveState === 'error' ? 'Save failed' : 'Saved' }}
        </span>
        <button
          @click="undo"
          :disabled="historyIndex <= 0"
          class="h-8 w-8 rounded-lg flex items-center justify-center text-text-2 hover:text-text hover:bg-surface-2 disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer"
          title="Undo [Ctrl+Z]"
        >
          <Undo2 :size="15" />
        </button>
        <button
          @click="redo"
          :disabled="historyIndex >= history.length - 1"
          class="h-8 w-8 rounded-lg flex items-center justify-center text-text-2 hover:text-text hover:bg-surface-2 disabled:opacity-30 disabled:hover:bg-transparent cursor-pointer"
          title="Redo [Ctrl+Y]"
        >
          <Redo2 :size="15" />
        </button>
        <button
          @click="activeToolTab = 'export'"
          class="h-8 ml-1.5 px-3.5 bg-accent text-white hover:bg-accent/90 rounded-lg font-medium flex items-center gap-1.5 cursor-pointer"
        >
          <Download :size="14" />
          Export
        </button>
      </div>
    </header>

    <!-- Video + mixer -->
    <div class="flex-1 flex overflow-hidden min-h-0">
      <div class="flex-1 min-w-0 bg-black flex items-center justify-center relative overflow-hidden group">
        <video
          ref="videoRef"
          :src="`/api/clips/${clip.id}/stream`"
          muted
          playsinline
          class="max-h-full max-w-full object-contain cursor-pointer"
          @click="togglePlay"
        />
        <div
          v-if="!isPlaying"
          class="absolute inset-0 flex items-center justify-center pointer-events-none"
        >
          <div class="w-14 h-14 rounded-full bg-black/40 backdrop-blur-md border border-white/20 text-white flex items-center justify-center opacity-80 group-hover:opacity-100 transition-opacity">
            <Play :size="22" class="ml-1 fill-white" />
          </div>
        </div>
        <div v-if="currentMix.crop" class="absolute top-3 left-3 px-2 py-0.5 rounded-md bg-black/60 backdrop-blur text-[11px] text-white flex items-center gap-1 pointer-events-none">
          <Crop :size="11" /> 9:16 crop in export
        </div>
        <div v-if="isRecordingVoiceover" class="rec-live absolute top-3 right-3 px-2.5 py-1 rounded-full bg-danger text-white text-[11px] font-medium flex items-center gap-1.5 pointer-events-none">
          <span class="w-1.5 h-1.5 rounded-full bg-white animate-pulse" /> Recording voiceover · {{ voiceoverSeconds }} s
        </div>
      </div>

      <!-- Mixer -->
      <aside class="w-80 bg-surface border-l border-border flex flex-col shrink-0 text-xs">
        <div class="h-10 px-3 flex items-center justify-between border-b border-border shrink-0">
          <span class="text-[11px] font-semibold uppercase tracking-wider text-text-2">Mixer</span>
          <span class="mono-num text-[10px] text-text-3">{{ currentMix.tracks.length }} {{ plural(currentMix.tracks.length, 'track') }}</span>
        </div>

        <div class="flex-1 overflow-y-auto p-2 space-y-1.5">
          <div
            v-for="(trackSetting, idx) in currentMix.tracks"
            :key="trackKey(trackSetting)"
            class="rounded-lg border border-border bg-surface-2 px-2.5 py-2 space-y-1.5 transition-opacity"
            :class="isAudible(trackSetting) ? '' : 'opacity-50'"
          >
            <div class="h-6 flex items-center gap-2">
              <span class="w-2 h-2 rounded-full shrink-0" :class="KIND_BG[trackMeta(trackSetting).kind]" />
              <span class="flex-1 min-w-0 font-semibold text-text truncate" :title="trackMeta(trackSetting).name">{{ trackMeta(trackSetting).name }}</span>
              <span class="text-[10px] text-text-3 mono-num" :title="`Key ${idx + 1}`">{{ idx + 1 }}</span>
              <button
                v-if="trackMeta(trackSetting).importId !== null"
                @click="removeImport(trackMeta(trackSetting).importId!, trackMeta(trackSetting).name)"
                class="w-6 h-6 rounded-md flex items-center justify-center text-text-3 hover:text-danger hover:bg-danger/10 cursor-pointer"
                title="Remove added track"
              >
                <Trash2 :size="12" />
              </button>
              <button
                @click="toggleMute(trackSetting)"
                class="w-6 h-6 rounded-md font-mono font-bold text-[10px] cursor-pointer"
                :class="trackSetting.mute ? 'bg-danger text-white' : 'bg-surface-3 text-text-3 hover:text-text'"
                :title="`Mute [${idx + 1}]`"
              >M</button>
              <button
                @click="toggleSolo(trackSetting)"
                class="w-6 h-6 rounded-md font-mono font-bold text-[10px] cursor-pointer"
                :class="trackSetting.solo ? 'bg-warning text-black' : 'bg-surface-3 text-text-3 hover:text-text'"
                :title="`Solo [Shift+${idx + 1}]`"
              >S</button>
            </div>

            <!-- Volume + peak meter -->
            <div>
              <div class="flex items-center gap-2">
                <input
                  type="range" min="0" max="1.5" step="0.01"
                  v-model.number="trackSetting.gain"
                  @input="setTrackGain(trackSetting, trackSetting.gain)"
                  @change="onGainCommitted"
                  class="flex-1 min-w-0 h-4 cursor-pointer"
                  :aria-label="`Volume: ${trackMeta(trackSetting).name}`"
                />
                <span
                  class="w-10 text-right mono-num text-[11px] cursor-pointer select-none"
                  :class="trackSetting.gain === 1 ? 'text-text-3' : 'text-text'"
                  @dblclick="resetGain(trackSetting)"
                  title="Double-click = 100%"
                >{{ Math.round(trackSetting.gain * 100) }}%</span>
              </div>
              <div class="mt-1 h-1 rounded-full bg-black/50 overflow-hidden">
                <div
                  class="h-full rounded-full transition-[width] duration-75"
                  :class="(vuLevels[trackKey(trackSetting)] || 0) > 0.9 ? 'bg-danger' : KIND_BG[trackMeta(trackSetting).kind]"
                  :style="{ width: `${Math.min(100, (vuLevels[trackKey(trackSetting)] || 0) * 100)}%` }"
                />
              </div>
            </div>

            <div class="grid grid-cols-2 gap-3 text-[10px] text-text-3">
              <label class="flex items-center gap-1.5 min-w-0" title="Pan · double-click = centre">
                Pan
                <input
                  type="range" min="-1" max="1" step="0.1"
                  v-model.number="trackSetting.pan"
                  @input="applyMixToGraph"
                  @change="onGainCommitted"
                  @dblclick="trackSetting.pan = 0; applyMixToGraph(); pushHistory()"
                  class="flex-1 min-w-0 h-3 cursor-pointer"
                />
                <span class="w-6 text-right mono-num">{{ trackSetting.pan === 0 ? 'C' : (trackSetting.pan < 0 ? 'L' : 'R') + Math.round(Math.abs(trackSetting.pan) * 100) }}</span>
              </label>
              <label class="flex items-center gap-1.5 min-w-0" title="Time offset · double-click = 0">
                Offset
                <input
                  type="range" min="-5" max="5" step="0.1"
                  v-model.number="trackSetting.offset"
                  @input="applyMixToGraph"
                  @change="onGainCommitted"
                  @dblclick="trackSetting.offset = 0; applyMixToGraph(); pushHistory()"
                  class="flex-1 min-w-0 h-3 cursor-pointer"
                />
                <span class="w-8 text-right mono-num">{{ trackSetting.offset > 0 ? '+' : '' }}{{ trackSetting.offset.toFixed(1) }}s</span>
              </label>
            </div>
          </div>

          <!-- Add track -->
          <div class="grid grid-cols-2 gap-2 pt-1">
            <input ref="fileInputRef" type="file" accept="audio/*" class="hidden" @change="handleFileImport" />
            <button
              @click="fileInputRef?.click()"
              class="h-8 rounded-lg border border-dashed border-border-strong text-text-2 hover:text-text hover:bg-surface-2 flex items-center justify-center gap-1.5 cursor-pointer"
            >
              <Plus :size="13" /> Import audio
            </button>
            <button
              @click="toggleVoiceover"
              class="h-8 rounded-lg border flex items-center justify-center gap-1.5 cursor-pointer"
              :class="isRecordingVoiceover
                ? 'bg-danger border-danger text-white'
                : 'border-dashed border-border-strong text-text-2 hover:text-text hover:bg-surface-2'"
            >
              <Mic :size="13" /> {{ isRecordingVoiceover ? `Stop · ${voiceoverSeconds} s` : 'Record voiceover' }}
            </button>
          </div>
        </div>

        <!-- Master -->
        <div class="p-3 border-t border-border bg-surface-2/50 space-y-2 shrink-0">
          <div class="flex items-center justify-between">
            <span class="text-[11px] font-semibold uppercase tracking-wider text-text-2">Master</span>
            <span class="mono-num text-[11px]" :class="currentMix.master.gain === 0 ? 'text-danger' : 'text-text'" title="M mutes the master">
              {{ currentMix.master.gain === 0 ? 'muted' : Math.round(currentMix.master.gain * 100) + '%' }}
            </span>
          </div>
          <input
            type="range" min="0" max="1.5" step="0.01"
            v-model.number="currentMix.master.gain"
            @input="applyMixToGraph"
            @change="onGainCommitted"
            @dblclick="currentMix.master.gain = 1; applyMixToGraph(); pushHistory()"
            class="w-full cursor-pointer"
            aria-label="Master volume"
          />
          <div class="flex items-center gap-1.5">
            <button
              @click="currentMix.master.limiter = !currentMix.master.limiter; pushHistory()"
              class="chip !h-7 !px-2.5 text-[11px]"
              :class="currentMix.master.limiter ? 'chip-on' : ''"
              title="Master limiter in export (alimiter)"
            >
              <Check v-if="currentMix.master.limiter" :size="11" /> Limiter
            </button>
            <select
              v-model="currentMix.master.normalize_lufs"
              @change="pushHistory()"
              class="flex-1 min-w-0 h-7 bg-surface-2 border border-border rounded-full px-2.5 text-[11px] text-text-2 focus:outline-none cursor-pointer"
              title="Loudness normalization in export (loudnorm)"
            >
              <option v-for="o in LUFS_OPTIONS" :key="String(o.value)" :value="o.value">{{ o.label }}</option>
            </select>
          </div>
        </div>
      </aside>
    </div>

    <!-- Transport -->
    <div class="h-11 px-3 flex items-center justify-between gap-4 bg-surface border-t border-border shrink-0 text-xs">
      <div class="flex items-center gap-1">
        <button @click="handleSeek(0)" class="h-8 w-8 rounded-lg flex items-center justify-center text-text-2 hover:text-text hover:bg-surface-2 cursor-pointer" title="Start [Home]">
          <SkipBack :size="15" />
        </button>
        <button
          @click="togglePlay"
          class="h-8 w-8 rounded-full bg-accent text-white flex items-center justify-center cursor-pointer hover:bg-accent/90 shadow-[0_4px_14px_-4px] shadow-accent/70"
          :title="isPlaying ? 'Pause [Space]' : 'Play [Space]'"
        >
          <Pause v-if="isPlaying" :size="14" class="fill-white" />
          <Play v-else :size="14" class="ml-0.5 fill-white" />
        </button>
        <button @click="handleSeek(duration)" class="h-8 w-8 rounded-lg flex items-center justify-center text-text-2 hover:text-text hover:bg-surface-2 cursor-pointer" title="End [End]">
          <SkipForward :size="15" />
        </button>
        <span class="mono-num ml-2 text-[13px] text-text">{{ formatTimecode(currentTime) }}</span>
        <span class="mono-num text-text-3">/ {{ formatTimecode(duration) }}</span>
      </div>

      <div class="flex items-center gap-1.5">
        <span v-if="currentMix.trim" class="mono-num text-[11px] text-text-2 mr-1.5">
          <span class="text-accent">IN</span> {{ formatTimecode(currentMix.trim.start) }}
          <span class="text-accent ml-1">OUT</span> {{ formatTimecode(currentMix.trim.end) }}
          <span class="text-text-3">· {{ (currentMix.trim.end - currentMix.trim.start).toFixed(1) }} s</span>
        </span>
        <button
          @click="toggleLoopTrim"
          class="chip"
          :class="loopTrim ? 'chip-on' : ''"
          title="Loop the in–out range [P]"
        >
          <Repeat :size="12" :class="loopTrim ? 'text-accent' : ''" /> Loop
        </button>
        <select
          v-model.number="playbackRate"
          @change="syncEngine.setPlaybackRate(playbackRate)"
          class="h-7 bg-surface-2 border border-border rounded-full px-2.5 text-xs text-text-2 focus:outline-none cursor-pointer"
          title="Preview speed (does not affect the export)"
        >
          <option v-for="r in [0.25, 0.5, 1, 1.5, 2]" :key="r" :value="r">{{ r }}×</option>
        </select>
        <button
          @click="runDriftTest"
          :disabled="isDriftTestRunning"
          class="chip"
          :class="isDriftTestRunning
            ? '!border-warning/50 !bg-warning/15 !text-warning'
            : maxDriftResultMs !== null
              ? (maxDriftResultMs <= 150 ? '!border-success/50 !bg-success/15 !text-success' : '!border-danger/50 !bg-danger/15 !text-danger')
              : ''"
          title="Sync test: 30 s of playback, 150 ms threshold"
        >
          <Radio :size="12" />
          <span v-if="isDriftTestRunning" class="mono-num">Drift test… {{ driftTestSecondsLeft }} s</span>
          <span v-else-if="maxDriftResultMs !== null" class="mono-num">Drift {{ maxDriftResultMs }} ms · {{ maxDriftResultMs <= 150 ? 'OK' : 'too high' }}</span>
          <span v-else>Drift test</span>
        </button>
      </div>
    </div>

    <!-- Timeline -->
    <div class="flex bg-surface-2/40 border-t border-border shrink-0 select-none">
      <!-- Track labels -->
      <div class="w-32 shrink-0 border-r border-border py-2 space-y-1">
        <div class="h-5" />
        <div
          v-for="track in clip.audio_tracks"
          :key="track.id"
          class="h-8 px-3 flex items-center gap-2 text-[11px] transition-opacity"
          :class="isAudible(settingForStream(track.stream_index)) ? 'text-text-2' : 'text-text-3 opacity-50'"
          :title="track.name"
        >
          <span class="w-1.5 h-1.5 rounded-full shrink-0" :class="KIND_BG[track.kind]" />
          <span class="truncate">{{ track.display_name }}</span>
        </div>
      </div>

      <!-- Scrub area -->
      <div
        class="flex-1 min-w-0 relative py-2 space-y-1 cursor-text touch-none"
        @pointerdown="onScrubStart"
        @pointermove="onScrubMove"
      >
        <!-- Ruler + keyframes -->
        <div class="h-5 relative">
          <div
            v-for="kf in keyframes"
            :key="'kf' + kf"
            class="absolute bottom-0 w-px h-1.5 bg-warning/50"
            :style="{ left: pct(kf) }"
          />
          <div
            v-for="m in rulerMarks"
            :key="'m' + m"
            class="absolute top-0 bottom-0 border-l border-border-strong pl-1 text-[10px] leading-none text-text-3 mono-num"
            :style="{ left: pct(m) }"
          >{{ Math.floor(m / 60) }}:{{ String(Math.floor(m % 60)).padStart(2, '0') }}</div>
        </div>

        <div
          v-for="track in clip.audio_tracks"
          :key="track.id"
          class="h-8 rounded-md bg-bg/60 overflow-hidden transition-opacity"
          :class="isAudible(settingForStream(track.stream_index)) ? '' : 'opacity-30'"
        >
          <WaveformCanvas
            :clip-id="clip.id"
            :track-id="track.id"
            :color="canvasColor(track.kind)"
            :height="32"
          />
        </div>

        <!-- In/out range: dim outside the range -->
        <template v-if="currentMix.trim">
          <div class="absolute inset-y-0 left-0 bg-black/55 pointer-events-none" :style="{ width: pct(currentMix.trim.start) }" />
          <div class="absolute inset-y-0 right-0 bg-black/55 pointer-events-none" :style="{ left: pct(currentMix.trim.end) }" />
          <div
            class="absolute inset-y-0 border-x-2 border-accent pointer-events-none"
            :style="{ left: pct(currentMix.trim.start), width: pct(Math.max(0, currentMix.trim.end - currentMix.trim.start)) }"
          />
        </template>

        <!-- Playhead -->
        <div class="absolute inset-y-0 w-px bg-white z-20 pointer-events-none" :style="{ left: pct(currentTime) }">
          <div class="absolute -top-px -left-[5px] w-[11px] h-2.5 bg-white rounded-b-sm" />
        </div>
      </div>
    </div>

    <!-- Tools -->
    <div class="bg-surface border-t border-border shrink-0 text-xs">
      <div class="px-3 pt-2 flex items-center gap-1">
        <button
          v-for="tool in TOOLS"
          :key="tool.id"
          @click="activeToolTab = tool.id"
          class="h-7 flex items-center gap-1.5 px-3 rounded-md font-medium cursor-pointer"
          :class="activeToolTab === tool.id ? 'bg-surface-3 text-text' : 'text-text-3 hover:text-text hover:bg-surface-2'"
        >
          <component :is="tool.icon" :size="13" :class="activeToolTab === tool.id ? 'text-accent' : ''" />
          {{ tool.label }}
        </button>
      </div>

      <div class="h-14 px-4 flex items-center gap-4 overflow-x-auto">
        <!-- Trim -->
        <template v-if="activeToolTab === 'trim'">
          <button @click="setInPoint" class="h-8 px-3 rounded-lg bg-surface-2 hover:bg-surface-3 border border-border text-text font-medium cursor-pointer flex items-center gap-2">
            Set IN <kbd class="px-1 text-[10px] rounded border border-border text-text-3 font-mono">I</kbd>
          </button>
          <button @click="setOutPoint" class="h-8 px-3 rounded-lg bg-surface-2 hover:bg-surface-3 border border-border text-text font-medium cursor-pointer flex items-center gap-2">
            Set OUT <kbd class="px-1 text-[10px] rounded border border-border text-text-3 font-mono">O</kbd>
          </button>
          <template v-if="currentMix.trim">
            <button @click="clearTrim" class="h-8 px-2.5 rounded-lg text-text-3 hover:text-danger hover:bg-danger/10 cursor-pointer flex items-center gap-1">
              <X :size="13" /> Clear
            </button>
            <div class="h-6 w-px bg-border" />
            <span class="text-text-3">Cut:</span>
            <div class="h-8 flex items-center bg-surface-2 border border-border rounded-lg p-0.5">
              <button
                v-for="m in ([['accurate', 'Accurate', 'Re-encode, frame-accurate'], ['fast', 'Fast', 'No re-encode (-c:v copy), cuts on keyframes']] as const)"
                :key="m[0]"
                @click="currentMix.trim.mode = m[0]; pushHistory()"
                class="h-full px-3 rounded-md cursor-pointer"
                :class="currentMix.trim.mode === m[0] ? 'bg-surface-3 text-text shadow-sm' : 'text-text-3 hover:text-text'"
                :title="m[2]"
              >{{ m[1] }}</button>
            </div>
          </template>
          <span v-else class="text-text-3">Set points at the playhead or use the I / O keys.</span>
        </template>

        <!-- Speed -->
        <template v-else-if="activeToolTab === 'speed'">
          <span class="text-text-3">Export speed:</span>
          <div class="flex items-center gap-1.5">
            <button
              v-for="sp in [0.25, 0.5, 1, 1.5, 2]"
              :key="sp"
              @click="setSpeed(sp)"
              class="chip mono-num"
              :class="currentMix.speed === sp ? 'chip-on' : ''"
            >{{ sp }}×</button>
          </div>
        </template>

        <!-- Crop -->
        <template v-else-if="activeToolTab === 'crop'">
          <span class="text-text-3">Format:</span>
          <button @click="setVerticalCrop(false)" class="chip" :class="currentMix.crop === null ? 'chip-on' : ''">
            <span class="w-4 h-2.5 rounded-[2px] border border-current" /> Original {{ clip.width }}×{{ clip.height }}
          </button>
          <button @click="setVerticalCrop(true)" class="chip" :class="currentMix.crop !== null ? 'chip-on' : ''">
            <span class="w-2.5 h-4 rounded-[2px] border border-current" /> Vertical 9:16 · centre of frame
          </button>
        </template>

        <!-- Fades -->
        <template v-else-if="activeToolTab === 'effects'">
          <span class="text-text-3">Video — fade in and fade out:</span>
          <label class="flex items-center gap-2 text-text-2">
            At start
            <input type="number" min="0" max="5" step="0.5" v-model.number="currentMix.video_fade.in"
              class="w-16 h-8 bg-surface-2 border border-border rounded-lg px-2 text-text mono-num focus:outline-none focus:border-accent/60" />
            s
          </label>
          <label class="flex items-center gap-2 text-text-2">
            At end
            <input type="number" min="0" max="5" step="0.5" v-model.number="currentMix.video_fade.out"
              class="w-16 h-8 bg-surface-2 border border-border rounded-lg px-2 text-text mono-num focus:outline-none focus:border-accent/60" />
            s
          </label>
          <span class="text-text-3 text-[11px]">Visible in the export only.</span>
        </template>

        <!-- Tags -->
        <template v-else-if="activeToolTab === 'tags'">
          <form @submit.prevent="addTag" class="flex items-center gap-1.5 shrink-0">
            <input
              type="text"
              placeholder="New tag…"
              v-model="newTagName"
              class="w-40 h-8 bg-surface-2 border border-border rounded-lg px-2.5 text-text placeholder:text-text-3 focus:outline-none focus:border-accent/60"
            />
            <button type="submit" :disabled="!newTagName.trim()" class="h-8 px-3 bg-accent text-white rounded-lg font-medium cursor-pointer disabled:opacity-40 flex items-center gap-1">
              <Plus :size="13" /> Add
            </button>
          </form>
          <div class="flex items-center gap-1.5">
            <span
              v-for="t in clip.tags"
              :key="t.id"
              class="h-7 flex items-center gap-1 pl-2.5 pr-1 rounded-full bg-surface-2 border border-border text-text-2 whitespace-nowrap"
            >
              <span :style="{ color: t.color }">#</span>{{ t.name }}
              <button @click="removeTag(t.id)" class="w-5 h-5 rounded-full flex items-center justify-center text-text-3 hover:text-danger hover:bg-danger/10 cursor-pointer" :title="`Remove tag ${t.name}`">
                <X :size="11" />
              </button>
            </span>
            <span v-if="!clip.tags.length" class="text-text-3">No tags.</span>
          </div>
        </template>

        <!-- Export -->
        <template v-else-if="activeToolTab === 'export'">
          <div class="flex items-center gap-1.5">
            <button
              v-for="p in EXPORT_PRESETS"
              :key="p.id"
              @click="exportPreset = p.id"
              class="h-10 px-3 rounded-lg border text-left cursor-pointer whitespace-nowrap"
              :class="exportPreset === p.id ? 'border-accent/60 bg-accent/15' : 'border-border bg-surface-2 hover:border-border-strong'"
            >
              <div class="font-medium leading-tight" :class="exportPreset === p.id ? 'text-text' : 'text-text-2'">{{ p.label }}</div>
              <div class="text-[10px] text-text-3 leading-tight">{{ p.hint }}</div>
            </button>
          </div>
          <button
            @click="triggerExport"
            :disabled="isExporting"
            class="ml-auto shrink-0 h-9 px-4 bg-accent hover:bg-accent/90 text-white rounded-lg font-medium flex items-center gap-1.5 cursor-pointer disabled:opacity-50"
          >
            <RefreshCw v-if="isExporting" :size="14" class="animate-spin" />
            <Download v-else :size="14" />
            {{ isExporting ? 'Queuing…' : 'Export' }}
          </button>
        </template>
      </div>
    </div>
  </div>
</template>
