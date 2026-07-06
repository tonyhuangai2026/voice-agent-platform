// vue-i18n setup for the admin SPA.
//
// - createI18n in Composition API mode (legacy:false) so it plays well with
//   Vue 3.5 <script setup>.
// - Seven supported locales: zh-CN (default / source of truth), zh-TW
//   (繁體中文 — 台灣用語), en, ja, ko, es, fr.
// - detectLocale() prefers an explicit user choice persisted in
//   localStorage['app.lang']; otherwise it picks based on
//   navigator.language with a sensible prefix-fallback (e.g. ja-JP -> ja,
//   zh-HK / zh-MO -> zh-TW, other zh-* -> zh-CN). Anything unmatched
//   falls back to zh-CN.
// - setLocale(code) flips the runtime locale, persists the choice, and
//   updates <html lang=...>.
//
// T1 only ships infrastructure + the zh-CN message bundle. T3 will replace
// the hard-coded strings in App.vue / views/* with t() calls; T5 will fill
// in the remaining five locale bundles.

import { createI18n } from 'vue-i18n';
import zhCN from './locales/zh-CN.js';
import zhTW from './locales/zh-TW.js';
import en from './locales/en.js';
import ja from './locales/ja.js';
import ko from './locales/ko.js';
import es from './locales/es.js';
import fr from './locales/fr.js';

export const SUPPORTED_LOCALES = [
  { code: 'zh-CN', label: '简体中文' },
  { code: 'zh-TW', label: '繁體中文' },
  { code: 'en', label: 'English' },
  { code: 'ja', label: '日本語' },
  { code: 'ko', label: '한국어' },
  { code: 'es', label: 'Español' },
  { code: 'fr', label: 'Français' },
];

const STORAGE_KEY = 'app.lang';
const DEFAULT_LOCALE = 'zh-CN';

export function detectLocale() {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved && SUPPORTED_LOCALES.some((l) => l.code === saved)) return saved;
  } catch {
    // localStorage may be unavailable (private mode, ssr, etc.) — fall
    // through to navigator-based detection.
  }
  const nav = ((typeof navigator !== 'undefined' && navigator.language) || '').toLowerCase();
  if (!nav) return DEFAULT_LOCALE;
  // Exact match first (e.g. zh-CN).
  const exact = SUPPORTED_LOCALES.find((l) => l.code.toLowerCase() === nav);
  if (exact) return exact.code;
  // Prefix match (ja-JP -> ja). For Chinese variants, route Taiwan / Hong
  // Kong / Macau navigator strings to zh-TW; everything else (zh-CN, zh-SG,
  // bare 'zh', etc.) lands on zh-CN.
  const prefix = nav.split('-')[0];
  if (prefix === 'zh') {
    if (nav === 'zh-tw' || nav === 'zh-hk' || nav === 'zh-mo') return 'zh-TW';
    return 'zh-CN';
  }
  const byPrefix = SUPPORTED_LOCALES.find(
    (l) => l.code.toLowerCase().split('-')[0] === prefix,
  );
  return byPrefix ? byPrefix.code : DEFAULT_LOCALE;
}

export const i18n = createI18n({
  legacy: false,
  globalInjection: true,
  locale: detectLocale(),
  fallbackLocale: DEFAULT_LOCALE,
  // Silence the noisy "Not found 'xxx' key" warnings for now: T3/T5 are
  // landing key replacements in stages and the default fallback to zh-CN
  // already covers the user-visible UX.
  missingWarn: false,
  fallbackWarn: false,
  messages: {
    'zh-CN': zhCN,
    'zh-TW': zhTW,
    en,
    ja,
    ko,
    es,
    fr,
  },
});

export function setLocale(code) {
  if (!SUPPORTED_LOCALES.some((l) => l.code === code)) return;
  i18n.global.locale.value = code;
  try {
    localStorage.setItem(STORAGE_KEY, code);
  } catch {
    /* storage unavailable — the runtime switch still applies for this tab */
  }
  if (typeof document !== 'undefined' && document.documentElement) {
    document.documentElement.setAttribute('lang', code);
  }
}

// Apply <html lang=...> on first load so the very first paint also reflects
// the active locale (helps with screen readers and Naive UI initial render).
if (typeof document !== 'undefined' && document.documentElement) {
  document.documentElement.setAttribute('lang', i18n.global.locale.value);
}
