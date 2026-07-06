<!--
  Sparkline — pure props -> SVG sparkline for a small numeric time series.

  Zero chart-library dependency: maps a number[] to a polyline (+ optional area
  fill + last-point dot). The line/fill/dot colors read --vb-* CSS variables so
  the chart follows dark mode. No business logic.

  Props:
    values — number[]  (chronological)
    width  — px width of the SVG viewBox (default 220)
    height — px height of the SVG viewBox (default 48)
    color  — stroke color (default var(--vb-primary)); pass a var(--vb-*) ref
             to stay dark-aware
    fill   — draw a faint area under the line (default true)
-->
<template>
  <svg
    class="vb-sparkline"
    :viewBox="`0 0 ${width} ${height}`"
    :width="width"
    :height="height"
    preserveAspectRatio="none"
    role="img"
    aria-hidden="true"
  >
    <polygon
      v-if="fill && points.length > 1"
      :points="areaPoints"
      :fill="color"
      fill-opacity="0.12"
      stroke="none"
    />
    <polyline
      v-if="points.length > 1"
      :points="linePoints"
      fill="none"
      :stroke="color"
      stroke-width="2"
      stroke-linejoin="round"
      stroke-linecap="round"
      vector-effect="non-scaling-stroke"
    />
    <circle
      v-if="points.length"
      :cx="points[points.length - 1].x"
      :cy="points[points.length - 1].y"
      r="2.5"
      :fill="color"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  values: { type: Array, default: () => [] },
  width: { type: Number, default: 220 },
  height: { type: Number, default: 48 },
  color: { type: String, default: 'var(--vb-primary)' },
  fill: { type: Boolean, default: true },
});

const PAD = 3; // keep the stroke + end dot inside the viewBox

const points = computed(() => {
  const nums = props.values.map((v) => Number(v) || 0);
  const n = nums.length;
  if (n === 0) return [];
  const min = Math.min(...nums);
  const max = Math.max(...nums);
  const span = max - min || 1;
  const innerW = props.width - PAD * 2;
  const innerH = props.height - PAD * 2;
  return nums.map((v, i) => ({
    x: PAD + (n === 1 ? innerW / 2 : (i / (n - 1)) * innerW),
    y: PAD + innerH - ((v - min) / span) * innerH,
  }));
});

const linePoints = computed(() =>
  points.value.map((p) => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' '),
);

const areaPoints = computed(() => {
  if (points.value.length < 2) return '';
  const first = points.value[0];
  const last = points.value[points.value.length - 1];
  const base = props.height - PAD;
  return (
    `${first.x.toFixed(2)},${base.toFixed(2)} ` +
    linePoints.value +
    ` ${last.x.toFixed(2)},${base.toFixed(2)}`
  );
});
</script>

<style scoped>
.vb-sparkline {
  display: block;
}
</style>
