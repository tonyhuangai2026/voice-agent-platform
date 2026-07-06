<template>
  <div class="monitor-root">
    <div class="header-row">
      <StatChip :tone="status === 'streaming' ? 'success' : 'default'">
        {{ statusText }}
      </StatChip>
      <n-popover trigger="hover">
        <template #trigger>
          <n-button quaternary circle size="small" :loading="loading" @click="refreshCalls">
            <template #icon>
              <n-icon :size="16" :component="RefreshIcon" />
            </template>
          </n-button>
        </template>
        {{ t('monitor.refreshTooltip') }}
      </n-popover>
    </div>

    <div class="split-area">
      <!-- Left: call list -->
      <div class="call-pane">
        <EmptyState
          v-if="sortedCalls.length === 0"
          :title="t('monitor.empty.noActive')"
          :description="t('monitor.empty.noActiveHint')"
        >
          <template #icon><n-icon :component="PhoneIcon" /></template>
        </EmptyState>

        <div v-else class="call-list">
          <div
            v-for="c in sortedCalls"
            :key="c.call_id"
            class="call-item"
            :class="{
              'is-selected': c.call_id === selectedCallId,
              'is-live': isLive(c.call_id),
            }"
            @click="selectedCallId = c.call_id"
          >
            <div class="row1">
              <span class="live-dot" />
              <span class="live-label">{{ t('monitor.callItem.live') }}</span>
              <span class="caller">{{ c.caller || t('common.unknown') }}</span>
            </div>
            <div class="row2">
              <n-icon :size="13" :component="ClockIcon" class="meta-icon" />
              <span class="rel">{{ fmtRel(c.started) }}</span>
              <span class="dot-sep">·</span>
              <span class="dur">{{ fmtDuration(c.started) }}</span>
            </div>
            <div class="row3">#{{ shortId(c.call_id) }}</div>
          </div>
        </div>
      </div>

      <!-- Right: event stream -->
      <div class="event-pane">
        <div v-if="!selectedCallId" class="event-empty-wrap">
          <EmptyState
            :title="t('monitor.empty.noSelection')"
            :description="t('monitor.empty.noSelectionHint')"
          >
            <template #icon><n-icon :component="StreamIcon" /></template>
          </EmptyState>
        </div>

        <div v-else class="event-card">
          <div ref="logRef" class="evt-list">
            <div
              v-for="(e, i) in events"
              :key="i"
              class="evt-row"
              :class="evtClass(e.type)"
            >
              <span class="ts">{{ fmtTs(e.t) }}s</span>
              <span class="tag">{{ e.type }}</span>
              <span class="evt-body" :title="fmtBody(e)">{{ fmtBody(e) }}</span>
            </div>
            <div v-if="events.length === 0" class="empty">
              <n-icon :size="20" :component="StreamIcon" class="empty-icon" />
              <n-text depth="3">{{ t('monitor.empty.noEvents') }}</n-text>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import {
  NButton,
  NPopover,
  NText,
  NIcon,
  useMessage,
} from 'naive-ui';
import {
  Renew as RefreshIcon,
  Time as ClockIcon,
  Phone as PhoneIcon,
  DataViewAlt as StreamIcon,
} from '@vicons/carbon';
import { useI18n } from 'vue-i18n';
import { api } from '../api.js';
import { openMonitorWs } from '../ws.js';
import { useEventLog } from '../composables/useEventLog.js';
import EmptyState from '../components/ui/EmptyState.vue';
import StatChip from '../components/ui/StatChip.vue';

const message = useMessage();
const { t } = useI18n();

const calls = ref([]);
const selectedCallId = ref(null);
// Merged display rows come from the shared composable (was the inline pushEvent
// merge logic, 240-308). `events` keeps its name so the template is unchanged.
const { rows: events, push: pushMerged, reset: resetEvents } = useEventLog();
const loading = ref(false);
const status = ref('idle'); // idle | streaming | ended
const logRef = ref(null);
const now = ref(Date.now());

let ws = null;
let pollTimer = null;
let tickTimer = null;

const sortedCalls = computed(() =>
  [...calls.value].sort((a, b) => (b.started || 0) - (a.started || 0)),
);

const liveSet = computed(() => new Set(calls.value.map((c) => c.call_id)));
function isLive(callId) {
  return liveSet.value.has(callId);
}

