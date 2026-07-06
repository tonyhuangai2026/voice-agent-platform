import { describe, it, expect } from 'vitest';
import {
  PROVIDERS,
  voiceFormFields,
  extraColumnFor,
  langKeyFor,
  defaultFormValues,
  isVoiceFormValid,
  buildVoiceAttrs,
  voicesForProvider,
  normalizeVoicesResponse,
} from '../voiceFields.js';

// The REAL GET /api/admin/voices response shape (bot.py admin_voices_list):
// a provider-keyed dict whose rows are keyed by `id` (the DDB SK), plus `live`.
// This is the ground-truth fixture the view must consume — NOT a flat list.
const T2_RESPONSE = {
  voices: {
    minimax: [
      { id: 'mm1', provider: 'minimax', label: 'MM One', language: 'zh-CN', boost: 1 },
      { id: 'mm2', provider: 'minimax', label: 'MM Two', language: 'en-US', boost: 0 },
    ],
    polly: [
      { id: 'Joanna', provider: 'polly', language: 'en-US', engine: 'neural' },
    ],
    'nova-sonic': [
      { id: 'matthew', provider: 'nova-sonic', locale: 'en-US', polyglot: false },
      { id: 'tiffany', provider: 'nova-sonic', locale: 'en-US', polyglot: true },
    ],
  },
  live: true,
};

// Pure-helper unit tests for the voice registry editor (tech_design §A.6).
// DOM-free — no mount. The provider→fields mapping is the conditional logic the
// VoicesView form/table key off, so it lives in this pure module to be testable
// without a full component mount.

const keysOf = (provider) => voiceFormFields(provider).map((f) => f.key);

describe('PROVIDERS', () => {
  it('is exactly the three registry providers', () => {
    expect(PROVIDERS).toEqual(['minimax', 'polly', 'nova-sonic']);
  });
});

describe('voiceFormFields — provider-conditional field list', () => {
  it('every provider list begins with the common voice_id field (required)', () => {
    for (const p of PROVIDERS) {
      const fields = voiceFormFields(p);
      expect(fields[0]).toMatchObject({ key: 'voice_id', type: 'text', required: true });
    }
  });

  it('minimax → voice_id,label,gender,language,boost (boost is a number)', () => {
    expect(keysOf('minimax')).toEqual(['voice_id', 'label', 'gender', 'language', 'boost']);
    const boost = voiceFormFields('minimax').find((f) => f.key === 'boost');
    expect(boost.type).toBe('number');
    // minimax has NO engine / locale / polyglot
    expect(keysOf('minimax')).not.toContain('engine');
    expect(keysOf('minimax')).not.toContain('locale');
    expect(keysOf('minimax')).not.toContain('polyglot');
    // language is required for minimax
    expect(voiceFormFields('minimax').find((f) => f.key === 'language').required).toBe(true);
  });

  it('polly → voice_id,label,gender,language,engine (engine required, text)', () => {
    expect(keysOf('polly')).toEqual(['voice_id', 'label', 'gender', 'language', 'engine']);
    const engine = voiceFormFields('polly').find((f) => f.key === 'engine');
    expect(engine).toMatchObject({ type: 'text', required: true });
    expect(keysOf('polly')).not.toContain('boost');
    expect(keysOf('polly')).not.toContain('polyglot');
    expect(keysOf('polly')).not.toContain('locale');
  });

  it('nova-sonic → voice_id,label,gender,locale,lang_label,polyglot (polyglot switch; locale not language)', () => {
    expect(keysOf('nova-sonic')).toEqual([
      'voice_id', 'label', 'gender', 'locale', 'lang_label', 'polyglot',
    ]);
    const poly = voiceFormFields('nova-sonic').find((f) => f.key === 'polyglot');
    expect(poly.type).toBe('switch');
    // nova keys by locale, NOT language; locale is required
    expect(keysOf('nova-sonic')).toContain('locale');
    expect(keysOf('nova-sonic')).not.toContain('language');
    expect(voiceFormFields('nova-sonic').find((f) => f.key === 'locale').required).toBe(true);
    // lang_label is optional
    expect(voiceFormFields('nova-sonic').find((f) => f.key === 'lang_label').required).toBe(false);
    expect(keysOf('nova-sonic')).not.toContain('boost');
    expect(keysOf('nova-sonic')).not.toContain('engine');
  });

  it('unknown provider → just voice_id (defensive)', () => {
    expect(keysOf('bogus')).toEqual(['voice_id']);
    expect(keysOf(undefined)).toEqual(['voice_id']);
  });

  it('returns fresh field objects (no shared mutable state across calls)', () => {
    const a = voiceFormFields('minimax');
    a[1].required = 'MUTATED';
    const b = voiceFormFields('minimax');
    expect(b[1].required).not.toBe('MUTATED');
  });
});

