#!/usr/bin/env node
// Headless screenshot harness for the UI-redesign (T6).
//
// Why this exists: the demo + admin SPAs fetch /api/* at runtime. To capture
// PRODUCT-LEVEL visuals headless without a live backend, we:
//   1. copy each built dist/ into a scratch serve dir,
//   2. inject a tiny <script> into index.html (BEFORE the app module) that
//      (a) sets the dark-mode localStorage key for the dark variant so the
//          real App.vue setup path runs applyDarkClass() -> <html class="dark">,
//          and (b) stubs window.fetch to return mock JSON for every /api/* call
//          so pages render POPULATED (fake config / metrics / demos / history).
//   3. serve the dir over http (python3 -m http.server) — needed because the
//      apps use ESM modules + absolute /assets paths,
//   4. drive chromium (snap) headless --screenshot at each hash route, once in
//      light and once in dark, writing PNGs into ~/snap/chromium/common/
//      (the snap-confined writable dir) then copying them to docs/ui-redesign/.
//
// This injects MOCK DATA only — it does not fabricate pixels. Every component
// renders itself from real built code; we merely feed it plausible API JSON.
// The dark variant exercises the BLOCKER-1 regression guard: self-drawn
// components (SVG charts, waveform area, BrandLogo/StatChip/MetricCard) must
// read html.dark { --vb-* } and render dark.
//
// Run: node docs/ui-redesign/screenshot-harness.mjs
// Output: docs/ui-redesign/*.png  +  a per-shot pixel-sanity summary.

