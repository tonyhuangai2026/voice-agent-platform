<!--
  BarList — pure props -> SVG horizontal bar list for categorical distributions.

  Zero chart-library dependency: each row is an SVG-backed track + filled bar
  with an inline label, count, and percentage. Colors are passed in by the
  caller (ideally var(--vb-*) references) so the chart follows dark mode; the
  track reads --vb-* directly. No business logic.

  Props:
    items — [{ key, label, count, color }]
    max   — value mapped to a full-width bar (default: largest count)
-->
<template>
  <div class="vb-barlist">
    <div v-for="item in rows" :key="item.key" class="vb-barlist__row">
      <div class="vb-barlist__head">
        <span class="vb-barlist__label" :title="item.label">{{ item.label }}</span>
        <span class="vb-barlist__count">{{ item.count }}</span>
        <span class="vb-barlist__pct">{{ item.pct.toFixed(1) }}%</span>
      </div>
      <svg
        class="vb-barlist__svg"
        :viewBox="`0 0 100 ${barHeight}`"
        preserveAspectRatio="none"
        :height="barHeight"
        width="100%"
        role="img"
        aria-hidden="true"
      >
        <rect
          x="0"
          y="0"
          width="100"
          :height="barHeight"
          :rx="radius"
          :ry="radius"
          fill="var(--vb-surface-alt)"
        />
        <rect
          x="0"
          y="0"
          :width="Math.max(item.fillW, item.count > 0 ? 1.5 : 0)"
          :height="barHeight"
          :rx="radius"
          :ry="radius"
          :fill="item.color"
        />
      </svg>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  items: { type: Array, default: () => [] },
  max: { type: Number, default: 0 },
  barHeight: { type: Number, default: 10 },
});

const radius = computed(() => props.barHeight / 2);

const rows = computed(() => {
  const total = props.items.reduce((s, it) => s + (Number(it.count) || 0), 0);
  const scaleMax =
    props.max > 0
      ? props.max
      : props.items.reduce((m, it) => Math.max(m, Number(it.count) || 0), 0);
  return props.items.map((it) => {
    const count = Number(it.count) || 0;
    return {
      key: it.key,
      label: it.label,
      color: it.color,
      count,
      pct: total > 0 ? (count / total) * 100 : 0,
      // viewBox is 0..100 wide, so fill width is a direct percentage of scaleMax
      fillW: scaleMax > 0 ? (count / scaleMax) * 100 : 0,
    };
  });
});
</script>

<style scoped>
.vb-barlist {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-md);
}

.vb-barlist__head {
  display: flex;
  align-items: baseline;
  gap: var(--vb-space-sm);
  margin-bottom: 4px;
}

.vb-barlist__label {
  flex: 1 1 auto;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: 13px;
  color: var(--vb-text-secondary);
}

.vb-barlist__count {
  flex: none;
  font-size: 13px;
  font-weight: 600;
  color: var(--vb-text);
}

.vb-barlist__pct {
  flex: none;
  font-size: 11px;
  color: var(--vb-text-tertiary);
  min-width: 42px;
  text-align: right;
}

.vb-barlist__svg {
  display: block;
}
</style>
