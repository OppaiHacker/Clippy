<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue';
import { Star, LayoutGrid, List, Play, Mic, Film, Trash2, Check, RotateCcw, X, ArrowLeft } from 'lucide-vue-next';
import { Clip, TrackKind } from '../types';
import { updateClip, deleteClip, restoreClip } from '../api/client';
import { plural } from '../format';

const props = defineProps<{
  clips: Clip[];
  selectedClipIds: Set<number>;
  searchQuery: string;
  trash: boolean;
}>();

const emit = defineEmits<{
  (e: 'update:selectedClipIds', ids: Set<number>): void;
  (e: 'open-clip', clip: Clip): void;
  (e: 'refresh'): void;
  (e: 'update:trash', value: boolean): void;
}>();

const TRASH_RETENTION_DAYS = 30;

const daysLeftInTrash = (deletedAt: string | null): number => {
  if (!deletedAt) return TRASH_RETENTION_DAYS;
  const elapsedDays = (Date.now() - new Date(deletedAt).getTime()) / 86400000;
  return Math.max(0, Math.ceil(TRASH_RETENTION_DAYS - elapsedDays));
};

const viewMode = ref<'grid' | 'list'>('grid');
const selectedGame = ref<string | null>(null);
const selectedTags = ref<Set<string>>(new Set());
const tagFilterMode = ref<'or' | 'and'>('or');
const hasMicOnly = ref(false);
const starredOnly = ref(false);
const maxDuration = ref<number>(0); // 0 = any length
const sortBy = ref<'date_desc' | 'date_asc' | 'dur_desc' | 'dur_asc' | 'size_desc'>('date_desc');

// Hover sprite frames (0..39)
const hoveredSpriteFrames = ref<Record<number, number>>({});

const KIND_COLORS: Record<TrackKind, string> = {
  system: 'bg-trk-system',
  app: 'bg-trk-app',
  mic: 'bg-trk-mic',
  device: 'bg-trk-device',
  imported: 'bg-trk-imported',
};

const KIND_LABELS: Record<TrackKind, string> = {
  system: 'Game / system',
  app: 'App',
  mic: 'Microphone',
  device: 'Device',
  imported: 'Imported',
};

function formatDuration(sec: number): string {
  const m = Math.floor(sec / 60);
  const s = Math.floor(sec % 60);
  return `${m}:${s.toString().padStart(2, '0')}`;
}

const gameCounts = computed(() => {
  const counts: Record<string, number> = {};
  props.clips.forEach(c => {
    const g = c.game || 'Other';
    counts[g] = (counts[g] || 0) + 1;
  });
  return counts;
});

const tagCounts = computed(() => {
  const counts: Record<string, number> = {};
  props.clips.forEach(c => {
    c.tags.forEach(t => {
      counts[t.name] = (counts[t.name] || 0) + 1;
    });
  });
  return counts;
});

const tagColors = computed(() => Object.fromEntries(props.clips.flatMap(c => c.tags.map(t => [t.name, t.color]))));

const filteredClips = computed(() => {
  return props.clips.filter(c => {
    if (props.searchQuery) {
      const q = props.searchQuery.toLowerCase();
      const matchTitle = c.title?.toLowerCase().includes(q);
      const matchFilename = c.filename.toLowerCase().includes(q);
      const matchGame = c.game?.toLowerCase().includes(q);
      const matchNotes = c.notes?.toLowerCase().includes(q);
      const matchTags = c.tags.some(t => t.name.toLowerCase().includes(q));
      if (!matchTitle && !matchFilename && !matchGame && !matchNotes && !matchTags) {
        return false;
      }
    }

    if (selectedGame.value && (c.game || 'Other') !== selectedGame.value) {
      return false;
    }

    if (starredOnly.value && !c.starred) {
      return false;
    }

    if (hasMicOnly.value) {
      const hasMic = c.audio_tracks.some(t => t.kind === 'mic');
      if (!hasMic) return false;
    }

    if (maxDuration.value && c.duration_s > maxDuration.value) {
      return false;
    }

    if (selectedTags.value.size > 0) {
      const clipTagNames = new Set(c.tags.map(t => t.name));
      if (tagFilterMode.value === 'and') {
        for (const t of selectedTags.value) {
          if (!clipTagNames.has(t)) return false;
        }
      } else {
        let hasAny = false;
        for (const t of selectedTags.value) {
          if (clipTagNames.has(t)) {
            hasAny = true;
            break;
          }
        }
        if (!hasAny) return false;
      }
    }

    return true;
  }).sort((a, b) => {
    if (sortBy.value === 'date_asc') return (a.saved_at || '').localeCompare(b.saved_at || '');
    if (sortBy.value === 'dur_desc') return b.duration_s - a.duration_s;
    if (sortBy.value === 'dur_asc') return a.duration_s - b.duration_s;
    if (sortBy.value === 'size_desc') return b.size_bytes - a.size_bytes;
    return (b.saved_at || '').localeCompare(a.saved_at || '');
  });
});

