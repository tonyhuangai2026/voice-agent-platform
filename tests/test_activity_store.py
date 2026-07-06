"""Unit tests for activity_store.ActivityStore (T3 / Part B) — DDB-backed
operations audit log + DEFAULT-DENY redaction.

Coverage (AC#1, #2, #5):
  - log() writes a row with correct day (UTC YYYY-MM-DD) / ts_id
    (<epoch_ms>#<uuid>) / ttl (now + ttl_days*86400).
  - DEFAULT-DENY redaction (round-1 BLOCKER fix): _sanitize_detail masks an
    ODDLY-NAMED credential field (one NOT matching any secret substring) to its
    NAME ONLY ("***changed***"), never its value — the allowlist is the
    primary defence, not the substring scrub. Unknown type masks all values.
  - query() filters by actor/type + date range, newest-first, paginates.
  - Table-missing: log() is a silent no-op AND a simulated underlying op runs
    unaffected; query() -> empty. No raise.
  - Lazy table: constructing an ActivityStore against an absent table never
    raises (the boto3 Table is built on first USE, not in __init__).

DynamoDB is mocked with moto (mock_aws). Best-effort/lazy paths run without a
live table.
"""

from __future__ import annotations

import asyncio
import time
import uuid

import boto3
import pytest

try:
    from moto import mock_aws
    _HAVE_MOTO = True
except Exception:  # pragma: no cover
    _HAVE_MOTO = False

import activity_store
from activity_store import (
    ActivityStore,
    _sanitize_detail,
    ACTIVITY_DETAIL_VALUE_ALLOWLIST,
)

ACTIVITY_TABLE = "voicebot-test-activity"
_MASK = "***changed***"


@pytest.fixture
def ddb_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("ACTIVITY_TABLE", ACTIVITY_TABLE)
    yield


def _create_activity_table(region: str = "us-east-1") -> None:
    ddb = boto3.client("dynamodb", region_name=region)
    ddb.create_table(
        TableName=ACTIVITY_TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "day", "AttributeType": "S"},
            {"AttributeName": "ts_id", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "day", "KeyType": "HASH"},
            {"AttributeName": "ts_id", "KeyType": "RANGE"},
        ],
    )
    ddb.get_waiter("table_exists").wait(TableName=ACTIVITY_TABLE)


def _scan_all(region: str = "us-east-1") -> list[dict]:
    table = boto3.resource("dynamodb", region_name=region).Table(ACTIVITY_TABLE)
    return table.scan().get("Items", [])


# --------------------------------------------------------------------------
# REDACTION — the BLOCKER-fix proof (no DDB needed — pure function)
# --------------------------------------------------------------------------

def test_sanitize_masks_oddly_named_credential_to_name_only():
    """An mcp 'url'/'headers'/'auth' value — keys that do NOT match the secret
    substring scrub — must be stored as the FIELD NAME ONLY, never the raw
    value. This is the default-deny allowlist proof (round-1 BLOCKER)."""
    detail = {
        "id": "srv1",
        "label": "My Server",
        "transport": "streamable_http",
        "enabled": True,
        # Credential-bearing fields whose KEYS do not match password|token|...
        "url": "https://secret-host.internal/mcp?session=abcdef",
        "headers": {"X-Custom": "raw-bearer-value-xyz"},
        "auth": {"type": "sigv4", "service": "bedrock"},
    }
    out = _sanitize_detail("mcp-upsert", detail)
    # Allowlisted fields survive by value.
    assert out["id"] == "srv1"
    assert out["label"] == "My Server"
    assert out["transport"] == "streamable_http"
    assert out["enabled"] is True
    # Non-allowlisted credential-bearing fields → NAME ONLY, value masked.
    assert out["url"] == _MASK
    assert out["headers"] == _MASK
    assert out["auth"] == _MASK
    # The raw secret never appears anywhere in the serialized detail.
    assert "secret-host.internal" not in repr(out)
    assert "raw-bearer-value-xyz" not in repr(out)


