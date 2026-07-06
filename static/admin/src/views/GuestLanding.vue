<template>
  <!-- Public landing for a temporary guest link (tech_design §3.1). Renders a
       bare centered card — App.vue treats this like /login (no sider/header)
       only if isLogin; here we are inside the layout shell, but the view is
       self-contained and short-lived (it redirects on success). -->
  <div class="guest-landing">
    <n-card style="max-width: 420px; width: 92vw;" :bordered="true">
      <n-space vertical align="center" :size="16" style="padding: 24px 8px;">
        <template v-if="state !== 'failed'">
          <n-spin size="large" />
          <n-text>{{ stateMessage }}</n-text>
        </template>
        <template v-else>
          <n-icon :size="40" :component="WarningAlt" style="color: var(--vb-error, #d03050);" />
          <n-text style="text-align: center;">{{ stateMessage }}</n-text>
        </template>
      </n-space>
    </n-card>
  </div>
</template>

<script setup>
import { onMounted, ref, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import { NCard, NSpace, NSpin, NText, NIcon } from 'naive-ui';
import { WarningAlt } from '@vicons/carbon';
import { api } from '../api.js';
import { guestLaunchQuery } from '../talkConfig.js';

const { t } = useI18n();
const route = useRoute();
const router = useRouter();

// 'validating' | 'redirecting' | 'failed'
const state = ref('validating');

const stateMessage = computed(() => {
  if (state.value === 'failed') return t('guest.failed');
  if (state.value === 'redirecting') return t('guest.redirecting');
  return t('guest.validating');
});

onMounted(async () => {
  // Hash-history exposes the query on route.query (e.g. /#/guest?token=…).
  const token = route.query.token;
  if (!token) {
    state.value = 'failed';
    return;
  }
  try {
    const res = await api.guestLogin({ token });
    state.value = 'redirecting';
    // Forward the full launch set the link carried (scenario + lang/engine/
    // voice/provider, any subset) into the existing Talk launch-query path
    // TalkView already supports (seedPrevFromLaunch seeds the chips/selectors,
    // mergeDemoFirst drives the real /ws call). The guest then experiences the
    // admin's configured variant, not global defaults. An old scenario-only
    // token still yields just {scenario}; a bare link → undefined query.
    // replace() drops the token-bearing URL from history so it can't be
    // re-shared / back-nav'd.
    const query = guestLaunchQuery(res);
    router.replace({ name: 'talk', query });
  } catch (e) {
    state.value = 'failed';
  }
});
</script>

<style scoped>
.guest-landing {
  display: flex;
  align-items: center;
  justify-content: center;
  min-height: 60vh;
}
</style>
