<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ t('dashboard.title') }}</template>
      <template #subtitle>
        {{ t('dashboard.subtitle') }}
        <n-text v-if="lastUpdated" depth="3" style="font-size: 12px; margin-left: 8px;">
          {{ t('dashboard.updatedAt', { time: lastUpdatedDisplay }) }}
        </n-text>
      </template>
      <template #extra>
        <n-space :size="8" align="center">
          <n-tag
            :type="failed ? 'error' : 'success'"
            size="small"
            :bordered="false"
          >
            {{ failed ? t('dashboard.statusFailed') : t('dashboard.statusOnline') }}
          </n-tag>
          <n-button
            size="small"
            :loading="loading && !!metrics"
            :disabled="loading"
            @click="refresh"
          >
            {{ t('dashboard.refresh') }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-alert type="info" style="margin-bottom: 16px;" :show-icon="false">
      <template #header>{{ t('dashboard.notice.header') }}</template>
      <span style="font-size: 12px;" v-html="t('dashboard.notice.body')" />
    </n-alert>

    <!-- First-load skeleton -->
    <template v-if="!metrics && loading">
      <n-grid :cols="3" :x-gap="16" :y-gap="16" responsive="screen" :item-responsive="true">
        <n-grid-item v-for="i in 6" :key="i" :span="'1 s:1 m:1 l:1'">
          <n-card :bordered="true">
            <n-skeleton text :repeat="1" style="width: 60%;" />
            <n-skeleton text :repeat="1" style="width: 40%; margin-top: 12px; height: 28px;" />
          </n-card>
        </n-grid-item>
      </n-grid>
      <n-card :bordered="true" style="margin-top: 16px;">
        <n-skeleton text :repeat="3" />
      </n-card>
    </template>

    <!-- Loaded view -->
    <template v-else-if="metrics">
      <!-- Section: key metrics -->
      <div class="section-title">{{ t('dashboard.sections.metricsTitle') }}</div>
      <!-- 6 stat cards in responsive grid (3 cols on wide, collapses on small) -->
      <n-grid
        :x-gap="16"
        :y-gap="16"
        responsive="screen"
        cols="1 s:2 m:2 l:3 xl:3 2xl:3"
      >
        <n-grid-item>
          <MetricCard :value="metrics.active_calls ?? 0" :label="t('dashboard.cards.activeCalls')">
            <template #icon><n-icon :component="UserActivity" /></template>
          </MetricCard>
        </n-grid-item>

        <n-grid-item>
          <MetricCard :value="todayTotal" :label="t('dashboard.cards.todayCalls')">
            <template #icon><n-icon :component="Calendar" /></template>
          </MetricCard>
        </n-grid-item>

        <n-grid-item>
          <MetricCard
            :value="`${avgDurationDisplay}${t('dashboard.cards.avgDurationSuffix')}`"
            :label="t('dashboard.cards.avgDuration')"
          >
            <template #icon><n-icon :component="Timer" /></template>
          </MetricCard>
        </n-grid-item>

        <n-grid-item>
          <MetricCard
            :value="`${transferRateDisplay}${t('dashboard.cards.transferRateSuffix')}`"
            :label="t('dashboard.cards.transferRate')"
          >
            <template #icon><n-icon :component="PhoneOutgoing" /></template>
          </MetricCard>
        </n-grid-item>

        <n-grid-item>
          <MetricCard
            :value="topDemo.key === '—' ? '—' : `${topDemo.key} (${topDemo.count})`"
            :label="t('dashboard.cards.topDemo')"
          >
            <template #icon><n-icon :component="TrophyFilled" /></template>
          </MetricCard>
        </n-grid-item>

        <n-grid-item>
          <MetricCard
            :value="metrics.peak_concurrent_24h ?? 0"
            :label="t('dashboard.cards.peakConcurrent')"
          >
            <template #icon><n-icon :component="PhoneVoice" /></template>
          </MetricCard>
        </n-grid-item>
      </n-grid>

      <!-- Section: distributions -->
      <div class="section-title">{{ t('dashboard.sections.distributionsTitle') }}</div>
      <n-grid
        :x-gap="16"
        :y-gap="16"
        responsive="screen"
        cols="1 m:2"
      >
        <!-- Outcome distribution — donut + legend -->
        <n-grid-item>
          <n-card :title="t('dashboard.sections.outcomeTitle')" :bordered="true">
            <template #header-extra>
              <n-text depth="3" style="font-size: 12px;">
                {{ t('dashboard.sections.total', { n: outcomeTotal }) }}
              </n-text>
            </template>
            <template v-if="outcomeTotal === 0">
              <n-text depth="3">{{ t('dashboard.sections.empty') }}</n-text>
            </template>
            <div v-else class="dist-row">
              <Donut
                :segments="outcomeSegments"
                :size="156"
                :thickness="22"
                :center-value="outcomeTotal"
                :center-label="t('dashboard.sections.totalLabel')"
              />
              <div class="legend">
                <div v-for="seg in outcomeSegments" :key="seg.key" class="legend-item">
                  <span class="legend-dot" :style="{ background: seg.color }" />
                  <span class="legend-label">{{ seg.label }}</span>
                  <span class="legend-count">{{ seg.count }}</span>
                  <n-text depth="3" style="font-size: 11px; margin-left: 4px;">
                    ({{ seg.pct.toFixed(1) }}%)
                  </n-text>
                </div>
              </div>
            </div>
          </n-card>
        </n-grid-item>

        <!-- Engine distribution — horizontal bar list -->
        <n-grid-item>
          <n-card :title="t('dashboard.sections.engineTitle')" :bordered="true">
            <template #header-extra>
              <n-text depth="3" style="font-size: 12px;">
                {{ t('dashboard.sections.total', { n: engineTotal }) }}
              </n-text>
            </template>
            <template v-if="engineTotal === 0">
              <n-text depth="3">{{ t('dashboard.sections.empty') }}</n-text>
            </template>
            <BarList v-else :items="engineSegments" />
          </n-card>
        </n-grid-item>

        <!-- Demo distribution — horizontal bar list -->
        <n-grid-item :span="'1 m:2'">
          <n-card :title="t('dashboard.sections.demoTitle')" :bordered="true">
            <template #header-extra>
              <n-text depth="3" style="font-size: 12px;">
                {{ t('dashboard.sections.total', { n: demoTotal }) }}
              </n-text>
            </template>
            <template v-if="demoTotal === 0">
              <n-text depth="3">{{ t('dashboard.sections.empty') }}</n-text>
            </template>
            <BarList v-else :items="demoSegments" />
          </n-card>
        </n-grid-item>
      </n-grid>
    </template>

    <!-- Initial fetch failed before any payload arrived -->
    <template v-else>
      <n-card :bordered="true">
        <n-empty :description="t('dashboard.emptyState')" />
      </n-card>
    </template>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  NPageHeader,
  NAlert,
  NCard,
  NGrid,
  NGridItem,
  NIcon,
  NSkeleton,
  NSpace,
  NTag,
  NText,
  NButton,
  NEmpty,
  useMessage,
} from 'naive-ui';
import {
  PhoneVoice,
  Calendar,
  Timer,
  PhoneOutgoing,
  TrophyFilled,
  UserActivity,
} from '@vicons/carbon';
import { api } from '../api.js';
import { localOutcome } from '../i18n/enums.js';
import MetricCard from '../components/ui/MetricCard.vue';
import Donut from '../components/charts/Donut.vue';
import BarList from '../components/charts/BarList.vue';

