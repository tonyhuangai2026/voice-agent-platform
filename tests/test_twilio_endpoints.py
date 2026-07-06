"""T3 tests: Twilio ingress endpoints + pipecat TwilioFrameSerializer wiring.

Covers (per tech_design 2f6d1455 §2.3 / §3 and the task AC):

  * POST /twilio/incoming-call — 503 when unconfigured, 403 on missing/invalid
    X-Twilio-Signature, 200 + Connect/Stream TwiML (wss .../twilio/media-stream
    + the caller <Parameter> + the *public* host from TWILIO_PUBLIC_BASE_URL,
    never an internal/CloudFront host) on a valid signature.
  * WS /twilio/media-stream — refuses when disabled; on a connected→start→media
    →stop handshake it captures streamSid/caller, constructs a real pipecat
    TwilioFrameSerializer, hands off to _run_phone_session, and cleans up on stop.
  * Serializer wiring sanity — using the REAL pipecat TwilioFrameSerializer API:
    media JSON → deserialize() → InputAudioRawFrame; OutputAudioRawFrame →
    serialize() → media JSON with streamSid; InterruptionFrame → {event:"clear"}.

The endpoint env is read fresh per request (bot._twilio_config), so tests just
monkeypatch the env vars — no module re-import needed. _run_phone_session is
monkeypatched to capture args (this module proves the wiring up to the kernel;
the kernel itself is exercised by tests/test_phone_session.py).
"""

from __future__ import annotations

import asyncio
import base64
import json

import pytest
from fastapi.testclient import TestClient

import bot
import twilio_sig


PUBLIC_BASE = "https://twilio.example.com"
INTERNAL_HOST = "d28jyp0rnkqvcx.cloudfront.net"  # the host Twilio must NOT see
AUTH_TOKEN = "test-auth-token-123"
ACCOUNT_SID = "ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx"


@pytest.fixture
def client():
    return TestClient(bot.app)


def _enable_twilio(monkeypatch, *, account_sid: bool = True):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.setenv("TWILIO_PUBLIC_BASE_URL", PUBLIC_BASE)
    if account_sid:
        monkeypatch.setenv("TWILIO_ACCOUNT_SID", ACCOUNT_SID)
    else:
        monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)


def _disable_twilio(monkeypatch):
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("TWILIO_PUBLIC_BASE_URL", raising=False)
    monkeypatch.delenv("TWILIO_ACCOUNT_SID", raising=False)


# ===========================================================================
# POST /twilio/incoming-call  (AC1)
# ===========================================================================
def test_incoming_call_503_when_not_configured(client, monkeypatch):
    _disable_twilio(monkeypatch)
    resp = client.post("/twilio/incoming-call", data={"From": "+15551234567"})
    assert resp.status_code == 503


def test_incoming_call_403_when_signature_missing(client, monkeypatch):
    _enable_twilio(monkeypatch)
    resp = client.post("/twilio/incoming-call", data={"From": "+15551234567"})
    assert resp.status_code == 403


def test_incoming_call_403_when_signature_invalid(client, monkeypatch):
    _enable_twilio(monkeypatch)
    resp = client.post(
        "/twilio/incoming-call",
        data={"From": "+15551234567"},
        headers={"X-Twilio-Signature": "totally-wrong-signature"},
    )
    assert resp.status_code == 403


def test_incoming_call_403_when_signature_for_wrong_host(client, monkeypatch):
    """Canonical pitfall: a signature computed against the internal CloudFront
    host must NOT validate — the bot signs against TWILIO_PUBLIC_BASE_URL."""
    _enable_twilio(monkeypatch)
    params = {"From": "+15551234567", "CallSid": "CA123"}
    wrong_url = f"https://{INTERNAL_HOST}/twilio/incoming-call"
    bad_sig = twilio_sig.compute_twilio_signature(AUTH_TOKEN, wrong_url, params)
    resp = client.post(
        "/twilio/incoming-call",
        data=params,
        headers={"X-Twilio-Signature": bad_sig},
    )
    assert resp.status_code == 403


