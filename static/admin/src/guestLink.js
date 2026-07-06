// Pure helpers for the admin temporary guest-experience link (tech_design §3.3).
// Kept DOM-free so the link construction is unit-testable in isolation
// (src/__tests__/guestLink.spec.js) without mounting a view or touching
// window. The view passes window.location.origin in at call time.

// Build the shareable guest link from an origin and a freshly-minted token.
// The SPA uses hash-history (createWebHashHistory) so guest links are
// `${origin}/#/guest?token=…`. The token is URL-encoded so JWT chars that are
// query-unsafe (rare, but `+` / `=` padding can appear) survive a round-trip.
export function buildGuestLink(origin, token) {
  return `${origin}/#/guest?token=${encodeURIComponent(token)}`;
}

// TTL options for the generate-link modal (minutes). Default is 60 (1 hour),
// matching the backend GUEST_TTL_DEFAULT_MIN. All are <= the backend
// GUEST_TTL_MAX_MIN (1440) hard cap.
export const GUEST_TTL_OPTIONS = [15, 30, 60, 120, 240];
export const GUEST_TTL_DEFAULT = 60;

// Build the role-based sider menu key list. Pure so the role→menu mapping is
// unit-testable without mounting App.vue. Returns the set of *route keys* a
// given role may see in the nav; App.vue's menuOptions consults this so a
// guest gets a Talk-ONLY menu (no My History / Monitor / admin group).
//   - guest: ['talk'] only
//   - admin: full set (call + monitor + admin group)
//   - user (or anything else): call group only (talk + my-history)
export function menuKeysForRole(role) {
  if (role === 'guest') return ['talk'];
  if (role === 'admin') {
    return [
      'talk', 'my-history', 'monitor',
      'dashboard', 'history', 'activity', 'demos', 'mcp', 'voices',
      'web', 'phone', 'users',
    ];
  }
  return ['talk', 'my-history'];
}
