<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ t('history.title') }}</template>
      <template #subtitle>
        {{ t('history.subtitle') }}
      </template>
      <template #extra>
        <n-space :size="8">
          <n-button @click="reload" :loading="loading">
            <template #icon><n-icon :component="Renew" /></template>
            {{ t('history.actions.refresh') }}
          </n-button>
          <n-button type="primary" @click="exportCsv">
            <template #icon><n-icon :component="DocumentExport" /></template>
            {{ t('history.actions.exportCsv') }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-card :bordered="true" style="margin-bottom: 16px;">
      <n-grid
        :cols="24"
        :x-gap="12"
        :y-gap="12"
        responsive="screen"
        item-responsive
      >
        <n-grid-item span="24 m:6">
          <n-form-item :label="t('history.filters.caller')" :show-feedback="false">
            <n-input
              v-model:value="filters.caller"
              :placeholder="t('history.filters.callerPlaceholder')"
              clearable
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item span="24 m:4">
          <n-form-item :label="t('history.filters.outcome')" :show-feedback="false">
            <n-select
              v-model:value="filters.outcome"
              :options="outcomeOptions"
              clearable
              :placeholder="t('history.filters.all')"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item span="24 m:4">
          <n-form-item :label="t('history.filters.engine')" :show-feedback="false">
            <n-select
              v-model:value="filters.engine"
              :options="engineOptions"
              clearable
              :placeholder="t('history.filters.all')"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item span="24 m:4">
          <n-form-item :label="t('history.filters.demo')" :show-feedback="false">
            <n-select
              v-model:value="filters.demo"
              :options="demoOptions"
              clearable
              filterable
              :placeholder="t('history.filters.all')"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item span="24 m:6">
          <n-form-item :label="t('history.filters.dateRange')" :show-feedback="false">
            <n-date-picker
              v-model:value="filters.dateRange"
              type="daterange"
              clearable
              :first-day-of-week="0"
              style="width: 100%;"
            />
          </n-form-item>
        </n-grid-item>
      </n-grid>
    </n-card>

    <n-card :bordered="true">
      <n-data-table
        :columns="columns"
        :data="rows"
        :loading="loading"
        :row-props="rowProps"
        :pagination="false"
        :bordered="false"
        size="small"
      >
        <template #empty>
          <EmptyState :title="t('history.emptyTitle')" :description="t('history.emptyDesc')">
            <template #icon><n-icon :component="RecentlyViewed" /></template>
          </EmptyState>
        </template>
      </n-data-table>
      <div class="load-more">
        <n-button
          @click="loadMore"
          :disabled="!nextCursor || loading"
          :loading="loadingMore"
        >
          {{ nextCursor ? t('history.actions.loadMore') : t('history.actions.noMore') }}
        </n-button>
        <n-text depth="3" style="margin-left: 12px; font-size: 12px;">
          {{ t('history.actions.loadedRows', { n: rows.length }) }}
        </n-text>
      </div>
    </n-card>

    <n-drawer v-model:show="drawerOpen" :width="720" placement="right">
      <n-drawer-content
        :title="detail ? t('history.detail.titlePrefix', { id: detail.call_id }) : ''"
        closable
      >
        <template v-if="detail">
          <n-space style="margin-bottom: 12px;">
            <n-button @click="downloadMd">
              <template #icon><n-icon :component="DocumentDownload" /></template>
              {{ t('history.actions.downloadMd') }}
            </n-button>
            <n-button
              v-if="detail.summary_status !== 'ok'"
              type="primary"
              :loading="summarizing"
              @click="summarizeCurrent"
            >
              <template #icon><n-icon :component="DocumentTasks" /></template>
              {{ t('history.actions.summarize') }}
            </n-button>
          </n-space>

          <n-descriptions :column="2" bordered size="small" label-placement="left">
            <n-descriptions-item :label="t('history.detail.caller')">
              {{ detail.caller || t('common.placeholderDash') }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.startedAt')">
              {{ formatEpoch(detail.started_at) }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.endedAt')">
              {{ formatEpoch(detail.ended_at) }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.duration')">
              {{ formatDuration(detail.duration_s) }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.engine')">
              {{ detail.engine || t('common.placeholderDash') }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.demo')">
              {{ detail.scenario || detail.demo || t('common.placeholderDash') }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.lang')">
              {{ detail.lang || t('common.placeholderDash') }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.outcome')">
              <n-tag
                size="small"
                :type="outcomeTagType(detail.outcome)"
                :bordered="false"
              >
                {{ localOutcome(detail.outcome) }}
              </n-tag>
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.transferred')">
              {{ detail.transfer_requested ? t('history.detail.transferYes') : t('history.detail.transferNo') }}
              <span v-if="detail.transfer_topic">
                · {{ detail.transfer_topic }}
              </span>
            </n-descriptions-item>
            <n-descriptions-item :label="t('history.detail.turns')">
              {{ detail.turn_count ?? (detail.turns ? detail.turns.length : 0) }}
            </n-descriptions-item>
          </n-descriptions>

          <n-divider title-placement="left">{{ t('history.detail.summary') }}</n-divider>
          <template v-if="detail.summary_status === 'ok' && detail.summary">
            <SummaryBlock :summary="detail.summary" />
          </template>
          <template v-else>
            <n-alert
              :type="detail.summary_status === 'failed' ? 'error' : 'warning'"
              :show-icon="false"
              style="margin-bottom: 12px;"
            >
              {{ t('history.detail.noSummary') }}
              <span v-if="detail.summary_status">
                ({{ localSummaryStatus(detail.summary_status) }})
              </span>
              <span v-if="detail.summary_error">
                · {{ detail.summary_error }}
              </span>
            </n-alert>
            <n-button
              type="primary"
              :loading="summarizing"
              @click="summarizeCurrent"
            >
              <template #icon><n-icon :component="DocumentTasks" /></template>
              {{ t('history.actions.summarize') }}
            </n-button>
          </template>

          <n-divider title-placement="left">{{ t('history.detail.transcript') }}</n-divider>
          <template v-if="detail.turns && detail.turns.length">
            <div class="transcript">
              <div
                v-for="(turn, i) in detail.turns"
                :key="i"
                class="bubble-row"
                :class="{
                  'bubble-row--bot': isBot(turn),
                  'bubble-row--user': !isBot(turn),
                }"
              >
                <div
                  class="bubble"
                  :class="{
                    'bubble--bot': isBot(turn),
                    'bubble--user': !isBot(turn),
                  }"
                >
                  <div class="bubble-meta">
                    <n-tag
                      size="tiny"
                      :type="isBot(turn) ? 'info' : 'default'"
                      :bordered="false"
                    >
                      {{ turn.who || turn.role || (isBot(turn) ? 'bot' : 'user') }}
                    </n-tag>
                    <n-text v-if="turn.ts" depth="3" style="font-size: 11px;">
                      {{ formatEpoch(turn.ts) }}
                    </n-text>
                  </div>
                  <div class="bubble-text">{{ turnText(turn) }}</div>
                </div>
              </div>
            </div>
          </template>
          <template v-else>
            <n-text depth="3">{{ t('history.detail.noTurns') }}</n-text>
          </template>
        </template>
      </n-drawer-content>
    </n-drawer>
  </div>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  NPageHeader,
  NCard,
  NGrid,
  NGridItem,
  NFormItem,
  NIcon,
  NInput,
  NSelect,
  NDatePicker,
  NSpace,
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NDescriptions,
  NDescriptionsItem,
  NDivider,
  NAlert,
  NTag,
  NText,
  useMessage,
} from 'naive-ui';
import {
  Renew,
  DocumentExport,
  DocumentDownload,
  DocumentTasks,
  RecentlyViewed,
} from '@vicons/carbon';
import { api } from '../api.js';
import { useConfigStore } from '../stores/config.js';
import SummaryBlock from './_HistorySummary.vue';
import EmptyState from '../components/ui/EmptyState.vue';
import { localOutcome, localSummaryStatus } from '../i18n/enums.js';

const { t } = useI18n();
const message = useMessage();
const store = useConfigStore();

// -- canonical outcome buckets (Tech Design §3 / outcome dimension) --------
// `value` keeps the raw English code (the schema contract with backend); the
// dropdown `label` is localised at render time via a computed wrapper below.
const OUTCOMES = [
  'user_requested',
  'task_completed',
  'transferred',
  'timeout',
  'error',
  'unknown',
];
const outcomeOptions = computed(() =>
  OUTCOMES.map((v) => ({ label: localOutcome(v), value: v })),
);

// Engine list — stays in sync with backend `EngineRouter`. We hard-code here
// because options.engines isn't always loaded; UI is forgiving (extra values
// from DDB rows still render as raw strings in the table).
const engineOptions = [
  { label: 'nova-sonic', value: 'nova-sonic' },
  { label: 'pipeline', value: 'pipeline' },
];

// -- filter state ----------------------------------------------------------
const filters = reactive({
  caller: '',
  outcome: null,
  engine: null,
  demo: null,
  dateRange: null, // [startMs, endMs] from n-date-picker
});

// -- list state ------------------------------------------------------------
const rows = ref([]);
const nextCursor = ref(null);
const loading = ref(false);
const loadingMore = ref(false);

// -- detail / drawer state -------------------------------------------------
const drawerOpen = ref(false);
const detail = ref(null);
const summarizing = ref(false);

// Demo options pulled from the shared config store (already populated for
// /web /phone defaults pages). Fall back to /api/admin/options if the store
// hasn't been hydrated yet.
const demoOptions = ref([]);
async function ensureDemoOptions() {
  try {
    if (store.options?.demos?.length) {
      demoOptions.value = store.options.demos.map((d) => ({
        label: d.label || d.id,
        value: d.id,
      }));
      return;
    }
    if (!store.loaded) {
      // Lazy-load the full config store (covers /options).
      try {
        await store.loadAll();
      } catch {
        /* fall through to direct fetch */
      }
    }
    if (store.options?.demos?.length) {
      demoOptions.value = store.options.demos.map((d) => ({
        label: d.label || d.id,
        value: d.id,
      }));
      return;
    }
    const opts = await api.options();
    const list = opts?.demos || [];
    demoOptions.value = list.map((d) => ({
      label: d.label || d.id,
      value: d.id,
    }));
  } catch (e) {
    // Demo filter is optional; don't blow up the page.
    demoOptions.value = [];
  }
}

// -- helpers ---------------------------------------------------------------
function outcomeTagType(o) {
  switch (o) {
    case 'task_completed':
      return 'success';
    case 'user_requested':
      return 'info';
    case 'transferred':
      return 'warning';
    case 'timeout':
      return 'warning';
    case 'error':
      return 'error';
    default:
      return 'default';
  }
}

function summaryStatusType(s) {
  if (s === 'ok') return 'success';
  if (s === 'failed') return 'error';
  if (s === 'pending') return 'warning';
  return 'default';
}

function formatEpoch(epoch) {
  if (!epoch) return t('common.placeholderDash');
  const n = typeof epoch === 'number' ? epoch : Number(epoch);
  if (!Number.isFinite(n)) return String(epoch);
  // DDB stores epoch seconds; tolerate ms in case a future row drifts.
  const ms = n > 1e12 ? n : n * 1000;
  try {
    return new Date(ms).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, 'Z');
  } catch {
    return String(epoch);
  }
}

function formatDuration(s) {
  if (s === undefined || s === null || s === '') return t('common.placeholderDash');
  const n = Number(s);
  if (!Number.isFinite(n)) return String(s);
  if (n < 60) return `${n.toFixed(0)}s`;
  const m = Math.floor(n / 60);
  const r = Math.round(n % 60);
  return `${m}m ${r}s`;
}

function isBot(turn) {
  const role = (turn?.who || turn?.role || '').toLowerCase();
  return role === 'bot' || role === 'assistant' || role === 'agent';
}

function turnText(turn) {
  if (!turn) return '';
  if (typeof turn === 'string') return turn;
  return turn.text || turn.content || turn.message || '';
}

// -- query construction ---------------------------------------------------
function buildQueryParams({ withCursor = true } = {}) {
  const p = {};
  if (filters.caller) p.caller = filters.caller.trim();
  if (filters.outcome) p.outcome = filters.outcome;
  if (filters.engine) p.engine = filters.engine;
  if (filters.demo) p.demo = filters.demo;
  if (Array.isArray(filters.dateRange) && filters.dateRange.length === 2) {
    const [a, b] = filters.dateRange;
    if (a) p.start_after = Math.floor(a / 1000);
    if (b) p.start_before = Math.floor(b / 1000);
  }
  if (withCursor && nextCursor.value) p.cursor = nextCursor.value;
  return p;
}

// -- table columns --------------------------------------------------------
// Columns are a `computed` so titles + functional renders re-evaluate when
// the active locale changes. Functional renders capture `t` from setup
// scope (vue-i18n's reactive `locale.value` makes the `computed` re-run).
const columns = computed(() => [
  {
    title: t('history.columns.startedAt'),
    key: 'started_at',
    width: 180,
    render: (row) => formatEpoch(row.started_at),
  },
  { title: t('history.columns.caller'), key: 'caller', width: 150 },
  {
    title: t('history.columns.outcome'),
    key: 'outcome',
    width: 140,
    render: (row) =>
      h(
        NTag,
        {
          size: 'small',
          type: outcomeTagType(row.outcome),
          bordered: false,
        },
        () => localOutcome(row.outcome),
      ),
  },
  { title: t('history.columns.engine'), key: 'engine', width: 110 },
  {
    title: t('history.columns.demo'),
    key: 'scenario',
    width: 140,
    render: (row) => row.scenario || row.demo || t('common.placeholderDash'),
  },
  {
    title: t('history.columns.duration'),
    key: 'duration_s',
    width: 100,
    render: (row) => formatDuration(row.duration_s),
  },
  {
    title: t('history.columns.summary'),
    key: 'summary_status',
    width: 110,
    render: (row) =>
      h(
        NTag,
        {
          size: 'small',
          type: summaryStatusType(row.summary_status),
          bordered: false,
        },
        () => localSummaryStatus(row.summary_status),
      ),
  },
  {
    title: t('history.columns.actions'),
    key: '__actions',
    width: 90,
    render: (row) =>
      h(
        NButton,
        {
          size: 'tiny',
          type: 'primary',
          tertiary: true,
          onClick: (e) => {
            // Don't double-fire with rowProps.onClick.
            e.stopPropagation();
            openDetail(row.call_id);
          },
        },
        () => t('history.actions.view'),
      ),
  },
]);

function rowProps(row) {
  return {
    style: 'cursor: pointer;',
    onClick: () => openDetail(row.call_id),
  };
}

// -- data fetch -----------------------------------------------------------
async function reload() {
  loading.value = true;
  rows.value = [];
  nextCursor.value = null;
  try {
    const params = buildQueryParams({ withCursor: false });
    params.limit = 50;
    const r = await api.historyList(params);
    rows.value = r.items || [];
    nextCursor.value = r.next_cursor || null;
  } catch (e) {
    message.error(t('history.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  if (!nextCursor.value || loadingMore.value) return;
  loadingMore.value = true;
  try {
    const params = buildQueryParams({ withCursor: true });
    params.limit = 50;
    const r = await api.historyList(params);
    rows.value = rows.value.concat(r.items || []);
    nextCursor.value = r.next_cursor || null;
  } catch (e) {
    message.error(t('history.messages.loadMoreFailed', { msg: e.message }));
  } finally {
    loadingMore.value = false;
  }
}

async function openDetail(callId) {
  if (!callId) return;
  drawerOpen.value = true;
  detail.value = null;
  try {
    detail.value = await api.historyDetail(callId);
  } catch (e) {
    message.error(t('history.messages.detailFailed', { msg: e.message }));
    drawerOpen.value = false;
  }
}

async function summarizeCurrent() {
  if (!detail.value?.call_id) return;
  summarizing.value = true;
  try {
    const updated = await api.historySummarize(detail.value.call_id);
    // Backend returns the updated row. Patch both the drawer and the row in
    // the table list (so summary_status tag reflects the new state without a
    // full reload).
    const next = updated?.row || updated;
    if (next && typeof next === 'object') {
      detail.value = { ...detail.value, ...next };
      const i = rows.value.findIndex((r) => r.call_id === detail.value.call_id);
      if (i >= 0) {
        rows.value[i] = {
          ...rows.value[i],
          summary_status: next.summary_status ?? rows.value[i].summary_status,
          summary: next.summary ?? rows.value[i].summary,
        };
      }
    } else {
      // Fallback: re-fetch detail.
      detail.value = await api.historyDetail(detail.value.call_id);
    }
    message.success(t('history.messages.summaryUpdated'));
  } catch (e) {
    message.error(t('history.messages.summarizeFailed', { msg: e.message }));
  } finally {
    summarizing.value = false;
  }
}

function exportCsv() {
  // Export URL keeps raw enum codes (schema contract with backend / spreadsheets).
  const url = api.historyCsvUrl(buildQueryParams({ withCursor: false }));
  window.open(url, '_blank');
}

function downloadMd() {
  // MD download keeps raw enum codes too.
  if (!detail.value?.call_id) return;
  window.open(api.historyExportMdUrl(detail.value.call_id), '_blank');
}

// -- watchers --------------------------------------------------------------
// Any filter change → debounce + reload. Caller text input gets a debounce
// to avoid one request per keystroke.
let debounceHandle = null;
function debouncedReload(delay = 300) {
  if (debounceHandle) clearTimeout(debounceHandle);
  debounceHandle = setTimeout(() => {
    debounceHandle = null;
    reload();
  }, delay);
}

watch(
  () => filters.caller,
  () => debouncedReload(400),
);
watch(
  () => [filters.outcome, filters.engine, filters.demo, filters.dateRange],
  () => debouncedReload(150),
  { deep: true },
);

onMounted(async () => {
  await ensureDemoOptions();
  await reload();
});
</script>

<style scoped>
.load-more {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--vb-space-lg) 0 var(--vb-space-xs);
}

.transcript {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-sm);
  margin-top: var(--vb-space-xs);
}

.bubble-row {
  display: flex;
  width: 100%;
}

.bubble-row--bot {
  justify-content: flex-start;
}

.bubble-row--user {
  justify-content: flex-end;
}

.bubble {
  max-width: 78%;
  padding: var(--vb-space-sm) var(--vb-space-md);
  border-radius: var(--vb-radius-md);
  font-size: 13px;
  line-height: 1.45;
  color: var(--vb-text);
}

.bubble--bot {
  background: color-mix(in srgb, var(--vb-primary) 12%, transparent);
  border: 1px solid color-mix(in srgb, var(--vb-primary) 28%, transparent);
}

.bubble--user {
  background: var(--vb-surface-alt);
  border: 1px solid var(--vb-border);
}

.bubble-meta {
  display: flex;
  gap: var(--vb-space-sm);
  align-items: center;
  margin-bottom: var(--vb-space-xs);
}

.bubble-text {
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
