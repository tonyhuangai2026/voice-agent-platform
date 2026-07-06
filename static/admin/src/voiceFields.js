// Pure, DOM-free helpers for the admin voice registry editor (VoicesView.vue).
//
// The voice registry stores three providers in one table, each with a
// provider-specific attribute superset (tech_design §A.2 / §A.5):
//   minimax     → { label, gender, language, boost }     (boost = Number)
//   polly       → { label, gender, language, engine }    (engine = str)
//   nova-sonic  → { label, gender, locale, lang_label, polyglot }  (polyglot = Bool)
//
// `voiceFormFields(provider)` returns the ORDERED field descriptor list that
// drives both the add/edit form (which inputs to render) and the per-provider
// table (which extra column to show). Keeping it a pure function means the
// provider→fields mapping is unit-testable without mounting the view.
//
// Field descriptor shape:
//   { key, type, required }
//     key      — attribute name on the voice row / POST body
//     type     — 'text' | 'number' | 'switch' | 'select'  (drives the input + the
//                empty/default value via defaultFormValues)
//     required — client-side gate (server re-validates per _validate_voice_body)
// `voice_id` is included for ALL providers (the composite SK; required, and
// immutable on edit — the caller disables it when editing).

export const PROVIDERS = ['minimax', 'polly', 'nova-sonic'];

// Provider-specific attribute fields, in display order. voice_id is prepended
// by voiceFormFields() since it is common to every provider.
const PROVIDER_FIELDS = {
  minimax: [
    { key: 'label', type: 'text', required: false },
    { key: 'gender', type: 'select', required: false },
    { key: 'language', type: 'text', required: true },
    { key: 'boost', type: 'number', required: false },
  ],
  polly: [
    { key: 'label', type: 'text', required: false },
    { key: 'gender', type: 'select', required: false },
    { key: 'language', type: 'text', required: true },
    { key: 'engine', type: 'text', required: true },
  ],
  'nova-sonic': [
    { key: 'label', type: 'text', required: false },
    { key: 'gender', type: 'select', required: false },
    { key: 'locale', type: 'text', required: true },
    { key: 'lang_label', type: 'text', required: false },
    { key: 'polyglot', type: 'switch', required: false },
  ],
};

// The single provider-specific column shown in the per-provider table (in
// addition to the shared id/label/gender/language|locale columns). minimax→boost,
// polly→engine, nova-sonic→polyglot. Null for an unknown provider.
const EXTRA_COLUMN = {
  minimax: 'boost',
  polly: 'engine',
  'nova-sonic': 'polyglot',
};

// Whether the provider keys its language with `language` (minimax/polly) or
// `locale` (nova-sonic). Drives the shared language|locale table column.
export function langKeyFor(provider) {
  return provider === 'nova-sonic' ? 'locale' : 'language';
}

// Ordered field list for the add/edit form of `provider`. Always begins with
// the common voice_id field; unknown provider → just voice_id (defensive).
export function voiceFormFields(provider) {
  const idField = { key: 'voice_id', type: 'text', required: true };
  const fields = PROVIDER_FIELDS[provider];
  if (!fields) return [idField];
  return [idField, ...fields.map((f) => ({ ...f }))];
}

// The extra provider-specific table column key, or null for unknown providers.
export function extraColumnFor(provider) {
  return EXTRA_COLUMN[provider] || null;
}

// The rows shown under a provider tab: the flat voice list filtered to that
// provider. This is exactly what drives the per-provider table in VoicesView —
// keeping it pure lets "lists per provider" be asserted without a DOM mount.
export function voicesForProvider(voices, provider) {
  if (!Array.isArray(voices)) return [];
  return voices.filter((v) => v && v.provider === provider);
}

// Normalize the GET /api/admin/voices response into a flat internal row list.
//
// The T2 backend returns a PROVIDER-KEYED object:
//   { voices: { minimax: [{ id, provider, ...attrs }], polly: [...],
//               "nova-sonic": [...] }, live }
// where each row's primary key is `id` (the DynamoDB SK). Internally the view
// works with a flat list of rows carrying `provider` + `voice_id`, so this
// flattens the dict and maps `id` → `voice_id` (preserving `id` too). It is
// defensive: a flat array (already-normalized rows) or a missing/odd payload is
// tolerated and coerced to the internal shape.
export function normalizeVoicesResponse(data) {
  const toRow = (row, providerHint) => {
    const r = row || {};
    const provider = r.provider || providerHint;
    const voiceId = r.voice_id ?? r.id ?? '';
    return { ...r, provider, id: r.id ?? voiceId, voice_id: voiceId };
  };

  // A top-level array is itself the row list; otherwise read the `voices` field.
  const voices = Array.isArray(data)
    ? data
    : data && typeof data === 'object'
      ? data.voices
      : data;
  if (Array.isArray(voices)) {
    // Already a flat list of rows.
    return voices.map((r) => toRow(r, r && r.provider));
  }
  if (voices && typeof voices === 'object') {
    // Provider-keyed dict { provider: [rows] } — the real T2 shape.
    const out = [];
    for (const [p, rows] of Object.entries(voices)) {
      if (!Array.isArray(rows)) continue;
      for (const r of rows) out.push(toRow(r, p));
    }
    return out;
  }
  return [];
}

// A blank form object for `provider`: every field key seeded with a sensible
// empty value by type (switch→false, number→null, text/select→''). Used to
// reset the form on "add".
export function defaultFormValues(provider) {
  const out = {};
  for (const f of voiceFormFields(provider)) {
    if (f.type === 'switch') out[f.key] = false;
    else if (f.type === 'number') out[f.key] = null;
    else out[f.key] = '';
  }
  return out;
}

// Client-side validity gate mirroring _validate_voice_body (server is
// authoritative). voice_id must be non-empty; every `required` field must be
// present; minimax `boost`, when supplied, must be numeric.
export function isVoiceFormValid(provider, form) {
  if (!form) return false;
  const f = form;
  for (const field of voiceFormFields(provider)) {
    if (!field.required) continue;
    const v = f[field.key];
    if (v === undefined || v === null || (typeof v === 'string' && v.trim() === '')) {
      return false;
    }
  }
  // minimax boost is optional but, when present, must be a finite number.
  if (provider === 'minimax' && f.boost !== null && f.boost !== undefined && f.boost !== '') {
    if (!Number.isFinite(Number(f.boost))) return false;
  }
  return true;
}

// Build the POST/PATCH body for `provider` from the form: only the fields that
// belong to the provider, trimming strings and coercing boost to Number. Empty
// optional values are dropped so the backend keeps its defaults. `voice_id` and
// `provider` are NOT included here — the caller adds them (PATCH targets them in
// the URL path; POST adds them to the body).
export function buildVoiceAttrs(provider, form) {
  const out = {};
  for (const field of voiceFormFields(provider)) {
    if (field.key === 'voice_id') continue;
    const v = form[field.key];
    if (field.type === 'switch') {
      out[field.key] = !!v;
    } else if (field.type === 'number') {
      if (v === null || v === undefined || v === '') continue;
      out[field.key] = Number(v);
    } else {
      const s = (v ?? '').toString().trim();
      if (s === '') continue;
      out[field.key] = s;
    }
  }
  return out;
}
