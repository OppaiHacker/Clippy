<script setup lang="ts">
import { ref, computed, onMounted } from 'vue';
import { RefreshCw, HardDrive, Folder, Keyboard, CircleDot, Check } from 'lucide-vue-next';
import { fetchSettings, triggerRescan } from '../api/client';
import { shortcuts } from '../shortcuts';

const emit = defineEmits<{
  (e: 'openShortcuts'): void;
}>();

const settingsData = ref<any>(null);
const isRescanning = ref(false);
const rescanTriggered = ref(false);

const loadSettings = async () => {
  try {
    settingsData.value = await fetchSettings();
  } catch (e) {}
};

onMounted(() => {
  loadSettings();
});

const handleRescan = async () => {
  isRescanning.value = true;
  try {
    await triggerRescan();
    rescanTriggered.value = true;
    setTimeout(() => {
      rescanTriggered.value = false;
      isRescanning.value = false;
      loadSettings();
    }, 3000);
  } catch (e) {
    isRescanning.value = false;
  }
};

const recordingShortcuts = shortcuts.filter(s => s.category === 'recording');

const diskUsedPct = computed(() => {
  const d = settingsData.value;
  return d?.disk_total_gb ? ((d.disk_total_gb - d.disk_free_gb) / d.disk_total_gb) * 100 : 0;
});

const cacheRows = computed(() => {
  const d = settingsData.value;
  if (!d) return [];
  return [
    { label: 'Extracted audio', mb: d.audio_size_mb, cls: 'bg-trk-system' },
    { label: 'Thumbnails and sprites', mb: d.thumbs_size_mb, cls: 'bg-trk-app' },
    { label: 'Waveforms', mb: d.waveforms_size_mb, cls: 'bg-trk-device' },
    { label: 'Imports and voiceover', mb: d.imports_size_mb ?? 0, cls: 'bg-trk-mic' },
    { label: 'Exports', mb: d.exports_size_mb, cls: 'bg-trk-imported' },
  ];
});
const cacheTotalMb = computed(() => cacheRows.value.reduce((a, r) => a + r.mb, 0));
</script>

