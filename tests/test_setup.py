"""Tests for the first-run admin setup backend (T1).

Covers:
  - _needs_setup(): empty table -> True; with a user -> False.
  - GET /api/auth/setup-status: PUBLIC (no cookie), empty -> {needs_setup:true},
    with an admin -> false; returns only the bool (no user info).
  - POST /api/auth/setup: empty table -> creates a role=admin user, sets the
    session cookie (auto-login), and a subsequent /api/auth/me succeeds;
    empty username/password -> 400; with an existing user -> 409 and the
    existing account is left unchanged.
  - CONCURRENCY: a botocore ClientError(ConditionalCheckFailedException) raised
    by the conditional write must map to 409, never 500.
  - user_store.create() normalization: a ConditionalCheckFailedException from
    put_item surfaces as ValueError("... already exists").
  - Dropped seed: even with ADMIN_PASSWORD set, after startup the table is NOT
    seeded.

DynamoDB is mocked with moto; each test gets a fresh per-test users table and a
freshly re-imported module so the module-level USER_STORE binds to that table.
bcrypt + PyJWT are real. https base_url lets the Secure vb_session cookie
round-trip through TestClient.
"""

from __future__ import annotations

import asyncio
import importlib
import sys

import boto3
import pytest
from botocore.exceptions import ClientError
from moto import mock_aws

USERS_TABLE = "voicebot-test-setup-users"
_ADMIN_PWD = "seed-pwd-from-env"


def _create_users_table(region: str = "us-east-1") -> None:
    ddb = boto3.client("dynamodb", region_name=region)
    ddb.create_table(
        TableName=USERS_TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[{"AttributeName": "username", "AttributeType": "S"}],
        KeySchema=[{"AttributeName": "username", "KeyType": "HASH"}],
    )
    ddb.get_waiter("table_exists").wait(TableName=USERS_TABLE)


@pytest.fixture
def setup_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    monkeypatch.setenv("AUTH_SECRET", "unit-test-secret-key-32-bytes-long!!")
    monkeypatch.setenv("USERS_TABLE", USERS_TABLE)
    # ADMIN_PASSWORD is intentionally set: the seed must be a no-op anyway.
    monkeypatch.setenv("ADMIN_PASSWORD", _ADMIN_PWD)
    yield


def _fresh_user_store():
    for mod in ("user_store",):
        sys.modules.pop(mod, None)
    return importlib.import_module("user_store")


def _import_bot():
    for mod in ("bot", "runtime_config", "demo_loader", "user_store"):
        sys.modules.pop(mod, None)
    return importlib.import_module("bot")


def _anon_client(bot):
    """Anonymous https TestClient (runs startup; no cookie set)."""
    from fastapi.testclient import TestClient

    client = TestClient(bot.app, base_url="https://testserver")
    client.__enter__()
    return client


# ---------------------------------------------------------------------------
# _needs_setup
# ---------------------------------------------------------------------------

def test_needs_setup_empty_then_populated(setup_env):
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        # empty table -> True
        assert asyncio.run(bot._needs_setup()) is True
        # with a user -> False
        asyncio.run(bot.USER_STORE.create("admin", "pw", role="admin"))
        assert asyncio.run(bot._needs_setup()) is False


# ---------------------------------------------------------------------------
# GET /api/auth/setup-status  (PUBLIC)
# ---------------------------------------------------------------------------

def test_setup_status_public_empty_true(setup_env):
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        anon = _anon_client(bot)
        # No cookie at all -> still callable (public).
        r = anon.get("/api/auth/setup-status")
        assert r.status_code == 200, r.text
        # Returns ONLY the bool, no user info.
        assert r.json() == {"needs_setup": True}


def test_setup_status_public_with_admin_false(setup_env):
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        asyncio.run(bot.USER_STORE.create("admin", "pw", role="admin"))
        anon = _anon_client(bot)
        r = anon.get("/api/auth/setup-status")
        assert r.status_code == 200, r.text
        assert r.json() == {"needs_setup": False}


