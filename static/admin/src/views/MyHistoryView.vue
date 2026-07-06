<template>
  <div class="history-root">
    <div class="filter-row">
      <n-select
        v-model:value="windowKey"
        size="small"
        :options="windowOptions"
        style="width: 150px;"
      />
      <n-popover trigger="hover">
        <template #trigger>
          <n-button quaternary circle size="small" :loading="listLoading" @click="reloadFirstPage">
            <template #icon>
              <n-icon :size="16" :component="RefreshIcon" />
            </template>
          </n-button>
        </template>
        {{ t('myHistory.filter.refreshTooltip') }}
      </n-popover>
      <span class="counter">
        {{ t('myHistory.filter.counter', { filtered: filteredItems.length, total: items.length }) }}
      </span>
    </div>

    <div class="split-area">
      <!-- Left: list -->
      <div class="list-pane">
        <EmptyState
          v-if="!listLoading && filteredItems.length === 0"
          :title="t('myHistory.list.emptyTitle')"
          :description="t('myHistory.list.empty')"
        >
          <template #icon><n-icon :component="HistoryIcon" /></template>
        </EmptyState>
        <div v-else class="list-scroll">
          <div
            v-for="item in filteredItems"
            :key="item.call_id"
            class="row"
            :class="{ 'is-selected': item.call_id === selectedCallId }"
            @click="selectCall(item.call_id)"
          >
            <div class="row-top">
              <span class="caller">
                <n-icon :size="14" :component="CallerIcon" class="caller-icon" />
                {{ item.caller || t('common.unknown') }}
              </span>
              <StatChip :tone="statusTone(item.summary_status)">
                {{ statusLabel(item.summary_status) }}
              </StatChip>
            </div>
            <div class="row-mid" :title="absTime(item.started_at)">
              <n-icon :size="13" :component="ClockIcon" class="meta-icon" />
              <span class="rel">{{ relTime(item.started_at) }}</span>
              <span class="dot-sep">·</span>
              <span class="dur">{{ fmtDuration(item.duration_s) }}</span>
            </div>
            <div v-if="item.intent" class="row-intent">
              {{ firstSentence(item.intent) }}
            </div>
            <div class="row-id">#{{ shortId(item.call_id) }}</div>
          </div>

          <div v-if="nextCursor" class="load-more">
            <n-button size="small" :loading="loadingMore" @click="loadMore">
              {{ t('myHistory.list.loadMore') }}
            </n-button>
          </div>
          <div v-else-if="items.length > 0" class="end-marker">
            <n-text depth="3" style="font-size: 11px;">{{ t('myHistory.list.end') }}</n-text>
          </div>
        </div>
      </div>

      <!-- Right: detail -->
      <div class="detail-pane">
        <EmptyState
          v-if="!selectedCallId"
          :title="t('myHistory.detail.emptyTitle')"
          :description="t('myHistory.detail.empty')"
        >
          <template #icon><n-icon :component="RecordIcon" /></template>
        </EmptyState>
        <div v-else class="detail-content">
          <div v-if="detailLoading" class="detail-skel">
            <n-skeleton text :repeat="6" />
          </div>
          <div v-else-if="!detail" class="detail-skel">
            <n-text depth="3">{{ t('myHistory.detail.notFound') }}</n-text>
          </div>
          <template v-else>
            <div class="detail-header">
              <div class="detail-title">
                <n-icon :size="18" :component="CallerIcon" class="caller-big-icon" />
                <span class="caller-big">{{ detail.caller || t('common.unknown') }}</span>
                <StatChip :tone="statusTone(detail.summary_status)">
                  {{ statusLabel(detail.summary_status) }}
                </StatChip>
              </div>
              <div class="detail-sub">
                <n-icon :size="13" :component="ClockIcon" class="meta-icon" />
                <span :title="absTime(detail.started_at)">{{ absTime(detail.started_at) }}</span>
                <span class="dot-sep">·</span>
                <span>{{ t('myHistory.detail.durationLabel', { value: fmtDuration(detail.duration_s) }) }}</span>
                <span class="dot-sep">·</span>
                <span>{{ t('myHistory.detail.turnsLabel', { n: detail.turn_count || 0 }) }}</span>
              </div>
              <div v-if="detail.summary && detail.summary.model" class="model-line">
                {{ t('myHistory.detail.modelPrefix', { model: detail.summary.model }) }}
              </div>
            </div>

            <div class="detail-grid">
              <!-- Turns -->
              <div class="turns-pane">
                <div class="pane-label">{{ t('myHistory.detail.panes.turns') }}</div>
                <div v-if="!detail.turns || detail.turns.length === 0" class="empty-turns">
                  <n-text depth="3">{{ t('myHistory.detail.turnsEmpty') }}</n-text>
                </div>
                <div v-else class="turns-list">
                  <div
                    v-for="(turn, i) in detail.turns"
                    :key="i"
                    class="bubble"
                    :class="turn.who === 'bot' ? 'bot' : 'user'"
                  >
                    <div class="bubble-meta">
                      <n-icon
                        :size="13"
                        :component="turn.who === 'bot' ? BotIcon : UserIcon"
                        class="who-icon"
                      />
                      <span class="who">{{ turn.who === 'bot' ? t('myHistory.detail.bubbleWho.bot') : t('myHistory.detail.bubbleWho.user') }}</span>
                      <span class="ts">{{ fmtTs(turn.t) }}s</span>
                    </div>
                    <div class="bubble-text">{{ turn.text || t('common.dash') }}</div>
                  </div>
                </div>
              </div>

              <!-- Summary -->
              <div class="summary-pane">
                <div class="pane-label">{{ t('myHistory.detail.panes.summary') }}</div>
                <div v-if="detail.summary_status === 'pending'" class="summary-skel">
                  <n-text depth="3" style="font-size: 12px;">{{ t('myHistory.summary.pendingHint') }}</n-text>
                  <n-skeleton text :repeat="4" style="margin-top: 8px;" />
                </div>
                <div v-else-if="detail.summary_status === 'failed'" class="summary-failed">
                  <n-alert type="error" :show-icon="true" :title="t('myHistory.summary.failedTitle')">
                    {{ detail.summary_error || t('myHistory.summary.failedFallback') }}
                  </n-alert>
                </div>
                <div v-else-if="detail.summary" class="summary-ok">
                  <div class="summary-section">
                    <div class="section-label">{{ t('myHistory.summary.sections.intent') }}</div>
                    <div class="section-body">{{ detail.summary.intent || t('common.dash') }}</div>
                  </div>
                  <div class="summary-section">
                    <div class="section-label">{{ t('myHistory.summary.sections.keyQuestions') }}</div>
                    <ul v-if="(detail.summary.key_questions || []).length" class="section-list">
                      <li v-for="(q, i) in detail.summary.key_questions" :key="i">{{ q }}</li>
                    </ul>
                    <div v-else class="section-body empty">{{ t('common.dash') }}</div>
                  </div>
                  <div class="summary-section">
                    <div class="section-label">{{ t('myHistory.summary.sections.actionItems') }}</div>
                    <ul v-if="(detail.summary.action_items || []).length" class="section-list">
                      <li v-for="(a, i) in detail.summary.action_items" :key="i">{{ a }}</li>
                    </ul>
                    <div v-else class="section-body empty">{{ t('common.dash') }}</div>
                  </div>
                  <div class="summary-section">
                    <div class="section-label">{{ t('myHistory.summary.sections.sentiment') }}</div>
                    <div class="section-body">{{ detail.summary.sentiment || t('myHistory.summary.sentimentNeutral') }}</div>
                  </div>
                </div>
                <div v-else class="summary-skel">
                  <n-text depth="3">{{ t('myHistory.summary.empty') }}</n-text>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import {
  NButton,
  NSelect,
  NText,
  NPopover,
  NSkeleton,
  NAlert,
  NIcon,
  useMessage,
} from 'naive-ui';
import {
  Renew as RefreshIcon,
  RecentlyViewed as HistoryIcon,
  Time as ClockIcon,
  Phone as CallerIcon,
  DocumentBlank as RecordIcon,
  User as UserIcon,
  Bot as BotIcon,
} from '@vicons/carbon';
import { useI18n } from 'vue-i18n';
import { api } from '../api.js';
import EmptyState from '../components/ui/EmptyState.vue';
import StatChip from '../components/ui/StatChip.vue';