const POLL_MS = 7000;

const { t } = useI18n();
const message = useMessage();
const metrics = ref(null);
const loading = ref(false);
const failed = ref(false);
const lastUpdated = ref(null); // epoch ms of latest successful response

let timer = null;

// --- derived display values --------------------------------------------------

const todayTotal = computed(() => metrics.value?.today?.total ?? 0);

const avgDurationDisplay = computed(() => {
  const v = metrics.value?.today?.avg_duration_s;
  if (v === null || v === undefined) return '0';
  // Backend returns seconds (float). Show one decimal when < 100s, else integer.
  const num = Number(v);
  if (!Number.isFinite(num)) return '0';
  return num < 100 ? num.toFixed(1) : Math.round(num).toString();
});

const transferRateDisplay = computed(() => {
  const r = metrics.value?.transfer_rate_24h;
  if (r === null || r === undefined) return '0.0';
  const num = Number(r);
  if (!Number.isFinite(num)) return '0.0';
  return (num * 100).toFixed(1);
});

const topDemo = computed(() => {
  const dist = metrics.value?.demo_distribution_24h || {};
  let bestKey = '—';
  let bestCount = 0;
  for (const [k, v] of Object.entries(dist)) {
    const n = Number(v) || 0;
    if (n > bestCount) {
      bestCount = n;
      bestKey = k;
    }
  }
  return { key: bestKey, count: bestCount };
});

// Stable color palette per known outcome / engine. Colors are var(--vb-*)
// references (defined in styles/tokens.css with html.dark overrides) so the
// SVG charts and legends stay dark-aware — no hardcoded hex.
const OUTCOME_ORDER = [
  'user_requested',
  'task_completed',
  'transferred',
  'timeout',
  'error',
  'unknown',
];
const OUTCOME_COLORS = {
  user_requested: 'var(--vb-info)',
  task_completed: 'var(--vb-success)',
  transferred: 'var(--vb-accent)',
  timeout: 'var(--vb-text-tertiary)',
  error: 'var(--vb-error)',
  unknown: 'var(--vb-border-strong)',
};

