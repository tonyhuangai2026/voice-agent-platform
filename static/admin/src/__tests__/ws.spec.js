import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { openTalkWs, demoLaunchParams, pickLaunchQuery } from '../ws.js';

// T1 pure-function + URL-assembly unit tests (tech_design §1, §2, §4.1).
// fetchWsToken is module-internal, so we drive openTalkWs through the same
// public seams it uses: global fetch (the /api/ws-token GET) and global
// WebSocket (which we capture to assert the assembled URL).

describe('demoLaunchParams', () => {
  it('no tools/mcp → only {scenario, lang}', () => {
    const p = demoLaunchParams({ id: 'it-helpdesk', lang: 'zh-HK' });
    expect(p).toEqual({ scenario: 'it-helpdesk', lang: 'zh-HK' });
    expect('engine' in p).toBe(false);
  });

  // tech_design §3: tools/MCP no longer force an engine (Nova Sonic supports
  // function-calling). A tool demo with no stored engine omits engine entirely.
  it('non-empty tools with no stored engine → no engine forced', () => {
    const p = demoLaunchParams({ id: 'x', lang: 'en', tools: ['end_call'] });
    expect(p).toEqual({ scenario: 'x', lang: 'en' });
    expect('engine' in p).toBe(false);
  });

  it('non-empty mcp_servers with no stored engine → no engine forced', () => {
    const p = demoLaunchParams({ id: 'connect-repair', lang: 'en', mcp_servers: ['repair'] });
    expect(p).toEqual({ scenario: 'connect-repair', lang: 'en' });
    expect('engine' in p).toBe(false);
  });

  it('empty tools AND empty mcp_servers → no engine', () => {
    const p = demoLaunchParams({ id: 'x', lang: 'en', tools: [], mcp_servers: [] });
    expect(p).toEqual({ scenario: 'x', lang: 'en' });
  });

  it('missing lang → no lang key', () => {
    const p = demoLaunchParams({ id: 'no-lang' });
    expect(p).toEqual({ scenario: 'no-lang' });
    expect('lang' in p).toBe(false);
  });

  // tech_design §5: a demo carrying its own engine/voice/provider emits them
  // (demo-first priority); fields the demo did not set are omitted.
  it('emits engine/voice/provider when the demo sets them', () => {
    const p = demoLaunchParams({
      id: 'd1',
      lang: 'zh-CN',
      engine: 'pipeline',
      provider: 'minimax',
      voice: 'mm-zh-f',
    });
    expect(p).toEqual({
      scenario: 'd1',
      lang: 'zh-CN',
      engine: 'pipeline',
      provider: 'minimax',
      voice: 'mm-zh-f',
    });
  });

  it('omits engine/voice/provider when the demo does not set them', () => {
    const p = demoLaunchParams({ id: 'd2', lang: 'en-US' });
    expect(p).toEqual({ scenario: 'd2', lang: 'en-US' });
    expect('engine' in p).toBe(false);
    expect('voice' in p).toBe(false);
    expect('provider' in p).toBe(false);
  });

  // T2: a demo carrying its own model (LLM) emits it; absent → omitted.
  it('emits model when the demo sets it', () => {
    const p = demoLaunchParams({
      id: 'dm',
      lang: 'zh-HK',
      engine: 'pipeline',
      model: 'nova-lite',
    });
    expect(p.model).toBe('nova-lite');
  });

  it('omits model when the demo does not set it', () => {
    const p = demoLaunchParams({ id: 'dm2', lang: 'en-US', engine: 'pipeline' });
    expect('model' in p).toBe(false);
  });

  it('nova-sonic demo (no tools) emits engine=nova-sonic + voice', () => {
    const p = demoLaunchParams({
      id: 'd3',
      lang: 'en-US',
      engine: 'nova-sonic',
      voice: 'matthew',
    });
    expect(p.engine).toBe('nova-sonic');
    expect(p.voice).toBe('matthew');
  });

  // Regression-direction: Nova Sonic supports tools/MCP, so a tools demo with
  // demo.engine==='nova-sonic' launches on Nova Sonic (NOT forced to pipeline).
  it('tools demo with demo.engine===nova-sonic emits engine=nova-sonic', () => {
    const p = demoLaunchParams({
      id: 'd4',
      lang: 'en-US',
      engine: 'nova-sonic',
      voice: 'matthew',
      tools: ['end_call'],
    });
    expect(p.engine).toBe('nova-sonic');
    expect(p.voice).toBe('matthew');
  });

  it('mcp_servers demo with demo.engine===nova-sonic emits engine=nova-sonic', () => {
    const p = demoLaunchParams({
      id: 'd5',
      lang: 'en-US',
      engine: 'nova-sonic',
      mcp_servers: ['repair'],
    });
    expect(p.engine).toBe('nova-sonic');
  });
});

