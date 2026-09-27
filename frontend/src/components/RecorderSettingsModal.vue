<script setup lang="ts">
import { ref, watch } from 'vue';
import { X, Settings, RefreshCw } from 'lucide-vue-next';
import { fetchRecorderConfig, saveRecorderConfig } from '../api/client';
import { RecorderBindAction, RecorderConfig, RecorderStatus } from '../types';

const props = defineProps<{ isOpen: boolean; running: boolean }>();
const emit = defineEmits<{
  (e: 'close'): void;
  (e: 'saved', cfg: RecorderConfig, status: RecorderStatus): void;
}>();

const cfg = ref<RecorderConfig | null>(null);
const saving = ref(false);
const error = ref('');
const capturing = ref<RecorderBindAction | null>(null);

const FPS_PRESETS = [30, 60, 120, 144, 165, 180, 240];
const BIND_LABELS: [RecorderBindAction, string][] = [
  ['toggle', 'Buffer on / off'],
  ['save_10', 'Save last 10 s'],
  ['save_30', 'Save last 30 s'],
  ['save_60', 'Save last 60 s'],
  ['save_full', 'Save whole buffer'],
];

watch(() => props.isOpen, async open => {
  if (!open) return;
  error.value = '';
  capturing.value = null;
  try {
    cfg.value = await fetchRecorderConfig();
  } catch (e) {
    error.value = String(e);
  }
}, { immediate: true });

// Browser key names -> Hyprland (xkb) key names; letters, digits and F-keys pass through
const KEY_NAMES: Record<string, string> = {
  ' ': 'SPACE', Enter: 'RETURN', Tab: 'TAB', Escape: 'ESCAPE', PrintScreen: 'Print',
  Insert: 'Insert', Delete: 'Delete', Home: 'Home', End: 'End', PageUp: 'Prior', PageDown: 'Next',
};

const captureKey = (action: RecorderBindAction, e: KeyboardEvent) => {
  e.preventDefault();
  e.stopPropagation();
  if (!cfg.value) return;
  if (e.key === 'Backspace') {
    cfg.value.binds[action] = '';
    capturing.value = null;
    return;
  }
  if (['Alt', 'Control', 'Shift', 'Meta', 'OS', 'AltGraph'].includes(e.key)) return; // wait for the real key
  const key = /^(F\d{1,2}|[a-z0-9])$/i.test(e.key) ? e.key.toUpperCase() : KEY_NAMES[e.key];
  if (!key) return;
  const mods = [e.metaKey && 'SUPER', e.ctrlKey && 'CTRL', e.altKey && 'ALT', e.shiftKey && 'SHIFT'].filter(Boolean);
  cfg.value.binds[action] = [...mods, key].join(' + ');
  capturing.value = null;
};

const handleSave = async () => {
  if (!cfg.value) return;
  saving.value = true;
  error.value = '';
  try {
    const res = await saveRecorderConfig(cfg.value);
    emit('saved', res.config, res.recorder);
    emit('close');
  } catch (e) {
    error.value = String(e);
  } finally {
    saving.value = false;
  }
};

