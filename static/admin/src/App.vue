<template>
  <n-config-provider
    :theme="darkMode ? darkTheme : null"
    :theme-overrides="darkMode ? darkThemeOverrides : themeOverrides"
    :locale="naiveLocale"
    :date-locale="naiveDateLocale"
  >
    <n-message-provider>
      <n-dialog-provider>
        <!-- Bare layout for the login page: no sider / header chrome. -->
        <router-view v-if="isLogin" />

        <n-layout v-else class="layout-root">
          <!-- Header -->
          <n-layout-header bordered class="header">
            <BrandLogo :title="t('app.brand')" :subtitle="t('app.sub')" />
            <n-space :size="12" align="center">
              <!-- Teleport target for per-view header actions (e.g. TalkView's
                   summarize / debug buttons merged from the demo SPA). -->
              <span id="page-actions" class="page-actions"></span>
              <StatChip :tone="health ? 'success' : 'error'">
                {{ health ? t('common.online') : t('common.offline') }}
              </StatChip>
              <LanguageSwitcher />
              <n-button
                quaternary
                circle
                @click="toggleTheme"
                :title="darkMode ? t('common.toggleLight') : t('common.toggleDark')"
              >
                <template #icon>
                  <n-icon :size="18" :component="darkMode ? Sun : Moon" />
                </template>
              </n-button>
              <!-- Current user + logout (tech_design §2). -->
              <n-dropdown
                v-if="me"
                trigger="click"
                :options="userMenuOptions"
                @select="onUserMenu"
              >
                <n-button quaternary>
                  <template #icon>
                    <n-icon :size="18" :component="UserAvatar" />
                  </template>
                  {{ me.username }}
                </n-button>
              </n-dropdown>
            </n-space>
          </n-layout-header>

          <n-layout has-sider class="body">
            <!-- Sider menu -->
            <n-layout-sider
              bordered
              :width="220"
              :native-scrollbar="false"
              class="sider"
            >
              <n-menu
                :value="route.name"
                :options="menuOptions"
                :collapsed-width="64"
                :indent="20"
                @update:value="onMenuClick"
              />
              <div class="sider-foot">
                <n-text depth="3" style="font-size: 11px;">
                  v0.1.0 · {{ new Date().getFullYear() }}
                </n-text>
              </div>
            </n-layout-sider>

            <!-- Content -->
            <n-layout :native-scrollbar="false" class="content">
              <router-view />
            </n-layout>
          </n-layout>
        </n-layout>
      </n-dialog-provider>
    </n-message-provider>
  </n-config-provider>
</template>

<script setup>
import { ref, computed, onMounted, watch, h } from 'vue';
import { useRoute, useRouter, RouterLink } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NLayout,
  NLayoutHeader,
  NLayoutSider,
  NMenu,
  NSpace,
  NButton,
  NIcon,
  NText,
  NDropdown,
  darkTheme,
  // Naive UI locale + date-locale exports — names cross-checked against
  // node_modules/naive-ui/es/locales/index.mjs (zhCN/enUS/jaJP/koKR/esAR/frFR
  // and dateZhCN/dateEnUS/dateJaJP/dateKoKR/dateEsAR/dateFrFR are all
  // present at the time of writing). Spanish / French only ship with the
  // esAR / frFR variants in 2.x; the UI message text is still standard
  // European Spanish / French — only date / number formatting follows the
  // -AR / -FR conventions, which is acceptable for this rollout.
  zhCN as nZhCN,
  zhTW as nZhTW,
  enUS as nEnUS,
  jaJP as nJaJP,
  koKR as nKoKR,
  esAR as nEsAR,
  frFR as nFrFR,
  dateZhCN,
  dateZhTW,
  dateEnUS,
  dateJaJP,
  dateKoKR,
  dateEsAR,
  dateFrFR,
} from 'naive-ui';
import {
  Dashboard,
  RecentlyViewed,
  Globe,
  PhoneVoice,
  Catalog,
  Plug,
  VolumeUp,
  Sun,
  Moon,
  UserAvatar,
  UserMultiple,
  Logout,
  Microphone,
  Headset,
  Time,
  Activity,
} from '@vicons/carbon';
import { api } from './api.js';
import { themeOverrides, darkThemeOverrides } from './theme.js';
import LanguageSwitcher from './components/LanguageSwitcher.vue';
import BrandLogo from './components/ui/BrandLogo.vue';
import StatChip from './components/ui/StatChip.vue';

