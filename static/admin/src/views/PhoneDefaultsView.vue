<template>
  <div class="phone-defaults-root">
    <DefaultsForm
      segment="phone"
      :page-title="t('phone.title')"
      :page-subtitle="t('phone.subtitle')"
      :alert-text="t('phone.alert')"
      alert-type="warning"
    />

    <!-- Read-only Chime VC ↔ phone-number view (GET /api/admin/phone-numbers).
         Pure display — no actions. Best-effort: backend returns 200 even on a
         Chime error, with the reason in `error`. -->
    <n-card :title="t('phoneNumbers.title')" class="pn-card" data-test="pn-card">
      <n-text depth="3" class="pn-subtitle">{{ t('phoneNumbers.subtitle') }}</n-text>

      <n-alert
        v-if="pnError"
        type="warning"
        :show-icon="true"
        class="pn-alert"
        data-test="pn-error"
      >
        {{ t('phoneNumbers.error', { msg: pnError }) }}
      </n-alert>

      <n-spin :show="pnLoading">
        <n-empty
          v-if="!pnLoading && !pnError && rows.length === 0"
          :description="t('phoneNumbers.empty')"
          data-test="pn-empty"
        />
        <n-table v-else-if="rows.length" :bordered="true" size="small" data-test="pn-table">
          <thead>
            <tr>
              <th>{{ t('phoneNumbers.colVc') }}</th>
              <th>{{ t('phoneNumbers.colVcId') }}</th>
              <th>{{ t('phoneNumbers.colE164') }}</th>
              <th>{{ t('phoneNumbers.colStatus') }}</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="(r, i) in rows" :key="i" data-test="pn-row">
              <td>{{ r.voice_connector_name || '—' }}</td>
              <td class="pn-mono">{{ r.voice_connector_id || '—' }}</td>
              <td class="pn-mono">{{ r.e164 || t('phoneNumbers.none') }}</td>
              <td>{{ r.status || '—' }}</td>
            </tr>
          </tbody>
        </n-table>
      </n-spin>
    </n-card>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue';
import { useI18n } from 'vue-i18n';
import { NCard, NTable, NText, NAlert, NEmpty, NSpin } from 'naive-ui';
import DefaultsForm from './DefaultsForm.vue';
import { api } from '../api.js';

const { t } = useI18n();

const rows = ref([]);
const pnError = ref('');
const pnLoading = ref(false);

async function loadPhoneNumbers() {
  pnLoading.value = true;
  pnError.value = '';
  try {
    const data = await api.phoneNumbers();
    rows.value = Array.isArray(data?.voice_connectors) ? data.voice_connectors : [];
    // Backend is best-effort: it returns 200 with an `error` string when Chime
    // could not be read (e.g. missing IAM permission). Surface that as a notice.
    if (data?.error) pnError.value = String(data.error);
  } catch (e) {
    // Network / non-200 (e.g. not admin) — still don't crash the page.
    pnError.value = e?.message || 'request failed';
    rows.value = [];
  } finally {
    pnLoading.value = false;
  }
}

onMounted(loadPhoneNumbers);

// Exposed for unit tests to drive load + assert state without a real network.
defineExpose({ loadPhoneNumbers, rows, pnError, pnLoading });
</script>

<style scoped>
.phone-defaults-root {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-lg, 16px);
}
.pn-card {
  margin-top: var(--vb-space-md, 12px);
}
.pn-subtitle {
  display: block;
  font-size: 12px;
  margin-bottom: 12px;
}
.pn-alert {
  margin-bottom: 12px;
}
.pn-mono {
  font-family: var(--vb-font-mono, monospace);
  font-size: 13px;
}
</style>
