import { ref } from 'vue';

// useEventLog — shared debug-event-stream merge logic (tech_design §1, §6).
//
// Extracted verbatim (semantics-identical) from MonitorView.vue pushEvent
// (lines 240-308) so Talk + Monitor + DebugDrawer can share one merge core.
//
// Two layers:
//   1. mergeEvent(rows, evt)  — PURE, side-effect-free core. Transforms the
//      `rows` display array (find-and-roll-up / accumulate / dedupe / push) and
//      returns it. NEVER mutates `evt`; pushed rows are COPIES ({...evt}); the
//      raw events array (session.js) stays pristine. No scroll / trim / cap.
//   2. useEventLog()          — reactive wrapper. Owns a `rows` ref, runs
//      mergeEvent in push(), and applies display-only side effects (cap 1000)
//      that DON'T belong in the pure core.

const DEDUPE_WINDOW_SEC = 0.05;
const MAX_ROWS = 1000;

/**
 * Pure merge core. Mutates the passed display `rows` array (the composable owns
 * it) and returns it. Does NOT mutate `evt` nor any source-array element — rows
 * are independent copies. Carries NO scroll / trim / cap side effects.
 *
 * Merge rules (mirror MonitorView.pushEvent exactly):
 *  - dedupe: drop when the last row has identical type/value/text and the
 *    timestamps are <0.05s apart.
 *  - asr_partial/asr_final: roll the latest in-flight asr row's text forward
 *    (asr_final closes it); otherwise push a new asr row.
 *  - llm_delta/llm_end: accumulate text into the latest in-flight llm row
 *    (llm_end closes it, replacing text with the final text if provided);
 *    otherwise push a new llm row.
 *  - everything else (user_speaking/tts_start/tts_end/bot_speaking/…): its own
 *    new row.
 *
 * @param {Array<object>} rows display rows array (mutated in place)
 * @param {object} evt raw event { t, type, text, value, ... } — left untouched
 * @returns {Array<object>} the same `rows` array, after merge
 */
export function mergeEvent(rows, evt) {
  const last = rows[rows.length - 1];

  // Dedupe: identical consecutive event inside the <0.05s window → drop.
  if (
    last &&
    last.type === evt.type &&
    last.value === evt.value &&
    last.text === evt.text &&
    typeof last.t === 'number' &&
    typeof evt.t === 'number' &&
    Math.abs(evt.t - last.t) < DEDUPE_WINDOW_SEC
  ) {
    return rows;
  }

  if (evt.type === 'asr_partial' || evt.type === 'asr_final') {
    for (let i = rows.length - 1; i >= 0; i--) {
      const row = rows[i];
      if (row._asrInFlight) {
        row.type = evt.type === 'asr_final' ? 'asr_final' : 'asr_partial';
        row.text = evt.text || '';
        row.t = evt.t;
        if (evt.type === 'asr_final') row._asrInFlight = false;
        return rows;
      }
      if (row.type !== 'asr_partial' && row.type !== 'asr_final') break;
    }
    rows.push({ ...evt, _asrInFlight: evt.type === 'asr_partial' });
    return rows;
  }

  if (evt.type === 'llm_delta' || evt.type === 'llm_end') {
    for (let i = rows.length - 1; i >= 0; i--) {
      const row = rows[i];
      if (row._llmInFlight) {
        if (evt.type === 'llm_delta') {
          row.text = (row.text || '') + (evt.text || '');
        } else {
          row.text = evt.text || row.text || '';
          row.type = 'llm_end';
          row._llmInFlight = false;
        }
        row.t = evt.t;
        return rows;
      }
      if (row.type !== 'llm_delta' && row.type !== 'llm_end' && row.type !== 'llm_start') break;
    }
    rows.push({
      ...evt,
      type: evt.type === 'llm_end' ? 'llm_end' : 'llm_delta',
      _llmInFlight: evt.type === 'llm_delta',
    });
    return rows;
  }

  rows.push({ ...evt });
  return rows;
}

/**
 * Tail key of a raw events array — the newest event's timestamp. Used as the
 * change signal for incremental merge sync: session.appendEvent caps `events`
 * at 1000 by trimming the FRONT and pushing the back, so once a long call
 * plateaus at the cap the array LENGTH stops changing while content keeps
 * advancing. The tail `t` (falling back to `_ts`) still advances, so it detects
 * cap-churn that a length-only signal would miss.
 *
 * @param {Array<object>} arr raw events array
 * @returns {(number|string)} newest event's t / _ts, or '' when empty
 */
export function tailKey(arr) {
  if (!arr || !arr.length) return '';
  const last = arr[arr.length - 1];
  return last?.t ?? last?._ts ?? '';
}

/**
 * PURE decision for incrementally syncing a merged view from a raw events array
 * that may grow, shrink/reset, OR churn at a front-trimmed cap. Given the prior
 * cursor state, returns what the consumer should do — no side effects, fully
 * unit-testable (covers the cap-plateau bug where length alone goes deaf).
 *
 *  - { action: 'rebuild' }            → loadAll(events): shrink/reset, or
 *                                        cap-churn (length steady, tail moved)
 *                                        where the index cursor is no longer valid.
 *  - { action: 'append', from }       → push(events[from..len-1]): pure growth,
 *                                        preserves in-flight asr/llm roll-up.
 *  - { action: 'noop' }               → nothing changed meaningfully.
 *
 * @param {Array<object>} events current raw events array
 * @param {{ processed: number, lastTail: (number|string) }} prev cursor state
 * @returns {{ action: 'rebuild'|'append'|'noop', from?: number }}
 */
export function planLogSync(events, prev) {
  const len = events ? events.length : 0;
  const { processed, lastTail } = prev;
  if (len < processed) return { action: 'rebuild' };
  if (len > processed) return { action: 'append', from: processed };
  // len === processed: only churn (front-trim at the cap) can have changed the
  // tail. If the newest timestamp advanced, the index cursor is stale → rebuild.
  return tailKey(events) !== lastTail ? { action: 'rebuild' } : { action: 'noop' };
}

/**
 * Reactive wrapper around mergeEvent. Returns:
 *   - rows: ref<Array> of merged display rows
 *   - push(evt): merge one raw event, then apply display-only cap (1000 rows)
 *   - reset(): clear rows
 *   - loadAll(events): rebuild rows from a raw events array (reset + push each)
 */
export function useEventLog() {
  const rows = ref([]);

  function push(evt) {
    mergeEvent(rows.value, evt);
    // Display-only side effect — kept OUT of the pure core. Scroll/trim concerns
    // belong to the consumer; here we only cap the display buffer.
    const arr = rows.value;
    if (arr.length > MAX_ROWS) arr.splice(0, arr.length - MAX_ROWS);
  }

  function reset() {
    rows.value = [];
  }

  function loadAll(events) {
    reset();
    for (const e of events || []) push(e);
  }

  return { rows, push, reset, loadAll };
}
