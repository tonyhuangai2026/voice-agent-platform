"""T1 tests: LatencyObserver + latency_log — synthetic frames, injected clock.

No real pipeline, no AWS, no sleeps. We feed hand-built frame objects (each with
a unique ``.id``) to ``LatencyObserver.on_push_frame`` through a controlled
monotonic clock and assert the derived latencies, the graceful nova-sonic
degradation, MetricsFrame consumption, half-turn discard, and the JSONL log
format (tmp file + empty-path no-op).

Mirrors the monkeypatch style of tests/test_phone_session.py: fakes capture
what the unit under test produces, no network.
"""

from __future__ import annotations

import asyncio
import json

import pytest

import latency_log
from latency_observer import LatencyObserver

# Real frame classes — we instantiate them so isinstance checks in the observer
# hit the genuine types (the dedupe/boundary logic keys off real frame types).
from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    MetricsFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.metrics.metrics import (
    LLMTokenUsage,
    LLMUsageMetricsData,
    TTFBMetricsData,
    TTSUsageMetricsData,
)


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #


class FakeClock:
    """Deterministic monotonic clock. ``tick`` advances by ``dt`` and returns
    the new time, so a test can stamp each frame at a known offset."""

    def __init__(self, start: float = 1000.0):
        self.now = start

    def __call__(self) -> float:
        return self.now

    def tick(self, dt: float) -> float:
        self.now += dt
        return self.now


class FakePushed:
    """Stand-in for FramePushed: the observer only reads ``.frame``."""

    def __init__(self, frame):
        self.frame = frame
        self.direction = None


_next_id = [0]


def _mk(frame_cls, **kw):
    """Build a frame and force a unique monotonic ``.id`` (pipecat normally
    assigns this; we set it explicitly so dedupe is testable)."""
    f = frame_cls(**kw)
    _next_id[0] += 1
    f.id = _next_id[0]
    return f


class CapturingEmit:
    """Async emit that records every payload it receives."""

    def __init__(self):
        self.events: list[dict] = []

    async def __call__(self, payload: dict):
        self.events.append(payload)


class FakeLog:
    """Records records handed to write(); never touches disk."""

    def __init__(self):
        self.records: list[dict] = []

    def write(self, record: dict):
        self.records.append(record)


def _feed(observer, frame, clock=None, dt=None):
    """Optionally advance the clock, then push one frame synchronously."""
    if clock is not None and dt is not None:
        clock.tick(dt)
    asyncio.run(observer.on_push_frame(FakePushed(frame)))


# --------------------------------------------------------------------------- #
# 1. Full pipeline turn → all stages computed correctly
# --------------------------------------------------------------------------- #


def test_full_turn_stage_latencies():
    clock = FakeClock(start=1000.0)
    emit = CapturingEmit()
    log = FakeLog()
    obs = LatencyObserver(
        emit=emit,
        call_id="web-123",
        engine="pipeline",
        scenario="it-helpdesk",
        lang="zh-HK",
        clock=clock,
        log_writer=log,
    )

    # Stamp each stage at a deliberate offset. The clock value at the moment a
    # frame is pushed becomes that stage's timestamp.
    _feed(obs, _mk(UserStartedSpeakingFrame))          # t=1000.0 user_start
    _feed(obs, _mk(UserStoppedSpeakingFrame), clock, 0.50)   # t=1000.50 user_stop
    _feed(obs, _mk(TranscriptionFrame, text="hi", user_id="u", timestamp="t"),
          clock, 0.42)                                  # t=1000.92 asr_final
    _feed(obs, _mk(LLMFullResponseStartFrame), clock, 0.10)  # t=1001.02 llm_start
    _feed(obs, _mk(LLMTextFrame, text="he"), clock, 0.46)    # t=1001.48 llm_first
    _feed(obs, _mk(LLMFullResponseEndFrame), clock, 0.52)    # t=1002.00 llm_end
    _feed(obs, _mk(TTSStartedFrame), clock, 0.05)            # t=1002.05 tts_start
    _feed(obs, _mk(TTSAudioRawFrame, audio=b"\0\0", sample_rate=16000,
                   num_channels=1), clock, 0.31)             # t=1002.36 tts_first_audio
    _feed(obs, _mk(BotStartedSpeakingFrame), clock, 0.04)    # t=1002.40 bot_start

    assert len(log.records) == 1
    rec = log.records[0]
    # stt_ms = asr_final - user_stop = 0.42s
    assert rec["stt_ms"] == 420
    # llm_ttft_ms = llm_first - asr_final = 0.10 + 0.46 = 0.56s
    assert rec["llm_ttft_ms"] == 560
    # llm_total_ms = llm_end - llm_start = 0.46 + 0.52 = 0.98s
    assert rec["llm_total_ms"] == 980
    # tts_ttfb_ms = tts_first_audio - tts_start = 0.31s
    assert rec["tts_ttfb_ms"] == 310
    # e2e_ms = bot_start - user_stop = total since user_stop
    #        = 0.42+0.10+0.46+0.52+0.05+0.31+0.04 = 1.90s
    assert rec["e2e_ms"] == 1900
    assert rec["turn_id"] == 1
    assert rec["engine"] == "pipeline"
    assert rec["call_id"] == "web-123"

    # Live event mirrors the record.
    assert len(emit.events) == 1
    assert emit.events[0]["type"] == "latency_report"
    assert emit.events[0]["e2e_ms"] == 1900