const message = useMessage();
const { t } = useI18n();

const items = ref([]);
const nextCursor = ref(null);
const listLoading = ref(false);
const loadingMore = ref(false);

const windowKey = ref('all');
// Compute options reactively so labels track the active locale.
const windowOptions = computed(() => [
  { label: t('myHistory.window.all'), value: 'all' },
  { label: t('myHistory.window.today'), value: 'today' },
  { label: t('myHistory.window.last7d'), value: '7d' },
  { label: t('myHistory.window.last30d'), value: '30d' },
]);

const selectedCallId = ref(null);
const detail = ref(null);
const detailLoading = ref(false);

const now = ref(Date.now());
let nowTimer = null;
let pollTimer = null;

const filteredItems = computed(() => {
  const arr = items.value;
  const cutoff = windowCutoffSec();
  if (cutoff == null) return arr;
  return arr.filter((it) => (Number(it.started_at) || 0) >= cutoff);
});

function windowCutoffSec() {
  const nowSec = Math.floor(Date.now() / 1000);
  if (windowKey.value === 'today') {
    const d = new Date();
    d.setHours(0, 0, 0, 0);
    return Math.floor(d.getTime() / 1000);
  }
  if (windowKey.value === '7d') return nowSec - 7 * 86400;
  if (windowKey.value === '30d') return nowSec - 30 * 86400;
  return null;
}

