/**
 * Bridge between an in-progress phone call and the Pipecat /phone/ws endpoint.
 *
 *   PSTN  →  RtpSession  (G.711 μ-law 8 kHz)
 *   →  decode μ-law  →  upsample 8→16 kHz  →  binary frame  →  Pipecat /phone/ws
 *
 *   Pipecat  →  binary frame (24 kHz PCM)  →  downsample 24→8 kHz
 *   →  encode μ-law  →  RtpSession  →  PSTN
 *
 *   Pipecat also sends JSON text frames (EventBroadcaster). We just log them
 *   here; browser monitors subscribe via /monitor/ws on the Pipecat side, not
 *   through this client.
 */
import WebSocket from "ws";
import { EventEmitter } from "node:events";
import { PIPECAT_WS_URL } from "./consts";
// Uplink is now sent as native 8 kHz (no upsample8to16 — see sendPCM8). The
// downlink still downsamples 24→8 kHz here.
import { downsample24to8 } from "./audio-utils";

export interface PipecatClientHandlers {
  onAudioOutput?: (pcm8k: Buffer) => void;     // already 8 kHz μ-law-ready PCM
  onEvent?: (evt: any) => void;                 // optional: see EventBroadcaster JSON
  onError?: (err: Error) => void;
  onComplete?: () => void;
}

export class PipecatClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private handlers: PipecatClientHandlers;
  private callId: string;
  private caller: string | null;
  private active = false;

  constructor(callId: string, caller: string | null, handlers: PipecatClientHandlers) {
    super();
    this.callId = callId;
    this.caller = caller;
    this.handlers = handlers;
  }

  async connect(): Promise<void> {
    return new Promise((resolve, reject) => {
      const params = new URLSearchParams({ call_id: this.callId });
      if (this.caller) params.set("caller", this.caller);
      const url = `${PIPECAT_WS_URL}?${params}`;
      console.log(`[Pipecat] connecting ${url}`);
      this.ws = new WebSocket(url);

      this.ws.on("open", () => {
        console.log(`[${new Date().toISOString()}] [Pipecat] connected call_id=${this.callId}`);
        this.active = true;
        resolve();
      });

      this.ws.on("message", (data: WebSocket.Data, isBinary: boolean) => {
        if (isBinary) {
          // Pipeline output: 24 kHz PCM. Downsample to 8 kHz for the RTP leg.
          const buf = data as Buffer;
          const pcm8 = downsample24to8(buf);
          this.handlers.onAudioOutput?.(pcm8);
        } else {
          // EventBroadcaster JSON event.
          try {
            const evt = JSON.parse(data.toString());
            this.handlers.onEvent?.(evt);
          } catch {
            // ignore parse errors
          }
        }
      });

      this.ws.on("error", (err) => {
        console.error(`[Pipecat] error: ${err.message}`);
        this.handlers.onError?.(err);
      });

      this.ws.on("close", () => {
        console.log(`[${new Date().toISOString()}] [Pipecat] disconnected call_id=${this.callId}`);
        this.active = false;
        this.handlers.onComplete?.();
      });

      setTimeout(() => {
        if (!this.active) reject(new Error("Pipecat connection timeout"));
      }, 10000);
    });
  }

  /** Send the PSTN uplink audio to Pipecat as NATIVE 8 kHz PCM (unchanged).
   *
   * We used to upsample 8→16 kHz here (naive linear interpolation), but that
   * only injected imaging/aliasing noise into the ASR without recovering any
   * of the high-frequency content G.711 already discarded. AWS Transcribe has
   * a dedicated 8 kHz telephony model, so the backend now feeds it native
   * 8 kHz directly (pipeline path). Engine-specific sample-rate adaptation now
   * lives in the backend: the pipeline path uses 8 kHz as-is; the nova-sonic
   * path (which requires 16 kHz) upsamples server-side. voice-server stays
   * engine-agnostic — symmetric with the downlink, which always downsamples
   * 24→8 kHz here regardless of engine. */
  sendPCM8(pcm8: Buffer): void {
    if (!this.active || !this.ws || this.ws.readyState !== WebSocket.OPEN) return;
    this.ws.send(pcm8, { binary: true });
  }

  close(): void {
    if (this.ws && this.ws.readyState === WebSocket.OPEN) {
      this.ws.close();
    }
    this.ws = null;
    this.active = false;
  }
}
