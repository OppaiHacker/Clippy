<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch } from 'vue';

const props = withDefaults(defineProps<{
  clipId: number;
  trackId: number;
  color: string;
  height?: number;
}>(), {
  height: 36,
});

const canvasRef = ref<HTMLCanvasElement | null>(null);
const peaks = ref<[number, number][] | null>(null);

const fetchWaveform = async () => {
  try {
    const res = await fetch(`/api/clips/${props.clipId}/waveform/${props.trackId}`);
    if (res.ok) {
      const data = await res.json();
      if (data.peaks) peaks.value = data.peaks;
    }
  } catch (e) {
    // ignore
  }
};

// Speech usually sits around -25 dBFS, i.e. 0.02-0.05 on a linear scale: on a 28px
// lane that is less than a pixel and the whole track looks flat. So each track is
// scaled to its own loud part (99th percentile, so a single click does not eat the
// whole scale) and quiet parts are lifted with a gamma curve.
const GAMMA = 0.65;

const scaleFor = (data: [number, number][]): number => {
  const mags = data.map(([lo, hi]) => Math.max(Math.abs(lo), Math.abs(hi))).sort((a, b) => a - b);
  const p99 = mags[Math.floor(mags.length * 0.99)] ?? 0;
  if (p99 < 0.0005) return 0; // silence: draw just the baseline
  return 1 / p99;
};

const shape = (v: number, scale: number): number => {
  const norm = Math.min(1, Math.abs(v) * scale);
  return Math.sign(v) * Math.pow(norm, GAMMA);
};

const draw = () => {
  const canvas = canvasRef.value;
  if (!canvas || !peaks.value || peaks.value.length === 0) return;

  const ctx = canvas.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const width = canvas.parentElement?.clientWidth || 600;
  canvas.width = width * dpr;
  canvas.height = props.height * dpr;

  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, props.height);

  ctx.fillStyle = props.color;
  const midY = props.height / 2;
  const step = width / peaks.value.length;
  const scale = scaleFor(peaks.value);

  for (let i = 0; i < peaks.value.length; i++) {
    const [minVal, maxVal] = peaks.value[i];
    const x = i * step;
    const y1 = midY + shape(minVal, scale) * midY * 0.95;
    const y2 = midY + shape(maxVal, scale) * midY * 0.95;
    const barH = Math.max(1, Math.abs(y2 - y1));
    ctx.fillRect(x, Math.min(y1, y2), Math.max(1, step), barH);
  }
};

let observer: ResizeObserver | null = null;

onMounted(() => {
  fetchWaveform();
  if (canvasRef.value?.parentElement) {
    observer = new ResizeObserver(() => draw());
    observer.observe(canvasRef.value.parentElement);
  }
});

onUnmounted(() => observer?.disconnect());

watch(peaks, () => {
  draw();
});
</script>

<template>
  <div class="w-full h-full relative overflow-hidden">
    <canvas
      ref="canvasRef"
      :style="{ width: '100%', height: `${height}px` }"
      class="block opacity-75"
    />
  </div>
</template>
