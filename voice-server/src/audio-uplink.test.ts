/**
 * Uplink sample-rate test (node:test, run via `npm test`).
 *
 * The phone uplink must be sent to Pipecat as NATIVE 8 kHz — no upsampling —
 * so AWS Transcribe's telephony model gets true 8 kHz. This test drives
 * PipecatClient.sendPCM8 with a fake WebSocket and asserts the bytes go out
 * unchanged (same length, same content). It also guards the downlink resampler
 * so the 24→8 kHz path is not disturbed.
 */

import { test } from "node:test";
import assert from "node:assert/strict";

import { PipecatClient } from "./pipecat-client";
import { downsample24to8, upsample8to16, resample } from "./audio-utils";

// A minimal fake WebSocket capturing send() payloads.
class FakeWS {
  static OPEN = 1;
  readyState = 1;
  sent: Buffer[] = [];
  send(data: Buffer, _opts?: unknown) {
    this.sent.push(Buffer.from(data));
  }
}

function makePcm8(nSamples: number): Buffer {
  const b = Buffer.alloc(nSamples * 2);
  for (let i = 0; i < nSamples; i++) b.writeInt16LE(((i * 37) % 2000) - 1000, i * 2);
  return b;
}

test("sendPCM8 forwards native 8 kHz bytes unchanged (no upsample)", () => {
  const client = new PipecatClient("call-1", "+1555", {});
  const ws = new FakeWS();
  // Inject fake ws + active state (private fields; cast through unknown).
  (client as unknown as { ws: FakeWS; active: boolean }).ws = ws;
  (client as unknown as { ws: FakeWS; active: boolean }).active = true;

  const pcm8 = makePcm8(160); // 20 ms @ 8 kHz = 160 samples = 320 bytes
  client.sendPCM8(pcm8);

  assert.equal(ws.sent.length, 1, "exactly one frame sent");
  assert.equal(ws.sent[0].length, pcm8.length, "byte length unchanged (NOT doubled)");
  assert.ok(ws.sent[0].equals(pcm8), "bytes forwarded verbatim");
});

test("sendPCM8 no-ops when ws not open", () => {
  const client = new PipecatClient("call-2", null, {});
  const ws = new FakeWS();
  ws.readyState = 3; // CLOSED
  (client as unknown as { ws: FakeWS; active: boolean }).ws = ws;
  (client as unknown as { ws: FakeWS; active: boolean }).active = true;
  client.sendPCM8(makePcm8(160));
  assert.equal(ws.sent.length, 0);
});

test("downlink downsample24to8 unchanged: 24k→8k is 1/3 the samples", () => {
  const pcm24 = Buffer.alloc(24 * 2); // 24 samples
  const out = downsample24to8(pcm24);
  assert.equal(out.length / 2, 8, "24 samples @24k -> 8 samples @8k");
});

test("upsample8to16 still works (kept util): 8k→16k doubles samples", () => {
  const pcm8 = makePcm8(100);
  const out = upsample8to16(pcm8);
  assert.equal(out.length / 2, 200, "100 samples @8k -> 200 @16k");
});

test("resample identity when src==dst", () => {
  const b = makePcm8(50);
  assert.ok(resample(b, 8000, 8000).equals(b));
});
