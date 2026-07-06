<template>
  <div class="debug-root">
    <div class="debug-head">
      <n-text depth="3" style="font-size: 12px;">
        {{ t('debug.intro') }}
      </n-text>
      <div class="raw-toggle">
        <n-text depth="3" style="font-size: 12px;">{{ t('debug.rawMode') }}</n-text>
        <n-switch v-model:value="rawMode" size="small" />
      </div>
    </div>
    <n-divider />
    <div class="evt-list">
      <!-- merged view (default): rows from useEventLog -->
      <template v-if="!rawMode">
        <div
          v-for="(e, i) in mergedRows"
          :key="i"
          class="evt-row"
          :class="evtClass(e.type)"
        >
          <span class="ts">{{ fmtTs(e.t) }}s</span>
          <span class="tag">{{ e.type }}</span>
          <span class="evt-body" :title="fmtBody(e)">{{ fmtBody(e) }}</span>
        </div>
        <div v-if="mergedRows.length === 0" class="empty">
          <n-text depth="3">{{ t('debug.empty') }}</n-text>
        </div>
      </template>

      <!-- raw view: the unmodified events prop, one row per event -->
      <template v-else>
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
          <n-text depth="3">{{ t('debug.empty') }}</n-text>
        </div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue';
import { NText, NDivider, NSwitch } from 'naive-ui';
import { useI18n } from 'vue-i18n';
import { useEventLog, planLogSync, tailKey } from '../composables/useEventLog.js';

const { t } = useI18n();

const props = defineProps({
  events: { type: Array, required: true },
});

// --- raw/merged toggle, persisted ------------------------------------------
const RAW_KEY = 'vb.debugRaw';
const rawMode = ref(readRaw());

function readRaw() {
  try {
    return localStorage.getItem(RAW_KEY) === '1';
  } catch {
    return false;
  }
}

watch(rawMode, (v) => {
  try {
    localStorage.setItem(RAW_KEY, v ? '1' : '0');
  } catch {
    /* ignore */
  }
});

// --- merged display rows (shared merge core) -------------------------------
const { rows: mergedRows, push, loadAll } = useEventLog();

// Incremental merge-sync cursor. `processed` = how many raw events we've merged
// by index; `lastTail` = newest event's timestamp. session.appendEvent caps the
// raw `events` at 1000 by trimming the FRONT and pushing the back, so once a
// long call plateaus at the cap the array LENGTH stops changing even though new
// events keep arriving — watching length alone would go deaf and the merged
// view would freeze. We watch length + tail-timestamp and delegate the
// append-vs-rebuild decision to the pure, unit-tested planLogSync().
let processed = 0;
let lastTail = '';

watch(
  // Signal that changes on BOTH append (length grows) AND cap-churn (length
  // steady, newest `t` advances after a front-trim).
  () => props.events.length + '|' + tailKey(props.events),
  () => {
    const arr = props.events;
    const plan = planLogSync(arr, { processed, lastTail });
    if (plan.action === 'rebuild') {
      loadAll(arr); // shrink / reset / cap-churn → rebuild from the full array
    } else if (plan.action === 'append') {
      // pure growth → push only the new tail (keeps in-flight asr/llm roll-up)
      for (let i = plan.from; i < arr.length; i++) push(arr[i]);
    } else {
      return; // noop — nothing meaningful changed
    }
    processed = arr.length;
    lastTail = tailKey(arr);
  },
  { immediate: true },
);

function evtClass(type) {
  if (!type) return '';
  if (type.startsWith('asr')) return 'evt-asr';
  if (type.startsWith('llm')) return 'evt-llm';
  if (type.startsWith('tts')) return 'evt-tts';
  if (type.includes('speaking')) return 'evt-vad';
  return '';
}

function fmtTs(ts) {
  if (typeof ts !== 'number') return '–';
  return ts.toFixed(2);
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
</script>

<style scoped>
.debug-root {
  font-family: var(--vb-font-mono);
}

.debug-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}

.raw-toggle {
  display: flex;
  align-items: center;
  gap: 6px;
  flex: none;
}

.evt-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 12px;
}

.evt-row {
  display: grid;
  grid-template-columns: 48px 130px 1fr;
  gap: 8px;
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
     text (fmtBody caps at 200 chars) would otherwise wrap to 4-6 lines in this
     narrow column and look like big gaps between rows. Full text on hover via
     the title attribute. */
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
  padding: 24px 0;
  text-align: center;
}
</style>
