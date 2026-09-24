<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { Plus, Trash2, ArrowRight, Tag as TagIcon } from 'lucide-vue-next';
import { fetchTags, createTag, deleteTag } from '../api/client';
import { TagItem } from '../types';
import { plural } from '../format';

const tags = ref<TagItem[]>([]);
const newTagName = ref('');
const newTagColor = ref('#8470ff');

const gameMappings = ref<{ window_class: string; game_name: string }[]>([]);
const newWindowClass = ref('');
const newGameName = ref('');

const loadTags = async () => {
  try {
    tags.value = await fetchTags();
    const res = await fetch('/api/games/mappings');
    if (res.ok) gameMappings.value = await res.json();
  } catch (e) {}
};

onMounted(() => {
  loadTags();
});

const handleCreateTag = async () => {
  if (!newTagName.value.trim()) return;
  try {
    await createTag(newTagName.value.trim(), newTagColor.value);
    newTagName.value = '';
    loadTags();
  } catch (e) {
    alert('Could not add the tag: ' + e);
  }
};

const handleDeleteTag = async (t: TagItem) => {
  const used = t.count ? ` It will be removed from ${t.count} ${plural(t.count, 'clip')}.` : '';
  if (!confirm(`Delete tag #${t.name}?${used}`)) return;
  try {
    await deleteTag(t.id);
    loadTags();
  } catch (e) {}
};

const handleSaveMapping = async () => {
  if (!newWindowClass.value.trim() || !newGameName.value.trim()) return;
  try {
    await fetch('/api/games/mappings', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        window_class: newWindowClass.value.trim(),
        game_name: newGameName.value.trim(),
      }),
    });
    newWindowClass.value = '';
    newGameName.value = '';
    loadTags();
  } catch (e) {}
};

const input = 'h-8 bg-surface-2 border border-border rounded-lg px-2.5 text-text placeholder:text-text-3 focus:outline-none focus:border-accent/60';
</script>

<template>
  <main class="flex-1 min-w-0 flex flex-col overflow-hidden bg-bg text-xs">
    <header class="px-6 pt-5 pb-4 shrink-0 border-b border-border bg-surface/40 flex items-end justify-between gap-4">
      <div>
        <h1 class="text-xl font-semibold tracking-tight text-text">Tags</h1>
        <p class="text-xs text-text-3 mt-0.5 mono-num">{{ tags.length }} {{ plural(tags.length, 'tag') }} · {{ gameMappings.length }} window {{ plural(gameMappings.length, 'mapping') }}</p>
      </div>
      <form @submit.prevent="handleCreateTag" class="flex items-center gap-1.5">
        <label class="relative w-8 h-8 rounded-lg border border-border overflow-hidden cursor-pointer" title="Tag colour">
          <input type="color" v-model="newTagColor" class="absolute inset-0 opacity-0 cursor-pointer" />
          <span class="absolute inset-1.5 rounded-full" :style="{ backgroundColor: newTagColor }" />
        </label>
        <input type="text" placeholder="Tag name…" v-model="newTagName" :class="[input, 'w-48']" />
        <button
          type="submit"
          :disabled="!newTagName.trim()"
          class="h-8 px-3 bg-accent hover:bg-accent/90 text-white rounded-lg font-medium flex items-center gap-1.5 cursor-pointer disabled:opacity-40"
        >
          <Plus :size="14" /> Add tag
        </button>
      </form>
    </header>

    <div class="flex-1 overflow-y-auto px-6 py-5 space-y-8">
      <!-- Tags -->
      <section>
        <div v-if="!tags.length" class="py-14 flex flex-col items-center gap-3 text-center rounded-xl border border-dashed border-border">
          <div class="w-12 h-12 rounded-2xl bg-surface-2 border border-border flex items-center justify-center">
            <TagIcon :size="20" class="text-text-3" />
          </div>
          <p class="text-text-3">No tags yet. Add one above or in the clip editor.</p>
        </div>
        <div v-else class="grid grid-cols-[repeat(auto-fill,minmax(200px,1fr))] gap-2.5">
          <div
            v-for="t in tags"
            :key="t.id"
            class="group relative p-3 bg-surface rounded-xl border border-border hover:border-border-strong flex items-center gap-3 overflow-hidden"
          >
            <span class="absolute left-0 inset-y-0 w-[3px]" :style="{ backgroundColor: t.color }" />
            <div class="flex-1 min-w-0">
              <div class="font-semibold text-text truncate"><span :style="{ color: t.color }">#</span>{{ t.name }}</div>
              <div class="text-[11px] text-text-3 mono-num mt-0.5">
                {{ t.count }} {{ plural(t.count, 'clip') }}<template v-if="t.kind === 'auto'"> · auto</template>
              </div>
            </div>
            <button
              @click="handleDeleteTag(t)"
              class="w-7 h-7 rounded-lg flex items-center justify-center text-text-3 hover:text-danger hover:bg-danger/10 cursor-pointer opacity-0 group-hover:opacity-100 focus-visible:opacity-100"
              :title="`Delete tag #${t.name}`"
            >
              <Trash2 :size="13" />
            </button>
          </div>
        </div>
      </section>

      <!-- Window map -->
      <section class="space-y-3 max-w-3xl">
        <div>
          <h2 class="text-sm font-semibold text-text">Window map</h2>
          <p class="text-text-3 mt-0.5">Turns the window class from the gsr-saved sidecar (e.g. <span class="font-mono text-text-2">steam_app_252950</span>) into a readable game name.</p>
        </div>

        <div class="bg-surface rounded-xl border border-border overflow-hidden">
          <form @submit.prevent="handleSaveMapping" class="p-2.5 grid grid-cols-[1fr_14px_1fr_84px] items-center gap-2 border-b border-border bg-surface-2/40">
            <input type="text" placeholder="Window class, e.g. cs2" v-model="newWindowClass" :class="[input, 'font-mono min-w-0']" />
            <ArrowRight :size="14" class="text-text-3" />
            <input type="text" placeholder="Game name, e.g. Counter-Strike 2" v-model="newGameName" :class="[input, 'min-w-0']" />
            <button
              type="submit"
              :disabled="!newWindowClass.trim() || !newGameName.trim()"
              class="h-8 bg-accent hover:bg-accent/90 text-white rounded-lg font-medium flex items-center justify-center gap-1.5 cursor-pointer disabled:opacity-40"
            >
              <Plus :size="14" /> Add
            </button>
          </form>
          <div
            v-for="map in gameMappings"
            :key="map.window_class"
            class="px-2.5 h-10 grid grid-cols-[1fr_14px_1fr_84px] items-center gap-2 border-b border-border last:border-b-0 hover:bg-surface-2/50"
          >
            <span class="pl-2.5 font-mono text-[11px] text-accent truncate">{{ map.window_class }}</span>
            <ArrowRight :size="13" class="text-text-3" />
            <span class="pl-2.5 font-semibold text-text truncate">{{ map.game_name }}</span>
            <span />
          </div>
          <div v-if="!gameMappings.length" class="px-4 py-6 text-center text-text-3">No mappings.</div>
        </div>
      </section>
    </div>
  </main>
</template>
