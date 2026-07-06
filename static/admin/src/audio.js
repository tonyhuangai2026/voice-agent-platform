// Audio Recorder + Player, extracted from the legacy static/index.html.
//
// Critical browser quirks (learned the hard way):
//   - Don't pin sampleRate when constructing AudioContext. Some desktop
//     browsers reject non-native rates (notably Chrome on macOS at 16 kHz
//     output). Use the default; AudioBufferSourceNode resamples per buffer.
//   - The Player uses one AudioContext for output at OUT_RATE per buffer
//     (typically 24 kHz from Pipecat's pipeline output transport).
//   - Recorder downsamples to 16 kHz Int16 PCM before sending. /ws on the
//     server side configures audio_in_sample_rate=16000.

const IN_RATE = 16000;
const OUT_RATE = 24000;

// ---------------------------------------------------------------------------
// Push-to-Talk (PTT) pure helpers — tech_design §2. Frontend-only; the WS line
// protocol and backend VAD are untouched. These are deliberately framework-free
// (no Vue/Pinia) so they unit-test in plain vitest.
// ---------------------------------------------------------------------------

// localStorage key for the persisted PTT toggle (tech_design §2.1).
export const PTT_STORAGE_KEY = 'vb.ptt';

/**
 * Mic-gate for the recorder frame callback.
 *
 * The WS audio stream MUST stay continuous (server Silero VAD + pipeline expect
 * a steady 16 kHz Int16 frame cadence). So "released" does NOT mean stop sending
 * — it means send an equal-length all-zero (silence) frame instead. The server
 * VAD then naturally times out the turn via its existing stop_secs. No PTT flag
 * is ever sent to the backend.
 *
 * The worklet posts `out.buffer` (a plain ArrayBuffer); we therefore type/return
 * ArrayBuffer here.
 *
 * @param {ArrayBuffer} buf  the real PCM frame from the worklet
 * @param {boolean} micOpen  true → forward the original buffer; false → silence
 * @returns {ArrayBuffer} the buffer to actually send on the wire
 */
export function gateFrame(buf, micOpen) {
  if (micOpen) return buf;
  // All-zero, same byteLength → identical frame cadence on the server side.
  return new ArrayBuffer(buf.byteLength);
}

/**
 * Derive whether the mic is "open" (real audio forwarded) for the current frame.
 * PTT off → always open (hands-free, current behavior). PTT on → open only while
 * the hold-button / spacebar is held.
 *
 * @param {boolean} pttEnabled  is Push-to-Talk mode on
 * @param {boolean} pttHolding  is the user currently holding to talk
 * @returns {boolean}
 */
export function deriveMicOpen(pttEnabled, pttHolding) {
  return !pttEnabled || pttHolding;
}

/**
 * Should a keydown event enter the "talking" (holding) state?
 *
 * Filters keyboard auto-repeat (`event.repeat`) so a long-held spacebar only
 * enters talking once. Only the space key counts.
 *
 * @param {{ code?: string, key?: string, repeat?: boolean }} event
 * @returns {boolean}
 */
export function shouldEnterTalking(event) {
  if (!event || event.repeat) return false;
  return event.code === 'Space' || event.key === ' ' || event.key === 'Spacebar';
}

/** Read the persisted PTT toggle from localStorage. Defaults to false (off). */
export function readPtt(storage = globalThis.localStorage) {
  try {
    return storage.getItem(PTT_STORAGE_KEY) === 'true';
  } catch {
    return false;
  }
}

/** Persist the PTT toggle to localStorage. */
export function writePtt(value, storage = globalThis.localStorage) {
  try {
    storage.setItem(PTT_STORAGE_KEY, value ? 'true' : 'false');
  } catch {
    /* ignore — storage unavailable (private mode etc.) */
  }
}

// ---------------------------------------------------------------------------
// Talk engine/voice selection persistence (tech_design §3.1). Mirrors the
// readPtt/writePtt pattern: ALL localStorage access lives here (the component
// calls these) so talkConfig.js stays pure/DOM-free. Five flat scalar keys
// (one per selection field) rather than a JSON blob — simpler to inspect and
// matches the per-key convention the design specifies.
// ---------------------------------------------------------------------------

/** localStorage keys for the persisted Talk selection (tech_design §3.1). */
export const TALK_SEL_KEYS = {
  engine: 'vb.talk.engine',
  lang: 'vb.talk.lang',
  provider: 'vb.talk.provider',
  voice: 'vb.talk.voice',
  novaVoice: 'vb.talk.novaVoice',
  model: 'vb.talk.model',
};

/**
 * Read the persisted Talk selection from localStorage. Returns a plain object
 * with only the keys that are actually present (missing → omitted, so
 * reconcileSelection treats them as "no preference" and falls back to config
 * defaults). Never throws.
 */