const statusText = computed(() => {
  if (status.value === 'streaming') return t('monitor.status.online');
  if (status.value === 'ended') return t('monitor.status.ended');
  if (sortedCalls.value.length === 0) return t('monitor.status.noCalls');
  return t('monitor.status.idle');
});

async function refreshCalls() {
  loading.value = true;
  try {
    const data = await api.calls();
    calls.value = data.calls || [];
  } catch (e) {
    message.error(t('monitor.errors.refresh', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  refreshCalls();
  pollTimer = setInterval(refreshCalls, 2000);
  tickTimer = setInterval(() => {
    now.value = Date.now();
  }, 1000);
});

onBeforeUnmount(() => {
  if (pollTimer) clearInterval(pollTimer);
  if (tickTimer) clearInterval(tickTimer);
  closeWs();
});

watch(selectedCallId, (newId) => {
  closeWs();
  resetEvents();
  if (!newId) {
    status.value = 'idle';
    return;
  }
  openWs(newId);
});

// Auto-select newest call when list arrives & nothing chosen.
watch(
  sortedCalls,
  (latest) => {
    if (!selectedCallId.value && latest.length) {
      selectedCallId.value = latest[0].call_id;
    }
  },
  { immediate: true },
);

// If selected call disappears (hung up), switch to newest remaining call.
watch(sortedCalls, (latest) => {
  if (!selectedCallId.value) return;
  const stillThere = latest.some((c) => c.call_id === selectedCallId.value);
  if (!stillThere && status.value === 'streaming') {
    message.info(t('monitor.errors.callEnded', { id: selectedCallId.value.slice(0, 8) }));
    const nextCall = latest[0]; // sortedCalls[0] = newest
    selectedCallId.value = nextCall ? nextCall.call_id : null;
  }
});

async function openWs(callId) {
  status.value = 'streaming';
  ws = await openMonitorWs(callId);
  ws.onmessage = (e) => {
    if (typeof e.data !== 'string') return;
    try {
      const evt = JSON.parse(e.data);
      // Merge via the shared composable, then apply Monitor's display-only
      // scroll-to-bottom + 1000-cap (kept here since mergeEvent is side-effect-free).
      pushMerged(evt);
      trimAndScroll();
    } catch {
      /* ignore */
    }
  };
  ws.onclose = () => {
    status.value = 'ended';
  };
  ws.onerror = () => {
    message.error(t('monitor.errors.ws'));
    status.value = 'ended';
  };
}

function closeWs() {
  if (ws) {
    try {
      if (ws.readyState <= 1) ws.close();
    } catch {
      /* ignore */
    }
    ws = null;
  }
}

function scrollToBottom() {
  nextTick(() => {
    const el = logRef.value;
    if (el) el.scrollTop = el.scrollHeight;
  });
}

// Merge logic now lives in useEventLog (mergeEvent). Monitor keeps only the
// display-only side effects here: cap the buffer at 1000 + scroll to bottom,
// called after each pushMerged() (the composable's mergeEvent is pure).
function trimAndScroll() {
  const arr = events.value;
  if (arr.length > 1000) arr.splice(0, arr.length - 1000);
  scrollToBottom();
}

function evtClass(type) {
  if (!type) return '';
  if (type.startsWith('asr')) return 'evt-asr';
  if (type.startsWith('llm')) return 'evt-llm';
  if (type.startsWith('tts')) return 'evt-tts';
  if (type.includes('speaking')) return 'evt-vad';
  return '';
}

function fmtTs(t) {
  return typeof t === 'number' ? t.toFixed(2) : '–';
}

function fmtBody(e) {
  if (e.text != null && e.text !== '') {
    const s = String(e.text);
    return s.length > 200 ? s.slice(0, 200) + '…' : s;
  }
  if (e.value === true) return t('monitor.eventBody.start');
  if (e.value === false) return t('monitor.eventBody.end');
  if (e.value != null) return String(e.value);
  return t('common.dash');
}

function fmtDuration(startedSec) {
  if (typeof startedSec !== 'number') return '00:00';
  const sec = Math.max(0, Math.floor(now.value / 1000 - startedSec));
  const m = Math.floor(sec / 60).toString().padStart(2, '0');
  const s = (sec % 60).toString().padStart(2, '0');
  return `${m}:${s}`;
}

function fmtRel(startedSec) {
  if (typeof startedSec !== 'number') return '';
  const sec = Math.max(0, Math.floor(now.value / 1000 - startedSec));
  if (sec < 60) return t('monitor.rel.seconds', { n: sec });
  const m = Math.floor(sec / 60);
  if (m < 60) return t('monitor.rel.minutes', { n: m });
  const h = Math.floor(m / 60);
  return t('monitor.rel.hours', { n: h });
}

function shortId(id) {
  if (!id) return '';
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}
</script>

<style scoped>
.monitor-root {
  max-width: 1280px;
  margin: 0 auto;
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-md);
}

.header-row {
  display: flex;
  align-items: center;
  gap: var(--vb-space-sm);
}

.split-area {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: var(--vb-space-lg);
}

@media (max-width: 1023px) {
  .split-area {
    grid-template-columns: 1fr;
    grid-template-rows: auto 1fr;
  }
  .call-pane {
    max-height: 30vh;
    overflow-y: auto;
  }
}

.call-pane {
  min-height: 0;
  overflow-y: auto;
}

.call-list {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-sm);
}