<template>
  <main class="flex-1 min-w-0 flex flex-col overflow-hidden bg-bg text-xs">
    <header class="px-6 pt-5 pb-4 shrink-0 border-b border-border bg-surface/40">
      <h1 class="text-xl font-semibold tracking-tight text-text">Settings</h1>
      <p class="text-xs text-text-3 mt-0.5">Directories, storage and recording shortcuts</p>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-5 space-y-8">
      <section v-if="settingsData" class="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <!-- Directories -->
        <div class="p-4 bg-surface rounded-xl border border-border space-y-3">
          <div class="flex items-center gap-2 font-semibold text-text">
            <Folder :size="15" class="text-accent" /> Directories
          </div>
          <div class="space-y-2.5">
            <div>
              <div class="text-text-3 flex items-center gap-1.5">
                Clips <span class="px-1.5 rounded bg-surface-3 text-[10px]">read-only</span>
                <span v-if="settingsData.clips_exists === false" class="text-danger">· directory does not exist</span>
              </div>
              <div class="mt-0.5 font-mono text-text break-all select-text">{{ settingsData.clips_dir }}</div>
            </div>
            <div>
              <div class="text-text-3">Clippy work directory</div>
              <div class="mt-0.5 font-mono text-text break-all select-text">{{ settingsData.work_dir }}</div>
            </div>
          </div>
          <div class="pt-3 border-t border-border flex items-center justify-between gap-3">
            <div class="text-text-3">Looks for new files in the clips directory and refreshes metadata.</div>
            <button
              @click="handleRescan"
              :disabled="isRescanning"
              class="h-8 px-3 shrink-0 bg-surface-2 hover:bg-surface-3 border border-border rounded-lg text-text font-medium flex items-center gap-1.5 cursor-pointer disabled:opacity-60"
            >
              <Check v-if="rescanTriggered" :size="13" class="text-success" />
              <RefreshCw v-else :size="13" :class="isRescanning ? 'animate-spin' : ''" />
              {{ rescanTriggered ? 'Scanning…' : 'Rescan directory' }}
            </button>
          </div>
        </div>

        <!-- Disk -->
        <div class="p-4 bg-surface rounded-xl border border-border space-y-3">
          <div class="flex items-center justify-between">
            <div class="flex items-center gap-2 font-semibold text-text">
              <HardDrive :size="15" class="text-accent" /> Disk
            </div>
            <span class="mono-num text-text-2">{{ settingsData.disk_free_gb }} GB free of {{ settingsData.disk_total_gb }} GB</span>
          </div>
          <div class="h-2 rounded-full bg-surface-3 overflow-hidden">
            <div
              class="h-full rounded-full"
              :class="diskUsedPct > 90 ? 'bg-danger' : diskUsedPct > 75 ? 'bg-warning' : 'bg-accent'"
              :style="{ width: `${diskUsedPct}%` }"
            />
          </div>
          <div class="pt-3 border-t border-border space-y-1.5">
            <div class="flex items-center justify-between text-text-3">
              <span>Clippy data</span>
              <span class="mono-num text-text">{{ cacheTotalMb.toFixed(1) }} MB</span>
            </div>
            <div class="h-1.5 rounded-full bg-surface-3 overflow-hidden flex">
              <div
                v-for="r in cacheRows"
                :key="r.label"
                :class="r.cls"
                :style="{ width: `${cacheTotalMb ? (r.mb / cacheTotalMb) * 100 : 0}%` }"
                :title="`${r.label}: ${r.mb} MB`"
              />
            </div>
            <div class="grid grid-cols-2 gap-x-6 gap-y-1 pt-1">
              <div v-for="r in cacheRows" :key="r.label" class="flex items-center gap-2">
                <span class="w-2 h-2 rounded-full shrink-0" :class="r.cls" />
                <span class="text-text-3 flex-1">{{ r.label }}</span>
                <span class="mono-num text-text-2">{{ r.mb }} MB</span>
              </div>
            </div>
          </div>
        </div>
      </section>
      <section v-else class="grid grid-cols-1 lg:grid-cols-2 gap-3">
        <div class="skeleton h-44 rounded-xl" />
        <div class="skeleton h-44 rounded-xl" />
      </section>

      <!-- Recording shortcuts -->
      <section class="space-y-3">
        <div class="flex items-end justify-between gap-4">
          <div>
            <h2 class="text-sm font-semibold text-text flex items-center gap-2">
              <CircleDot :size="14" class="text-danger" /> Recording shortcuts
            </h2>
            <p class="text-text-3 mt-0.5">Global Hyprland binds for gpu-screen-recorder. They work outside the browser.</p>
          </div>
          <button
            @click="emit('openShortcuts')"
            class="h-8 px-3 shrink-0 bg-surface-2 hover:bg-surface-3 border border-border rounded-lg text-text flex items-center gap-1.5 cursor-pointer"
          >
            <Keyboard :size="14" class="text-accent" /> All shortcuts
            <kbd class="px-1.5 text-[10px] leading-4 rounded border border-border text-text-3 font-mono">?</kbd>
          </button>
        </div>

        <div class="bg-surface rounded-xl border border-border divide-y divide-border overflow-hidden">
          <div v-for="s in recordingShortcuts" :key="s.id" class="px-4 py-2.5 flex items-center gap-4">
            <div class="flex-1 min-w-0">
              <div class="font-medium text-text">{{ s.title }}</div>
              <div v-if="s.command" class="font-mono text-[10px] text-text-3 mt-0.5 truncate select-text">{{ s.command }}</div>
            </div>
            <div class="flex items-center gap-1 shrink-0">
              <kbd
                v-for="k in s.keys"
                :key="k"
                class="min-w-[28px] h-6 px-1.5 inline-flex items-center justify-center rounded-md bg-surface-2 border border-border-strong border-b-2 font-mono text-[11px] font-semibold text-text"
              >{{ k }}</kbd>
            </div>
          </div>
        </div>
      </section>
    </div>
  </main>
</template>
