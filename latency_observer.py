"""Pure-observation latency measurement (tech design §1).

``LatencyObserver`` rides alongside the existing ``EventBroadcaster`` on the
same ``PipelineTask(observers=[...])``. It watches the frame stream, groups
frames into **turns**, and on each turn close computes per-stage and
end-to-end latencies, writes a structured JSONL record, and emits a live
``latency_report`` event on the same fan-out channel the monitor already uses.

Design invariants:
  * **Zero pipeline impact.** Every code path in ``on_push_frame`` is wrapped
    in try/except; an observer exception must NEVER propagate into the pipeline
    (an instrumentation bug must not be able to drop a live call). Failures are
    logged at debug.
  * **Turn boundary.** ``UserStartedSpeakingFrame`` opens a turn; the next
    ``BotStartedSpeakingFrame`` closes it (turn_id increments on open). A turn
    that never closes (e.g. the user barged in / no bot audio) is discarded
    when the next ``UserStartedSpeakingFrame`` arrives — no partial record is
    written.
  * **First-occurrence wins.** Frames are deduped by ``frame.id`` (Pipecat's
    monotonic ``obj_id``), and each stage timestamp records only the first
    matching frame within a turn.
  * **Monotonic clock.** All timestamps come from a single injectable clock
    (``time.monotonic`` by default) so tests drive a fake clock — no sleeps,
    no flakiness.

nova-sonic (end-to-end engine) emits no STT/LLM/TTS frames, so those stage
timestamps stay ``None`` and their derived latencies are ``null`` — only
``e2e_ms`` is populated. This is graceful degradation, not an error.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    LLMFullResponseEndFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    TranscriptionFrame,
    TTSAudioRawFrame,
    TTSStartedFrame,
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
)
from pipecat.observers.base_observer import BaseObserver, FramePushed

import latency_log

# MetricsFrame + its data classes are optional / version-sensitive. Import
# defensively: if the pipecat version doesn't ship them (or renames them) we
# simply skip the service-level enrichment rather than crash the observer.
try:  # pragma: no cover - exercised implicitly; both branches are simple
    from pipecat.frames.frames import MetricsFrame
    from pipecat.metrics.metrics import (
        LLMUsageMetricsData,
        TTFBMetricsData,
        TTSUsageMetricsData,
    )

    _METRICS_AVAILABLE = True
except Exception as e:  # noqa: BLE001
    MetricsFrame = ()  # isinstance(x, ()) is always False → branch disabled
    LLMUsageMetricsData = TTFBMetricsData = TTSUsageMetricsData = None
    _METRICS_AVAILABLE = False
    logger.debug(f"[latency] MetricsFrame import unavailable, svc metrics off: {e}")


def _ms(later: float | None, earlier: float | None) -> int | None:
    """Milliseconds between two monotonic timestamps, None-safe.

    Returns ``None`` if either end is missing (so a stage that never occurred —
    e.g. on nova-sonic — degrades to ``null`` instead of a bogus number).
    """
    if later is None or earlier is None:
        return None
    return round((later - earlier) * 1000)


class LatencyObserver(BaseObserver):
    """Observes frames, aggregates per-turn latency, logs + emits per turn."""

    def __init__(
        self,
        emit,
        *,
        call_id: str | None = None,
        engine: str | None = None,
        scenario: str | None = None,
        lang: str | None = None,
        start_time: float | None = None,
        clock=time.monotonic,
        log_writer=latency_log,
    ):
        """Args:
        emit: async callable taking a JSON-serializable dict (the same fan-out
            channel ``EventBroadcaster`` uses; failures are swallowed).
        call_id / engine / scenario / lang: static context stamped onto every
            record (the builders already know these).
        start_time: accepted for parity with ``EventBroadcaster``; unused for
            latency math (we use absolute monotonic deltas), kept so the two
            observers can be constructed identically.
        clock: zero-arg monotonic time source; injectable for tests.
        log_writer: object exposing ``write(record)``; defaults to the
            ``latency_log`` module. Injectable for tests.
        """
        super().__init__()
        self._emit = emit
        self._call_id = call_id
        self._engine = engine
        self._scenario = scenario
        self._lang = lang
        self._start = start_time
        self._clock = clock
        self._log = log_writer

        self._seen: set[int] = set()
        self._turn_id = 0
        self._turn_open = False
        self._reset_turn()

    # ------------------------------------------------------------------ turn

    def _reset_turn(self) -> None:
        """Clear all per-turn state (timestamps + service metrics)."""
        self._ts: dict[str, float | None] = {
            "user_start": None,
            "user_stop": None,
            "asr_final": None,
            "llm_start": None,
            "llm_first": None,
            "llm_end": None,
            "tts_start": None,
            "tts_first_audio": None,
            "bot_start": None,
        }
        self._svc: dict = {
            "svc_llm_ttfb_ms": None,
            "svc_tts_ttfb_ms": None,
            "tokens": None,
            "tts_chars": None,
        }

    def _mark(self, key: str, now: float) -> None:
        """Record the first-occurrence timestamp for ``key`` only."""
        if self._ts.get(key) is None:
            self._ts[key] = now

    # ----------------------------------------------------------- frame entry

    async def on_push_frame(self, data: FramePushed):
        """Observe one frame. All logic is guarded; never raises into the
        pipeline."""
        try:
            frame = data.frame

            # MetricsFrame is a SystemFrame, not in any _WATCHED-style gate, and
            # carries no per-turn boundary meaning. Consume it (deduped) and
            # return — it does not open/close turns.
            if _METRICS_AVAILABLE and isinstance(frame, MetricsFrame):
                if self._dedupe(frame):
                    self._consume_metrics(frame)
                return

            # TTSAudioRawFrame is NOT a monitor-broadcast frame (mirrors the
            # bot.py playout block); capture its first occurrence explicitly.
            if isinstance(frame, TTSAudioRawFrame):
                if self._turn_open and self._dedupe(frame):
                    self._mark("tts_first_audio", self._clock())
                return

            if not isinstance(frame, _BOUNDARY_FRAMES):
                return
            if not self._dedupe(frame):
                return

            now = self._clock()

            if isinstance(frame, UserStartedSpeakingFrame):
                self._on_user_started(now)
            elif isinstance(frame, BotStartedSpeakingFrame):
                await self._on_bot_started(now)
            elif self._turn_open:
                # Mid-turn stage frames only count inside an open turn.
                if isinstance(frame, UserStoppedSpeakingFrame):
                    self._mark("user_stop", now)
                elif isinstance(frame, TranscriptionFrame):
                    self._mark("asr_final", now)
                elif isinstance(frame, LLMFullResponseStartFrame):
                    self._mark("llm_start", now)
                elif isinstance(frame, LLMTextFrame):
                    self._mark("llm_first", now)
                elif isinstance(frame, LLMFullResponseEndFrame):
                    self._mark("llm_end", now)
                elif isinstance(frame, TTSStartedFrame):
                    self._mark("tts_start", now)
        except Exception as e:  # noqa: BLE001 — observer must never break pipeline
            logger.debug(f"[latency] on_push_frame swallowed: {e}")

    def _dedupe(self, frame) -> bool:
        """Return True the first time this frame.id is seen, else False."""
        fid = frame.id
        if fid in self._seen:
            return False
        self._seen.add(fid)
        return True

    # ------------------------------------------------------------ boundaries

    def _on_user_started(self, now: float) -> None:
        if self._turn_open:
            # Previous turn never closed (no bot audio / barge-in) → discard the
            # half-turn rather than emit an incomplete record.
            logger.debug(
                f"[latency] discarding unclosed turn {self._turn_id} "
                f"(new user-start before bot-start)"
            )
        self._turn_id += 1
        self._turn_open = True
        self._reset_turn()
        self._ts["user_start"] = now

    async def _on_bot_started(self, now: float) -> None:
        if not self._turn_open:
            # Bot audio with no open turn (e.g. opening greeting) → no turn to
            # close; ignore.
            return
        self._mark("bot_start", now)
        record = self._build_record()
        self._turn_open = False
        # Both outputs are independent; either failing must not affect the
        # other or the pipeline (each guarded internally).
        self._write_log(record)
        await self._emit_report(record)

    # --------------------------------------------------------------- outputs

    def _build_record(self) -> dict:
        ts = self._ts
        record = {
            "ts": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3]
            + "Z",
            "call_id": self._call_id,
            "turn_id": self._turn_id,
            "engine": self._engine,
            "scenario": self._scenario,
            "lang": self._lang,
            "e2e_ms": _ms(ts["bot_start"], ts["user_stop"]),
            "stt_ms": _ms(ts["asr_final"], ts["user_stop"]),
            "llm_ttft_ms": _ms(ts["llm_first"], ts["asr_final"]),
            "llm_total_ms": _ms(ts["llm_end"], ts["llm_start"]),
            "tts_ttfb_ms": _ms(ts["tts_first_audio"], ts["tts_start"]),
            "svc_llm_ttfb_ms": self._svc["svc_llm_ttfb_ms"],
            "svc_tts_ttfb_ms": self._svc["svc_tts_ttfb_ms"],
            "tokens": self._svc["tokens"],
            "tts_chars": self._svc["tts_chars"],
        }
        return record

    def _write_log(self, record: dict) -> None:
        try:
            self._log.write(record)
        except Exception as e:  # noqa: BLE001 — write() shouldn't raise, belt+braces
            logger.debug(f"[latency] log write swallowed: {e}")

    async def _emit_report(self, record: dict) -> None:
        if self._emit is None:
            return
        try:
            await self._emit({"type": "latency_report", **record})
        except Exception as e:  # noqa: BLE001 — same contract as EventBroadcaster
            logger.debug(f"[latency] emit swallowed: {e}")

    # --------------------------------------------------------------- metrics

    def _consume_metrics(self, frame) -> None:
        """Fold a MetricsFrame's data into the current turn's svc_* fields.

        Defensive: each item is parsed in isolation so one malformed/renamed
        field can't lose the rest. TTFB is bucketed to LLM vs TTS by a
        case-insensitive substring of the processor name (heuristic).
        """
        data = getattr(frame, "data", None) or []
        for item in data:
            try:
                if TTFBMetricsData is not None and isinstance(item, TTFBMetricsData):
                    name = (getattr(item, "processor", "") or "").upper()
                    val_ms = round(float(item.value) * 1000)
                    if "LLM" in name:
                        if self._svc["svc_llm_ttfb_ms"] is None:
                            self._svc["svc_llm_ttfb_ms"] = val_ms
                    elif "TTS" in name:
                        if self._svc["svc_tts_ttfb_ms"] is None:
                            self._svc["svc_tts_ttfb_ms"] = val_ms
                elif (
                    LLMUsageMetricsData is not None
                    and isinstance(item, LLMUsageMetricsData)
                ):
                    usage = item.value
                    self._svc["tokens"] = {
                        "prompt": getattr(usage, "prompt_tokens", None),
                        "completion": getattr(usage, "completion_tokens", None),
                        "total": getattr(usage, "total_tokens", None),
                    }
                elif (
                    TTSUsageMetricsData is not None
                    and isinstance(item, TTSUsageMetricsData)
                ):
                    self._svc["tts_chars"] = int(item.value)
            except Exception as e:  # noqa: BLE001 — one bad item must not lose others
                logger.debug(f"[latency] metric item skipped: {e}")


# Frames that participate in turn boundary / stage timing (TTSAudioRawFrame and
# MetricsFrame are handled before this gate). Defined at module scope so the
# isinstance tuple is built once.
_BOUNDARY_FRAMES = (
    UserStartedSpeakingFrame,
    UserStoppedSpeakingFrame,
    TranscriptionFrame,
    LLMFullResponseStartFrame,
    LLMTextFrame,
    LLMFullResponseEndFrame,
    TTSStartedFrame,
    BotStartedSpeakingFrame,
)
