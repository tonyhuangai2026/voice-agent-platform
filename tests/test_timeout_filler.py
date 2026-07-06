"""Tests for timeout_filler — Observer architecture (proposal 1b606e70).

Two layers:

* **Unit (pure logic):** ``pick_filler`` — per-language independent pools
  (zh-CN/zh-HK/en-US/ja-JP), en-US fallback for an unknown language, and
  deterministic selection under an injected ``rng``.

* **Observer behaviour:** drive ``TimeoutFillerObserver.on_push_frame`` with a
  mock ``task`` recording ``queue_frames`` calls. The filler is now an OBSERVER
  (not an in-pipeline processor): it sees every frame regardless of direction,
  including the downstream ``TTSStartedFrame``. We assert:

  - **Core race test:** ``UserStopped`` arms the timer; a ``TTSStartedFrame``
    within the threshold cancels it → ``task.queue_frames`` is NEVER called
    (the filler can no longer queue behind the real reply — the bug is gone).
  - An uncancelled timeout calls ``queue_frames`` once with a single
    ``TTSSpeakFrame`` whose text is in the language pool and
    ``append_to_context is False``.
  - ``VADUserStoppedSpeakingFrame`` also arms; barge-in via
    ``UserStartedSpeakingFrame`` AND ``VADUserStartedSpeakingFrame`` cancels.
  - ``probability`` 0/1 boundaries; ``lang`` fallback to en-US; ``enabled=False``
    is a pure no-op.
  - Timer cleanup: after fire or cancel, ``_pending`` is None (no leak), and
    cancelling an armed timer never raises.

The timeout is set to a few ms and we ``asyncio.sleep`` a small margin past it,
so the timer-fired assertions are deterministic without real-time flakiness.
"""

