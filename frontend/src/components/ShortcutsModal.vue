<script setup lang="ts">
import { ref, computed } from 'vue';
import { X, Keyboard, Sliders, Film, Search, CircleDot, Cpu } from 'lucide-vue-next';
import { shortcuts } from '../shortcuts';

const props = defineProps<{
  isOpen: boolean;
}>();

const emit = defineEmits<{
  (e: 'close'): void;
}>();

const activeTab = ref<'recording' | 'editor' | 'library' | 'all'>('recording');
const searchQuery = ref('');

const TABS = [
  { id: 'recording', label: 'Recording', icon: CircleDot },
  { id: 'editor', label: 'Editor', icon: Sliders },
  { id: 'library', label: 'Library', icon: Film },
  { id: 'all', label: 'All', icon: null },
] as const;

const filteredShortcuts = computed(() => {
  let list = shortcuts;
  if (activeTab.value !== 'all') {
    list = list.filter(s => s.category === activeTab.value);
  }
  if (searchQuery.value.trim()) {
    const q = searchQuery.value.toLowerCase();
    list = list.filter(s => 
      s.title.toLowerCase().includes(q) ||
      s.description.toLowerCase().includes(q) ||
      s.keys.some(k => k.toLowerCase().includes(q)) ||
      (s.command && s.command.toLowerCase().includes(q))
    );
  }
  return list;
});
</script>

