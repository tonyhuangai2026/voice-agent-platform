// activityFields.js — pure, DOM-free helpers for the admin activity-log viewer
// (ActivityLogView.vue, tech_design Part B B.5). Kept out of the component so
// the two non-trivial mappings — filter→query-params and activity-type→human
// label — are unit-testable without mounting Vue.
//
// The backend contract (GET /api/admin/activity, bot.py admin_activity_list):
//   params: from, to (UTC YYYY-MM-DD), actor, type, limit, cursor
//   response: { items: [...], cursor: <opaque|null> }
//   row: { actor, actor_role, type, target?, detail (sanitized map), status,
//          error?, ts (epoch MS), day, ts_id }
// Activity types come from the T3 log_activity() call sites; this list is the
// dropdown source AND the i18n label key suffix.

import { i18n } from './i18n/index.js';

// The closed set of activity types the backend emits (T3). Order = dropdown
// order. Kept here (not derived from rows) so the filter dropdown is stable
// even before any row of a given type has been logged.
export const ACTIVITY_TYPES = [
  'login',
  'logout',
  'demo-edit',
  'mcp-upsert',
  'mcp-delete',
  'config-web',
  'config-phone',
  'user-create',
  'user-update',
  'user-delete',
  'voice-create',
  'voice-update',
  'voice-delete',
  'call-start',
  'call-end',
];

// activity-type → localized human label. Mirrors enums.js: te() falls back to
// the raw code so an unknown/forward-compat type never renders a literal i18n
// key path. The raw `type` stays the schema contract; only render-time calls
// this.
export function activityTypeLabel(type) {
  if (!type) return '';
  const key = `activity.types.${type}`;
  return i18n.global.te(key) ? i18n.global.t(key) : type;
}

// Dropdown options for the type filter (localized labels, raw values).
export function activityTypeOptions() {
  return ACTIVITY_TYPES.map((t) => ({ label: activityTypeLabel(t), value: t }));
}

// status → naive-ui tag type. Backend writes "success" by default and
// "error"/"failure" on failed mutations; be forgiving about either spelling.
export function statusTagType(status) {
  const s = (status || '').toLowerCase();
  if (s === 'success' || s === 'ok') return 'success';
  if (s === 'error' || s === 'failure' || s === 'failed') return 'error';
  if (s === 'warning' || s === 'warn') return 'warning';
  return 'default';
}

// filters → query-params for api.activity(). Mirrors HistoryView.buildQueryParams:
//   - empty/whitespace strings are dropped (never narrow the backend filter)
//   - dateRange is an [startMs, endMs] pair from n-date-picker; each end is
//     mapped to the backend's UTC YYYY-MM-DD `from`/`to` day strings.
//   - cursor is appended only when paginating (withCursor) and present.
// PURE: takes plain values, returns a plain object — no reactive deps.
export function buildActivityParams(filters = {}, { cursor = null, withCursor = false, limit } = {}) {
  const p = {};
  const actor = typeof filters.actor === 'string' ? filters.actor.trim() : '';
  if (actor) p.actor = actor;
  if (filters.type) p.type = filters.type;
  const dr = filters.dateRange;
  if (Array.isArray(dr) && dr.length === 2) {
    if (dr[0] != null && dr[0] !== '') p.from = msToUtcDay(dr[0]);
    if (dr[1] != null && dr[1] !== '') p.to = msToUtcDay(dr[1]);
  }
  if (limit != null) p.limit = limit;
  if (withCursor && cursor) p.cursor = cursor;
  return p;
}

// epoch-ms → UTC YYYY-MM-DD (the backend's `day` partition-key format).
export function msToUtcDay(ms) {
  const n = typeof ms === 'number' ? ms : Number(ms);
  if (!Number.isFinite(n)) return '';
  return new Date(n).toISOString().slice(0, 10);
}

// epoch-ms (or seconds, tolerated) → "YYYY-MM-DD HH:MM:SSZ" for the table /
// detail. Activity rows store `ts` in MILLISECONDS (activity_store now_ms), but
// tolerate a seconds-scale value defensively (same guard as HistoryView).
export function formatTs(ts) {
  if (ts == null || ts === '') return '';
  const n = typeof ts === 'number' ? ts : Number(ts);
  if (!Number.isFinite(n)) return String(ts);
  const ms = n < 1e12 ? n * 1000 : n;
  try {
    return new Date(ms).toISOString().replace('T', ' ').replace(/\.\d{3}Z$/, 'Z');
  } catch {
    return String(ts);
  }
}

// Shape one raw API row into the flat record the table renders. Pure so the
// "render rows" expectation is testable without a DOM mount: the view's
// columns read exactly these fields. `detail` is passed through untouched (it
// was already sanitized server-side) for the detail modal.
export function toActivityRow(raw = {}) {
  return {
    ts: raw.ts ?? null,
    tsText: formatTs(raw.ts),
    actor: raw.actor || '',
    actorRole: raw.actor_role || '',
    type: raw.type || '',
    typeLabel: activityTypeLabel(raw.type),
    target: raw.target || '',
    status: raw.status || '',
    error: raw.error || '',
    detail: raw.detail && typeof raw.detail === 'object' ? raw.detail : {},
    // stable key for n-data-table (ts_id is unique per row)
    ts_id: raw.ts_id || `${raw.ts || ''}#${raw.actor || ''}#${raw.type || ''}`,
  };
}

// Map an API response { items, cursor } into shaped rows + next cursor.
export function toActivityRows(items) {
  if (!Array.isArray(items)) return [];
  return items.map(toActivityRow);
}
