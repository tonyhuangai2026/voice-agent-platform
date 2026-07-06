// ASR A/B test helpers (tech_design §3, §4) — pure, DOM-free so they unit-test
// in plain vitest. The /asr-test/ws endpoint (T1) fans one mic's PCM to two
// Transcribe streams and tags every JSON message with a `stream` field:
//   { stream: 'A' | 'B', text, is_final, lang? }   (transcript)
//   { stream: 'A' | 'B', error }                    (per-stream failure)
// Stream A = single-language zh-HK; stream B = multi-language zh-HK + en-US.

/** The two panes, in display order. A = single zh-HK, B = multi zh-HK+en-US. */
export const ASR_STREAMS = ['A', 'B'];

/** Default mode for stream B's multi-language Transcribe identification. */
export const ASR_B_MODE_DEFAULT = 'multiple';
export const ASR_B_MODES = ['multiple', 'single'];

/**
 * Stream B partial-results-stability levels → &stability= on the WS. Lower =
 * partials surface earlier (lower latency) but get rewritten more; "high" is
 * AWS's / stock-pipecat's default (most stable, slowest). Stream A always uses
 * stock "high" and is NOT tunable — this affects only B.
 */
export const ASR_B_STABILITY_DEFAULT = 'high';
export const ASR_B_STABILITY_LEVELS = ['low', 'medium', 'high'];
export const ASR_STABILITY_OPTIONS = [
  { label: 'low(最快/多改写)', value: 'low' },
  { label: 'medium(折中)', value: 'medium' },
  { label: 'high(最稳/最慢)', value: 'high' },
];

/**
 * Classify an incoming /asr-test/ws JSON message.
 *
 * Returns a normalized record `{ stream, kind, text, is_final, lang, error }`
 * where `kind` is 'error' | 'final' | 'interim', or `null` when the message
 * carries no usable `stream` tag (so the caller can safely ignore it). Keeping
 * the routing in one pure function makes the view's onmessage trivial and the
 * vitest assertion exact.
 *
 * @param {any} msg parsed JSON message from the WS
 * @returns {{stream:'A'|'B', kind:'error'|'final'|'interim', text:string, is_final:boolean, lang:(string|null), error:(string|null)}|null}
 */
export function routeAsrMessage(msg) {
  if (!msg || (msg.stream !== 'A' && msg.stream !== 'B')) return null;
  if (msg.error != null && msg.error !== '') {
    return {
      stream: msg.stream,
      kind: 'error',
      text: '',
      is_final: false,
      lang: null,
      error: String(msg.error),
    };
  }
  const is_final = msg.is_final === true;
  return {
    stream: msg.stream,
    kind: is_final ? 'final' : 'interim',
    text: typeof msg.text === 'string' ? msg.text : '',
    is_final,
    lang: msg.lang != null && msg.lang !== '' ? String(msg.lang) : null,
    error: null,
  };
}
