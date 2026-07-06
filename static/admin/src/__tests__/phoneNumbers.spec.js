// @vitest-environment jsdom
//
// T3: PhoneDefaultsView read-only "VC ↔ phone-number" block.
// Verifies the three states (rows / empty / error) driven by api.phoneNumbers().

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { mount, flushPromises } from '@vue/test-utils';

// api.phoneNumbers is the data source; mock it per-test. vi.mock is hoisted
// above imports, so the mock var must be created via vi.hoisted (not a plain
// const, which would be in the TDZ when the hoisted factory runs).
const { phoneNumbersMock } = vi.hoisted(() => ({ phoneNumbersMock: vi.fn() }));
vi.mock('../api.js', () => ({
  api: { phoneNumbers: (...a) => phoneNumbersMock(...a) },
}));

// useI18n() needs the plugin installed; mock it to a key-returning t() (with
// {msg} interpolation) so we can assert which message rendered, locale-free.
vi.mock('vue-i18n', () => ({
  useI18n: () => ({
    t: (key, params) =>
      params && params.msg !== undefined ? `${key}:${params.msg}` : key,
  }),
}));

// DefaultsForm pulls in the whole config form (incl. a Pinia store); stub it to
// an inert tag. Mock path is resolved relative to THIS test file.
vi.mock('../views/DefaultsForm.vue', () => ({
  default: { name: 'DefaultsForm', template: '<div class="defaults-form-stub" />' },
}));

// naive-ui: passthrough stubs (we assert on data-test attrs + text, not styling).
vi.mock('naive-ui', () => ({
  useMessage: () => ({ error: vi.fn(), success: vi.fn(), warning: vi.fn(), info: vi.fn() }),
  NCard: { name: 'NCard', template: '<div><slot /></div>' },
  NTable: { name: 'NTable', template: '<table><slot /></table>' },
  NText: { name: 'NText', template: '<span><slot /></span>' },
  NAlert: { name: 'NAlert', template: '<div><slot /></div>' },
  NEmpty: { name: 'NEmpty', props: ['description'], template: '<div class="n-empty">{{ description }}</div>' },
  NSpin: { name: 'NSpin', template: '<div><slot /></div>' },
}));

import PhoneDefaultsView from '../views/PhoneDefaultsView.vue';

// useI18n is mocked above, so no per-mount i18n wiring is needed.
const global = {};

beforeEach(() => {
  phoneNumbersMock.mockReset();
});

describe('PhoneDefaultsView — VC↔number table', () => {
  it('renders a row per voice_connector entry', async () => {
    phoneNumbersMock.mockResolvedValue({
      voice_connectors: [
        { voice_connector_id: 'vc-a', voice_connector_name: 'yue-test', e164: '+15550001111', status: 'Assigned' },
        { voice_connector_id: 'vc-b', voice_connector_name: 'nova-bot-test', e164: '+15550002222', status: 'Assigned' },
      ],
      error: null,
    });
    const w = mount(PhoneDefaultsView, { global });
    await flushPromises();
    const rows = w.findAll('[data-test="pn-row"]');
    expect(rows).toHaveLength(2);
    expect(w.find('[data-test="pn-table"]').exists()).toBe(true);
    expect(w.text()).toContain('+15550001111');
    expect(w.text()).toContain('yue-test');
    expect(w.find('[data-test="pn-error"]').exists()).toBe(false);
  });

  it('shows the empty state when there are no voice connectors', async () => {
    phoneNumbersMock.mockResolvedValue({ voice_connectors: [], error: null });
    const w = mount(PhoneDefaultsView, { global });
    await flushPromises();
    expect(w.find('[data-test="pn-empty"]').exists()).toBe(true);
    expect(w.findAll('[data-test="pn-row"]')).toHaveLength(0);
  });

  it('shows the degraded error notice when backend returns an error field', async () => {
    phoneNumbersMock.mockResolvedValue({ voice_connectors: [], error: 'AccessDeniedException: not authorized' });
    const w = mount(PhoneDefaultsView, { global });
    await flushPromises();
    const err = w.find('[data-test="pn-error"]');
    expect(err.exists()).toBe(true);
    expect(err.text()).toContain('AccessDeniedException');
    // empty state suppressed while an error is shown
    expect(w.find('[data-test="pn-empty"]').exists()).toBe(false);
  });

  it('does not crash on a thrown request (network/non-200) — shows error', async () => {
    phoneNumbersMock.mockRejectedValue(new Error('403 forbidden'));
    const w = mount(PhoneDefaultsView, { global });
    await flushPromises();
    expect(w.find('[data-test="pn-error"]').exists()).toBe(true);
    expect(w.findAll('[data-test="pn-row"]')).toHaveLength(0);
  });

  it('renders "no number" for a VC with null e164', async () => {
    phoneNumbersMock.mockResolvedValue({
      voice_connectors: [
        { voice_connector_id: 'vc-empty', voice_connector_name: 'no-num', e164: null, status: null },
      ],
      error: null,
    });
    const w = mount(PhoneDefaultsView, { global });
    await flushPromises();
    expect(w.findAll('[data-test="pn-row"]')).toHaveLength(1);
    // the t() stub returns the key for the "none" label
    expect(w.text()).toContain('phoneNumbers.none');
  });
});
