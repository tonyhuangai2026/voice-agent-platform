// Pure helpers for the global ASR hallucination-filter card on the
// Web/Phone defaults form (DefaultsForm.vue, tech_design §7). DOM-free so the
// config<->PUT-body mapping is unit-testable without mounting the component
// (same convention as voiceFields.js / talkConfig.js).
//
// The stored / config / PUT-body key names are the FOUR sub-keys the backend
// reads (bot.py _validate_asr_filter_patch / GET /api/admin/config):
//   enabled (bool) · min_confidence (0..1 float) · max_chars (int >=0) ·
//   max_words (int >=0)
// GET /api/admin/config returns { web: {...,asr_filter?}, phone: {...,asr_filter?} };
// PUT /api/admin/config/{web,phone} accepts { asr_filter: { ...subset } } and
// read-merge-writes the sub-block, so sending the full four-key object is safe.

// Defaults mirror the backend's built-in / env fallbacks (OFF, 0.5, 4, 1 —
// bot.py _resolve_asr_filter). Used when a segment has no stored asr_filter yet
// so the card shows the same values a live call would resolve to.
export const ASR_FILTER_DEFAULTS = Object.freeze({
  enabled: false,
  min_confidence: 0.5,
  max_chars: 4,
  max_words: 1,
});

// Load: pull the asr_filter sub-block out of a stored segment object
// (store.web / store.phone, i.e. one half of GET /api/admin/config) into the
// flat form values the card binds to. Missing block / missing keys fall back to
// ASR_FILTER_DEFAULTS so the n-input-numbers never bind to undefined.
export function asrFilterFromConfig(segment) {
  const af = (segment && segment.asr_filter) || {};
  return {
    enabled: typeof af.enabled === 'boolean' ? af.enabled : ASR_FILTER_DEFAULTS.enabled,
    min_confidence:
      typeof af.min_confidence === 'number'
        ? af.min_confidence
        : ASR_FILTER_DEFAULTS.min_confidence,
    max_chars: typeof af.max_chars === 'number' ? af.max_chars : ASR_FILTER_DEFAULTS.max_chars,
    max_words: typeof af.max_words === 'number' ? af.max_words : ASR_FILTER_DEFAULTS.max_words,
  };
}

// Save: build the { enabled, min_confidence, max_chars, max_words } block to
// nest under `asr_filter` in the PUT body. Coerces to the backend's expected
// types (bool / float / int / int) so the n-input-number values (which may be
// null when blanked) are normalised back to safe numbers before they leave the
// browser. The backend read-merge-writes the sub-block, so emitting all four
// keys is intentional (never clobbers siblings — there are none beyond these).
export function asrFilterPutBlock(values) {
  const v = values || {};
  // A blanked n-input-number yields null/undefined (or '') — fall back to the
  // field default rather than coercing to 0 (Number(null) === 0). An explicit
  // numeric 0 is preserved (it is a valid threshold / count).
  const num = (x, fallback) => {
    if (x === null || x === undefined || x === '') return fallback;
    const n = Number(x);
    return Number.isFinite(n) ? n : fallback;
  };
  return {
    enabled: Boolean(v.enabled),
    min_confidence: num(v.min_confidence, ASR_FILTER_DEFAULTS.min_confidence),
    max_chars: Math.trunc(num(v.max_chars, ASR_FILTER_DEFAULTS.max_chars)),
    max_words: Math.trunc(num(v.max_words, ASR_FILTER_DEFAULTS.max_words)),
  };
}

// True when the card's current values differ from what was loaded — lets the
// form include `asr_filter` in the PUT body only when the user actually touched
// it (matching the form's existing "diff against snapshot" save behaviour).
export function asrFilterChanged(current, snapshot) {
  const a = asrFilterPutBlock(current);
  const b = asrFilterPutBlock(snapshot);
  return (
    a.enabled !== b.enabled ||
    a.min_confidence !== b.min_confidence ||
    a.max_chars !== b.max_chars ||
    a.max_words !== b.max_words
  );
}
