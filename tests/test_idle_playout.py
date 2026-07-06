"""Idle-nudge playout-duration timing fix — BotPlayoutTracker unit tests.

The idle-nudge timer must key off when the bot's audio finishes *playing*, not
when TTS finishes *generating*. The server models playout duration from the
PCM16 byte count: duration = bytes / (sample_rate * 2 bytes/sample * channels).
These tests pin that math and the per-turn reset / deferral semantics that the
idle handler relies on (a nudge requested while audio remains is deferred).

Hermetic: only imports BotPlayoutTracker; no AWS, no pipeline, no network.
"""
from __future__ import annotations

import os

import pytest

# Module-level imports in bot.py touch a few env vars; give them dummies so the
# import is hermetic (these tests never hit AWS / admin / auth).
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("ADMIN_PASSWORD", "test-pwd")
os.environ.setdefault("AUTH_SECRET", "test-secret")
os.environ.setdefault("MINIMAX_API_KEY", "x")
os.environ.setdefault("SITE_PASSWORD", "")

import bot  # noqa: E402

RATE = 24000  # bot.OUTPUT_SAMPLE_RATE


def test_bot_audio_secs_matches_pcm16_duration():
    """N bytes at rate R mono PCM16 → N / (R*2) seconds."""
    t = bot.BotPlayoutTracker(out_sample_rate=RATE, channels=1)
    # 1 second of audio = RATE samples * 2 bytes.
    one_second_bytes = RATE * 2
    t.add_audio(one_second_bytes, now=100.0)
    assert t.bot_audio_secs == pytest.approx(1.0)
    # Accumulates across chunks within the turn.
    t.add_audio(one_second_bytes, now=100.1)
    assert t.bot_audio_secs == pytest.approx(2.0)


def test_playout_finish_and_remaining():
    """playout_finish_at = start + duration; remaining counts down from now."""
    t = bot.BotPlayoutTracker(out_sample_rate=RATE, channels=1)
    t.add_audio(RATE * 2 * 3, now=50.0)  # 3 s of audio, started at t=50
    assert t.playout_finish_at() == pytest.approx(53.0)
    # 1 s elapsed → ~2 s still unplayed (this is the "defer the nudge" signal).
    assert t.remaining(now=51.0) == pytest.approx(2.0)
    # Past the finish → non-positive remaining → nudge may proceed.
    assert t.remaining(now=54.0) == pytest.approx(-1.0)


def test_remaining_zero_before_any_audio():
    """No bot audio yet → no playout to wait on."""
    t = bot.BotPlayoutTracker(out_sample_rate=RATE, channels=1)
    assert t.playout_finish_at() is None
    assert t.remaining(now=10.0) == 0.0


def test_new_turn_resets_byte_counter():
    """First audio frame of a fresh turn measures from its own first sample,
    not from the previous turn's bytes (so a short reply isn't seen as long)."""
    t = bot.BotPlayoutTracker(out_sample_rate=RATE, channels=1)
    t.add_audio(RATE * 2 * 5, now=0.0)  # turn 1: 5 s
    assert t.bot_audio_secs == pytest.approx(5.0)
    t.on_bot_turn_end()  # bot stopped (or user barged in)
    t.add_audio(RATE * 2 * 1, now=10.0)  # turn 2: 1 s, fresh start
    assert t.bot_audio_secs == pytest.approx(1.0)
    assert t.playout_finish_at() == pytest.approx(11.0)


def test_bot_turn_start_before_audio_does_not_zero_first_chunk():
    """If BotStartedSpeaking is observed first it anchors the clock; if the
    first audio frame is observed first it anchors instead — either ordering
    must keep the first chunk's bytes (the early-fire-before-BotStarted case)."""
    # Ordering A: audio frame first (real pipeline ordering), then turn-start.
    a = bot.BotPlayoutTracker(out_sample_rate=RATE, channels=1)
    a.add_audio(RATE * 2, now=5.0)          # 1 s chunk anchors start at 5.0
    a.on_bot_turn_start(now=5.01)           # must NOT zero the counted chunk
    a.add_audio(RATE * 2, now=5.02)         # +1 s
    assert a.bot_audio_secs == pytest.approx(2.0)
    assert a.playout_finish_at() == pytest.approx(7.0)  # 5.0 + 2 s

    # Ordering B: turn-start first, then audio.
    b = bot.BotPlayoutTracker(out_sample_rate=RATE, channels=1)
    b.on_bot_turn_start(now=20.0)
    b.add_audio(RATE * 2 * 2, now=20.0)     # 2 s
    assert b.bot_audio_secs == pytest.approx(2.0)
    assert b.playout_finish_at() == pytest.approx(22.0)


def test_deferral_signal_then_clear():
    """Reproduces the handler's decision: while remaining>0 the nudge is
    deferred; once past playout-finish (and no new audio) it may fire."""
    t = bot.BotPlayoutTracker(out_sample_rate=RATE, channels=1)
    t.add_audio(RATE * 2 * 4, now=0.0)  # 4 s opening sentence
    # Idle controller fires its 4 s window early (at the generation-done
    # BotStopped, say t=1.5) — bot still has ~2.5 s of audio left.
    assert t.remaining(now=1.5) > 0       # → defer, don't nudge / don't count
    # After playout finishes and the user is still silent, the re-check passes.
    assert t.remaining(now=4.3) <= 0      # → nudge allowed
