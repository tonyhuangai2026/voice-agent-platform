"""Tests for the phone uplink sample-rate handling (proposal b82af82c).

voice-server now sends native 8 kHz on the phone uplink. Backend adapts:
  - pipeline / Transcribe: feed native 8 kHz directly (input_sample_rate=8000)
  - nova-sonic: upsample 8 kHz -> 16 kHz (UpsamplingPCMSerializer) so the S2S
    model still gets 16 kHz (no regression)
Twilio path (serializer != None) is untouched. Web (non-phone) stays 16 kHz.

We test the serializers directly + capture the args _run_phone_session passes
to the pipeline builders by monkeypatching them.
"""

import asyncio
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------
def test_rawpcm_serializer_tags_8000():
    s = bot.RawPCMSerializer(8000, bot.OUTPUT_SAMPLE_RATE)
    f = asyncio.run(s.deserialize(b"\x01\x00" * 160))
    assert f.sample_rate == 8000
    assert len(f.audio) == 320  # unchanged, not upsampled


def test_rawpcm_serializer_tags_16000_for_web():
    s = bot.RawPCMSerializer(16000, bot.OUTPUT_SAMPLE_RATE)
    f = asyncio.run(s.deserialize(b"\x01\x00" * 160))
    assert f.sample_rate == 16000


def test_upsampling_serializer_8k_to_16k():
    u = bot.UpsamplingPCMSerializer(8000, 16000, bot.OUTPUT_SAMPLE_RATE)
    f = asyncio.run(u.deserialize(b"\x01\x00" * 160))  # 160 samples @8k = 320 bytes
    assert f.sample_rate == 16000
    # 8k -> 16k doubles the sample count (320 -> ~640 bytes)
    assert len(f.audio) == 640


def test_upsample_helper_identity_and_ratio():
    pcm = b"\x02\x00" * 100  # 100 samples
    assert bot._upsample_pcm16_linear(pcm, 8000, 8000) == pcm  # identity
    out = bot._upsample_pcm16_linear(pcm, 8000, 16000)
    assert len(out) // 2 == 200  # doubled
    assert bot._upsample_pcm16_linear(b"", 8000, 16000) == b""  # empty-safe


# ---------------------------------------------------------------------------
# _run_phone_session: capture builder args per engine / path
# ---------------------------------------------------------------------------
class _FakeTask:
    async def cancel(self, *a, **k):
        pass


def _drive_phone_session(monkeypatch, *, engine, serializer):
    """Run _run_phone_session far enough to capture the builder call args, then
    abort (we don't want to actually run a PipelineRunner)."""
    captured = {}

    async def fake_build_pipeline(*args, **kwargs):
        captured["which"] = "pipeline"
        captured["input_sample_rate"] = kwargs.get("input_sample_rate")
        captured["serializer"] = kwargs.get("serializer")
        return _FakeTask()

    async def fake_build_nova(*args, **kwargs):
        captured["which"] = "nova"
        captured["input_sample_rate"] = kwargs.get("input_sample_rate")
        captured["serializer"] = kwargs.get("serializer")
        return _FakeTask()

    async def fake_runner_run(self, task):
        # stop right after build; nothing to run
        return None

    monkeypatch.setattr(bot, "_build_pipeline", fake_build_pipeline)
    monkeypatch.setattr(bot, "_build_nova_sonic_pipeline", fake_build_nova)
    monkeypatch.setattr(bot.PipelineRunner, "run", fake_runner_run)
    # runtime config → chosen engine, zh-HK (pipeline default) / en-US-ish
    monkeypatch.setattr(
        bot.RUNTIME_CONFIG, "get_phone_defaults",
        lambda: {"engine": engine, "lang": "zh-HK", "scenario": "default",
                 "voice": bot.DEFAULT_MINIMAX_VOICE, "provider": "minimax",
                 "model": bot.DEFAULT_MODEL, "minimax_model": bot.DEFAULT_MINIMAX_MODEL},
    )
    # neutralize side effects
    monkeypatch.setattr(bot, "log_activity", lambda **k: _noop_coro())

    class _FakeWS:
        async def accept(self, *a, **k): pass
        async def close(self, *a, **k): pass
        async def send_text(self, *a, **k): pass

    asyncio.run(bot._run_phone_session(
        _FakeWS(), call_id="test-call", caller="+100", serializer=serializer))
    return captured


async def _noop_coro():
    return None


def test_phone_pipeline_uses_8000(monkeypatch):
    cap = _drive_phone_session(monkeypatch, engine="pipeline", serializer=None)
    assert cap["which"] == "pipeline"
    assert cap["input_sample_rate"] == 8000  # native 8 kHz to Transcribe
    # Chime path: serializer stays None → builder makes RawPCMSerializer(8000)
    assert cap["serializer"] is None


def test_phone_nova_uses_16000_via_upsampling_serializer(monkeypatch):
    cap = _drive_phone_session(monkeypatch, engine="nova-sonic", serializer=None)
    assert cap["which"] == "nova"
    assert cap["input_sample_rate"] == bot.INPUT_SAMPLE_RATE == 16000
    # nova gets an UpsamplingPCMSerializer (8k wire -> 16k frames)
    assert isinstance(cap["serializer"], bot.UpsamplingPCMSerializer)


def test_twilio_serializer_left_untouched(monkeypatch):
    sentinel = bot.RawPCMSerializer(16000, bot.OUTPUT_SAMPLE_RATE)  # stand-in for Twilio's
    cap = _drive_phone_session(monkeypatch, engine="pipeline", serializer=sentinel)
    # caller-provided serializer must pass through unchanged, and we must NOT
    # override input_sample_rate to 8000 for a non-Chime (Twilio) caller.
    assert cap["serializer"] is sentinel
    assert cap["input_sample_rate"] == bot.INPUT_SAMPLE_RATE  # not forced to 8000
