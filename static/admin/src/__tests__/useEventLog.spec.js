import { describe, it, expect } from 'vitest';
import { mergeEvent, useEventLog, planLogSync, tailKey } from '../composables/useEventLog.js';

// T1 useEventLog merge-logic unit tests (tech_design §1, §6). Pure logic +
// reactive wrapper — no jsdom needed (Vue reactivity runs headless).

// --- helpers ---------------------------------------------------------------

// Drive a list of raw events through mergeEvent on a fresh rows array.
function merge(events) {
  const rows = [];
  for (const e of events) mergeEvent(rows, e);
  return rows;
}

function ev(type, t, extra = {}) {
  return { type, t, ...extra };
}

// --- mergeEvent: llm accumulation -----------------------------------------

describe('mergeEvent — llm_delta accumulation', () => {
  it('10 llm_delta → 1 llm row, text = concatenation', () => {
    const deltas = [];
    for (let i = 0; i < 10; i++) deltas.push(ev('llm_delta', i * 0.1, { text: `${i}` }));
    const rows = merge(deltas);
    expect(rows.length).toBe(1);
    expect(rows[0].type).toBe('llm_delta');
    expect(rows[0].text).toBe('0123456789');
    expect(rows[0]._llmInFlight).toBe(true); // still open (no llm_end yet)
  });

  it('llm_delta×N then llm_end → 1 closed llm_end row', () => {
    const rows = merge([
      ev('llm_delta', 0.0, { text: 'Hel' }),
      ev('llm_delta', 0.1, { text: 'lo ' }),
      ev('llm_delta', 0.2, { text: 'wor' }),
      ev('llm_delta', 0.3, { text: 'ld' }),
      ev('llm_end', 0.4, { text: 'Hello world' }),
    ]);
    expect(rows.length).toBe(1);
    expect(rows[0].type).toBe('llm_end');
    expect(rows[0].text).toBe('Hello world'); // llm_end final text replaces accumulation
    expect(rows[0]._llmInFlight).toBe(false);
  });

  it('llm_end with no text keeps the accumulated text', () => {
    const rows = merge([
      ev('llm_delta', 0.0, { text: 'abc' }),
      ev('llm_delta', 0.1, { text: 'def' }),
      ev('llm_end', 0.2, {}),
    ]);
    expect(rows.length).toBe(1);
    expect(rows[0].text).toBe('abcdef');
    expect(rows[0].type).toBe('llm_end');
  });
});

// --- mergeEvent: asr roll-up ----------------------------------------------

describe('mergeEvent — asr partial/final roll-up', () => {
  it('asr_partial×N then asr_final → 1 asr row = final text', () => {
    const rows = merge([
      ev('asr_partial', 0.0, { text: 'how' }),
      ev('asr_partial', 0.1, { text: 'how are' }),
      ev('asr_partial', 0.2, { text: 'how are you' }),
      ev('asr_final', 0.3, { text: 'how are you today' }),
    ]);
    expect(rows.length).toBe(1);
    expect(rows[0].type).toBe('asr_final');
    expect(rows[0].text).toBe('how are you today');
    expect(rows[0]._asrInFlight).toBe(false); // final closed it
  });

  it('asr_partial alone stays in-flight as a single row', () => {
    const rows = merge([
      ev('asr_partial', 0.0, { text: 'a' }),
      ev('asr_partial', 0.1, { text: 'ab' }),
    ]);
    expect(rows.length).toBe(1);
    expect(rows[0].type).toBe('asr_partial');
    expect(rows[0].text).toBe('ab');
    expect(rows[0]._asrInFlight).toBe(true);
  });

  it('a new asr utterance after a closed one becomes its own row', () => {
    const rows = merge([
      ev('asr_partial', 0.0, { text: 'first' }),
      ev('asr_final', 0.3, { text: 'first done' }),
      ev('asr_partial', 1.0, { text: 'second' }),
      ev('asr_final', 1.3, { text: 'second done' }),
    ]);
    expect(rows.length).toBe(2);
    expect(rows[0].text).toBe('first done');
    expect(rows[1].text).toBe('second done');
  });
});

// --- mergeEvent: boundary events + ordering -------------------------------