describe('pickLaunchQuery', () => {
  it('keeps only whitelisted keys, drops unknown ones', () => {
    const out = pickLaunchQuery({
      scenario: 's',
      lang: 'en',
      engine: 'pipeline',
      voice: 'v',
      provider: 'p',
      model: 'm',
      minimax_model: 'mm',
      token: 'SHOULD_DROP',
      foo: 'bar',
    });
    expect(out).toEqual({
      scenario: 's',
      lang: 'en',
      engine: 'pipeline',
      voice: 'v',
      provider: 'p',
      model: 'm',
      minimax_model: 'mm',
    });
    expect('token' in out).toBe(false);
    expect('foo' in out).toBe(false);
  });

  it('empty query → empty object', () => {
    expect(pickLaunchQuery({})).toEqual({});
    expect(pickLaunchQuery(undefined)).toEqual({});
  });
});

describe('openTalkWs URL assembly', () => {
  let captured;

  beforeEach(() => {
    captured = [];
    // Capture the URL each WebSocket is constructed with; no real socket opens.
    vi.stubGlobal(
      'WebSocket',
      class {
        constructor(url) {
          captured.push(url);
          this.url = url;
        }
      }
    );
    // Mint a deterministic token via the /api/ws-token GET.
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: true, json: async () => ({ token: 'TOK' }) }))
    );
    // wsBaseUrl reads location.protocol/host.
    vi.stubGlobal('location', { protocol: 'https:', host: 'demo.example' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('no args → only token in query', async () => {
    await openTalkWs();
    const url = new URL(captured[0]);
    expect(url.pathname).toBe('/ws');
    expect(url.searchParams.get('token')).toBe('TOK');
    expect([...url.searchParams.keys()]).toEqual(['token']);
  });

  it('{scenario, lang} → url contains token & scenario & lang', async () => {
    await openTalkWs({ scenario: 'it-helpdesk', lang: 'zh-HK' });
    const url = new URL(captured[0]);
    expect(url.searchParams.get('token')).toBe('TOK');
    expect(url.searchParams.get('scenario')).toBe('it-helpdesk');
    expect(url.searchParams.get('lang')).toBe('zh-HK');
  });

  it('empty/null values are not appended', async () => {
    await openTalkWs({ scenario: 'x', lang: '', engine: null, voice: undefined });
    const url = new URL(captured[0]);
    expect(url.searchParams.get('scenario')).toBe('x');
    expect(url.searchParams.has('lang')).toBe(false);
    expect(url.searchParams.has('engine')).toBe(false);
    expect(url.searchParams.has('voice')).toBe(false);
  });

  it('still opens with token-only query when fetch fails (empty token guarded)', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => ({ ok: false, json: async () => ({}) }))
    );
    await openTalkWs({ scenario: 'x' });
    const url = new URL(captured[0]);
    expect(url.searchParams.has('token')).toBe(false);
    expect(url.searchParams.get('scenario')).toBe('x');
  });
});
