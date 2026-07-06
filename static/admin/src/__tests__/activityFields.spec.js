import { describe, it, expect, beforeAll } from 'vitest';
import { i18n } from '../i18n/index.js';
import {
  ACTIVITY_TYPES,
  activityTypeLabel,
  activityTypeOptions,
  statusTagType,
  buildActivityParams,
  msToUtcDay,
  formatTs,
  toActivityRow,
  toActivityRows,
} from '../activityFields.js';

// Pure-helper unit tests for the admin activity-log viewer (ActivityLogView.vue,
// tech_design Part B B.5). DOM-free — the two non-trivial mappings
// (filter→query-params and activity-type→human-label) plus row shaping live in
// activityFields.js so they're testable without mounting Vue. activityTypeLabel
// resolves real i18n keys — we pin the active locale to `en` so the label
// assertions are deterministic regardless of the test env's navigator.language.
beforeAll(() => {
  i18n.global.locale.value = 'en';
});

describe('ACTIVITY_TYPES — the closed set the backend (T3) emits', () => {
  it('is exactly the 15 documented activity types, in dropdown order', () => {
    expect(ACTIVITY_TYPES).toEqual([
      'login', 'logout', 'demo-edit', 'mcp-upsert', 'mcp-delete',
      'config-web', 'config-phone', 'user-create', 'user-update', 'user-delete',
      'voice-create', 'voice-update', 'voice-delete', 'call-start', 'call-end',
    ]);
  });
});

describe('activityTypeLabel — type → human label (i18n with raw fallback)', () => {
  it('maps known types to their localized label', () => {
    expect(activityTypeLabel('login')).toBe('Sign in');
    expect(activityTypeLabel('user-delete')).toBe('Delete user');
    expect(activityTypeLabel('voice-update')).toBe('Update voice');
    expect(activityTypeLabel('call-start')).toBe('Call started');
  });
  it('every known type resolves to a non-key label (no literal activity.types.* leaks)', () => {
    for (const t of ACTIVITY_TYPES) {
      const label = activityTypeLabel(t);
      expect(label).not.toContain('activity.types.');
      expect(label.length).toBeGreaterThan(0);
    }
  });
  it('falls back to the raw code for an unknown / forward-compat type', () => {
    expect(activityTypeLabel('some-future-type')).toBe('some-future-type');
  });
  it('empty / null → empty string', () => {
    expect(activityTypeLabel('')).toBe('');
    expect(activityTypeLabel(null)).toBe('');
    expect(activityTypeLabel(undefined)).toBe('');
  });
});

describe('activityTypeOptions — the type-filter dropdown source', () => {
  it('one option per type, raw code as value, localized label', () => {
    const opts = activityTypeOptions();
    expect(opts).toHaveLength(ACTIVITY_TYPES.length);
    expect(opts.map((o) => o.value)).toEqual(ACTIVITY_TYPES);
    const login = opts.find((o) => o.value === 'login');
    expect(login.label).toBe('Sign in');
  });
});

describe('statusTagType — status → naive-ui tag type', () => {
  it('success / ok → success', () => {
    expect(statusTagType('success')).toBe('success');
    expect(statusTagType('ok')).toBe('success');
    expect(statusTagType('SUCCESS')).toBe('success');
  });
  it('error / failure / failed → error', () => {
    expect(statusTagType('error')).toBe('error');
    expect(statusTagType('failure')).toBe('error');
    expect(statusTagType('failed')).toBe('error');
  });
  it('unknown / empty → default', () => {
    expect(statusTagType('')).toBe('default');
    expect(statusTagType(null)).toBe('default');
    expect(statusTagType('weird')).toBe('default');
  });
});

describe('msToUtcDay — epoch-ms → backend UTC YYYY-MM-DD', () => {
  it('maps a millisecond timestamp to its UTC day', () => {
    // 2026-06-26T12:00:00Z
    expect(msToUtcDay(Date.UTC(2026, 5, 26, 12, 0, 0))).toBe('2026-06-26');
  });
  it('non-finite → empty string', () => {
    expect(msToUtcDay('nope')).toBe('');
    expect(msToUtcDay(NaN)).toBe('');
  });
});

