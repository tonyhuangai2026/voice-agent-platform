"""ASR hallucination filter for the STT→aggregator seam.

AWS Transcribe streaming hallucinates short Japanese filler words (うん/はい/
は/そう …) on near-silent / noise audio that VAD mis-triggers on. Those land
as final TranscriptionFrames and get fed to the LLM as if the user spoke,
derailing the conversation. This processor sits between the STT service and the
user-context aggregator and drops those hallucinations — conservatively, so
real short answers (はい/いいえ/digits) are never eaten.

Design (see proposal b4ac7049 tech design §2.1):
  1. Only final ``TranscriptionFrame`` is judged; ``InterimTranscriptionFrame``
     and every other frame pass through untouched (interim is used for live
     display / barge-in and must not be disturbed).
  2. Decision order for a final transcript ``text`` with raw STT ``result``:
       a. contains a digit  → KEEP (社員番号 / OTP / phone — never drop).
       b. not "short"       → KEEP (long utterances are real).
       c. confidence known  → DROP iff (conf < MIN_CONFIDENCE AND short).
       d. confidence None   → DROP iff (text in FILLER_DENYLIST AND short).
  3. Every DROP is logged at WARNING so nothing is silently swallowed and the
     real confidence distribution can be observed in prod (T1 left the live
     value unobserved; T3 reads it from these logs to tune MIN_CONFIDENCE).

``はい`` / ``いいえ`` are intentionally NOT in the denylist; combined with the
"low-confidence AND short" double-gate, valid confirmations survive.
"""

import os
import re

from loguru import logger

from pipecat.frames.frames import Frame, TranscriptionFrame
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return v.strip().lower() in ("1", "true", "yes", "on")


# Short interjections/fillers AWS Transcribe ja-JP tends to hallucinate on
# noise/silence. Deliberately EXCLUDES はい / いいえ (valid confirmations).
DEFAULT_FILLER_DENYLIST = frozenset(
    {
        "うん", "うーん", "ううん", "ん", "んー",
        "は", "はぁ", "はあ",
        "あ", "ああ", "あっ", "あの", "あのー",
        "え", "えっ", "えー", "えーと", "ええと",
        "そう", "そうそう",
        "お", "おお", "へえ", "ふん", "まあ", "なるほど",
    }
)

# Any digit (ASCII or full-width) marks a transcript as data-bearing → never drop.
_DIGIT_RE = re.compile(r"[0-9０-９]")
# CJK char class for length measurement (Han / Hiragana / Katakana).
_CJK_RE = re.compile(r"[぀-ヿ㐀-䶿一-鿿ｦ-ﾟ]")


def _has_digit(text: str) -> bool:
    return bool(_DIGIT_RE.search(text))


def _is_short(text: str, max_cjk_chars: int, max_latin_words: int) -> bool:
    """Short = few CJK chars OR few latin words (whichever applies)."""
    cjk = _CJK_RE.findall(text)
    if cjk:
        # Count CJK characters (drop spaces/punct already excluded by the class).
        return len(cjk) <= max_cjk_chars
    # No CJK: treat as latin/space-delimited.
    return len(text.split()) <= max_latin_words


def _extract_confidence(result) -> float | None:
    """Mean per-item Confidence from an AWS Transcribe streaming final result.

    Returns None when confidence is unavailable (result shape missing, no Items,
    or no numeric Confidence present) — caller then uses the rule path.
    """
    if not isinstance(result, dict):
        return None
    alts = result.get("Alternatives") or []
    if not alts:
        return None
    items = (alts[0] or {}).get("Items") or []
    confs = []
    for it in items:
        if not isinstance(it, dict):
            continue
        c = it.get("Confidence")
        if c is None:
            continue
        try:
            confs.append(float(c))
        except (TypeError, ValueError):
            continue
    if not confs:
        return None
    return sum(confs) / len(confs)


class TranscriptHallucinationFilter(FrameProcessor):
    """Drops short, low-confidence ASR hallucinations before the aggregator."""

    def __init__(
        self,
        *,
        min_confidence: float | None = None,
        max_cjk_chars: int | None = None,
        max_latin_words: int | None = None,
        enabled: bool | None = None,
        filler_denylist=DEFAULT_FILLER_DENYLIST,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self._min_confidence = (
            min_confidence if min_confidence is not None
            else _env_float("ASR_FILTER_MIN_CONFIDENCE", 0.5)
        )
        self._max_cjk_chars = (
            max_cjk_chars if max_cjk_chars is not None
            else _env_int("ASR_FILTER_MAX_CHARS", 4)
        )
        self._max_latin_words = (
            max_latin_words if max_latin_words is not None
            else _env_int("ASR_FILTER_MAX_WORDS", 1)
        )
        self._enabled = (
            enabled if enabled is not None
            else _env_bool("ASR_FILTER_ENABLED", False)
        )
        self._denylist = filler_denylist

    def _should_drop(self, text: str, result) -> tuple[bool, str]:
        """Return (drop?, reason) for a final transcript."""
        if _has_digit(text):
            return False, "has-digit"
        short = _is_short(text, self._max_cjk_chars, self._max_latin_words)
        if not short:
            return False, "long"
        conf = _extract_confidence(result)
        if conf is not None:
            if conf < self._min_confidence:
                return True, f"low-conf({conf:.2f}<{self._min_confidence})+short"
            return False, f"conf-ok({conf:.2f})"
        # Confidence unavailable → rule path.
        if text in self._denylist:
            return True, "filler-denylist+short(conf=None)"
        return False, "short-but-not-filler(conf=None)"

    async def process_frame(self, frame: Frame, direction: FrameDirection):
        # Base class handles Start/Interruption/etc.; do NOT skip it.
        await super().process_frame(frame, direction)

        # Only judge FINAL transcripts moving downstream. Everything else
        # (interim, audio, control frames, upstream) passes through.
        if (
            self._enabled
            and direction == FrameDirection.DOWNSTREAM
            and isinstance(frame, TranscriptionFrame)
        ):
            text = (frame.text or "").strip()
            if text:
                drop, reason = self._should_drop(text, getattr(frame, "result", None))
                if drop:
                    logger.warning(
                        f"[asr-filter] dropped hallucination: {text!r} reason={reason}"
                    )
                    return  # swallow: do not push downstream

        await self.push_frame(frame, direction)
