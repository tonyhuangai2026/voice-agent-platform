<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ t('mcp.title') }}</template>
      <template #subtitle>{{ t('mcp.subtitle') }}</template>
      <template #extra>
        <n-space :size="8">
          <n-button @click="load" :loading="loading">
            <template #icon><n-icon :component="Renew" /></template>
            {{ t('common.refresh') }}
          </n-button>
          <n-button type="primary" @click="openCreate">
            <template #icon><n-icon :component="Add" /></template>
            {{ t('mcp.actions.add') }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-alert type="info" style="margin-bottom: 16px;">
      <span v-html="t('mcp.notice')" />
    </n-alert>

    <n-card :bordered="true">
      <n-data-table
        :columns="columns"
        :data="servers"
        :loading="loading"
        :pagination="{ pageSize: 10 }"
        :row-key="(row) => row.id"
      >
        <template #empty>
          <EmptyState :title="t('mcp.emptyTitle')" :description="t('mcp.emptyDesc')">
            <template #icon><n-icon :component="Plug" /></template>
            <n-button type="primary" size="small" @click="openCreate">
              <template #icon><n-icon :component="Add" /></template>
              {{ t('mcp.actions.add') }}
            </n-button>
          </EmptyState>
        </template>
      </n-data-table>
    </n-card>

    <!-- Add / edit modal -->
    <n-modal
      v-model:show="modalOpen"
      preset="card"
      :title="editing ? t('mcp.form.titleEdit') : t('mcp.form.titleNew')"
      style="width: 560px; max-width: 92vw;"
      :mask-closable="false"
    >
      <n-form label-placement="top">
        <n-form-item :label="t('mcp.form.id')">
          <n-input
            v-model:value="form.id"
            :disabled="editing"
            :placeholder="'weather-api'"
          />
        </n-form-item>
        <n-text
          v-if="!editing"
          depth="3"
          style="display: block; font-size: 12px; margin: -8px 0 12px;"
        >
          {{ t('mcp.form.idHint') }}
        </n-text>

        <n-form-item :label="t('mcp.form.label')">
          <n-input v-model:value="form.label" :placeholder="form.id || ''" />
        </n-form-item>

        <n-form-item :label="t('mcp.form.transport')">
          <!-- Backend rejects anything except sse / streamable_http (stdio is
               a security no-go) — the select offers exactly those two. -->
          <n-select v-model:value="form.transport" :options="transportOptions" />
        </n-form-item>

        <n-form-item :label="t('mcp.form.url')">
          <n-input v-model:value="form.url" :placeholder="t('mcp.form.urlPlaceholder')" />
        </n-form-item>

        <n-form-item :label="t('mcp.form.enabled')">
          <n-switch v-model:value="form.enabled" />
        </n-form-item>

        <n-form-item :label="t('mcp.form.auth')">
          <!-- none = no auth; header = the headers editor below; sigv4 = AWS
               SigV4 signing at connect time (service + region, no stored
               secret — uses the instance IAM role). Selecting sigv4 hides the
               headers editor; selecting header shows it. -->
          <n-select v-model:value="form.authType" :options="authOptions" />
        </n-form-item>

        <template v-if="form.authType === 'sigv4'">
          <n-text depth="3" style="display: block; font-size: 12px; margin: -8px 0 12px;">
            {{ t('mcp.form.sigv4Hint') }}
          </n-text>
          <n-form-item :label="t('mcp.form.sigv4Service')">
            <n-input v-model:value="form.sigv4Service" :placeholder="SIGV4_DEFAULT_SERVICE" />
          </n-form-item>
          <n-form-item :label="t('mcp.form.sigv4Region')">
            <n-input v-model:value="form.sigv4Region" :placeholder="SIGV4_DEFAULT_REGION" />
          </n-form-item>
        </template>

        <n-form-item v-if="form.authType === 'header'" :label="t('mcp.form.headers')">
          <div style="width: 100%;">
            <n-text depth="3" style="display: block; font-size: 12px; margin-bottom: 8px;">
              {{ t('mcp.form.headersHint') }}
            </n-text>
            <div
              v-for="(row, idx) in headerRows"
              :key="idx"
              class="header-row"
            >
              <n-input
                v-model:value="row.key"
                :placeholder="t('mcp.form.headerKey')"
                style="flex: 2;"
              />
              <n-input
                v-model:value="row.value"
                type="password"
                show-password-on="click"
                :placeholder="row.existing ? t('mcp.form.headerValuePlaceholder') : t('mcp.form.headerValueNewPlaceholder')"
                style="flex: 3;"
              />
              <n-button quaternary circle size="small" @click="headerRows.splice(idx, 1)">
                <template #icon><n-icon :component="Close" /></template>
              </n-button>
            </div>
            <n-button size="small" dashed style="margin-top: 4px;" @click="addHeaderRow">
              <template #icon><n-icon :component="Add" /></template>
              {{ t('mcp.form.addHeader') }}
            </n-button>
          </div>
        </n-form-item>
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
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NSelect,
  NSwitch,
  NTag,
  NText,
  NEllipsis,
  useDialog,
  useMessage,
} from 'naive-ui';
import {
  Renew,
  Add,
  Close,
  Plug,
  Result,
  Edit,
  TrashCan,
} from '@vicons/carbon';
import { api } from '../api.js';
import EmptyState from '../components/ui/EmptyState.vue';