def test_sanitize_user_never_stores_password_value():
    """user-* allowlist = {role, disabled}; a password (even under the literal
    'password' key) is masked. The allowlist is what protects us — confirm the
    value is gone."""
    out = _sanitize_detail("user-update", {"role": "admin", "password": "hunter2", "disabled": False})
    assert out["role"] == "admin"
    assert out["disabled"] is False
    assert out["password"] == _MASK
    assert "hunter2" not in repr(out)


def test_sanitize_unknown_type_masks_all_values():
    """An unknown activity type has no allowlist → ALL values masked
    (field-names preserved)."""
    out = _sanitize_detail("totally-unknown-type", {"a": "1", "b": "2"})
    assert out == {"a": _MASK, "b": _MASK}


def test_sanitize_config_allowlist_value_through_residual_scrub():
    """A config field whose KEY accidentally matches the residual scrub list
    but is allowlisted by value still survives the allowlist, then the residual
    scrub runs last as belt-and-suspenders. Confirm an allowlisted non-secret
    survives and a non-allowlisted secret-keyed field is name-only."""
    out = _sanitize_detail("config-web", {"engine": "pipeline", "api_key": "sk-xxxx"})
    assert out["engine"] == "pipeline"
    # api_key is NOT in config-* allowlist → masked by default-deny (and would
    # also be caught by the residual scrub).
    assert out["api_key"] == _MASK
    assert "sk-xxxx" not in repr(out)


def test_allowlist_excludes_secrets_by_construction():
    """Defence-in-depth contract: no secret-bearing field name is in any
    type's allowlist."""
    forbidden = {"password", "password_hash", "url", "headers", "auth", "token", "api_key", "secret"}
    for atype, allow in ACTIVITY_DETAIL_VALUE_ALLOWLIST.items():
        assert not (allow & forbidden), f"{atype} allowlist leaks {allow & forbidden}"


# --------------------------------------------------------------------------
# LAZY TABLE — constructing against an absent table must never raise
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_lazy_table_ctor_never_raises_on_absent_table(ddb_env):
    """Constructing an ActivityStore when the table does NOT exist must not
    touch AWS / raise — the boto3 Table is built on first use (N3)."""
    with mock_aws():
        # No table created. Construction is pure.
        store = ActivityStore()
        assert store._table is None  # not built eagerly


# --------------------------------------------------------------------------
# log() — row shape + ttl
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_log_writes_row_with_day_ts_id_ttl(ddb_env):
    with mock_aws():
        _create_activity_table()
        store = ActivityStore(ttl_days=90)
        t0 = time.time()
        asyncio.run(store.log(
            actor="admin", actor_role="admin", type="login",
            target="admin", detail={"username": "admin"},
        ))
        rows = _scan_all()
        assert len(rows) == 1
        row = rows[0]
        # day = UTC YYYY-MM-DD
        assert len(row["day"]) == 10 and row["day"][4] == "-" and row["day"][7] == "-"
        # ts_id = <epoch_ms>#<uuid-hex>
        assert "#" in row["ts_id"]
        epoch_ms, uid = row["ts_id"].split("#", 1)
        assert epoch_ms.isdigit()
        uuid.UUID(hex=uid)  # parses → valid uuid hex
        # ttl ~= now + 90 days (allow a few seconds of slack)
        expected = int(t0) + 90 * 86400
        assert abs(int(row["ttl"]) - expected) < 10
        assert row["actor"] == "admin"
        assert row["type"] == "login"
        assert row["status"] == "success"
        assert row["detail"] == {"username": "admin"}


@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_log_sanitizes_detail_at_store_layer(ddb_env):
    """Even a careless caller passing a raw credential value is sanitized by the
    store-side backstop before the row is written."""
    with mock_aws():
        _create_activity_table()
        store = ActivityStore()
        asyncio.run(store.log(
            actor="admin", type="mcp-upsert", target="srv1",
            detail={"id": "srv1", "url": "https://secret/x", "headers": {"A": "tok"}},
        ))
        row = _scan_all()[0]
        assert row["detail"]["id"] == "srv1"
        assert row["detail"]["url"] == _MASK
        assert row["detail"]["headers"] == _MASK
        assert "secret" not in repr(row["detail"])


