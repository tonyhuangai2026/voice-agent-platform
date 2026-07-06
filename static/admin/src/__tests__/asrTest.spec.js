// @vitest-environment jsdom
//
// T2 ASR A/B test tool (tech_design §3-§4):
//   - openAsrTestWs builds a /asr-test/ws?token=… URL (mirrors openTalkWs)
//   - routeAsrMessage routing helper is pure + exact
//   - AsrTestView mounts, renders both panes + Start/Stop, and a fake
//     {stream:'B'} message lands in pane B and NOT pane A.
//
// jsdom is selected per-file (docblock above) so the rest of the suite keeps
// running in the default node environment, unchanged.

import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import { mount } from '@vue/test-utils';

import { openAsrTestWs } from '../ws.js';
import { routeAsrMessage, ASR_STREAMS, ASR_B_MODE_DEFAULT } from '../asrTest.js';

// naive-ui's useMessage() requires an n-message-provider ancestor; the view
// only uses it for error toasts, so stub it (and the few components the view
// renders) to a no-op. We keep the real component tags as passthrough stubs.
vi.mock('naive-ui', () => ({
  useMessage: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  NText: { name: 'NText', template: '<span><slot /></span>' },
  NIcon: { name: 'NIcon', template: '<i><slot /></i>' },
  NSwitch: { name: 'NSwitch', template: '<button class="n-switch"><slot /></button>' },
  NSelect: { name: 'NSelect', props: ['value', 'options'], template: '<select class="n-select"></select>' },
}));

// The view imports Recorder from audio.js; mounting must not touch real audio.
vi.mock('../audio.js', () => ({
  Recorder: class {
    async start() {}
    stop() {}
  },
}));

describe('routeAsrMessage', () => {
  it('exposes the two streams in display order (A single, B multi)', () => {
    expect(ASR_STREAMS).toEqual(['A', 'B']);
    expect(ASR_B_MODE_DEFAULT).toBe('multiple');
  });

  it('routes an interim (non-final) transcript', () => {
    expect(routeAsrMessage({ stream: 'A', text: 'hi', is_final: false })).toEqual({
      stream: 'A',
      kind: 'interim',
      text: 'hi',
      is_final: false,
      lang: null,
      error: null,
    });
  });

  it('routes a finalized transcript and keeps lang', () => {
    expect(routeAsrMessage({ stream: 'B', text: 'hello', is_final: true, lang: 'en-US' })).toEqual({
      stream: 'B',
      kind: 'final',
      text: 'hello',
      is_final: true,
      lang: 'en-US',
      error: null,
    });
  });

  it('routes a per-stream error message', () => {
    const r = routeAsrMessage({ stream: 'A', error: 'boom' });
    expect(r.kind).toBe('error');
    expect(r.error).toBe('boom');
    expect(r.stream).toBe('A');
  });

  it('ignores messages with no/unknown stream tag', () => {
    expect(routeAsrMessage({ text: 'x', is_final: true })).toBeNull();
    expect(routeAsrMessage({ stream: 'C', text: 'x' })).toBeNull();
    expect(routeAsrMessage(null)).toBeNull();
  });
});

describe('openAsrTestWs URL assembly', () => {
  let captured;

  beforeEach(() => {
    captured = [];
    vi.stubGlobal(
      'WebSocket',
      class {
        constructor(url) {
          captured.push(url);
          this.url = url;
        }
      },
    );
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ token: 'TOK' }) })));
    vi.stubGlobal('location', { protocol: 'https:', host: 'demo.example' });
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('builds /asr-test/ws?token=… with no mode', async () => {
    const ws = await openAsrTestWs();
    const url = new URL(captured[0]);
    expect(url.pathname).toBe('/asr-test/ws');
    expect(url.searchParams.get('token')).toBe('TOK');
    expect([...url.searchParams.keys()]).toEqual(['token']);
    expect(ws.binaryType).toBe('arraybuffer');
  });

  it('appends &mode= when provided', async () => {
    await openAsrTestWs({ mode: 'multiple' });
    const url = new URL(captured[0]);
    expect(url.pathname).toBe('/asr-test/ws');
    expect(url.searchParams.get('token')).toBe('TOK');
    expect(url.searchParams.get('mode')).toBe('multiple');
  });

  it('drops empty/null params (token-only URL)', async () => {
    await openAsrTestWs({ mode: '' });
    const url = new URL(captured[0]);
    expect(url.searchParams.has('mode')).toBe(false);
    expect(url.searchParams.get('token')).toBe('TOK');
  });

  it('appends &stability= when provided (stream B latency tuning)', async () => {
    await openAsrTestWs({ mode: 'multiple', stability: 'medium' });
    const url = new URL(captured[0]);
    expect(url.searchParams.get('stability')).toBe('medium');
  });
});

describe('ASR stability options', () => {
  it('default is high; options cover low/medium/high', async () => {
    const m = await import('../asrTest.js');
    expect(m.ASR_B_STABILITY_DEFAULT).toBe('high');
    expect(m.ASR_B_STABILITY_LEVELS).toEqual(['low', 'medium', 'high']);
    expect(m.ASR_STABILITY_OPTIONS.map((o) => o.value)).toEqual(['low', 'medium', 'high']);
  });
});

describe('AsrTestView', () => {
  let AsrTestView;

  beforeEach(async () => {
    // No real socket should open while mounting; the component only constructs
    // a WS inside start() (user-initiated), so a passthrough stub is enough.
    vi.stubGlobal('WebSocket', class {});
    AsrTestView = (await import('../views/AsrTestView.vue')).default;
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('mounts and renders both panes + Start/Stop + the STT-only note', () => {
    const wrapper = mount(AsrTestView);
    expect(wrapper.find('[data-test="asr-pane-A"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="asr-pane-B"]').exists()).toBe(true);
    expect(wrapper.find('[data-test="asr-pane-A"]').text()).toContain('单语言 zh-HK');
    expect(wrapper.find('[data-test="asr-pane-B"]').text()).toContain('多语言 zh-HK+en-US');

    const btn = wrapper.find('[data-test="asr-toggle"]');
    expect(btn.exists()).toBe(true);
    expect(btn.text()).toContain('Start');

    expect(wrapper.find('[data-test="asr-note"]').text()).toContain('仅测 STT,不影响正式通话');
  });

  it('routes a {stream:B} message into pane B and NOT pane A', async () => {
    const wrapper = mount(AsrTestView);
    // Drive the exposed applyMessage (the same path ws.onmessage uses).
    wrapper.vm.applyMessage({ stream: 'B', text: 'hi', is_final: true });
    await wrapper.vm.$nextTick();

    const paneB = wrapper.find('[data-test="asr-pane-B"]');
    const paneA = wrapper.find('[data-test="asr-pane-A"]');
    expect(paneB.text()).toContain('hi');
    expect(paneA.text()).not.toContain('hi');

    // Sanity: a {stream:A} message lands only in pane A.
    wrapper.vm.applyMessage({ stream: 'A', text: 'yo', is_final: true });
    await wrapper.vm.$nextTick();
    expect(wrapper.find('[data-test="asr-pane-A"]').text()).toContain('yo');
    expect(wrapper.find('[data-test="asr-pane-B"]').text()).not.toContain('yo');
  });
});
