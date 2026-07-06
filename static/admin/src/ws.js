// WebSocket helpers. Demo SPA does NOT pass any config query params — the
// /ws and /monitor/ws endpoints read defaults from runtime_config (T3).
//
// Browsers cannot send Authorization on the WS handshake, and CloudFront
// strips it anyway. So we mint a short-lived ?token=... via /api/ws-token
// (the GET still goes over HTTPS with cached Basic Auth) and append it to
// the WS URL.

export function wsBaseUrl() {
  const proto = location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${location.host}`;
}

async function fetchWsToken() {
  try {
    const res = await fetch('/api/ws-token', { credentials: 'include' });
    if (!res.ok) return '';
    const data = await res.json();
    return data?.token || '';
  } catch {
    return '';
  }
}

// Query keys the /ws endpoint understands as per-session overrides
// (bot.py reads ?scenario=&lang=&engine=&voice=...; priority query > web_defaults
// > DEFAULT_*). Used as the whitelist for both openTalkWs() and pickLaunchQuery().
export const LAUNCH_QUERY_KEYS = [
  'scenario',
  'lang',
  'engine',
  'voice',
  'provider',
  'model',
  'minimax_model',
];

/**
 * Open a WS to /ws (Talk mode).
 *
 * Backward-compatible: `openTalkWs()` with no args behaves exactly as before
 * (token only — server uses runtime defaults). Pass a config object to append
 * per-session overrides (scenario / lang / engine / voice / provider / model /
 * minimax_model). Null/undefined/empty-string values are NOT appended.
 */
export async function openTalkWs(params = {}) {
  const token = await fetchWsToken();
  const qs = new URLSearchParams();
  if (token) qs.set('token', token);
  for (const [k, v] of Object.entries(params || {})) {
    if (v != null && v !== '') qs.set(k, String(v));
  }
  const query = qs.toString();
  const ws = new WebSocket(`${wsBaseUrl()}/ws${query ? '?' + query : ''}`);
  ws.binaryType = 'arraybuffer';
  return ws;
}

/**
 * Derive the per-session launch query for a demo (pure function).
 *
 * Returns `{ scenario: demo.id }`, plus `lang` when `demo.lang` is truthy. A
 * demo that carries its own engine/voice/provider emits them too (demo-first
 * priority, tech_design §5) — fields the demo did not set are simply absent so
 * TalkView's session selection (demo > session > default) supplies them.
 *
 * A tools/MCP demo carries no engine constraint: Nova Sonic supports
 * function-calling, so a tool/MCP demo with `demo.engine === 'nova-sonic'`
 * launches on Nova Sonic. A demo with no stored engine omits `engine` so the
 * server falls back to the session/global default.
 */
export function demoLaunchParams(demo) {
  const d = demo || {};
  const p = { scenario: d.id };
  if (d.lang) p.lang = d.lang;
  // demo-set engine/voice/provider/model (demo-first priority).
  if (d.engine) p.engine = d.engine;
  if (d.voice) p.voice = d.voice;
  if (d.provider) p.provider = d.provider;
  if (d.model) p.model = d.model;
  return p;
}

/**
 * Whitelist-filter a route.query object (pure function): keep only the keys the
 * /ws endpoint understands (LAUNCH_QUERY_KEYS), dropping any unknown keys.
 */
export function pickLaunchQuery(query) {
  const out = {};
  const q = query || {};
  for (const k of LAUNCH_QUERY_KEYS) {
    if (k in q) out[k] = q[k];
  }
  return out;
}

/**
 * Open a WS to /asr-test/ws (ASR A/B test tool, tech_design §3-§4).
 *
 * Mirrors openTalkWs: mint the short-lived ?token=... (same /api/ws-token the
 * /ws endpoint uses) and append it. Optionally append &mode= (single|multiple)
 * which the backend applies to stream B's multi-language identification. Empty/
 * null params are not appended (token-only URL if no mode given).
 */
export async function openAsrTestWs(params = {}) {
  const token = await fetchWsToken();
  const qs = new URLSearchParams();
  if (token) qs.set('token', token);
  for (const [k, v] of Object.entries(params || {})) {
    if (v != null && v !== '') qs.set(k, String(v));
  }
  const query = qs.toString();
  const ws = new WebSocket(`${wsBaseUrl()}/asr-test/ws${query ? '?' + query : ''}`);
  ws.binaryType = 'arraybuffer';
  return ws;
}

/** Open a WS to /monitor/ws?call_id=... (Monitor mode). */
export async function openMonitorWs(callId) {
  const token = await fetchWsToken();
  const params = new URLSearchParams({ call_id: callId });
  if (token) params.set('token', token);
  const ws = new WebSocket(`${wsBaseUrl()}/monitor/ws?${params}`);
  ws.binaryType = 'arraybuffer';
  return ws;
}
