"""Unit tests for TranscriptHallucinationFilter (proposal b4ac7049, T2).

Strategy: drive the processor's decision logic directly. We unit-test the pure
predicate ``_should_drop`` (no pipeline wiring needed) for the full matrix, then
do a lightweight end-to-end check of ``process_frame`` by stubbing ``push_frame``
to record which frames survive — asserting interim/other frames always pass and
only judged finals can be dropped.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipecat.frames.frames import (  # noqa: E402
    InterimTranscriptionFrame,
    TranscriptionFrame,
    TextFrame,
)
from pipecat.processors.frame_processor import FrameDirection  # noqa: E402

from asr_filter import (  # noqa: E402
    TranscriptHallucinationFilter,
    _extract_confidence,
)


def _result_with_confidence(conf: float) -> dict:
    """Mimic an AWS Transcribe streaming final result with per-item Confidence."""
    return {
        "Alternatives": [
            {
                "Transcript": "x",
                "Items": [
                    {"Content": "x", "Confidence": conf, "Type": "pronunciation"}
                ],
            }
        ],
        "IsPartial": False,
    }


def _result_no_confidence() -> dict:
    """Final result whose Items carry no Confidence (the 'unavailable' case)."""
    return {
        "Alternatives": [{"Transcript": "x", "Items": [{"Content": "x"}]}],
        "IsPartial": False,
    }


@pytest.fixture
def filt():
    # Explicit params so tests don't depend on env: short=≤4 CJK chars, conf<0.5.
    return TranscriptHallucinationFilter(
        min_confidence=0.5, max_cjk_chars=4, max_latin_words=1, enabled=True
    )


# ---- _extract_confidence ------------------------------------------------

def test_extract_confidence_present():
    assert _extract_confidence(_result_with_confidence(0.3)) == pytest.approx(0.3)


def test_extract_confidence_absent_returns_none():
    assert _extract_confidence(_result_no_confidence()) is None
    assert _extract_confidence(None) is None
    assert _extract_confidence({}) is None


# ---- decision matrix (_should_drop) -------------------------------------

def test_un_low_confidence_dropped(filt):
    drop, reason = filt._should_drop("うん", _result_with_confidence(0.12))
    assert drop is True
    assert "low-conf" in reason


def test_hai_high_confidence_kept(filt):
    # Real short confirmation with high confidence must survive.
    drop, _ = filt._should_drop("はい", _result_with_confidence(0.97))
    assert drop is False


def test_hai_conf_none_kept(filt):
    # Confidence unavailable + not in denylist → keep.
    drop, reason = filt._should_drop("はい", _result_no_confidence())
    assert drop is False
    assert "not-filler" in reason


def test_un_conf_none_dropped(filt):
    # Confidence unavailable + in denylist + short → drop.
    drop, reason = filt._should_drop("うん", _result_no_confidence())
    assert drop is True
    assert "denylist" in reason


def test_digits_always_kept_even_low_conf(filt):
    # 社員番号 / OTP must never be dropped, regardless of confidence.
    for txt in ("W123456", "123456", "１２３４"):
        drop, reason = filt._should_drop(txt, _result_with_confidence(0.01))
        assert drop is False, f"{txt!r} should be kept"
        assert reason == "has-digit"


def test_long_utterance_kept_even_low_conf(filt):
    drop, reason = filt._should_drop(
        "アカウントがロックされたので解除してください", _result_with_confidence(0.1)
    )
    assert drop is False
    assert reason == "long"


def test_iie_not_in_denylist(filt):
    # いいえ is a valid answer; even conf=None it must be kept.
    drop, _ = filt._should_drop("いいえ", _result_no_confidence())
    assert drop is False


# ---- process_frame end-to-end (stubbed push) ----------------------------

class _Recorder(TranscriptHallucinationFilter):
    """Captures frames that survive past push_frame."""

    def __init__(self, **kw):
        super().__init__(**kw)
        self.pushed = []

    async def push_frame(self, frame, direction=FrameDirection.DOWNSTREAM):
        self.pushed.append((frame, direction))


# No pytest-asyncio in this env and no async-test convention in the repo, so
# drive the coroutine with asyncio.run() inside plain sync tests (always runs,
# never silently skipped).

def _run_through(frame, *, enabled=True):
    rec = _Recorder(
        min_confidence=0.5, max_cjk_chars=4, max_latin_words=1, enabled=enabled
    )
    asyncio.run(rec.process_frame(frame, FrameDirection.DOWNSTREAM))
    return any(fr is frame for fr, _ in rec.pushed)


def test_interim_passes_through():
    f = InterimTranscriptionFrame("うん", "", "t", None, result=_result_with_confidence(0.01))
    assert _run_through(f), "interim must pass through"


def test_final_hallucination_swallowed():
    f = TranscriptionFrame("うん", "", "t", None, result=_result_with_confidence(0.12))
    assert not _run_through(f), "final hallucination must be dropped"


def test_final_real_answer_passes():
    f = TranscriptionFrame("はい", "", "t", None, result=_result_with_confidence(0.95))
    assert _run_through(f), "real answer must pass"


def test_disabled_passes_everything():
    f = TranscriptionFrame("うん", "", "t", None, result=_result_with_confidence(0.01))
    assert _run_through(f, enabled=False), "disabled filter must pass everything"


def test_non_transcription_frame_passes():
    f = TextFrame("うん")
    assert _run_through(f), "non-transcription frame must pass"


# ---- _resolve_asr_filter (bot.py) ---------------------------------------
# Resolver maps config keys (max_chars/max_words) → ctor names
# (max_cjk_chars/max_latin_words), takes the defaults segment as an EXPLICIT
# arg (phone-vs-web), and applies per-field precedence demo > segment > env >
# built-in(OFF). importing bot is heavy but the only way to reach the resolver.

import os  # noqa: E402

import bot as _bot  # noqa: E402


@pytest.fixture
def _clear_asr_env(monkeypatch):
    """Ensure no ASR_FILTER_* env leaks into precedence/default tests."""
    for k in (
        "ASR_FILTER_ENABLED",
        "ASR_FILTER_MIN_CONFIDENCE",
        "ASR_FILTER_MAX_CHARS",
        "ASR_FILTER_MAX_WORDS",
    ):
        monkeypatch.delenv(k, raising=False)
    yield


def test_resolve_default_off(_clear_asr_env):
    # Regression-direction: all default (env unset, no global, no demo) → OFF.
    resolved = _bot._resolve_asr_filter({}, {})
    assert resolved["enabled"] is False
    # And a filter built from it does NOT drop the genuine short low-conf
    # Cantonese command "解鎖就好" that the bug dropped. The enabled gate lives in
    # process_frame, so drive a real frame through (not the pure predicate).
    rec = _Recorder(**resolved)
    f = TranscriptionFrame("解鎖就好", "", "t", None, result=_result_with_confidence(0.38))
    asyncio.run(rec.process_frame(f, FrameDirection.DOWNSTREAM))
    assert any(fr is f for fr, _ in rec.pushed), "default-off filter must not drop the real command"


def test_resolve_key_name_map(_clear_asr_env):
    # max_chars→max_cjk_chars, max_words→max_latin_words.
    resolved = _bot._resolve_asr_filter({"asr_filter": {"max_chars": 9, "max_words": 3}}, {})
    assert resolved["max_cjk_chars"] == 9
    assert resolved["max_latin_words"] == 3


def test_resolve_phone_vs_web_segment(_clear_asr_env):
    # A global set ONLY in the phone segment must enable for phone, not web.
    phone_seg = {"asr_filter": {"enabled": True}}
    web_seg = {}
    assert _bot._resolve_asr_filter({}, phone_seg)["enabled"] is True
    assert _bot._resolve_asr_filter({}, web_seg)["enabled"] is False


def test_resolve_precedence_demo_over_segment_over_env(monkeypatch):
    monkeypatch.setenv("ASR_FILTER_ENABLED", "true")
    monkeypatch.setenv("ASR_FILTER_MIN_CONFIDENCE", "0.9")
    monkeypatch.setenv("ASR_FILTER_MAX_CHARS", "2")
    monkeypatch.setenv("ASR_FILTER_MAX_WORDS", "1")
    segment = {"asr_filter": {"min_confidence": 0.7, "max_chars": 5}}
    demo = {"asr_filter": {"min_confidence": 0.3}}
    resolved = _bot._resolve_asr_filter(demo, segment)
    assert resolved["min_confidence"] == 0.3          # demo wins
    assert resolved["max_cjk_chars"] == 5             # segment beats env
    assert resolved["max_latin_words"] == 1           # env (neither demo nor seg)
    assert resolved["enabled"] is True                # env


def test_resolve_demo_enabled_only_inherits_thresholds(monkeypatch):
    # Demo sets only enabled → thresholds fall through to segment/env/default.
    for k in ("ASR_FILTER_ENABLED", "ASR_FILTER_MIN_CONFIDENCE",
              "ASR_FILTER_MAX_CHARS", "ASR_FILTER_MAX_WORDS"):
        monkeypatch.delenv(k, raising=False)
    segment = {"asr_filter": {"min_confidence": 0.2, "max_chars": 6}}
    resolved = _bot._resolve_asr_filter({"asr_filter": {"enabled": True}}, segment)
    assert resolved["enabled"] is True
    assert resolved["min_confidence"] == 0.2          # inherited from segment
    assert resolved["max_cjk_chars"] == 6             # inherited from segment
    assert resolved["max_latin_words"] == 1           # built-in default


def test_resolve_enabled_high_conf_still_drops_filler(_clear_asr_env):
    # enabled + high min_confidence → built filter still drops a true filler.
    resolved = _bot._resolve_asr_filter(
        {"asr_filter": {"enabled": True, "min_confidence": 0.95}}, {}
    )
    filt_on = TranscriptHallucinationFilter(**resolved)
    drop, reason = filt_on._should_drop("うん", _result_with_confidence(0.4))
    assert drop is True
    assert "low-conf" in reason


# ---- _validate_asr_filter_patch (bot.py) --------------------------------

def test_validate_asr_filter_full_and_partial():
    full = _bot._validate_asr_filter_patch(
        {"enabled": True, "min_confidence": 0.3, "max_chars": 6, "max_words": 2}
    )
    assert full == {"enabled": True, "min_confidence": 0.3, "max_chars": 6, "max_words": 2}
    assert isinstance(full["min_confidence"], float)
    # partial → only present keys returned
    assert _bot._validate_asr_filter_patch({"enabled": False}) == {"enabled": False}
    assert _bot._validate_asr_filter_patch({}) == {}


@pytest.mark.parametrize("bad", [
    {"enabled": "yes"},                 # non-bool
    {"min_confidence": 1.5},            # >1
    {"min_confidence": -0.1},           # <0
    {"min_confidence": "x"},            # non-numeric
    {"min_confidence": True},           # bool-as-number
    {"max_chars": -1},                  # negative
    {"max_chars": True},                # bool-as-int
    {"max_chars": 1.5},                 # float not int
    {"max_words": -1},                  # negative
    {"max_words": True},                # bool-as-int
])
def test_validate_asr_filter_400(bad):
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as ei:
        _bot._validate_asr_filter_patch(bad)
    assert ei.value.status_code == 400
