"""Focused unit tests for latency_log.write() disk behaviour (task T1).

Covers the makedirs auto-create fix plus the documented degrade/no-op contract:
  * LATENCY_LOG_PATH -> a NON-EXISTENT nested subdir under tmp: write() must
    auto-create the parent dir(s) and append exactly one valid JSON line.
  * LATENCY_LOG_PATH="" : write() is a no-op — no dir created, no file written.
  * An unwritable parent dir: write() must NOT raise (degrades to one-shot warn).

These complement (and overlap intentionally with) the inline writer cases in
tests/test_latency.py so the disk contract has a dedicated, self-contained home.
"""

from __future__ import annotations

import json
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import latency_log  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_guard(monkeypatch):
    # Each case starts with the one-shot warning guard cleared so warn-once
    # logic from a prior test never masks a fresh failure path.
    monkeypatch.setattr(latency_log, "_warned_once", False)
    yield


def test_write_auto_creates_missing_subdir(tmp_path, monkeypatch):
    """Path under a not-yet-existing nested subdir → dir is created and one
    valid JSON line is appended."""
    target = tmp_path / "deep" / "nested" / "logs" / "latency.jsonl"
    assert not target.parent.exists()  # precondition: dir does NOT exist
    monkeypatch.setenv("LATENCY_LOG_PATH", str(target))

    rec = {"call_id": "web-1", "turn_id": 1, "e2e_ms": 1840, "msg": "café"}
    latency_log.write(rec)

    assert target.parent.is_dir()  # makedirs ran
    lines = target.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0]) == rec
    # ensure_ascii=False keeps non-ASCII human-readable on disk.
    assert "café" in lines[0]


def test_write_appends_second_line_after_dir_exists(tmp_path, monkeypatch):
    """A second write to the same auto-created path appends (not truncates)."""
    target = tmp_path / "made" / "latency.jsonl"
    monkeypatch.setenv("LATENCY_LOG_PATH", str(target))

    latency_log.write({"turn_id": 1})
    latency_log.write({"turn_id": 2})

    parsed = [json.loads(ln) for ln in target.read_text().splitlines()]
    assert parsed == [{"turn_id": 1}, {"turn_id": 2}]


def test_empty_path_is_noop(tmp_path, monkeypatch):
    """LATENCY_LOG_PATH="" disables disk writes: no dir, no file, no raise."""
    monkeypatch.setenv("LATENCY_LOG_PATH", "")
    latency_log.write({"x": 1})
    assert list(tmp_path.iterdir()) == []


def test_unwritable_dir_degrades_without_raising(tmp_path, monkeypatch):
    """makedirs failure on an unwritable parent degrades to no-op, never raises."""
    # Create a read-only directory and aim the log at a child subdir of it so
    # os.makedirs() raises PermissionError, exercising the in-try degrade path.
    ro = tmp_path / "readonly"
    ro.mkdir()
    os.chmod(ro, 0o500)  # r-x, no write
    target = ro / "child" / "latency.jsonl"
    monkeypatch.setenv("LATENCY_LOG_PATH", str(target))
    try:
        # Must not raise even though the parent dir cannot be created.
        latency_log.write({"x": 1})
    finally:
        os.chmod(ro, 0o700)  # restore so tmp cleanup can remove it
    # Nothing was written.
    assert not target.exists()


def test_unwritable_dir_does_not_raise_when_running_as_root(tmp_path, monkeypatch):
    """Fallback: if the suite runs as root (chmod is bypassed), point at a path
    whose parent is a regular file so open()/makedirs still fails and degrades.
    This guarantees the degrade-no-raise contract regardless of test UID."""
    afile = tmp_path / "iam_a_file"
    afile.write_text("not a dir")
    target = afile / "sub" / "latency.jsonl"  # parent component is a file
    monkeypatch.setenv("LATENCY_LOG_PATH", str(target))
    # Must not raise (NotADirectoryError swallowed by the degrade path).
    latency_log.write({"x": 1})
