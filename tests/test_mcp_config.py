"""Unit tests for mcp_config.McpConfig — CRUD, validation, atomic writes.

Covers task 1ac6a539 AC #1:
- list/get/upsert/delete round-trip
- validation rejects stdio transport, bad ids, non-http(s) urls
- "***" header sentinel preserves the previously stored value
- writes are atomic (tempfile + os.replace; failed write leaves the old
  file intact and no temp litter)
- corrupt / missing file degrades to an empty registry (no crash)
"""

from __future__ import annotations

import json
import os
import threading

import pytest

from mcp_config import (
    HEADER_MASK,
    McpConfig,
    mask_headers,
    validate_auth,
    validate_server,
)


def _server(**overrides):
    base = {
        "id": "weather-api",
        "label": "Weather API",
        "transport": "streamable_http",
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer secret-token"},
        "enabled": True,
    }
    base.update(overrides)
    return base


@pytest.fixture
def cfg(tmp_path):
    return McpConfig(path=str(tmp_path / "config" / "mcp_servers.json"))


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------
def test_empty_registry_when_file_missing(cfg):
    assert cfg.list_servers() == []
    assert cfg.get("nope") is None


def test_upsert_insert_then_get(cfg):
    stored = cfg.upsert(_server())
    assert stored["id"] == "weather-api"
    assert stored["headers"] == {"Authorization": "Bearer secret-token"}
    got = cfg.get("weather-api")
    assert got is not None
    assert got["url"] == "https://example.com/mcp"
    assert got["enabled"] is True
    assert [s["id"] for s in cfg.list_servers()] == ["weather-api"]


def test_upsert_replaces_existing(cfg):
    cfg.upsert(_server())
    cfg.upsert(_server(url="https://other.example.com/mcp", label="Other"))
    servers = cfg.list_servers()
    assert len(servers) == 1
    assert servers[0]["url"] == "https://other.example.com/mcp"
    assert servers[0]["label"] == "Other"


def test_delete(cfg):
    cfg.upsert(_server())
    assert cfg.delete("weather-api") is True
    assert cfg.get("weather-api") is None
    assert cfg.delete("weather-api") is False  # already gone


def test_persistence_across_instances(tmp_path):
    path = str(tmp_path / "mcp_servers.json")
    McpConfig(path=path).upsert(_server())
    # Fresh instance reads the same file.
    fresh = McpConfig(path=path)
    assert fresh.get("weather-api")["label"] == "Weather API"


def test_label_defaults_to_id(cfg):
    stored = cfg.upsert(_server(label=None))
    assert stored["label"] == "weather-api"


def test_returned_dicts_are_copies(cfg):
    cfg.upsert(_server())
    got = cfg.get("weather-api")
    got["url"] = "https://mutated.example.com"
    got["headers"]["Authorization"] = "mutated"
    again = cfg.get("weather-api")
    assert again["url"] == "https://example.com/mcp"
    assert again["headers"]["Authorization"] == "Bearer secret-token"


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def test_rejects_stdio_transport(cfg):
    with pytest.raises(ValueError, match="stdio"):
        cfg.upsert(_server(transport="stdio"))


def test_rejects_unknown_transport(cfg):
    with pytest.raises(ValueError, match="transport"):
        cfg.upsert(_server(transport="websocket"))


@pytest.mark.parametrize(
    "bad_id",
    [
        "",  # empty
        "A-Upper",  # uppercase
        "-leading-dash",
        "under_score",
        "x",  # too short (min 2 chars)
        "a" * 64,  # too long (max 63)
        "café",  # non-ascii
        None,
        123,
    ],
)
def test_rejects_invalid_ids(cfg, bad_id):
    with pytest.raises(ValueError):
        cfg.upsert(_server(id=bad_id))


@pytest.mark.parametrize("good_id", ["ab", "weather-api", "a1-b2-c3", "0zero", "a" * 63])
def test_accepts_valid_ids(cfg, good_id):
    assert cfg.upsert(_server(id=good_id))["id"] == good_id


@pytest.mark.parametrize(
    "bad_url",
    [
        "",
        None,
        "ftp://example.com/mcp",
        "file:///etc/passwd",
        "example.com/mcp",  # no scheme
        "https://",  # no host
    ],
)
def test_rejects_non_http_urls(cfg, bad_url):
    with pytest.raises(ValueError):
        cfg.upsert(_server(url=bad_url))


