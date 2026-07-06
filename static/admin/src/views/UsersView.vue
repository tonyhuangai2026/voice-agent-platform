<template>
  <div>
    <n-page-header style="margin-bottom: 16px;">
      <template #title>{{ t('users.title') }}</template>
      <template #subtitle>{{ t('users.subtitle') }}</template>
      <template #extra>
        <n-space :size="8">
          <n-button @click="load" :loading="loading">
            <template #icon><n-icon :component="Renew" /></template>
            {{ t('common.refresh') }}
          </n-button>
          <n-button @click="openGuestLink">
            <template #icon><n-icon :component="Link" /></template>
            {{ t('users.guestLink.button') }}
          </n-button>
          <n-button type="primary" @click="openCreate">
            <template #icon><n-icon :component="Add" /></template>
            {{ t('users.actions.add') }}
          </n-button>
        </n-space>
      </template>
    </n-page-header>

    <n-card :bordered="true">
      <n-data-table
        :columns="columns"
        :data="users"
        :loading="loading"
        :pagination="{ pageSize: 10 }"
        :row-key="(row) => row.username"
      >
        <template #empty>
          <EmptyState :title="t('users.emptyTitle')" :description="t('users.emptyDesc')">
            <template #icon><n-icon :component="UserMultiple" /></template>
            <n-button type="primary" size="small" @click="openCreate">
              <template #icon><n-icon :component="Add" /></template>
              {{ t('users.actions.add') }}
            </n-button>
          </EmptyState>
        </template>
      </n-data-table>
    </n-card>

    <!-- Create-user modal -->
    <n-modal
      v-model:show="createOpen"
      preset="card"
      :title="t('users.form.titleNew')"
      style="width: 480px; max-width: 92vw;"
      :mask-closable="false"
    >
      <n-form label-placement="top">
        <n-form-item :label="t('users.form.username')">
          <n-input v-model:value="createForm.username" placeholder="jdoe" />
        </n-form-item>
        <n-text
          depth="3"
          style="display: block; font-size: 12px; margin: -8px 0 12px;"
        >
          {{ t('users.form.usernameHint') }}
        </n-text>

        <n-form-item :label="t('users.form.password')">
          <n-input
            v-model:value="createForm.password"
            type="password"
            show-password-on="click"
            :placeholder="t('users.form.passwordPlaceholder')"
          />
        </n-form-item>

        <n-form-item :label="t('users.form.role')">
          <n-select v-model:value="createForm.role" :options="roleOptions" />
        </n-form-item>
      </n-form>

      <template #footer>
        <n-space justify="end">
          <n-button @click="createOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button
            type="primary"
            :loading="saving"
            :disabled="!createValid"
            @click="doCreate"
          >
            {{ t('common.create') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Reset-password modal -->
    <n-modal
      v-model:show="pwOpen"
      preset="card"
      :title="t('users.form.titleResetPw', { username: pwTarget })"
      style="width: 440px; max-width: 92vw;"
      :mask-closable="false"
    >
      <n-form label-placement="top">
        <n-form-item :label="t('users.form.newPassword')">
          <n-input
            v-model:value="pwValue"
            type="password"
            show-password-on="click"
            :placeholder="t('users.form.passwordPlaceholder')"
          />
        </n-form-item>
      </n-form>
      <template #footer>
        <n-space justify="end">
          <n-button @click="pwOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button
            type="primary"
            :loading="saving"
            :disabled="!pwValue"
            @click="doResetPassword"
          >
            {{ t('common.save') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>

    <!-- Generate-guest-link modal (tech_design §3.3). Before minting: TTL +
         optional scenario selectors. After minting: the link is shown ONCE in
         a read-only input with copy-to-clipboard + human expiry; it is never
         persisted. Closing the modal discards it. -->
    <n-modal
      v-model:show="guestOpen"
      preset="card"
      :title="t('users.guestLink.title')"
      style="width: 520px; max-width: 92vw;"
      :mask-closable="false"
      @after-leave="resetGuest"
    >
      <template v-if="!guestResult">
        <n-form label-placement="top">
          <n-form-item :label="t('users.guestLink.ttl')">
            <n-select v-model:value="guestForm.ttl" :options="ttlOptions" />
          </n-form-item>
          <n-form-item :label="t('users.guestLink.scenario')">
            <n-select
              v-model:value="guestForm.scenario"
              :options="scenarioOptions"
              :loading="scenarioLoading"
              clearable
              @update:value="onScenarioPick"
            />
          </n-form-item>

          <!-- Launch-config overrides (tech_design §3.1). Picking a scenario
               prefills these from that demo's DETAIL (GET /api/admin/demos/{id});
               they stay editable and cross-filter exactly like Talk/Demos
               (engine → lang list; provider/lang → pipeline voice list; nova →
               nova-voice list). Their non-empty values ride the token. -->
          <n-form-item :label="t('users.guestLink.engine')">
            <n-select
              v-model:value="guestForm.engine"
              :options="guestEngineOptions"
              :loading="guestCfgLoading || guestDetailLoading"
              clearable
            />
          </n-form-item>
          <n-form-item :label="t('users.guestLink.lang')">
            <n-select
              v-model:value="guestForm.lang"
              :options="guestLangOptions"
              :loading="guestCfgLoading || guestDetailLoading"
              clearable
            />
          </n-form-item>
          <template v-if="guestEffectiveEngine === 'nova-sonic'">
            <n-form-item :label="t('users.guestLink.voice')">
              <n-select
                v-model:value="guestForm.voice"
                :options="guestNovaVoiceOptions"
                :loading="guestCfgLoading || guestDetailLoading"
                clearable
                filterable
              />
            </n-form-item>
          </template>
          <template v-else>
            <n-form-item :label="t('users.guestLink.provider')">
              <n-select
                v-model:value="guestForm.provider"
                :options="guestProviderOptions"
                :loading="guestCfgLoading || guestDetailLoading"
                clearable
              />
            </n-form-item>
            <n-form-item :label="t('users.guestLink.voice')">
              <n-select
                v-model:value="guestForm.voice"
                :options="guestPipelineVoiceOptions"
                :loading="guestCfgLoading || guestDetailLoading"
                clearable
                filterable
              />
            </n-form-item>
          </template>
        </n-form>
      </template>
      <template v-else>
        <n-space vertical :size="12">
          <n-text depth="3" style="font-size: 12px;">
            {{ t('users.guestLink.expiry', { time: guestExpiryText }) }}
          </n-text>
          <n-input-group>
            <n-input :value="guestResult.link" readonly />
            <n-button type="primary" @click="copyGuestLink">
              <template #icon><n-icon :component="Copy" /></template>
              {{ t('users.guestLink.copy') }}
            </n-button>
          </n-input-group>
        </n-space>
      </template>

      <template #footer>
        <n-space justify="end">
          <n-button @click="guestOpen = false">{{ t('common.cancel') }}</n-button>
          <n-button
            v-if="!guestResult"
            type="primary"
            :loading="guestSaving"
            @click="doGuestLink"
          >
            {{ t('users.guestLink.button') }}
          </n-button>
        </n-space>
      </template>
    </n-modal>
  </div>
</template>

<script setup>
import { computed, h, onMounted, reactive, ref, watch } from 'vue';
import { useI18n } from 'vue-i18n';
import {
  NPageHeader,
  NCard,
  NSpace,
  NButton,
  NDataTable,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NInputGroup,
  NModal,
  NSelect,
  NTag,
  NText,
  useDialog,
  useMessage,
} from 'naive-ui';
import {
  Renew,
  Add,
  Password,
  UserMultiple,
  TrashCan,
  UserFollow,
  Locked,
  Link,
  Copy,
} from '@vicons/carbon';
import { api } from '../api.js';
import { buildGuestLink, GUEST_TTL_OPTIONS, GUEST_TTL_DEFAULT } from '../guestLink.js';
import {
  enginesFor,
  langsForEngine,
  voicesForProvLang,
  novaVoices,
  guestPrefillFromDemo,
  guestLinkBody,
} from '../talkConfig.js';
import EmptyState from '../components/ui/EmptyState.vue';

const { t } = useI18n();
const message = useMessage();
const dialog = useDialog();

const users = ref([]);
const loading = ref(false);
const saving = ref(false);

// Create-user modal state.
const createOpen = ref(false);
const createForm = reactive({ username: '', password: '', role: 'user' });

// Reset-password modal state (separate from create so the username field is
// fixed and only a new password is collected).
const pwOpen = ref(false);
const pwTarget = ref('');
const pwValue = ref('');

// Generate-guest-link modal state (tech_design §3.3). `guestResult` is null
// until the link is minted; once set the modal flips to the read-only link +
// copy view. Scenario options are lazy-loaded from /api/config demos.
const guestOpen = ref(false);
const guestSaving = ref(false);
// guestForm now carries the full launch config (tech_design §3.1): the four
// optional overrides ride the token alongside ttl + scenario.
const guestForm = reactive({
  ttl: GUEST_TTL_DEFAULT,
  scenario: null,
  lang: null,
  engine: null,
  voice: null,
  provider: null,
});
const guestResult = ref(null); // { link, expires_at }
const scenarioOptions = ref([]);
const scenarioLoading = ref(false);

// Runtime config (engine/lang/provider/voice option lists) — lazy-loaded once
// with the scenario list; drives the cross-filtered selects below. Demo detail
// (GET /api/admin/demos/{id}) is fetched on scenario pick to prefill the four
// fields from the demo's STORED config (NOT the /api/config demos list, which
// has no config — tech_design §3.1).
const guestConfig = ref(null);
const guestCfgLoading = ref(false);
const guestDetailLoading = ref(false);

// Effective engine for nova-vs-pipeline branching: explicit pick, else the
// config default (mirrors DemosView's evEffectiveEngine).
const guestEffectiveEngine = computed(
  () => guestForm.engine || guestConfig.value?.default_engine || null,
);

const guestEngineOptions = computed(() =>
  enginesFor(guestConfig.value).map((e) => ({ label: e.label, value: e.id })),
);
// lang cross-filtered by the effective engine (engine×language capability).
const guestLangOptions = computed(() => {
  const eng = guestEffectiveEngine.value;
  const langs = eng
    ? langsForEngine(guestConfig.value, eng)
    : guestConfig.value?.languages || [];
  return langs.map((l) => ({ label: l.label, value: l.id }));
});
const guestProviderOptions = computed(() =>
  (guestConfig.value?.providers || []).map((p) => ({ label: p.label, value: p.id })),
);
const guestPipelineVoiceOptions = computed(() => {
  const provider = guestForm.provider || guestConfig.value?.default_provider;
  return voicesForProvLang(guestConfig.value, provider, guestForm.lang).map((v) => ({
    label: v.label,
    value: v.id,
  }));
});
const guestNovaVoiceOptions = computed(() =>
  novaVoices(guestConfig.value).map((v) => ({
    label: `${v.label}${v.gender ? ' · ' + v.gender : ''}${v.polyglot ? ' · polyglot' : ''}`,
    value: v.id,
  })),
);

// Cross-filtering: when the engine changes, drop a now-invalid lang/voice so the
// selects never show a stale value not in their current option list (same self-
// correction DemosView/TalkView do). Only runs while the modal is open.
watch(
  () => guestForm.engine,
  () => {
    if (!guestOpen.value || !guestConfig.value) return;
    const langIds = guestLangOptions.value.map((o) => o.value);
    if (guestForm.lang && !langIds.includes(guestForm.lang)) guestForm.lang = null;
    if (guestEffectiveEngine.value === 'nova-sonic') {
      guestForm.provider = null;
      const novaIds = guestNovaVoiceOptions.value.map((o) => o.value);
      if (guestForm.voice && !novaIds.includes(guestForm.voice)) guestForm.voice = null;
    } else {
      const pipeIds = guestPipelineVoiceOptions.value.map((o) => o.value);
      if (guestForm.voice && !pipeIds.includes(guestForm.voice)) guestForm.voice = null;
    }
  },
);
// When provider/lang change (pipeline), drop a voice that's no longer offered.
watch(
  () => [guestForm.provider, guestForm.lang],
  () => {
    if (!guestOpen.value || !guestConfig.value) return;
    if (guestEffectiveEngine.value === 'nova-sonic') return;
    const pipeIds = guestPipelineVoiceOptions.value.map((o) => o.value);
    if (guestForm.voice && !pipeIds.includes(guestForm.voice)) guestForm.voice = null;
  },
);

const ttlOptions = computed(() =>
  GUEST_TTL_OPTIONS.map((m) => ({
    label: t('users.guestLink.ttlOption', { min: m }),
    value: m,
  })),
);

// Human expiry shown alongside the minted link ("expires at HH:MM").
const guestExpiryText = computed(() => {
  const exp = guestResult.value?.expires_at;
  if (!exp) return '';
  return new Date(exp * 1000).toLocaleString();
});

// Mirror user_store.USERNAME validation client-side so obvious mistakes are
// caught before the round-trip (server still re-validates).
const USERNAME_RE = /^[A-Za-z0-9._-]{2,64}$/;

const roleOptions = computed(() => [
  { label: t('users.roles.user'), value: 'user' },
  { label: t('users.roles.admin'), value: 'admin' },
]);

const createValid = computed(
  () => USERNAME_RE.test(createForm.username) && !!createForm.password,
);

function roleLabel(role) {
  return role === 'admin' ? t('users.roles.admin') : t('users.roles.user');
}

function fmtCreated(secs) {
  const ts = Number(secs);
  if (!Number.isFinite(ts) || ts <= 0) return t('common.dash');
  return new Date(ts * 1000).toLocaleString();
}

const columns = computed(() => [
  {
    title: t('users.columns.username'),
    key: 'username',
    render: (row) =>
      h(
        'span',
        { style: 'font-weight:600;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:13px;' },
        row.username,
      ),
  },
  {
    title: t('users.columns.role'),
    key: 'role',
    width: 120,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.role === 'admin' ? 'warning' : 'info', bordered: false },
        () => roleLabel(row.role),
      ),
  },
  {
    title: t('users.columns.status'),
    key: 'disabled',
    width: 110,
    render: (row) =>
      h(
        NTag,
        { size: 'small', type: row.disabled ? 'default' : 'success', bordered: false },
        () => (row.disabled ? t('users.status.disabled') : t('users.status.active')),
      ),
  },
  {
    title: t('users.columns.createdAt'),
    key: 'created_at',
    width: 200,
    render: (row) =>
      h('span', { style: 'font-size:12px;color:var(--vb-text-tertiary);' }, fmtCreated(row.created_at)),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 300,
    render: (row) =>
      h(NSpace, { size: 6 }, () => [
        // Toggle role between user <-> admin.
        h(
          NButton,
          { size: 'small', onClick: () => toggleRole(row) },
          {
            icon: () => h(NIcon, null, { default: () => h(UserMultiple) }),
            default: () =>
              row.role === 'admin' ? t('users.actions.makeUser') : t('users.actions.makeAdmin'),
          },
        ),
        // Reset password.
        h(
          NButton,
          { size: 'small', onClick: () => openResetPassword(row) },
          {
            icon: () => h(NIcon, null, { default: () => h(Password) }),
            default: () => t('users.actions.resetPw'),
          },
        ),
        // Enable / disable.
        h(
          NButton,
          {
            size: 'small',
            type: row.disabled ? 'success' : 'warning',
            secondary: true,
            onClick: () => toggleDisabled(row),
          },
          {
            icon: () => h(NIcon, null, { default: () => h(row.disabled ? UserFollow : Locked) }),
            default: () => (row.disabled ? t('users.actions.enable') : t('users.actions.disable')),
          },
        ),
        // Delete.
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
    const data = await api.users();
    users.value = data.users || [];
  } catch (e) {
    message.error(t('users.messages.loadFailed', { msg: e.message }));
  } finally {
    loading.value = false;
  }
}

function openCreate() {
  createForm.username = '';
  createForm.password = '';
  createForm.role = 'user';
  createOpen.value = true;
}

async function doCreate() {
  saving.value = true;
  try {
    await api.createUser({
      username: createForm.username.trim(),
      password: createForm.password,
      role: createForm.role,
    });
    message.success(t('users.messages.created', { username: createForm.username.trim() }));
    createOpen.value = false;
    await load();
  } catch (e) {
    message.error(t('users.messages.createFailed', { msg: e.message }));
  } finally {
    saving.value = false;
  }
}

async function toggleRole(row) {
  const next = row.role === 'admin' ? 'user' : 'admin';
  try {
    await api.updateUser(row.username, { role: next });
    message.success(t('users.messages.roleChanged', { username: row.username, role: roleLabel(next) }));
    await load();
  } catch (e) {
    message.error(t('users.messages.updateFailed', { msg: e.message }));
  }
}

function openResetPassword(row) {
  pwTarget.value = row.username;
  pwValue.value = '';
  pwOpen.value = true;
}

async function doResetPassword() {
  saving.value = true;
  try {
    await api.updateUser(pwTarget.value, { password: pwValue.value });
    message.success(t('users.messages.pwReset', { username: pwTarget.value }));
    pwOpen.value = false;
  } catch (e) {
    message.error(t('users.messages.updateFailed', { msg: e.message }));
  } finally {
    saving.value = false;
  }
}

async function toggleDisabled(row) {
  const next = !row.disabled;
  try {
    await api.updateUser(row.username, { disabled: next });
    message.success(
      next
        ? t('users.messages.disabled', { username: row.username })
        : t('users.messages.enabled', { username: row.username }),
    );
    await load();
  } catch (e) {
    // 400 — the backend refuses to let an admin disable their own account.
    message.error(t('users.messages.updateFailed', { msg: e.message }));
  }
}

function confirmDelete(row) {
  dialog.warning({
    title: t('users.deleteConfirm.title'),
    content: t('users.deleteConfirm.body', { username: row.username }),
    positiveText: t('common.delete'),
    negativeText: t('common.cancel'),
    onPositiveClick: () => doDelete(row),
  });
}

async function doDelete(row) {
  try {
    await api.deleteUser(row.username);
    message.success(t('users.messages.deleted', { username: row.username }));
    await load();
  } catch (e) {
    // 400 — the backend refuses to let an admin delete their own account.
    message.error(t('users.messages.deleteFailed', { msg: e.message }));
  }
}

// -- Generate guest link --------------------------------------------------
async function openGuestLink() {
  guestForm.ttl = GUEST_TTL_DEFAULT;
  guestForm.scenario = null;
  guestForm.lang = null;
  guestForm.engine = null;
  guestForm.voice = null;
  guestForm.provider = null;
  guestResult.value = null;
  guestOpen.value = true;
  // Lazy-load the scenario selector from /api/config demos. The first entry
  // ({id:'default'}) is the "no demo" sentinel — we omit it so an empty
  // (cleared) selection means "no scenario pin", which the backend treats the
  // same as default. The SAME /api/config payload feeds the engine/lang/
  // provider/voice option lists (config.engines/languages/providers/
  // voices_by_provider/nova_sonic_voices). Failures are non-fatal: the modal
  // still mints (the selects just stay empty).
  if (scenarioOptions.value.length === 0 || !guestConfig.value) {
    scenarioLoading.value = true;
    guestCfgLoading.value = true;
    try {
      const cfg = await api.config();
      guestConfig.value = cfg;
      scenarioOptions.value = (cfg.demos || [])
        .filter((d) => d.kind !== 'default' && d.id !== 'default')
        .map((d) => ({ label: d.label || d.id, value: d.id }));
    } catch (e) {
      /* non-fatal — mint without a scenario pin / config-less selects */
    } finally {
      scenarioLoading.value = false;
      guestCfgLoading.value = false;
    }
  }
}

// On scenario pick, prefill lang/engine/voice/provider from that demo's DETAIL
// (GET /api/admin/demos/{id} — _demo_detail_with_tools exposes the stored
// engine/voice/provider/lang). Clearing the scenario blanks the four fields so
// "no scenario" → "no config override" (pure global default for the guest).
// Failures are non-fatal: the fields just stay as-is and remain editable.
async function onScenarioPick(scenarioId) {
  if (!scenarioId) {
    guestForm.lang = null;
    guestForm.engine = null;
    guestForm.voice = null;
    guestForm.provider = null;
    return;
  }
  guestDetailLoading.value = true;
  try {
    const detail = await api.demoDetail(scenarioId);
    const pre = guestPrefillFromDemo(detail);
    // Assign engine first so the lang/voice cross-filter watchers settle against
    // the right engine; absent keys reset to null (blank).
    guestForm.engine = pre.engine ?? null;
    guestForm.provider = pre.provider ?? null;
    guestForm.lang = pre.lang ?? null;
    guestForm.voice = pre.voice ?? null;
  } catch (e) {
    /* non-fatal — leave the fields blank/editable */
  } finally {
    guestDetailLoading.value = false;
  }
}

async function doGuestLink() {
  guestSaving.value = true;
  try {
    // Carry only the non-empty launch fields (token encodes everything; the
    // backend validates each and rejects impossible combos). An empty scenario
    // with no overrides → a pure global-default guest link, unchanged.
    const body = guestLinkBody(guestForm);
    const res = await api.createGuestLink(body);
    guestResult.value = {
      link: buildGuestLink(window.location.origin, res.token),
      expires_at: res.expires_at,
    };
  } catch (e) {
    message.error(t('users.guestLink.failed', { msg: e.message }));
  } finally {
    guestSaving.value = false;
  }
}

async function copyGuestLink() {
  try {
    await navigator.clipboard.writeText(guestResult.value.link);
    message.success(t('users.guestLink.copied'));
  } catch (e) {
    message.error(t('users.guestLink.copyFailed'));
  }
}

// Discard the minted link when the modal fully closes — never persisted.
function resetGuest() {
  guestResult.value = null;
  guestForm.scenario = null;
  guestForm.lang = null;
  guestForm.engine = null;
  guestForm.voice = null;
  guestForm.provider = null;
}

onMounted(load);
</script>
