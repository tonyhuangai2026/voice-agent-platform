"""Unit tests for T2: demo_loader tools-field parsing, empty-KB tolerance,
and last_skipped diagnostics.

Acceptance criteria covered (per task 6a24cb00):

(a) demo_loader parses ``tools: [end_call, transfer_to_human]`` into
    ``demo["tool_ids"] == ["end_call", "transfer_to_human"]``.
(b) Manifest without a ``tools`` field yields ``demo["tool_ids"] == []``
    (backward compatible default).
(c) Unknown tool ids are dropped using ``tools.registry.REGISTRY`` keys
    (T1 registry validator).
(d) Missing / unreadable KB file does not reject the demo; ``kb_body``
    is "" (or per-lang empty strings) instead.
(e) Manifests where ``system`` / ``greeting`` are missing or have no
    languages are skipped, and the rejection is recorded on
    ``loader.last_skipped`` as ``{"id": ..., "reason": ...}``.

(f) ``loader.last_skipped`` is reset at the start of every ``rescan()``
    call — only the most recent scan's skips remain.
"""
from __future__ import annotations

import logging
import os

import pytest
import yaml

from demo_loader import DemoLoader
from tools.registry import REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _write_demo(
    root,
    demo_id: str,
    *,
    manifest_extra: dict | None = None,
    write_kb: bool = True,
    kb_filename: str = "kb.md",
    kb_body_text: str = "kb body",
    omit_system: bool = False,
    omit_greeting: bool = False,
    empty_system: bool = False,
):
    """Materialise a tmp_path/<demo_id>/manifest.yaml (+ optional kb.md).

    ``manifest_extra`` is merged on top of the minimal valid manifest. Pass
    ``write_kb=False`` to deliberately leave the file out so we can test
    the missing-KB path.
    """
    sub = root / demo_id
    sub.mkdir()
    if write_kb:
        (sub / kb_filename).write_text(kb_body_text)

    manifest: dict = {
        "id": demo_id,
        "label": demo_id.title(),
        "lang": "en-US",
    }
    if not omit_system:
        manifest["system"] = {} if empty_system else {"en-US": "you are a bot"}
    if not omit_greeting:
        manifest["greeting"] = {"en-US": "hi"}

    if manifest_extra:
        manifest.update(manifest_extra)

    (sub / "manifest.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True))
    return sub


# ---------------------------------------------------------------------------
# AC (a): tools field parsed into tool_ids
# ---------------------------------------------------------------------------
def test_tools_field_parsed_into_tool_ids(tmp_path):
    _write_demo(
        tmp_path,
        "with-tools",
        manifest_extra={
            "tools": ["end_call", "transfer_to_human"],
            "kb_path": "kb.md",
        },
    )
    loader = DemoLoader(str(tmp_path))
    demo = loader.get("with-tools")
    assert demo is not None
    assert demo["tool_ids"] == ["end_call", "transfer_to_human"]


def test_tools_field_preserves_order(tmp_path):
    _write_demo(
        tmp_path,
        "ordered",
        manifest_extra={"tools": ["transfer_to_human", "end_call"]},
    )
    loader = DemoLoader(str(tmp_path))
    assert loader.get("ordered")["tool_ids"] == ["transfer_to_human", "end_call"]


# ---------------------------------------------------------------------------
# AC (b): no tools field -> tool_ids = []
# ---------------------------------------------------------------------------
def test_missing_tools_field_defaults_to_empty_list(tmp_path):
    _write_demo(tmp_path, "no-tools")
    loader = DemoLoader(str(tmp_path))
    demo = loader.get("no-tools")
    assert demo is not None
    assert demo["tool_ids"] == []


def test_tools_field_wrong_type_logs_warning_and_uses_empty_list(tmp_path, caplog):
    _write_demo(
        tmp_path,
        "bad-tools-type",
        manifest_extra={"tools": "end_call"},  # str, not list
    )
    with caplog.at_level(logging.WARNING):
        loader = DemoLoader(str(tmp_path))

    demo = loader.get("bad-tools-type")
    assert demo is not None
    assert demo["tool_ids"] == []
    assert any("'tools' must be a list" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# AC (c): unknown ids dropped via tools.registry.REGISTRY
# ---------------------------------------------------------------------------
def test_unknown_tool_id_dropped_with_warning(tmp_path, caplog):
    # Sanity: pin our assumption that "not_a_real_tool" is not in REGISTRY.
    assert "not_a_real_tool" not in REGISTRY

    _write_demo(
        tmp_path,
        "mixed-tools",
        manifest_extra={"tools": ["end_call", "not_a_real_tool"]},
    )
    with caplog.at_level(logging.WARNING):
        loader = DemoLoader(str(tmp_path))

    demo = loader.get("mixed-tools")
    assert demo is not None
    # Only the registry-known id survives.
    assert demo["tool_ids"] == ["end_call"]
    # And the drop is logged with the offending id.
    assert any(
        "not_a_real_tool" in r.getMessage() and "unknown tool id" in r.getMessage()
        for r in caplog.records
    ), [r.getMessage() for r in caplog.records]


def test_all_unknown_tools_yield_empty_tool_ids(tmp_path):
    _write_demo(
        tmp_path,
        "all-unknown",
        manifest_extra={"tools": ["nope_a", "nope_b"]},
    )
    loader = DemoLoader(str(tmp_path))
    demo = loader.get("all-unknown")
    assert demo is not None
    assert demo["tool_ids"] == []


# ---------------------------------------------------------------------------
# AC (d): missing KB file is tolerated, demo still loads with empty kb_body
# ---------------------------------------------------------------------------
def test_missing_kb_file_legacy_string_path_demo_still_loads(tmp_path, caplog):
    # kb_path defaults to "kb.md" historically; with write_kb=False there is
    # no kb.md on disk. The demo must still load, kb_body == "".
    _write_demo(
        tmp_path,
        "no-kb-file",
        write_kb=False,
        manifest_extra={"kb_path": "kb.md"},
    )
    with caplog.at_level(logging.WARNING):
        loader = DemoLoader(str(tmp_path))

    demo = loader.get("no-kb-file")
    assert demo is not None, "demo without kb file must NOT be rejected"
    assert demo["kb_body"] == ""
    assert any("not found" in r.getMessage() for r in caplog.records)


def test_kb_path_omitted_entirely_yields_empty_kb_body(tmp_path):
    # Pure tool-only demo: no kb_path declared, no kb file.
    _write_demo(
        tmp_path,
        "tools-only",
        write_kb=False,
        manifest_extra={"tools": ["end_call"]},
    )
    loader = DemoLoader(str(tmp_path))
    demo = loader.get("tools-only")
    assert demo is not None
    assert demo["kb_body"] == ""
    assert demo["tool_ids"] == ["end_call"]


def test_per_lang_kb_path_partial_missing_uses_empty_string_per_lang(
    tmp_path, caplog,
):
    # Two langs declared, only one file on disk -> the other is "".
    sub = tmp_path / "partial-kb"
    sub.mkdir()
    (sub / "kb.en.md").write_text("english body")
    # zh-HK file deliberately missing.
    manifest = {
        "id": "partial-kb",
        "label": "Partial",
        "lang": "en-US",
        "system": {"en-US": "sys"},
        "greeting": {"en-US": "hi"},
        "kb_path": {"en-US": "kb.en.md", "zh-HK": "kb.zh.md"},
    }
    (sub / "manifest.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True))

    with caplog.at_level(logging.WARNING):
        loader = DemoLoader(str(tmp_path))

    demo = loader.get("partial-kb")
    assert demo is not None
    assert isinstance(demo["kb_body"], dict)
    assert demo["kb_body"]["en-US"] == "english body"
    assert demo["kb_body"]["zh-HK"] == ""
    # Demo must NOT be in last_skipped — partial KB is a soft warning only.
    assert all(s["id"] != "partial-kb" for s in loader.last_skipped)


# ---------------------------------------------------------------------------
# AC (e): missing/empty system or greeting -> demo skipped + last_skipped entry
# ---------------------------------------------------------------------------
def test_missing_system_skips_demo_and_records_reason(tmp_path):
    _write_demo(tmp_path, "no-system", omit_system=True)
    loader = DemoLoader(str(tmp_path))

    assert loader.get("no-system") is None
    skipped_ids = [s["id"] for s in loader.last_skipped]
    assert "no-system" in skipped_ids
    entry = next(s for s in loader.last_skipped if s["id"] == "no-system")
    assert "system" in entry["reason"]


def test_empty_system_dict_skips_demo_and_records_reason(tmp_path):
    # system is a dict but has no languages — the LOCALIZED_REQUIRED rule
    # explicitly requires a NON-EMPTY dict so a misconfigured migration
    # script can't sneak in an empty system prompt.
    _write_demo(tmp_path, "empty-system", empty_system=True)
    loader = DemoLoader(str(tmp_path))

    assert loader.get("empty-system") is None
    entry = next(
        (s for s in loader.last_skipped if s["id"] == "empty-system"),
        None,
    )
    assert entry is not None
    assert "system" in entry["reason"]


def test_missing_greeting_skips_demo_and_records_reason(tmp_path):
    _write_demo(tmp_path, "no-greeting", omit_greeting=True)
    loader = DemoLoader(str(tmp_path))

    assert loader.get("no-greeting") is None
    entry = next(
        (s for s in loader.last_skipped if s["id"] == "no-greeting"),
        None,
    )
    assert entry is not None
    assert "greeting" in entry["reason"]


# ---------------------------------------------------------------------------
# AC (f): last_skipped is reset on each rescan
# ---------------------------------------------------------------------------
def test_last_skipped_reset_each_rescan(tmp_path):
    # First scan: one bad demo present.
    _write_demo(tmp_path, "broken", omit_system=True)
    loader = DemoLoader(str(tmp_path))
    assert any(s["id"] == "broken" for s in loader.last_skipped)
    first_count = len(loader.last_skipped)
    assert first_count >= 1

    # Remove the bad demo, add a fully valid one, rescan.
    import shutil
    shutil.rmtree(tmp_path / "broken")
    _write_demo(tmp_path, "good")
    loader.rescan()

    assert loader.get("good") is not None
    # Nothing was rejected this round, and the previous rejection is gone.
    assert loader.last_skipped == []


def test_last_skipped_attribute_is_list(tmp_path):
    loader = DemoLoader(str(tmp_path))
    # Must always be a list, even on an empty data root.
    assert isinstance(loader.last_skipped, list)


# ---------------------------------------------------------------------------
# Smoke: a fully valid manifest with all features at once still loads.
# ---------------------------------------------------------------------------
def test_full_manifest_with_tools_and_per_lang_kb(tmp_path):
    sub = tmp_path / "full"
    sub.mkdir()
    (sub / "kb.en.md").write_text("EN KB")
    (sub / "kb.zh.md").write_text("ZH KB")
    manifest = {
        "id": "full",
        "label": "Full demo",
        "lang": "en-US",
        "system": {"en-US": "sys-en", "zh-HK": "sys-zh"},
        "greeting": {"en-US": "hi", "zh-HK": "你好"},
        "kb_intro": {"en-US": "intro-en", "zh-HK": "intro-zh"},
        "kb_ack": {"en-US": "ack-en", "zh-HK": "ack-zh"},
        "kb_path": {"en-US": "kb.en.md", "zh-HK": "kb.zh.md"},
        "tools": ["end_call", "transfer_to_human"],
        "tags": ["smoke"],
    }
    (sub / "manifest.yaml").write_text(yaml.safe_dump(manifest, allow_unicode=True))

    loader = DemoLoader(str(tmp_path))
    demo = loader.get("full")
    assert demo is not None
    assert demo["tool_ids"] == ["end_call", "transfer_to_human"]
    assert demo["kb_body"] == {"en-US": "EN KB", "zh-HK": "ZH KB"}
    assert demo["tags"] == ["smoke"]
    assert loader.last_skipped == []
