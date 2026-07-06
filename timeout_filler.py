"""Timeout filler for the three-stage pipeline — speak a short 语气词 when the
bot has been silent too long after the user stopped speaking.

Problem (see proposal tech_design §0): in the three-stage engine a turn runs
``STT → LLM → TTS`` end-to-end. If any of those is slow, the user hears dead
air after they finish talking. The filler arms a timer when the user stops
speaking; if the bot has not started speaking within the timeout, it
*probabilistically* injects one random filler ("嗯"/"um"/…) in the call's
language to cover the latency, then the real reply takes over.

**Why an Observer, not an in-pipeline FrameProcessor (tech_design §0-§1):**
the old ``TimeoutFillerProcessor`` sat UPSTREAM of ``tts`` (after ``user_agg``,
before ``llm``). The only "the real reply is coming" signal it could see was
``BotStartedSpeakingFrame``, which transport.output emits UPSTREAM only once the
bot's audio actually starts PLAYING — very late. The timely "real-reply TTS is
starting" signal ``TTSStartedFrame`` flows DOWNSTREAM (tts → output) and never
reached the upstream processor. Result: a race — TTS was already synthesising
the real reply, but BotStarted had not yet travelled back upstream, so the timer
fired and the filler ``TTSSpeakFrame`` queued *behind* the real reply → the
filler 语气词 played AFTER the real answer.

``BaseObserver.on_push_frame`` sees **every** frame in the pipeline regardless
of direction (base_observer.py: "view all frames that flow through the
pipeline"), so the observer DOES see the downstream ``TTSStartedFrame`` — the
earliest, most reliable "real reply is starting" signal — and cancels the timer
before it can fire. Race gone.

It is **orthogonal** to ``tool_filler.py`` (which fires before an MCP tool
call): a tool-call ack makes the bot start speaking, producing TTS/BotStarted
frames the observer's cancel path catches, so the two never double-speak.

Design (tech_design §1-§2, verified against real pipecat source):
  - ``UserStoppedSpeakingFrame`` OR ``VADUserStoppedSpeakingFrame`` (siblings —
    both subclass ``SystemFrame`` directly, ``issubclass`` between them is
    False, so BOTH must be matched) → arm an ``asyncio.sleep(timeout)`` timer.
    ``BaseObserver`` has no managed ``create_task``, so we use the asyncio
    primitive ``asyncio.create_task`` (``on_push_frame`` runs on the loop) and
    cancel/clear it ourselves.
  - ``TTSStartedFrame`` (key signal — earliest sign the real reply is starting),
    ``BotStartedSpeakingFrame``, ``UserStartedSpeakingFrame`` or
    ``VADUserStartedSpeakingFrame`` (barge-in / new turn) → cancel the timer.
  - On timeout (not cancelled): ``rng.random() < probability`` → inject one
    ``TTSSpeakFrame(filler, append_to_context=False)`` via
    ``task.queue_frames(...)`` (task.py: coroutine; bot.py already uses it).
  - All work is wrapped in try/except — an observer must NEVER break the
    pipeline (``CancelledError`` returns silently; anything else is logged at
    debug).

Verified against real pipecat source:
  - ``BaseObserver.on_push_frame(data: FramePushed)`` with ``data.frame`` /
    ``data.direction``                                          (base_observer.py)
  - ``PipelineTask.queue_frames(frames)`` is a coroutine        (task.py)
  - ``TTSSpeakFrame(text, append_to_context)``                  (frames.py)
  - ``UserStartedSpeakingFrame`` / ``UserStoppedSpeakingFrame`` /
    ``VADUserStartedSpeakingFrame`` / ``VADUserStoppedSpeakingFrame`` /
    ``TTSStartedFrame`` / ``BotStartedSpeakingFrame``  from ``pipecat.frames.frames``.

Env-gated like ``asr_filter.py``: ``FILLER_ENABLED`` (default **false** —
ships dormant, zero behaviour change until explicitly turned on),
``FILLER_TIMEOUT_MS`` (default 1500), ``FILLER_PROBABILITY`` (default 0.5).
"""

import asyncio
import os
import random

from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    TTSSpeakFrame,
    TTSStartedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    VADUserStartedSpeakingFrame,
    VADUserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


# Per-language filler pools. Each language is INDEPENDENT — ``pick_filler``
# draws only from the requested language's pool, falling back to the en-US pool
# when ``lang_key`` is absent entirely (tech_design §3 table).
FILLERS: dict[str, list[str]] = {
    "zh-CN": ["嗯", "啊", "好的", "嗯…稍等", "让我看一下"],
    "zh-HK": ["嗯", "好嘅", "等我睇一睇", "稍等"],
    "en-US": ["um", "uh-huh", "let me see", "one sec"],
    "ja-JP": ["えっと", "はい", "少々お待ちください"],
}

# Language used when ``lang_key`` is absent from FILLERS entirely.
DEFAULT_LANG_FALLBACK = "en-US"


