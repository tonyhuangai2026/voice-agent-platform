<template>
  <div class="summary-block">
    <!-- String summary: render as a single paragraph. -->
    <template v-if="isString">
      <p class="summary-text">{{ summary }}</p>
    </template>

    <!-- Dict summary: render named fields first, then any extras. -->
    <template v-else-if="isObject">
      <p v-if="text" class="summary-text">{{ text }}</p>

      <n-descriptions
        v-if="leadFields.length"
        :column="1"
        bordered
        size="small"
        label-placement="left"
        style="margin-bottom: 8px;"
      >
        <n-descriptions-item
          v-for="f in leadFields"
          :key="f.key"
          :label="f.key"
        >
          {{ f.value }}
        </n-descriptions-item>
      </n-descriptions>

      <div v-if="listFields.length" class="summary-lists">
        <div v-for="f in listFields" :key="f.key" class="summary-list">
          <div class="summary-list-label">{{ f.key }}</div>
          <ul>
            <li v-for="(item, i) in f.value" :key="i">{{ stringify(item) }}</li>
          </ul>
        </div>
      </div>

      <details v-if="extras.length" class="summary-extras">
        <summary>{{ t('historySummary.moreFields', { n: extras.length }) }}</summary>
        <n-descriptions
          :column="1"
          bordered
          size="small"
          label-placement="left"
        >
          <n-descriptions-item
            v-for="f in extras"
            :key="f.key"
            :label="f.key"
          >
            {{ stringify(f.value) }}
          </n-descriptions-item>
        </n-descriptions>
      </details>
    </template>

    <!-- Anything else: stringify as last resort. -->
    <template v-else>
      <p class="summary-text">{{ String(summary) }}</p>
    </template>
  </div>
</template>

<script setup>
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { NDescriptions, NDescriptionsItem } from 'naive-ui';

const { t } = useI18n();

const props = defineProps({
  summary: { type: [String, Object, Array, Number, Boolean], default: null },
});

const isString = computed(() => typeof props.summary === 'string');
const isObject = computed(
  () =>
    props.summary !== null &&
    typeof props.summary === 'object' &&
    !Array.isArray(props.summary)
);

// Pull the most informative text body out of the dict for top-of-block.
const text = computed(() => {
  if (!isObject.value) return '';
  const s = props.summary;
  return s.text || s.body || s.narrative || '';
});

// "Lead" fields render as a 1-col descriptions grid.
const LEAD_KEYS = [
  'intent',
  'outcome',
  'language',
  'lang',
  'caller',
  'sentiment',
  'category',
];

const leadFields = computed(() => {
  if (!isObject.value) return [];
  const out = [];
  for (const k of LEAD_KEYS) {
    const v = props.summary[k];
    if (v === undefined || v === null || v === '') continue;
    if (typeof v === 'object') continue;
    out.push({ key: k, value: String(v) });
  }
  return out;
});

// Array fields → bullet lists.
const listFields = computed(() => {
  if (!isObject.value) return [];
  const out = [];
  for (const [k, v] of Object.entries(props.summary)) {
    if (Array.isArray(v) && v.length > 0) out.push({ key: k, value: v });
  }
  return out;
});

// Anything not already shown → collapsed details panel.
const extras = computed(() => {
  if (!isObject.value) return [];
  const seen = new Set([...LEAD_KEYS, 'text', 'body', 'narrative']);
  for (const f of listFields.value) seen.add(f.key);
  const out = [];
  for (const [k, v] of Object.entries(props.summary)) {
    if (seen.has(k)) continue;
    if (v === undefined || v === null || v === '') continue;
    out.push({ key: k, value: v });
  }
  return out;
});

function stringify(x) {
  if (x === null || x === undefined) return '';
  if (typeof x === 'string') return x;
  if (typeof x === 'number' || typeof x === 'boolean') return String(x);
  try {
    return JSON.stringify(x, null, 2);
  } catch {
    return String(x);
  }
}
</script>

<style scoped>
.summary-block {
  margin-bottom: 4px;
}

.summary-text {
  margin: 0 0 12px;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.5;
}

.summary-list {
  margin-bottom: 8px;
}

.summary-list-label {
  font-size: 12px;
  font-weight: 600;
  margin-bottom: 4px;
  opacity: 0.75;
}

.summary-list ul {
  margin: 0;
  padding-left: 20px;
}

.summary-list li {
  margin-bottom: 2px;
  white-space: pre-wrap;
}

.summary-extras {
  margin-top: 8px;
}

.summary-extras summary {
  cursor: pointer;
  font-size: 12px;
  opacity: 0.7;
  margin-bottom: 6px;
}
</style>
