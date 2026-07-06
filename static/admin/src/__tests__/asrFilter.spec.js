import { describe, it, expect } from 'vitest';
import {
  ASR_FILTER_DEFAULTS,
  asrFilterFromConfig,
  asrFilterPutBlock,
  asrFilterChanged,
} from '../asrFilter.js';

// Pure-helper unit tests for the global ASR-filter card on DefaultsForm.vue
// (tech_design §7). DOM-free — no mount. Covers the config<->PUT-body mapping
// the card keys off: load from GET /api/admin/config's segment.asr_filter and
// build the { asr_filter: {...} } PUT block. The four sub-keys are exactly what
// the backend reads/writes (bot.py _validate_asr_filter_patch):
// enabled / min_confidence / max_chars / max_words.

describe('ASR_FILTER_DEFAULTS — mirrors the backend OFF/built-in fallbacks', () => {
  it('is OFF with the same thresholds _resolve_asr_filter falls back to', () => {
    expect(ASR_FILTER_DEFAULTS).toEqual({
      enabled: false,
      min_confidence: 0.5,
      max_chars: 4,
      max_words: 1,
    });
  });
});

describe('asrFilterFromConfig — load segment.asr_filter into form values', () => {
  it('reads a fully-populated stored block verbatim', () => {
    const seg = { engine: 'pipeline', asr_filter: { enabled: true, min_confidence: 0.8, max_chars: 6, max_words: 2 } };
    expect(asrFilterFromConfig(seg)).toEqual({
      enabled: true,
      min_confidence: 0.8,
      max_chars: 6,
      max_words: 2,
    });
  });

  it('a segment with NO asr_filter → defaults (card shows the resolved OFF state)', () => {
    expect(asrFilterFromConfig({ engine: 'pipeline' })).toEqual(ASR_FILTER_DEFAULTS);
  });

  it('null / undefined segment → defaults (no throw)', () => {
    expect(asrFilterFromConfig(undefined)).toEqual(ASR_FILTER_DEFAULTS);
    expect(asrFilterFromConfig(null)).toEqual(ASR_FILTER_DEFAULTS);
  });

  it('partial stored block → present keys kept, missing keys defaulted', () => {
    expect(asrFilterFromConfig({ asr_filter: { enabled: true } })).toEqual({
      enabled: true,
      min_confidence: 0.5,
      max_chars: 4,
      max_words: 1,
    });
    expect(asrFilterFromConfig({ asr_filter: { max_chars: 0 } })).toEqual({
      enabled: false,
      min_confidence: 0.5,
      max_chars: 0, // 0 is a valid stored value, not treated as "missing"
      max_words: 1,
    });
  });

  it('ignores non-typed junk in the stored block (defensive)', () => {
    const seg = { asr_filter: { enabled: 'yes', min_confidence: 'high', max_chars: null } };
    expect(asrFilterFromConfig(seg)).toEqual(ASR_FILTER_DEFAULTS);
  });
});

describe('asrFilterPutBlock — build the asr_filter PUT body block', () => {
  it('coerces to backend types: bool / float / int / int', () => {
    const out = asrFilterPutBlock({ enabled: true, min_confidence: 0.65, max_chars: 5, max_words: 3 });
    expect(out).toEqual({ enabled: true, min_confidence: 0.65, max_chars: 5, max_words: 3 });
    expect(typeof out.enabled).toBe('boolean');
    expect(typeof out.min_confidence).toBe('number');
    expect(Number.isInteger(out.max_chars)).toBe(true);
    expect(Number.isInteger(out.max_words)).toBe(true);
  });

  it('always emits all four keys (backend read-merge-writes the sub-block)', () => {
    expect(Object.keys(asrFilterPutBlock({})).sort()).toEqual([
      'enabled', 'max_chars', 'max_words', 'min_confidence',
    ]);
  });

  it('blanked n-input-number (null) → falls back to the default for that field', () => {
    const out = asrFilterPutBlock({ enabled: false, min_confidence: null, max_chars: null, max_words: null });
    expect(out).toEqual({ enabled: false, min_confidence: 0.5, max_chars: 4, max_words: 1 });
  });

  it('truncates fractional char/word counts to int and forces enabled to bool', () => {
    const out = asrFilterPutBlock({ enabled: 1, min_confidence: 0.5, max_chars: 4.9, max_words: 2.2 });
    expect(out.enabled).toBe(true);
    expect(out.max_chars).toBe(4);
    expect(out.max_words).toBe(2);
  });

  it('null-safe → all defaults', () => {
    expect(asrFilterPutBlock(undefined)).toEqual({
      enabled: false, min_confidence: 0.5, max_chars: 4, max_words: 1,
    });
  });
});

describe('asrFilterChanged — only PUT asr_filter when the user touched it', () => {
  it('identical values → not changed (so save() omits asr_filter)', () => {
    const v = { enabled: false, min_confidence: 0.5, max_chars: 4, max_words: 1 };
    expect(asrFilterChanged(v, { ...v })).toBe(false);
  });

  it('any single field differing → changed', () => {
    const base = { enabled: false, min_confidence: 0.5, max_chars: 4, max_words: 1 };
    expect(asrFilterChanged({ ...base, enabled: true }, base)).toBe(true);
    expect(asrFilterChanged({ ...base, min_confidence: 0.55 }, base)).toBe(true);
    expect(asrFilterChanged({ ...base, max_chars: 5 }, base)).toBe(true);
    expect(asrFilterChanged({ ...base, max_words: 0 }, base)).toBe(true);
  });

  it('cosmetic-only difference that normalises away → NOT changed', () => {
    // 4.0 (float) and 4 (int) both truncate to 4; enabled 1 and true both → true.
    const a = { enabled: 1, min_confidence: 0.5, max_chars: 4.0, max_words: 1 };
    const b = { enabled: true, min_confidence: 0.5, max_chars: 4, max_words: 1 };
    expect(asrFilterChanged(a, b)).toBe(false);
  });
});

// End-to-end: load a stored segment, flip enabled, and confirm the PUT block
// reflects exactly what the card would send (the load->edit->save round-trip).
describe('round-trip: config → card → PUT body', () => {
  it('loaded OFF, user enables + raises confidence → correct PUT block', () => {
    const segment = { engine: 'pipeline' }; // no asr_filter stored yet
    const values = asrFilterFromConfig(segment);
    expect(values.enabled).toBe(false);
    // user toggles it on and bumps the confidence threshold
    values.enabled = true;
    values.min_confidence = 0.7;
    expect(asrFilterChanged(values, asrFilterFromConfig(segment))).toBe(true);
    expect(asrFilterPutBlock(values)).toEqual({
      enabled: true,
      min_confidence: 0.7,
      max_chars: 4,
      max_words: 1,
    });
  });
});
