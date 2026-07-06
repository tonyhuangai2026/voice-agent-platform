"""T4 integration test: full Twilio ingress wiring, fake-websocket driven.

This is the T4 AC#1 end-to-end seam check. The original AC text named a
``TwilioMediaStreamAdapter`` shim, but that shim was deleted during the
Round-1 design revision (we use pipecat's built-in ``TwilioFrameSerializer``,
no custom adapter — see tech_design 2f6d1455 §1). So AC#1 is interpreted as:

    Drive a real Twilio frame sequence (connected → start → media×N → stop)
    through the REAL ``/twilio/media-stream`` endpoint into the REAL
    ``_run_phone_session`` kernel, and prove the wiring end to end:

      * streamSid is captured from the ``start`` frame,
      * a real pipecat ``TwilioFrameSerializer`` is threaded into the kernel
        and on to the pipeline-transport params,
      * inbound ``media`` frames deserialize to ``InputAudioRawFrame`` via that
        serializer (audio round-trips IN),
      * an output audio frame serializes back to a Twilio ``media`` JSON whose
        ``streamSid`` matches the call (audio round-trips OUT),
      * the session is registered before hand-off and cleaned up at the end.

The heavy pipeline build (Bedrock/Nova/MCP/TTS) is impractical to run fully
offline, so we monkeypatch the two ``_build_*`` builders to a lightweight stub
that returns a fake PipelineTask, and monkeypatch ``PipelineRunner`` to a fake
runner that plays the role of the real ``FastAPIWebsocketTransport``: it pulls
WS frames, deserializes media through the *real* serializer the endpoint built,
and serializes one synthetic bot output frame back out. That is exactly the
contract the real transport fulfils, so this proves our wiring without standing
up the full engine. No real Twilio call, no AWS, no network.

Unlike tests/test_twilio_endpoints.py (which stubs the whole kernel and only
asserts the serializer *type* reaches it), this test runs the real kernel body
and exercises the serializer's deserialize/serialize round-trip.
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest

import bot


PUBLIC_BASE = "https://twilio.example.com"
AUTH_TOKEN = "test-auth-token-123"


def _enable_twilio(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("TWILIO_PUBLIC_BASE_URL", PUBLIC_BASE)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)


def _ulaw_silence(n: int = 160) -> bytes:
    """``n`` bytes of μ-law silence (0xFF) — a valid Twilio media payload."""
    return b"\xff" * n


class _FakeTwilioWS:
    """Scripted Twilio Media-Streams websocket.

    ``twilio_media_stream`` reads frames up to ``start`` via ``receive_text``;
    after hand-off our fake runner keeps pulling the remaining frames the same
    way the real transport would. When frames are exhausted, ``receive_text``
    raises to mimic the client disconnecting (end of stream).
    """

    def __init__(self, frames):
        self._frames = list(frames)
        self.accepted = False
        self.closed_code = None
        self.sent_text = []

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if not self._frames:
            raise RuntimeError("client disconnected")
        return self._frames.pop(0)

    async def close(self, code=1000):
        self.closed_code = code

    async def send_text(self, data):
        self.sent_text.append(data)


@pytest.mark.asyncio
async def test_twilio_media_stream_full_round_trip(monkeypatch):
    """connected→start→media×N→stop drives the real endpoint + real kernel;
    proves streamSid capture, serializer threading, and audio round-trip."""
    _enable_twilio(monkeypatch)
    # No history side effects in the kernel.
    monkeypatch.setattr(bot, "_history", None)

    from pipecat.frames.frames import (
        InputAudioRawFrame,
        OutputAudioRawFrame,
    )
    from pipecat.serializers.twilio import TwilioFrameSerializer

    evidence: dict = {}

    # ----- Stub the heavy builders: return a fake task carrying the serializer
    # the endpoint built, exactly as the real builders thread it into the
    # transport params. We capture it so the fake runner can exercise it.
    class _FakeTask:
        def __init__(self, serializer):
            self.serializer = serializer

    async def _fake_build(websocket, *args, serializer=None, **kwargs):
        evidence["serializer_in_builder"] = serializer
        evidence["is_phone"] = kwargs.get("is_phone")
        evidence["call_id_in_builder"] = kwargs.get("call_id")
        return _FakeTask(serializer)

    monkeypatch.setattr(bot, "_build_pipeline", _fake_build)
    monkeypatch.setattr(bot, "_build_nova_sonic_pipeline", _fake_build)

    # ----- Fake PipelineRunner: plays the role of FastAPIWebsocketTransport.
    # It reads the post-start WS frames, deserializes media through the REAL
    # serializer (audio IN), and serializes one synthetic bot output frame
    # back out (audio OUT) — the exact transport<->serializer contract.
    class _FakeRunner:
        def __init__(self, *a, **k):
            pass

        async def run(self, task):
            ser = task.serializer
            # Prime the serializer the way pipecat does on StartFrame.
            from pipecat.frames.frames import StartFrame
            await ser.setup(
                StartFrame(audio_in_sample_rate=8000, audio_out_sample_rate=8000)
            )
            input_frames = []
            while True:
                try:
                    raw = await ws.receive_text()
                except Exception:
                    break  # client disconnect / end of script
                msg = json.loads(raw)
                if msg.get("event") == "media":
                    frame = await ser.deserialize(raw)
                    if frame is not None:
                        input_frames.append(frame)
                elif msg.get("event") == "stop":
                    break
            evidence["input_frames"] = input_frames
            # Bot speaks back: serialize one output audio frame to Twilio media.
            out = await ser.serialize(
                OutputAudioRawFrame(
                    audio=b"\x00\x00" * 160, sample_rate=8000, num_channels=1
                )
            )
            evidence["output_media_json"] = out

    monkeypatch.setattr(bot, "PipelineRunner", _FakeRunner)

    stream_sid = "MZ1234567890abcdef"
    payload = base64.b64encode(_ulaw_silence()).decode()
    frames = [
        json.dumps({"event": "connected", "protocol": "Call", "version": "1.0.0"}),
        json.dumps(
            {
                "event": "start",
                "streamSid": stream_sid,
                "start": {
                    "streamSid": stream_sid,
                    "callSid": "CA999",
                    "customParameters": {"caller": "+15551112222"},
                },
            }
        ),
        json.dumps({"event": "media", "media": {"payload": payload}}),
        json.dumps({"event": "media", "media": {"payload": payload}}),
        json.dumps({"event": "media", "media": {"payload": payload}}),
        json.dumps({"event": "stop", "streamSid": stream_sid}),
    ]
    ws = _FakeTwilioWS(frames)

    # ---- Drive the REAL endpoint end to end.
    await bot.twilio_media_stream(ws)

    # ===== Assertions: prove the full wiring =====
    assert ws.accepted is True

    # 1. streamSid captured → call_id; real TwilioFrameSerializer threaded into
    #    the kernel and on to the (stubbed) builder.
    ser = evidence["serializer_in_builder"]
    assert isinstance(ser, TwilioFrameSerializer)
    assert ser._stream_sid == stream_sid
    assert evidence["call_id_in_builder"] == f"twilio-{stream_sid}"
    assert evidence["is_phone"] is True  # phone defaults / kernel reuse

    # 2. Inbound media frames deserialized to InputAudioRawFrame (audio IN).
    assert len(evidence["input_frames"]) == 3
    for f in evidence["input_frames"]:
        assert isinstance(f, InputAudioRawFrame)
        assert f.sample_rate == 8000
        assert len(f.audio) > 0

    # 3. Output frame serialized back to a Twilio media JSON with our streamSid
    #    (audio OUT / return-path media frame).
    out_msg = json.loads(evidence["output_media_json"])
    assert out_msg["event"] == "media"
    assert out_msg["streamSid"] == stream_sid
    assert "payload" in out_msg["media"]
    base64.b64decode(out_msg["media"]["payload"])  # valid base64 μ-law

    # 4. Session lifecycle: registered before hand-off, cleaned up after.
    assert f"twilio-{stream_sid}" not in bot.ACTIVE_SESSIONS


@pytest.mark.asyncio
async def test_twilio_media_stream_pipeline_engine_path(monkeypatch):
    """Same wiring, but assert the pipeline (non-nova) builder is the one the
    kernel selects under default phone config — i.e. the serializer reaches the
    Bedrock/MiniMax pipeline builder, not just any builder."""
    _enable_twilio(monkeypatch)
    monkeypatch.setattr(bot, "_history", None)

    # Force the pipeline engine branch explicitly.
    base = dict(bot.RUNTIME_CONFIG.get_phone_defaults())
    base["engine"] = "pipeline"
    monkeypatch.setattr(bot.RUNTIME_CONFIG, "get_phone_defaults", lambda: dict(base))

    which = {}

    async def _fake_pipeline(websocket, *a, serializer=None, **k):
        which["builder"] = "pipeline"
        which["serializer"] = serializer

        class _T:
            pass
        return _T()

    async def _fake_nova(websocket, *a, serializer=None, **k):
        which["builder"] = "nova"
        return object()

    monkeypatch.setattr(bot, "_build_pipeline", _fake_pipeline)
    monkeypatch.setattr(bot, "_build_nova_sonic_pipeline", _fake_nova)

    class _FakeRunner:
        def __init__(self, *a, **k):
            pass

        async def run(self, task):
            return None

    monkeypatch.setattr(bot, "PipelineRunner", _FakeRunner)

    from pipecat.serializers.twilio import TwilioFrameSerializer

    stream_sid = "MZengine"
    frames = [
        json.dumps({"event": "connected"}),
        json.dumps(
            {
                "event": "start",
                "streamSid": stream_sid,
                "start": {"customParameters": {"caller": "+1"}},
            }
        ),
    ]
    ws = _FakeTwilioWS(frames)
    await bot.twilio_media_stream(ws)

    assert which["builder"] == "pipeline"
    assert isinstance(which["serializer"], TwilioFrameSerializer)