// The buffer lives in RAM. very_high h264 at 1440p60 is ~1 GB per 5 min (README), scaled linearly by fps
const ramEstimateGb = (c: RecorderConfig) => ((c.buffer / 300) * (c.fps / 60)).toFixed(1);
</script>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div
        v-if="isOpen"
        class="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
        @click.self="emit('close')"
        @keydown.esc="!capturing && emit('close')"
      >
        <div class="modal-card bg-surface border border-border-strong rounded-xl w-full max-w-md flex flex-col shadow-2xl overflow-hidden" role="dialog" aria-modal="true" aria-labelledby="rec-settings-title">
          <div class="px-5 py-4 border-b border-border flex items-center justify-between bg-surface-2">
            <div class="flex items-center gap-3">
              <div class="p-2 rounded-lg bg-accent-dim text-accent border border-accent/20"><Settings :size="18" /></div>
              <div>
                <h2 id="rec-settings-title" class="text-base font-bold text-text">Recorder settings</h2>
                <p class="text-xs text-text-3">gpu-screen-recorder replay buffer and Hyprland hotkeys</p>
              </div>
            </div>
            <button @click="emit('close')" class="p-1.5 rounded-lg text-text-3 hover:text-text hover:bg-surface-3 cursor-pointer" title="Close">
              <X :size="18" />
            </button>
          </div>

          <div v-if="!cfg" class="p-8 flex justify-center text-text-3">
            <span v-if="error" class="text-danger text-xs">{{ error }}</span>
            <RefreshCw v-else :size="16" class="animate-spin" />
          </div>

          <div v-else class="p-5 space-y-5">
            <!-- FPS -->
            <div>
              <label for="rec-fps" class="text-[11px] uppercase tracking-wider text-text-3">Frames per second</label>
              <div class="mt-1.5 flex gap-1 flex-wrap">
                <button
                  v-for="f in FPS_PRESETS" :key="f"
                  @click="cfg.fps = f"
                  class="h-7 px-2.5 rounded-md text-[11px] font-mono border cursor-pointer"
                  :class="cfg.fps === f ? 'border-accent/50 bg-accent/20 text-accent' : 'border-border bg-surface-2 text-text-2 hover:text-text'"
                >{{ f }}</button>
                <input id="rec-fps" v-model.number="cfg.fps" type="number" min="10" max="500"
                       class="h-7 w-16 bg-surface-2 border border-border rounded-md px-2 text-[11px] font-mono text-text focus:border-accent/60 focus:outline-none" />
              </div>
              <p class="mt-1 text-[10px] text-text-3">Capped by the monitor refresh rate.</p>
            </div>

            <!-- Buffer -->
            <div>
              <label for="rec-buffer" class="text-[11px] uppercase tracking-wider text-text-3">Max buffer (seconds)</label>
              <div class="mt-1.5 flex items-center gap-3">
                <input id="rec-buffer" v-model.number="cfg.buffer" type="range" min="10" max="1800" step="10" class="flex-1" />
                <input v-model.number="cfg.buffer" type="number" min="10" max="1800" aria-label="Buffer seconds"
                       class="h-7 w-20 bg-surface-2 border border-border rounded-md px-2 text-[11px] font-mono text-text focus:border-accent/60 focus:outline-none" />
              </div>
              <p class="mt-1 text-[10px] text-text-3 mono-num">≈ {{ ramEstimateGb(cfg) }} GB RAM at {{ cfg.fps }} fps (rough, depends on the scene)</p>
            </div>

            <!-- Binds -->
            <div>
              <div class="text-[11px] uppercase tracking-wider text-text-3">Hotkeys</div>
              <p class="mt-0.5 text-[10px] text-text-3">Click a field and press the combo. Backspace clears it.</p>
              <div class="mt-2 space-y-1.5">
                <div v-for="[action, label] in BIND_LABELS" :key="action" class="flex items-center justify-between gap-3">
                  <span class="text-xs text-text-2">{{ label }}</span>
                  <button
                    @click="capturing = action"
                    @keydown="capturing === action && captureKey(action, $event)"
                    @blur="capturing === action && (capturing = null)"
                    class="h-7 min-w-[9rem] px-2.5 rounded-md text-[11px] font-mono border cursor-pointer text-left"
                    :class="capturing === action ? 'border-accent/60 bg-accent/15 text-accent' : 'border-border bg-surface-2 text-text hover:border-border-strong'"
                  >{{ capturing === action ? 'press keys…' : (cfg.binds[action] || '—') }}</button>
                </div>
              </div>
            </div>

            <p v-if="running" class="text-[11px] text-warning">Saving restarts the recorder. What is in the buffer now is lost.</p>
            <p v-if="error" class="text-[11px] text-danger break-words">{{ error }}</p>
          </div>

          <div class="px-5 py-3 border-t border-border flex justify-end gap-2 bg-surface-2">
            <button @click="emit('close')" class="h-8 px-3 rounded-lg text-xs text-text-2 hover:text-text hover:bg-surface-3 cursor-pointer">Cancel</button>
            <button @click="handleSave" :disabled="!cfg || saving"
                    class="h-8 px-4 rounded-lg text-xs font-semibold bg-accent text-white hover:opacity-90 disabled:opacity-50 cursor-pointer flex items-center gap-1.5">
              <RefreshCw v-if="saving" :size="12" class="animate-spin" /> Save
            </button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>
