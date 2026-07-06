<!--
  StatChip — compact status / meta chip (dot + label).

  (Formerly kept byte-identical with the demo SPA's copy; the demo SPA was
  removed in the single-page merge — this is now the sole copy.)

  Used for connection state, engine / lang / voice meta. References only --vb-*
  tokens (follows dark mode). No business logic.

  Props:
    label — chip text
    tone  — semantic color of the dot: default | success | warning | error | info | accent
    dot   — show the leading dot (default true)
-->
<template>
  <span class="vb-chip">
    <span v-if="dot" class="vb-chip__dot" :style="{ background: dotColor }"></span>
    <span class="vb-chip__label"><slot>{{ label }}</slot></span>
  </span>
</template>

<script setup>
import { computed } from 'vue';

const props = defineProps({
  label: { type: String, default: '' },
  tone: {
    type: String,
    default: 'default',
    validator: (v) =>
      ['default', 'success', 'warning', 'error', 'info', 'accent'].includes(v),
  },
  dot: { type: Boolean, default: true },
});

const TONE_VAR = {
  default: 'var(--vb-text-tertiary)',
  success: 'var(--vb-success)',
  warning: 'var(--vb-warning)',
  error: 'var(--vb-error)',
  info: 'var(--vb-info)',
  accent: 'var(--vb-accent)',
};

const dotColor = computed(() => TONE_VAR[props.tone] || TONE_VAR.default);
</script>

<style scoped>
.vb-chip {
  display: inline-flex;
  align-items: center;
  gap: var(--vb-space-sm);
  height: 24px;
  padding: 0 10px;
  border-radius: 999px;
  background: var(--vb-surface-alt);
  border: 1px solid var(--vb-border);
  font-size: 12px;
  line-height: 1;
  color: var(--vb-text-secondary);
  white-space: nowrap;
}

.vb-chip__dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex: none;
}

.vb-chip__label {
  display: inline-flex;
  align-items: center;
}
</style>
