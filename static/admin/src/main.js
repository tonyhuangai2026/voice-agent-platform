import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import { router } from './router/index.js';
import { i18n } from './i18n/index.js';
import { setUnauthorizedHandler } from './api.js';
import './styles/tokens.css';

// Centralised "session expired" handling: any /api/admin/* 401 bounces the
// user to the login page (the guard re-validates from there).
setUnauthorizedHandler(() => {
  if (router.currentRoute.value.name !== 'login') {
    router.push({ name: 'login' });
  }
});

const app = createApp(App);
app.use(createPinia());
app.use(router);
app.use(i18n);
app.mount('#app');
