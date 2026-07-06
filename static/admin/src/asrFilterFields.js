// Pure prime/save mapping for the per-demo ASR-filter editor (DemosView 高级
// group). DOM-free so it can be unit-tested without mounting the component —
// the same way the filler editor's prime/save is structured inline, but
// extracted here so T2's mapping is covered by a vitest spec.
//
// Config contract (tech_design §2/§7, T1 PATCH): the demo's `asr_filter` block
// is { enabled, min_confidence, max_chars, max_words } — the STORED config /
// UI key names (NOT the filter ctor's max_cjk_chars/max_latin_words; the
// backend resolver does that name-mapping). The editor only ever reads/writes
// these four UI-managed fields.

// Built-in defaults shown when a demo has no asr_filter block. Mirrors the env
// defaults the backend resolver falls back to (ASR_FILTER_* — off / 0.5 / 4 / 1)
// so an unconfigured demo's form reflects the effective default. On save we
// always send concrete values (matching how the filler editor always PATCHes a
// concrete enabled boolean rather than an unset/tri-state).
export const ASR_FILTER_DEFAULTS = Object.freeze({
  enabled: false,
  min_confidence: 0.5,
  max_chars: 4,
  max_words: 1,
});

// Seed the reactive form from the demo detail's `asr_filter` block. Each
// subfield falls back to its default when absent/wrong-typed, so a partial
// block still shows sensible values. Returns a plain object the caller assigns
// onto its reactive form; also returns `configured` (true when the demo
// actually carries an asr_filter dict) to drive the "inherits global/default
// when unconfigured" hint — same role as fillerConfigured.
export function primeAsrFilterForm(asrFilter) {
  const f = asrFilter && typeof asrFilter === 'object' && !Array.isArray(asrFilter) ? asrFilter : {};
  const configured = asrFilter != null && typeof asrFilter === 'object' && !Array.isArray(asrFilter);
  return {
    configured,
    form: {
      enabled: typeof f.enabled === 'boolean' ? f.enabled : ASR_FILTER_DEFAULTS.enabled,
      min_confidence:
        typeof f.min_confidence === 'number' ? f.min_confidence : ASR_FILTER_DEFAULTS.min_confidence,
      max_chars: typeof f.max_chars === 'number' ? f.max_chars : ASR_FILTER_DEFAULTS.max_chars,
      max_words: typeof f.max_words === 'number' ? f.max_words : ASR_FILTER_DEFAULTS.max_words,
    },
  };
}

// Build the PATCH body's asr_filter sub-block from the current form. Sends only
// the four UI-managed fields (like saveFiller sends only its triple) — the
// backend partial-merges, so omitting a field leaves it untouched, but the UI
// owns all four so it always emits all four.
export function buildAsrFilterPatch(form) {
  const f = form || {};
  return {
    enabled: f.enabled,
    min_confidence: f.min_confidence,
    max_chars: f.max_chars,
    max_words: f.max_words,
  };
}
