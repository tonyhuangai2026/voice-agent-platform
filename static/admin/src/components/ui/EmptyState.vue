<!--
  EmptyState — unified empty / no-data placeholder (icon + title + description).

  (Formerly kept byte-identical with the demo SPA's copy; the demo SPA was
  removed in the single-page merge — this is now the sole copy.)

  References only --vb-* tokens (follows dark mode). No business logic.

  Props:
    title       — headline
    description — supporting text
  Slots:
    icon    — leading icon (e.g. <n-icon :component="Catalog" />)
    default  — optional action area (e.g. a button) rendered below the text
-->
<template>
  <div class="vb-empty">
    <div v-if="$slots.icon" class="vb-empty__icon"><slot name="icon" /></div>
    <div v-if="title" class="vb-empty__title">{{ title }}</div>
    <div v-if="description" class="vb-empty__desc">{{ description }}</div>
    <div v-if="$slots.default" class="vb-empty__action"><slot /></div>
  </div>
</template>

<script setup>
defineProps({
  title: { type: String, default: '' },
  description: { type: String, default: '' },
});
</script>

<style scoped>
.vb-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  padding: var(--vb-space-xxl) var(--vb-space-xl);
  color: var(--vb-text-tertiary);
}

.vb-empty__icon {
  width: 56px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--vb-radius-lg);
  background: var(--vb-surface-alt);
  color: var(--vb-text-tertiary);
  font-size: 30px;
  margin-bottom: var(--vb-space-lg);
}

.vb-empty__title {
  font-size: 15px;
  font-weight: 600;
  color: var(--vb-text-secondary);
}

.vb-empty__desc {
  margin-top: var(--vb-space-sm);
  font-size: 13px;
  max-width: 360px;
  line-height: 1.5;
  color: var(--vb-text-tertiary);
}

.vb-empty__action {
  margin-top: var(--vb-space-lg);
}
</style>
