<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { Download, Trash2, X, Copy, Check, FileAudio, RefreshCw, AlertTriangle, Clock, CheckCircle2, Inbox, Play } from 'lucide-vue-next';
import { fetchExports, fetchJobs, deleteExport, cancelJob } from '../api/client';
import { Clip, ExportItem, Job } from '../types';
import { plural, formatDuration } from '../format';

const props = defineProps<{
  clips: Clip[];
}>();

const exportsList = ref<ExportItem[]>([]);
const jobsList = ref<Job[]>([]);
const copiedId = ref<number | null>(null);
const playingId = ref<number | null>(null);
const hoverFrame = ref<{ id: number; frame: number } | null>(null);
const loaded = ref(false);

let pollTimer: any = null;

const refreshData = async () => {
  try {
    const [exp, jobs] = await Promise.all([fetchExports(), fetchJobs()]);
    exportsList.value = exp;
    jobsList.value = jobs;
  } catch (e) {}
  loaded.value = true;
};

onMounted(() => {
  refreshData();
  pollTimer = setInterval(refreshData, 2000);
});

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer);
});

const handleCancelJob = async (jobId: number) => {
  try {
    await cancelJob(jobId);
    refreshData();
  } catch (e) {}
};

const handleDeleteExport = async (exp: ExportItem) => {
  if (!confirm(`Delete file ${exp.filename}?`)) return;
  try {
    await deleteExport(exp.id);
    refreshData();
  } catch (e) {}
};

const copyPath = (id: number, path: string) => {
  navigator.clipboard.writeText(path);
  copiedId.value = id;
  setTimeout(() => {
    copiedId.value = null;
  }, 2000);
};

const STATE: Record<Job['state'], { label: string; cls: string; icon: any }> = {
  pending: { label: 'Queued', cls: 'bg-surface-3 text-text-2', icon: Clock },
  running: { label: 'Running', cls: 'bg-accent/15 text-accent', icon: RefreshCw },
  done: { label: 'Done', cls: 'bg-success/15 text-success', icon: CheckCircle2 },
  error: { label: 'Error', cls: 'bg-danger/15 text-danger', icon: AlertTriangle },
  cancelled: { label: 'Cancelled', cls: 'bg-surface-3 text-text-3', icon: X },
};

const PRESETS: Record<string, string> = {
  original: 'Original',
  discord: 'Discord',
  youtube: 'YouTube',
  vertical: 'Vertical 9:16',
  audio_only: 'Audio only',
};

const presetLabel = (p: string) => (p.startsWith('custom_') ? `Max ${p.slice(7)} MB` : PRESETS[p] || p);

const KINDS: Record<string, string> = { export: 'Export' };

const isActive = (j: Job) => j.state === 'running' || j.state === 'pending';
const activeCount = computed(() => jobsList.value.filter(isActive).length);
const exportsSizeMb = computed(() => exportsList.value.reduce((a, e) => a + e.size_bytes, 0) / 1024 ** 2);

const clipOf = (id: number) => props.clips.find(c => c.id === id);

// same sprite scrub as the library cards (8x5 sprite, 40 frames)
const onScrub = (id: number, e: MouseEvent) => {
  const r = (e.currentTarget as HTMLElement).getBoundingClientRect();
  hoverFrame.value = { id, frame: Math.min(39, Math.floor(Math.max(0, (e.clientX - r.left) / r.width) * 40)) };
};

const clipName = (id: number | null) => {
  const c = id !== null ? props.clips.find(c => c.id === id) : undefined;
  return c ? c.title || c.filename : id !== null ? `clip #${id}` : '';
};

const when = (iso: string) =>
  new Date(iso).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
</script>