const ENGINE_COLORS = [
  'var(--vb-primary)',
  'var(--vb-success)',
  'var(--vb-accent)',
  'var(--vb-error)',
  'var(--vb-info)',
  'var(--vb-warning)',
  'var(--vb-text-tertiary)',
];

function buildSegments(dist, orderHint, colorMap, paletteFallback, labelFn) {
  const entries = [];
  const seen = new Set();
  // First pass: keys in declared order
  for (const key of orderHint || []) {
    if (key in (dist || {})) {
      entries.push([key, Number(dist[key]) || 0]);
      seen.add(key);
    }
  }
  // Second pass: any extra keys, sorted by descending count for stability
  const extras = Object.entries(dist || {})
    .filter(([k]) => !seen.has(k))
    .map(([k, v]) => [k, Number(v) || 0])
    .sort((a, b) => b[1] - a[1]);
  for (const e of extras) entries.push(e);

  const total = entries.reduce((s, [, n]) => s + n, 0);
  let paletteIdx = 0;
  return entries.map(([key, count]) => {
    let color = colorMap?.[key];
    if (!color) {
      color = paletteFallback[paletteIdx % paletteFallback.length];
      paletteIdx += 1;
    }
    return {
      key,
      label: labelFn ? labelFn(key) : key,
      count,
      pct: total > 0 ? (count / total) * 100 : 0,
      color,
    };
  });
}

const outcomeSegments = computed(() =>
  buildSegments(
    metrics.value?.outcome_24h || {},
    OUTCOME_ORDER,
    OUTCOME_COLORS,
    ENGINE_COLORS,
    localOutcome,
  ),
);

const engineSegments = computed(() =>
  // Engine codes (e.g. nova-sonic / pipeline) stay as raw strings — they're
  // protocol identifiers, not user-facing labels.
  buildSegments(metrics.value?.engine_distribution_24h || {}, [], {}, ENGINE_COLORS, (k) => k),
);

const demoSegments = computed(() =>
  // Demo ids are user-defined string keys — keep as raw labels, descending count.
  buildSegments(metrics.value?.demo_distribution_24h || {}, [], {}, ENGINE_COLORS, (k) => k),
);

const outcomeTotal = computed(() =>
  outcomeSegments.value.reduce((s, seg) => s + seg.count, 0),
);
const engineTotal = computed(() =>
  engineSegments.value.reduce((s, seg) => s + seg.count, 0),
);
const demoTotal = computed(() =>
  demoSegments.value.reduce((s, seg) => s + seg.count, 0),
);

const lastUpdatedDisplay = computed(() => {
  if (!lastUpdated.value) return '';
  const d = new Date(lastUpdated.value);
  const hh = String(d.getHours()).padStart(2, '0');
  const mm = String(d.getMinutes()).padStart(2, '0');
  const ss = String(d.getSeconds()).padStart(2, '0');
  return `${hh}:${mm}:${ss}`;
});

// --- polling -----------------------------------------------------------------

async function load() {
  loading.value = true;
  try {
    const data = await api.metrics();
    metrics.value = data;
    lastUpdated.value = Date.now();
    failed.value = false;
  } catch (e) {
    failed.value = true;
    // Toast only on first failure or transition; avoid flooding on persistent errors.
    message.error(t('dashboard.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

function refresh() {
  // Manual refresh — fire and forget; current poll interval keeps ticking.
  load();
}

onMounted(() => {
  load();
  timer = setInterval(load, POLL_MS);
});

onUnmounted(() => {
  if (timer !== null) {
    clearInterval(timer);
    timer = null;
  }
});
</script>

<style scoped>
.section-title {
  margin: 24px 0 12px;
  font-size: 13px;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--vb-text-tertiary);
}
.section-title:first-of-type {
  margin-top: 8px;
}

/* Donut + legend side by side, wraps on narrow cards */
.dist-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--vb-space-xl);
}

.legend {
  display: flex;
  flex-direction: column;
  gap: var(--vb-space-sm);
  min-width: 160px;
  flex: 1 1 auto;
}

.legend-item {
  display: inline-flex;
  align-items: center;
  font-size: 12px;
}

.legend-dot {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  margin-right: 6px;
  display: inline-block;
  flex: none;
}

.legend-label {
  font-family: var(--vb-font-mono);
  color: var(--vb-text-secondary);
}

.legend-count {
  font-weight: 600;
  margin-left: 6px;
  color: var(--vb-text);
}

code {
  background: var(--vb-surface-alt);
  padding: 1px 4px;
  border-radius: var(--vb-radius-sm);
  font-size: 12px;
}
</style>
