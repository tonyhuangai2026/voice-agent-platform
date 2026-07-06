<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ t('voices.title') }}</template>
      <template #subtitle>{{ t('voices.subtitle') }}</template>
      <template #extra>
        <n-space :size="8">
          <n-button @click="load" :loading="loading">
            <template #icon><n-icon :component="Renew" /></template>
            {{ t('common.refresh') }}
          </n-button>
          <n-button type="primary" @click="openCreate">
            <template #icon><n-icon :component="Add" /></template>
            {{ t('voices.actions.add') }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-alert type="info" style="margin-bottom: 16px;">
      <span v-html="t('voices.notice')" />
    </n-alert>

    <!-- One tab per provider; the active tab decides which voices and which
         provider-specific column/form fields are shown. -->
    <n-tabs v-model:value="provider" type="line" animated @update:value="onTabChange">
      <n-tab-pane
        v-for="p in PROVIDERS"
        :key="p"
        :name="p"
        :tab="t('voices.providers.' + providerKey(p))"
      >
        <n-card :bordered="true">
          <n-data-table
            :columns="columns"
            :data="rowsForProvider"
            :loading="loading"
            :pagination="{ pageSize: 10 }"
            :row-key="(row) => row.voice_id"
          >
            <template #empty>
              <EmptyState :title="t('voices.emptyTitle')" :description="t('voices.emptyDesc')">
                <template #icon><n-icon :component="VolumeUp" /></template>
                <n-button type="primary" size="small" @click="openCreate">
                  <template #icon><n-icon :component="Add" /></template>
                  {{ t('voices.actions.add') }}
                </n-button>
              </EmptyState>
            </template>
          </n-data-table>
        </n-card>
      </n-tab-pane>
    </n-tabs>

    <!-- Add / edit modal. Fields are CONDITIONAL on the selected provider —
         the list comes from the pure helper voiceFormFields(provider). -->
    <n-modal
      v-model:show="modalOpen"
      preset="card"
      :title="editing ? t('voices.form.titleEdit') : t('voices.form.titleNew')"
      style="width: 520px; max-width: 92vw;"
      :mask-closable="false"
    >
      <n-form label-placement="top">
        <template v-for="field in formFields" :key="field.key">
          <!-- voice_id is the composite SK: required, immutable on edit. -->
          <n-form-item :label="fieldLabel(field.key)">
            <n-input
              v-if="field.type === 'text'"
              v-model:value="form[field.key]"
              :disabled="field.key === 'voice_id' && editing"
              :placeholder="fieldPlaceholder(field.key)"
            />
            <n-input-number
              v-else-if="field.type === 'number'"
              v-model:value="form[field.key]"
              :placeholder="fieldPlaceholder(field.key)"
              style="width: 100%;"
            />
            <n-select
              v-else-if="field.type === 'select' && field.key === 'gender'"
              v-model:value="form[field.key]"
              clearable
              :options="genderOptions"
              :placeholder="fieldPlaceholder(field.key)"
            />
            <n-switch v-else-if="field.type === 'switch'" v-model:value="form[field.key]" />
          </n-form-item>
        </template>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="modalOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button
            type="primary"
            :loading="saving"
            :disabled="!formValid"
            @click="save"
          >
            {{ t('common.save') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  NPageHeader,
  NCard,
  NAlert,
  NSpace,
  NButton,
  NDataTable,
  NTabs,
  NTabPane,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputNumber,
  NModal,
  NSelect,
  NSwitch,
  NTag,
  useDialog,
  useMessage,
} from 'naive-ui';
import { Renew, Add, VolumeUp, Edit, TrashCan } from '@vicons/carbon';
import { api } from '../api.js';
import {
  PROVIDERS,
  voiceFormFields,
  extraColumnFor,
  langKeyFor,
  defaultFormValues,
  isVoiceFormValid,
  buildVoiceAttrs,
  voicesForProvider,
  normalizeVoicesResponse,
} from '../voiceFields.js';
import EmptyState from '../components/ui/EmptyState.vue';

const { t } = useI18n();
const message = useMessage();
const dialog = useDialog();

// All voices, kept as a flat list; the active tab filters by provider.
const voices = ref([]);
const loading = ref(false);
const saving = ref(false);

const provider = ref(PROVIDERS[0]);

const modalOpen = ref(false);
const editing = ref(false);
// Reactive form keyed by the active provider's field set. Reset on open.
const form = reactive({});

// i18n key for a provider id (nova-sonic → novaSonic).
function providerKey(p) {
  return p === 'nova-sonic' ? 'novaSonic' : p;
}

const genderOptions = computed(() => [
  { label: t('voices.gender.male'), value: 'male' },
  { label: t('voices.gender.female'), value: 'female' },
  { label: t('voices.gender.neutral'), value: 'neutral' },
]);

// Field descriptor list for the CURRENT provider (pure helper).
const formFields = computed(() => voiceFormFields(provider.value));

const rowsForProvider = computed(() =>
  voicesForProvider(voices.value, provider.value),
);

const formValid = computed(() => isVoiceFormValid(provider.value, form));

// Localized label for a field; falls back to the raw key if no translation.
function fieldLabel(key) {
  return t('voices.fields.' + key);
}
function fieldPlaceholder(key) {
  if (key === 'voice_id') return t('voices.form.voiceIdPlaceholder');
  return '';
}

// The shared language|locale column key + the provider-specific extra column.
const langKey = computed(() => langKeyFor(provider.value));
const extraCol = computed(() => extraColumnFor(provider.value));

function renderExtra(row) {
  const key = extraCol.value;
  if (!key) return t('common.dash');
  const val = row[key];
  if (key === 'polyglot') {
    return h(
      NTag,
      { size: 'small', type: val ? 'success' : 'default', bordered: false },
      () => (val ? t('common.yes') : t('common.no')),
    );
  }
  if (val === undefined || val === null || val === '') return t('common.dash');
  return String(val);
}

const columns = computed(() => {
  const cols = [
    {
      title: t('voices.columns.voiceId'),
      key: 'voice_id',
      width: 170,
      render: (row) =>
        h(
          'span',
          { style: 'font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;' },
          row.voice_id,
        ),
    },
    { title: t('voices.columns.label'), key: 'label', width: 150 },
    {
      title: t('voices.columns.gender'),
      key: 'gender',
      width: 100,
      render: (row) => row.gender || t('common.dash'),
    },
    {
      title: t('voices.columns.language'),
      key: langKey.value,
      width: 120,
      render: (row) => row[langKey.value] || t('common.dash'),
    },
    {
      title: t('voices.columns.' + extraCol.value),
      key: extraCol.value,
      width: 110,
      render: (row) => renderExtra(row),
    },
    {
      title: t('common.actions'),
      key: 'actions',
      width: 160,
      render: (row) =>
        h(NSpace, { size: 6 }, () => [
          h(
            NButton,
            { size: 'small', onClick: () => openEdit(row) },
            {
              icon: () => h(NIcon, null, { default: () => h(Edit) }),
              default: () => t('common.edit'),
            },
          ),
          h(
            NButton,
            { size: 'small', type: 'error', secondary: true, onClick: () => confirmDelete(row) },
            {
              icon: () => h(NIcon, null, { default: () => h(TrashCan) }),
              default: () => t('common.delete'),
            },
          ),
        ]),
    },
  ];
  return cols;
});

async function load() {
  loading.value = true;
  try {
    // T2 returns a provider-keyed dict ({ voices: { minimax: [{id,...}], ... },
    // live }) keyed by `id`; normalize to a flat list carrying provider +
    // voice_id so the table / helpers work on one uniform shape.
    const data = await api.listVoices();
    voices.value = normalizeVoicesResponse(data);
  } catch (e) {
    message.error(t('voices.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

function onTabChange() {
  // Tab switch only changes the filtered view; no reload needed (the list is
  // loaded once and filtered client-side).
}

// Reset `form` to a blank descriptor-seeded object for the active provider.
function resetForm() {
  for (const k of Object.keys(form)) delete form[k];
  Object.assign(form, defaultFormValues(provider.value));
}

function openCreate() {
  editing.value = false;
  resetForm();
  modalOpen.value = true;
}

function openEdit(row) {
  editing.value = true;
  resetForm();
  // Pre-fill from the row; only keys present in the provider's field set are
  // touched (resetForm already seeded them).
  for (const field of voiceFormFields(provider.value)) {
    if (row[field.key] !== undefined && row[field.key] !== null) {
      form[field.key] = row[field.key];
    }
  }
  modalOpen.value = true;
}

async function save() {
  saving.value = true;
  try {
    const attrs = buildVoiceAttrs(provider.value, form);
    if (editing.value) {
      await api.updateVoice(provider.value, form.voice_id, attrs);
    } else {
      // Backend canonical key is `id` (it also accepts `voice_id`); send `id`.
      await api.createVoice({
        provider: provider.value,
        id: (form.voice_id || '').trim(),
        ...attrs,
      });
    }
    message.success(t('voices.messages.saved'));
    modalOpen.value = false;
    await load();
  } catch (e) {
    message.error(t('voices.messages.saveFailed', { msg: e.message }));
  } finally {
    saving.value = false;
  }
}

function confirmDelete(row) {
  dialog.warning({
    title: t('voices.deleteConfirm.title'),
    content: t('voices.deleteConfirm.body', { id: row.voice_id }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => doDelete(row),
  });
}

async function doDelete(row) {
  try {
    await api.deleteVoice(row.provider, row.voice_id);
    message.success(t('voices.messages.deleted'));
    await load();
  } catch (e) {
    message.error(t('voices.messages.deleteFailed', { msg: e.message }));
  }
}

onMounted(load);
</script>
