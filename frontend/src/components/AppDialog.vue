<script lang="ts">
import { ref } from 'vue';

// in-app replacement for window.confirm/alert: one dialog at a time, mounted once in App.vue
interface DialogState {
  message: string;
  okLabel: string;
  danger: boolean;
  cancel: boolean;
  resolve: (ok: boolean) => void;
}

const current = ref<DialogState | null>(null);

const open = (message: string, opts: Partial<Omit<DialogState, 'message' | 'resolve'>>) =>
  new Promise<boolean>(resolve => {
    current.value?.resolve(false);
    current.value = { message, okLabel: 'OK', danger: false, cancel: true, ...opts, resolve };
  });

export const confirmDialog = (message: string, opts: { okLabel?: string; danger?: boolean } = {}) =>
  open(message, opts);

export const alertDialog = (message: string) => open(message, { cancel: false }).then(() => {});
</script>

<script setup lang="ts">
import { nextTick, watch } from 'vue';

const okRef = ref<HTMLButtonElement | null>(null);

const close = (ok: boolean) => {
  current.value?.resolve(ok);
  current.value = null;
};

watch(current, d => d && nextTick(() => okRef.value?.focus()));
</script>

<template>
  <Transition name="modal">
    <div
      v-if="current"
      class="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-black/75 backdrop-blur-sm"
      @click.self="close(false)"
      @keydown.stop
      @keydown.esc="close(false)"
    >
      <div class="modal-card bg-surface border border-border-strong rounded-xl w-full max-w-sm shadow-2xl p-5" role="dialog" aria-modal="true">
        <p class="text-sm text-text whitespace-pre-line break-words">{{ current.message }}</p>
        <div class="mt-5 flex justify-end gap-2 text-xs">
          <button
            v-if="current.cancel"
            @click="close(false)"
            class="h-8 px-3.5 rounded-lg bg-surface-2 border border-border text-text hover:bg-surface-3 cursor-pointer"
          >
            Cancel
          </button>
          <button
            ref="okRef"
            @click="close(true)"
            class="h-8 px-3.5 rounded-lg font-medium text-white cursor-pointer outline-none focus-visible:ring-2 focus-visible:ring-white/40"
            :class="current.danger ? 'bg-danger hover:bg-danger/90' : 'bg-accent hover:bg-accent/90'"
          >
            {{ current.okLabel }}
          </button>
        </div>
      </div>
    </div>
  </Transition>
</template>
