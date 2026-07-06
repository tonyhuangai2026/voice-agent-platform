<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ pageTitle }}</template>
      <template #subtitle>{{ pageSubtitle }}</template>
    </n-page-header>

    <n-alert :type="alertType" style="margin-bottom: 16px;">
      {{ alertText }}
    </n-alert>

    <n-card v-if="loading" :bordered="true">
      <n-skeleton :rows="6" />
    </n-card>

    <template v-else>
      <n-card :bordered="true" style="margin-bottom: 16px;">
        <template #header>
          <n-space :size="8" align="center">
            <n-icon :component="Voicemail" :depth="3" />
            {{ t('defaultsForm.sections.engineDemo') }}
          </n-space>
        </template>
        <n-grid :cols="2" :x-gap="20" :y-gap="16" responsive="screen" item-responsive>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('defaultsForm.fields.engine')">
              <n-select v-model:value="form.engine" :options="engineOptions" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('defaultsForm.fields.lang')">
              <n-select v-model:value="form.lang" :options="langOptions" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item span="2">
            <n-form-item :label="t('defaultsForm.fields.demo')">
              <n-select
                v-model:value="form.demo"
                :options="demoOptions"
                filterable
              />
            </n-form-item>
          </n-grid-item>
        </n-grid>
      </n-card>

      <!-- Voice picker — always visible. Both pipeline (per-provider voices)
           and nova-sonic (grouped nova voices) select a voice here, so it must
           NOT live under the pipeline-only hint. -->
      <n-card :bordered="true" style="margin-bottom: 16px;">
        <template #header>
          <n-space :size="8" align="center">
            <n-icon :component="UserSpeaker" :depth="3" />
            {{ t('defaultsForm.sections.voice') }}
          </n-space>
        </template>
        <n-grid :cols="2" :x-gap="20" :y-gap="16" responsive="screen" item-responsive>
          <n-grid-item span="2 m:1">
            <n-form-item :label="isNovaSonic ? t('defaultsForm.fields.novaVoiceId') : t('defaultsForm.fields.voiceId')">
              <n-select
                v-model:value="form.voice"
                :options="voiceOptions"
                filterable
              />
            </n-form-item>
          </n-grid-item>
        </n-grid>
      </n-card>

      <!-- Pipeline-only fields (LLM / TTS provider / MiniMax model). Nova Sonic
           runs end-to-end and does not read these, so the whole card is hidden
           when nova-sonic is selected. -->
      <n-card v-if="!isNovaSonic" :bordered="true" style="margin-bottom: 16px;">
        <template #header>
          <n-space :size="8" align="center">
            <n-icon :component="Tools" :depth="3" />
            {{ t('defaultsForm.sections.pipeline') }}
          </n-space>
        </template>
        <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
          {{ t('defaultsForm.pipelineHint') }}
        </n-text>
        <n-grid :cols="2" :x-gap="20" :y-gap="16" responsive="screen" item-responsive>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('defaultsForm.fields.llmModel')">
              <n-select v-model:value="form.model" :options="modelOptions" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('defaultsForm.fields.ttsProvider')">
              <n-select v-model:value="form.provider" :options="providerOptions" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('defaultsForm.fields.minimaxModel')">
              <n-select v-model:value="form.minimax_model" :options="minimaxModelOptions" />
            </n-form-item>
          </n-grid-item>
        </n-grid>
      </n-card>

      <!-- ASR hallucination filter (tech_design §7). Default OFF; pipeline-only
           (Nova Sonic uses server-side STT); per-demo settings override this. -->
      <n-card :bordered="true" style="margin-bottom: 16px;">
        <template #header>
          <n-space :size="8" align="center">
            <n-icon :component="Filter" :depth="3" />
            {{ t('config.asrFilter.title') }}
          </n-space>
        </template>
        <n-text depth="3" style="display:block; margin-bottom: 12px; font-size: 12px;">
          {{ t('config.asrFilter.note') }}
        </n-text>
        <n-grid :cols="2" :x-gap="20" :y-gap="16" responsive="screen" item-responsive>
          <n-grid-item span="2">
            <n-form-item :label="t('config.asrFilter.enabled')">
              <n-switch v-model:value="asrFilter.enabled" />
            </n-form-item>
          </n-grid-item>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('config.asrFilter.minConfidence')">
              <n-input-number
                v-model:value="asrFilter.min_confidence"
                :min="0"
                :max="1"
                :step="0.05"
                style="width: 100%;"
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('config.asrFilter.maxChars')">
              <n-input-number
                v-model:value="asrFilter.max_chars"
                :min="0"
                :precision="0"
                style="width: 100%;"
              />
            </n-form-item>
          </n-grid-item>
          <n-grid-item span="2 m:1">
            <n-form-item :label="t('config.asrFilter.maxWords')">
              <n-input-number
                v-model:value="asrFilter.max_words"
                :min="0"
                :precision="0"
                style="width: 100%;"
              />
            </n-form-item>
          </n-grid-item>
        </n-grid>
      </n-card>

      <n-space justify="end" style="margin-top: 24px;">
        <n-button @click="reset">
          <template #icon><n-icon :component="Reset" /></template>
          {{ t('defaultsForm.actions.reset') }}
        </n-button>
        <n-button type="primary" :loading="saving" @click="save">
          <template #icon><n-icon :component="Save" /></template>
          {{ t('defaultsForm.actions.save') }}
        </n-button>
      </n-space>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  NPageHeader,
  NCard,
  NAlert,
  NGrid,
  NGridItem,
  NFormItem,
  NIcon,
  NSelect,
  NButton,
  NSpace,
  NSkeleton,
  NText,
  NSwitch,
  NInputNumber,
  useMessage,
} from 'naive-ui';
import { Voicemail, Tools, UserSpeaker, Reset, Save, Filter } from '@vicons/carbon';
import { useConfigStore } from '../stores/config.js';
import {
  asrFilterFromConfig,
  asrFilterPutBlock,
  asrFilterChanged,
} from '../asrFilter.js';

