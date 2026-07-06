#!/usr/bin/env python3
"""Offline latency aggregation CLI (tech design §5).

Reads one or more JSONL files produced by ``latency_log`` /
``LatencyObserver`` (one record per turn) and reports per-stage summary
statistics — count / avg / p50 / p95 / p99 / min / max — for each latency
stage, optionally grouped by ``engine`` or ``scenario``.

The record schema (see ``latency_observer._build_record``) is, per turn::

    {
      "ts": "...Z", "call_id": "web-...", "turn_id": 3,
      "engine": "pipeline", "scenario": "it-helpdesk", "lang": "zh-HK",
      "e2e_ms": 1840, "stt_ms": 420, "llm_ttft_ms": 560,
      "llm_total_ms": 980, "tts_ttfb_ms": 310,
      "svc_llm_ttfb_ms": 540, "svc_tts_ttfb_ms": 300,
      "tokens": {...}, "tts_chars": 86
    }

Any stage value may be ``null`` (e.g. nova-sonic only populates ``e2e_ms``);
nulls are skipped per stage so they don't pollute that stage's percentiles.

Design: the statistical core (:func:`percentile`, :func:`aggregate`) is pure
and dependency-free (**stdlib only** — no numpy/pandas) so it is directly
unit-testable; the CLI (:func:`main`) is a thin argparse shell over it.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Iterable

# The latency stages reported, in display order. These names match the actual
# record fields written by latency_observer._build_record (verified against
# latency_observer.py — do not rename without matching that schema).
STAGES = ("e2e_ms", "stt_ms", "llm_ttft_ms", "llm_total_ms", "tts_ttfb_ms")

# Fields a record may be grouped by.
GROUP_FIELDS = ("engine", "scenario")

# The per-stage statistics computed, in display order.
STAT_KEYS = ("count", "avg", "p50", "p95", "p99", "min", "max")


# --------------------------------------------------------------------- pure core


def percentile(values: list[float], p: float) -> float:
    """Return the ``p``-th percentile (0..100) of ``values``.

    Pure stdlib: sorts a copy and linearly interpolates between the two
    nearest ranks (the same "linear interpolation between closest ranks"
    method numpy uses by default), so it matches common tooling without any
    third-party dependency.

    Args:
        values: non-empty sequence of numbers.
        p: percentile in the inclusive range [0, 100].

    Raises:
        ValueError: if ``values`` is empty or ``p`` is out of range.
    """
    if not values:
        raise ValueError("percentile() of empty sequence")
    if not 0 <= p <= 100:
        raise ValueError(f"percentile p must be in [0, 100], got {p}")

    ordered = sorted(values)
    n = len(ordered)
    if n == 1:
        return float(ordered[0])

    # Rank position on a 0-based index scale: p=0 -> 0, p=100 -> n-1.
    rank = (p / 100.0) * (n - 1)
    lo = int(rank)  # floor
    hi = min(lo + 1, n - 1)
    frac = rank - lo
    return float(ordered[lo] + (ordered[hi] - ordered[lo]) * frac)


def _stage_stats(values: list[float]) -> dict | None:
    """Summary stats for one stage's collected (non-null) values.

    Returns ``None`` when there are no values, so a stage with zero samples is
    omitted from the report rather than shown as empty.
    """
    if not values:
        return None
    return {
        "count": len(values),
        "avg": round(sum(values) / len(values), 1),
        "p50": round(percentile(values, 50), 1),
        "p95": round(percentile(values, 95), 1),
        "p99": round(percentile(values, 99), 1),
        "min": round(float(min(values)), 1),
        "max": round(float(max(values)), 1),
    }


def aggregate(records: Iterable[dict], group_by: str | None = None) -> dict:
    """Aggregate per-stage statistics over ``records``.

    For each stage in :data:`STAGES`, collects every non-null numeric value
    and computes :func:`_stage_stats`. ``None`` values (and missing keys) are
    skipped so they never enter a percentile computation.

    Args:
        records: iterable of decoded JSONL records (dicts).
        group_by: ``None`` for a single overall group, or one of
            :data:`GROUP_FIELDS` (``"engine"`` / ``"scenario"``) to bucket
            records by that field's value before aggregating. A record whose
            group field is missing/None is bucketed under the literal
            ``"unknown"``.

    Returns:
        A mapping ``group_label -> {stage -> stats|None}``. When ``group_by``
        is ``None`` the single label is ``"all"``. Stages with no samples in a
        group map to ``None``.
    """
    if group_by is not None and group_by not in GROUP_FIELDS:
        raise ValueError(
            f"group_by must be one of {GROUP_FIELDS} or None, got {group_by!r}"
        )

    # group_label -> stage -> list[float]
    buckets: dict[str, dict[str, list[float]]] = {}

    for rec in records:
        if group_by is None:
            label = "all"
        else:
            raw = rec.get(group_by)
            label = str(raw) if raw not in (None, "") else "unknown"

        stage_values = buckets.setdefault(label, {s: [] for s in STAGES})
        for stage in STAGES:
            val = rec.get(stage)
            if val is None:
                continue
            if isinstance(val, bool):  # guard: bool is an int subclass
                continue
            if isinstance(val, (int, float)):
                stage_values[stage].append(float(val))

    result: dict[str, dict[str, dict | None]] = {}
    for label, stage_values in buckets.items():
        result[label] = {s: _stage_stats(stage_values[s]) for s in STAGES}
    return result


# ------------------------------------------------------------------ IO / parsing


def parse_jsonl(lines: Iterable[str]) -> list[dict]:
    """Decode JSONL lines into record dicts.

    Blank lines are skipped. Lines that aren't valid JSON objects are skipped
    with a warning to stderr (so one corrupt line doesn't abort a whole run).
    """
    records: list[dict] = []
    for i, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            print(f"warning: skipping malformed JSON on line {i}: {e}", file=sys.stderr)
            continue
        if isinstance(obj, dict):
            records.append(obj)
        else:
            print(
                f"warning: skipping non-object JSON on line {i}", file=sys.stderr
            )
    return records


def load_records(paths: list[str]) -> list[dict]:
    """Read and parse every path, concatenating all records."""
    records: list[dict] = []
    for path in paths:
        with open(path, "r", encoding="utf-8") as fh:
            records.extend(parse_jsonl(fh))
    return records


# ------------------------------------------------------------------- formatting


def _format_num(v) -> str:
    """Render a stat value: ints without a trailing .0, floats to 1 dp."""
    if isinstance(v, float) and v.is_integer():
        return str(int(v))
    return str(v)


def format_table(agg: dict, group_by: str | None) -> str:
    """Render the aggregation as a human-readable text table."""
    lines: list[str] = []
    col_w = 12
    header = "stage".ljust(14) + "".join(k.rjust(col_w) for k in STAT_KEYS)

    for label in sorted(agg):
        stages = agg[label]
        if group_by is not None:
            lines.append(f"=== {group_by}={label} ===")
        lines.append(header)
        lines.append("-" * len(header))
        any_row = False
        for stage in STAGES:
            stats = stages.get(stage)
            if stats is None:
                continue
            any_row = True
            row = stage.ljust(14) + "".join(
                _format_num(stats[k]).rjust(col_w) for k in STAT_KEYS
            )
            lines.append(row)
        if not any_row:
            lines.append("(no data)")
        lines.append("")  # blank line between groups
    return "\n".join(lines).rstrip("\n") + "\n"


# -------------------------------------------------------------------------- CLI


def _default_paths() -> list[str]:
    """Default input from LATENCY_LOG_PATH env (empty/unset -> no default)."""
    raw = os.environ.get("LATENCY_LOG_PATH")
    if raw is None:
        return []
    raw = raw.strip()
    return [raw] if raw else []


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="latency_report",
        description="Aggregate voice-bot latency JSONL into per-stage stats.",
    )
    parser.add_argument(
        "--path",
        action="append",
        metavar="FILE",
        help="JSONL file to read (repeatable). Defaults to $LATENCY_LOG_PATH.",
    )
    parser.add_argument(
        "--group-by",
        choices=GROUP_FIELDS,
        default=None,
        help="Group records by 'engine' or 'scenario' before aggregating.",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit machine-readable JSON instead of a text table.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    paths = args.path if args.path else _default_paths()
    if not paths:
        print(
            "error: no input. Pass --path FILE (repeatable) or set "
            "LATENCY_LOG_PATH.",
            file=sys.stderr,
        )
        return 2

    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        for p in missing:
            print(f"error: no such file: {p}", file=sys.stderr)
        return 2

    records = load_records(paths)
    agg = aggregate(records, group_by=args.group_by)

    if args.as_json:
        print(
            json.dumps(
                {"group_by": args.group_by, "groups": agg},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if not records:
            print("(no records)")
        else:
            sys.stdout.write(format_table(agg, args.group_by))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
