"""Tests for voice_store.VoiceStore (T2) — DDB-backed editable voice registry.

Coverage (AC#5):
  - seed_if_empty writes the in-code constants ONCE on an empty live table and
    is idempotent (a non-empty table is never re-seeded).
  - put -> rescan -> get/list CRUD round-trip across all three providers, incl.
    a numeric MiniMax boost surviving the Decimal round-trip.
  - delete removes one item.
  - Table-missing degrades: rescan() returns -1, live stays False, get()->None,
    list()->{} — no raise (the lazy table accessor never touches AWS at ctor).

bot-level fallback (table-missing -> voices_for returns constants, resolver
byte-identical; deleted voice -> provider default; nova alias) is covered in
tests/test_admin_api.py where the bot module + FastAPI app are in scope.

DynamoDB is mocked with moto (mock_aws). The pure table-missing + empty-cache
paths run without a live table.
"""

from __future__ import annotations

import asyncio

import boto3
import pytest

try:
    from moto import mock_aws
    _HAVE_MOTO = True
except Exception:  # pragma: no cover — env without moto
    _HAVE_MOTO = False

from voice_store import VoiceStore

VOICES_TABLE = "voicebot-test-voices"


@pytest.fixture
def ddb_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("VOICES_TABLE", VOICES_TABLE)
    yield


def _create_voices_table(region: str = "us-east-1") -> None:
    ddb = boto3.client("dynamodb", region_name=region)
    ddb.create_table(
        TableName=VOICES_TABLE,
        BillingMode="PAY_PER_REQUEST",
        AttributeDefinitions=[
            {"AttributeName": "provider", "AttributeType": "S"},
            {"AttributeName": "voice_id", "AttributeType": "S"},
        ],
        KeySchema=[
            {"AttributeName": "provider", "KeyType": "HASH"},
            {"AttributeName": "voice_id", "KeyType": "RANGE"},
        ],
    )
    ddb.get_waiter("table_exists").wait(TableName=VOICES_TABLE)


# A tiny constants map mirroring the three in-code dict shapes.
SAMPLE_CONSTANTS = {
    "minimax": {
        "Cantonese_GentleLady": {"label": "Gentle Lady", "gender": "F", "language": "zh-HK", "boost": "Cantonese"},
        "English_Graceful_Lady": {"label": "Graceful Lady", "gender": "F", "language": "en-US", "boost": "English"},
    },
    "polly": {
        "Zhiyu": {"label": "Zhiyu", "gender": "F", "language": "zh-CN", "engine": "neural"},
    },
    "nova-sonic": {
        "tiffany": {"label": "Tiffany", "gender": "F", "locale": "en-US", "lang_label": "English (US)", "polyglot": True},
        "ambre": {"label": "Ambre", "gender": "F", "locale": "fr-FR", "lang_label": "Français", "polyglot": False},
    },
}


# ---------------------------------------------------------------------------
# Lazy accessor / empty-cache tolerance — no AWS at all.
# ---------------------------------------------------------------------------

def test_ctor_is_lazy_and_empty_cache_safe(ddb_env):
    """Constructing a VoiceStore never touches AWS; reads on an unprewarmed
    store return empty/None and `live` starts False."""
    store = VoiceStore(table_name=VOICES_TABLE)
    assert store.live is False
    assert store.get("minimax", "anything") is None
    assert store.list("minimax") == {}
    assert store.list() == {"minimax": {}, "polly": {}, "nova-sonic": {}}


# ---------------------------------------------------------------------------
# Table-missing degrade — moto scopes an empty AWS env; NO table created.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_MOTO, reason="moto unavailable")
def test_missing_table_degrades(ddb_env):
    async def run():
        store = VoiceStore(table_name=VOICES_TABLE)
        n = await store.rescan()
        assert n == -1  # explicit not-live signal
        assert store.live is False
        assert store.get("minimax", "x") is None
        assert store.list("minimax") == {}
        assert store.last_skipped and "missing" in store.last_skipped[0]["reason"]

    with mock_aws():
        asyncio.run(run())