const toggleSelectClip = (id: number, e: MouseEvent) => {
  e.stopPropagation();
  const next = new Set(props.selectedClipIds);
  if (next.has(id)) next.delete(id);
  else next.add(id);
  emit('update:selectedClipIds', next);
};

const handleSelectAll = () => {
  if (props.selectedClipIds.size === filteredClips.value.length) {
    emit('update:selectedClipIds', new Set());
  } else {
    emit('update:selectedClipIds', new Set(filteredClips.value.map(c => c.id)));
  }
};

const toggleStar = async (clip: Clip, e: MouseEvent) => {
  e.stopPropagation();
  try {
    await updateClip(clip.id, { starred: !clip.starred });
    emit('refresh');
  } catch (err) {
    console.error(err);
  }
};

const deleteSelected = async () => {
  const count = props.selectedClipIds.size;
  if (count === 0) return;
  const n = `${count} ${plural(count, 'clip')}`;
  const message = props.trash
    ? `Delete ${n} FOREVER? The files will be removed from disk.`
    : `Move ${n} to the trash? They will be removed from disk after ${TRASH_RETENTION_DAYS} days.`;
  if (!confirm(message)) return;

  for (const id of props.selectedClipIds) {
    try {
      await deleteClip(id, props.trash);
    } catch (e) {
      console.error(e);
    }
  }
  emit('update:selectedClipIds', new Set());
  emit('refresh');
};

const restoreSelected = async () => {
  if (props.selectedClipIds.size === 0) return;
  for (const id of props.selectedClipIds) {
    try {
      await restoreClip(id);
    } catch (e) {
      console.error(e);
    }
  }
  emit('update:selectedClipIds', new Set());
  emit('refresh');
};

const toggleTag = (tagName: string) => {
  const next = new Set(selectedTags.value);
  if (next.has(tagName)) next.delete(tagName);
  else next.add(tagName);
  selectedTags.value = next;
};

const resetFilters = () => {
  selectedGame.value = null;
  selectedTags.value = new Set();
  hasMicOnly.value = false;
  starredOnly.value = false;
  maxDuration.value = 0;
};

const onKeydown = (e: KeyboardEvent) => {
  const t = e.target;
  if (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement || t instanceof HTMLSelectElement) return;
  if (document.querySelector('[aria-modal="true"]')) return;
  if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'a') {
    e.preventDefault();
    emit('update:selectedClipIds', new Set(filteredClips.value.map(c => c.id)));
  } else if (e.key === 'Escape' && props.selectedClipIds.size) {
    emit('update:selectedClipIds', new Set());
  } else if (e.key === 'Delete') {
    deleteSelected();
  }
};
onMounted(() => window.addEventListener('keydown', onKeydown));
onUnmounted(() => window.removeEventListener('keydown', onKeydown));

// Sprite hover handling
const onMouseMove = (clipId: number, e: MouseEvent) => {
  const target = e.currentTarget as HTMLElement;
  const rect = target.getBoundingClientRect();
  const x = Math.max(0, Math.min(rect.width, e.clientX - rect.left));
  const ratio = x / rect.width;
  const frameIndex = Math.min(39, Math.floor(ratio * 40));
  hoveredSpriteFrames.value = { ...hoveredSpriteFrames.value, [clipId]: frameIndex };
};

const onMouseLeave = (clipId: number) => {
  const next = { ...hoveredSpriteFrames.value };
  delete next[clipId];
  hoveredSpriteFrames.value = next;
};

const totalSizeGb = computed(() => props.clips.reduce((acc, c) => acc + c.size_bytes, 0) / 1024 ** 3);

const hasActiveFilters = computed(() =>
  !!selectedGame.value || selectedTags.value.size > 0 || hasMicOnly.value || starredOnly.value || maxDuration.value > 0);

const clipTime = (c: Clip) =>
  c.saved_at ? new Date(c.saved_at).toLocaleString(undefined, { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }) : '';
