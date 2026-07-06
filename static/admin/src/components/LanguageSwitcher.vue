<template>
  <n-select
    :value="locale"
    :options="options"
    size="small"
    style="width: 130px;"
    @update:value="onChange"
  />
</template>

<script setup>
// LanguageSwitcher.vue — top-right NSelect for runtime locale switching.
// See tech_design §3.4. Reads/writes the active locale via vue-i18n + the
// shared setLocale() helper from src/i18n/index.js (which persists the
// choice to localStorage['app.lang'] and updates <html lang=...>).
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { NSelect } from 'naive-ui';
import { SUPPORTED_LOCALES, setLocale } from '../i18n/index.js';

const { locale } = useI18n();
const options = computed(() =>
  SUPPORTED_LOCALES.map((l) => ({ label: l.label, value: l.code })),
);

function onChange(v) {
  setLocale(v);
}
</script>
