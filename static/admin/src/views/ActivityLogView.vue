<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ t('activity.title') }}</template>
      <template #subtitle>{{ t('activity.subtitle') }}</template>
      <template #extra>
        <n-button @click="reload" :loading="loading">
          <template #icon><n-icon :component="Renew" /></template>
          {{ t('activity.actions.refresh') }}
        </n-button>
      </template>
    </n-page-header>

    <n-card :bordered="true" style="margin-bottom: 16px;">
      <n-grid :cols="24" :x-gap="12" :y-gap="12" responsive="screen" item-responsive>
        <n-grid-item span="24 m:8">
          <n-form-item :label="t('activity.filters.actor')" :show-feedback="false">
            <n-input
              v-model:value="filters.actor"
              :placeholder="t('activity.filters.actorPlaceholder')"
              clearable
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item span="24 m:8">
          <n-form-item :label="t('activity.filters.type')" :show-feedback="false">
            <n-select
              v-model:value="filters.type"
              :options="typeOptions"
              clearable
              :placeholder="t('activity.filters.all')"
            />
          </n-form-item>
        </n-grid-item>
        <n-grid-item span="24 m:8">
          <n-form-item :label="t('activity.filters.dateRange')" :show-feedback="false">
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
          <EmptyState :title="t('activity.emptyTitle')" :description="t('activity.emptyDesc')">
            <template #icon><n-icon :component="Catalog" /></template>
          </EmptyState>
        </template>
      </n-data-table>
      <div class="load-more">
        <n-button @click="loadMore" :disabled="!nextCursor || loading" :loading="loadingMore">
          {{ nextCursor ? t('activity.actions.loadMore') : t('activity.actions.noMore') }}
        </n-button>
        <n-text depth="3" style="margin-left: 12px; font-size: 12px;">
          {{ t('activity.actions.loadedRows', { n: rows.length }) }}
        </n-text>
      </div>
    </n-card>

    <n-drawer v-model:show="drawerOpen" :width="560" placement="right">
      <n-drawer-content
        :title="detail ? t('activity.detail.titlePrefix', { type: detail.typeLabel }) : ''"
        closable
      >
        <template v-if="detail">
          <n-descriptions :column="1" bordered size="small" label-placement="left">
            <n-descriptions-item :label="t('activity.detail.time')">
              {{ detail.tsText || t('common.placeholderDash') }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('activity.detail.actor')">
              {{ detail.actor || t('common.placeholderDash') }}
              <n-tag v-if="detail.actorRole" size="tiny" :bordered="false" style="margin-left: 6px;">
                {{ detail.actorRole }}
              </n-tag>
            </n-descriptions-item>
            <n-descriptions-item :label="t('activity.detail.type')">
              {{ detail.typeLabel }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('activity.detail.target')">
              {{ detail.target || t('common.placeholderDash') }}
            </n-descriptions-item>
            <n-descriptions-item :label="t('activity.detail.status')">
              <n-tag size="small" :type="statusTagType(detail.status)" :bordered="false">
                {{ detail.status || t('common.placeholderDash') }}
              </n-tag>
            </n-descriptions-item>
            <n-descriptions-item v-if="detail.error" :label="t('activity.detail.error')">
              <n-text type="error">{{ detail.error }}</n-text>
            </n-descriptions-item>
          </n-descriptions>

          <n-divider title-placement="left">{{ t('activity.detail.detailMap') }}</n-divider>
          <template v-if="detailEntries.length">
            <n-descriptions :column="1" bordered size="small" label-placement="left">
              <n-descriptions-item
                v-for="[k, v] in detailEntries"
                :key="k"
                :label="k"
              >
                {{ renderDetailValue(v) }}
              </n-descriptions-item>
            </n-descriptions>
          </template>
          <template v-else>
            <n-text depth="3">{{ t('activity.detail.noDetail') }}</n-text>
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
  NButton,
  NDataTable,
  NDrawer,
  NDrawerContent,
  NDescriptions,
  NDescriptionsItem,
  NDivider,
  NTag,
  NText,
  useMessage,
} from 'naive-ui';
import { Renew, Catalog } from '@vicons/carbon';
import { api } from '../api.js';
import EmptyState from '../components/ui/EmptyState.vue';
import {
  activityTypeOptions,
  buildActivityParams,
  statusTagType,
  toActivityRows,
} from '../activityFields.js';

const { t } = useI18n();
const message = useMessage();

const PAGE_LIMIT = 50;

// type dropdown — localized labels, raw values (recomputed on locale change).
const typeOptions = computed(() => activityTypeOptions());

const filters = reactive({
  actor: '',
  type: null,
  dateRange: null, // [startMs, endMs] from n-date-picker
});

const rows = ref([]);
const nextCursor = ref(null);
const loading = ref(false);
const loadingMore = ref(false);

const drawerOpen = ref(false);
const detail = ref(null);
const detailEntries = computed(() =>
  detail.value ? Object.entries(detail.value.detail || {}) : [],
);

function renderDetailValue(v) {
  if (v === null || v === undefined) return t('common.placeholderDash');
  if (typeof v === 'object') return JSON.stringify(v);
  return String(v);
}

const columns = computed(() => [
  { title: t('activity.columns.time'), key: 'tsText', width: 200 },
  { title: t('activity.columns.actor'), key: 'actor', width: 150 },
  {
    title: t('activity.columns.type'),
    key: 'type',
    width: 150,
    render: (row) => row.typeLabel,
  },
  {
    title: t('activity.columns.target'),
    key: 'target',
    render: (row) => row.target || t('common.placeholderDash'),
  },
  {
    title: t('activity.columns.status'),
    key: 'status',
    width: 120,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: statusTagType(row.status), bordered: false },
        () => row.status || t('common.placeholderDash'),
      ),
  },
  {
    title: t('activity.columns.actions'),
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
            e.stopPropagation();
            openDetail(row);
          },
        },
        () => t('activity.actions.view'),
      ),
  },
]);

function rowProps(row) {
  return { style: 'cursor: pointer;', onClick: () => openDetail(row) };
}

function openDetail(row) {
  detail.value = row;
  drawerOpen.value = true;
}

async function reload() {
  loading.value = true;
  rows.value = [];
  nextCursor.value = null;
  try {
    const params = buildActivityParams(filters, { withCursor: false, limit: PAGE_LIMIT });
    const r = await api.activity(params);
    rows.value = toActivityRows(r.items);
    nextCursor.value = r.cursor || null;
  } catch (e) {
    message.error(t('activity.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

async function loadMore() {
  if (!nextCursor.value || loadingMore.value) return;
  loadingMore.value = true;
  try {
    const params = buildActivityParams(filters, {
      withCursor: true,
      cursor: nextCursor.value,
      limit: PAGE_LIMIT,
    });
    const r = await api.activity(params);
    rows.value = rows.value.concat(toActivityRows(r.items));
    nextCursor.value = r.cursor || null;
  } catch (e) {
    message.error(t('activity.messages.loadMoreFailed', { msg: e.message }));
  } finally {
    loadingMore.value = false;
  }
}

let debounceHandle = null;
function debouncedReload(delay = 300) {
  if (debounceHandle) clearTimeout(debounceHandle);
  debounceHandle = setTimeout(() => {
    debounceHandle = null;
    reload();
  }, delay);
}

watch(() => filters.actor, () => debouncedReload(400));
watch(
  () => [filters.type, filters.dateRange],
  () => debouncedReload(150),
  { deep: true },
);

onMounted(reload);
</script>

<style scoped>
.load-more {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--vb-space-lg) 0 var(--vb-space-xs);
}
</style>
