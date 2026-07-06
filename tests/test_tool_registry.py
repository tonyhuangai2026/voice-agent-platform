"""Unit tests for tools.registry.

Covers the five behavioral acceptance criteria for T1:

1. REGISTRY contains end_call + transfer_to_human as ToolDefinitions.
2. Each tool's policy_blurb has non-empty text for all four supported
   languages (en-US / zh-CN / zh-HK / ja-JP).
3. get_tool_defs(['end_call', 'foo'], 'phone') returns only end_call AND
   logs a warning mentioning 'foo'.
4. assemble_tools_schema preserves length + each FunctionSchema name
   matches the input ToolDefinition.id.
5. assemble_policy_blurb joins per-language blurbs separated by a blank
   line; fallback to en-US when the requested language is missing.
"""
from __future__ import annotations

import logging

import pytest

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema

from tools import registry as reg
from tools.registry import (
    REGISTRY,
    SUPPORTED_LANGS,
    ToolDefinition,
    assemble_policy_blurb,
    assemble_tools_schema,
    get_tool_defs,
)


# ---------------------------------------------------------------------------
# AC1: REGISTRY contains both tools as ToolDefinitions
# ---------------------------------------------------------------------------
def test_registry_contains_both_tools():
    assert "end_call" in REGISTRY
    assert "transfer_to_human" in REGISTRY
    assert isinstance(REGISTRY["end_call"], ToolDefinition)
    assert isinstance(REGISTRY["transfer_to_human"], ToolDefinition)
    # id must equal the schema name so the LLM handler registration matches.
    assert REGISTRY["end_call"].schema.name == "end_call"
    assert REGISTRY["transfer_to_human"].schema.name == "transfer_to_human"


def test_registry_tools_in_phone_and_web_scope():
    for tool_id in ("end_call", "transfer_to_human"):
        scope = REGISTRY[tool_id].scope
        assert "phone" in scope
        assert "web" in scope
        assert isinstance(scope, frozenset)


# ---------------------------------------------------------------------------
# AC2: Each tool has non-empty policy_blurb for all four languages
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("tool_id", ["end_call", "transfer_to_human"])
@pytest.mark.parametrize("lang", list(SUPPORTED_LANGS))
def test_policy_blurb_all_languages_non_empty(tool_id, lang):
    blurb = REGISTRY[tool_id].policy_blurb.get(lang)
    assert blurb is not None, f"{tool_id} missing blurb for {lang}"
    assert blurb.strip(), f"{tool_id} blurb for {lang} is whitespace-only"


def test_policy_blurb_supported_langs_constant():
    # Sanity: registry's declared SUPPORTED_LANGS matches the four langs we
    # care about. If this drifts, the per-language test above also fails.
    assert set(SUPPORTED_LANGS) == {"en-US", "zh-CN", "zh-HK", "ja-JP"}


# ---------------------------------------------------------------------------
# AC3: get_tool_defs filters unknown ids and warns
# ---------------------------------------------------------------------------
def test_get_tool_defs_drops_unknown_id_and_warns(caplog):
    with caplog.at_level(logging.WARNING, logger=reg.logger.name):
        defs = get_tool_defs(["end_call", "foo"], "phone")

    assert [d.id for d in defs] == ["end_call"]

    warnings = [r for r in caplog.records if r.levelno >= logging.WARNING]
    assert any("foo" in r.getMessage() for r in warnings), (
        "expected a WARNING-level log mentioning the unknown id 'foo'; "
        f"got: {[r.getMessage() for r in warnings]}"
    )


def test_get_tool_defs_preserves_input_order():
    defs = get_tool_defs(["transfer_to_human", "end_call"], "phone")
    assert [d.id for d in defs] == ["transfer_to_human", "end_call"]


def test_get_tool_defs_filters_by_scope():
    # Inject a temporary single-scope tool to confirm scope filtering.
    only_web = ToolDefinition(
        id="_only_web_test",
        label="Web Only Test",
        description_short="test-only",
        schema=FunctionSchema(
            name="_only_web_test",
            description="test only",
            properties={},
            required=[],
        ),
        policy_blurb={lang: "x" for lang in SUPPORTED_LANGS},
        scope=frozenset({"web"}),
    )
    REGISTRY[only_web.id] = only_web
    try:
        phone_defs = get_tool_defs(["_only_web_test"], "phone")
        web_defs = get_tool_defs(["_only_web_test"], "web")
        assert phone_defs == []
        assert [d.id for d in web_defs] == ["_only_web_test"]
    finally:
        del REGISTRY[only_web.id]


# ---------------------------------------------------------------------------
# AC4: assemble_tools_schema returns a ToolsSchema with matching names
# ---------------------------------------------------------------------------
def test_assemble_tools_schema_shape():
    defs = get_tool_defs(["end_call", "transfer_to_human"], "phone")
    schema = assemble_tools_schema(defs)

    assert isinstance(schema, ToolsSchema)
    standard = schema.standard_tools
    assert len(standard) == len(defs)
    for tool, defn in zip(standard, defs):
        assert isinstance(tool, FunctionSchema)
        assert tool.name == defn.id


def test_assemble_tools_schema_empty():
    schema = assemble_tools_schema([])
    assert isinstance(schema, ToolsSchema)
    assert schema.standard_tools == []


# ---------------------------------------------------------------------------
# AC5: assemble_policy_blurb joins per-language with a blank line, falls
#       back to en-US when requested language is missing
# ---------------------------------------------------------------------------
def test_assemble_policy_blurb_zh_cn_joined_with_blank_line():
    defs = get_tool_defs(["end_call", "transfer_to_human"], "phone")
    text = assemble_policy_blurb(defs, "zh-CN")

    assert text, "blurb assembly produced empty string for zh-CN"
    # Two blurbs -> exactly one blank-line separator between them.
    assert text.count("\n\n") == 1
    parts = text.split("\n\n")
    assert len(parts) == 2
    # Both parts must be the zh-CN text from the registry, not en-US.
    assert parts[0] == REGISTRY["end_call"].policy_blurb["zh-CN"].strip()
    assert parts[1] == REGISTRY["transfer_to_human"].policy_blurb["zh-CN"].strip()


def test_assemble_policy_blurb_falls_back_to_en_us(caplog):
    # Build a tool that has only en-US text, then ask for zh-CN.
    only_en = ToolDefinition(
        id="_only_en_test",
        label="EN Only Test",
        description_short="test-only",
        schema=FunctionSchema(
            name="_only_en_test",
            description="test",
            properties={},
            required=[],
        ),
        policy_blurb={"en-US": "EN-only fallback body."},
        scope=frozenset({"phone", "web"}),
    )

    with caplog.at_level(logging.INFO, logger=reg.logger.name):
        text = assemble_policy_blurb([only_en], "zh-CN")

    assert text == "EN-only fallback body."


def test_assemble_policy_blurb_empty_defs_returns_empty_string():
    assert assemble_policy_blurb([], "en-US") == ""


def test_end_call_description_mentions_both_channels():
    """T5 acceptance — scope=web closes WS, scope=phone triggers SIP BYE.
    The LLM must see this cross-channel hint in the tool description so it
    behaves correctly on whichever leg it is running."""
    end_call = reg.REGISTRY["end_call"]
    desc = end_call.schema.description.lower()
    assert "phone" in desc
    assert "web" in desc
    assert ("sip" in desc) or ("bye" in desc) or ("pstn" in desc)
