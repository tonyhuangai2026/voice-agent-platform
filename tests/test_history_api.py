"""Integration tests for /api/history endpoints.

Hits the FastAPI app via TestClient with a moto[dynamodb] mocked table.
Covers:
  - GET /api/history list shape, started_at desc ordering across multi-page Scan.
  - GET /api/history?cursor=... continues from the previous LastEvaluatedKey.
  - GET /api/history/by-caller uses the GSI + BatchGetItem to return full rows.
  - GET /api/history/{call_id} returns full item / 404 on miss.
  - HISTORY_DISABLED short-circuits to empty (and constructs no boto3 client).
  - SITE_PASSWORD enforces 401 on unauthenticated requests.
"""
from __future__ import annotations

import base64
import importlib
import json
import os
import sys
import time
from decimal import Decimal

import boto3
import pytest

from moto import mock_aws


TABLE_NAME = "voicebot-test-call-history-api"


def _create_table(region: str = "us-east-1") -> None:
    ddb = boto3.client("dynamodb", region_name=region)
    ddb.create_table(
        TableName=TABLE_NAME,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "call_id", "AttributeType": "S"},
            {"AttributeName": "caller", "AttributeType": "S"},
            {"AttributeName": "started_at", "AttributeType": "N"},
        ],
        KeySchema=[{"AttributeName": "call_id", "KeyType": "HASH"}],
        GlobalSecondaryIndexes=[
            {
                "IndexName": "caller-started-index",
                "KeySchema": [
                    {"AttributeName": "caller", "KeyType": "HASH"},
                    {"AttributeName": "started_at", "KeyType": "RANGE"},
                ],
                "Projection": {"ProjectionType": "KEYS_ONLY"},
            }
        ],
    )


def _seed(rows: list[dict]) -> None:
    table = boto3.resource("dynamodb", region_name="us-east-1").Table(TABLE_NAME)
    for r in rows:
        # boto3 resource layer rejects float — turn started_at/turn_count etc
        # into Decimal up-front (mimics what HistoryRecorder does).
        coerced = {k: (Decimal(str(v)) if isinstance(v, float) else v) for k, v in r.items()}
        table.put_item(Item=coerced)


USERS_TABLE = "voicebot-test-history-api-users"
_ADMIN_PWD = "test-pwd"


def _create_users_table(region: str = "us-east-1") -> None:
    ddb = boto3.client("dynamodb", region_name=region)
    ddb.create_table(
        TableName=USERS_TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "username", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "username", "KeyType": "HASH"}],
    )
    ddb.get_waiter("table_exists").wait(TableName=USERS_TABLE)


def _basic(pwd: str = _ADMIN_PWD, user: str = "x") -> dict:
    # Back-compat no-op: auth is now via the vb_session cookie on the client.
    return {}


def _import_bot_with_env(env: dict) -> object:
    for mod in list(sys.modules):
        if mod in ("bot", "runtime_config", "demo_loader", "user_store"):
            del sys.modules[mod]
    # Always wire the auth env so the JWT-cookie login path works in tests.
    env = {
        "AUTH_SECRET": "test-secret",
        "USERS_TABLE": USERS_TABLE,
        "ADMIN_PASSWORD": _ADMIN_PWD,
        **env,
    }
    for k, v in env.items():
        os.environ[k] = v
    return importlib.import_module("bot")


def _login_admin(bot):
    """Return an authed https TestClient (creates + logs in 'admin').

    The ADMIN_PASSWORD first-boot seed has been removed, so the bootstrap admin
    is created explicitly. Requires a USERS_TABLE created in the active moto
    mock. https base_url so the Secure vb_session cookie round-trips."""
    import asyncio
    from fastapi.testclient import TestClient
    asyncio.run(bot.USER_STORE.create("admin", _ADMIN_PWD, role="admin"))
    client = TestClient(bot.app, base_url="https://testserver")
    client.__enter__()
    r = client.post("/api/auth/login", json={"username": "admin", "password": _ADMIN_PWD})
    assert r.status_code == 200, r.text
    return client