# ---------------------------------------------------------------------------
# POST /api/auth/setup
# ---------------------------------------------------------------------------

def test_setup_creates_admin_and_auto_logs_in(setup_env):
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        anon = _anon_client(bot)

        r = anon.post("/api/auth/setup", json={"username": "owner", "password": "strong-pw"})
        assert r.status_code == 200, r.text
        assert r.json() == {"username": "owner", "role": "admin"}
        # Auto-login: the session cookie was set...
        assert "vb_session" in anon.cookies
        # ...and a subsequent /api/auth/me succeeds with that cookie.
        me = anon.get("/api/auth/me")
        assert me.status_code == 200, me.text
        assert me.json() == {"username": "owner", "role": "admin"}
        # The created account really is an admin in the store.
        users = asyncio.run(bot.USER_STORE.list())
        assert [u["username"] for u in users] == ["owner"]
        assert users[0]["role"] == "admin"
        # setup-status now reports initialized.
        assert anon.get("/api/auth/setup-status").json() == {"needs_setup": False}


def test_setup_empty_username_or_password_400(setup_env):
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        anon = _anon_client(bot)

        assert anon.post("/api/auth/setup", json={"username": "", "password": "pw"}).status_code == 400
        assert anon.post("/api/auth/setup", json={"username": "owner", "password": ""}).status_code == 400
        assert anon.post("/api/auth/setup", json={"username": "   ", "password": "pw"}).status_code == 400
        assert anon.post("/api/auth/setup", json={}).status_code == 400
        # Nothing was created.
        assert asyncio.run(bot.USER_STORE.list()) == []


def test_setup_self_closes_when_user_exists_409(setup_env):
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        # Pre-existing admin with a known password.
        asyncio.run(bot.USER_STORE.create("existing", "original-pw", role="admin"))
        anon = _anon_client(bot)

        r = anon.post("/api/auth/setup", json={"username": "intruder", "password": "new-pw"})
        assert r.status_code == 409, r.text
        # No cookie issued (no auto-login on the closed path).
        assert "vb_session" not in anon.cookies
        # Existing account is UNCHANGED: still the same single user, password intact.
        users = asyncio.run(bot.USER_STORE.list())
        assert [u["username"] for u in users] == ["existing"]
        assert asyncio.run(bot.USER_STORE.verify("existing", "original-pw")) is not None
        # The would-be new account does not exist.
        assert asyncio.run(bot.USER_STORE.get("intruder")) is None


# ---------------------------------------------------------------------------
# CONCURRENCY: conditional-write race -> 409, never 500
# ---------------------------------------------------------------------------

def _conditional_check_failed() -> ClientError:
    return ClientError(
        {"Error": {"Code": "ConditionalCheckFailedException", "Message": "The conditional request failed"}},
        "PutItem",
    )


def test_setup_concurrent_loser_maps_to_409_not_500(setup_env):
    """Simulate the TOCTOU window: _needs_setup() sees an empty table, but by
    the time create() runs another request has won. create() must raise (the
    normalized ValueError) and the endpoint must return 409, never 500."""
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        anon = _anon_client(bot)

        async def _boom(*a, **k):
            raise _conditional_check_failed()

        # Patch the store's create to raise the raw botocore error. Even if
        # create's own normalization were bypassed, the endpoint's
        # defense-in-depth ClientError catch must still produce 409.
        bot.USER_STORE.create = _boom  # type: ignore[assignment]
        r = anon.post("/api/auth/setup", json={"username": "owner", "password": "pw"})
        assert r.status_code == 409, r.text


def test_setup_concurrent_loser_via_normalized_valueerror_409(setup_env):
    """create() normalizes the conditional-write failure to ValueError; the
    endpoint's ValueError branch must map that to 409 (not 500)."""
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        anon = _anon_client(bot)

        async def _dup(*a, **k):
            raise ValueError("user 'owner' already exists")

        bot.USER_STORE.create = _dup  # type: ignore[assignment]
        r = anon.post("/api/auth/setup", json={"username": "owner", "password": "pw"})
        assert r.status_code == 409, r.text


