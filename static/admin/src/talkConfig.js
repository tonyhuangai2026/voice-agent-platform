// talkConfig.js — pure, DOM-free selection helpers for the Talk page
// engine/voice selectors (tech_design §2). No Vue, no DOM, no localStorage:
// TalkView passes any persisted state in as `prev`. Every helper is null-safe —
// a missing/empty config section yields safe empties and never throws.

// Languages whose capability list includes `engine`.
export function langsForEngine(config, engine) {
  return (config?.languages || []).filter((l) => (l.engines || []).includes(engine));
}

// Pipeline voices for a provider, preferring those whose `language` matches
// `lang`; if none match exactly, fall back to the full provider list (so a
// provider is never empty). nova-sonic handled separately (novaVoices).
export function voicesForProvLang(config, provider, lang) {
  const all = config?.voices_by_provider?.[provider] || [];
  const exact = all.filter((v) => v.language === lang);
  return exact.length ? exact : all;
}

export function novaVoices(config) {
  return config?.nova_sonic_voices || [];
}

// The engines list (all configured engines; engine is cross-filtered by
// language elsewhere via langsForEngine, not here).
export function enginesFor(config) {
  return config?.engines || [];
}

// Reconcile a (possibly stale / persisted) selection against config. Returns a
// fully-valid {engine, lang, provider, voice, novaVoice} — every field
// guaranteed present in its current list, with config defaults as the fallback.
// Single source of correctness for both the initial seed (prev = persisted||{})
// and engine/lang/provider changes.
export function reconcileSelection(prev, config) {
  const c = config || {};
  // engine
  const engineList = enginesFor(c).map((e) => e.id);
  let engine = prev?.engine;
  if (!engineList.includes(engine)) {
    engine = engineList.includes(c.default_engine) ? c.default_engine : engineList[0];
  }
  // lang — must be valid for the chosen engine
  const langList = langsForEngine(c, engine).map((l) => l.id);
  let lang = prev?.lang;
  if (!langList.includes(lang)) {
    lang = langList.includes(c.default_language) ? c.default_language : langList[0];
  }
  // provider (pipeline only)
  const provList = (c.providers || []).map((p) => p.id);
  let provider = prev?.provider;
  if (!provList.includes(provider)) {
    provider = provList.includes(c.default_provider) ? c.default_provider : provList[0];
  }
  // pipeline voice — valid within provider+lang
  const pvList = voicesForProvLang(c, provider, lang).map((v) => v.id);
  let voice = prev?.voice;
  if (!pvList.includes(voice)) {
    voice =
      c.default_voices?.[provider] && pvList.includes(c.default_voices[provider])
        ? c.default_voices[provider]
        : pvList[0];
  }
  // nova voice
  const nvList = novaVoices(c).map((v) => v.id);
  let novaVoice = prev?.novaVoice;
  if (!nvList.includes(novaVoice)) {
    novaVoice = nvList.includes(c.default_nova_sonic_voice) ? c.default_nova_sonic_voice : nvList[0];
  }
  // model (pipeline LLM) — OPTIONAL: '' / null / unknown means "inherit the
  // global default" (DEFAULT_MODEL is resolved server-side). Unlike voice we do
  // NOT force a default here; we only validate that a non-empty value is a known
  // model id, dropping it to '' (inherit) if it isn't. nova-sonic ignores it.
  const modelList = (c.models || []).map((m) => m.id);
  let model = prev?.model;
  if (model && !modelList.includes(model)) model = '';
  if (!model) model = '';
  return { engine, lang, provider, voice, novaVoice, model };
}

// Layer a URL launch cfg (pickLaunchQuery output: flat scenario/lang/engine/
// voice/provider/...) OVER a persisted selection, producing a `prev` to feed
// reconcileSelection (tech_design §2-§3). URL-provided keys win; persisted fills
// the gaps; keys the URL did NOT provide are left untouched. PURE — no config
// access, no reconcile. So the display chips/selectors reflect the URL launch
// params (matching the actual call) instead of stale global defaults.
//
// voice is routed by the EFFECTIVE engine (URL engine, else persisted engine):
// nova-sonic → novaVoice, otherwise → voice. Edge: a URL voice with no engine
// in either URL or persisted → effEngine undefined → falls to the else → .voice
// (the safe default for an unspecified engine).
//
// An empty/missing launchCfg returns a copy of persisted unchanged (manual
// /talk → identical to today).
export function seedPrevFromLaunch(persisted, launchCfg) {
  const p = { ...(persisted || {}) };
  const c = launchCfg || {};
  if (c.engine) p.engine = c.engine;
  if (c.lang) p.lang = c.lang;
  if (c.provider) p.provider = c.provider;
  if (c.model) p.model = c.model;
  if (c.voice) {
    const effEngine = c.engine || p.engine;
    if (effEngine === 'nova-sonic') p.novaVoice = c.voice;
    else p.voice = c.voice;
  }
  return p;
}