import { spawn, spawnSync } from 'node:child_process';
import {
  cpSync, rmSync, mkdirSync, readFileSync, writeFileSync, copyFileSync,
  existsSync,
} from 'node:fs';
import { join, resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { setTimeout as sleep } from 'node:timers/promises';
import os from 'node:os';

const __dirname = dirname(fileURLToPath(import.meta.url));
const repoRoot = resolve(__dirname, '..', '..');
const outDir = __dirname; // docs/ui-redesign
const snapDir = join(os.homedir(), 'snap', 'chromium', 'common'); // snap-writable
const scratch = join(snapDir, 'ui-shot-serve');
const chromium = process.env.CHROMIUM_BIN || 'chromium';

// ---------------------------------------------------------------------------
// Mock API payloads (field names taken strictly from what the .vue code reads).
// ---------------------------------------------------------------------------
const MOCK = {
  // demo GET /api/config
  config: {
    languages: [
      { id: 'zh-CN', label: 'Chinese (Simplified)' },
      { id: 'zh-HK', label: 'Cantonese' },
      { id: 'en-US', label: 'English (US)' },
    ],
    engines: [
      { id: 'nova-sonic', label: 'Nova Sonic' },
      { id: 'pipeline', label: 'Pipeline' },
    ],
    demos: [
      { id: 'acme-security-support', label: 'ACME Security Support' },
      { id: 'telco-billing', label: 'Telco Billing' },
    ],
    scenarios: [
      { id: 'acme-security-support', label: 'ACME Security Support' },
      { id: 'telco-billing', label: 'Telco Billing' },
    ],
    default_demo: 'acme-security-support',
    default_scenario: 'acme-security-support',
    default_engine: 'nova-sonic',
    default_language: 'zh-CN',
    require_password: false,
  },
  // demo GET /api/history  (and /api/history/by-caller)
  history: {
    items: [
      { call_id: 'call-9a3f1c0b2d', caller: '+1 555-000-1111', started_at: nowMinus(6 * 60), duration_s: 182, summary_status: 'ready', outcome: 'task_completed' },
      { call_id: 'call-77be21aa90', caller: '+1 415-555-0142', started_at: nowMinus(42 * 60), duration_s: 95, summary_status: 'ready', outcome: 'user_requested' },
      { call_id: 'call-1d0c4e5f88', caller: '+1 206-555-7781', started_at: nowMinus(3 * 3600), duration_s: 410, summary_status: 'pending', outcome: 'transferred' },
      { call_id: 'call-b2a6f3119c', caller: '+44 20 7946 0991', started_at: nowMinus(20 * 3600), duration_s: 47, summary_status: 'failed', outcome: 'error' },
      { call_id: 'call-5e8d220a4f', caller: '(unknown)', started_at: nowMinus(26 * 3600), duration_s: 233, summary_status: 'ready', outcome: 'task_completed' },
    ],
    next_cursor: null,
  },
  // demo GET /api/history/{id}
  historyDetail: {
    call_id: 'call-9a3f1c0b2d', caller: '+1 555-000-1111', started_at: nowMinus(6 * 60), duration_s: 182,
    summary_status: 'ready', outcome: 'task_completed',
    summary: {
      model: 'anthropic.claude-3-5-sonnet',
      intent: 'Customer reported an offline NVR channel and requested a remote restart.',
      key_questions: ['Which channel is offline?', 'Has the camera lost power?'],
      action_items: ['Remote-restarted channel 3', 'Confirmed stream recovered'],
    },
    turns: [
      { role: 'assistant', text: 'Hi, this is ACME Security support. How can I help?', ts: 0 },
      { role: 'user', text: 'Channel 3 on my NVR went black this morning.', ts: 4 },
      { role: 'assistant', text: 'Let me check the device status and restart that channel for you.', ts: 9 },
    ],
  },
  // demo GET /api/calls
  calls: { calls: [] },
  // admin GET /api/admin/metrics
  metrics: {
    as_of: Math.floor(Date.now() / 1000),
    active_calls: 3,
    today: { total: 42, avg_duration_s: 185.5, p50_duration_s: 120.0, p95_duration_s: 450.5 },
    outcome_24h: { task_completed: 28, user_requested: 5, error: 4, unknown: 2, transferred: 2, timeout: 1 },
    transfer_rate_24h: 0.0714,
    demo_distribution_24h: { 'acme-security-support': 22, 'telco-billing': 15, 'weather-assistant': 5, unknown: 2 },
    engine_distribution_24h: { 'nova-sonic': 30, pipeline: 14 },
    peak_concurrent_24h: 5,
  },
  // admin GET /api/admin/demos
  demos: {
    demos: [
      { id: 'acme-security-support', label: 'ACME Security Support', lang: 'zh-HK', kb_chars: 2850, tools: ['get_device_status', 'restart_device'], mcp_servers: ['acme-security-api'] },
      { id: 'telco-billing', label: 'Telco Billing Support', lang: 'en-US', kb_chars: 5420, tools: ['check_balance', 'update_plan'], mcp_servers: [] },
      { id: 'weather-assistant', label: 'Weather Assistant', lang: 'zh-CN', kb_chars: 1200, tools: [], mcp_servers: ['weather-service'] },
      { id: 'retail-orders', label: 'Retail Order Status', lang: 'en-US', kb_chars: 3310, tools: ['check_balance'], mcp_servers: [] },
    ],
  },
  // admin GET /api/admin/tools
  tools: {
    tools: [
      { id: 'get_device_status', label: 'Get Device Status', description: 'Retrieve the current status of a device', scope: ['phone', 'web'], default_enabled: false, supported_langs: ['en-US', 'zh-CN', 'zh-HK'] },
      { id: 'restart_device', label: 'Restart Device', description: 'Restart a device remotely', scope: ['phone'], default_enabled: false, supported_langs: ['en-US', 'zh-CN'] },
      { id: 'check_balance', label: 'Check Account Balance', description: 'Check the current balance and usage', scope: ['web'], default_enabled: false, supported_langs: ['en-US'] },
      { id: 'update_plan', label: 'Update Plan', description: 'Modify subscription plan', scope: ['phone', 'web'], default_enabled: false, supported_langs: ['en-US'] },
      { id: 'transfer_call', label: 'Transfer to Agent', description: 'Transfer the call to a human agent', scope: ['phone'], default_enabled: false, supported_langs: ['en-US', 'zh-CN'] },
    ],
  },
  // admin GET /api/admin/options
  options: {
    languages: [{ id: 'zh-CN', label: 'Chinese (Simplified)' }, { id: 'zh-HK', label: 'Cantonese' }, { id: 'en-US', label: 'English (US)' }],
    engines: [{ id: 'nova-sonic', label: 'Nova Sonic' }, { id: 'pipeline', label: 'Pipeline' }],
    providers: [{ id: 'minimax', label: 'Minimax' }, { id: 'polly', label: 'AWS Polly' }],
    models: [{ id: 'anthropic.claude-3-5-sonnet', label: 'anthropic.claude-3-5-sonnet' }],
    minimax_models: [{ id: 'MiniMax-01', label: 'MiniMax-01' }],
    demos: [{ id: 'acme-security-support', label: 'ACME Security Support' }, { id: 'telco-billing', label: 'Telco Billing' }],
    scenarios: [{ id: 'acme-security-support', label: 'ACME Security Support' }],
    voices_by_provider: { minimax: [{ id: 'mimsinese_male', label: 'Mimsinese (Male)', language: 'zh-CN' }], polly: [{ id: 'Joanna', label: 'Joanna', language: 'en-US' }] },
    nova_sonic_voices: [{ id: 'nova-sonic-en-US', label: 'English (US)', gender: 'male', locale: 'en-US', lang_label: 'English', polyglot: false }],
    mcp_servers: [{ id: 'acme-security-api', label: 'ACME Security API', enabled: true }, { id: 'weather-service', label: 'Weather Service', enabled: true }, { id: 'legacy-soap', label: 'Legacy SOAP Bridge', enabled: false }],
  },
  // admin GET /api/admin/mcp-servers
  mcpServers: {
    mcp_servers: [
      { id: 'acme-security-api', label: 'ACME Security API', enabled: true },
      { id: 'weather-service', label: 'Weather Service', enabled: true },
      { id: 'legacy-soap', label: 'Legacy SOAP Bridge', enabled: false },
    ],
  },
  // admin GET /api/admin/config (web/phone defaults form)
  adminConfig: {
    web: { engine: 'nova-sonic', language: 'zh-CN', demo: 'acme-security-support', provider: 'minimax', voice: 'mimsinese_male', model: 'anthropic.claude-3-5-sonnet', nova_sonic_voice: 'nova-sonic-en-US' },
    phone: { engine: 'nova-sonic', language: 'zh-HK', demo: 'acme-security-support', provider: 'minimax', voice: 'mimsinese_male', model: 'anthropic.claude-3-5-sonnet', nova_sonic_voice: 'nova-sonic-en-US' },
  },
  health: { ok: true },
};

function nowMinus(sec) {
  return new Date(Date.now() - sec * 1000).toISOString();
}

// ---------------------------------------------------------------------------
// The fetch-stub injected into the page. Routes every /api/* path to MOCK.
// Serialised as a string with the MOCK object inlined.
// ---------------------------------------------------------------------------
function injectionScript(dark) {
  return `<script>
(function(){
  // 1) dark-mode: set BOTH SPA localStorage keys before the app module boots,
  //    so the real App.vue setup runs applyDarkClass() -> <html class="dark">.
  try {
    if (${dark}) { localStorage.setItem('vb-demo-theme','dark'); localStorage.setItem('vb-admin-theme','dark'); }
    else { localStorage.setItem('vb-demo-theme','light'); localStorage.setItem('vb-admin-theme','light'); }
  } catch(e){}

  // 2) stub fetch for /api/* — return mock JSON so pages render populated.
  var MOCK = ${JSON.stringify(MOCK)};
  function json(body){ return new Response(JSON.stringify(body), {status:200, headers:{'Content-Type':'application/json'}}); }
  function route(url){
    var u = url.split('?')[0];
    // admin (BASE = /api/admin)
    if (u === '/api/admin/metrics') return MOCK.metrics;
    if (u === '/api/admin/demos') return MOCK.demos;
    if (u === '/api/admin/tools') return MOCK.tools;
    if (u === '/api/admin/options') return MOCK.options;
    if (u === '/api/admin/mcp-servers') return MOCK.mcpServers;
    if (u === '/api/admin/config') return MOCK.adminConfig;
    if (u === '/api/admin/health') return MOCK.health;
    if (u.indexOf('/api/admin/demos/') === 0) return MOCK.demos.demos[0];
    if (u.indexOf('/api/admin/history/') === 0) return MOCK.historyDetail;
    if (u === '/api/admin/history') return MOCK.history;
    // demo
    if (u === '/api/config') return MOCK.config;
    if (u === '/api/calls') return MOCK.calls;
    if (u === '/api/history' || u === '/api/history/by-caller') return MOCK.history;
    if (u.indexOf('/api/history/') === 0) return MOCK.historyDetail;
    return null; // unknown -> fall through to {}
  }
  var origFetch = window.fetch ? window.fetch.bind(window) : null;
  window.fetch = function(input, init){
    var url = (typeof input === 'string') ? input : (input && input.url) || '';
    if (url.indexOf('/api/') !== -1) {
      var body = route(url);
      return Promise.resolve(json(body == null ? {} : body));
    }
    return origFetch ? origFetch(input, init) : Promise.resolve(json({}));
  };

  // 3) stub WebSocket (MonitorView / TalkView open WS) so nothing throws.
  try {
    var RealWS = window.WebSocket;
    window.WebSocket = function(){ this.readyState=0; this.send=function(){}; this.close=function(){}; this.addEventListener=function(){}; setTimeout(()=>{ this.readyState=1; if(typeof this.onopen==='function') this.onopen({}); },50); };
    window.WebSocket.OPEN = 1; window.WebSocket.CLOSED = 3;
  } catch(e){}
})();
</script>`;
}

// ---------------------------------------------------------------------------
// Build a serve dir for one SPA + theme variant with the injection baked in.
// ---------------------------------------------------------------------------
function prepServeDir(spa, dark) {
  const dist = join(repoRoot, 'static', spa, 'dist');
  if (!existsSync(dist)) throw new Error(`missing dist: ${dist} — run npm run build first`);
  const dir = join(scratch, `${spa}-${dark ? 'dark' : 'light'}`);
  rmSync(dir, { recursive: true, force: true });
  mkdirSync(dir, { recursive: true });
  // demo serves dist at server root (assets at /assets/*, index at /index.html).
  // admin's built index references absolute /admin/assets/* + uses base /admin/,
  // so copy admin's dist into a /admin subdir under the server root.
  const contentDir = spa === 'admin' ? join(dir, 'admin') : dir;
  mkdirSync(contentDir, { recursive: true });
  cpSync(dist, contentDir, { recursive: true });
  const idxPath = join(contentDir, 'index.html');
  let html = readFileSync(idxPath, 'utf8');
  html = html.replace('</head>', injectionScript(dark) + '\n</head>');
  writeFileSync(idxPath, html);
  return dir;
}

function startServer(dir, port) {
  const proc = spawn('python3', ['-m', 'http.server', String(port), '--bind', '127.0.0.1'], {
    cwd: dir, stdio: 'ignore',
  });
  return proc;
}

function shoot(url, outPng, width, height) {
  const args = [
    '--headless', '--no-sandbox', '--disable-gpu', '--hide-scrollbars',
    '--force-device-scale-factor=1',
    `--window-size=${width},${height}`,
    `--screenshot=${outPng}`,
    '--virtual-time-budget=6000',
    '--run-all-compositor-stages-before-draw',
    url,
  ];
  const r = spawnSync(chromium, args, { stdio: 'ignore', timeout: 60000 });
  return existsSync(outPng);
}

function pixelSanity(png) {
  const r = spawnSync('python3', ['-c', `
from PIL import Image
im = Image.open(${JSON.stringify(png)}).convert('RGB')
w,h = im.size
# sample a grid; report mean luminance + whether it's "mostly dark"
import itertools
pts = [(int(w*fx),int(h*fy)) for fx in (0.05,0.5,0.95) for fy in (0.05,0.5,0.95)]
lums = []
for (x,y) in pts:
    r_,g_,b_ = im.getpixel((min(x,w-1),min(y,h-1)))
    lums.append(0.299*r_+0.587*g_+0.114*b_)
mean = sum(lums)/len(lums)
print(f"{w}x{h} meanLum={mean:.0f} {'DARK' if mean<90 else 'LIGHT'}")
`], { encoding: 'utf8' });
  return (r.stdout || '').trim() || (r.stderr || '').trim();
}

// ---------------------------------------------------------------------------
// Shot plan. Each: spa, route hash, filename stem, viewport.
// ---------------------------------------------------------------------------
const SHOTS = [
  { spa: 'demo', hash: '#/talk', stem: 'demo-talkview-idle', w: 1440, h: 1000 },
  { spa: 'demo', hash: '#/history', stem: 'demo-historyview', w: 1440, h: 1000 },
  { spa: 'admin', hash: '#/dashboard', stem: 'admin-dashboard', w: 1600, h: 1100 },
  { spa: 'admin', hash: '#/demos', stem: 'admin-demos', w: 1600, h: 1100 },
];

const PORTS = { demo: 8731, admin: 8732 };

async function main() {
  rmSync(scratch, { recursive: true, force: true });
  mkdirSync(scratch, { recursive: true });
  const results = [];

  for (const dark of [false, true]) {
    const variant = dark ? 'dark' : 'light';
    // one server per spa per variant (different injected html)
    const servers = {};
    const dirs = {};
    for (const spa of ['demo', 'admin']) {
      dirs[spa] = prepServeDir(spa, dark);
      const port = PORTS[spa] + (dark ? 100 : 0);
      servers[spa] = { proc: startServer(dirs[spa], port), port };
    }
    await sleep(1200); // let http.server bind

    for (const shot of SHOTS) {
      const { port } = servers[shot.spa];
      // admin served at /admin/index.html (base /admin/), demo at /index.html
      const path = shot.spa === 'admin' ? `/admin/index.html` : `/index.html`;
      const url = `http://127.0.0.1:${port}${path}${shot.hash}`;
      const tmpPng = join(snapDir, `${shot.stem}-${variant}.png`);
      const ok = shoot(url, tmpPng, shot.w, shot.h);
      let sanity = ok ? pixelSanity(tmpPng) : 'NO FILE';
      const finalPng = join(outDir, `${shot.stem}-${variant}.png`);
      if (ok) copyFileSync(tmpPng, finalPng);
      results.push({ shot: `${shot.stem}-${variant}`, url, ok, sanity, file: ok ? finalPng : null });
      console.log(`[${ok ? 'OK ' : 'FAIL'}] ${shot.stem}-${variant}  ${sanity}`);
    }

    for (const spa of ['demo', 'admin']) servers[spa].proc.kill('SIGKILL');
    await sleep(300);
  }

  console.log('\n=== SUMMARY ===');
  for (const r of results) {
    console.log(`${r.ok ? 'OK ' : 'FAIL'}  ${r.shot.padEnd(28)} ${r.sanity}`);
  }
  // cleanup scratch serve dir (keep PNGs in docs/)
  rmSync(scratch, { recursive: true, force: true });
}

main().catch((e) => { console.error(e); process.exit(1); });