@pytest.mark.skipif(not _HAVE_MOTO, reason="moto unavailable")
def test_seed_noop_when_table_missing(ddb_env):
    async def run():
        store = VoiceStore(table_name=VOICES_TABLE)
        written = await store.seed_if_empty(SAMPLE_CONSTANTS)
        assert written == 0
        assert store.live is False

    with mock_aws():
        asyncio.run(run())


# ---------------------------------------------------------------------------
# seed-on-empty + idempotency.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_MOTO, reason="moto unavailable")
def test_seed_if_empty_writes_constants_once(ddb_env):
    async def run():
        store = VoiceStore(table_name=VOICES_TABLE)
        written = await store.seed_if_empty(SAMPLE_CONSTANTS)
        assert written == 5  # 2 minimax + 1 polly + 2 nova
        assert store.live is True
        # Cache reflects the seeded rows, byte-identical attr shape.
        assert store.get("minimax", "Cantonese_GentleLady")["boost"] == "Cantonese"
        assert store.get("polly", "Zhiyu")["engine"] == "neural"
        assert store.get("nova-sonic", "tiffany")["polyglot"] is True

        # Idempotent: a non-empty live table is never re-seeded.
        again = await store.seed_if_empty(SAMPLE_CONSTANTS)
        assert again == 0

    with mock_aws():
        _create_voices_table()
        asyncio.run(run())


@pytest.mark.skipif(not _HAVE_MOTO, reason="moto unavailable")
def test_seed_not_reinjected_after_full_delete(ddb_env):
    """Deleting every voice then re-seeding still re-injects (table empty again)
    — but a partially-populated table is NOT re-seeded."""
    async def run():
        store = VoiceStore(table_name=VOICES_TABLE)
        await store.seed_if_empty(SAMPLE_CONSTANTS)
        # Delete all but one nova voice -> table non-empty -> no re-seed.
        await store.delete("minimax", "Cantonese_GentleLady")
        await store.delete("minimax", "English_Graceful_Lady")
        await store.delete("polly", "Zhiyu")
        await store.delete("nova-sonic", "ambre")
        again = await store.seed_if_empty(SAMPLE_CONSTANTS)
        assert again == 0  # still has tiffany -> not empty -> no re-seed

    with mock_aws():
        _create_voices_table()
        asyncio.run(run())


# ---------------------------------------------------------------------------
# CRUD round-trip incl. numeric boost Decimal round-trip.
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not _HAVE_MOTO, reason="moto unavailable")
def test_put_get_delete_roundtrip(ddb_env):
    async def run():
        store = VoiceStore(table_name=VOICES_TABLE)
        await store.put("minimax", "custom_voice_1", {"label": "Custom", "gender": "M", "language": "en-US", "boost": 1.5})
        await store.put("polly", "Joanna", {"label": "Joanna", "gender": "F", "language": "en-US", "engine": "generative"})
        n = await store.rescan()
        assert n == 2
        assert store.live is True

        mm = store.get("minimax", "custom_voice_1")
        assert mm["label"] == "Custom"
        # Numeric boost survives the Decimal round-trip as a plain float.
        assert mm["boost"] == 1.5 and isinstance(mm["boost"], float)
        # Cached attrs DO NOT carry the key columns.
        assert "provider" not in mm and "voice_id" not in mm

        # list(provider) shape == {voice_id: attrs}; list() nested.
        assert set(store.list("minimax").keys()) == {"custom_voice_1"}
        assert set(store.list().keys()) == {"minimax", "polly", "nova-sonic"}

        # delete -> rescan -> gone.
        await store.delete("minimax", "custom_voice_1")
        await store.rescan()
        assert store.get("minimax", "custom_voice_1") is None
        assert store.get("polly", "Joanna") is not None

    with mock_aws():
        _create_voices_table()
        asyncio.run(run())


@pytest.mark.skipif(not _HAVE_MOTO, reason="moto unavailable")
def test_put_requires_keys(ddb_env):
    async def run():
        store = VoiceStore(table_name=VOICES_TABLE)
        with pytest.raises(ValueError):
            await store.put("", "x", {})
        with pytest.raises(ValueError):
            await store.put("minimax", "", {})

    with mock_aws():
        _create_voices_table()
        asyncio.run(run())
