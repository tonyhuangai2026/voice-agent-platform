<!--
  SetupView — first-run admin bootstrap for the merged single-page admin SPA.

  Shown only when the deploy is uninitialized (GET /api/auth/setup-status →
  needs_setup=true; the router guard force-routes here). POSTs
  {username, password} to /api/auth/setup which creates the first admin AND
  auto-logs the caller in (sets the HttpOnly vb_session cookie server-side), so
  on success we go straight to '/'. The backend is self-closing: a 409 means
  someone already initialized → bounce to /login; a 400 means empty/weak input
  → inline error. Mirrors LoginView's structure / shared --vb-* tokens so it
  follows dark mode like the rest of the app.
-->
<template>
  <div class="setup-root">
    <n-card class="setup-card" :bordered="true">
      <div class="setup-head">
        <BrandLogo :title="t('app.brand')" :subtitle="t('setup.subtitle')" />
      </div>

      <p class="setup-intro">{{ t('setup.intro') }}</p>

      <n-form ref="formRef" :model="model" :rules="rules" @submit.prevent="onSubmit">
        <n-form-item path="username" :label="t('setup.username')">
          <n-input
            v-model:value="model.username"
            :placeholder="t('setup.usernamePlaceholder')"
            :input-props="{ autocomplete: 'username' }"
            @keyup.enter="onSubmit"
          />
        </n-form-item>
        <n-form-item path="password" :label="t('setup.password')">
          <n-input
            v-model:value="model.password"
            type="password"
            show-password-on="click"
            :placeholder="t('setup.passwordPlaceholder')"
            :input-props="{ autocomplete: 'new-password' }"
            @keyup.enter="onSubmit"
          />
        </n-form-item>
        <n-form-item path="confirm" :label="t('setup.confirm')">
          <n-input
            v-model:value="model.confirm"
            type="password"
            show-password-on="click"
            :placeholder="t('setup.confirmPlaceholder')"
            :input-props="{ autocomplete: 'new-password' }"
            @keyup.enter="onSubmit"
          />
        </n-form-item>

        <n-alert
          v-if="errorMsg"
          type="error"
          :show-icon="true"
          class="setup-error"
        >
          {{ errorMsg }}
        </n-alert>

        <n-button
          type="primary"
          block
          :loading="loading"
          attr-type="submit"
          class="setup-submit"
          @click="onSubmit"
        >
          {{ t('setup.submit') }}
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue';
import { useRouter } from 'vue-router';
import { useI18n } from 'vue-i18n';
import {
  NCard,
  NForm,
  NFormItem,
  NInput,
  NButton,
  NAlert,
} from 'naive-ui';
import { api } from '../api.js';
import BrandLogo from '../components/ui/BrandLogo.vue';

const { t } = useI18n();
const router = useRouter();

const formRef = ref(null);
const model = reactive({ username: '', password: '', confirm: '' });
const loading = ref(false);
const errorMsg = ref('');

const rules = {
  username: { required: true, message: () => t('setup.errors.usernameRequired'), trigger: ['blur', 'input'] },
  password: { required: true, message: () => t('setup.errors.passwordRequired'), trigger: ['blur', 'input'] },
  confirm: {
    // Client-side "passwords match" check. The required-ness is covered by the
    // mismatch message too (empty confirm never equals a non-empty password).
    validator: (_rule, value) => value === model.password,
    message: () => t('setup.errors.passwordsMismatch'),
    trigger: ['blur', 'input'],
  },
};

async function onSubmit() {
  errorMsg.value = '';
  try {
    await formRef.value?.validate();
  } catch {
    return; // field-level validation errors are already shown inline
  }
  loading.value = true;
  try {
    await api.setup({ username: model.username.trim(), password: model.password });
    // Backend already issued the session cookie (auto-login) — go straight in.
    router.replace('/');
  } catch (e) {
    if (e?.status === 409) {
      // Someone else completed setup first (self-closing endpoint). Send the
      // user to the normal login page.
      errorMsg.value = t('setup.errors.alreadyInitialized');
      router.replace('/login');
    } else if (e?.status === 400) {
      errorMsg.value = t('setup.errors.invalidInput');
    } else {
      errorMsg.value = t('setup.errors.generic', { msg: e?.message || '' });
    }
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.setup-root {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--vb-space-xl);
  background: var(--vb-bg);
}

.setup-card {
  width: 100%;
  max-width: 380px;
}

.setup-head {
  display: flex;
  justify-content: center;
  margin-bottom: var(--vb-space-xl);
}

.setup-intro {
  margin: 0 0 var(--vb-space-lg);
  color: var(--vb-text-muted, inherit);
  font-size: 13px;
  line-height: 1.5;
  text-align: center;
}

.setup-error {
  margin-bottom: var(--vb-space-md);
}

.setup-submit {
  margin-top: var(--vb-space-sm);
}
</style>