const props = defineProps({
  segment: { type: String, required: true }, // 'web' | 'phone'
  pageTitle: { type: String, required: true },
  pageSubtitle: { type: String, required: true },
  alertText: { type: String, required: true },
  alertType: { type: String, default: 'info' },
});

const { t } = useI18n();
const message = useMessage();
const store = useConfigStore();
const loading = ref(true);
const saving = ref(false);

const form = reactive({
  engine: '',
  lang: '',
  demo: '',
  model: '',
  provider: '',
  voice: '',
  minimax_model: '',
});

let snapshot = {};

// ASR hallucination-filter sub-block (tech_design §7). Kept OUT of `form`
// because it is a NESTED object (PUT body nests it under `asr_filter`) whereas
// `form` holds flat scalar keys diffed one-for-one; mixing them would break the
// flat snapshot diff in save(). Loaded from / saved to segment.asr_filter via
// the pure helpers in asrFilter.js (which are unit-tested).
const asrFilter = reactive(asrFilterFromConfig(null));
let asrSnapshot = { ...asrFilter };

function fillFrom(src) {
  for (const k of Object.keys(form)) form[k] = src[k] || '';
  snapshot = { ...form };
  const af = asrFilterFromConfig(src);
  for (const k of Object.keys(af)) asrFilter[k] = af[k];
  asrSnapshot = { ...asrFilter };
}

const opts = computed(() => store.options || {});

function toSelect(arr, label = 'label', value = 'id') {
  return (arr || []).map((x) => ({ label: x[label] ?? x.id, value: x[value] }));
}

const engineOptions = computed(() => toSelect(opts.value.engines));

// Languages available for the selected engine. The backend (T1) tags each
// language with an `engines: string[]`; a missing/undefined `engines` is
// treated as "available for all engines" so this stays correct even before
// that field ships. Returns the raw language objects (with `engines`) for
// reuse by the engine-change normalization watcher.
const availableLanguages = computed(() =>
  (opts.value.languages || []).filter(
    (l) => !l.engines || l.engines.includes(form.engine),
  ),
);
const langOptions = computed(() => toSelect(availableLanguages.value));
const demoOptions = computed(() => toSelect(opts.value.demos));
const modelOptions = computed(() => toSelect(opts.value.models));
const providerOptions = computed(() => toSelect(opts.value.providers));
const minimaxModelOptions = computed(() => toSelect(opts.value.minimax_models));
const isNovaSonic = computed(() => form.engine === 'nova-sonic');