def pick_filler(lang_key: str, rng=random, phrases=None) -> str:
    """Pick one random filler.

    If ``phrases`` is a non-empty list, draw from it — a per-demo override that
    is language-agnostic and FULLY REPLACES the language pool (tech_design §3).
    Otherwise fall back to the global per-language ``FILLERS`` pool (``lang_key``
    → en-US fallback), exactly as before.

    ``phrases=None`` (default) and ``phrases=[]`` are both byte-identical to the
    pre-override behaviour — an empty list is NOT an override, it means "use the
    global pool". ``phrases`` is a value param (injection): no module-global
    mutable state, so concurrent calls with different demos stay isolated.

    ``rng`` is injectable so the choice is deterministic in tests
    (``rng.choice``). Returns ``""`` only if every candidate pool is empty.
    """
    pool = None
    if phrases:  # non-empty list → per-demo override (full replace)
        pool = phrases
    if not pool:
        pool = FILLERS.get(lang_key) or FILLERS.get(DEFAULT_LANG_FALLBACK) or []
    return rng.choice(pool) if pool else ""


# Frames that ARM the timer (user just stopped talking — real reply now owed).
# UserStoppedSpeakingFrame and VADUserStoppedSpeakingFrame are SIBLINGS (both
# subclass SystemFrame directly; issubclass between them is False) so BOTH must
# be listed — matching only one would miss VAD-driven turn ends.
_ARM_FRAMES = (UserStoppedSpeakingFrame, VADUserStoppedSpeakingFrame)

# Frames that CANCEL the timer. TTSStartedFrame is the KEY one: an observer sees
# downstream frames, so the real reply's TTS start cancels the filler before it
# fires — this is what eliminates the race the in-pipeline processor had.
# BotStarted is a later fallback; UserStarted / VADUserStarted are barge-ins.
_CANCEL_FRAMES = (
    TTSStartedFrame,
    BotStartedSpeakingFrame,
    UserStartedSpeakingFrame,
    VADUserStartedSpeakingFrame,
)


class TimeoutFillerObserver(BaseObserver):
    """Probabilistic timeout filler as a pipeline observer.

    Watches the whole frame stream (both directions). Arms a timer when the user
    stops speaking; cancels it the moment the real reply's TTS starts
    (``TTSStartedFrame`` — visible to an observer but not to an upstream
    processor) or on a barge-in. On timeout it may inject one ``TTSSpeakFrame``
    filler via ``task.queue_frames``. Because the cancel happens at the earliest
    possible "real reply incoming" signal, the filler can no longer queue behind
    the real reply (the old race).

    ``task`` may be ``None`` at construction time and set afterwards
    (``observer.task = task``): ``PipelineTask`` takes its ``observers`` list at
    construction, so the observer must exist before the task does. ``_fire``
    re-reads ``self._task`` so the late assignment is picked up.
    """

    def __init__(
        self,
        *,
        task,
        lang_key: str,
        enabled: bool | None = None,
        timeout_ms: int | None = None,
        probability: float | None = None,
        phrases=None,
        rng=None,
    ):
        super().__init__()
        self._task = task
        self._lang = lang_key
        # Per-demo override pool (tech_design §3.2). None / [] → global FILLERS
        # pool; a non-empty list fully replaces it. No env fallback — phrases is
        # a purely per-demo manifest value (global phrase config is a non-goal).
        self._phrases = phrases
        self._enabled = (
            enabled if enabled is not None
            else _env_bool("FILLER_ENABLED", False)  # default OFF — ships dormant
        )
        self._timeout = (
            (timeout_ms if timeout_ms is not None
             else _env_int("FILLER_TIMEOUT_MS", 1500)) / 1000.0
        )
        self._prob = (
            probability if probability is not None
            else _env_float("FILLER_PROBABILITY", 0.5)
        )
        self._rng = rng or random
        self._pending: asyncio.Task | None = None

    @property
    def task(self):
        return self._task

    @task.setter
    def task(self, value):
        # Settable post-construction so bot.py can build the observer (for the
        # PipelineTask(observers=[...]) list) and inject the task reference after
        # the task itself is constructed.
        self._task = value

    async def on_push_frame(self, data: FramePushed):
        # An observer must NEVER raise into the pipeline — guard everything.
        try:
            if not self._enabled:
                return
            frame = data.frame
            if isinstance(frame, _ARM_FRAMES):
                self._arm()
            elif isinstance(frame, _CANCEL_FRAMES):
                self._cancel()
        except Exception as e:  # noqa: BLE001 — instrumentation must not crash a call
            logger.debug(f"timeout filler on_push_frame swallowed: {e}")

    def _arm(self) -> None:
        # At most one pending timer per turn — cancel any prior one first.
        self._cancel()
        self._pending = asyncio.create_task(self._fire())

    def _cancel(self) -> None:
        if self._pending is not None and not self._pending.done():
            self._pending.cancel()
        self._pending = None

    async def _fire(self) -> None:
        me = asyncio.current_task()
        try:
            await asyncio.sleep(self._timeout)
            if self._rng.random() < self._prob and self._task is not None:
                text = pick_filler(self._lang, self._rng, self._phrases)
                if text:
                    await self._task.queue_frames(
                        [TTSSpeakFrame(text=text, append_to_context=False)]
                    )
        except asyncio.CancelledError:
            # Cancelled before timeout (TTS started / barge-in) — say nothing.
            return
        except Exception as e:  # noqa: BLE001 — a filler is a nicety, never crash
            logger.debug(f"timeout filler fire failed: {e}")
        finally:
            # Clear the one-shot timer so it can't leak / self-trigger again —
            # but only if a re-arm hasn't already replaced _pending with a newer
            # task (don't stomp the live timer with this finished one's cleanup).
            if self._pending is me:
                self._pending = None
