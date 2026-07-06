"""Structured JSONL latency log — one line per measured turn.

A deliberately tiny, dependency-free append-only writer for latency records
produced by :class:`latency_observer.LatencyObserver`. Kept independent of the
loguru sink config so it never tangles with the app's logger routing.

Behaviour (tech design §2):
  * Destination is the env var ``LATENCY_LOG_PATH`` (default
    ``/var/log/voicebot-latency.jsonl``).
  * An **empty string** (``LATENCY_LOG_PATH=""``) disables disk writes
    entirely — :func:`write` becomes a no-op. This keeps tests and locked-down
    environments side-effect free while still letting the observer emit live
    events.
  * Each record is serialized with ``json.dumps(record, ensure_ascii=False)``
    plus a trailing newline and appended. One record == one line, so the file
    is trivially ``grep``/``jq``/aggregator friendly.
  * IO failures degrade gracefully: a single ``logger.warning`` is emitted (so
    a broken path is visible once, not on every turn) and the exception is
    swallowed. :func:`write` never raises — a logging failure must never break
    a live call.

The path is resolved **per call** to :func:`write` (reading the env each time)
so tests can monkeypatch ``LATENCY_LOG_PATH`` between writes without re-import.
"""

from __future__ import annotations

import json
import os

from loguru import logger

DEFAULT_LATENCY_LOG_PATH = "/var/log/voicebot-latency.jsonl"

# One-shot guard so a persistently broken path warns once, not per turn.
_warned_once = False


def _resolve_path() -> str | None:
    """Return the configured log path, or ``None`` when writing is disabled.

    An env value that is present but empty (``""``) means "do not write to
    disk". An absent env var falls back to the prod default.
    """
    raw = os.environ.get("LATENCY_LOG_PATH")
    if raw is None:
        return DEFAULT_LATENCY_LOG_PATH
    raw = raw.strip()
    if raw == "":
        return None
    return raw


def write(record: dict) -> None:
    """Append one JSON record as a single line. Never raises.

    No-op when ``LATENCY_LOG_PATH`` is the empty string. On any IO/serialization
    error, warns at most once and swallows the exception.
    """
    global _warned_once
    path = _resolve_path()
    if path is None:
        return
    try:
        line = json.dumps(record, ensure_ascii=False)
        # Auto-create the parent dir so a fresh box / non-existent log dir
        # doesn't silently drop records. Inside the try so a makedirs failure
        # (e.g. unwritable parent) still degrades to the one-shot warning below
        # rather than raising into a live call.
        dirname = os.path.dirname(path)
        if dirname:
            os.makedirs(dirname, exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except Exception as e:  # noqa: BLE001 — logging must never break a call
        if not _warned_once:
            _warned_once = True
            logger.warning(
                f"[latency-log] failed to write to {path!r}: {e} "
                f"(further failures suppressed)"
            )


def _reset_warning_guard() -> None:
    """Test hook: clear the one-shot warning guard between cases."""
    global _warned_once
    _warned_once = False