describe('mergeEvent — boundary events each own a row, in order', () => {
  it('user_speaking / tts_start / tts_end / bot_speaking each become a row', () => {
    const seq = [
      ev('user_speaking', 0.0, { value: true }),
      ev('tts_start', 0.5),
      ev('bot_speaking', 0.6, { value: true }),
      ev('tts_end', 2.0),
    ];
    const rows = merge(seq);
    expect(rows.length).toBe(4);
    expect(rows.map((r) => r.type)).toEqual([
      'user_speaking',
      'tts_start',
      'bot_speaking',
      'tts_end',
    ]);
  });
});

// --- mergeEvent: dedupe ----------------------------------------------------

describe('mergeEvent — <0.05s same type/value/text dedupe', () => {
  it('drops a duplicate inside the 0.05s window', () => {
    const rows = merge([
      ev('tts_start', 1.00, { value: true, text: 'x' }),
      ev('tts_start', 1.02, { value: true, text: 'x' }), // 0.02s → deduped
    ]);
    expect(rows.length).toBe(1);
  });

  it('keeps it when outside the window', () => {
    const rows = merge([
      ev('tts_start', 1.00, { value: true, text: 'x' }),
      ev('tts_start', 1.10, { value: true, text: 'x' }), // 0.10s → kept
    ]);
    expect(rows.length).toBe(2);
  });

  it('keeps it when text differs even within the window', () => {
    const rows = merge([
      ev('user_speaking', 1.00, { value: true, text: 'a' }),
      ev('user_speaking', 1.01, { value: true, text: 'b' }),
    ]);
    expect(rows.length).toBe(2);
  });
});

// --- mergeEvent: mixed realistic sequence ---------------------------------

describe('mergeEvent — mixed ~26-event sequence collapses to ~6 rows', () => {
  it('user_speaking → asr_partial×3 → asr_final → llm_delta×20 → llm_end → tts_start → bot_speaking', () => {
    const seq = [];
    let t = 0;
    seq.push(ev('user_speaking', (t += 0.1), { value: true }));
    seq.push(ev('asr_partial', (t += 0.1), { text: 'one' }));
    seq.push(ev('asr_partial', (t += 0.1), { text: 'one two' }));
    seq.push(ev('asr_partial', (t += 0.1), { text: 'one two three' }));
    seq.push(ev('asr_final', (t += 0.1), { text: 'one two three.' }));
    for (let i = 0; i < 20; i++) seq.push(ev('llm_delta', (t += 0.1), { text: 'x' }));
    seq.push(ev('llm_end', (t += 0.1), { text: 'xxxxxxxxxxxxxxxxxxxx' }));
    seq.push(ev('tts_start', (t += 0.1)));
    seq.push(ev('bot_speaking', (t += 0.1), { value: true }));

    // raw stream is ~26+ carrier events (1 user + 3 asr_partial + 1 asr_final +
    // 20 llm_delta + 1 llm_end + 1 tts_start + 1 bot_speaking = 28).
    expect(seq.length).toBe(28);
    expect(seq.length).toBeGreaterThanOrEqual(26);

    const rows = merge(seq);
    // user_speaking, asr (1), llm (1), tts_start, bot_speaking = 5..6 rows
    expect(rows.length).toBeLessThanOrEqual(6);
    expect(rows.length).toBeGreaterThanOrEqual(5);
    expect(rows.length).toBeLessThan(26);
    expect(rows.map((r) => r.type)).toEqual([
      'user_speaking',
      'asr_final',
      'llm_end',
      'tts_start',
      'bot_speaking',
    ]);
    expect(rows[1].text).toBe('one two three.');
    expect(rows[2].text).toBe('xxxxxxxxxxxxxxxxxxxx');
  });
});

// --- purity: source events untouched (copy, not mutate) -------------------

