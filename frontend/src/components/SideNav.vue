<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import { Film, Sliders, Download, Tag, Settings, Search, RefreshCw, Keyboard, Check, X, Power } from 'lucide-vue-next';
import { fetchRecorderStatus, toggleRecorder, fetchJobs, saveReplay } from '../api/client';
import { RecorderStatus } from '../types';

defineProps<{
  activeTab: string;
  searchQuery: string;
}>();

const emit = defineEmits<{
  (e: 'update:activeTab', tab: string): void;
  (e: 'update:searchQuery', q: string): void;
  (e: 'openShortcuts'): void;
}>();

const searchInputRef = ref<HTMLInputElement | null>(null);
const recorder = ref<RecorderStatus>({ status: 'checking', running: false, raw: '' });
const activeJobsCount = ref(0);
const isTogglingRecorder = ref(false);

const tabs = [
  { id: 'library', label: 'Library', icon: Film },
  { id: 'editor', label: 'Editor', icon: Sliders },
  { id: 'downloads', label: 'Downloads', icon: Download },
  { id: 'tags', label: 'Tags', icon: Tag },
  { id: 'settings', label: 'Settings', icon: Settings },
];

let intervalId: any = null;

const checkStatus = async () => {
  try {
    recorder.value = await fetchRecorderStatus();
  } catch (e) {}

  try {
    const jobs = await fetchJobs();
    activeJobsCount.value = jobs.filter(j => j.state === 'running' || j.state === 'pending').length;
  } catch (e) {}
};

onMounted(() => {
  checkStatus();
  intervalId = setInterval(checkStatus, 3000);
});

onUnmounted(() => {
  if (intervalId) clearInterval(intervalId);
});

const savingSeconds = ref<number | null>(null);
const savedFlash = ref(false);

const handleSaveReplay = async (seconds: number) => {
  savingSeconds.value = seconds;
  try {
    await saveReplay(seconds);
    savedFlash.value = true;
    setTimeout(() => (savedFlash.value = false), 1600);
  } catch (e) {
    alert('Could not save the clip: ' + e);
  } finally {
    savingSeconds.value = null;
  }
};

const handleToggleRecorder = async () => {
  isTogglingRecorder.value = true;
  try {
    recorder.value = await toggleRecorder();
  } catch (e) {
    alert('Could not toggle the recorder: ' + e);
  } finally {
    isTogglingRecorder.value = false;
  }
};

defineExpose({
  focusSearch: () => searchInputRef.value?.focus(),
});
</script>

