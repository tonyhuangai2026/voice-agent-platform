// T4: the demo-detail drawer's "高级/Advanced" group was flattened — filler /
// asr-filter / engine-voice / translate are now top-level tabs, and the
// `demos.detail.groups.advanced` i18n key was removed from every locale.
//
// A full DemosView mount needs the whole naive-ui + session + API surface
// mocked, which would be brittle. Instead we assert the two concrete,
// machine-checkable artifacts of the flatten:
//   1. No locale still defines `demos.detail.groups.advanced` (no dangling key).
//   2. The DemosView source no longer renders a `name="g-advanced"` tab pane,
//      and the four formerly-nested tabs are still present as panes.

import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, resolve } from 'node:path';

import en from '../i18n/locales/en.js';
import zhCN from '../i18n/locales/zh-CN.js';
import zhTW from '../i18n/locales/zh-TW.js';
import ja from '../i18n/locales/ja.js';
import ko from '../i18n/locales/ko.js';
import fr from '../i18n/locales/fr.js';
import es from '../i18n/locales/es.js';

const LOCALES = { en, 'zh-CN': zhCN, 'zh-TW': zhTW, ja, ko, fr, es };

describe('T4 — advanced group flattened', () => {
  it('no locale defines demos.detail.groups.advanced (dangling key removed)', () => {
    for (const [name, mod] of Object.entries(LOCALES)) {
      const groups = mod?.demos?.detail?.groups || {};
      expect(groups, `${name} groups`).not.toHaveProperty('advanced');
      // the surviving group keys are still present
      expect(groups).toHaveProperty('info');
      expect(groups).toHaveProperty('tools');
    }
  });

  it('DemosView no longer renders a g-advanced tab; the 4 tabs are top-level', () => {
    const here = dirname(fileURLToPath(import.meta.url));
    const src = readFileSync(resolve(here, '../views/DemosView.vue'), 'utf8');
    expect(src).not.toContain('name="g-advanced"');
    expect(src).not.toContain("groups.advanced");
    for (const tab of ['filler', 'asr-filter', 'engine-voice', 'translate']) {
      expect(src, `tab ${tab} still present`).toContain(`name="${tab}"`);
    }
  });
});