async function loadFirstPage() {
  listLoading.value = true;
  try {
    const data = await api.fetchHistory({ limit: 50 });
    items.value = data.items || [];
    nextCursor.value = data.next_cursor || null;
  } catch (e) {
    message.error(t('myHistory.errors.load', { msg: e.message }));
  } finally {
    listLoading.value = false;
  }
}

async function reloadFirstPage() {
  await loadFirstPage();
}

async function loadMore() {
  if (!nextCursor.value || loadingMore.value) return;
  loadingMore.value = true;
  try {
    const data = await api.fetchHistory({
      cursor: nextCursor.value,
      limit: 50,
    });
    const seen = new Set(items.value.map((it) => it.call_id));
    for (const it of data.items || []) {
      if (!seen.has(it.call_id)) items.value.push(it);
    }
    nextCursor.value = data.next_cursor || null;
  } catch (e) {
    message.error(t('myHistory.errors.loadMore', { msg: e.message }));
  } finally {
    loadingMore.value = false;
  }
}

async function refreshIfVisible() {
  if (typeof document !== 'undefined' && document.visibilityState !== 'visible') return;
  // Refetch first page only — keep cursor / appended pages stable.
  try {
    const data = await api.fetchHistory({ limit: 50 });
    const incoming = data.items || [];
    const incomingIds = new Set(incoming.map((it) => it.call_id));
    // Replace head with incoming, keep tail rows that aren't in head.
    const tail = items.value.filter((it) => !incomingIds.has(it.call_id));
    items.value = [...incoming, ...tail];
    if (data.next_cursor && !nextCursor.value) {
      nextCursor.value = data.next_cursor;
    }
  } catch {
    /* swallow polling errors */
  }
}

function selectCall(callId) {
  if (selectedCallId.value === callId) return;
  selectedCallId.value = callId;
}

watch(selectedCallId, async (id) => {
  detail.value = null;
  if (!id) return;
  detailLoading.value = true;
  try {
    detail.value = await api.fetchHistoryDetail(id);
  } catch (e) {
    message.error(t('myHistory.errors.detail', { msg: e.message }));
  } finally {
    detailLoading.value = false;
  }
});