# ---------------------------------------------------------------------------
# user_store.create() normalization
# ---------------------------------------------------------------------------

def test_create_normalizes_conditional_check_failed_to_valueerror(setup_env, monkeypatch):
    """A ConditionalCheckFailedException from put_item must surface as the same
    ValueError('... already exists') as the _get_raw pre-check, so callers only
    ever handle ValueError."""
    us = _fresh_user_store()

    async def run():
        store = us.UserStore()
        table = store._get_table()

        # Force put_item to raise the conditional-check failure (simulating a
        # concurrent winner) while _get_raw still reports the row absent.
        def _raise_conditional(**kwargs):
            raise _conditional_check_failed()

        monkeypatch.setattr(table, "put_item", _raise_conditional)

        with pytest.raises(ValueError) as exc:
            await store.create("racer", "pw", role="admin")
        assert "already exists" in str(exc.value)

    with mock_aws():
        _create_users_table()
        asyncio.run(run())


def test_create_reraises_other_client_errors(setup_env, monkeypatch):
    """A non-conditional ClientError from put_item must NOT be swallowed as a
    ValueError — it should propagate so genuine failures aren't masked."""
    us = _fresh_user_store()

    async def run():
        store = us.UserStore()
        table = store._get_table()

        def _raise_other(**kwargs):
            raise ClientError(
                {"Error": {"Code": "ProvisionedThroughputExceededException", "Message": "slow down"}},
                "PutItem",
            )

        monkeypatch.setattr(table, "put_item", _raise_other)

        with pytest.raises(ClientError):
            await store.create("racer", "pw", role="admin")

    with mock_aws():
        _create_users_table()
        asyncio.run(run())


def test_list_reraises_access_denied_not_empty(setup_env, monkeypatch):
    """user_store.list() must NOT swallow AccessDenied as an empty table — that
    would make _needs_setup() wrongly report needs_setup=true on an
    initialized-but-misconfigured deploy. Only a missing table degrades to []."""
    us = _fresh_user_store()

    async def run():
        store = us.UserStore()
        table = store._get_table()

        def _denied(**kwargs):
            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "no policy"}},
                "Scan",
            )

        monkeypatch.setattr(table, "scan", _denied)
        with pytest.raises(ClientError):
            await store.list()

    with mock_aws():
        _create_users_table()
        asyncio.run(run())


def test_setup_status_503_when_user_store_errors(setup_env, monkeypatch):
    """When list() raises (e.g. AccessDenied), GET /api/auth/setup-status must
    return 503 — never a wrong {needs_setup:true} that would send an
    initialized deploy to the /setup wizard."""
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        anon = _anon_client(bot)

        async def _boom():
            raise ClientError(
                {"Error": {"Code": "AccessDeniedException", "Message": "no policy"}},
                "Scan",
            )

        bot.USER_STORE.list = _boom  # type: ignore[assignment]
        r = anon.get("/api/auth/setup-status")
        assert r.status_code == 503, r.text


# ---------------------------------------------------------------------------
# Dropped ADMIN_PASSWORD seed
# ---------------------------------------------------------------------------

def test_seed_dropped_startup_does_not_create_user(setup_env):
    """Even with ADMIN_PASSWORD set in the env, going through app startup (which
    no longer registers a seed hook) leaves the table empty."""
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        assert bot.ADMIN_PASSWORD == _ADMIN_PWD  # env value is read...
        anon = _anon_client(bot)  # __enter__ runs FastAPI startup
        # ...but no user was seeded.
        assert asyncio.run(bot.USER_STORE.list()) == []
        # And setup-status correctly reports the deploy still needs setup.
        assert anon.get("/api/auth/setup-status").json() == {"needs_setup": True}


def test_seed_admin_helper_is_noop(setup_env):
    """Direct call to the deprecated _seed_admin() no-op creates nothing."""
    with mock_aws():
        _create_users_table()
        bot = _import_bot()
        asyncio.run(bot._seed_admin())
        assert asyncio.run(bot.USER_STORE.list()) == []
