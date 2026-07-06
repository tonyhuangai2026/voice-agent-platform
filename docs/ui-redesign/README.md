# UI Redesign — T6 verification evidence

Product-level visual verification for the demo + admin SPA redesign
(proposal `5eb4bf79`, tech_design §6). Captured headless, no live backend.

## Build

The admin SPA builds green (`npm run build`):

- `static/admin` — vite, ~7.2s, only the expected `chunk > 500 kB` advisory.

(The standalone demo SPA was removed in the single-page merge; its call views
now live inside the admin SPA.)

## i18n full-coverage

`node docs/ui-redesign/check-i18n-coverage.mjs` — PASS.

- demo: 91 referenced static `t()` keys resolve in all 7 locales
  (en/es/fr/ja/ko/zh-CN/zh-TW); 110 keys/locale; no cross-locale drift.
- admin: 204 referenced static `t()` keys resolve in all 7 locales
  (en/zh-CN/zh-TW/ja/ko/es/fr); 226 keys/locale; no cross-locale drift.
- Dynamic `t()` sites are reported, not silently passed: demo `App.vue`
  `t(r.labelKey)` resolves to static nav keys; admin `i18n/enums.js` uses
  `te()`-guarded keys with raw-code fallback by design.

## Screenshots (light + dark)

Captured with `docs/ui-redesign/screenshot-harness.mjs`: each built `dist/`
is served over `http.server` with a `<head>`-injected script that (a) sets the
SPA dark-mode `localStorage` key so the real `App.vue` boot path applies
`<html class="dark">`, and (b) stubs `window.fetch` for `/api/*` with mock JSON
so pages render populated. **Mock data only — no fabricated pixels.** Dark shots
exercise the BLOCKER-1 guard: self-drawn components (SVG charts, waveform area,
MetricCard/StatChip/EmptyState/BrandLogo) must read `html.dark { --vb-* }`.

| Page | Light | Dark |
|------|-------|------|
| demo TalkView (idle) | `demo-talkview-idle-light.png` | `demo-talkview-idle-dark.png` |
| demo HistoryView | `demo-historyview-light.png` | `demo-historyview-dark.png` |
| admin DashboardView (charts) | `admin-dashboard-light.png` | `admin-dashboard-dark.png` |
| admin DemosView | `admin-demos-light.png` | `admin-demos-dark.png` |

Mean-luminance sanity (sampled 3×3 grid): light ≈ 252–254, dark ≈ 33–37.

TalkView is captured in **idle** state: the recording waveform needs a live mic
(`getUserMedia`), which is unavailable headless, so the idle button + idle
conversation panel are shown. Both are self-drawn and confirmed dark in the dark
shot. HistoryView/Demos/Dashboard render fully populated from mock data; the
History detail pane needs a click (not possible in single-shot headless), so it
shows the dark `EmptyState`.

## BLOCKER-1 regression found + fixed during verification

The dark screenshots initially showed a real regression: self-drawn components
(`--vb-*`) went dark correctly, but **naive-ui components (cards, tables,
inputs, sider, header) stayed light-on-dark** — confirmed via CDP that
`getComputedStyle(.n-card).backgroundColor === rgb(255,255,255)` even with
`<html class="dark">` and `darkMode === true`.

Root cause: `theme.js` exported a single static `themeOverrides` bound to
`<n-config-provider :theme-overrides>` for **both** light and dark naive base
themes. Its `common` block hardcoded light surfaces/text
(`cardColor/modalColor/tableColor/inputColor/bodyColor` = white/grey,
`textColorBase` = dark ink) plus `Card.color`/`DataTable.thColor`, so naive
rendered light surfaces in dark mode.

Fix (theme.js, byte-identical in both SPAs; App.vue in both SPAs):
- split mode-agnostic overrides (`baseOverrides`: brand/semantic/radius/type)
  from mode-specific surface/text overrides;
- add `darkThemeOverrides` (dark surfaces + light text, mirroring the
  `html.dark` palette in `styles/tokens.css`);
- bind `:theme-overrides="darkMode ? darkThemeOverrides : themeOverrides"`.

After the fix, dark shots are fully coherent (naive + self-drawn both dark) and
light shots are unchanged.

## Re-run

```bash
cd static/admin && npm run build && cd ../..
node docs/ui-redesign/check-i18n-coverage.mjs
node docs/ui-redesign/screenshot-harness.mjs   # needs snap chromium
```