describe('buildActivityParams — filters → query-params (the backend contract)', () => {
  it('drops empty / whitespace actor and a null type', () => {
    expect(buildActivityParams({ actor: '   ', type: null, dateRange: null })).toEqual({});
  });
  it('trims actor and forwards a selected type', () => {
    expect(buildActivityParams({ actor: '  alice ', type: 'login' }))
      .toEqual({ actor: 'alice', type: 'login' });
  });
  it('maps the [startMs, endMs] date range to from/to UTC day strings', () => {
    const range = [Date.UTC(2026, 5, 1, 0, 0, 0), Date.UTC(2026, 5, 26, 23, 0, 0)];
    expect(buildActivityParams({ dateRange: range }))
      .toEqual({ from: '2026-06-01', to: '2026-06-26' });
  });
  it('includes limit when provided', () => {
    expect(buildActivityParams({}, { limit: 50 })).toEqual({ limit: 50 });
  });
  it('appends cursor only when withCursor AND a cursor is present', () => {
    expect(buildActivityParams({}, { cursor: 'c1', withCursor: false })).toEqual({});
    expect(buildActivityParams({}, { cursor: 'c1', withCursor: true })).toEqual({ cursor: 'c1' });
    expect(buildActivityParams({}, { cursor: null, withCursor: true })).toEqual({});
  });
  it('a partial date range (only start) emits only `from`', () => {
    expect(buildActivityParams({ dateRange: [Date.UTC(2026, 5, 1), null] }))
      .toEqual({ from: '2026-06-01' });
  });
});

describe('formatTs — epoch (ms or s) → readable UTC string', () => {
  it('formats a millisecond timestamp', () => {
    expect(formatTs(Date.UTC(2026, 5, 26, 8, 30, 15))).toBe('2026-06-26 08:30:15Z');
  });
  it('tolerates a seconds-scale value (defensive)', () => {
    const secs = Math.floor(Date.UTC(2026, 5, 26, 8, 30, 15) / 1000);
    expect(formatTs(secs)).toBe('2026-06-26 08:30:15Z');
  });
  it('empty / null → empty string', () => {
    expect(formatTs(null)).toBe('');
    expect(formatTs('')).toBe('');
  });
});

describe('toActivityRow / toActivityRows — shape raw API rows for the table', () => {
  const RAW = {
    actor: 'admin',
    actor_role: 'admin',
    type: 'user-delete',
    target: 'bob',
    detail: { username: 'bob' },
    status: 'success',
    ts: Date.UTC(2026, 5, 26, 8, 30, 15),
    day: '2026-06-26',
    ts_id: '1750000000000#abc',
  };

  it('flattens a raw row into the exact fields the columns render', () => {
    const row = toActivityRow(RAW);
    expect(row).toMatchObject({
      actor: 'admin',
      actorRole: 'admin',
      type: 'user-delete',
      typeLabel: 'Delete user',
      target: 'bob',
      status: 'success',
      tsText: '2026-06-26 08:30:15Z',
      ts_id: '1750000000000#abc',
    });
    expect(row.detail).toEqual({ username: 'bob' });
  });

  it('renders many rows newest-first as given, each with a stable key', () => {
    const rows = toActivityRows([
      RAW,
      { ...RAW, type: 'login', target: '', detail: null, ts_id: 'k2' },
      { ...RAW, type: 'voice-create', ts_id: 'k3' },
    ]);
    expect(rows).toHaveLength(3);
    expect(rows.map((r) => r.typeLabel)).toEqual(['Delete user', 'Sign in', 'Create voice']);
    // non-object detail is coerced to {} (safe for the modal's Object.entries)
    expect(rows[1].detail).toEqual({});
    // keys are unique
    expect(new Set(rows.map((r) => r.ts_id)).size).toBe(3);
  });

  it('synthesizes a key when ts_id is absent, and is null-safe', () => {
    const row = toActivityRow({ actor: 'x', type: 'login', ts: 1 });
    expect(row.ts_id).toContain('login');
    expect(toActivityRows(undefined)).toEqual([]);
    expect(toActivityRows(null)).toEqual([]);
  });
});
