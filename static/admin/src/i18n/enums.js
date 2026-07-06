// enums.js — display-layer helpers that translate raw enum codes (the
// English constants we keep in DDB / API / CSV / MD) into the user's
// active locale.
//
// Why this exists: outcome / summary_status are "open enums" — the
// backend can grow new buckets faster than the front-end's i18n bundle.
// `i18n.global.te()` lets us fall back to the raw code when the key is
// missing, so the UI never shows a literal i18n key path.
//
// Export / API / CSV / MD writers MUST keep using the raw `row.outcome`
// /`row.summary_status` values; they are the schema contract with the
// backend. Only render-time should call these helpers.

import { i18n } from './index.js';

export function localOutcome(o) {
  if (!o) {
    const fallbackKey = 'history.enums.outcome.unknown';
    return i18n.global.te(fallbackKey) ? i18n.global.t(fallbackKey) : 'unknown';
  }
  const key = `history.enums.outcome.${o}`;
  return i18n.global.te(key) ? i18n.global.t(key) : o;
}

export function localSummaryStatus(s) {
  if (!s) {
    const fallbackKey = 'history.enums.summary.pending';
    return i18n.global.te(fallbackKey) ? i18n.global.t(fallbackKey) : 'pending';
  }
  const key = `history.enums.summary.${s}`;
  return i18n.global.te(key) ? i18n.global.t(key) : s;
}