describe('extraColumnFor — the one provider-specific table column', () => {
  it('minimax→boost, polly→engine, nova-sonic→polyglot', () => {
    expect(extraColumnFor('minimax')).toBe('boost');
    expect(extraColumnFor('polly')).toBe('engine');
    expect(extraColumnFor('nova-sonic')).toBe('polyglot');
  });
  it('unknown provider → null', () => {
    expect(extraColumnFor('bogus')).toBeNull();
    expect(extraColumnFor(undefined)).toBeNull();
  });
});

describe('langKeyFor — language vs locale column', () => {
  it('nova-sonic keys by locale; minimax/polly by language', () => {
    expect(langKeyFor('nova-sonic')).toBe('locale');
    expect(langKeyFor('minimax')).toBe('language');
    expect(langKeyFor('polly')).toBe('language');
  });
});

describe('defaultFormValues — blank seed per provider', () => {
  it('seeds every field by type: switch→false, number→null, text/select→""', () => {
    const mm = defaultFormValues('minimax');
    expect(mm).toEqual({ voice_id: '', label: '', gender: '', language: '', boost: null });
    const nova = defaultFormValues('nova-sonic');
    expect(nova).toEqual({
      voice_id: '', label: '', gender: '', locale: '', lang_label: '', polyglot: false,
    });
  });
});

describe('isVoiceFormValid — client-side gate mirroring _validate_voice_body', () => {
  it('minimax: needs voice_id + language; boost optional but numeric when present', () => {
    expect(isVoiceFormValid('minimax', { voice_id: '', language: 'zh-CN' })).toBe(false);
    expect(isVoiceFormValid('minimax', { voice_id: 'v1', language: '' })).toBe(false);
    expect(isVoiceFormValid('minimax', { voice_id: 'v1', language: 'zh-CN' })).toBe(true);
    expect(isVoiceFormValid('minimax', { voice_id: 'v1', language: 'zh-CN', boost: 1.5 })).toBe(true);
    expect(isVoiceFormValid('minimax', { voice_id: 'v1', language: 'zh-CN', boost: 'NaN-ish' })).toBe(false);
    // empty boost is allowed (optional)
    expect(isVoiceFormValid('minimax', { voice_id: 'v1', language: 'zh-CN', boost: '' })).toBe(true);
  });

  it('polly: needs voice_id + language + engine', () => {
    expect(isVoiceFormValid('polly', { voice_id: 'Joanna', language: 'en-US' })).toBe(false);
    expect(isVoiceFormValid('polly', { voice_id: 'Joanna', language: 'en-US', engine: 'neural' })).toBe(true);
  });

  it('nova-sonic: needs voice_id + locale (polyglot defaulted, lang_label optional)', () => {
    expect(isVoiceFormValid('nova-sonic', { voice_id: 'matthew' })).toBe(false);
    expect(isVoiceFormValid('nova-sonic', { voice_id: 'matthew', locale: 'en-US' })).toBe(true);
    expect(isVoiceFormValid('nova-sonic', { voice_id: 'matthew', locale: 'en-US', polyglot: true })).toBe(true);
  });

  it('whitespace-only required field is rejected; null form → false', () => {
    expect(isVoiceFormValid('minimax', { voice_id: '   ', language: 'zh-CN' })).toBe(false);
    expect(isVoiceFormValid('minimax', null)).toBe(false);
  });
});