const { t } = useI18n();
const message = useMessage();
const dialog = useDialog();

const servers = ref([]);
const loading = ref(false);
const saving = ref(false);
// Per-row Test button loading flags, keyed by server id.
const testing = reactive({});

const modalOpen = ref(false);
const editing = ref(false);
// SigV4 defaults mirror mcp_config.SIGV4_DEFAULT_SERVICE / _REGION — used as
// input placeholders and as the value sent when the field is left blank.
const SIGV4_DEFAULT_SERVICE = 'bedrock-agentcore';
const SIGV4_DEFAULT_REGION = 'us-east-1';

const form = reactive({
  id: '',
  label: '',
  transport: 'streamable_http',
  url: '',
  enabled: true,
  // auth.type ∈ none|header|sigv4. sigv4 carries service/region (no secret);
  // header keeps using the headerRows editor; none uses neither.
  authType: 'none',
  sigv4Service: '',
  sigv4Region: '',
});
// Headers editor rows. For headers already stored server-side the GET
// response masks values as "***" — we render an EMPTY input with a
// "*** (unchanged)" placeholder instead of pre-filling anything, and an
// empty value on save is sent as the "***" sentinel so the backend keeps
// the stored secret (mcp_config.upsert mask round-trip).
const headerRows = ref([]);

// Mirrors mcp_config.SERVER_ID_RE / URL validation so obvious mistakes are
// caught before the round-trip (server still re-validates).
const ID_RE = /^[a-z0-9][a-z0-9-]{1,62}$/;
const URL_RE = /^https?:\/\/\S+$/;

const transportOptions = computed(() => [
  { label: 'SSE', value: 'sse' },
  { label: 'Streamable HTTP', value: 'streamable_http' },
]);

const authOptions = computed(() => [
  { label: t('mcp.authType.none'), value: 'none' },
  { label: t('mcp.authType.header'), value: 'header' },
  { label: t('mcp.authType.sigv4'), value: 'sigv4' },
]);

const formValid = computed(
  () => ID_RE.test(form.id) && URL_RE.test(form.url || ''),
);

const columns = computed(() => [
  {
    title: t('mcp.columns.id'),
    key: 'id',
    width: 160,
    // Inline style (not a scoped class): this vnode renders inside
    // NDataTable's subtree where this component's scoped attr is absent.
    render: (row) =>
      h(
        'span',
        { style: 'font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;' },
        row.id,
      ),
  },
  { title: t('mcp.columns.label'), key: 'label', width: 160 },
  {
    title: t('mcp.columns.transport'),
    key: 'transport',
    width: 150,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.transport === 'sse' ? 'warning' : 'info', bordered: false },
        () => (row.transport === 'sse' ? 'SSE' : 'Streamable HTTP'),
      ),
  },
  {
    title: t('mcp.columns.auth'),
    key: 'auth',
    width: 120,
    // GET re-display of auth: sigv4 has no secret so the type is shown plainly
    // (header secrets stay masked as "***" in the edit form, never here).
    render: (row) => {
      const atype = row.auth?.type || 'none';
      const labels = {
        none: t('mcp.authType.none'),
        header: t('mcp.authType.header'),
        sigv4: t('mcp.authType.sigv4'),
      };
      return h(
        NTag,
        { size: 'small', type: atype === 'sigv4' ? 'warning' : 'default', bordered: false },
        () => labels[atype] || atype,
      );
    },
  },
  {
    title: t('mcp.columns.url'),
    key: 'url',
    render: (row) =>
      h(NEllipsis, { style: 'max-width: 260px; font-size: 12px;' }, () => row.url),
  },
  {
    title: t('mcp.columns.enabled'),
    key: 'enabled',
    width: 100,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.enabled ? 'success' : 'default', bordered: false },
        () => (row.enabled ? t('mcp.enabledTag.on') : t('mcp.enabledTag.off')),
      ),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 210,
    render: (row) =>
      h(NSpace, { size: 6 }, () => [
        h(
          NButton,
          {
            size: 'small',
            type: 'primary',
            secondary: true,
            loading: !!testing[row.id],
            onClick: () => testServer(row),
          },
          {
            icon: () => h(NIcon, null, { default: () => h(Result) }),
            default: () => t('mcp.actions.test'),
          },
        ),
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
]);

