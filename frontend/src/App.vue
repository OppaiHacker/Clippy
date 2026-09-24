<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue';
import SideNav from './components/SideNav.vue';
import LibraryView from './views/LibraryView.vue';
import EditorView from './views/EditorView.vue';
import DownloadsView from './views/DownloadsView.vue';
import TagsView from './views/TagsView.vue';
import SettingsView from './views/SettingsView.vue';
import ShortcutsModal from './components/ShortcutsModal.vue';
import { Clip } from './types';
import { fetchClips } from './api/client';
import { Sliders } from 'lucide-vue-next';

const activeTab = ref<'library' | 'editor' | 'downloads' | 'tags' | 'settings'>('library');
const searchQuery = ref('');
const clips = ref<Clip[]>([]);
const selectedClipIds = ref<Set<number>>(new Set());
const showTrash = ref(false);
const activeEditingClip = ref<Clip | null>(null);
const sideNavRef = ref<any>(null);
const isShortcutsOpen = ref(false);

let clipsPollInterval: any = null;
let clipsSig = '';

const loadClips = async () => {
  try {
    const newClips = await fetchClips({ trash: showTrash.value });
    // full comparison: a signature built from a few fields missed changes to game, tracks and thumbnails
    const newSig = JSON.stringify(newClips);
    if (newSig !== clipsSig) {
      clipsSig = newSig;
      clips.value = newClips;
      // the editor holds a copy of the clip: refresh it (new tags, imports)
      const fresh = activeEditingClip.value && newClips.find(c => c.id === activeEditingClip.value!.id);
      if (fresh) activeEditingClip.value = fresh;
    }
  } catch (e) {
    console.error('Failed to load clips', e);
  }
};

onMounted(() => {
  loadClips();
  clipsPollInterval = setInterval(loadClips, 3000);

  // Global keyboard shortcuts
  window.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

    if (e.key === '?' || (e.key === '/' && e.shiftKey) || e.key === 'F1') {
      e.preventDefault();
      isShortcutsOpen.value = !isShortcutsOpen.value;
    } else if (e.key === 'Escape' && isShortcutsOpen.value) {
      isShortcutsOpen.value = false;
    } else if (e.key === '/') {
      e.preventDefault();
      sideNavRef.value?.focusSearch();
    } else if (e.key === 'Enter' && activeTab.value === 'library') {
      if (selectedClipIds.value.size === 1) {
        const id = Array.from(selectedClipIds.value)[0];
        const clip = clips.value.find(c => c.id === id);
        if (clip) openClipInEditor(clip);
      }
    }
  });
});

onUnmounted(() => {
  if (clipsPollInterval) clearInterval(clipsPollInterval);
});

const openClipInEditor = (clip: Clip) => {
  activeEditingClip.value = clip;
  activeTab.value = 'editor';
};

const switchTrash = (value: boolean) => {
  showTrash.value = value;
  clips.value = [];
  clipsSig = '';
  loadClips();
};

const handleBackToLibrary = () => {
  activeTab.value = 'library';
  loadClips();
};
</script>

<template>
  <div class="h-screen w-screen flex overflow-hidden bg-bg text-text">
    <SideNav
      ref="sideNavRef"
      :active-tab="activeTab"
      @update:active-tab="activeTab = $event as any"
      :search-query="searchQuery"
      @update:search-query="searchQuery = $event"
      @open-shortcuts="isShortcutsOpen = true"
    />

    <div class="flex-1 min-w-0 flex overflow-hidden">
      <Transition name="view" mode="out-in">
      <LibraryView
        v-if="activeTab === 'library'"
        :clips="clips"
        :selected-clip-ids="selectedClipIds"
        @update:selected-clip-ids="selectedClipIds = $event"
        :search-query="searchQuery"
        @open-clip="openClipInEditor"
        @refresh="loadClips"
        :trash="showTrash"
        @update:trash="switchTrash"
      />

      <EditorView
        v-else-if="activeTab === 'editor' && activeEditingClip"
        :key="`${activeEditingClip.id}:${activeEditingClip.imported_tracks.map(t => t.id).join(',')}`"
        :clip="activeEditingClip"
        @back="handleBackToLibrary"
        @refresh="loadClips"
        @goto-downloads="activeTab = 'downloads'"
      />

      <div
        v-else-if="activeTab === 'editor' && !activeEditingClip"
        class="flex-1 flex flex-col items-center justify-center text-center gap-4"
      >
        <div class="w-14 h-14 rounded-2xl bg-surface-2 border border-border flex items-center justify-center">
          <Sliders :size="24" class="text-accent" />
        </div>
        <div>
          <p class="text-sm font-semibold text-text">No clip open</p>
          <p class="text-xs text-text-3 mt-1">Pick a clip in the library to open the editor.</p>
        </div>
        <button
          @click="activeTab = 'library'"
          class="h-8 px-3.5 bg-accent text-white rounded-lg text-xs font-medium cursor-pointer hover:bg-accent/90"
        >
          Go to library
        </button>
      </div>

      <DownloadsView v-else-if="activeTab === 'downloads'" :clips="clips" />

      <TagsView v-else-if="activeTab === 'tags'" />

      <SettingsView 
        v-else-if="activeTab === 'settings'" 
        @open-shortcuts="isShortcutsOpen = true" 
      />
      </Transition>
    </div>

    <!-- Keyboard Shortcuts Cheat Sheet Modal -->
    <ShortcutsModal
      :is-open="isShortcutsOpen"
      @close="isShortcutsOpen = false"
    />
  </div>
</template>