def test_dedupe_first_occurrence_wins():
    """Re-pushing the same frame.id (crossing processor boundaries) must not
    overwrite the first timestamp."""
    clock = FakeClock(start=500.0)
    obs = LatencyObserver(emit=CapturingEmit(), clock=clock, log_writer=FakeLog())

    _feed(obs, _mk(UserStartedSpeakingFrame))
    asr = _mk(TranscriptionFrame, text="x", user_id="u", timestamp="t")
    clock.tick(0.3)
    _feed(obs, asr)               # asr_final recorded here (t=500.3)
    clock.tick(5.0)
    _feed(obs, asr)               # same id → ignored, must NOT move to 505.3
    assert obs._ts["asr_final"] == 500.3


# --------------------------------------------------------------------------- #
# 2. nova-sonic degradation → only e2e_ms, three stages null
# --------------------------------------------------------------------------- #


def test_nova_sonic_degradation_e2e_only():
    clock = FakeClock(start=0.0)
    log = FakeLog()
    obs = LatencyObserver(
        emit=CapturingEmit(), engine="nova-sonic", clock=clock, log_writer=log
    )

    _feed(obs, _mk(UserStartedSpeakingFrame))
    _feed(obs, _mk(UserStoppedSpeakingFrame), clock, 0.25)
    _feed(obs, _mk(BotStartedSpeakingFrame), clock, 1.10)

    assert len(log.records) == 1
    rec = log.records[0]
    assert rec["e2e_ms"] == 1100           # bot_start - user_stop = 1.10s
    assert rec["stt_ms"] is None
    assert rec["llm_ttft_ms"] is None
    assert rec["llm_total_ms"] is None
    assert rec["tts_ttfb_ms"] is None
    assert rec["engine"] == "nova-sonic"


# --------------------------------------------------------------------------- #
# 3. MetricsFrame consumption
# --------------------------------------------------------------------------- #


def test_metrics_frame_consumption():
    clock = FakeClock(start=10.0)
    log = FakeLog()
    obs = LatencyObserver(emit=CapturingEmit(), clock=clock, log_writer=log)

    _feed(obs, _mk(UserStartedSpeakingFrame))
    _feed(obs, _mk(UserStoppedSpeakingFrame), clock, 0.1)

    metrics = _mk(
        MetricsFrame,
        data=[
            TTFBMetricsData(processor="LLMService#0", value=0.54),
            TTFBMetricsData(processor="TTSService#0", value=0.30),
            LLMUsageMetricsData(
                processor="LLMService#0",
                value=LLMTokenUsage(
                    prompt_tokens=1200, completion_tokens=48, total_tokens=1248
                ),
            ),
            TTSUsageMetricsData(processor="TTSService#0", value=86),
        ],
    )
    _feed(obs, metrics)
    _feed(obs, _mk(BotStartedSpeakingFrame), clock, 0.9)

    rec = log.records[0]
    assert rec["svc_llm_ttfb_ms"] == 540
    assert rec["svc_tts_ttfb_ms"] == 300
    assert rec["tokens"] == {"prompt": 1200, "completion": 48, "total": 1248}
    assert rec["tts_chars"] == 86


# --------------------------------------------------------------------------- #
# 4. Half-turn discard → no record, no raise
# --------------------------------------------------------------------------- #


