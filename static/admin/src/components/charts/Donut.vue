<!--
  Donut — pure props -> SVG donut chart for categorical distributions.

  Zero chart-library dependency: draws arc segments with the SVG circle
  stroke-dasharray technique. Colors are passed in by the caller as --vb-*
  CSS variable references (e.g. "var(--vb-primary)") so the chart follows dark
  mode automatically; the track + center label read --vb-* directly. No
  business logic.

  Props:
    segments — [{ key, label, count, color }]  (color = a CSS color, ideally
               a var(--vb-*) reference so it is dark-aware)
    size     — outer px size of the square SVG (default 160)
    thickness — ring thickness in px (default 22)
    centerValue — big number shown in the hole (optional)
    centerLabel — caption under the center value (optional)
-->
<template>
  <div class="vb-donut">
    <svg
      class="vb-donut__svg"
      :width="size"
      :height="size"
      :viewBox="`0 0 ${size} ${size}`"
      role="img"
      aria-hidden="true"
    >
      <!-- Track -->
      <circle
        :cx="center"
        :cy="center"
        :r="radius"
        fill="none"
        stroke="var(--vb-surface-alt)"
        :stroke-width="thickness"
      />
      <!-- Segments -->
      <g :transform="`rotate(-90 ${center} ${center})`">
        <circle
          v-for="arc in arcs"
          :key="arc.key"
          :cx="center"
          :cy="center"
          :r="radius"
          fill="none"
          :stroke="arc.color"
          :stroke-width="thickness"
          :stroke-dasharray="`${arc.len} ${circumference - arc.len}`"
          :stroke-dashoffset="-arc.offset"
          stroke-linecap="butt"
        />
      </g>
      <!-- Center label -->
      <text
        v-if="centerValue !== '' && centerValue !== null && centerValue !== undefined"
        :x="center"
        :y="center - 2"
        text-anchor="middle"
        dominant-baseline="central"
        class="vb-donut__value"
      >{{ centerValue }}</text>
      <text
        v-if="centerLabel"
        :x="center"
        :y="center + 16"
        text-anchor="middle"
        dominant-baseline="central"
        class="vb-donut__caption"
      >{{ centerLabel }}</text>
    </svg>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  segments: { type: Array, default: () => [] },
  size: { type: Number, default: 160 },
  thickness: { type: Number, default: 22 },
  centerValue: { type: [String, Number], default: '' },
  centerLabel: { type: String, default: '' },
});

const center = computed(() => props.size / 2);
const radius = computed(() => (props.size - props.thickness) / 2);
const circumference = computed(() => 2 * Math.PI * radius.value);

const arcs = computed(() => {
  const total = props.segments.reduce((s, seg) => s + (Number(seg.count) || 0), 0);
  if (total <= 0) return [];
  let offset = 0;
  return props.segments
    .filter((seg) => (Number(seg.count) || 0) > 0)
    .map((seg) => {
      const frac = (Number(seg.count) || 0) / total;
      const len = frac * circumference.value;
      const arc = { key: seg.key, color: seg.color, len, offset };
      offset += len;
      return arc;
    });
});
</script>

<style scoped>
.vb-donut {
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.vb-donut__svg {
  display: block;
}

.vb-donut__value {
  fill: var(--vb-text);
  font-size: 22px;
  font-weight: 600;
  font-family: var(--vb-font-family);
}

.vb-donut__caption {
  fill: var(--vb-text-tertiary);
  font-size: 11px;
  font-family: var(--vb-font-family);
}
</style>
