import { describe, it, expect } from 'vitest';
import {
  buildGuestLink,
  menuKeysForRole,
  GUEST_TTL_OPTIONS,
  GUEST_TTL_DEFAULT,
} from '../guestLink.js';

// Pure-helper unit tests (tech_design §6). DOM-free — no mount, no window;
// the view passes window.location.origin into buildGuestLink at call time.

describe('buildGuestLink', () => {
  it('builds a hash-history /guest link with the token in the query', () => {
    expect(buildGuestLink('https://demo.example.com', 'abc123')).toBe(
      'https://demo.example.com/#/guest?token=abc123',
    );
  });

  it('URL-encodes tokens containing query-unsafe JWT characters', () => {
    // A JWT can contain '+', '/', '=' padding and '.' separators; only the
    // truly query-unsafe ones must be percent-encoded. encodeURIComponent
    // leaves '.', '-', '_', '~' intact (JWT base64url is safe), but escapes
    // '+', '/', '='.
    const token = 'aa.bb+cc/dd==';
    expect(buildGuestLink('https://x.io', token)).toBe(
      `https://x.io/#/guest?token=${encodeURIComponent(token)}`,
    );
    expect(buildGuestLink('https://x.io', token)).toContain('%2B'); // '+'
    expect(buildGuestLink('https://x.io', token)).toContain('%2F'); // '/'
    expect(buildGuestLink('https://x.io', token)).toContain('%3D'); // '='
  });

  it('preserves a bare origin without a trailing slash', () => {
    expect(buildGuestLink('http://localhost:5173', 't')).toBe(
      'http://localhost:5173/#/guest?token=t',
    );
  });
});

describe('GUEST_TTL_OPTIONS', () => {
  it('offers 15/30/60/120/240 with a default of 60', () => {
    expect(GUEST_TTL_OPTIONS).toEqual([15, 30, 60, 120, 240]);
    expect(GUEST_TTL_DEFAULT).toBe(60);
    expect(GUEST_TTL_OPTIONS).toContain(GUEST_TTL_DEFAULT);
  });
});

describe('menuKeysForRole', () => {
  it("confines a guest to Talk ONLY — no my-history/monitor/admin", () => {
    expect(menuKeysForRole('guest')).toEqual(['talk']);
  });

  it('gives a normal user the Call group (talk + my-history) but no admin/monitor', () => {
    const keys = menuKeysForRole('user');
    expect(keys).toEqual(['talk', 'my-history']);
    expect(keys).not.toContain('monitor');
    expect(keys).not.toContain('users');
  });

  it('gives an admin the full set including monitor + admin group', () => {
    const keys = menuKeysForRole('admin');
    expect(keys).toContain('talk');
    expect(keys).toContain('monitor');
    expect(keys).toContain('users');
    expect(keys).toContain('dashboard');
  });

  it('treats an unknown/empty role like a normal user (call group only)', () => {
    expect(menuKeysForRole(null)).toEqual(['talk', 'my-history']);
    expect(menuKeysForRole(undefined)).toEqual(['talk', 'my-history']);
  });
});
