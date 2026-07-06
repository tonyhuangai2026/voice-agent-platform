"""T7 — integration checkpoint: moto end-to-end across the REAL Demo-in-DDB modules.

This is the cross-module contract proof demanded by reviewer BLOCKER #2 (the
6-task DAG had no integration checkpoint). Unlike the per-module unit tests
(test_demo_store / test_migrate_demos / test_admin_api filler cases), every test
here wires the *actual* modules together against a single moto-mocked DynamoDB
table — no isolated mocks of the collaborators:

  * scripts.migrate_demos_to_ddb.migrate()  — the real migration entry fn
  * demo_store.DemoStore                     — rescan / get / list / put
  * bot.admin_demo_patch                      — via the FastAPI TestClient PATCH
  * demo_loader.normalize_demo_dict          — shared key-shape normalizer
  * tools.registry.get_tool_defs             — the tool_ids contract consumer
  * timeout_filler.TimeoutFillerObserver     — the filler.probability consumer

Coverage (task ACs):
  1. Empty table: DemoStore.rescan() -> list() == []  (documented "pre-migration
     empty table" degrade — no crash).
  2. Migration: run migrate() against the real data/ into DemosTable ->
     DemoStore.rescan() -> get(id) returns a full dict CONTAINING `tool_ids`;
     list() shape == {id,label,lang,kb_chars}.
  3. Full-field PATCH: admin_demo_patch (via TestClient) changes
     label + system[lang] + kb_body + filler -> writes DDB -> rescan ->
     get(id) reflects ALL updates.
  4. tool_ids end-to-end: migrate it-helpdesk (end_call/transfer_to_human) ->
     get -> tool_ids non-empty AND get_tool_defs(tool_ids, scope) resolves
     without KeyError (proves the BLOCKER #1 contract is truly wired through).
  5. filler.probability is a float (not Decimal) on read-back, i.e. it can be
     handed to TimeoutFillerObserver.

moto availability: moto IS present in this repo's dev venv (it backs
test_admin_api), so the full path runs. The fallback note (table-missing
degrade + pure-function chaining) is documented in the task report; AC1 already
exercises the degrade-on-empty branch.
"""

import asyncio
import importlib
import os
import sys

import boto3
import pytest
from moto import mock_aws

# The full-link PATCH path logs in through user_store -> bcrypt. Without bcrypt
# the login path raises AuthUnavailable; skip the whole module (mirrors
# test_admin_api). moto is likewise required for the in-memory DDB.
pytest.importorskip("bcrypt")
pytest.importorskip("moto")

USERS_TABLE = "voicebot-t7-users"
DEMOS_TABLE = "voicebot-t7-demos"
_ADMIN_PWD = "test-pwd"

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO_DATA_ROOT = os.path.join(_REPO_ROOT, "data")

# Real demos in data/ used by the assertions below.
_TOOLS_DEMO_ID = "it-helpdesk"  # carries end_call + transfer_to_human
_PATCH_DEMO_ID = "it-helpdesk"


def _create_table(name: str, key: str, region: str = "us-east-1") -> None:
    ddb = boto3.client("dynamodb", region_name=region)
    ddb.create_table(
        TableName=name,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": key, "AttributeType": "S"}],
        KeySchema=[{"AttributeName": key, "KeyType": "HASH"}],
    )
    ddb.get_waiter("table_exists").wait(TableName=name)


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    """Point bot.py's module-level singletons at the moto tables + dummy creds.

    Same env contract as test_admin_api: ADMIN_PASSWORD is unused (the bootstrap
    admin is created explicitly), AUTH_SECRET stabilizes JWTs, and MINIMAX_API_KEY
    lets bot.py import without a real key.
    """
    monkeypatch.setenv("ADMIN_PASSWORD", _ADMIN_PWD)
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    monkeypatch.setenv("DEMOS_TABLE", DEMOS_TABLE)
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    with mock_aws():
        _create_table(USERS_TABLE, "username")
        _create_table(DEMOS_TABLE, "id")
        yield


def _import_app():
    """(Re-)import bot.py fresh so module-level singletons see the moto env."""
    for mod in list(sys.modules):
        if mod in ("bot", "runtime_config", "demo_store", "demo_loader", "user_store"):
            del sys.modules[mod]
    return importlib.import_module("bot")


def _admin_client(bot):
    """A TestClient carrying a logged-in admin vb_session cookie."""
    from fastapi.testclient import TestClient

    asyncio.run(bot.USER_STORE.create("admin", _ADMIN_PWD, role="admin"))
    client = TestClient(bot.app, base_url="https://testserver")
    client.__enter__()
    r = client.post("/api/auth/login", json={"username": "admin", "password": _ADMIN_PWD})
    assert r.status_code == 200, r.text
    return client


