import { describe, it, expect } from 'vitest';
import {
  ASR_FILTER_DEFAULTS,
  primeAsrFilterForm,
  buildAsrFilterPatch,
} from '../asrFilterFields.js';

// Pure prime/save mapping for the DemosView ASR-filter editor (tech_design §7,
// T2). DOM-free — mirrors the filler editor's inline prime/save semantics but
// extracted so the mapping is unit-tested. The editor owns exactly the four
// UI-managed fields { enabled, min_confidence, max_chars, max_words } (the
// stored-config key names — NOT the ctor's max_cjk_chars/max_latin_words).

describe('ASR_FILTER_DEFAULTS', () => {
  it('mirrors the env-default fallback (off / 0.5 / 4 / 1)', () => {
    expect(ASR_FILTER_DEFAULTS).toEqual({
      enabled: false,
      min_confidence: 0.5,
      max_chars: 4,
      max_words: 1,
    });
  });
});

describe('primeAsrFilterForm — seed the form from detail.asr_filter', () => {
  it('a full block round-trips verbatim and is marked configured', () => {
    const { configured, form } = primeAsrFilterForm({
      enabled: true,
      min_confidence: 0.3,
      max_chars: 9,
      max_words: 3,
    });
    expect(configured).toBe(true);
    expect(form).toEqual({
      enabled: true,
      min_confidence: 0.3,
      max_chars: 9,
      max_words: 3,
    });
  });

  it('a partial block fills the missing fields from defaults (still configured)', () => {
    const { configured, form } = primeAsrFilterForm({ enabled: true });
    expect(configured).toBe(true);
    expect(form).toEqual({
      enabled: true,
      min_confidence: 0.5, // default
      max_chars: 4, // default
      max_words: 1, // default
    });
  });

  it('a zero/false partial block keeps the explicit values (not coerced to default)', () => {
    const { form } = primeAsrFilterForm({ enabled: false, min_confidence: 0, max_chars: 0, max_words: 0 });
    expect(form).toEqual({ enabled: false, min_confidence: 0, max_chars: 0, max_words: 0 });
  });

  it('null / undefined / non-object → defaults form and configured=false (drives the inherit hint)', () => {
    for (const v of [null, undefined, 'x', 42, []]) {
      const { configured, form } = primeAsrFilterForm(v);
      expect(configured).toBe(false);
      expect(form).toEqual({ ...ASR_FILTER_DEFAULTS });
    }
  });

  it('wrong-typed subfields fall back to defaults defensively', () => {
    const { configured, form } = primeAsrFilterForm({
      enabled: 'yes',
      min_confidence: '0.2',
      max_chars: null,
      max_words: undefined,
    });
    expect(configured).toBe(true);
    expect(form).toEqual({ ...ASR_FILTER_DEFAULTS });
  });
});

describe('buildAsrFilterPatch — PATCH body sub-block from the form', () => {
  it('emits exactly the four UI-managed fields', () => {
    const body = buildAsrFilterPatch({
      enabled: true,
      min_confidence: 0.25,
      max_chars: 6,
      max_words: 2,
    });
    expect(body).toEqual({
      enabled: true,
      min_confidence: 0.25,
      max_chars: 6,
      max_words: 2,
    });
    expect(Object.keys(body).sort()).toEqual(['enabled', 'max_chars', 'max_words', 'min_confidence']);
  });

  it('does not leak any extra form fields (e.g. stray state) into the patch', () => {
    const body = buildAsrFilterPatch({
      enabled: false,
      min_confidence: 0.5,
      max_chars: 4,
      max_words: 1,
      _dirty: true,
      configured: false,
    });
    expect('_dirty' in body).toBe(false);
    expect('configured' in body).toBe(false);
  });

  it('prime → build is a stable round-trip for a configured demo', () => {
    const detail = { enabled: true, min_confidence: 0.4, max_chars: 5, max_words: 2 };
    const { form } = primeAsrFilterForm(detail);
    expect(buildAsrFilterPatch(form)).toEqual(detail);
  });

  it('null-safe → emits the four keys as undefined-free shape', () => {
    const body = buildAsrFilterPatch(null);
    expect(Object.keys(body).sort()).toEqual(['enabled', 'max_chars', 'max_words', 'min_confidence']);
  });
});