<template>
  <Transition name="modal">
  <div 
    v-if="isOpen"
    class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
    @click.self="emit('close')"
  >
    <div 
      class="modal-card bg-surface border border-border-strong rounded-xl w-full max-w-3xl max-h-[85vh] flex flex-col shadow-2xl overflow-hidden"
      role="dialog"
      aria-modal="true"
    >
      <!-- Modal Header -->
      <div class="px-5 py-4 border-b border-border flex items-center justify-between bg-surface-2">
        <div class="flex items-center space-x-3">
          <div class="p-2 rounded-lg bg-accent-dim text-accent border border-accent/20">
            <Keyboard :size="20" />
          </div>
          <div>
            <h2 class="text-base font-bold text-text flex items-center gap-2">
              Keyboard shortcuts
              <span class="text-[11px] font-normal px-2 py-0.5 rounded bg-surface-3 text-text-2 border border-border">
                Clippy & GSR
              </span>
            </h2>
            <p class="text-xs text-text-3">
              gpu-screen-recorder binds (Hyprland) and in-app shortcuts
            </p>
          </div>
        </div>

        <button 
          @click="emit('close')"
          class="p-1.5 rounded-lg text-text-3 hover:text-text hover:bg-surface-3 transition-colors cursor-pointer"
          title="Close (Esc)"
        >
          <X :size="18" />
        </button>
      </div>

      <!-- Filter bar and tabs -->
      <div class="px-5 py-3 border-b border-border bg-surface/50 flex flex-wrap items-center justify-between gap-3">
        <div class="h-8 flex items-center bg-surface-2 border border-border rounded-lg p-0.5 text-xs">
          <button
            v-for="tab in TABS"
            :key="tab.id"
            @click="activeTab = tab.id"
            class="h-full flex items-center gap-1.5 px-3 rounded-md font-medium cursor-pointer"
            :class="activeTab === tab.id ? 'bg-surface-3 text-text shadow-sm' : 'text-text-3 hover:text-text'"
          >
            <component :is="tab.icon" v-if="tab.icon" :size="13" :class="activeTab === tab.id ? (tab.id === 'recording' ? 'text-danger' : 'text-accent') : ''" />
            {{ tab.label }}
          </button>
        </div>

        <!-- Search input -->
        <div class="relative w-52">
          <Search :size="13" class="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-3" />
          <input
            v-model="searchQuery"
            type="text"
            placeholder="Search shortcuts…"
            class="w-full h-8 bg-surface-2 border border-border rounded-lg pl-7 pr-2.5 text-xs text-text placeholder:text-text-3 focus:border-accent/60 focus:outline-none"
          />
        </div>
      </div>

      <!-- Modal Content Body -->
      <div class="flex-1 overflow-y-auto p-5 space-y-4">
        <!-- Replay Buffer Special Info Card (when on recording or all) -->
        <div 
          v-if="(activeTab === 'recording' || activeTab === 'all') && !searchQuery"
          class="bg-gradient-to-r from-surface-2 to-surface-3 p-4 rounded-xl border border-border-strong text-xs space-y-2.5"
        >
          <div class="flex items-center justify-between">
            <div class="flex items-center space-x-2 font-semibold text-text">
              <Cpu :size="16" class="text-accent" />
              <span>How recording works (ShadowPlay-style, gpu-screen-recorder)</span>
            </div>
            <span class="text-[10px] px-2 py-0.5 rounded bg-surface border border-border text-text-3 font-mono">
              Buffer: 300 s in RAM
            </span>
          </div>

          <p class="text-text-2 leading-relaxed">
            The buffer keeps the last 5 minutes of video and audio in RAM without writing anything to disk. Only a bind (e.g. <kbd class="px-1 py-0.5 rounded bg-surface border border-border font-mono text-text font-bold">ALT + F10</kbd>) dumps the chosen length to a video file, in a fraction of a second.
          </p>

          <!-- Audio track breakdown -->
          <div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-2 pt-1 text-[11px]">
            <div class="p-2 rounded bg-surface/80 border border-trk-system/30">
              <span class="text-trk-system font-medium block">Track 1: Game & system</span>
              <span class="text-text-3 text-[10px]">Game audio only (no Discord, no browser)</span>
            </div>
            <div class="p-2 rounded bg-surface/80 border border-trk-app/30">
              <span class="text-trk-app font-medium block">Track 2: Discord</span>
              <span class="text-text-3 text-[10px]">Vesktop / voice chat</span>
            </div>
            <div class="p-2 rounded bg-surface/80 border border-trk-app/30">
              <span class="text-trk-app font-medium block">Track 3: Browser</span>
              <span class="text-text-3 text-[10px]">Zen Browser / YouTube etc.</span>
            </div>
            <div class="p-2 rounded bg-surface/80 border border-trk-mic/30">
              <span class="text-trk-mic font-medium block">Track 4: Microphone</span>
              <span class="text-text-3 text-[10px]">Your voice (default input)</span>
            </div>
          </div>
        </div>

        <!-- Shortcuts List -->
        <div class="space-y-2">
          <div 
            v-for="item in filteredShortcuts" 
            :key="item.id"
            class="flex flex-col sm:flex-row sm:items-center justify-between p-3 rounded-lg bg-surface-2 border border-border hover:border-border-strong hover:bg-surface-3/50 transition-colors gap-2"
          >
            <div class="space-y-1">
              <div class="flex items-center space-x-2">
                <span class="font-semibold text-text text-sm">{{ item.title }}</span>
                <span 
                  v-if="item.badge"
                  class="text-[10px] px-1.5 py-0.2 rounded font-medium"
                  :class="{
                    'bg-danger/20 text-danger border border-danger/30': item.badgeType === 'danger',
                    'bg-warning/20 text-warning border border-warning/30': item.badgeType === 'warning',
                    'bg-accent/20 text-accent border border-accent/30': item.badgeType === 'accent',
                    'bg-success/20 text-success border border-success/30': item.badgeType === 'success',
                    'bg-surface-3 text-text-3 border border-border': item.badgeType === 'neutral' || !item.badgeType,
                  }"
                >
                  {{ item.badge }}
                </span>
              </div>
              <p class="text-xs text-text-2 leading-snug">{{ item.description }}</p>
              <div v-if="item.command" class="pt-0.5">
                <span class="text-[10px] font-mono text-text-3 bg-surface px-1.5 py-0.5 rounded border border-border">
                  CLI: {{ item.command }}
                </span>
              </div>
            </div>

            <!-- Keycaps -->
            <div class="flex items-center space-x-1.5 shrink-0 sm:ml-4">
              <template v-for="(k, idx) in item.keys" :key="idx">
                <span v-if="k === '/'" class="text-text-3 text-xs font-mono px-0.5">/</span>
                <kbd 
                  v-else 
                  class="inline-flex items-center justify-center min-w-[28px] h-7 px-2 py-0.5 text-xs font-mono font-semibold text-text bg-surface border border-border-strong rounded shadow-sm"
                >
                  {{ k }}
                </kbd>
              </template>
            </div>
          </div>

          <div 
            v-if="filteredShortcuts.length === 0" 
            class="text-center py-8 text-text-3 text-xs"
          >
            No shortcuts match "{{ searchQuery }}".
          </div>
        </div>
      </div>

      <!-- Modal Footer -->
      <div class="px-5 py-3 border-t border-border bg-surface-2 flex items-center justify-between text-xs text-text-3">
        <div class="flex items-center space-x-2">
          <span>Tip: press <kbd class="px-1.5 py-0.5 rounded bg-surface border border-border font-mono text-text">?</kbd> anywhere to open this window.</span>
        </div>
        <button
          @click="emit('close')"
          class="px-3 py-1 rounded bg-surface-3 hover:bg-border text-text font-medium transition-colors cursor-pointer border border-border"
        >
          Close
        </button>
      </div>
    </div>
  </div>
  </Transition>
</template>