// Build the per-session launch query for openTalkWs() from a reconciled
// selection + the active demo launch cfg. Engine-appropriate voice only.
export function launchParamsFromSelection(sel, baseCfg = {}) {
  const p = { ...baseCfg }; // keeps scenario (and any demo-set engine)
  p.engine = sel.engine;
  p.lang = sel.lang;
  if (sel.engine === 'nova-sonic') {
    p.voice = sel.novaVoice;
    delete p.provider;
    delete p.model;
    delete p.minimax_model;
  } else {
    p.provider = sel.provider;
    p.voice = sel.voice;
    // model is OPTIONAL: only emit a non-empty selection (''=inherit global
    // DEFAULT_MODEL server-side). openTalkWs also drops empties, but keeping the
    // key absent here means the demo-first merge / chips don't see a phantom ''.
    if (sel.model) p.model = sel.model;
    else delete p.model;
  }
  return p;
}

// Drop null / undefined / '' values from a shallow object (pure). Used so a
// demo cfg's unset (null/empty) engine/voice/provider keys don't clobber the
// session selection in the demo-first merge.
export function stripEmpty(obj) {
  const out = {};
  for (const [k, v] of Object.entries(obj || {})) {
    if (v != null && v !== '') out[k] = v;
  }
  return out;
}

// Build a guest-link prefill object {lang, engine, voice, provider} from a demo
// DETAIL payload (GET /api/admin/demos/{id} — flat top-level engine/voice/
// provider/lang). PURE — no config, no reconcile. Only non-empty fields are
// carried; everything else is omitted so an empty/undefined detail → {} (the
// modal then shows blank fields). Used by the UsersView generate-link modal
// when the admin picks a scenario, so the link inherits the demo's stored
// launch config (which the guest then experiences) instead of global defaults.
export function guestPrefillFromDemo(detail) {
  const d = detail || {};
  const out = {};
  for (const k of ['lang', 'engine', 'voice', 'provider']) {
    const v = d[k];
    if (v != null && v !== '') out[k] = v;
  }
  return out;
}

// Build the createGuestLink request body from the generate-link modal form
// (tech_design §3.1). PURE. ttl_minutes always rides; scenario + the four
// launch overrides are carried ONLY when non-empty, so an empty scenario / no
// overrides → a body with just ttl (pure global-default guest link). Mirror of
// guestLaunchQuery's "non-empty only" rule, on the mint side.
export function guestLinkBody(form) {
  const f = form || {};
  const body = { ttl_minutes: f.ttl };
  for (const k of ['scenario', 'lang', 'engine', 'voice', 'provider']) {
    if (f[k]) body[k] = f[k];
  }
  return body;
}

// Build the GuestLanding → Talk forward query from a guest-login response.
// PURE. Carries only the non-empty launch keys (scenario + the four config
// fields) — the exact set TalkView's seedPrevFromLaunch/mergeDemoFirst consume.
// Returns undefined when nothing is present so router.replace gets a clean
// /talk URL (matching today's scenario-only / no-config behavior).
export function guestLaunchQuery(res) {
  const r = res || {};
  const query = {};
  for (const k of ['scenario', 'lang', 'engine', 'voice', 'provider']) {
    if (r[k]) query[k] = r[k];
  }
  return Object.keys(query).length ? query : undefined;
}

// Demo-first merge (tech_design §6): the demo's explicit (non-empty) keys WIN
// over the session selection. `sessionParams` is the reconciled session/global
// launch query (launchParamsFromSelection); `demoCfg` is the active demo launch
// cfg (scenario + any demo-set engine/voice/provider). A demo that sets none of
// engine/voice/provider inherits the session selection; a manual /talk (empty
// demoCfg) → pure session selection.
export function mergeDemoFirst(sessionParams, demoCfg) {
  return { ...sessionParams, ...stripEmpty(demoCfg) };
}
