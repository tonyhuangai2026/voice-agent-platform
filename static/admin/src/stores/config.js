import { defineStore } from 'pinia';
import { ref } from 'vue';
import { api } from '../api.js';

export const useConfigStore = defineStore('config', () => {
  const web = ref({});
  const phone = ref({});
  const options = ref(null);
  const loaded = ref(false);

  async function loadAll() {
    const [cfg, opts] = await Promise.all([api.getConfig(), api.options()]);
    web.value = cfg.web || {};
    phone.value = cfg.phone || {};
    options.value = opts;
    loaded.value = true;
  }

  async function saveWeb(updates) {
    const r = await api.putWeb(updates);
    web.value = r.web || web.value;
    return r;
  }

  async function savePhone(updates) {
    const r = await api.putPhone(updates);
    phone.value = r.phone || phone.value;
    return r;
  }

  return { web, phone, options, loaded, loadAll, saveWeb, savePhone };
});