def test_accepts_http_and_https(cfg):
    assert cfg.upsert(_server(id="srv-http", url="http://10.0.0.5:8080/mcp"))
    assert cfg.upsert(_server(id="srv-https", url="https://example.com/mcp"))


def test_rejects_non_dict_headers(cfg):
    with pytest.raises(ValueError, match="headers"):
        cfg.upsert(_server(headers=["not", "a", "dict"]))


def test_rejects_non_string_header_values(cfg):
    with pytest.raises(ValueError, match="header"):
        cfg.upsert(_server(headers={"X-Num": 42}))


def test_rejects_non_bool_enabled(cfg):
    with pytest.raises(ValueError, match="enabled"):
        cfg.upsert(_server(enabled="yes"))


def test_failed_validation_does_not_persist(cfg, tmp_path):
    with pytest.raises(ValueError):
        cfg.upsert(_server(transport="stdio"))
    assert cfg.list_servers() == []


def test_validate_server_is_pure():
    # Direct unit check of the canonicalisation helper.
    out = validate_server(_server(headers=None))
    assert out["headers"] == {}
    # ``auth`` is part of the canonical shape (defaults to {"type": "none"}).
    assert sorted(out.keys()) == ["auth", "enabled", "headers", "id", "label", "transport", "url"]
    assert out["auth"] == {"type": "none"}


# ---------------------------------------------------------------------------
# auth schema (none / header / sigv4) — backward compatible
# ---------------------------------------------------------------------------
def test_auth_defaults_to_none_when_missing():
    # Backward compat: a server with no auth field normalizes to none.
    out = validate_server(_server())
    assert out["auth"] == {"type": "none"}


def test_validate_auth_none_and_header():
    assert validate_auth(None) == {"type": "none"}
    assert validate_auth({"type": "none"}) == {"type": "none"}
    assert validate_auth({"type": "header"}) == {"type": "header"}


def test_validate_auth_sigv4_defaults():
    out = validate_auth({"type": "sigv4"})
    assert out == {"type": "sigv4", "service": "bedrock-agentcore", "region": "us-east-1"}


def test_validate_auth_sigv4_explicit():
    out = validate_auth({"type": "sigv4", "service": "lambda", "region": "eu-west-1"})
    assert out == {"type": "sigv4", "service": "lambda", "region": "eu-west-1"}


@pytest.mark.parametrize("bad_type", ["sigv5", "oauth", "", 123, "SIGV4"])
def test_validate_auth_rejects_bad_type(bad_type):
    with pytest.raises(ValueError, match="auth.type"):
        validate_auth({"type": bad_type})


def test_validate_auth_rejects_non_dict():
    with pytest.raises(ValueError, match="auth must be an object"):
        validate_auth("sigv4")


@pytest.mark.parametrize("bad", [{"type": "sigv4", "service": ""}, {"type": "sigv4", "service": 5}])
def test_validate_auth_sigv4_bad_service(bad):
    with pytest.raises(ValueError, match="service"):
        validate_auth(bad)


@pytest.mark.parametrize("bad", [{"type": "sigv4", "region": ""}, {"type": "sigv4", "region": 5}])
def test_validate_auth_sigv4_bad_region(bad):
    with pytest.raises(ValueError, match="region"):
        validate_auth(bad)


def test_upsert_rejects_bad_auth_type(cfg):
    with pytest.raises(ValueError, match="auth.type"):
        cfg.upsert(_server(auth={"type": "nope"}))


def test_sigv4_auth_survives_upsert_get_round_trip(cfg):
    """N2 regression: the canonical dict MUST keep ``auth`` — otherwise the
    sigv4 config is silently stripped on upsert and bot.py never sees it."""
    cfg.upsert(
        _server(
            id="connect-repair",
            headers={},
            auth={"type": "sigv4", "service": "bedrock-agentcore", "region": "us-east-1"},
        )
    )
    got = cfg.get("connect-repair")
    assert got["auth"] == {
        "type": "sigv4",
        "service": "bedrock-agentcore",
        "region": "us-east-1",
    }
    # Survives a fresh instance read (disk round-trip) too.
    listed = cfg.list_servers()
    assert listed[0]["auth"]["type"] == "sigv4"


def test_header_auth_survives_round_trip(cfg):
    cfg.upsert(_server(auth={"type": "header"}))
    assert cfg.get("weather-api")["auth"] == {"type": "header"}


