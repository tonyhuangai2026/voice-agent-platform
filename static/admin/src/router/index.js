import { createRouter, createWebHashHistory } from 'vue-router';
import { api } from '../api.js';

const DashboardView = () => import('../views/DashboardView.vue');
const HistoryView = () => import('../views/HistoryView.vue');
const WebDefaultsView = () => import('../views/WebDefaultsView.vue');
const PhoneDefaultsView = () => import('../views/PhoneDefaultsView.vue');
const DemosView = () => import('../views/DemosView.vue');
const McpServersView = () => import('../views/McpServersView.vue');
const VoicesView = () => import('../views/VoicesView.vue');
const UsersView = () => import('../views/UsersView.vue');
const ActivityLogView = () => import('../views/ActivityLogView.vue');
const LoginView = () => import('../views/LoginView.vue');
const SetupView = () => import('../views/SetupView.vue');
// Public landing for a temporary admin-minted guest link (tech_design §3.1):
// redeems ?token via POST /api/auth/guest-login, then replaces to /talk.
const GuestLanding = () => import('../views/GuestLanding.vue');
// Call views merged in from the old demo SPA (tech_design §3). MyHistoryView is
// the per-user "my calls" view (GET /api/history) — distinct from the admin-only
// full HistoryView above (GET /api/admin/history).
const TalkView = () => import('../views/TalkView.vue');
const MonitorView = () => import('../views/MonitorView.vue');
const MyHistoryView = () => import('../views/MyHistoryView.vue');
// ASR A/B test tool (tech_design §3-§4): a STT-only diagnostic that runs one
// mic through two Transcribe streams (single zh-HK vs multi zh-HK+en-US) for
// 粤英混说 comparison. Admin-gated by the beforeEach guard below; deliberately
// NOT wired into the App.vue nav menu — reachable by direct URL (#/asr-test).
const AsrTestView = () => import('../views/AsrTestView.vue');

// SPA now serves at the site root (single-page merge, tech_design §2). Hash
// history with base '/' keeps client-side routing working under the FastAPI
// StaticFiles catch-all mount without a server rewrite.
export const router = createRouter({
  history: createWebHashHistory('/'),
  routes: [
    { path: '/login', name: 'login', component: LoginView, meta: { public: true, title: 'Login' } },
    { path: '/setup', name: 'setup', component: SetupView, meta: { public: true, title: 'Setup' } },
    // Public — establishes its own guest session by redeeming the link token.
    { path: '/guest', name: 'guest', component: GuestLanding, meta: { public: true, title: 'Guest' } },
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: DashboardView, meta: { title: 'Dashboard' } },
    { path: '/history', name: 'history', component: HistoryView, meta: { title: '历史记录' } },
    { path: '/web', name: 'web', component: WebDefaultsView, meta: { title: 'Web 默认' } },
    { path: '/phone', name: 'phone', component: PhoneDefaultsView, meta: { title: 'Phone 默认' } },
    { path: '/demos', name: 'demos', component: DemosView, meta: { title: '场景配置' } },
    { path: '/mcp-servers', name: 'mcp', component: McpServersView, meta: { title: 'MCP Servers' } },
    { path: '/voices', name: 'voices', component: VoicesView, meta: { title: '语音管理' } },
    { path: '/users', name: 'users', component: UsersView, meta: { title: '用户管理' } },
    // Admin operations audit log (Part B B.5). Admin-only — backend enforces
    // require_admin on GET /api/admin/activity and App.vue gates the menu entry
    // into the admin group. Distinct from /history (call history) and
    // /my-history (the caller's own web calls).
    { path: '/activity', name: 'activity', component: ActivityLogView, meta: { title: '操作日志' } },
    // Call views (tech_design §3). Route names talk / monitor / my-history do
    // not collide with existing admin routes; menu wiring/role gating is T4.
    { path: '/talk', name: 'talk', component: TalkView, meta: { title: '通话演示' } },
    { path: '/monitor', name: 'monitor', component: MonitorView, meta: { title: '通话监听' } },
    { path: '/my-history', name: 'my-history', component: MyHistoryView, meta: { title: '我的通话历史' } },
    // ASR A/B test tool — admin-gated (the guard below redirects guests away;
    // App.vue hides it from the menu so it is direct-URL only).
    { path: '/asr-test', name: 'asr-test', component: AsrTestView, meta: { title: 'ASR Test' } },
  ],
});

// Global auth guard (tech_design §2 / §4). Every navigation first probes
// GET /api/auth/setup-status to decide whether the deploy still needs
// first-run admin setup, THEN falls through to the session check via
// GET /api/auth/me (cookie-based). Unauthenticated → /login. Visiting /login
// while already authenticated bounces to the home page.
router.beforeEach(async (to) => {
  // --- First-run setup gate (runs BEFORE the me() session check) ----------
  // FAIL-SAFE: if the probe errors (network / 5xx) treat as needs_setup=false
  // and fall through to the normal login flow — never trap the user on /setup.
  // The backend is authoritative (the setup endpoint 409s once initialized),
  // so failing open here cannot be abused to reset an existing account.
  let needsSetup = false;
  try {
    const status = await api.setupStatus();
    needsSetup = status?.needs_setup === true;
  } catch (e) {
    needsSetup = false;
  }

  if (needsSetup) {
    // Uninitialized deploy: force everything (including /login) to /setup;
    // only /setup itself is allowed through.
    return to.name === 'setup' ? true : { name: 'setup' };
  }

  // Initialized deploy: /setup is meaningless — bounce visitors away. We still
  // need the session state to choose the destination, so probe me() first.
  let authed = false;
  // Capture the role from THIS me() call — the guard keeps no cached `me`
  // (App.vue holds its own separately), so guest confinement below must read
  // the role from the same probe rather than assume a shared identity.
  let role = null;
  try {
    const me = await api.me();
    authed = true;
    role = me?.role ?? null;
  } catch (e) {
    // Only a 401 means "not logged in"; treat other errors (network/5xx) as
    // unauthenticated too so the guard fails safe to the login page.
    authed = false;
  }

  if (to.name === 'setup') {
    return authed ? { path: '/' } : { name: 'login' };
  }

  if (to.meta?.public) {
    // Already signed in? Skip the login page.
    if (to.name === 'login' && authed) return { path: '/' };
    return true;
  }

  if (!authed) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : undefined };
  }

  // Guest confinement (tech_design §3.2) — defense-in-depth for typed URLs.
  // A guest session may only reach Talk (and /guest, already handled above as
  // public); any other authed route is redirected to /talk. The menu already
  // hides the rest and the backend 403s admin APIs, so this is the third layer.
  if (role === 'guest' && to.name !== 'talk' && to.name !== 'guest') {
    return { name: 'talk' };
  }
  return true;
});