<template>
  <aside class="w-60 shrink-0 bg-surface border-r border-border flex flex-col select-none z-30">
    <!-- Logo -->
    <div class="h-14 px-4 flex items-center gap-2.5 shrink-0">
      <img src="/logo.svg" alt="" class="w-8 h-8 rounded-[9px] shadow-[0_6px_20px_-6px] shadow-accent/60" />
      <div class="leading-tight">
        <div class="font-semibold text-[15px] tracking-tight text-text">Clippy</div>
        <div class="text-[10px] text-text-3 uppercase tracking-[0.14em]">clip vault</div>
      </div>
    </div>

    <!-- Search: typing switches to the library -->
    <div class="px-3 pb-3 shrink-0">
      <div class="relative">
        <Search :size="14" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-3 pointer-events-none" />
        <input
          ref="searchInputRef"
          type="text"
          placeholder="Search clips…"
          :value="searchQuery"
          @input="emit('update:searchQuery', ($event.target as HTMLInputElement).value); activeTab !== 'library' && emit('update:activeTab', 'library')"
          class="w-full h-8 bg-surface-2 border border-border rounded-lg pl-8 pr-8 text-xs text-text placeholder:text-text-3 focus:border-accent/60 focus:bg-surface-3 focus:outline-none transition-colors"
        />
        <button
          v-if="searchQuery"
          @click="emit('update:searchQuery', '')"
          class="absolute right-2 top-1/2 -translate-y-1/2 text-text-3 hover:text-text"
          title="Clear"
        >
          <X :size="13" />
        </button>
        <kbd v-else class="absolute right-2 top-1/2 -translate-y-1/2 px-1.5 text-[10px] leading-4 rounded border border-border text-text-3 font-mono">/</kbd>
      </div>
    </div>

    <!-- Navigation -->
    <nav class="px-3 space-y-0.5">
      <button
        v-for="tab in tabs"
        :key="tab.id"
        @click="emit('update:activeTab', tab.id)"
        class="relative w-full h-9 flex items-center gap-3 px-3 rounded-lg text-[13px] font-medium cursor-pointer"
        :class="activeTab === tab.id
          ? 'bg-accent/[0.12] text-text'
          : 'text-text-2 hover:text-text hover:bg-surface-2'"
      >
        <span
          class="absolute left-0 top-2 bottom-2 w-[3px] rounded-r-full bg-accent transition-opacity"
          :class="activeTab === tab.id ? 'opacity-100' : 'opacity-0'"
        />
        <component :is="tab.icon" :size="16" :class="activeTab === tab.id ? 'text-accent' : ''" />
        <span class="flex-1 text-left">{{ tab.label }}</span>
        <span
          v-if="tab.id === 'downloads' && activeJobsCount > 0"
          class="flex items-center gap-1 px-1.5 rounded-full bg-accent/20 text-accent text-[10px] mono-num"
        >
          <RefreshCw :size="10" class="animate-spin" />{{ activeJobsCount }}
        </span>
      </button>
    </nav>

    <div class="flex-1" />

    <!-- Replay buffer (gpu-screen-recorder) -->
    <div class="mx-3 mb-3 rounded-xl border p-3 transition-colors"
         :class="recorder.running ? 'border-danger/30 bg-danger/[0.06]' : 'border-border bg-surface-2'">
      <div class="flex items-center justify-between">
        <div class="flex items-center gap-2 min-w-0">
          <span class="relative flex w-2.5 h-2.5 shrink-0">
            <span v-if="recorder.running" class="absolute inset-0 rounded-full bg-danger animate-ping opacity-60" />
            <span class="relative w-2.5 h-2.5 rounded-full" :class="recorder.running ? 'bg-danger' : 'bg-text-3'" />
          </span>
          <div class="min-w-0">
            <div class="text-xs font-semibold text-text">{{ recorder.running ? 'Recording' : 'Buffer off' }}</div>
            <div class="text-[10px] text-text-3 mono-num">{{ recorder.running ? 'RAM · last 300 s' : 'ALT+F9 to start' }}</div>
          </div>
        </div>
        <button
          @click="handleToggleRecorder"
          :disabled="isTogglingRecorder"
          :title="recorder.running ? 'Stop buffer (ALT+F9)' : 'Start buffer (ALT+F9)'"
          class="w-7 h-7 rounded-lg flex items-center justify-center border cursor-pointer disabled:opacity-50"
          :class="recorder.running
            ? 'border-danger/40 text-danger hover:bg-danger/15'
            : 'border-border-strong text-text-2 hover:text-text hover:bg-surface-3'"
        >
          <RefreshCw v-if="isTogglingRecorder" :size="13" class="animate-spin" />
          <Power v-else :size="13" />
        </button>
      </div>

      <!-- Save a clip from the buffer (works even when the Hyprland hotkeys do not fire) -->
      <div v-if="recorder.running" class="mt-3">
        <div class="text-[10px] uppercase tracking-wider text-text-3 mb-1.5 flex items-center justify-between">
          <span>Save last</span>
          <Transition name="view">
            <span v-if="savedFlash" class="flex items-center gap-1 text-success normal-case tracking-normal font-medium">
              <Check :size="11" /> saved
            </span>
          </Transition>
        </div>
        <div class="grid grid-cols-4 gap-1">
          <button
            v-for="sec in [10, 30, 60, 300]"
            :key="sec"
            @click="handleSaveReplay(sec)"
            :disabled="savingSeconds !== null"
            :title="`Dump the last ${sec} s of the RAM buffer to a file`"
            class="h-7 rounded-md text-[11px] font-mono border cursor-pointer disabled:opacity-50"
            :class="savingSeconds === sec
              ? 'border-accent/50 bg-accent/20 text-accent'
              : 'border-border bg-surface/60 text-text-2 hover:text-text hover:border-border-strong'"
          >
            {{ sec === 300 ? '5m' : sec + 's' }}
          </button>
        </div>
      </div>
    </div>

    <!-- Shortcuts -->
    <button
      @click="emit('openShortcuts')"
      title="Keyboard shortcut cheat sheet (? key)"
      class="mx-3 mb-3 h-9 flex items-center gap-3 px-3 rounded-lg text-[13px] text-text-2 hover:text-text hover:bg-surface-2 cursor-pointer"
    >
      <Keyboard :size="16" />
      <span class="flex-1 text-left">Shortcuts</span>
      <kbd class="px-1.5 text-[10px] leading-4 rounded border border-border text-text-3 font-mono">?</kbd>
    </button>
  </aside>
</template>
