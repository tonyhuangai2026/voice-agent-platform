/**
 * Voice-server: Chime SDK Voice Connector → Pipecat bridge.
 *
 *   Chime  →  SIP INVITE (UDP:5060)  →  RTP G.711 μ-law 8 kHz
 *      → decode μ-law → PCM 8 kHz → upsample → 16 kHz
 *      → ws://pipecat:7860/phone/ws  (binary frames)
 *      → return PCM 24 kHz → downsample → 8 kHz → μ-law → RTP → Chime
 *
 * No DynamoDB, no per-customer prompts. The Pipecat side reads PHONE_*
 * env vars to decide language / scenario / voice.
 */
import Fastify from "fastify";
import { SipServer, type IncomingCallInfo } from "./sip";
import { PipecatClient } from "./pipecat-client";
import { MAX_CALL_DURATION_MS } from "./consts";

const PORT = parseInt(process.env.PORT || "3000", 10);
const PUBLIC_IP = process.env.PUBLIC_IP || "0.0.0.0";
const RTP_PORT_BASE = parseInt(process.env.RTP_PORT_BASE || "10000", 10);
const RTP_PORT_COUNT = parseInt(process.env.RTP_PORT_COUNT || "1000", 10);

interface ActiveSession {
  callId: string;
  callerPhone: string;
  startTime: string;
}
const activeSessions = new Map<string, ActiveSession>();
// Per-call teardown closures keyed by callId. The global onCallEnded handler
// (remote BYE / CANCEL) looks up the matching closure to also close the
// Pipecat WebSocket — without this, bot.py keeps the session live forever.
const callEnders = new Map<string, (reason: string) => void>();

const sipServer = new SipServer({
  publicIp: PUBLIC_IP,
  sipPort: 5060,
  rtpPortBase: RTP_PORT_BASE,
  rtpPortCount: RTP_PORT_COUNT,
});

sipServer.onIncomingCall(async (call: IncomingCallInfo) => {
  const { callId, callerPhone, rtpSession } = call;
  console.log(`[${new Date().toISOString()}] [CALL] Incoming: caller=${callerPhone} callId=${callId}`);
  activeSessions.set(callId, {
    callId,
    callerPhone,
    startTime: new Date().toISOString(),
  });

  let client: PipecatClient | null = null;
  let ended = false;

  const endCall = (reason: string) => {
    if (ended) return;
    ended = true;
    clearTimeout(callTimer);
    activeSessions.delete(callId);
    callEnders.delete(callId);
    if (client) client.close();
    sipServer.endCall(callId);
    console.log(`[${new Date().toISOString()}] [CALL] Ended: ${callId} reason=${reason}`);
  };

  // Per-call teardown hook for the global onCallEnded handler below.
  callEnders.set(callId, endCall);

  const callTimer = setTimeout(() => endCall("max-duration"), MAX_CALL_DURATION_MS);

  client = new PipecatClient(callId, callerPhone, {
    onAudioOutput: (pcm8) => {
      rtpSession.sendAudio(pcm8);
    },
    onEvent: (evt) => {
      // Log every event we receive so we can confirm the JSON-event channel
      // is actually reaching us (debugging barge-in).
      console.log(`[EVT ${callId}] ${evt.type} ${evt.value !== undefined ? "value=" + evt.value : (evt.text ? (evt.text + "").slice(0, 60) : "")}`);

      // Barge-in: when the user starts speaking (or partial/final ASR
      // arrives), MUTE outbound audio. Mute is stronger than clearQueue —
      // it also drops new audio that Nova Sonic keeps streaming after the
      // interruption signal, so the caller hears immediate silence instead
      // of the queue refilling and playing back ~200 ms later.
      if (
        (evt.type === "user_speaking" && evt.value === true) ||
        evt.type === "asr_partial" ||
        evt.type === "asr_final"
      ) {
        rtpSession.setMuted(true);
      }
      // Unmute on any of: new LLM/TTS turn (Nova Sonic honored the barge-in
      // and is starting fresh) OR user finished speaking (Nova Sonic chose
      // to keep its original turn — let it continue rather than stay silent
      // forever). bot_speaking=true is too late here: it fires only after
      // BotStoppedSpeakingFrame, which Nova Sonic may never emit.
      if (
        evt.type === "llm_start" ||
        evt.type === "tts_start" ||
        (evt.type === "user_speaking" && evt.value === false)
      ) {
        rtpSession.setMuted(false);
      }
    },
    onError: (err) => {
      console.error(`[Pipecat] error on ${callId}: ${err.message}`);
    },
    onComplete: () => {
      // Pipecat side closed; tear the call down.
      endCall("pipecat-closed");
    },
  });

  try {
    await client.connect();
  } catch (e: any) {
    console.error(`[Pipecat] connect failed: ${e.message}`);
    endCall("pipecat-connect-failed");
    return;
  }

  // RTP → Pipecat. Log first packet + every 500th (10 s) to confirm RTP keeps
  // flowing without flooding logs.
  let rtpPktCount = 0;
  rtpSession.onAudioReceived((pcm8: Buffer) => {
    rtpPktCount++;
    if (rtpPktCount === 1 || rtpPktCount % 500 === 0) {
      console.log(`[RTP→WS ${callId}] pkt=${rtpPktCount} pcm8=${pcm8.length}b`);
    }
    client?.sendPCM8(pcm8);
  });
});

sipServer.onCallEnded((callId, reason) => {
  console.log(`[${new Date().toISOString()}] [SIP] call ended: ${callId} reason=${reason}`);
  const ender = callEnders.get(callId);
  if (ender) ender(`sip:${reason}`);
  else activeSessions.delete(callId);
});

// --- HTTP health/diagnostics ---
const app = Fastify({ logger: false });
app.get("/health", async () => ({
  status: "ok",
  service: "voice-server",
  activeCalls: activeSessions.size,
}));
app.get("/api/active-calls", async () =>
  Array.from(activeSessions.values())
);

async function main() {
  await sipServer.start();
  console.log(
    `[SIP] ready: UDP 5060, RTP ${RTP_PORT_BASE}-${RTP_PORT_BASE + RTP_PORT_COUNT - 1}`
  );
  await app.listen({ port: PORT, host: "0.0.0.0" });
  console.log(`[HTTP] ready on :${PORT}`);
}

process.on("SIGTERM", () => {
  console.log("SIGTERM, shutting down...");
  sipServer.stop();
  process.exit(0);
});

main().catch((e) => {
  console.error("fatal:", e);
  process.exit(1);
});