const clipMb = (c: Clip) => `${(c.size_bytes / 1024 ** 2).toFixed(0)} MB`;
</script>

<template>
  <main class="flex-1 min-w-0 flex flex-col overflow-hidden bg-bg relative">
    <!-- Header -->
    <header class="px-6 pt-5 pb-3 shrink-0 space-y-3 border-b border-border bg-surface/40">
      <div class="flex items-end justify-between gap-4">
        <div class="min-w-0">
          <h1 class="text-xl font-semibold tracking-tight text-text flex items-center gap-2">
            <template v-if="trash"><Trash2 :size="18" class="text-danger" /> Trash</template>
            <template v-else>Library</template>
          </h1>
          <p class="text-xs text-text-3 mt-0.5 mono-num">
            {{ clips.length }} {{ plural(clips.length, 'clip') }} · {{ totalSizeGb.toFixed(1) }} GB
            <template v-if="filteredClips.length !== clips.length"> · {{ filteredClips.length }} shown</template>
            <template v-if="trash"> · purged after {{ TRASH_RETENTION_DAYS }} days</template>
          </p>
        </div>

        <div class="flex items-center gap-2 text-xs shrink-0">
          <button
            @click="emit('update:trash', !trash)"
            class="h-8 flex items-center gap-1.5 px-3 rounded-lg border cursor-pointer"
            :class="trash
              ? 'border-border bg-surface-2 text-text hover:bg-surface-3'
              : 'border-transparent text-text-3 hover:text-text hover:bg-surface-2'"
          >
            <ArrowLeft v-if="trash" :size="14" />
            <Trash2 v-else :size="14" />
            <span>{{ trash ? 'Back to library' : 'Trash' }}</span>
          </button>

          <select
            v-model="sortBy"
            class="h-8 bg-surface-2 border border-border rounded-lg px-2.5 text-xs text-text focus:outline-none focus:border-accent/60 cursor-pointer"
            title="Sort"
          >
            <option value="date_desc">Newest</option>
            <option value="date_asc">Oldest</option>
            <option value="dur_desc">Longest</option>
            <option value="dur_asc">Shortest</option>
            <option value="size_desc">Largest</option>
          </select>

          <div class="h-8 flex items-center bg-surface-2 border border-border rounded-lg p-0.5">
            <button
              v-for="m in (['grid', 'list'] as const)"
              :key="m"
              @click="viewMode = m"
              class="h-full px-2 rounded-md cursor-pointer"
              :class="viewMode === m ? 'bg-surface-3 text-text shadow-sm' : 'text-text-3 hover:text-text'"
              :title="m === 'grid' ? 'Grid view' : 'List view'"
            >
              <LayoutGrid v-if="m === 'grid'" :size="14" />
              <List v-else :size="14" />
            </button>
          </div>
        </div>
      </div>

      <!-- Filters: games + toggles -->
      <div class="flex items-center gap-2 text-xs">
        <div class="flex-1 min-w-0 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          <button
            @click="selectedGame = null"
            class="chip"
            :class="!selectedGame ? 'chip-on' : ''"
          >
            All
          </button>
          <button
            v-for="(count, game) in gameCounts"
            :key="game"
            @click="selectedGame = selectedGame === game ? null : String(game)"
            class="chip"
            :class="selectedGame === game ? 'chip-on' : ''"
          >
            {{ game }} <span class="mono-num opacity-60">{{ count }}</span>
          </button>
        </div>

        <div class="flex items-center gap-1.5 shrink-0 pl-2 border-l border-border">
          <button @click="starredOnly = !starredOnly" class="chip" :class="starredOnly ? 'chip-on' : ''" title="Starred only">
            <Star :size="12" :class="starredOnly ? 'fill-warning text-warning' : ''" /> Starred
          </button>
          <button @click="hasMicOnly = !hasMicOnly" class="chip" :class="hasMicOnly ? 'chip-on' : ''" title="Only clips with a mic track">
            <Mic :size="12" :class="hasMicOnly ? 'text-trk-mic' : ''" /> Mic
          </button>
          <select
            v-model.number="maxDuration"
            class="h-7 bg-surface-2 border border-border rounded-full px-2.5 text-xs text-text-2 focus:outline-none cursor-pointer"
            title="Maximum length"
          >
            <option :value="0">Any length</option>
            <option :value="15">up to 15 s</option>
            <option :value="30">up to 30 s</option>
            <option :value="60">up to 1 min</option>
            <option :value="120">up to 2 min</option>
          </select>
          <button v-if="hasActiveFilters" @click="resetFilters" class="chip text-accent" title="Clear filters">
            <X :size="12" /> Clear
          </button>
        </div>
      </div>

      <!-- Tags -->
      <div v-if="Object.keys(tagCounts).length" class="flex items-center gap-2 text-xs">
        <div class="flex items-center bg-surface-2 border border-border rounded-full p-0.5 shrink-0 text-[10px] font-semibold">
          <button
            v-for="m in (['or', 'and'] as const)"
            :key="m"
            @click="tagFilterMode = m"
            class="px-2 py-0.5 rounded-full cursor-pointer uppercase"
            :class="tagFilterMode === m ? 'bg-surface-3 text-accent' : 'text-text-3 hover:text-text'"
            :title="m === 'or' ? 'Any of the selected tags' : 'All selected tags'"
          >
            {{ m }}
          </button>
        </div>
        <div class="flex-1 min-w-0 flex items-center gap-1.5 overflow-x-auto no-scrollbar">
          <button
            v-for="(count, tag) in tagCounts"
            :key="tag"
            @click="toggleTag(String(tag))"
            class="chip"
            :class="selectedTags.has(String(tag)) ? 'chip-on' : ''"
          >
            <span :style="{ color: tagColors[tag] }">#</span>{{ tag }} <span class="mono-num opacity-60">{{ count }}</span>
          </button>
        </div>
      </div>
    </header>

    <!-- Clips -->
    <div class="flex-1 overflow-y-auto px-6 pb-24">
      <div v-if="filteredClips.length === 0" class="h-full flex flex-col items-center justify-center text-center gap-3">
        <div class="w-14 h-14 rounded-2xl bg-surface-2 border border-border flex items-center justify-center">
          <Trash2 v-if="trash" :size="22" class="text-text-3" />
          <Film v-else :size="22" class="text-text-3" />
        </div>
        <div>
          <p class="text-sm font-semibold text-text">{{ trash ? 'Trash is empty' : clips.length ? 'Nothing matches the filters' : 'No clips yet' }}</p>
          <p class="text-xs text-text-3 mt-1">
            {{ trash ? 'Deleted clips stay here for ' + TRASH_RETENTION_DAYS + ' days.' : clips.length ? 'Change or clear the filters.' : 'Save a clip from the buffer and it shows up here automatically.' }}
          </p>
        </div>
        <button v-if="hasActiveFilters" @click="resetFilters" class="h-8 px-3.5 rounded-lg bg-surface-2 border border-border text-xs text-text hover:bg-surface-3 cursor-pointer">
          Clear filters
        </button>
      </div>

      <section v-else class="pt-5">

        <!-- Grid -->
        <div v-if="viewMode === 'grid'" class="grid grid-cols-[repeat(auto-fill,minmax(250px,1fr))] gap-4">
          <div
            v-for="(clip, idx) in filteredClips"
            :key="clip.id"
            @click="emit('open-clip', clip)"
            :style="{ '--i': Math.min(idx, 24) }"
            :title="clip.filename"
            class="card-in group relative bg-surface rounded-xl border cursor-pointer flex flex-col overflow-hidden
                   transition-[transform,box-shadow,border-color] duration-200 will-change-transform
                   hover:-translate-y-1 hover:shadow-[0_14px_36px_-14px] hover:shadow-accent/50"
            :class="selectedClipIds.has(clip.id) ? 'border-accent ring-1 ring-accent' : 'border-border hover:border-accent/40'"
          >
            <!-- Thumbnail + sprite preview -->
            <div
              @mousemove="onMouseMove(clip.id, $event)"
              @mouseleave="onMouseLeave(clip.id)"
              class="relative aspect-video bg-black overflow-hidden"
            >
              <img
                :src="`/api/clips/${clip.id}/thumb?v=${clip.thumb_version}`"
                :alt="clip.filename"
                class="w-full h-full object-cover transition-[opacity,transform] duration-300 group-hover:scale-[1.04]"
                :class="hoveredSpriteFrames[clip.id] !== undefined ? 'opacity-0' : 'opacity-100'"
                loading="lazy"
              />
              <div
                v-if="hoveredSpriteFrames[clip.id] !== undefined"
                class="absolute inset-0"
                :style="{
                  backgroundImage: `url(/api/clips/${clip.id}/sprite?v=${clip.thumb_version})`,
                  backgroundPosition: `${((hoveredSpriteFrames[clip.id] % 8) / 7) * 100}% ${(Math.floor(hoveredSpriteFrames[clip.id] / 8) / 4) * 100}%`,
                  backgroundSize: '800% 500%',
                }"
              />
              <!-- Preview progress bar -->
              <div
                v-if="hoveredSpriteFrames[clip.id] !== undefined"
                class="absolute bottom-0 left-0 h-0.5 bg-accent"
                :style="{ width: `${((hoveredSpriteFrames[clip.id] + 1) / 40) * 100}%` }"
              />
              <div class="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-black/70 to-transparent pointer-events-none" />

              <div class="absolute top-2 left-2 right-2 flex items-center justify-between">
                <button
                  @click="toggleSelectClip(clip.id, $event)"
                  class="w-6 h-6 rounded-md border flex items-center justify-center backdrop-blur cursor-pointer transition-opacity"
                  :class="selectedClipIds.has(clip.id)
                    ? 'bg-accent border-accent text-white opacity-100'
                    : 'bg-black/40 border-white/30 text-transparent hover:border-white/70 ' + (selectedClipIds.size ? 'opacity-100' : 'opacity-0 group-hover:opacity-100')"
                  :title="selectedClipIds.has(clip.id) ? 'Deselect' : 'Select'"
                >
                  <Check :size="14" :stroke-width="3" />
                </button>
                <button
                  @click="toggleStar(clip, $event)"
                  class="w-6 h-6 rounded-md bg-black/40 backdrop-blur flex items-center justify-center cursor-pointer transition-opacity"
                  :class="clip.starred ? 'opacity-100' : 'opacity-0 group-hover:opacity-100'"
                  :title="clip.starred ? 'Unstar' : 'Star'"
                >
                  <Star :size="13" :class="clip.starred ? 'fill-warning text-warning' : 'text-white/80'" />
                </button>
              </div>

              <div class="absolute bottom-2 right-2 px-1.5 py-0.5 rounded-md bg-black/60 backdrop-blur text-[11px] mono-num text-white">
                {{ formatDuration(clip.duration_s) }}
              </div>
              <div v-if="trash" class="absolute bottom-2 left-2 px-1.5 py-0.5 rounded-md bg-danger/85 text-[11px] text-white">
                {{ daysLeftInTrash(clip.deleted_at) }} d
              </div>

              <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity pointer-events-none">
                <div class="w-11 h-11 rounded-full bg-white/15 backdrop-blur-md border border-white/25 text-white flex items-center justify-center
                            scale-75 group-hover:scale-100 transition-transform duration-200">
                  <Play :size="17" class="ml-0.5 fill-white" />
                </div>
              </div>
            </div>

            <!-- Details -->
            <div class="p-3 flex flex-col gap-2 flex-1">
              <div class="min-w-0">
                <div class="text-[13px] font-semibold text-text truncate">{{ clip.title || clip.game || 'Untitled' }}</div>
                <div class="mt-0.5 flex items-center gap-1.5 text-[11px] text-text-3 mono-num">
                  <template v-if="clip.title"><span class="text-accent font-sans font-medium truncate">{{ clip.game || 'Other' }}</span><span>·</span></template>
                  <span>{{ clipTime(clip) }}</span><span>·</span><span>{{ clipMb(clip) }}</span>
                </div>
              </div>

              <div class="flex items-center gap-1" title="Audio tracks">
                <div
                  v-for="track in clip.audio_tracks"
                  :key="track.id"
                  class="h-1 flex-1 rounded-full opacity-80"
                  :class="KIND_COLORS[track.kind]"
                  :title="`${track.display_name} (${KIND_LABELS[track.kind]})`"
                />
              </div>

              <div v-if="clip.tags.length > 0" class="flex flex-wrap gap-1">
                <span
                  v-for="tag in clip.tags.slice(0, 3)"
                  :key="tag.id"
                  class="px-1.5 py-px rounded-md text-[10px] bg-surface-3 text-text-2 truncate max-w-[90px]"
                ><span :style="{ color: tag.color }">#</span>{{ tag.name }}</span>
                <span v-if="clip.tags.length > 3" class="text-[10px] text-text-3 self-center">+{{ clip.tags.length - 3 }}</span>
              </div>
            </div>
          </div>
        </div>

        <!-- List -->
        <div v-else class="bg-surface rounded-xl border border-border divide-y divide-border text-xs overflow-hidden">
          <div
            v-for="clip in filteredClips"
            :key="clip.id"
            @click="emit('open-clip', clip)"
            class="group flex items-center gap-4 px-3 py-2 hover:bg-surface-2 cursor-pointer transition-colors"
            :class="selectedClipIds.has(clip.id) ? 'bg-accent/[0.07]' : ''"
          >
            <button
              @click="toggleSelectClip(clip.id, $event)"
              class="w-5 h-5 rounded-md border flex items-center justify-center shrink-0 cursor-pointer"
              :class="selectedClipIds.has(clip.id) ? 'bg-accent border-accent text-white' : 'border-border-strong text-transparent hover:border-text-3'"
            >
              <Check :size="12" :stroke-width="3" />
            </button>

            <div class="w-24 aspect-video bg-black rounded-md overflow-hidden relative shrink-0">
              <img :src="`/api/clips/${clip.id}/thumb?v=${clip.thumb_version}`" alt="" class="w-full h-full object-cover" loading="lazy" />
              <div v-if="trash" class="absolute bottom-0.5 left-0.5 px-1 rounded bg-danger/85 text-[9px] text-white">{{ daysLeftInTrash(clip.deleted_at) }} d</div>
            </div>

            <div class="min-w-0 flex-1">
              <div class="font-semibold text-text truncate">{{ clip.title || clip.game || 'Untitled' }}</div>
              <div class="flex items-center gap-1.5 text-[11px] text-text-3 min-w-0">
                <span class="text-accent font-medium shrink-0">{{ clip.game || 'Other' }}</span>
                <span>·</span>
                <span class="truncate">{{ clip.filename }}</span>
              </div>
            </div>

            <div class="hidden lg:flex items-center gap-1 w-28 shrink-0">
              <div
                v-for="track in clip.audio_tracks"
                :key="track.id"
                class="h-1 flex-1 rounded-full opacity-80"
                :class="KIND_COLORS[track.kind]"
                :title="`${track.display_name} (${KIND_LABELS[track.kind]})`"
              />
            </div>

            <span class="mono-num text-text-3 w-28 text-right shrink-0">{{ clipTime(clip) }}</span>
            <span class="mono-num text-text w-12 text-right shrink-0">{{ formatDuration(clip.duration_s) }}</span>
            <span class="mono-num text-text-3 w-16 text-right shrink-0">{{ clipMb(clip) }}</span>

            <button @click="toggleStar(clip, $event)" class="shrink-0 text-text-3 hover:text-warning cursor-pointer" :title="clip.starred ? 'Unstar' : 'Star'">
              <Star :size="15" :class="clip.starred ? 'fill-warning text-warning' : 'opacity-0 group-hover:opacity-100'" />
            </button>
          </div>
        </div>
      </section>
    </div>

    <!-- Floating selection bar -->
    <Transition name="view">
      <div
        v-if="selectedClipIds.size > 0"
        class="absolute bottom-5 left-1/2 -translate-x-1/2 flex items-center gap-1 p-1.5 pl-4 rounded-xl bg-surface-3/90 backdrop-blur border border-border-strong shadow-2xl shadow-black/60 text-xs"
      >
        <span class="font-medium text-text mono-num mr-2">{{ selectedClipIds.size }} selected</span>
        <button @click="handleSelectAll" class="h-8 px-3 rounded-lg text-text-2 hover:text-text hover:bg-white/5 cursor-pointer">
          {{ selectedClipIds.size === filteredClips.length ? 'Deselect all' : `Select all (${filteredClips.length})` }}
        </button>
        <button v-if="trash" @click="restoreSelected" class="h-8 px-3 rounded-lg flex items-center gap-1.5 text-accent hover:bg-accent/15 cursor-pointer">
          <RotateCcw :size="13" /> Restore
        </button>
        <button @click="deleteSelected" class="h-8 px-3 rounded-lg flex items-center gap-1.5 text-danger hover:bg-danger/15 cursor-pointer">
          <Trash2 :size="13" /> {{ trash ? 'Delete forever' : 'Move to trash' }}
        </button>
        <button @click="emit('update:selectedClipIds', new Set())" class="h-8 w-8 rounded-lg flex items-center justify-center text-text-3 hover:text-text hover:bg-white/5 cursor-pointer" title="Clear selection">
          <X :size="14" />
        </button>
      </div>
    </Transition>
  </main>
</template>