describe('normalizeVoicesResponse — boundary adapter for the real T2 shape', () => {
  it('flattens the provider-keyed dict and maps id → voice_id (preserving id)', () => {
    const rows = normalizeVoicesResponse(T2_RESPONSE);
    expect(rows).toHaveLength(5);
    // every row gains a voice_id mirroring the backend `id`, keeps provider
    for (const r of rows) {
      expect(r.voice_id).toBe(r.id);
      expect(['minimax', 'polly', 'nova-sonic']).toContain(r.provider);
    }
    const mm = rows.filter((r) => r.provider === 'minimax');
    expect(mm.map((r) => r.voice_id)).toEqual(['mm1', 'mm2']);
    // attrs (boost / engine / locale / polyglot) are preserved
    expect(rows.find((r) => r.voice_id === 'tiffany')).toMatchObject({ locale: 'en-US', polyglot: true });
    expect(rows.find((r) => r.voice_id === 'Joanna')).toMatchObject({ engine: 'neural' });
  });

  it('?provider=-filtered response (single-key dict) normalizes to just that provider', () => {
    const rows = normalizeVoicesResponse({ voices: { polly: T2_RESPONSE.voices.polly }, live: true });
    expect(rows.map((r) => r.voice_id)).toEqual(['Joanna']);
    expect(rows.every((r) => r.provider === 'polly')).toBe(true);
  });

  it('infers provider from the dict key when a row omits it', () => {
    const rows = normalizeVoicesResponse({ voices: { minimax: [{ id: 'x', language: 'zh-CN' }] } });
    expect(rows[0]).toMatchObject({ provider: 'minimax', id: 'x', voice_id: 'x' });
  });

  it('tolerates an already-flat array (defensive) and a missing/odd payload', () => {
    const flat = normalizeVoicesResponse([{ id: 'a', provider: 'polly' }]);
    expect(flat[0]).toMatchObject({ provider: 'polly', voice_id: 'a' });
    expect(normalizeVoicesResponse(undefined)).toEqual([]);
    expect(normalizeVoicesResponse({})).toEqual([]);
    expect(normalizeVoicesResponse({ voices: null })).toEqual([]);
  });
});

describe('voicesForProvider — the per-provider listing the view renders', () => {
  // Derived from the REAL T2 response via the boundary adapter — proves the
  // per-provider tabs list correctly against the actual backend shape, not a
  // hand-built flat fixture.
  const VOICES = normalizeVoicesResponse(T2_RESPONSE);

  it('lists only the active provider tab rows — minimax', () => {
    expect(voicesForProvider(VOICES, 'minimax').map((v) => v.voice_id)).toEqual(['mm1', 'mm2']);
  });
  it('lists only polly rows', () => {
    expect(voicesForProvider(VOICES, 'polly').map((v) => v.voice_id)).toEqual(['Joanna']);
  });
  it('lists only nova-sonic rows', () => {
    expect(voicesForProvider(VOICES, 'nova-sonic').map((v) => v.voice_id)).toEqual(['matthew', 'tiffany']);
  });
  it('every provider tab partitions the flat list with no leakage', () => {
    const total = PROVIDERS.reduce((n, p) => n + voicesForProvider(VOICES, p).length, 0);
    expect(total).toBe(VOICES.length);
  });
  it('null-safe → []', () => {
    expect(voicesForProvider(undefined, 'minimax')).toEqual([]);
    expect(voicesForProvider(null, 'minimax')).toEqual([]);
  });
});

describe('buildVoiceAttrs — provider-scoped body (no voice_id/provider, coerced types)', () => {
  it('minimax: trims strings, coerces boost to Number, drops empty optionals, excludes voice_id', () => {
    const out = buildVoiceAttrs('minimax', {
      voice_id: 'v1', label: '  Lbl  ', gender: 'female', language: 'zh-CN', boost: '2',
    });
    expect(out).toEqual({ label: 'Lbl', gender: 'female', language: 'zh-CN', boost: 2 });
    expect('voice_id' in out).toBe(false);
  });

  it('minimax: empty boost is dropped, empty label dropped', () => {
    const out = buildVoiceAttrs('minimax', {
      voice_id: 'v1', label: '', gender: '', language: 'zh-CN', boost: '',
    });
    expect(out).toEqual({ language: 'zh-CN' });
  });

  it('nova-sonic: polyglot switch always emitted as a boolean', () => {
    const on = buildVoiceAttrs('nova-sonic', { voice_id: 'm', locale: 'en-US', polyglot: true });
    expect(on).toEqual({ locale: 'en-US', polyglot: true });
    const off = buildVoiceAttrs('nova-sonic', { voice_id: 'm', locale: 'en-US', polyglot: false });
    expect(off).toEqual({ locale: 'en-US', polyglot: false });
  });

  it('polly: only provider fields included (engine kept)', () => {
    const out = buildVoiceAttrs('polly', {
      voice_id: 'Joanna', label: 'Joanna', language: 'en-US', engine: 'neural',
      // a stray minimax-only key must not leak through
      boost: 9,
    });
    expect(out).toEqual({ label: 'Joanna', language: 'en-US', engine: 'neural' });
    expect('boost' in out).toBe(false);
  });
});