def _run_real_migration(bot, *, overwrite: bool = False) -> dict:
    """Run the REAL migration entry function against the repo data/ root,
    writing into the bot's DDB-backed DemoStore singleton (same moto table).

    We pass bot.DEMO_LOADER as the store so the migration, the PATCH endpoint,
    and the read-back assertions all share one DemoStore/cache — exercising the
    true end-to-end wiring rather than a parallel store object.
    """
    from scripts.migrate_demos_to_ddb import migrate

    return asyncio.run(
        migrate(data_root=_REPO_DATA_ROOT, store=bot.DEMO_LOADER, overwrite=overwrite)
    )


# ---------------------------------------------------------------------------
# AC1 — empty table degrade: rescan() on an empty (but present) table -> list() []
# ---------------------------------------------------------------------------
def test_empty_table_rescan_degrades_to_empty_list():
    """Pre-migration empty table: rescan() loads 0 demos and list()/get() are
    empty — no crash (documented degrade)."""
    bot = _import_app()
    store = bot.DEMO_LOADER  # DDB-backed DemoStore pointed at the empty moto table

    count = asyncio.run(store.rescan())
    assert count == 0
    assert store.list() == []
    assert store.get("anything") is None
    # The table EXISTS (just empty), so this is the clean degrade path, not the
    # table-missing branch — last_skipped stays empty.
    assert store.last_skipped == []


# ---------------------------------------------------------------------------
# AC2 — migrate real data/ -> rescan -> get() full dict w/ tool_ids; list() shape
# ---------------------------------------------------------------------------
def test_migrate_then_get_full_dict_and_list_shape():
    bot = _import_app()
    store = bot.DEMO_LOADER

    summary = _run_real_migration(bot)
    # Every demo on disk should have been a fresh migrate (table started empty).
    assert summary["total"] >= 1
    assert len(summary["migrated"]) == summary["total"]
    assert summary["overwritten"] == []

    n = asyncio.run(store.rescan())
    assert n == summary["total"]

    # get() returns a full demo dict that CONTAINS the tool_ids key (BLOCKER #1).
    demo = store.get(_TOOLS_DEMO_ID)
    assert demo is not None, f"{_TOOLS_DEMO_ID} not in store after migration"
    assert demo["id"] == _TOOLS_DEMO_ID
    assert "tool_ids" in demo, "migrated demo dict must carry the tool_ids key"
    assert "tools" not in demo, "internal key must be tool_ids, never tools"
    assert "system" in demo and isinstance(demo["system"], dict)

    # list() shape is exactly {id, label, lang, kb_chars}.
    summaries = store.list()
    assert len(summaries) == summary["total"]
    for s in summaries:
        assert set(s.keys()) == {"id", "label", "lang", "kb_chars"}
    row = next(s for s in summaries if s["id"] == _TOOLS_DEMO_ID)
    assert isinstance(row["kb_chars"], int)
    assert row["label"] == demo["label"]
    assert row["lang"] == demo["lang"]


# ---------------------------------------------------------------------------
# AC3 — full-field PATCH (label + system[lang] + kb_body + filler) -> read-back
# ---------------------------------------------------------------------------
def test_full_field_patch_writes_ddb_and_reads_back():
    bot = _import_app()
    client = _admin_client(bot)
    store = bot.DEMO_LOADER

    _run_real_migration(bot)
    asyncio.run(store.rescan())

    before = store.get(_PATCH_DEMO_ID)
    assert before is not None
    lang = before["lang"]  # en-US

    new_label = "IT Help Desk — T7 patched"
    new_system_text = "You are the T7 integration-test help-desk bot."
    new_kb_body = "T7 KB: reset passwords, unlock accounts, escalate P1s."
    new_filler = {"enabled": True, "timeout_ms": 850, "probability": 0.42}

    r = client.patch(
        f"/api/admin/demos/{_PATCH_DEMO_ID}",
        json={
            "label": new_label,
            "system": {lang: new_system_text},
            "kb_body": new_kb_body,
            "filler": new_filler,
        },
    )
    assert r.status_code == 200, r.text

    # The PATCH endpoint already wrote DDB + rescanned the SAME store; read back
    # straight from the store cache to prove the round-trip persisted.
    after = store.get(_PATCH_DEMO_ID)
    assert after is not None
    assert after["label"] == new_label
    assert after["system"][lang] == new_system_text
    # kb_body provided as a bare str replaces wholesale.
    assert after["kb_body"] == new_kb_body
    assert after["filler"] == new_filler

    # A truly independent read (fresh rescan from the moto table, not the cache
    # the PATCH left behind) must show the same — proves it hit DynamoDB.
    asyncio.run(store.rescan())
    reread = store.get(_PATCH_DEMO_ID)
    assert reread["label"] == new_label
    assert reread["system"][lang] == new_system_text
    assert reread["kb_body"] == new_kb_body
    assert reread["filler"] == new_filler