def test_half_turn_discarded_no_record():
    clock = FakeClock(start=0.0)
    log = FakeLog()
    emit = CapturingEmit()
    obs = LatencyObserver(emit=emit, clock=clock, log_writer=log)

    # Open a turn, get partway, then a NEW user-start arrives before any
    # bot-start (e.g. barge-in) → the first turn is abandoned.
    _feed(obs, _mk(UserStartedSpeakingFrame))
    _feed(obs, _mk(UserStoppedSpeakingFrame), clock, 0.2)
    _feed(obs, _mk(TranscriptionFrame, text="x", user_id="u", timestamp="t"),
          clock, 0.2)
    _feed(obs, _mk(UserStartedSpeakingFrame), clock, 0.5)  # new turn, no close

    # Nothing written/emitted yet (no turn ever closed).
    assert log.records == []
    assert emit.events == []

    # The new (second) turn can still close cleanly.
    _feed(obs, _mk(UserStoppedSpeakingFrame), clock, 0.1)
    _feed(obs, _mk(BotStartedSpeakingFrame), clock, 0.8)
    assert len(log.records) == 1
    assert log.records[0]["turn_id"] == 2
    assert log.records[0]["e2e_ms"] == 800  # bot_start - user_stop of turn 2


def test_observer_never_raises_on_bad_frame():
    """A frame whose attribute access explodes must be swallowed."""
    obs = LatencyObserver(emit=CapturingEmit(), clock=FakeClock(), log_writer=FakeLog())

    class Boom:
        @property
        def id(self):
            raise RuntimeError("boom")

    # Should not raise.
    asyncio.run(obs.on_push_frame(FakePushed(_mk(UserStartedSpeakingFrame))))
    asyncio.run(obs.on_push_frame(FakePushed(Boom())))


def test_bot_start_without_open_turn_ignored():
    """Opening greeting bot audio (no user turn) → no record, no crash."""
    log = FakeLog()
    obs = LatencyObserver(emit=CapturingEmit(), clock=FakeClock(), log_writer=log)
    _feed(obs, _mk(BotStartedSpeakingFrame))
    assert log.records == []


# --------------------------------------------------------------------------- #
# 5. JSONL log format (tmp file) + empty-path no-op
# --------------------------------------------------------------------------- #


def test_jsonl_log_writes_single_valid_line(tmp_path, monkeypatch):
    monkeypatch.setattr(latency_log, "_warned_once", False)
    path = tmp_path / "lat.jsonl"
    monkeypatch.setenv("LATENCY_LOG_PATH", str(path))

    rec1 = {"call_id": "web-1", "turn_id": 1, "e2e_ms": 1840, "stt_ms": None}
    rec2 = {"call_id": "web-1", "turn_id": 2, "e2e_ms": 900, "msg": "café"}
    latency_log.write(rec1)
    latency_log.write(rec2)

    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0] == rec1
    assert parsed[1] == rec2
    # ensure_ascii=False keeps non-ASCII readable.
    assert "café" in lines[1]


def test_empty_path_is_noop(tmp_path, monkeypatch):
    monkeypatch.setattr(latency_log, "_warned_once", False)
    monkeypatch.setenv("LATENCY_LOG_PATH", "")
    # No file should be created; no exception.
    latency_log.write({"x": 1})
    assert list(tmp_path.iterdir()) == []


def test_write_failure_degrades_without_raising(monkeypatch):
    monkeypatch.setattr(latency_log, "_warned_once", False)
    # Point at a path that can't be opened (a directory component is a file).
    monkeypatch.setenv("LATENCY_LOG_PATH", "/nonexistent_dir_xyz/sub/lat.jsonl")
    # Must not raise.
    latency_log.write({"x": 1})


def test_observer_default_log_writer_uses_empty_path(monkeypatch):
    """With the real latency_log module and empty path, a full turn closes,
    emits, and writes nothing to disk — exercising the default wiring."""
    monkeypatch.setenv("LATENCY_LOG_PATH", "")
    clock = FakeClock()
    emit = CapturingEmit()
    obs = LatencyObserver(emit=emit, clock=clock)  # default log_writer=latency_log

    _feed(obs, _mk(UserStartedSpeakingFrame))
    _feed(obs, _mk(UserStoppedSpeakingFrame), clock, 0.1)
    _feed(obs, _mk(BotStartedSpeakingFrame), clock, 0.5)

    assert len(emit.events) == 1
    assert emit.events[0]["type"] == "latency_report"