onMounted(() => {
  loadFirstPage();
  pollTimer = setInterval(refreshIfVisible, 15000);
  nowTimer = setInterval(() => {
    now.value = Date.now();
  }, 30000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (nowTimer) clearInterval(nowTimer);
});

function statusTone(s) {
  if (s === 'ok') return 'success';
  if (s === 'failed') return 'error';
  if (s === 'pending') return 'warning';
  return 'default';
}
function statusLabel(s) {
  if (s === 'ok') return t('myHistory.summaryStatus.ok');
  if (s === 'failed') return t('myHistory.summaryStatus.failed');
  if (s === 'pending') return t('myHistory.summaryStatus.pending');
  return s || t('common.dash');
}

function relTime(startedSec) {
  const ts = Number(startedSec);
  if (!Number.isFinite(ts)) return '';
  const sec = Math.max(0, Math.floor(now.value / 1000 - ts));
  if (sec < 60) return t('myHistory.rel.seconds', { n: sec });
  const m = Math.floor(sec / 60);
  if (m < 60) return t('myHistory.rel.minutes', { n: m });
  const h = Math.floor(m / 60);
  if (h < 24) return t('myHistory.rel.hours', { n: h });
  const d = Math.floor(h / 24);
  return t('myHistory.rel.days', { n: d });
}
function absTime(startedSec) {
  const ts = Number(startedSec);
  if (!Number.isFinite(ts)) return '';
  // Browser-native formatting follows the Naive UI date locale via
  // <html lang>; raw value still passes through for tooltips.
  return new Date(ts * 1000).toLocaleString();
}
function fmtDuration(secs) {
  const s = Math.max(0, Math.floor(Number(secs) || 0));
  const m = Math.floor(s / 60);
  const r = s % 60;
  return t('myHistory.duration', { m, s: r });
}
function fmtTs(ts) {
  return typeof ts === 'number' ? ts.toFixed(2) : '–';
}
function shortId(id) {
  if (!id) return '';
  return id.length > 10 ? `${id.slice(0, 10)}…` : id;
}
function firstSentence(s) {
  if (!s) return '';
  const m = String(s).match(/^[^。.!?！？\n]+[。.!?！？]?/);
  const out = (m ? m[0] : String(s)).trim();
  return out.length > 80 ? `${out.slice(0, 80)}…` : out;
}
</script>

<style scoped>
.history-root {
  max-width: 1280px;
  margin: 0 auto;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-md);
}

.filter-row {
  display: flex;
  align-items: center;
  gap: var(--vb-space-sm);
}

.counter {
  margin-left: auto;
  font-size: 12px;
  color: var(--vb-text-tertiary);
  font-variant-numeric: tabular-nums;
}

.split-area {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 360px 1fr;
  gap: var(--vb-space-lg);
}

@media (max-width: 1023px) {
  .split-area {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
  .list-pane {
    max-height: 40vh;
    overflow: hidden;
  }
}

.list-pane {
  min-height: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  background: var(--vb-surface);
  box-shadow: var(--vb-shadow-card);
}

.list-scroll {
  flex: 1;
  overflow-y: auto;
  padding: var(--vb-space-sm);
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-sm);
}

.row {
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  padding: 10px 12px;
  cursor: pointer;
  background: var(--vb-surface);
  transition: background-color 0.15s, border-color 0.15s;
}
.row:hover {
  background: var(--vb-surface-alt);
  border-color: var(--vb-border-strong);
}
.row.is-selected {
  background: var(--vb-surface-alt);
  border-color: var(--vb-primary);
  box-shadow: inset 3px 0 0 var(--vb-primary);
}

.row-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--vb-space-sm);
  margin-bottom: var(--vb-space-xs);
}

.caller {
  display: inline-flex;
  align-items: center;
  gap: var(--vb-space-xs);
  font-weight: 600;
  font-size: 13px;
  color: var(--vb-text);
  word-break: break-all;
}
.caller-icon {
  color: var(--vb-text-tertiary);
  flex: none;
}

.row-mid {
  font-size: 12px;
  color: var(--vb-text-tertiary);
  display: flex;
  align-items: center;
  gap: var(--vb-space-xs);
}
.meta-icon {
  color: var(--vb-text-tertiary);
  flex: none;
}