# --------------------------------------------------------------------------
# TABLE-MISSING — best-effort no-op, underlying op unaffected
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_log_table_missing_is_silent_noop_and_op_unaffected(ddb_env):
    """log() against an absent table swallows the error (no raise), and a
    simulated underlying operation runs to completion regardless."""
    with mock_aws():
        # NOTE: table deliberately NOT created.
        store = ActivityStore()
        op_ran = {"done": False}

        async def underlying_op():
            # The audit log is best-effort: even if it explodes internally, the
            # op must proceed. log() returns None and never raises.
            await store.log(actor="admin", type="login", detail={"username": "admin"})
            op_ran["done"] = True
            return "ok"

        result = asyncio.run(underlying_op())
        assert result == "ok"
        assert op_ran["done"] is True


@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_query_table_missing_returns_empty(ddb_env):
    with mock_aws():
        store = ActivityStore()  # no table
        out = asyncio.run(store.query())
        assert out == {"items": [], "cursor": None}


# --------------------------------------------------------------------------
# query() — filter + newest-first + paginate
# --------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_query_filters_and_orders_newest_first(ddb_env):
    with mock_aws():
        _create_activity_table()
        store = ActivityStore()
        # Write several rows on today's partition; spacing the epoch_ms so
        # ts_id ordering is deterministic.
        for i in range(5):
            asyncio.run(store.log(
                actor=("alice" if i % 2 == 0 else "bob"),
                type=("login" if i < 3 else "logout"),
                target=f"t{i}",
                detail={"username": "alice" if i % 2 == 0 else "bob"},
            ))
            time.sleep(0.005)  # ensure distinct epoch_ms

        # No filter: all 5, newest-first (descending ts).
        out = asyncio.run(store.query())
        items = out["items"]
        assert len(items) == 5
        ts_list = [it["ts"] for it in items]
        assert ts_list == sorted(ts_list, reverse=True), "not newest-first"

        # Filter by actor.
        alice = asyncio.run(store.query(actor="alice"))
        assert {it["actor"] for it in alice["items"]} == {"alice"}
        assert len(alice["items"]) == 3  # i=0,2,4

        # Filter by type.
        logout = asyncio.run(store.query(type="logout"))
        assert {it["type"] for it in logout["items"]} == {"logout"}
        assert len(logout["items"]) == 2  # i=3,4


@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_query_paginates_via_cursor(ddb_env):
    with mock_aws():
        _create_activity_table()
        store = ActivityStore()
        for i in range(5):
            asyncio.run(store.log(actor="admin", type="login", target=f"t{i}",
                                  detail={"username": "admin"}))
            time.sleep(0.005)

        page1 = asyncio.run(store.query(limit=2))
        assert len(page1["items"]) == 2
        assert page1["cursor"] is not None

        page2 = asyncio.run(store.query(limit=2, cursor=page1["cursor"]))
        assert len(page2["items"]) == 2

        page3 = asyncio.run(store.query(limit=2, cursor=page2["cursor"]))
        assert len(page3["items"]) == 1
        assert page3["cursor"] is None

        # No row repeated across pages; full set covered; strictly descending.
        all_ts = [it["ts"] for it in page1["items"] + page2["items"] + page3["items"]]
        assert len(set(all_ts)) == 5
        assert all_ts == sorted(all_ts, reverse=True)


@pytest.mark.skipif(not _HAVE_MOTO, reason="moto not installed")
def test_query_date_range_excludes_out_of_window(ddb_env):
    """A row whose day partition is outside [from,to] is not returned."""
    with mock_aws():
        _create_activity_table()
        store = ActivityStore()
        asyncio.run(store.log(actor="admin", type="login", detail={"username": "admin"}))
        # Window entirely in the past (yesterday and before) → no today rows.
        from datetime import datetime, timezone, timedelta
        today = datetime.now(timezone.utc)
        y = (today - timedelta(days=1)).strftime("%Y-%m-%d")
        past = (today - timedelta(days=5)).strftime("%Y-%m-%d")
        out = asyncio.run(store.query(day_from=past, day_to=y))
        assert out["items"] == []
        # Today included → row appears.
        td = today.strftime("%Y-%m-%d")
        out2 = asyncio.run(store.query(day_from=past, day_to=td))
        assert len(out2["items"]) == 1