// Map app i18n code -> [naive-ui locale, naive-ui date locale]. Kept in
// sync with src/i18n/index.js SUPPORTED_LOCALES.
const NAIVE_LOCALE_MAP = {
  'zh-CN': [nZhCN, dateZhCN],
  'zh-TW': [nZhTW, dateZhTW],
  en: [nEnUS, dateEnUS],
  ja: [nJaJP, dateJaJP],
  ko: [nKoKR, dateKoKR],
  es: [nEsAR, dateEsAR],
  fr: [nFrFR, dateFrFR],
};

const { t, locale } = useI18n();
const naiveLocale = computed(
  () => NAIVE_LOCALE_MAP[locale.value]?.[0] ?? nZhCN,
);
const naiveDateLocale = computed(
  () => NAIVE_LOCALE_MAP[locale.value]?.[1] ?? dateZhCN,
);

const route = useRoute();
const router = useRouter();

// Whether the current route is the standalone login page (renders without the
// sider/header chrome).
const isLogin = computed(() => route.name === 'login');

// Current session identity { username, role }, populated from /api/auth/me.
// Drives the top-right user menu; role gates menu items in T4.
const me = ref(null);
async function fetchMe() {
  try {
    me.value = await api.me();
  } catch {
    me.value = null;
  }
}

const userMenuOptions = computed(() => [
  {
    key: 'logout',
    label: t('app.user.logout'),
    icon: renderIcon(Logout),
  },
]);

async function onUserMenu(key) {
  if (key === 'logout') {
    try {
      await api.logout();
    } catch {
      /* logout is idempotent server-side; redirect regardless */
    }
    me.value = null;
    router.push({ name: 'login' });
  }
}

// Theme persistence
const darkMode = ref(localStorage.getItem('vb-admin-theme') === 'dark');

// Dark-mode activation contract (tech_design §0): keep the `dark` class on
// <html> in lock-step with the naive darkTheme prop so self-drawn components
// (BrandLogo / StatChip / MetricCard / EmptyState, charts, waveform) that read
// `html.dark { --vb-*: ... }` from styles/tokens.css follow dark mode too.
function applyDarkClass() {
  document.documentElement.classList.toggle('dark', darkMode.value);
}
// Init sync once from the persisted localStorage value (covers page reload).
applyDarkClass();

function toggleTheme() {
  darkMode.value = !darkMode.value;
  localStorage.setItem('vb-admin-theme', darkMode.value ? 'dark' : 'light');
  applyDarkClass();
}

// Render a carbon icon as a naive <n-icon> for use in the menu `icon` slot.
function renderIcon(component) {
  return () => h(NIcon, null, { default: () => h(component) });
}

// Whether the current session is an admin. Drives role-based menu rendering
// (tech_design §4): a normal user (role==='user', or no session yet) sees only
// the Call group; an admin additionally sees the full Admin group. The backend
// independently enforces require_admin on every admin route, so this is the
// frontend half of a double layer — never the sole gate.
const isAdmin = computed(() => me.value?.role === 'admin');

// A temporary guest session (tech_design §3.2) is confined to Talk: no My
// History, no Monitor, no admin group. isAdmin stays false for a guest, so the
// admin layer is unaffected; this is a separate, more-restrictive branch.
const isGuest = computed(() => me.value?.role === 'guest');