.dot-sep {
  opacity: 0.5;
}

.row-intent {
  font-size: 12px;
  margin-top: var(--vb-space-xs);
  color: var(--vb-text-secondary);
  line-height: 1.4;
}

.row-id {
  font-size: 10px;
  color: var(--vb-text-tertiary);
  font-family: var(--vb-font-mono);
  margin-top: var(--vb-space-xs);
}

.load-more {
  display: flex;
  justify-content: center;
  padding: var(--vb-space-sm) 0;
}
.end-marker {
  text-align: center;
  padding: var(--vb-space-sm) 0;
}

.detail-pane {
  min-height: 0;
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  background: var(--vb-surface);
  box-shadow: var(--vb-shadow-card);
  overflow: hidden;
  display: flex;
  flex-direction: column;
}

.detail-content {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.detail-skel {
  padding: var(--vb-space-xl);
}

.detail-header {
  padding: var(--vb-space-md) var(--vb-space-lg);
  border-bottom: 1px solid var(--vb-border);
  background: var(--vb-surface-alt);
}

.detail-title {
  display: flex;
  align-items: center;
  gap: var(--vb-space-sm);
}

.caller-big-icon {
  color: var(--vb-text-secondary);
  flex: none;
}

.caller-big {
  font-weight: 700;
  font-size: 16px;
  color: var(--vb-text);
}

.detail-sub {
  margin-top: var(--vb-space-xs);
  font-size: 12px;
  color: var(--vb-text-tertiary);
  display: flex;
  align-items: center;
  gap: var(--vb-space-xs);
}

.model-line {
  margin-top: var(--vb-space-xs);
  font-size: 11px;
  color: var(--vb-text-tertiary);
  font-family: var(--vb-font-mono);
}

.detail-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  overflow: hidden;
}

@media (max-width: 1023px) {
  .detail-grid {
    grid-template-columns: 1fr;
    grid-template-rows: 1fr 1fr;
  }
}

.turns-pane,
.summary-pane {
  padding: var(--vb-space-md) var(--vb-space-lg);
  overflow-y: auto;
  min-height: 0;
}

.turns-pane {
  border-right: 1px solid var(--vb-border);
}

.pane-label {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--vb-text-tertiary);
  margin-bottom: var(--vb-space-sm);
}

.turns-list {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-sm);
}

.bubble {
  border-radius: var(--vb-radius-md);
  padding: var(--vb-space-sm) 10px;
  max-width: 90%;
  border: 1px solid var(--vb-border);
  background: var(--vb-surface-alt);
}
.bubble.user {
  align-self: flex-start;
}
.bubble.bot {
  align-self: flex-end;
  border-color: var(--vb-primary);
  background: var(--vb-surface);
}
.bubble-meta {
  display: flex;
  align-items: center;
  gap: var(--vb-space-xs);
  font-size: 10px;
  color: var(--vb-text-tertiary);
  margin-bottom: 2px;
}
.who-icon {
  flex: none;
}
.who {
  font-weight: 700;
  letter-spacing: 0.5px;
}
.ts {
  font-variant-numeric: tabular-nums;
}
.bubble-text {
  font-size: 13px;
  line-height: 1.5;
  color: var(--vb-text);
  white-space: pre-wrap;
  word-break: break-word;
}

.summary-section {
  margin-bottom: var(--vb-space-md);
}
.section-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
  color: var(--vb-text-tertiary);
  margin-bottom: var(--vb-space-xs);
  text-transform: uppercase;
}
.section-body {
  font-size: 13px;
  line-height: 1.5;
  color: var(--vb-text);
  word-break: break-word;
}
.section-body.empty {
  color: var(--vb-text-tertiary);
}
.section-list {
  margin: 0;
  padding-left: 20px;
  font-size: 13px;
  line-height: 1.5;
  color: var(--vb-text);
}

.summary-skel,
.summary-failed {
  margin-top: var(--vb-space-xs);
}

.empty-turns {
  padding: var(--vb-space-lg) 0;
  text-align: center;
}
</style>