export function readTalkSel(storage = globalThis.localStorage) {
  const out = {};
  try {
    for (const [field, key] of Object.entries(TALK_SEL_KEYS)) {
      const v = storage.getItem(key);
      if (v != null && v !== '') out[field] = v;
    }
  } catch {
    /* ignore — storage unavailable */
  }
  return out;
}

/**
 * Persist a (reconciled) Talk selection to localStorage. Writes every field
 * present on `sel`; skips null/empty. Never throws.
 */
export function writeTalkSel(sel, storage = globalThis.localStorage) {
  const s = sel || {};
  try {
    for (const [field, key] of Object.entries(TALK_SEL_KEYS)) {
      const v = s[field];
      if (v != null && v !== '') storage.setItem(key, String(v));
    }
  } catch {
    /* ignore — storage unavailable */
  }
}

const WORKLET_CODE = `
class PCMWorklet extends AudioWorkletProcessor {
  constructor(opts) {
    super();
    this.targetRate = opts.processorOptions.targetRate;
    this.ratio = sampleRate / this.targetRate;
    this.acc = 0;
    this.buf = [];
  }
  process(inputs) {
    const ch = inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      this.acc += 1;
      if (this.acc >= this.ratio) {
        this.acc -= this.ratio;
        const s = Math.max(-1, Math.min(1, ch[i]));
        this.buf.push(s < 0 ? s * 0x8000 : s * 0x7fff);
      }
    }
    if (this.buf.length >= 320) {
      const out = new Int16Array(this.buf);
      this.buf = [];
      this.port.postMessage(out.buffer, [out.buffer]);
    }
    return true;
  }
}
registerProcessor("pcm-worklet", PCMWorklet);
`;

/** Records mic audio, downsamples to 16 kHz Int16, exposes a frame stream. */
export class Recorder {
  constructor() {
    this.audioCtx = null;
    this.workletNode = null;
    this.micStream = null;
    this.onFrame = null; // (Int16Array buffer) => void
  }

  async start(onFrame) {
    this.onFrame = onFrame;
    this.micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: true,
        noiseSuppression: true,
        autoGainControl: true,
      },
    });
    this.audioCtx = new AudioContext();

    if (!this.audioCtx.audioWorklet) {
      // AudioWorklet is widely supported (Chrome 66+, Safari 14.1+, Firefox 76+).
      // If absent we just fail loudly instead of maintaining a ScriptProcessor
      // fallback path that would diverge from the worklet code.
      throw new Error('AudioWorklet not supported in this browser');
    }
    const blob = new Blob([WORKLET_CODE], { type: 'application/javascript' });
    await this.audioCtx.audioWorklet.addModule(URL.createObjectURL(blob));
    const src = this.audioCtx.createMediaStreamSource(this.micStream);
    this.workletNode = new AudioWorkletNode(this.audioCtx, 'pcm-worklet', {
      processorOptions: { targetRate: IN_RATE },
    });
    src.connect(this.workletNode);
    // Keep the graph alive without making the user hear themselves.
    const sink = this.audioCtx.createGain();
    sink.gain.value = 0;
    this.workletNode.connect(sink).connect(this.audioCtx.destination);

    this.workletNode.port.onmessage = (e) => {
      if (this.onFrame) this.onFrame(e.data);
    };
  }

  stop() {
    if (this.workletNode) {
      this.workletNode.disconnect();
      this.workletNode = null;
    }
    if (this.audioCtx) {
      this.audioCtx.close();
      this.audioCtx = null;
    }
    if (this.micStream) {
      this.micStream.getTracks().forEach((t) => t.stop());
      this.micStream = null;
    }
    this.onFrame = null;
  }
}

/** Plays back streamed PCM (24 kHz Int16) without pinning context sampleRate. */
export class Player {
  constructor() {
    this.ctx = null;
    this.playhead = 0;
  }

  ensureCtx() {
    if (!this.ctx) {
      this.ctx = new AudioContext();
      this.playhead = this.ctx.currentTime;
    }
  }

  feed(arrayBufferOrInt16) {
    this.ensureCtx();
    const int16 =
      arrayBufferOrInt16 instanceof Int16Array
        ? arrayBufferOrInt16
        : new Int16Array(arrayBufferOrInt16);
    const f32 = new Float32Array(int16.length);
    for (let i = 0; i < int16.length; i++) f32[i] = int16[i] / 0x8000;
    const buf = this.ctx.createBuffer(1, f32.length, OUT_RATE);
    buf.copyToChannel(f32, 0);
    const node = this.ctx.createBufferSource();
    node.buffer = buf;
    node.connect(this.ctx.destination);
    const now = this.ctx.currentTime;
    if (this.playhead < now) this.playhead = now;
    node.start(this.playhead);
    this.playhead += buf.duration;
  }

  /** Drop pending playback — used on barge-in. */
  clear() {
    if (this.ctx) {
      this.ctx.close();
      this.ctx = null;
    }
    this.playhead = 0;
  }
}
