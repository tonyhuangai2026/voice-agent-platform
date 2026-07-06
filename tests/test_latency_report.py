"""Unit tests for scripts/latency_report.py — pure aggregation core + parsing.

No real call data: synthetic records / JSONL only. Stdlib + pytest only.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

# scripts/ is not a package; load latency_report.py by path.
_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "latency_report.py"
_spec = importlib.util.spec_from_file_location("latency_report", _SCRIPT)
latency_report = importlib.util.module_from_spec(_spec)
sys.modules["latency_report"] = latency_report
_spec.loader.exec_module(latency_report)

percentile = latency_report.percentile
aggregate = latency_report.aggregate
parse_jsonl = latency_report.parse_jsonl


# ----------------------------------------------------------------- percentile


def test_percentile_known_array_p50_p95_p99():
    # n=10, 0-based rank = p/100*(n-1) with linear interpolation.
    data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
    # p50: rank 4.5 -> 5 + (6-5)*0.5 = 5.5
    assert percentile(data, 50) == pytest.approx(5.5)
    # p95: rank 8.55 -> 9 + (10-9)*0.55 = 9.55
    assert percentile(data, 95) == pytest.approx(9.55)
    # p99: rank 8.91 -> 9 + (10-9)*0.91 = 9.91
    assert percentile(data, 99) == pytest.approx(9.91)


def test_percentile_unsorted_input_and_bounds():
    data = [40, 10, 30, 20]  # unsorted
    assert percentile(data, 0) == pytest.approx(10.0)  # min
    assert percentile(data, 100) == pytest.approx(40.0)  # max
    # p50: rank 1.5 -> 20 + (30-20)*0.5 = 25
    assert percentile(data, 50) == pytest.approx(25.0)


def test_percentile_single_value():
    assert percentile([7], 50) == 7.0
    assert percentile([7], 99) == 7.0


def test_percentile_errors():
    with pytest.raises(ValueError):
        percentile([], 50)
    with pytest.raises(ValueError):
        percentile([1, 2], 150)


# ------------------------------------------------------------------- aggregate


def test_aggregate_skips_null_and_missing():
    records = [
        {"e2e_ms": 100, "stt_ms": 10},
        {"e2e_ms": 200, "stt_ms": None},  # null stt skipped
        {"e2e_ms": 300},  # missing stt skipped
    ]
    agg = aggregate(records)
    assert set(agg) == {"all"}
    e2e = agg["all"]["e2e_ms"]
    assert e2e["count"] == 3
    assert e2e["min"] == 100
    assert e2e["max"] == 300
    assert e2e["avg"] == 200.0
    stt = agg["all"]["stt_ms"]
    assert stt["count"] == 1  # only the one non-null value
    assert stt["avg"] == 10
    # A stage with zero samples is None.
    assert agg["all"]["llm_ttft_ms"] is None


def test_aggregate_ignores_bool_and_non_numeric():
    records = [
        {"e2e_ms": 100},
        {"e2e_ms": True},  # bool must NOT be treated as 1
        {"e2e_ms": "fast"},  # non-numeric skipped
    ]
    agg = aggregate(records)
    assert agg["all"]["e2e_ms"]["count"] == 1


def test_aggregate_group_by_engine():
    records = [
        {"engine": "pipeline", "e2e_ms": 100},
        {"engine": "pipeline", "e2e_ms": 200},
        {"engine": "nova-sonic", "e2e_ms": 900},
    ]
    agg = aggregate(records, group_by="engine")
    assert set(agg) == {"pipeline", "nova-sonic"}
    assert agg["pipeline"]["e2e_ms"]["count"] == 2
    assert agg["pipeline"]["e2e_ms"]["avg"] == 150.0
    assert agg["nova-sonic"]["e2e_ms"]["count"] == 1
    assert agg["nova-sonic"]["e2e_ms"]["avg"] == 900


def test_aggregate_group_by_scenario_and_unknown_bucket():
    records = [
        {"scenario": "it-helpdesk", "e2e_ms": 100},
        {"scenario": None, "e2e_ms": 500},  # -> "unknown"
        {"e2e_ms": 600},  # missing -> "unknown"
    ]
    agg = aggregate(records, group_by="scenario")
    assert set(agg) == {"it-helpdesk", "unknown"}
    assert agg["it-helpdesk"]["e2e_ms"]["count"] == 1
    assert agg["unknown"]["e2e_ms"]["count"] == 2


def test_aggregate_invalid_group_by():
    with pytest.raises(ValueError):
        aggregate([], group_by="lang")


# --------------------------------------------------------------- JSONL parsing


SAMPLE_JSONL = "\n".join(
    [
        json.dumps(
            {
                "ts": "2026-06-24T07:00:00.000Z",
                "call_id": "web-1",
                "turn_id": 1,
                "engine": "pipeline",
                "scenario": "it-helpdesk",
                "lang": "zh-HK",
                "e2e_ms": 1840,
                "stt_ms": 420,
                "llm_ttft_ms": 560,
                "llm_total_ms": 980,
                "tts_ttfb_ms": 310,
            }
        ),
        "",  # blank line tolerated
        json.dumps(
            {
                "ts": "2026-06-24T07:00:05.000Z",
                "call_id": "phone-2",
                "turn_id": 1,
                "engine": "nova-sonic",
                "scenario": "it-helpdesk",
                "lang": "en-US",
                "e2e_ms": 900,
                "stt_ms": None,
                "llm_ttft_ms": None,
                "llm_total_ms": None,
                "tts_ttfb_ms": None,
            }
        ),
    ]
)


def test_parse_jsonl_sample():
    records = parse_jsonl(SAMPLE_JSONL.splitlines())
    assert len(records) == 2
    assert records[0]["engine"] == "pipeline"
    assert records[1]["e2e_ms"] == 900
    assert records[1]["stt_ms"] is None


def test_parse_jsonl_skips_malformed(capsys):
    lines = ['{"e2e_ms": 1}', "not json at all", "[1,2,3]"]
    records = parse_jsonl(lines)
    assert len(records) == 1  # only the valid object
    err = capsys.readouterr().err
    assert "skipping malformed" in err
    assert "non-object" in err


def test_aggregate_over_parsed_sample():
    records = parse_jsonl(SAMPLE_JSONL.splitlines())
    agg = aggregate(records)
    # Both turns have e2e; only the pipeline turn has stt.
    assert agg["all"]["e2e_ms"]["count"] == 2
    assert agg["all"]["stt_ms"]["count"] == 1
    assert agg["all"]["stt_ms"]["avg"] == 420


# --------------------------------------------------------------- CLI / main()


def test_main_default_path_from_env(tmp_path, monkeypatch, capsys):
    log = tmp_path / "lat.jsonl"
    log.write_text(SAMPLE_JSONL + "\n", encoding="utf-8")
    monkeypatch.setenv("LATENCY_LOG_PATH", str(log))
    rc = latency_report.main([])  # no --path -> falls back to env
    assert rc == 0
    out = capsys.readouterr().out
    assert "e2e_ms" in out
    assert "p95" in out


def test_main_json_output(tmp_path, capsys):
    log = tmp_path / "lat.jsonl"
    log.write_text(SAMPLE_JSONL + "\n", encoding="utf-8")
    rc = latency_report.main(["--path", str(log), "--json", "--group-by", "engine"])
    assert rc == 0
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["group_by"] == "engine"
    assert set(parsed["groups"]) == {"pipeline", "nova-sonic"}
    assert parsed["groups"]["pipeline"]["e2e_ms"]["count"] == 1


def test_main_multiple_paths(tmp_path, capsys):
    a = tmp_path / "a.jsonl"
    b = tmp_path / "b.jsonl"
    a.write_text(json.dumps({"engine": "pipeline", "e2e_ms": 100}) + "\n", "utf-8")
    b.write_text(json.dumps({"engine": "pipeline", "e2e_ms": 300}) + "\n", "utf-8")
    rc = latency_report.main(["--path", str(a), "--path", str(b), "--json"])
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["groups"]["all"]["e2e_ms"]["count"] == 2
    assert parsed["groups"]["all"]["e2e_ms"]["avg"] == 200.0


def test_main_no_input_returns_2(monkeypatch, capsys):
    monkeypatch.delenv("LATENCY_LOG_PATH", raising=False)
    rc = latency_report.main([])
    assert rc == 2
    assert "no input" in capsys.readouterr().err


def test_main_missing_file_returns_2(tmp_path, capsys):
    rc = latency_report.main(["--path", str(tmp_path / "nope.jsonl")])
    assert rc == 2
    assert "no such file" in capsys.readouterr().err