# ---------------------------------------------------------------------------
# AC4 — tool_ids end-to-end: migrate it-helpdesk -> get -> get_tool_defs resolves
# ---------------------------------------------------------------------------
def test_tool_ids_end_to_end_resolves_via_registry():
    bot = _import_app()
    store = bot.DEMO_LOADER
    from tools.registry import get_tool_defs

    _run_real_migration(bot)
    asyncio.run(store.rescan())

    demo = store.get(_TOOLS_DEMO_ID)
    assert demo is not None
    tool_ids = demo["tool_ids"]
    assert isinstance(tool_ids, list) and tool_ids, "it-helpdesk must carry tools"
    # The manifest declares these two; assert they survived the round-trip.
    assert "end_call" in tool_ids
    assert "transfer_to_human" in tool_ids

    # The contract: feeding tool_ids straight into get_tool_defs must resolve
    # without KeyError (BLOCKER #1 end-to-end insurance). it-helpdesk's tools are
    # scope {phone, web}, so both channels resolve them.
    for scope in ("phone", "web"):
        defs = get_tool_defs(tool_ids, scope)
        resolved_ids = [d.id for d in defs]
        assert "end_call" in resolved_ids
        assert "transfer_to_human" in resolved_ids


# ---------------------------------------------------------------------------
# AC5 — filler.probability is a float (not Decimal) and feeds TimeoutFillerObserver
# ---------------------------------------------------------------------------
def test_filler_probability_is_float_after_ddb_roundtrip():
    bot = _import_app()
    client = _admin_client(bot)
    store = bot.DEMO_LOADER

    _run_real_migration(bot)
    asyncio.run(store.rescan())

    # No data/ demo ships a filler block, so PATCH one in (fractional probability
    # is the Decimal/float trap: bot._to_ddb writes Decimal, _from_ddb must read
    # back a float).
    r = client.patch(
        f"/api/admin/demos/{_PATCH_DEMO_ID}",
        json={"filler": {"enabled": True, "timeout_ms": 700, "probability": 0.25}},
    )
    assert r.status_code == 200, r.text

    # Fresh rescan from the moto table (not the post-PATCH cache) to prove the
    # Decimal->float conversion happens on the real DDB read path.
    asyncio.run(store.rescan())
    demo = store.get(_PATCH_DEMO_ID)
    filler = demo["filler"]
    prob = filler["probability"]

    from decimal import Decimal

    assert not isinstance(prob, Decimal), "probability must NOT be a Decimal"
    assert isinstance(prob, float)
    assert prob == 0.25
    # timeout_ms is integral -> int (not Decimal either).
    assert isinstance(filler["timeout_ms"], int)
    assert filler["timeout_ms"] == 700

    # It must be passable to TimeoutFillerObserver (the real consumer) — a
    # Decimal here would be the regression this AC guards. Construct it the same
    # way bot.py does at pipeline-build time (task injected post-construction).
    from timeout_filler import TimeoutFillerObserver

    obs = TimeoutFillerObserver(
        task=None,
        lang_key=demo["lang"],
        enabled=filler["enabled"],
        timeout_ms=filler["timeout_ms"],
        probability=prob,
    )
    assert obs is not None
    # The float survived all the way into the observer's internal prob.
    assert obs._prob == 0.25


# ---------------------------------------------------------------------------
# asr_filter — per-demo PATCH writes DDB and survives a fresh rescan, with the
# min_confidence float surviving the Decimal round-trip (ASR-filter task §5/§8)
# ---------------------------------------------------------------------------
def test_asr_filter_patch_writes_ddb_and_reads_back():
    bot = _import_app()
    client = _admin_client(bot)
    store = bot.DEMO_LOADER

    _run_real_migration(bot)
    asyncio.run(store.rescan())

    new_asr = {"enabled": True, "min_confidence": 0.35, "max_chars": 6, "max_words": 2}
    r = client.patch(
        f"/api/admin/demos/{_PATCH_DEMO_ID}",
        json={"asr_filter": new_asr},
    )
    assert r.status_code == 200, r.text

    after = store.get(_PATCH_DEMO_ID)
    assert after["asr_filter"] == new_asr
    assert isinstance(after["asr_filter"]["min_confidence"], float)

    # Independent re-read from the moto table (not the cache the PATCH left).
    asyncio.run(store.rescan())
    reread = store.get(_PATCH_DEMO_ID)
    assert reread["asr_filter"] == new_asr
    assert isinstance(reread["asr_filter"]["min_confidence"], float)
    assert isinstance(reread["asr_filter"]["max_chars"], int)

    # The stored block splats cleanly into the resolver + filter ctor.
    resolved = bot._resolve_asr_filter(reread, {})
    assert resolved["enabled"] is True
    assert resolved["min_confidence"] == 0.35
    assert resolved["max_cjk_chars"] == 6
    assert resolved["max_latin_words"] == 2
    from asr_filter import TranscriptHallucinationFilter
    assert TranscriptHallucinationFilter(**resolved) is not None
