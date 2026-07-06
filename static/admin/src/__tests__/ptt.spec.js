import { describe, it, expect, beforeEach } from 'vitest';
import {
  gateFrame,
  deriveMicOpen,
  shouldEnterTalking,
  readPtt,
  writePtt,
  PTT_STORAGE_KEY,
} from '../audio.js';

// T2 Push-to-Talk pure-logic unit tests (tech_design §2). DOM-free — these
// helpers are deliberately framework-free so they run without jsdom.

describe('gateFrame', () => {
  it('returns the original buffer (same reference) when micOpen=true', () => {
    const buf = new ArrayBuffer(640);
    // seed some non-zero bytes to prove it is untouched
    new Uint8Array(buf).set([1, 2, 3, 255], 0);
    const out = gateFrame(buf, true);
    expect(out).toBe(buf); // identity — no copy, raw frame forwarded
    expect(new Uint8Array(out).slice(0, 4)).toEqual(new Uint8Array([1, 2, 3, 255]));
  });

  it('returns an equal-length all-zero buffer when micOpen=false', () => {
    const buf = new ArrayBuffer(640);
    new Uint8Array(buf).fill(0xff); // make the source non-zero
    const out = gateFrame(buf, false);
    expect(out).not.toBe(buf); // a fresh buffer, not the original
    expect(out.byteLength).toBe(buf.byteLength); // equal length → same cadence
    const view = new Uint8Array(out);
    expect(view.every((b) => b === 0)).toBe(true); // all zero (silence)
  });

  it('preserves byteLength for arbitrary frame sizes when gated', () => {
    for (const n of [0, 2, 320, 640, 1024]) {
      const out = gateFrame(new ArrayBuffer(n), false);
      expect(out.byteLength).toBe(n);
    }
  });
});

describe('deriveMicOpen', () => {
  it('is always true when PTT is off, regardless of holding', () => {
    expect(deriveMicOpen(false, false)).toBe(true);
    expect(deriveMicOpen(false, true)).toBe(true);
  });

  it('equals holding when PTT is on', () => {
    expect(deriveMicOpen(true, false)).toBe(false);
    expect(deriveMicOpen(true, true)).toBe(true);
  });
});

describe('shouldEnterTalking (spacebar repeat filter)', () => {
  it('enters talking on a fresh Space keydown', () => {
    expect(shouldEnterTalking({ code: 'Space', repeat: false })).toBe(true);
    expect(shouldEnterTalking({ key: ' ', repeat: false })).toBe(true);
    expect(shouldEnterTalking({ key: 'Spacebar', repeat: false })).toBe(true);
  });

  it('filters auto-repeat: repeat=true never re-enters talking', () => {
    expect(shouldEnterTalking({ code: 'Space', repeat: true })).toBe(false);
  });

  it('ignores non-space keys', () => {
    expect(shouldEnterTalking({ code: 'Enter', repeat: false })).toBe(false);
    expect(shouldEnterTalking({ key: 'a', repeat: false })).toBe(false);
  });

  it('is safe on null/undefined events', () => {
    expect(shouldEnterTalking(null)).toBe(false);
    expect(shouldEnterTalking(undefined)).toBe(false);
  });

  it('simulating a held key: first keydown enters, subsequent repeats do not', () => {
    const events = [
      { code: 'Space', repeat: false },
      { code: 'Space', repeat: true },
      { code: 'Space', repeat: true },
      { code: 'Space', repeat: true },
    ];
    const entries = events.filter(shouldEnterTalking);
    expect(entries.length).toBe(1); // only the first keydown counts
  });
});

describe('PTT localStorage wrapper', () => {
  // Minimal in-memory storage stub so the wrapper is testable without jsdom.
  let store;
  const fakeStorage = {
    getItem: (k) => (k in store ? store[k] : null),
    setItem: (k, v) => {
      store[k] = String(v);
    },
  };

  beforeEach(() => {
    store = {};
  });

  it('defaults to false (off) when nothing is persisted', () => {
    expect(readPtt(fakeStorage)).toBe(false);
  });

  it('round-trips true: writePtt(true) then readPtt() === true', () => {
    writePtt(true, fakeStorage);
    expect(store[PTT_STORAGE_KEY]).toBe('true');
    expect(readPtt(fakeStorage)).toBe(true);
  });

  it('round-trips false: writePtt(false) then readPtt() === false', () => {
    writePtt(false, fakeStorage);
    expect(store[PTT_STORAGE_KEY]).toBe('false');
    expect(readPtt(fakeStorage)).toBe(false);
  });

  it('only "true" reads back as true (any other string → false)', () => {
    store[PTT_STORAGE_KEY] = 'yes';
    expect(readPtt(fakeStorage)).toBe(false);
  });

  it('readPtt swallows storage errors and returns false', () => {
    const throwing = {
      getItem() {
        throw new Error('SecurityError: storage disabled');
      },
    };
    expect(readPtt(throwing)).toBe(false);
  });

  it('writePtt swallows storage errors (no throw)', () => {
    const throwing = {
      setItem() {
        throw new Error('QuotaExceededError');
      },
    };
    expect(() => writePtt(true, throwing)).not.toThrow();
  });
});
