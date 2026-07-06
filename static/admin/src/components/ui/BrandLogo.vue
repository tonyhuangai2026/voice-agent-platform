<!--
  BrandLogo — shared brand mark + wordmark.

  (Formerly kept byte-identical with the demo SPA's copy; the demo SPA was
  removed in the single-page merge — this is now the sole copy.)

  Self-drawn SVG mark + wordmark. No "Demo" text. References only --vb-* tokens (follows
  dark mode). No business logic.

  Props:
    title    — wordmark text (default "Voice Bot")
    subtitle — small line under the wordmark (optional)
-->
<template>
  <div class="vb-brand">
    <svg
      class="vb-brand__mark"
      viewBox="0 0 36 36"
      width="36"
      height="36"
      role="img"
      aria-hidden="true"
    >
      <rect x="0" y="0" width="36" height="36" rx="8" fill="var(--vb-primary)" />
      <!-- Stylized soundwave: three bars rising then accent dot -->
      <rect x="9" y="15" width="3" height="6" rx="1.5" fill="var(--vb-on-primary)" />
      <rect x="15" y="11" width="3" height="14" rx="1.5" fill="var(--vb-on-primary)" />
      <rect x="21" y="8" width="3" height="20" rx="1.5" fill="var(--vb-on-primary)" />
      <circle cx="28.5" cy="11" r="2.5" fill="var(--vb-accent)" />
    </svg>
    <div v-if="title || subtitle" class="vb-brand__text">
      <div v-if="title" class="vb-brand__title">{{ title }}</div>
      <div v-if="subtitle" class="vb-brand__sub">{{ subtitle }}</div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: 'Voice Bot' },
  subtitle: { type: String, default: '' },
});
</script>

<style scoped>
.vb-brand {
  display: flex;
  align-items: center;
  gap: var(--vb-space-md);
}

.vb-brand__mark {
  flex: none;
  border-radius: var(--vb-radius-md);
  display: block;
}

.vb-brand__title {
  font-size: 16px;
  font-weight: 600;
  line-height: 1.1;
  color: var(--vb-text);
}

.vb-brand__sub {
  font-size: 11px;
  line-height: 1.2;
  margin-top: 2px;
  color: var(--vb-text-tertiary);
}
</style>
