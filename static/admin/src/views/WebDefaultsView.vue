<template>
  <DefaultsForm
    segment="web"
    :page-title="t('web.title')"
    :page-subtitle="t('web.subtitle')"
    :alert-text="t('web.alert')"
    alert-type="info"
  />
</template>

<script setup>
import { useI18n } from 'vue-i18n';
import DefaultsForm from './DefaultsForm.vue';

const { t } = useI18n();
</script>