async function load() {
  loading.value = true;
  try {
    const data = await api.mcpServers();
    servers.value = data.servers || [];
  } catch (e) {
    message.error(t('mcp.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

function addHeaderRow() {
  headerRows.value.push({ key: '', value: '', existing: false });
}

function openCreate() {
  editing.value = false;
  form.id = '';
  form.label = '';
  form.transport = 'streamable_http';
  form.url = '';
  form.enabled = true;
  form.authType = 'none';
  form.sigv4Service = '';
  form.sigv4Region = '';
  headerRows.value = [];
  modalOpen.value = true;
}

function openEdit(row) {
  editing.value = true;
  form.id = row.id;
  form.label = row.label || '';
  form.transport = row.transport;
  form.url = row.url;
  form.enabled = !!row.enabled;
  // auth re-display: sigv4 carries no secret, so service/region come straight
  // from the GET response (blank → placeholder default on save).
  const auth = row.auth || { type: 'none' };
  form.authType = auth.type || 'none';
  form.sigv4Service = auth.service || '';
  form.sigv4Region = auth.region || '';
  // Never pre-fill secrets: existing headers get an empty input whose
  // placeholder explains "leave blank to keep the stored value".
  headerRows.value = Object.keys(row.headers || {}).map((k) => ({
    key: k,
    value: '',
    existing: true,
  }));
  modalOpen.value = true;
}

function buildHeaders() {
  const out = {};
  for (const row of headerRows.value) {
    const key = (row.key || '').trim();
    if (!key) continue;
    if (row.value !== '') {
      out[key] = row.value;
    } else if (row.existing) {
      // Untouched existing header — send the mask sentinel so the backend
      // keeps the secret it already has for this key.
      out[key] = '***';
    }
    // New row with an empty value: dropped on purpose (nothing to store).
  }
  return out;
}

// Canonical auth object for the POST body. sigv4 falls back to the
// bedrock-agentcore / us-east-1 defaults when the inputs are left blank
// (matching mcp_config.validate_auth); none/header carry no extra fields.
function buildAuth() {
  if (form.authType === 'sigv4') {
    return {
      type: 'sigv4',
      service: (form.sigv4Service || '').trim() || SIGV4_DEFAULT_SERVICE,
      region: (form.sigv4Region || '').trim() || SIGV4_DEFAULT_REGION,
    };
  }
  return { type: form.authType };
}

async function save() {
  saving.value = true;
  try {
    await api.saveMcpServer({
      id: form.id,
      label: (form.label || '').trim() || form.id,
      transport: form.transport,
      url: form.url.trim(),
      // Only header auth uses the headers editor; for none/sigv4 send an empty
      // object so no stale secrets ride along.
      headers: form.authType === 'header' ? buildHeaders() : {},
      enabled: form.enabled,
      auth: buildAuth(),
    });
    message.success(t('mcp.messages.saved'));
    modalOpen.value = false;
    await load();
  } catch (e) {
    message.error(t('mcp.messages.saveFailed', { msg: e.message }));
  } finally {
    saving.value = false;
  }
}

function confirmDelete(row) {
  dialog.warning({
    title: t('mcp.deleteConfirm.title'),
    content: t('mcp.deleteConfirm.body', { id: row.id }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => doDelete(row),
  });
}

async function doDelete(row) {
  try {
    await api.deleteMcpServer(row.id);
    message.success(t('mcp.messages.deleted'));
    await load();
  } catch (e) {
    // 409 — server is still mounted by demos; surface the referencing ids
    // so the admin knows exactly where to unmount it first.
    const refs = e?.body?.detail?.demos;
    if (e.status === 409 && Array.isArray(refs)) {
      dialog.error({
        title: t('mcp.deleteConfirm.title'),
        content: t('mcp.messages.deleteRefused', { id: row.id, demos: refs.join(', ') }),
        positiveText: t('common.confirm'),
      });
    } else {
      message.error(t('mcp.messages.deleteFailed', { msg: e.message }));
    }
  }
}

async function testServer(row) {
  testing[row.id] = true;
  try {
    const r = await api.testMcpServer(row.id);
    if (r.ok) {
      const tools = r.tools || [];
      if (tools.length === 0) {
        message.success(t('mcp.test.okEmpty', { id: row.id }));
      } else {
        dialog.success({
          title: t('mcp.test.okTitle', { id: row.id, n: tools.length }),
          content: () =>
            h(
              NSpace,
              { size: 6, wrap: true, style: 'margin-top: 8px;' },
              () =>
                tools.map((name) =>
                  h(
                    NTag,
                    { size: 'small', type: 'success', bordered: false, key: name },
                    () => name,
                  ),
                ),
            ),
          positiveText: t('common.confirm'),
        });
      }
    } else {
      message.error(
        t('mcp.test.failTitle', { id: row.id }) + ': ' + (r.error || 'unknown error'),
        { duration: 6000 },
      );
    }
  } catch (e) {
    message.error(t('mcp.messages.testFailed', { msg: e.message }));
  } finally {
    testing[row.id] = false;
  }
}

onMounted(load);
</script>

<style scoped>
.header-row {
  display: flex;
  gap: var(--vb-space-sm);
  align-items: center;
  margin-bottom: var(--vb-space-sm);
}
</style>