.call-item {
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  padding: 10px 12px;
  cursor: pointer;
  transition: background-color 0.15s, border-color 0.15s;
  background: var(--vb-surface);
  box-shadow: var(--vb-shadow-card);
}

.call-item:hover {
  background: var(--vb-surface-alt);
  border-color: var(--vb-border-strong);
}

.call-item.is-selected {
  background: var(--vb-surface-alt);
  border-color: var(--vb-primary);
  box-shadow: inset 3px 0 0 var(--vb-primary);
}

.call-item.is-live {
  border-color: var(--vb-success);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--vb-success) 22%, transparent);
}

/* When both selected and live: keep the live (green) accent ring + selected fill. */
.call-item.is-selected.is-live {
  background: var(--vb-surface-alt);
  border-color: var(--vb-success);
}

.row1 {
  display: flex;
  align-items: center;
  gap: var(--vb-space-xs);
  margin-bottom: var(--vb-space-xs);
}

.live-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--vb-success);
  display: inline-block;
  animation: live-pulse 1.6s ease-in-out infinite;
}

.live-label {
  font-size: 11px;
  font-weight: 700;
  color: var(--vb-success);
  letter-spacing: 0.5px;
}

.caller {
  font-weight: 600;
  font-size: 14px;
  margin-left: var(--vb-space-xs);
  color: var(--vb-text);
  word-break: break-all;
}

.row2 {
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

.row3 {
  font-size: 11px;
  color: var(--vb-text-tertiary);
  font-family: var(--vb-font-mono);
  margin-top: 2px;
}

@keyframes live-pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

.event-pane {
  min-height: 0;
}

.event-empty-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  background: var(--vb-surface);
}

.event-card {
  height: 100%;
  border: 1px solid var(--vb-border);
  border-radius: var(--vb-radius-md);
  background: var(--vb-surface);
  box-shadow: var(--vb-shadow-card);
  overflow: hidden;
}

.evt-list {
  height: 100%;
  max-height: calc(100vh - 200px);
  overflow-y: auto;
  padding: var(--vb-space-md) var(--vb-space-lg);
  font-family: var(--vb-font-mono);
  font-size: 12px;
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-xs);
}

.evt-row {
  display: grid;
  grid-template-columns: 56px 140px 1fr;
  gap: var(--vb-space-sm);
  align-items: baseline;
  padding: 2px 0;
}

.ts {
  color: var(--vb-text-tertiary);
}

.tag {
  font-weight: 600;
  color: var(--vb-text-secondary);
}

.evt-body {
  /* One line per event so the stream reads like a compact log. Long ASR/LLM
     text (fmtBody caps at 200 chars) would otherwise wrap to many lines and
     look like big gaps between event timestamps. Full text on hover via the
     title attribute. */
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  min-width: 0;
  color: var(--vb-text);
}

.evt-asr .tag { color: var(--vb-info); }
.evt-llm .tag { color: var(--vb-accent); }
.evt-tts .tag { color: var(--vb-success); }
.evt-vad .tag { color: var(--vb-text-tertiary); }

.empty {
  text-align: center;
  padding: var(--vb-space-xxl) 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: var(--vb-space-sm);
}

.empty-icon {
  color: var(--vb-text-tertiary);
  opacity: 0.5;
}
</style>