<template>
  <main class="flex-1 min-w-0 flex flex-col overflow-hidden bg-bg text-xs">
    <header class="px-6 pt-5 pb-4 shrink-0 border-b border-border bg-surface/40">
      <h1 class="text-xl font-semibold tracking-tight text-text">Downloads</h1>
      <p class="text-xs text-text-3 mt-0.5 mono-num">
        {{ activeCount ? `${activeCount} running` : 'queue empty' }} · {{ exportsList.length }} {{ plural(exportsList.length, 'finished file') }} · {{ exportsSizeMb.toFixed(1) }} MB
      </p>
    </header>

    <!-- Queue: compact, scrolls on its own so it never takes the whole page -->
    <section v-if="jobsList.length" class="px-6 pt-5 shrink-0">
      <h2 class="text-[11px] font-semibold uppercase tracking-wider text-text-3 mb-2.5">Queue</h2>
      <div class="max-h-56 overflow-y-auto bg-surface rounded-xl border border-border divide-y divide-border">
        <div v-for="job in jobsList" :key="job.id" class="px-3 py-2 flex items-center gap-3">
          <span class="w-6 h-6 rounded-md flex items-center justify-center shrink-0" :class="STATE[job.state].cls">
            <component :is="STATE[job.state].icon" :size="13" :class="job.state === 'running' ? 'animate-spin' : ''" />
          </span>
          <div class="flex-1 min-w-0">
            <div class="flex items-center gap-2 min-w-0">
              <span class="font-semibold text-text truncate shrink-0">
                {{ KINDS[job.kind] || job.kind }}<template v-if="job.preset"> · {{ presetLabel(job.preset) }}</template>
              </span>
              <span class="text-text-3 truncate">{{ clipName(job.clip_id) }}</span>
            </div>
            <div v-if="isActive(job)" class="mt-1 h-1 bg-surface-3 rounded-full overflow-hidden max-w-md">
              <div class="h-full bg-accent rounded-full transition-[width] duration-300" :style="{ width: `${Math.round(job.progress * 100)}%` }" />
            </div>
            <div v-else-if="job.error" class="text-danger text-[11px] truncate" :title="job.error">{{ job.error }}</div>
          </div>
          <span class="px-2 py-0.5 rounded-full text-[10px] font-medium shrink-0" :class="STATE[job.state].cls">{{ STATE[job.state].label }}</span>
          <span class="mono-num text-text-3 w-24 text-right shrink-0">{{ isActive(job) ? `${Math.round(job.progress * 100)}%` : when(job.created_at) }}</span>
          <button
            v-if="isActive(job)"
            @click="handleCancelJob(job.id)"
            class="w-6 h-6 rounded-md flex items-center justify-center text-text-3 hover:text-danger hover:bg-danger/10 cursor-pointer shrink-0"
            title="Cancel job"
          >
            <X :size="13" />
          </button>
          <span v-else class="w-6 shrink-0" />
        </div>
      </div>
    </section>

    <!-- Finished files -->
    <div class="flex-1 overflow-y-auto px-6 py-5">
      <h2 class="text-[11px] font-semibold uppercase tracking-wider text-text-3 mb-2.5">Finished files</h2>

      <div v-if="loaded && !exportsList.length" class="py-14 flex flex-col items-center justify-center text-center gap-3 rounded-xl border border-dashed border-border">
        <div class="w-12 h-12 rounded-2xl bg-surface-2 border border-border flex items-center justify-center">
          <Inbox :size="20" class="text-text-3" />
        </div>
        <div>
          <p class="text-sm font-semibold text-text">No exported files</p>
          <p class="text-xs text-text-3 mt-1">Open a clip in the editor and pick Export.</p>
        </div>
      </div>

      <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-4">
        <div
          v-for="exp in exportsList"
          :key="exp.id"
          :title="exp.filename"
          class="group bg-surface rounded-xl border border-border hover:border-accent/40 flex flex-col overflow-hidden transition-colors"
          :class="exp.exists ? '' : 'opacity-60'"
        >
          <!-- Preview: the exported file itself when playing, else the clip thumbnail + sprite scrub -->
          <div class="relative aspect-video bg-black overflow-hidden">
            <video
              v-if="playingId === exp.id && exp.preset !== 'audio_only'"
              :src="`/api/exports/${exp.id}/stream`"
              class="w-full h-full object-contain"
              controls
              autoplay
            />
            <template v-else>
              <div
                class="absolute inset-0"
                :class="exp.exists ? 'cursor-pointer' : ''"
                @mousemove="onScrub(exp.id, $event)"
                @mouseleave="hoverFrame = null"
                @click="exp.exists && (playingId = exp.id)"
              >
                <img
                  v-if="clipOf(exp.clip_id)"
                  :src="`/api/clips/${exp.clip_id}/thumb?v=${clipOf(exp.clip_id)!.thumb_version}`"
                  alt=""
                  class="w-full h-full object-cover"
                  loading="lazy"
                />
                <div
                  v-if="hoverFrame?.id === exp.id && clipOf(exp.clip_id)"
                  class="absolute inset-0"
                  :style="{
                    backgroundImage: `url(/api/clips/${exp.clip_id}/sprite?v=${clipOf(exp.clip_id)!.thumb_version})`,
                    backgroundPosition: `${((hoverFrame.frame % 8) / 7) * 100}% ${(Math.floor(hoverFrame.frame / 8) / 4) * 100}%`,
                    backgroundSize: '800% 500%',
                  }"
                />
                <div class="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 to-transparent pointer-events-none" />
                <div v-if="exp.exists" class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                  <div class="w-11 h-11 rounded-full bg-white/15 backdrop-blur-md border border-white/25 text-white flex items-center justify-center">
                    <FileAudio v-if="exp.preset === 'audio_only'" :size="17" />
                    <Play v-else :size="17" class="ml-0.5 fill-white" />
                  </div>
                </div>
              </div>
              <div class="absolute top-2 left-2 px-1.5 py-0.5 rounded-md bg-black/60 backdrop-blur text-[11px] text-white pointer-events-none">
                {{ presetLabel(exp.preset) }}
              </div>
              <div class="absolute bottom-2 right-2 px-1.5 py-0.5 rounded-md bg-black/60 backdrop-blur text-[11px] mono-num text-white pointer-events-none">
                {{ formatDuration(exp.duration_s) }}
              </div>
            </template>
            <audio
              v-if="playingId === exp.id && exp.preset === 'audio_only'"
              :src="`/api/exports/${exp.id}/stream`"
              class="absolute inset-x-2 bottom-2 w-[calc(100%-1rem)]"
              controls
              autoplay
            />
          </div>

          <div class="p-3 flex items-center gap-2">
            <div class="flex-1 min-w-0">
              <div class="text-[13px] font-semibold text-text truncate">{{ clipName(exp.clip_id) }}</div>
              <div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-text-3 mono-num">
                <span>{{ (exp.size_bytes / 1024 ** 2).toFixed(1) }} MB</span>
                <span>·</span><span>{{ when(exp.created_at) }}</span>
              </div>
              <div v-if="!exp.exists" class="text-[11px] text-warning mt-0.5">File is gone from disk</div>
            </div>
            <button
              @click="copyPath(exp.id, exp.path)"
              class="w-8 h-8 rounded-lg flex items-center justify-center text-text-3 hover:text-text hover:bg-surface-2 cursor-pointer shrink-0"
              :title="copiedId === exp.id ? 'Copied' : 'Copy path'"
            >
              <Check v-if="copiedId === exp.id" :size="14" class="text-success" />
              <Copy v-else :size="14" />
            </button>
            <button
              @click="handleDeleteExport(exp)"
              class="w-8 h-8 rounded-lg flex items-center justify-center text-text-3 hover:text-danger hover:bg-danger/10 cursor-pointer shrink-0"
              title="Delete file"
            >
              <Trash2 :size="14" />
            </button>
            <a
              v-if="exp.exists"
              :href="`/api/exports/${exp.id}/download`"
              download
              class="w-8 h-8 bg-accent hover:bg-accent/90 text-white rounded-lg flex items-center justify-center shrink-0"
              title="Download"
            >
              <Download :size="14" />
            </a>
          </div>
        </div>
      </div>
    </div>
  </main>
</template>
