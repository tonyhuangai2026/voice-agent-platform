<!--
  MetricCard — dashboard metric tile (icon slot + value + label + optional trend).

  (Formerly kept byte-identical with the demo SPA's copy; the demo SPA was
  removed in the single-page merge — this is now the sole copy.)

  References only --vb-* tokens (follows dark mode). No business logic.

  Props:
    value      — the metric value (string or number)
    label      — caption under the value
    trend      — optional signed number; sign drives up/down color
    trendLabel — optional text shown next to the trend (e.g. "vs last week")
  Slots:
    icon — leading icon (e.g. <n-icon :component="Dashboard" />)
-->
<template>
  <div class="vb-metric">
    <div v-if="$slots.icon" class="vb-metric__icon"><slot name="icon" /></div>
    <div class="vb-metric__body">
      <div class="vb-metric__value">{{ value }}</div>
      <div class="vb-metric__label">{{ label }}</div>
      <div
        v-if="trend !== null && trend !== undefined"
        class="vb-metric__trend"
        :class="trendClass"
      >
        <span class="vb-metric__trend-arrow">{{ trendArrow }}</span>
        <span>{{ trendText }}</span>
        <span v-if="trendLabel" class="vb-metric__trend-label">{{ trendLabel }}</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  value: { type: [String, Number], default: '' },
  label: { type: String, default: '' },
  trend: { type: Number, default: null },
  trendLabel: { type: String, default: '' },
});

const isUp = computed(() => (props.trend ?? 0) >= 0);
const trendClass = computed(() =>
  isUp.value ? 'vb-metric__trend--up' : 'vb-metric__trend--down',
);
const trendArrow = computed(() => (isUp.value ? '↑' : '↓'));
const trendText = computed(() => `${Math.abs(props.trend ?? 0)}%`);
</script>

<style scoped>
.vb-metric {
  display: flex;
  align-items: flex-start;
  gap: var(--vb-space-lg);
  padding: var(--vb-space-xl);
  background: var(--vb-surface);
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  box-shadow: var(--vb-shadow-card);
}

.vb-metric__icon {
  flex: none;
  width: 40px;
  height: 40px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--vb-radius-md);
  background: var(--vb-surface-alt);
  color: var(--vb-primary);
  font-size: 22px;
}

.vb-metric__body {
  min-width: 0;
}

.vb-metric__value {
  font-size: 26px;
  font-weight: 600;
  line-height: 1.1;
  color: var(--vb-text);
}

.vb-metric__label {
  margin-top: 4px;
  font-size: 13px;
  color: var(--vb-text-tertiary);
}

.vb-metric__trend {
  margin-top: var(--vb-space-sm);
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
}

.vb-metric__trend--up {
  color: var(--vb-success);
}

.vb-metric__trend--down {
  color: var(--vb-error);
}

.vb-metric__trend-label {
  color: var(--vb-text-tertiary);
  font-weight: 400;
}
</style>