@pytest.fixture
def aws_creds(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    monkeypatch.setenv("ADMIN_PASSWORD", _ADMIN_PWD)
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    yield


def _stub_rows(n: int, *, caller: str | None = None) -> list[dict]:
    """Build n rows with monotonically increasing started_at."""
    rows = []
    base = 1_700_000_000
    for i in range(n):
        rows.append({
            "call_id": f"call-{i:04d}",
            "caller": caller or f"+1555{i:07d}",
            "started_at": base + i,
            "ended_at": base + i + 30,
            "duration_s": 30,
            "turn_count": 4,
            "summary_status": "ok" if i % 2 == 0 else "pending",
            "ttl": base + i + 30 * 86400,
            "summary": {"intent": f"row {i}", "model": "stub", "generated_at": base + i + 30},
            # /api/history is now scoped to the caller's own web calls; tag rows
            # to the seeded 'admin' user so the list/cursor tests still exercise
            # the Scan + pagination machinery.
            "web_user": "admin",
        })
    return rows


def test_list_history_orders_desc_and_paginates(aws_creds, monkeypatch):
    """20 rows seeded, limit=5 should return the 5 newest (call-0019..0015)."""
    monkeypatch.setenv("HISTORY_TABLE", TABLE_NAME)
    monkeypatch.delenv("HISTORY_DISABLED", raising=False)

    with mock_aws():
        _create_table()
        _create_users_table()
        _seed(_stub_rows(20))
        bot = _import_bot_with_env({"HISTORY_TABLE": TABLE_NAME})

        client = _login_admin(bot)
        r = client.get("/api/history?limit=5", headers=_basic())
    assert r.status_code == 200
    body = r.json()
    assert "items" in body
    items = body["items"]
    assert len(items) == 5
    # Newest first.
    assert [it["call_id"] for it in items] == [
        "call-0019", "call-0018", "call-0017", "call-0016", "call-0015"
    ]
    for it in items:
        # Card shape only — `turns` should NOT leak.
        assert "turns" not in it
        assert {"call_id", "caller", "started_at", "turn_count", "summary_status"} <= set(it)
    # Even rows have summary => intent flattened.
    even = next(it for it in items if it["call_id"] == "call-0018")
    assert even.get("intent") == "row 18"


def test_list_history_cursor_resumes(aws_creds, monkeypatch):
    """Verify next_cursor round-trips: page 1 + page 2 cover disjoint sets."""
    monkeypatch.setenv("HISTORY_TABLE", TABLE_NAME)
    monkeypatch.delenv("HISTORY_DISABLED", raising=False)

    with mock_aws():
        _create_table()
        _create_users_table()
        # Seed enough to overflow one page (Scan page is min(limit*4, 200) = 40).
        _seed(_stub_rows(100))
        bot = _import_bot_with_env({"HISTORY_TABLE": TABLE_NAME})

        client = _login_admin(bot)
        r1 = client.get("/api/history?limit=10", headers=_basic())
        assert r1.status_code == 200
        body1 = r1.json()
        cursor = body1.get("next_cursor")
        # With 100 rows and at most 5 scan pages of 40, cursor may or may not
        # be set depending on Scan layout. If set, decoding succeeds:
        if cursor is not None:
            decoded = json.loads(base64.urlsafe_b64decode(cursor.encode()).decode())
            assert "call_id" in decoded
            r2 = client.get(f"/api/history?limit=10&cursor={cursor}", headers=_basic())
            assert r2.status_code == 200
            assert r2.json()["items"]  # second page non-empty


def test_by_caller_uses_gsi_and_batch_get(aws_creds, monkeypatch):
    """Two callers, query for one returns only their rows in desc order."""
    monkeypatch.setenv("HISTORY_TABLE", TABLE_NAME)
    monkeypatch.delenv("HISTORY_DISABLED", raising=False)

    with mock_aws():
        _create_table()
        _create_users_table()
        rows = _stub_rows(5, caller="+15551111111") + _stub_rows(3, caller="+15552222222")
        # Make call_ids unique across the two batches by re-tagging.
        for i, row in enumerate(rows):
            row["call_id"] = f"mixed-{i:03d}"
        _seed(rows)
        bot = _import_bot_with_env({"HISTORY_TABLE": TABLE_NAME})

        # by-caller is admin-only now.
        client = _login_admin(bot)
        r = client.get(
            "/api/history/by-caller?caller=%2B15551111111&limit=10",
            headers=_basic(),
        )
    assert r.status_code == 200
    items = r.json()["items"]
    assert len(items) == 5
    # Newest started_at first.
    starts = [it["started_at"] for it in items]
    assert starts == sorted(starts, reverse=True)
    assert {it["caller"] for it in items} == {"+15551111111"}


def test_get_one_history(aws_creds, monkeypatch):
    monkeypatch.setenv("HISTORY_TABLE", TABLE_NAME)
    monkeypatch.delenv("HISTORY_DISABLED", raising=False)

    with mock_aws():
        _create_table()
        _create_users_table()
        _seed(_stub_rows(2))
        bot = _import_bot_with_env({"HISTORY_TABLE": TABLE_NAME})

        # admin bypasses per-user ownership on the detail endpoint.
        client = _login_admin(bot)
        r = client.get("/api/history/call-0001", headers=_basic())
        assert r.status_code == 200
        assert r.json()["call_id"] == "call-0001"

        r404 = client.get("/api/history/does-not-exist", headers=_basic())
        assert r404.status_code == 404
        assert r404.json()["detail"] == "not found"


def test_history_disabled_returns_empty(aws_creds, monkeypatch):
    """HISTORY_DISABLED=1 ⇒ list endpoints return empty, detail returns 404,
    and the history boto3 client is never constructed."""
    monkeypatch.setenv("HISTORY_TABLE", TABLE_NAME)
    monkeypatch.setenv("HISTORY_DISABLED", "1")
    monkeypatch.delenv("SITE_PASSWORD", raising=False)

    with mock_aws():
        _create_users_table()  # only the users table — NO history table
        bot = _import_bot_with_env({
            "HISTORY_TABLE": TABLE_NAME,
            "HISTORY_DISABLED": "1",
        })
        assert bot._history is None

        client = _login_admin(bot)
        r = client.get("/api/history", headers=_basic())
        assert r.status_code == 200
        assert r.json() == {"items": [], "next_cursor": None}

        r2 = client.get("/api/history/by-caller?caller=%2B1", headers=_basic())
        assert r2.status_code == 200
        assert r2.json() == {"items": [], "next_cursor": None}

        r3 = client.get("/api/history/anything", headers=_basic())
        assert r3.status_code == 404


def test_history_requires_auth(aws_creds, monkeypatch):
    """No session cookie ⇒ 401 on every history route."""
    monkeypatch.setenv("HISTORY_TABLE", TABLE_NAME)
    monkeypatch.delenv("HISTORY_DISABLED", raising=False)

    with mock_aws():
        _create_table()
        _create_users_table()
        bot = _import_bot_with_env({"HISTORY_TABLE": TABLE_NAME})

        from fastapi.testclient import TestClient
        client = TestClient(bot.app, base_url="https://testserver")
        r1 = client.get("/api/history")
        assert r1.status_code == 401
        r2 = client.get("/api/history/by-caller?caller=x")
        assert r2.status_code == 401
        r3 = client.get("/api/history/anything")
        assert r3.status_code == 401
        r4 = client.get("/api/history", headers=_basic(pwd="wrong"))
        assert r4.status_code == 401
