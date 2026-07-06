<!--
  LoginView — credential form for the merged single-page admin SPA.

  POSTs {username, password} to /api/auth/login (sets the HttpOnly vb_session
  cookie server-side). On success the router guard lets the user through; we
  redirect to ?redirect= (if present) or the home page. A 401 surfaces an
  inline error. Styled with the shared --vb-* tokens + Naive UI so it follows
  dark mode like the rest of the app.
-->
<template>
  <div class="login-root">
    <n-card class="login-card" :bordered="true">
      <div class="login-head">
        <BrandLogo :title="t('app.brand')" :subtitle="t('login.subtitle')" />
      </div>

      <n-form ref="formRef" :model="model" :rules="rules" @submit.prevent="onSubmit">
        <n-form-item path="username" :label="t('login.username')">
          <n-input
            v-model:value="model.username"
            :placeholder="t('login.usernamePlaceholder')"
            :input-props="{ autocomplete: 'username' }"
            @keyup.enter="onSubmit"
          />
        </n-form-item>
        <n-form-item path="password" :label="t('login.password')">
          <n-input
            v-model:value="model.password"
            type="password"
            show-password-on="click"
            :placeholder="t('login.passwordPlaceholder')"
            :input-props="{ autocomplete: 'current-password' }"
            @keyup.enter="onSubmit"
          />
        </n-form-item>

        <n-alert
          v-if="errorMsg"
          type="error"
          :show-icon="true"
          class="login-error"
        >
          {{ errorMsg }}
        </n-alert>

        <n-button
          type="primary"
          block
          :loading="loading"
          attr-type="submit"
          class="login-submit"
          @click="onSubmit"
        >
          {{ t('login.submit') }}
        </n-button>
      </n-form>
    </n-card>
  </div>
</template>

<script setup>
import { ref, reactive } from 'vue';
import { useRoute, useRouter } from 'vue-router';
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
const route = useRoute();
const router = useRouter();

const formRef = ref(null);
const model = reactive({ username: '', password: '' });
const loading = ref(false);
const errorMsg = ref('');

const rules = {
  username: { required: true, message: () => t('login.errors.usernameRequired'), trigger: ['blur', 'input'] },
  password: { required: true, message: () => t('login.errors.passwordRequired'), trigger: ['blur', 'input'] },
};

async function onSubmit() {
  errorMsg.value = '';
  try {
    await formRef.value?.validate();
  } catch {
    return; // validation errors already shown on the fields
  }
  loading.value = true;
  try {
    await api.login(model.username.trim(), model.password);
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/';
    router.replace(redirect);
  } catch (e) {
    errorMsg.value =
      e?.status === 401 ? t('login.errors.invalidCredentials') : t('login.errors.generic', { msg: e?.message || '' });
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.login-root {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: var(--vb-space-xl);
  background: var(--vb-bg);
}

.login-card {
  width: 100%;
  max-width: 380px;
}

.login-head {
  display: flex;
  justify-content: center;
  margin-bottom: var(--vb-space-xl);
}

.login-error {
  margin-bottom: var(--vb-space-md);
}

.login-submit {
  margin-top: var(--vb-space-sm);
}
</style>