// Menu options are a `computed` so labels re-render reactively when the
// active locale flips (RouterLink children + group labels read from t() at
// render time) AND when `me`/role resolves. Items are grouped into a Call
// section (everyone) and an Admin section (admin only).
const menuOptions = computed(() => {
  // Guest session (tech_design §3.2): a Talk-ONLY menu — no My History, no
  // Monitor, no admin group. Returned before the normal call/admin groups so a
  // guest can never see another entry even if role gating elsewhere regressed.
  if (isGuest.value) {
    return [
      {
        type: 'group',
        key: 'grp-call',
        label: () => t('app.nav.groupCall'),
        children: [
          {
            key: 'talk',
            label: () => h(RouterLink, { to: '/talk' }, () => t('app.nav.talk')),
            icon: renderIcon(Microphone),
          },
        ],
      },
    ];
  }

  // Call group — available to every authenticated user. Monitor (listening to
  // others' live calls) is an admin-only action server-side, so it is gated
  // into the admin view rather than shown to normal users.
  const callGroup = {
    type: 'group',
    key: 'grp-call',
    label: () => t('app.nav.groupCall'),
    children: [
      {
        key: 'talk',
        label: () => h(RouterLink, { to: '/talk' }, () => t('app.nav.talk')),
        icon: renderIcon(Microphone),
      },
      {
        key: 'my-history',
        label: () => h(RouterLink, { to: '/my-history' }, () => t('app.nav.myHistory')),
        icon: renderIcon(Time),
      },
    ],
  };

  if (!isAdmin.value) return [callGroup];

  // Admins also get Monitor in the Call group, plus the full Admin group.
  callGroup.children.splice(1, 0, {
    key: 'monitor',
    label: () => h(RouterLink, { to: '/monitor' }, () => t('app.nav.monitor')),
    icon: renderIcon(Headset),
  });

  const adminGroup = {
    type: 'group',
    key: 'grp-admin',
    label: () => t('app.nav.groupAdmin'),
    children: [
      {
        key: 'dashboard',
        label: () => h(RouterLink, { to: '/dashboard' }, () => t('app.nav.dashboard')),
        icon: renderIcon(Dashboard),
      },
      {
        key: 'history',
        label: () => h(RouterLink, { to: '/history' }, () => t('app.nav.history')),
        icon: renderIcon(RecentlyViewed),
      },
      {
        key: 'activity',
        label: () => h(RouterLink, { to: '/activity' }, () => t('app.nav.activity')),
        icon: renderIcon(Activity),
      },
      {
        key: 'demos',
        label: () => h(RouterLink, { to: '/demos' }, () => t('app.nav.demos')),
        icon: renderIcon(Catalog),
      },
      {
        key: 'mcp',
        label: () => h(RouterLink, { to: '/mcp-servers' }, () => t('app.nav.mcp')),
        icon: renderIcon(Plug),
      },
      {
        key: 'voices',
        label: () => h(RouterLink, { to: '/voices' }, () => t('app.nav.voices')),
        icon: renderIcon(VolumeUp),
      },
      {
        key: 'web',
        label: () => h(RouterLink, { to: '/web' }, () => t('app.nav.web')),
        icon: renderIcon(Globe),
      },
      {
        key: 'phone',
        label: () => h(RouterLink, { to: '/phone' }, () => t('app.nav.phone')),
        icon: renderIcon(PhoneVoice),
      },
      {
        key: 'users',
        label: () => h(RouterLink, { to: '/users' }, () => t('app.nav.users')),
        icon: renderIcon(UserMultiple),
      },
    ],
  };

  return [callGroup, adminGroup];
});

function onMenuClick(key) {
  if (route.name !== key) router.push({ name: key });
}

const health = ref(false);
async function poll() {
  try {
    await api.health();
    health.value = true;
  } catch {
    health.value = false;
  }
}

onMounted(() => {
  poll();
  setInterval(poll, 30000);
  fetchMe();
});

// Re-fetch identity whenever we land on an authenticated route (e.g. right
// after a successful login navigates away from /login).
watch(
  () => route.name,
  (name) => {
    if (name && name !== 'login' && !me.value) fetchMe();
  },
);
</script>

<style>
:root {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'PingFang SC', 'Microsoft YaHei', sans-serif;
}

html, body, #app {
  height: 100%;
  margin: 0;
}

.layout-root {
  height: 100vh;
}

.header {
  height: 64px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 var(--vb-space-xl);
}

.body {
  height: calc(100vh - 64px);
}

.sider {
  display: flex;
  flex-direction: column;
  padding-top: var(--vb-space-sm);
}

.sider-foot {
  margin-top: auto;
  padding: var(--vb-space-lg);
  text-align: center;
  border-top: 1px solid var(--vb-border);
}

.content {
  padding: var(--vb-space-xl);
}

/* Teleport target for per-view header actions (TalkView). */
.page-actions {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
</style>
