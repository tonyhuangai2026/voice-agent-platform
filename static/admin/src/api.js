// Thin fetch wrapper for the JSON API. Authentication is a JWT session
// carried in the HttpOnly `vb_session` cookie (tech_design §1/§2), so every
// request sends credentials and a 401 routes the user back to /login.

const BASE = '/api/admin';

// Set by main.js after the router is created. Lets the wrapper centralise the
// "session expired → /login" redirect without importing the router (which would
// create a circular dependency: router/index.js imports this module).
let _onUnauthorized = null;
export function setUnauthorizedHandler(fn) {
  _onUnauthorized = fn;
}

// Auth-probe requests (GET /api/auth/me, POST /api/auth/login) must NOT trigger
// the global redirect on 401 — the router guard / login form handle those
// inline. `skipAuthRedirect` opts a call out of the centralised redirect.
async function rawRequest(url, options = {}, { skipAuthRedirect = false } = {}) {
  const res = await fetch(url, {
    credentials: 'include',
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  if (res.status === 401 && !skipAuthRedirect && _onUnauthorized) {
    _onUnauthorized();
  }
  if (!res.ok) {
    let body = '';
    try {
      body = await res.text();
    } catch {}
    const err = new Error(`HTTP ${res.status}: ${body || res.statusText}`);
    err.status = res.status;
    // Structured error payloads (e.g. DELETE /mcp-servers/{id} answering 409
    // with {detail: {message, demos: [...]}}) are surfaced on err.body so
    // views can render them without re-parsing the message string.
    try {
      err.body = JSON.parse(body);
    } catch {}
    throw err;
  }
  if (res.status === 204) return null;
  return res.json();
}

// Admin REST under /api/admin/*.
function request(path, options = {}) {
  return rawRequest(`${BASE}${path}`, options);
}

// Auth endpoints live at /api/auth/* (not under /api/admin). They skip the
// global 401 redirect so the guard / login form can react inline.
function authRequest(path, options = {}) {
  return rawRequest(`/api/auth${path}`, options, { skipAuthRedirect: true });
}

// Site-level (non-admin) endpoints under /api/* used by the call views merged
// in from the old demo SPA (Talk / Monitor / My History — tech_design §3).
// These are gated by require_user (or require_admin for /api/calls) on the
// backend, so they DO participate in the global 401 → /login redirect.
function siteRequest(path, options = {}) {
  return rawRequest(`/api${path}`, options);
}

export const api = {
  // -- Auth (tech_design §1.4) --------------------------------------------
  // Current session identity { username, role }; rejects (401) when no/expired
  // session cookie. Used by the router guard and App.vue header.
  me: () => authRequest('/me'),
  login: (username, password) =>
    authRequest('/login', { method: 'POST', body: JSON.stringify({ username, password }) }),
  logout: () => authRequest('/logout', { method: 'POST' }),
  // First-run setup (tech_design §4). Both are PUBLIC and skip the global 401
  // redirect (authRequest). setupStatus → { needs_setup: bool }; permanently
  // false once any admin exists. setup creates the first admin AND auto-logs
  // in (sets the vb_session cookie server-side) → { username, role }; 409 when
  // already initialized, 400 on empty input.
  setupStatus: () => authRequest('/setup-status'),
  setup: ({ username, password }) =>
    authRequest('/setup', { method: 'POST', body: JSON.stringify({ username, password }) }),
  // -- Temporary guest experience link (tech_design §3) -------------------
  // PUBLIC redeem: exchange a minted guest token for a vb_session cookie. No
  // auth dep on the backend (anyone with the link logs in), so it skips the
  // global 401 redirect (authRequest) — GuestLanding shows its own expired
  // message on failure. body: { token } → { username:'guest', role:'guest',
  // scenario?, lang?, engine?, voice?, provider? } (each null when the token
  // didn't carry it — GuestLanding forwards the non-null subset into the Talk
  // launch query); 401 when the token is tampered/expired/non-guest.
  guestLogin: (body) =>
    authRequest('/guest-login', { method: 'POST', body: JSON.stringify(body) }),

  // -- Call views (merged from demo SPA, tech_design §3) -------------------
  // Runtime config snapshot (engine / language / scenario defaults) shown by
  // TalkView. Backend: GET /api/config (require_user).
  config: () => siteRequest('/config'),
  // Active live phone/web sessions for MonitorView. Backend: GET /api/calls
  // (require_admin — monitoring others' calls is an admin action).
  calls: () => siteRequest('/calls'),
  // One-shot Bedrock conversation summary for TalkView's summary modal.
  // Backend: POST /api/summary (require_user).
  summary: (payload) =>
    siteRequest('/summary', { method: 'POST', body: JSON.stringify(payload) }),
  // The CALLER'S OWN web call history (MyHistoryView). Backend: GET /api/history
  // (require_user) is already user-scoped to web_user == current username, so we
  // do NOT forward a caller filter here — it would hit the admin-only
  // /api/history/by-caller GSI endpoint. This is distinct from the admin-only
  // full history (api.historyList → /api/admin/history).
  fetchHistory: ({ cursor = null, limit = 50 } = {}) => {
    const params = new URLSearchParams();
    params.set('limit', String(limit));
    if (cursor) params.set('cursor', cursor);
    return siteRequest(`/history?${params}`);
  },
  fetchHistoryDetail: (callId) =>
    siteRequest(`/history/${encodeURIComponent(callId)}`),

  health: () => request('/health'),
  getConfig: () => request('/config'),
  putWeb: (payload) => request('/config/web', { method: 'PUT', body: JSON.stringify(payload) }),
  putPhone: (payload) => request('/config/phone', { method: 'PUT', body: JSON.stringify(payload) }),
  // Read-only Chime VC ↔ phone-number view (GET /api/admin/phone-numbers).
  // Returns { voice_connectors: [{voice_connector_id, voice_connector_name,
  // e164, status}], error }. Best-effort: HTTP 200 even on Chime errors (the
  // error field carries the reason).
  phoneNumbers: () => request('/phone-numbers'),
  options: () => request('/options'),
  demos: () => request('/demos'),
  rescan: () => request('/demos/rescan', { method: 'POST' }),
  demoDetail: (id) => request(`/demos/${encodeURIComponent(id)}`),
  // Tool registry — listed by GET /api/admin/tools (T6).
  adminTools: () => request('/tools'),
  // Dashboard live metrics — see Tech Design §2 for response shape.
  // Polled every 7s by DashboardView; backend caches 10s so polling is cheap.
  metrics: () => request('/metrics'),
  // Patch a single demo's manifest. Server-side editable fields: `tools`
  // and `mcp_servers` (body shape: { tools?: [string], mcp_servers?: [string] };
  // omitted fields are left untouched).
  patchDemo: (id, body) =>
    request(`/demos/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  // Preview-translate a demo's inline localized fields into `target_lang`.
  // body: { target_lang, source_lang? }. Returns
  // { target_lang, source_used: {field: lang}, fields: {field: text},
  //   already_exists: {field: bool} } — NEVER writes disk. Confirmed text is
  // persisted via patchDemo({ localized: {field: {lang: text}}, overwrite }).
  // Errors: 400 (bad/absent lang, no source), 502 (LLM translate/parse fail).
  translateDemo: (id, body) =>
    request(`/demos/${encodeURIComponent(id)}/translate`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),
  // -- MCP server registry (tech_design §A.2 / §A.4) -----------------------
  // GET masks every header value as "***"; POST sends "***" back verbatim
  // for untouched values (the backend keeps the stored secret for that key).
  // Each server also carries an `auth` object { type: none|header|sigv4,
  // service?, region? }. sigv4 stores no secret (IAM role at connect time),
  // so its service/region round-trip in the clear — nothing to mask there.
  mcpServers: () => request('/mcp-servers'),
  // Upsert by id — body: { id, label, transport, url, headers, enabled, auth }.
  // `auth` is { type:'none' } | { type:'header' } | { type:'sigv4', service, region }.
  saveMcpServer: (body) =>
    request('/mcp-servers', { method: 'POST', body: JSON.stringify(body) }),
  // 409 when demos still reference the server — err.body.detail.demos
  // carries the referencing demo ids (see request() above).
  deleteMcpServer: (id) =>
    request(`/mcp-servers/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  // Always resolves 200 with { ok, tools, error } — connection failures are
  // data, not transport errors.
  testMcpServer: (id) =>
    request(`/mcp-servers/${encodeURIComponent(id)}/test`, { method: 'POST' }),
  // -- Voice registry (tech_design §A.5) ----------------------------------
  // The global editable voice registry: three providers (minimax / polly /
  // nova-sonic) in one composite-keyed store. Per-provider attribute superset
  // (minimax {label,gender,language,boost} / polly {label,gender,language,engine}
  // / nova-sonic {label,gender,locale,lang_label,polyglot}). After any write/
  // delete the backend rescans so /api/config reflects immediately.
  // GET → { voices: { minimax: [{id,provider,...attrs}], polly: [...],
  // "nova-sonic": [...] }, live }. The list is a PROVIDER-KEYED dict and each
  // row's primary key is `id` (the SK) — VoicesView normalizes it to a flat
  // list via normalizeVoicesResponse(). `provider` filters server-side when
  // supplied (the dict then has just that one key).
  listVoices: (provider) =>
    request('/voices' + (provider ? `?provider=${encodeURIComponent(provider)}` : '')),
  // POST → { voice }. body: { provider, id, ...attrs } (the backend also accepts
  // `voice_id` as an alias for `id`). 400 on invalid.
  createVoice: (body) =>
    request('/voices', { method: 'POST', body: JSON.stringify(body) }),
  // PATCH → { voice }. body = the attrs to update (provider + voice_id are in
  // the path, immutable). 400 on invalid, 404 when absent.
  updateVoice: (provider, voiceId, body) =>
    request(
      `/voices/${encodeURIComponent(provider)}/${encodeURIComponent(voiceId)}`,
      { method: 'PATCH', body: JSON.stringify(body) },
    ),
  // DELETE → { deleted }. A deleted/dangling voice never crashes a call (the
  // resolver falls back to the provider default).
  deleteVoice: (provider, voiceId) =>
    request(
      `/voices/${encodeURIComponent(provider)}/${encodeURIComponent(voiceId)}`,
      { method: 'DELETE' },
    ),
  // -- History (Tech Design §3 / §4.2) ------------------------------------
  // Cursor-paginated list of historical calls. `params` accepts: limit,
  // cursor, caller, outcome, engine, demo, start_after, start_before.
  // Empty / null values are stripped before serialisation so backend filters
  // are not narrowed accidentally.
  historyList: (params = {}) => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue;
      sp.append(k, v);
    }
    const qs = sp.toString();
    return request('/history' + (qs ? '?' + qs : ''));
  },
  // Full row (turns + summary included) for the drawer.
  historyDetail: (id) => request(`/history/${encodeURIComponent(id)}`),
  // URL-only helpers: returned strings are passed straight to window.open(),
  // so the browser's Basic Auth cookie travels automatically. Do NOT call
  // request() here — that would buffer the file in JS memory.
  historyExportMdUrl: (id) =>
    `${BASE}/history/${encodeURIComponent(id)}/export.md`,
  historyCsvUrl: (params = {}) => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue;
      sp.append(k, v);
    }
    const qs = sp.toString();
    return `${BASE}/history.csv` + (qs ? '?' + qs : '');
  },
  // Trigger Bedrock re-summarisation for one row. Server overwrites
  // `summary` + `summary_status` and returns the updated row.
  historySummarize: (id) =>
    request(`/history/${encodeURIComponent(id)}/summarize`, { method: 'POST' }),

  // -- Activity log (admin-only, tech_design Part B B.5) ------------------
  // Cursor-paginated, newest-first operations audit. Backend: GET
  // /api/admin/activity (require_admin) → { items: [...], cursor }. `params`
  // accepts: from, to (UTC YYYY-MM-DD), actor, type, limit, cursor. Empty /
  // null values are stripped so backend filters are never narrowed by accident
  // (the same convention as historyList). All detail maps were already
  // sanitized (default-deny) at write time, so rows are safe to render as-is.
  activity: (params = {}) => {
    const sp = new URLSearchParams();
    for (const [k, v] of Object.entries(params)) {
      if (v === undefined || v === null || v === '') continue;
      sp.append(k, v);
    }
    const qs = sp.toString();
    return request('/activity' + (qs ? '?' + qs : ''));
  },

  // -- User management (admin-only, tech_design §4) -----------------------
  // All routes are gated by require_admin on the backend (bot.py
  // /api/admin/users*). The "safe" user view never includes password_hash:
  // { username, role, created_at, disabled }.
  // GET → { users: [...] }.
  users: () => request('/users'),
  // POST → { user }. body: { username, password, role }.
  createUser: (body) =>
    request('/users', { method: 'POST', body: JSON.stringify(body) }),
  // PATCH → { user }. body is any subset of { role, password, disabled }.
  // The backend rejects disabling/deleting your own account (400) to avoid
  // admin lock-out — views surface that as an error message.
  updateUser: (username, body) =>
    request(`/users/${encodeURIComponent(username)}`, {
      method: 'PATCH',
      body: JSON.stringify(body),
    }),
  // DELETE → { deleted }.
  deleteUser: (username) =>
    request(`/users/${encodeURIComponent(username)}`, { method: 'DELETE' }),

  // -- Temporary guest experience link (admin mint, tech_design §3) -------
  // POST /api/admin/guest-links (require_admin) → mint a one-time guest link
  // token. body: { ttl_minutes?, scenario?, lang?, engine?, voice?, provider? }
  // (the four launch overrides are optional; the UsersView modal prefills them
  // from the picked demo's detail and sends only the non-empty ones) →
  // { token, ttl_seconds, expires_at, scenario, lang, engine, voice, provider,
  // path:'/guest' }. The token is returned ONLY here,
  // never logged; the view shows it once and does not persist it.
  createGuestLink: (body) =>
    request('/guest-links', { method: 'POST', body: JSON.stringify(body) }),
};