def test_incoming_call_200_valid_signature_returns_twiml(client, monkeypatch):
    _enable_twilio(monkeypatch)
    params = {"From": "+15557654321", "CallSid": "CA456", "To": "+18005551212"}
    # Sign against the PUBLIC base + path (no query here) exactly as the bot does.
    full_url = twilio_sig.build_signed_url(PUBLIC_BASE, "/twilio/incoming-call", "")
    good_sig = twilio_sig.compute_twilio_signature(AUTH_TOKEN, full_url, params)

    resp = client.post(
        "/twilio/incoming-call",
        data=params,
        headers={"X-Twilio-Signature": good_sig},
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/xml")
    body = resp.text
    # wss Stream URL points at our media-stream on the PUBLIC host (not internal).
    assert "wss://twilio.example.com/twilio/media-stream" in body
    assert INTERNAL_HOST not in body
    # caller Parameter carries the From number.
    assert 'name="caller"' in body
    assert "+15557654321" in body
    assert "<Connect>" in body and "<Stream" in body


def test_incoming_call_signature_includes_query_string(client, monkeypatch):
    """When Twilio appends a query string, the signed full_url must include it."""
    _enable_twilio(monkeypatch)
    params = {"From": "+15550009999"}
    full_url = twilio_sig.build_signed_url(
        PUBLIC_BASE, "/twilio/incoming-call", "tenant=acme"
    )
    good_sig = twilio_sig.compute_twilio_signature(AUTH_TOKEN, full_url, params)
    resp = client.post(
        "/twilio/incoming-call?tenant=acme",
        data=params,
        headers={"X-Twilio-Signature": good_sig},
    )
    assert resp.status_code == 200
    # And a signature that omitted the query must be rejected.
    sig_no_query = twilio_sig.compute_twilio_signature(
        AUTH_TOKEN,
        twilio_sig.build_signed_url(PUBLIC_BASE, "/twilio/incoming-call", ""),
        params,
    )
    resp_bad = client.post(
        "/twilio/incoming-call?tenant=acme",
        data=params,
        headers={"X-Twilio-Signature": sig_no_query},
    )
    assert resp_bad.status_code == 403


# ===========================================================================
# WS /twilio/media-stream  (AC2)
# ===========================================================================
class _FakeTwilioWS:
    """Drives the media-stream endpoint with a scripted Twilio frame sequence.

    receive_text() pops queued frames (JSON strings); when exhausted it behaves
    like a disconnect by raising, which is what the real transport / our reader
    treat as end-of-stream.
    """

    def __init__(self, frames):
        self._frames = list(frames)
        self.accepted = False
        self.closed_code = None
        self.sent = []

    async def accept(self):
        self.accepted = True

    async def receive_text(self):
        if not self._frames:
            raise RuntimeError("client disconnected")
        return self._frames.pop(0)

    async def close(self, code=1000):
        self.closed_code = code

    async def send_text(self, data):
        self.sent.append(data)


@pytest.mark.asyncio
async def test_media_stream_refused_when_disabled(monkeypatch):
    _disable_twilio(monkeypatch)
    ws = _FakeTwilioWS([])
    await bot.twilio_media_stream(ws)
    assert ws.accepted is True
    assert ws.closed_code is not None  # connection refused/closed


@pytest.mark.asyncio
async def test_media_stream_closes_when_no_start(monkeypatch):
    _enable_twilio(monkeypatch)
    # connected then immediate disconnect — never a start → abuse guard closes.
    ws = _FakeTwilioWS([json.dumps({"event": "connected"})])
    await bot.twilio_media_stream(ws)
    assert ws.closed_code is not None


@pytest.mark.asyncio
async def test_media_stream_closes_on_illegal_pre_start_frame(monkeypatch):
    _enable_twilio(monkeypatch)
    # media before start is illegal → close, never start a session.
    ws = _FakeTwilioWS([json.dumps({"event": "media", "media": {"payload": "x"}})])
    called = {}

    async def _fake_kernel(*a, **k):
        called["ran"] = True

    monkeypatch.setattr(bot, "_run_phone_session", _fake_kernel)
    await bot.twilio_media_stream(ws)
    assert ws.closed_code is not None
    assert "ran" not in called


@pytest.mark.asyncio
async def test_media_stream_happy_path_builds_serializer_and_runs_kernel(monkeypatch):
    _enable_twilio(monkeypatch)
    captured = {}

    async def _fake_kernel(websocket, *, call_id, caller, serializer=None):
        captured["call_id"] = call_id
        captured["caller"] = caller
        captured["serializer"] = serializer
        captured["registered"] = call_id in bot.ACTIVE_SESSIONS
        # Mirror the real kernel's finally: cleanup on stop/disconnect. (The
        # real cleanup path is exercised by tests/test_phone_session.py.)
        await bot.session_unregister(call_id)

    monkeypatch.setattr(bot, "_run_phone_session", _fake_kernel)

    stream_sid = "MZ1234567890abcdef"
    frames = [
        json.dumps({"event": "connected", "protocol": "Call"}),
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
        json.dumps({"event": "media", "media": {"payload": "AAAA"}}),
        json.dumps({"event": "stop"}),
    ]
    ws = _FakeTwilioWS(frames)
    await bot.twilio_media_stream(ws)

    from pipecat.serializers.twilio import TwilioFrameSerializer

    assert ws.accepted is True
    assert captured["call_id"] == f"twilio-{stream_sid}"
    assert captured["caller"] == "+15551112222"
    assert isinstance(captured["serializer"], TwilioFrameSerializer)
    assert captured["serializer"]._stream_sid == stream_sid
    # session was registered before hand-off; kernel's finally unregisters it.
    assert captured["registered"] is True
    assert f"twilio-{stream_sid}" not in bot.ACTIVE_SESSIONS  # cleaned up on stop


@pytest.mark.asyncio
async def test_media_stream_auto_hangup_off_without_account_sid(monkeypatch):
    """Without TWILIO_ACCOUNT_SID the serializer must be built with
    auto_hang_up=False, otherwise its constructor raises ValueError."""
    _enable_twilio(monkeypatch, account_sid=False)
    captured = {}

    async def _fake_kernel(websocket, *, call_id, caller, serializer=None):
        captured["serializer"] = serializer

    monkeypatch.setattr(bot, "_run_phone_session", _fake_kernel)
    stream_sid = "MZdeadbeef"
    frames = [
        json.dumps({"event": "connected"}),
        json.dumps(
            {
                "event": "start",
                "streamSid": stream_sid,
                "start": {"callSid": "CA1", "customParameters": {"caller": "+1"}},
            }
        ),
    ]
    ws = _FakeTwilioWS(frames)
    await bot.twilio_media_stream(ws)
    assert captured["serializer"]._params.auto_hang_up is False


# ===========================================================================
# Serializer wiring sanity — real pipecat API  (AC3)
# ===========================================================================
def _ulaw_silence(n: int = 160) -> bytes:
    """A known μ-law payload: ``n`` bytes of μ-law silence (0xFF)."""
    return b"\xff" * n


async def _make_serializer(stream_sid="MZwiringtest"):
    from pipecat.frames.frames import StartFrame
    from pipecat.serializers.twilio import TwilioFrameSerializer

    ser = TwilioFrameSerializer(
        stream_sid,
        params=TwilioFrameSerializer.InputParams(auto_hang_up=False),
    )
    # setup() pulls the pipeline input rate from StartFrame; use 8 kHz so the
    # serializer's μ-law<->PCM path is rate-identity (no resampling artifacts).
    await ser.setup(StartFrame(audio_in_sample_rate=8000, audio_out_sample_rate=8000))
    return ser


@pytest.mark.asyncio
async def test_serializer_deserialize_media_to_input_audio_frame():
    from pipecat.frames.frames import InputAudioRawFrame

    ser = await _make_serializer()
    payload_b64 = base64.b64encode(_ulaw_silence()).decode()
    media_json = json.dumps(
        {"event": "media", "media": {"payload": payload_b64}}
    )
    frame = await ser.deserialize(media_json)
    assert isinstance(frame, InputAudioRawFrame)
    assert frame.sample_rate == 8000
    assert len(frame.audio) > 0


@pytest.mark.asyncio
async def test_serializer_serialize_output_audio_to_media_json():
    from pipecat.frames.frames import OutputAudioRawFrame

    ser = await _make_serializer("MZoutput")
    # 8 kHz PCM16 silence in → 8 kHz μ-law media event out.
    pcm = b"\x00\x00" * 160
    out = await ser.serialize(
        OutputAudioRawFrame(audio=pcm, sample_rate=8000, num_channels=1)
    )
    assert out is not None
    msg = json.loads(out)
    assert msg["event"] == "media"
    assert msg["streamSid"] == "MZoutput"
    assert "payload" in msg["media"]
    # payload is valid base64 (μ-law bytes).
    base64.b64decode(msg["media"]["payload"])


@pytest.mark.asyncio
async def test_serializer_interruption_to_clear_event():
    from pipecat.frames.frames import InterruptionFrame

    ser = await _make_serializer("MZclear")
    out = await ser.serialize(InterruptionFrame())
    assert out is not None
    msg = json.loads(out)
    assert msg == {"event": "clear", "streamSid": "MZclear"}


# ===========================================================================
# env gate sanity  (AC4)
# ===========================================================================
def test_twilio_config_disabled_without_env(monkeypatch):
    _disable_twilio(monkeypatch)
    cfg = bot._twilio_config()
    assert cfg["enabled"] is False


def test_twilio_config_enabled_with_token_and_base(monkeypatch):
    _enable_twilio(monkeypatch)
    cfg = bot._twilio_config()
    assert cfg["enabled"] is True
    assert cfg["auth_token"] == AUTH_TOKEN
    assert cfg["public_base"] == PUBLIC_BASE


def test_twilio_config_disabled_with_token_but_no_base(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", AUTH_TOKEN)
    monkeypatch.delenv("TWILIO_PUBLIC_BASE_URL", raising=False)
    assert bot._twilio_config()["enabled"] is False


def test_public_host_strips_scheme():
    assert bot._twilio_public_host("https://twilio.example.com") == "twilio.example.com"
    assert bot._twilio_public_host("https://twilio.example.com/") == "twilio.example.com"
    assert bot._twilio_public_host("http://h:8080") == "h:8080"