describe('mergeEvent — purity: never mutates source events or caller array', () => {
  it('does not mutate the source event objects (rows are copies)', () => {
    const src = [
      ev('llm_delta', 0.0, { text: 'a' }),
      ev('llm_delta', 0.1, { text: 'b' }),
      ev('llm_end', 0.2, { text: 'ab' }),
      ev('asr_partial', 1.0, { text: 'p' }),
      ev('asr_final', 1.1, { text: 'pf' }),
    ];
    // deep snapshot before
    const before = JSON.parse(JSON.stringify(src));

    const rows = [];
    for (const e of src) mergeEvent(rows, e);

    // every source event is byte-identical to its pre-merge snapshot
    expect(src).toEqual(before);
    // and no source event picked up the internal _*InFlight flag
    for (const e of src) {
      expect('_llmInFlight' in e).toBe(false);
      expect('_asrInFlight' in e).toBe(false);
    }
    // rows are distinct objects, not aliases of the source events
    for (const r of rows) {
      expect(src.includes(r)).toBe(false);
    }
  });

  it('rolling-up does not retroactively change earlier source partials', () => {
    const p1 = ev('asr_partial', 0.0, { text: 'he' });
    const p2 = ev('asr_partial', 0.1, { text: 'hel' });
    const f = ev('asr_final', 0.2, { text: 'hello' });
    const rows = [];
    mergeEvent(rows, p1);
    mergeEvent(rows, p2);
    mergeEvent(rows, f);
    // source partials retain their original text — only the display row rolled forward
    expect(p1.text).toBe('he');
    expect(p2.text).toBe('hel');
    expect(rows[0].text).toBe('hello');
  });
});

// --- useEventLog reactive wrapper -----------------------------------------

describe('useEventLog — reactive wrapper', () => {
  it('exposes rows/push/reset/loadAll', () => {
    const log = useEventLog();
    expect(log.rows.value).toEqual([]);
    expect(typeof log.push).toBe('function');
    expect(typeof log.reset).toBe('function');
    expect(typeof log.loadAll).toBe('function');
  });

  it('push merges through mergeEvent (10 llm_delta → 1 row)', () => {
    const log = useEventLog();
    for (let i = 0; i < 10; i++) log.push(ev('llm_delta', i * 0.1, { text: `${i}` }));
    expect(log.rows.value.length).toBe(1);
    expect(log.rows.value[0].text).toBe('0123456789');
  });

  it('reset clears rows', () => {
    const log = useEventLog();
    log.push(ev('tts_start', 0.0));
    expect(log.rows.value.length).toBe(1);
    log.reset();
    expect(log.rows.value.length).toBe(0);
  });

  it('loadAll rebuilds: 26 raw events → ~6 merged rows', () => {
    const seq = [];
    let t = 0;
    seq.push(ev('user_speaking', (t += 0.1), { value: true }));
    for (let i = 0; i < 3; i++) seq.push(ev('asr_partial', (t += 0.1), { text: 'p' + i }));
    seq.push(ev('asr_final', (t += 0.1), { text: 'final' }));
    for (let i = 0; i < 20; i++) seq.push(ev('llm_delta', (t += 0.1), { text: 'y' }));
    seq.push(ev('llm_end', (t += 0.1), { text: 'done' }));
    seq.push(ev('tts_start', (t += 0.1)));
    seq.push(ev('bot_speaking', (t += 0.1), { value: true }));
    expect(seq.length).toBe(28);
    expect(seq.length).toBeGreaterThanOrEqual(26);

    const log = useEventLog();
    log.loadAll(seq);
    expect(log.rows.value.length).toBeLessThanOrEqual(6);
    expect(log.rows.value.length).toBeLessThan(26);

    // loadAll is idempotent in row-count (reset + rebuild)
    log.loadAll(seq);
    expect(log.rows.value.length).toBeLessThanOrEqual(6);

    // source array untouched by loadAll
    expect(seq.length).toBe(28);
    for (const e of seq) {
      expect('_llmInFlight' in e).toBe(false);
      expect('_asrInFlight' in e).toBe(false);
    }
  });

  it('caps the display buffer at 1000 rows', () => {
    const log = useEventLog();
    // distinct boundary events (each its own row, spaced >0.05s so no dedupe)
    for (let i = 0; i < 1100; i++) log.push(ev('tts_start', i * 1.0, { value: i }));
    expect(log.rows.value.length).toBe(1000);
  });
});

// --- tailKey ---------------------------------------------------------------