# ---------------------------------------------------------------------------
# Header mask sentinel ("***")
# ---------------------------------------------------------------------------
def test_mask_headers_masks_every_value():
    masked = mask_headers(_server(headers={"Authorization": "s3cret", "X-Api-Key": "k"}))
    assert masked["headers"] == {"Authorization": HEADER_MASK, "X-Api-Key": HEADER_MASK}
    # Original untouched, other fields intact.
    assert masked["url"] == "https://example.com/mcp"


def test_mask_headers_handles_empty():
    masked = mask_headers(_server(headers={}))
    assert masked["headers"] == {}


def test_upsert_mask_sentinel_preserves_stored_value(cfg):
    cfg.upsert(_server(headers={"Authorization": "Bearer real-secret"}))
    # Re-upsert with the masked value (what the admin SPA round-trips).
    stored = cfg.upsert(_server(headers={"Authorization": HEADER_MASK}))
    assert stored["headers"]["Authorization"] == "Bearer real-secret"
    assert cfg.get("weather-api")["headers"]["Authorization"] == "Bearer real-secret"


def test_upsert_mask_sentinel_with_no_stored_value_drops_key(cfg):
    stored = cfg.upsert(_server(headers={"Authorization": HEADER_MASK}))
    assert "Authorization" not in stored["headers"]


def test_upsert_mixed_masked_and_new_headers(cfg):
    cfg.upsert(_server(headers={"Authorization": "keep-me", "X-Old": "old"}))
    stored = cfg.upsert(
        _server(headers={"Authorization": HEADER_MASK, "X-New": "fresh"})
    )
    assert stored["headers"] == {"Authorization": "keep-me", "X-New": "fresh"}
    # X-Old removed because the new payload didn't include it.
    assert "X-Old" not in stored["headers"]


# ---------------------------------------------------------------------------
# Atomicity / robustness
# ---------------------------------------------------------------------------
def test_write_leaves_no_temp_files(cfg, tmp_path):
    cfg.upsert(_server())
    cfg_dir = tmp_path / "config"
    leftovers = [p for p in os.listdir(cfg_dir) if p != "mcp_servers.json"]
    assert leftovers == []


def test_file_is_valid_json_after_write(cfg, tmp_path):
    cfg.upsert(_server())
    with open(tmp_path / "config" / "mcp_servers.json", encoding="utf-8") as f:
        data = json.load(f)
    assert data["servers"][0]["id"] == "weather-api"
    assert data["_meta"]["version"] == 1
    assert "updated_at" in data["_meta"]


def test_failed_write_keeps_previous_file_intact(cfg, tmp_path, monkeypatch):
    cfg.upsert(_server())
    path = tmp_path / "config" / "mcp_servers.json"
    before = path.read_text(encoding="utf-8")

    # Make the rename step blow up mid-write.
    def boom(*a, **k):
        raise OSError("disk on fire")

    monkeypatch.setattr(os, "replace", boom)
    with pytest.raises(OSError):
        cfg.upsert(_server(id="second-server"))
    monkeypatch.undo()

    # Old file content untouched + no temp litter.
    assert path.read_text(encoding="utf-8") == before
    leftovers = [p for p in os.listdir(tmp_path / "config") if p != "mcp_servers.json"]
    assert leftovers == []

    # A fresh instance still reads the original single server.
    fresh = McpConfig(path=str(path))
    assert [s["id"] for s in fresh.list_servers()] == ["weather-api"]


def test_corrupt_file_degrades_to_empty_registry(tmp_path):
    path = tmp_path / "mcp_servers.json"
    path.write_text("{not json", encoding="utf-8")
    cfg = McpConfig(path=str(path))
    assert cfg.list_servers() == []
    # And the registry is usable again after a write.
    cfg.upsert(_server())
    assert len(cfg.list_servers()) == 1


def test_concurrent_upserts_are_all_persisted(tmp_path):
    path = str(tmp_path / "mcp_servers.json")
    cfg = McpConfig(path=path)

    def worker(i):
        cfg.upsert(_server(id=f"srv-{i:02d}", headers={}))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    ids = sorted(s["id"] for s in cfg.list_servers())
    assert ids == [f"srv-{i:02d}" for i in range(8)]
    # File on disk agrees (no lost updates).
    fresh = McpConfig(path=path)
    assert sorted(s["id"] for s in fresh.list_servers()) == ids