import asyncio
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from pipecat.frames.frames import (  # noqa: E402
    BotStartedSpeakingFrame,
    TextFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.processors.frame_processor import FrameDirection  # noqa: E402
from pipecat.observers.base_observer import FramePushed  # noqa: E402

from timeout_filler import (  # noqa: E402
    DEFAULT_LANG_FALLBACK,
    FILLERS,
    TimeoutFillerObserver,
    pick_filler,
)


# ==========================================================================
# pick_filler — pure function (AC#1)
# ==========================================================================

class _SeqRng:
    """Deterministic stand-in for random: choice() returns a fixed index,
    random() pops from a preset queue."""

    def __init__(self, choice_index=0, randoms=None):
        self._choice_index = choice_index
        self._randoms = list(randoms or [])

    def choice(self, seq):
        return seq[self._choice_index]

    def random(self):
        return self._randoms.pop(0) if self._randoms else 0.0


def test_pick_filler_each_language_draws_from_own_pool():
    # Every listed language draws ONLY from its own independent pool.
    for lang in ("zh-CN", "zh-HK", "en-US", "ja-JP"):
        for i in range(len(FILLERS[lang])):
            got = pick_filler(lang, rng=_SeqRng(choice_index=i))
            assert got == FILLERS[lang][i]
            assert got in FILLERS[lang]


def test_pick_filler_pools_are_independent():
    # The zh-CN pool and en-US pool share no members → truly per-language.
    assert set(FILLERS["zh-CN"]).isdisjoint(set(FILLERS["en-US"]))
    assert set(FILLERS["ja-JP"]).isdisjoint(set(FILLERS["en-US"]))


def test_pick_filler_unknown_language_falls_back_to_en_us():
    # An unknown lang (e.g. fr-FR) uses the en-US pool, not any other.
    for i in range(len(FILLERS[DEFAULT_LANG_FALLBACK])):
        got = pick_filler("fr-FR", rng=_SeqRng(choice_index=i))
        assert got == FILLERS["en-US"][i]
        assert got in FILLERS["en-US"]


def test_pick_filler_injected_rng_is_deterministic():
    # Same injected rng index → same string, repeatably.
    rng = _SeqRng(choice_index=2)
    assert pick_filler("zh-CN", rng=rng) == FILLERS["zh-CN"][2]
    assert pick_filler("zh-CN", rng=_SeqRng(choice_index=2)) == FILLERS["zh-CN"][2]


# ---- pick_filler phrases override (AC#1) ---------------------------------

def test_pick_filler_phrases_override_draws_from_phrases_not_global():
    # A non-empty phrases list fully REPLACES the language pool (language-
    # agnostic): the result is the injected index INTO phrases, never a global
    # FILLERS member.
    phrases = ["A", "B", "C"]
    for i in range(len(phrases)):
        got = pick_filler("zh-CN", rng=_SeqRng(choice_index=i), phrases=phrases)
        assert got == phrases[i]
        assert got in phrases
        assert got not in FILLERS["zh-CN"]
        assert got not in FILLERS["en-US"]


def test_pick_filler_phrases_none_is_global_pool():
    # phrases=None (default) → byte-identical to the global-pool behaviour.
    for i in range(len(FILLERS["zh-CN"])):
        got = pick_filler("zh-CN", rng=_SeqRng(choice_index=i), phrases=None)
        assert got == FILLERS["zh-CN"][i]
        assert got in FILLERS["zh-CN"]


def test_pick_filler_phrases_empty_list_is_global_pool():
    # phrases=[] is NOT an override → falls back to the global language pool.
    for i in range(len(FILLERS["en-US"])):
        got = pick_filler("en-US", rng=_SeqRng(choice_index=i), phrases=[])
        assert got == FILLERS["en-US"][i]
        assert got in FILLERS["en-US"]


# ==========================================================================
# Observer harness — mock task recording queue_frames, real asyncio timer
# ==========================================================================

class _RecordingTask:
    """Stand-in PipelineTask: records every queue_frames([...]) call."""

    def __init__(self):
        self.calls = []  # list of the frame-lists passed to queue_frames

    async def queue_frames(self, frames):
        self.calls.append(frames)


def _push(direction=FrameDirection.DOWNSTREAM):
    """Minimal FramePushed factory. on_push_frame reads only data.frame, but
    we build a real FramePushed (source/destination/timestamp filled with
    harmless stubs) so the test rides the genuine event-data type."""
    def make(frame):
        return FramePushed(
            source=None, destination=None, frame=frame,
            direction=direction, timestamp=0,
        )
    return make


_pushed = _push()  # downstream is the common case


def _make_observer(**kw):
    """Build an observer wired to a fresh recording task."""
    task = _RecordingTask()
    obs = TimeoutFillerObserver(task=task, **kw)
    return obs, task


def _fillers_in(task):
    """Flatten queue_frames calls to the TTSSpeakFrames they carried."""
    return [f for call in task.calls for f in call if isinstance(f, TTSSpeakFrame)]


# A timeout small enough to be fast, large enough not to fire spuriously
# before we feed the cancelling frame in the same event-loop tick.
TINY_MS = 30
MARGIN_S = 0.12  # comfortably past TINY_MS


# ---- CORE RACE TEST (AC#3): TTSStarted within threshold cancels ----------
# This is THE reason for the observer rewrite: an observer sees the downstream
# TTSStartedFrame (the real reply's TTS starting), so it cancels the filler
# before it can fire → the filler can no longer queue behind the real reply.

def test_ttsstarted_within_threshold_cancels_no_filler():
    async def run():
        obs, task = _make_observer(
            lang_key="en-US", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(0)  # let the timer coroutine actually start
        # Real reply's TTS starts within the timeout window → cancel.
        await obs.on_push_frame(_pushed(TTSStartedFrame()))
        await asyncio.sleep(MARGIN_S)
        assert task.calls == []           # queue_frames NEVER called
        assert _fillers_in(task) == []
        assert obs._pending is None       # timer cleaned up

    asyncio.run(run())


# ---- timer fires uncancelled (AC#3) --------------------------------------

def test_timer_fires_queues_ttsspeak_in_pool_after_timeout():
    async def run():
        obs, task = _make_observer(
            lang_key="zh-CN", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(choice_index=0, randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        # queue_frames called exactly once, with a single TTSSpeakFrame.
        assert len(task.calls) == 1
        assert len(task.calls[0]) == 1
        f = task.calls[0][0]
        assert isinstance(f, TTSSpeakFrame)
        assert f.text in FILLERS["zh-CN"]
        assert f.text == FILLERS["zh-CN"][0]  # injected choice index
        assert f.append_to_context is False
        assert obs._pending is None           # cleaned up after fire

    asyncio.run(run())


# ---- VADUserStopped also arms (AC#3) -------------------------------------

def test_vad_userstopped_also_arms():
    async def run():
        obs, task = _make_observer(
            lang_key="en-US", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(VADUserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        assert len(_fillers_in(task)) == 1

    asyncio.run(run())


# ---- barge-in cancels: UserStarted AND VADUserStarted (AC#3) -------------

@pytest.mark.parametrize("barge_in_cls", [
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    BotStartedSpeakingFrame,
])
def test_barge_in_or_botstarted_cancels_no_filler(barge_in_cls):
    async def run():
        obs, task = _make_observer(
            lang_key="en-US", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(0)  # let the timer coroutine actually start
        await obs.on_push_frame(_pushed(barge_in_cls()))
        await asyncio.sleep(MARGIN_S)
        assert _fillers_in(task) == []
        assert obs._pending is None

    asyncio.run(run())


# ---- re-arm cancels the previous pending timer (AC#3) --------------------

def test_rearm_cancels_previous_pending_only_one_fires():
    async def run():
        obs, task = _make_observer(
            lang_key="zh-CN", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(choice_index=0, randoms=[0.0, 0.0]),
        )
        # Two UserStopped in a row → second arm must cancel the first pending.
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(0)  # let the first timer coroutine actually start
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        # Only ONE filler despite two arms — the first timer was cancelled.
        assert len(_fillers_in(task)) == 1
        assert obs._pending is None

    asyncio.run(run())


# ---- probability boundaries (AC#3) ---------------------------------------

def test_probability_zero_never_queues():
    async def run():
        obs, task = _make_observer(
            lang_key="en-US", enabled=True, timeout_ms=TINY_MS,
            probability=0.0, rng=_SeqRng(randoms=[0.0]),  # 0.0 < 0.0 is False
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        assert task.calls == []
        assert obs._pending is None  # cleaned up even when prob gate blocks

    asyncio.run(run())


def test_probability_one_always_queues():
    async def run():
        obs, task = _make_observer(
            lang_key="en-US", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(randoms=[0.999]),  # 0.999 < 1.0 True
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        assert len(_fillers_in(task)) == 1

    asyncio.run(run())


# ---- lang fallback to en-US (AC#3) ---------------------------------------

def test_unknown_lang_fires_from_en_us_pool():
    async def run():
        obs, task = _make_observer(
            lang_key="fr-FR", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(choice_index=0, randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        fillers = _fillers_in(task)
        assert len(fillers) == 1
        assert fillers[0].text in FILLERS["en-US"]

    asyncio.run(run())


# ---- observer fires from per-demo phrases override (AC#2) ----------------

def test_observer_phrases_override_fires_demo_phrase_not_global():
    async def run():
        obs, task = _make_observer(
            lang_key="zh-CN", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, phrases=["稍等哦"],
            rng=_SeqRng(choice_index=0, randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        fillers = _fillers_in(task)
        assert len(fillers) == 1
        assert fillers[0].text == "稍等哦"          # from the demo phrases
        assert fillers[0].text not in FILLERS["zh-CN"]  # not the global pool

    asyncio.run(run())


def test_observer_phrases_none_fires_from_global_pool():
    # Regression: phrases=None → the global lang pool, same as before.
    async def run():
        obs, task = _make_observer(
            lang_key="zh-CN", enabled=True, timeout_ms=TINY_MS,
            probability=1.0, phrases=None,
            rng=_SeqRng(choice_index=0, randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(MARGIN_S)
        fillers = _fillers_in(task)
        assert len(fillers) == 1
        assert fillers[0].text in FILLERS["zh-CN"]

    asyncio.run(run())


# ---- enabled=False → pure no-op (AC#3) -----------------------------------

def test_disabled_is_noop_never_arms():
    async def run():
        obs, task = _make_observer(
            lang_key="zh-CN", enabled=False, timeout_ms=TINY_MS,
            probability=1.0, rng=_SeqRng(randoms=[0.0]),
        )
        for fr in (
            UserStoppedSpeakingFrame(),
            VADUserStoppedSpeakingFrame(),
            TTSStartedFrame(),
            UserStartedSpeakingFrame(),
            TextFrame("hi"),
        ):
            await obs.on_push_frame(_pushed(fr))
        await asyncio.sleep(MARGIN_S)
        assert task.calls == []
        assert obs._pending is None  # never armed

    asyncio.run(run())


# ---- timer cleanup: cancel never raises, _pending not leaked (reviewer) --

def test_cancel_armed_timer_does_not_raise_and_clears_pending():
    async def run():
        obs, task = _make_observer(
            lang_key="en-US", enabled=True, timeout_ms=1000,  # long; we cancel first
            probability=1.0, rng=_SeqRng(randoms=[0.0]),
        )
        await obs.on_push_frame(_pushed(UserStoppedSpeakingFrame()))
        await asyncio.sleep(0)
        assert obs._pending is not None and not obs._pending.done()
        # Cancelling (via a cancel-frame) must not raise and must clear _pending.
        await obs.on_push_frame(_pushed(UserStartedSpeakingFrame()))
        assert obs._pending is None
        await asyncio.sleep(0.02)
        assert task.calls == []  # never fired

    asyncio.run(run())


# ---- observer exception never escapes (zero pipeline impact) -------------

def test_on_push_frame_swallows_exceptions():
    async def run():
        obs, task = _make_observer(
            lang_key="en-US", enabled=True, timeout_ms=TINY_MS, probability=1.0,
        )
        # data with no .frame attribute → AttributeError inside the guard; must
        # be swallowed, not propagated.
        class _Bad:
            pass
        await obs.on_push_frame(_Bad())  # must not raise

    asyncio.run(run())


# ==========================================================================
# Config priority: per-field ctor value > env > built-in default
# (_build_pipeline passes demo.filler per-field; a None field falls back to
#  the observer's _env_* lookup — same precedence as the old processor.)
# ==========================================================================

# Sentinel values chosen to differ from both the env values and the built-in
# defaults (OFF / 1500 ms / 0.5) so a wrong source is unambiguous.
_PASSED_TIMEOUT_MS = 800
_PASSED_TIMEOUT_S = 0.8
_PASSED_PROB = 1.0


def test_ctor_values_override_env(monkeypatch):
    # All three passed explicitly → env is IGNORED entirely. Env is set to
    # CONFLICTING values to prove the passed values win.
    monkeypatch.setenv("FILLER_ENABLED", "false")
    monkeypatch.setenv("FILLER_TIMEOUT_MS", "5000")
    monkeypatch.setenv("FILLER_PROBABILITY", "0.1")
    obs = TimeoutFillerObserver(
        task=None,
        lang_key="en-US",
        enabled=True,
        timeout_ms=_PASSED_TIMEOUT_MS,
        probability=_PASSED_PROB,
    )
    assert obs._enabled is True
    assert obs._timeout == _PASSED_TIMEOUT_S
    assert obs._prob == _PASSED_PROB


def test_all_none_falls_back_to_env(monkeypatch):
    # All three None → every field reads from FILLER_* env.
    monkeypatch.setenv("FILLER_ENABLED", "true")
    monkeypatch.setenv("FILLER_TIMEOUT_MS", "2000")
    monkeypatch.setenv("FILLER_PROBABILITY", "0.25")
    obs = TimeoutFillerObserver(
        task=None,
        lang_key="en-US",
        enabled=None,
        timeout_ms=None,
        probability=None,
    )
    assert obs._enabled is True
    assert obs._timeout == 2.0  # 2000 ms env → 2.0 s
    assert obs._prob == 0.25


def test_default_off_when_unset(monkeypatch):
    # No FILLER_ENABLED env, no passed value → default OFF (ships dormant).
    monkeypatch.delenv("FILLER_ENABLED", raising=False)
    obs = TimeoutFillerObserver(task=None, lang_key="en-US")
    assert obs._enabled is False


def test_per_field_mix_passed_and_env(monkeypatch):
    # Only enabled passed (True); timeout_ms / probability None → those two
    # fall back to env, while enabled uses the passed value (NOT the env false).
    monkeypatch.setenv("FILLER_ENABLED", "false")  # must be ignored (passed True wins)
    monkeypatch.setenv("FILLER_TIMEOUT_MS", "3000")
    monkeypatch.setenv("FILLER_PROBABILITY", "0.7")
    obs = TimeoutFillerObserver(
        task=None,
        lang_key="en-US",
        enabled=True,
        timeout_ms=None,
        probability=None,
    )
    assert obs._enabled is True   # passed value, not env false
    assert obs._timeout == 3.0    # env fallback (3000 ms)
    assert obs._prob == 0.7       # env fallback


def test_task_settable_post_construction():
    # bot.py builds the observer with task=None then injects the task after the
    # PipelineTask is constructed (observers is constructor-only).
    obs = TimeoutFillerObserver(task=None, lang_key="en-US")
    assert obs.task is None
    sentinel = _RecordingTask()
    obs.task = sentinel
    assert obs.task is sentinel


# ---------------------------------------------------------------------------
# Filler PATCH validation (bcrypt-free) — directly exercises bot's
# _validate_filler_patch helper used by PATCH /api/admin/demos/{id} (T2).
# The full PATCH integration path lives in tests/test_admin_api.py, which is
# skipped without bcrypt; these cover the validation logic with no auth dep.
# ---------------------------------------------------------------------------
import pytest as _pytest
from fastapi import HTTPException as _HTTPException


def _validate():
    import bot
    return bot._validate_filler_patch


def test_validate_filler_valid_full_block():
    clean = _validate()({"enabled": True, "timeout_ms": 900, "probability": 0.3})
    assert clean == {"enabled": True, "timeout_ms": 900, "probability": 0.3}
    assert isinstance(clean["probability"], float)


def test_validate_filler_partial_returns_only_present_keys():
    # Only the present (valid) keys come back, so the caller's merge preserves
    # any existing sibling sub-fields.
    assert _validate()({"enabled": False}) == {"enabled": False}
    assert _validate()({"timeout_ms": 1500}) == {"timeout_ms": 1500}


def test_validate_filler_empty_block_is_noop():
    assert _validate()({}) == {}


def test_validate_filler_probability_boundaries_ok():
    assert _validate()({"probability": 0.0}) == {"probability": 0.0}
    assert _validate()({"probability": 1.0}) == {"probability": 1.0}


@_pytest.mark.parametrize(
    "bad",
    [
        {"enabled": "yes"},     # non-bool
        {"enabled": 1},         # int is not bool
        {"timeout_ms": 0},      # not > 0
        {"timeout_ms": -5},     # negative
        {"timeout_ms": True},   # bool excluded (int subclass)
        {"timeout_ms": 1.5},    # float not allowed for int field
        {"probability": 1.5},   # out of range
        {"probability": -0.1},  # out of range
        {"probability": True},  # bool excluded
        {"probability": "0.5"}, # non-numeric
    ],
)
def test_validate_filler_invalid_raises_400(bad):
    with _pytest.raises(_HTTPException) as ei:
        _validate()(bad)
    assert ei.value.status_code == 400


# ---- phrases validation (AC#3) -------------------------------------------

def test_validate_filler_phrases_valid():
    assert _validate()({"phrases": ["a", "b"]}) == {"phrases": ["a", "b"]}


def test_validate_filler_phrases_strips_and_drops_blanks():
    # Each item .strip()-ed; blank / whitespace-only items dropped.
    assert _validate()({"phrases": ["a", " ", "", "  b  "]}) == {"phrases": ["a", "b"]}


def test_validate_filler_phrases_empty_list_clears_override():
    assert _validate()({"phrases": []}) == {"phrases": []}


def test_validate_filler_phrases_all_blank_becomes_empty_clear():
    # A list of only blanks cleans down to [] → clears the override (allowed).
    assert _validate()({"phrases": [" ", "", "\t"]}) == {"phrases": []}


def test_validate_filler_phrases_only_body_returns_only_phrases_key():
    # Sibling-merge contract: a phrases-only body returns only the phrases key.
    assert _validate()({"phrases": ["x"]}) == {"phrases": ["x"]}


def test_validate_filler_combined_enabled_and_phrases_returns_both():
    assert _validate()({"enabled": True, "phrases": ["a"]}) == {
        "enabled": True,
        "phrases": ["a"],
    }


@_pytest.mark.parametrize(
    "bad",
    [
        {"phrases": "a"},                  # not a list
        {"phrases": {"a": 1}},             # dict, not a list
        {"phrases": ["a", 5]},             # non-str item
        {"phrases": ["a", None]},          # non-str item
        {"phrases": ["x"] * 21},           # >20 items
        {"phrases": ["a" * 41]},           # item >40 chars
    ],
)
def test_validate_filler_phrases_invalid_raises_400(bad):
    with _pytest.raises(_HTTPException) as ei:
        _validate()(bad)
    assert ei.value.status_code == 400


def test_validate_filler_phrases_40_char_item_ok_boundary():
    # Exactly 40 chars is allowed (cap is >40 rejects).
    item = "a" * 40
    assert _validate()({"phrases": [item]}) == {"phrases": [item]}


def test_validate_filler_phrases_20_items_ok_boundary():
    items = [f"p{i}" for i in range(20)]
    assert _validate()({"phrases": items}) == {"phrases": items}