describe('tailKey — newest-event change signal', () => {
  it('returns "" for empty/nullish arrays', () => {
    expect(tailKey([])).toBe('');
    expect(tailKey(null)).toBe('');
    expect(tailKey(undefined)).toBe('');
  });

  it('returns the newest event t', () => {
    expect(tailKey([ev('tts_start', 1.0), ev('tts_end', 2.5)])).toBe(2.5);
  });

  it('falls back to _ts when t is absent', () => {
    expect(tailKey([{ type: 'tts_start', _ts: 1717000000000 }])).toBe(1717000000000);
  });
});

// --- planLogSync (T3 cap-churn robustness, tech_design §8) -----------------
//
// Reproduces the DebugDrawer merge-sync watch decision. The key regression this
// guards: session.appendEvent caps raw events at 1000 by trimming the FRONT and
// pushing the back, so at the cap the array LENGTH plateaus while content keeps
// advancing. A length-only cursor goes deaf; planLogSync uses length + tailKey.

describe('planLogSync — append / rebuild / noop decisions', () => {
  it('pure growth → append from the old cursor', () => {
    const events = [ev('tts_start', 0.0), ev('tts_end', 1.0), ev('tts_start', 2.0)];
    const plan = planLogSync(events, { processed: 1, lastTail: 0.0 });
    expect(plan).toEqual({ action: 'append', from: 1 });
  });

  it('shrink / reset (len < processed) → rebuild', () => {
    const events = [ev('tts_start', 9.0)];
    expect(planLogSync(events, { processed: 50, lastTail: 8.0 }).action).toBe('rebuild');
    expect(planLogSync([], { processed: 50, lastTail: 8.0 }).action).toBe('rebuild');
  });

  it('no change (same length, same tail) → noop', () => {
    const events = [ev('tts_start', 0.0), ev('tts_end', 1.0)];
    expect(planLogSync(events, { processed: 2, lastTail: 1.0 }).action).toBe('noop');
  });

  it('CAP CHURN: length steady at the cap but tail advanced → rebuild (the bug)', () => {
    // Simulate the 1000-cap plateau: array stays length 1000, but the front was
    // trimmed and a fresh event pushed at the back, so the newest t advanced.
    const before = Array.from({ length: 1000 }, (_, i) => ev('tts_start', i, { value: i }));
    // after one appendEvent at the cap: drop index 0, push a newer event
    const after = [...before.slice(1), ev('tts_start', 1000, { value: 1000 })];
    expect(after.length).toBe(1000);

    const prev = { processed: 1000, lastTail: tailKey(before) }; // lastTail = 999
    const plan = planLogSync(after, prev);
    // length unchanged (1000 === 1000) but tail moved 999 → 1000: must rebuild,
    // NOT noop — otherwise new events would stop reaching the merged view.
    expect(plan.action).toBe('rebuild');
  });

  it('end-to-end at the cap: rebuild keeps the merged view tracking new events', () => {
    // Drive the full sync loop (append → cap-churn rebuild) against useEventLog,
    // proving the merged view does NOT freeze once the raw array plateaus.
    const log = useEventLog();
    let processed = 0;
    let lastTail = '';
    const raw = [];

    const appendEvent = (evt) => {
      raw.push(evt);
      if (raw.length > 1000) raw.splice(0, raw.length - 1000); // mirror session.js
    };
    const sync = () => {
      const plan = planLogSync(raw, { processed, lastTail });
      if (plan.action === 'rebuild') log.loadAll(raw);
      else if (plan.action === 'append') for (let i = plan.from; i < raw.length; i++) log.push(raw[i]);
      else return;
      processed = raw.length;
      lastTail = tailKey(raw);
    };

    // 1200 distinct boundary events, syncing after each (as the watch would).
    for (let i = 0; i < 1200; i++) {
      appendEvent(ev('tts_start', i, { value: i }));
      sync();
    }

    // Merged view tracks the newest event even though raw plateaued at 1000.
    const lastRow = log.rows.value[log.rows.value.length - 1];
    expect(lastRow.value).toBe(1199);
    expect(log.rows.value.length).toBeLessThanOrEqual(1000);
  });
});