// Build "Tiffany (F · Polyglot)" / "Lorenzo (M)" style labels.
function novaVoiceLabel(v) {
  const tags = [v.gender].filter(Boolean);
  if (v.polyglot) tags.push(t('defaultsForm.polyglot'));
  return tags.length ? `${v.label} (${tags.join(' · ')})` : v.label;
}

// Group the flat nova_sonic_voices list into naive-ui n-select group options,
// keyed by lang_label. Not coupled to the session language — purely organizes
// the picker (Nova Sonic does not support Chinese, etc.).
function novaGroupedOptions(list) {
  const groups = [];
  const byLang = new Map();
  for (const v of list) {
    const key = v.lang_label || v.locale || '';
    let g = byLang.get(key);
    if (!g) {
      g = { type: 'group', label: key, key: `nova-${key}`, children: [] };
      byLang.set(key, g);
      groups.push(g);
    }
    g.children.push({ label: novaVoiceLabel(v), value: v.id });
  }
  return groups;
}

const voiceOptions = computed(() => {
  if (isNovaSonic.value) {
    return novaGroupedOptions(opts.value.nova_sonic_voices || []);
  }
  const provider = form.provider || 'minimax';
  const list = (opts.value.voices_by_provider || {})[provider] || [];
  return list.map((v) => ({ label: `${v.label} · ${v.language}`, value: v.id }));
});

// Set of valid Nova Sonic voice ids, and the engine's default voice. Both the
// admin options payload and /api/config now carry `default_nova_sonic_voice`;
// fall back to the first voice in the list only for older/partial payloads.
const novaVoiceIds = computed(
  () => new Set((opts.value.nova_sonic_voices || []).map((v) => v.id)),
);
const defaultNovaVoice = computed(
  () =>
    opts.value.default_nova_sonic_voice ||
    (opts.value.nova_sonic_voices || [])[0]?.id ||
    '',
);

// When the engine changes, normalize lang/voice so we never leave an illegal
// combo (e.g. nova-sonic + zh-CN, or a MiniMax voice id under nova-sonic).
watch(
  () => form.engine,
  () => {
    const langs = availableLanguages.value;
    if (langs.length && !langs.some((l) => l.id === form.lang)) {
      form.lang = langs[0].id;
    }
    if (isNovaSonic.value) {
      if (!novaVoiceIds.value.has(form.voice)) {
        form.voice = defaultNovaVoice.value;
      }
    }
  },
);

async function ensureLoaded() {
  if (!store.loaded) {
    await store.loadAll();
  }
}

onMounted(async () => {
  try {
    await ensureLoaded();
    fillFrom(store[props.segment]);
  } catch (e) {
    message.error(t('defaultsForm.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
});

watch(
  () => store[props.segment],
  (v) => {
    if (!loading.value) fillFrom(v);
  },
  { deep: true },
);

async function save() {
  saving.value = true;
  try {
    const updates = {};
    for (const k of Object.keys(form)) {
      if (form[k] !== snapshot[k]) updates[k] = form[k];
    }
    // Nest the ASR-filter block under `asr_filter` only when touched. The
    // backend read-merge-writes it, so emitting the full four-key object is
    // fine (asrFilterPutBlock coerces types: bool / float / int / int).
    if (asrFilterChanged(asrFilter, asrSnapshot)) {
      updates.asr_filter = asrFilterPutBlock(asrFilter);
    }
    if (Object.keys(updates).length === 0) {
      message.info(t('defaultsForm.messages.noChanges'));
      return;
    }
    if (props.segment === 'web') await store.saveWeb(updates);
    else await store.savePhone(updates);
    snapshot = { ...form };
    asrSnapshot = { ...asrFilter };
    message.success(t('defaultsForm.messages.saved'));
  } catch (e) {
    message.error(t('defaultsForm.messages.saveFailed', { msg: e.message }));
  } finally {
    saving.value = false;
  }
}

function reset() {
  for (const k of Object.keys(form)) form[k] = snapshot[k];
  for (const k of Object.keys(asrSnapshot)) asrFilter[k] = asrSnapshot[k];
  message.info(t('defaultsForm.messages.restored'));
}
</script>
