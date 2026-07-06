"""Admin REST tests for the MCP server registry (task 1ac6a539).

Covers:
- auth (401 without credentials) on every /api/admin/mcp-servers route
- GET masks header values as "***"
- POST upserts; POST with "***" header value preserves the stored secret
- POST validation errors -> 400 (stdio transport, bad id, bad url)
- DELETE -> 200; DELETE of a server referenced by a demo manifest -> 409
  with the referencing demo ids; DELETE unknown -> 404
- POST /{id}/test returns {ok, tools, error} (unreachable server -> ok=False,
  friendly error; unknown id -> 404)
- /api/admin/options exposes mcp_servers as [{id, label, enabled}]
- PATCH /api/admin/demos/{id} accepts mcp_servers and writes it back to
  manifest.yaml; demo detail / list surface the field
"""

from __future__ import annotations

import base64
import importlib
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def admin_env(tmp_path, monkeypatch):
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pwd")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    # Isolate the MCP registry file per-test (bot.py honours this override).
    monkeypatch.setenv("MCP_CFG_PATH_OVERRIDE", str(tmp_path / "mcp_servers.json"))
    yield


def _import_app():
    """Re-import bot.py fresh so module-level singletons see the env."""
    for mod in list(sys.modules):
        if mod in ("bot", "runtime_config", "demo_loader", "mcp_config", "user_store"):
            del sys.modules[mod]
    bot = importlib.import_module("bot")
    # Auth moved to JWT cookies; bypass require_user/require_admin so these
    # tests focus on MCP CRUD (auth itself is covered by test_auth.py).
    _admin = {"username": "admin", "role": "admin", "disabled": False, "created_at": 0}
    bot.app.dependency_overrides[bot.require_user] = lambda: _admin
    bot.app.dependency_overrides[bot.require_admin] = lambda: _admin
    return bot


def _basic(user: str = "admin", pwd: str = "test-pwd") -> dict[str, str]:
    # No-op: auth bypassed via dependency_overrides in _import_app.
    return {}


def _server_payload(**overrides):
    base = {
        "id": "weather-api",
        "label": "Weather API",
        "transport": "streamable_http",
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer real-secret"},
        "enabled": True,
    }
    base.update(overrides)
    return base


def _make_demo_dir(data_root: Path, demo_id: str, *, mcp_servers: list[str] | None = None):
    demo_dir = data_root / demo_id
    demo_dir.mkdir(parents=True)
    (demo_dir / "kb.md").write_text("kb body")
    extra = ""
    if mcp_servers is not None:
        lines = "".join(f"  - {m}\n" for m in mcp_servers)
        extra = f"mcp_servers:\n{lines}" if mcp_servers else "mcp_servers: []\n"
    (demo_dir / "manifest.yaml").write_text(
        f"id: {demo_id}\nlabel: {demo_id}\nlang: en-US\n"
        "system:\n  en-US: 'sys'\n"
        "greeting:\n  en-US: 'hi'\n"
        "kb_path: kb.md\n" + extra
    )
    return demo_dir


class _MemStore:
    """In-memory stand-in for the DDB-backed DemoStore, exposing the same
    interface the PATCH endpoint uses (get/list/rescan + async put). It avoids
    a real moto/DDB round-trip while still exercising the endpoint's
    merge → put → rescan path. ``put`` normalizes through the SAME shared
    helper as DemoStore so the canonical key shape (incl. ``tool_ids``) and
    full-set semantics match production exactly."""

    def __init__(self, data_root):
        from demo_loader import DemoLoader, normalize_demo_dict

        self._normalize = normalize_demo_dict
        self._cache = {
            demo_id: normalize_demo_dict(demo, validate_tools=False)
            for demo_id, demo in DemoLoader(str(data_root))._cache.items()
        }
        self.last_skipped = []

    def get(self, demo_id):
        return self._cache.get(demo_id)

    def list(self):
        from demo_loader import kb_chars_of

        out = [
            {"id": d["id"], "label": d["label"], "lang": d["lang"],
             "kb_chars": kb_chars_of(d.get("kb_body"))}
            for d in self._cache.values()
        ]
        out.sort(key=lambda x: x["id"] or "")
        return out

    async def put(self, demo_dict):
        canonical = self._normalize(demo_dict, validate_tools=False)
        self._cache[canonical["id"]] = canonical

    async def rescan(self):
        return len(self._cache)


def _store_at(bot, data_root):
    """Point bot.DEMO_LOADER at an in-memory store seeded from disk manifests
    under ``data_root`` (DDB-as-truth replacement for the legacy disk loader on
    the PATCH path)."""
    store = _MemStore(data_root)
    bot.DEMO_LOADER = store
    return store


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
def test_mcp_routes_require_admin_auth():
    from fastapi.testclient import TestClient
    bot = _import_app()
    bot.app.dependency_overrides.clear()  # exercise the real require_admin
    client = TestClient(bot.app, base_url="https://testserver")
    assert client.get("/api/admin/mcp-servers").status_code == 401
    assert client.post("/api/admin/mcp-servers", json=_server_payload()).status_code == 401
    assert client.delete("/api/admin/mcp-servers/weather-api").status_code == 401
    assert client.post("/api/admin/mcp-servers/weather-api/test").status_code == 401


# ---------------------------------------------------------------------------
# GET masking + POST upsert
# ---------------------------------------------------------------------------
def test_post_then_get_masks_headers():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)

    r = client.post("/api/admin/mcp-servers", headers=_basic(), json=_server_payload())
    assert r.status_code == 200, r.text
    # POST response is masked too — secrets never echo.
    assert r.json()["server"]["headers"] == {"Authorization": "***"}

    r = client.get("/api/admin/mcp-servers", headers=_basic())
    assert r.status_code == 200
    servers = r.json()["servers"]
    assert len(servers) == 1
    assert servers[0]["id"] == "weather-api"
    assert servers[0]["headers"] == {"Authorization": "***"}
    # Raw secret must not appear anywhere in the response body.
    assert "real-secret" not in r.text

    # But the registry on disk holds the real value.
    assert bot.MCP_CONFIG.get("weather-api")["headers"]["Authorization"] == "Bearer real-secret"


def test_post_sigv4_auth_survives_upsert():
    """Regression: POST /api/admin/mcp-servers with auth=sigv4 must persist the
    auth object. McpServerBody originally lacked an `auth` field, so Pydantic
    silently dropped it — a SigV4 server saved as auth=none and 403'd at connect
    (the exact gap a customer hits wiring their own AgentCore MCP via the UI)."""
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)

    payload = _server_payload(
        id="client-agentcore",
        headers={},
        auth={"type": "sigv4", "service": "bedrock-agentcore", "region": "eu-central-1"},
    )
    r = client.post("/api/admin/mcp-servers", headers=_basic(), json=payload)
    assert r.status_code == 200, r.text
    assert r.json()["server"]["auth"] == {
        "type": "sigv4", "service": "bedrock-agentcore", "region": "eu-central-1",
    }
    # And it's actually persisted (not just echoed).
    stored = bot.MCP_CONFIG.get("client-agentcore")
    assert stored["auth"]["type"] == "sigv4"
    assert stored["auth"]["region"] == "eu-central-1"

    # Backward-compat: omitting auth normalizes to none.
    r2 = client.post("/api/admin/mcp-servers", headers=_basic(),
                     json=_server_payload(id="no-auth-srv", headers={}))
    assert r2.status_code == 200, r2.text
    assert bot.MCP_CONFIG.get("no-auth-srv")["auth"] == {"type": "none"}


def test_post_mask_sentinel_preserves_stored_secret():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)

    client.post("/api/admin/mcp-servers", headers=_basic(), json=_server_payload())
    # Round-trip an edit where the SPA sends back the masked value.
    r = client.post(
        "/api/admin/mcp-servers",
        headers=_basic(),
        json=_server_payload(label="Renamed", headers={"Authorization": "***"}),
    )
    assert r.status_code == 200, r.text
    stored = bot.MCP_CONFIG.get("weather-api")
    assert stored["label"] == "Renamed"
    assert stored["headers"]["Authorization"] == "Bearer real-secret"


def test_post_validation_errors_return_400():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)

    r = client.post(
        "/api/admin/mcp-servers", headers=_basic(),
        json=_server_payload(transport="stdio"),
    )
    assert r.status_code == 400
    assert "stdio" in r.json()["detail"]

    r = client.post(
        "/api/admin/mcp-servers", headers=_basic(),
        json=_server_payload(id="Bad_ID"),
    )
    assert r.status_code == 400

    r = client.post(
        "/api/admin/mcp-servers", headers=_basic(),
        json=_server_payload(url="ftp://example.com/mcp"),
    )
    assert r.status_code == 400


# ---------------------------------------------------------------------------
# DELETE + 409 when referenced
# ---------------------------------------------------------------------------
def test_delete_server():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)
    client.post("/api/admin/mcp-servers", headers=_basic(), json=_server_payload())

    r = client.delete("/api/admin/mcp-servers/weather-api", headers=_basic())
    assert r.status_code == 200
    assert r.json() == {"deleted": "weather-api"}
    assert client.get("/api/admin/mcp-servers", headers=_basic()).json()["servers"] == []


def test_delete_unknown_returns_404():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)
    r = client.delete("/api/admin/mcp-servers/nope", headers=_basic())
    assert r.status_code == 404


def test_delete_referenced_server_returns_409_with_demo_ids(tmp_path):
    from fastapi.testclient import TestClient
    bot = _import_app()

    data_root = tmp_path / "data"
    _make_demo_dir(data_root, "demo-a", mcp_servers=["weather-api"])
    _make_demo_dir(data_root, "demo-b", mcp_servers=["weather-api", "other-srv"])
    _make_demo_dir(data_root, "demo-c")  # no mcp_servers
    _store_at(bot, data_root)

    client = TestClient(bot.app)
    client.post("/api/admin/mcp-servers", headers=_basic(), json=_server_payload())

    r = client.delete("/api/admin/mcp-servers/weather-api", headers=_basic())
    assert r.status_code == 409, r.text
    detail = r.json()["detail"]
    assert detail["demos"] == ["demo-a", "demo-b"]
    # Server is still there.
    assert bot.MCP_CONFIG.get("weather-api") is not None

    # After the references are gone, delete succeeds.
    for d in ("demo-a", "demo-b"):
        client.patch(f"/api/admin/demos/{d}", headers=_basic(), json={"mcp_servers": []})
    r = client.delete("/api/admin/mcp-servers/weather-api", headers=_basic())
    assert r.status_code == 200


# ---------------------------------------------------------------------------
# /test endpoint
# ---------------------------------------------------------------------------
def test_test_endpoint_unknown_server_404():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)
    r = client.post("/api/admin/mcp-servers/nope/test", headers=_basic())
    assert r.status_code == 404


def test_test_endpoint_unreachable_server_returns_friendly_error():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)
    # 127.0.0.1:9 (discard port, nothing listening) -> connect fails fast.
    client.post(
        "/api/admin/mcp-servers", headers=_basic(),
        json=_server_payload(id="dead-srv", url="http://127.0.0.1:9/mcp", headers={}),
    )
    r = client.post("/api/admin/mcp-servers/dead-srv/test", headers=_basic())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["ok"] is False
    assert body["tools"] == []
    assert isinstance(body["error"], str) and body["error"]


def test_test_endpoint_reports_missing_mcp_package(monkeypatch):
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)
    client.post("/api/admin/mcp-servers", headers=_basic(), json=_server_payload())

    # Simulate the mcp package being absent: poison both lazy imports.
    import builtins
    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "mcp" or name.startswith("mcp.") or name == "pipecat.services.mcp_service":
            raise ModuleNotFoundError(f"No module named {name!r}")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    # Drop cached modules so the lazy import actually re-imports.
    for mod in list(sys.modules):
        if mod == "mcp" or mod.startswith("mcp.") or mod == "pipecat.services.mcp_service":
            monkeypatch.delitem(sys.modules, mod, raising=False)

    r = client.post("/api/admin/mcp-servers/weather-api/test", headers=_basic())
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error"] == "mcp package not installed"


def test_test_endpoint_happy_path_lists_tools(tmp_path):
    """Spin up a real FastMCP streamable-http server on a local port and
    verify /test returns its tool names."""
    import socket
    import subprocess
    import textwrap
    import time

    from fastapi.testclient import TestClient

    # Grab a free port.
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]

    server_py = tmp_path / "mcp_server.py"
    server_py.write_text(textwrap.dedent(f"""\
        from mcp.server.fastmcp import FastMCP

        mcp = FastMCP("smoke", host="127.0.0.1", port={port})

        @mcp.tool()
        def get_weather(city: str) -> str:
            \"\"\"Get weather for a city.\"\"\"
            return f"Sunny in {{city}}"

        @mcp.tool()
        def add(a: int, b: int) -> int:
            \"\"\"Add two numbers.\"\"\"
            return a + b

        mcp.run(transport="streamable-http")
    """))

    proc = subprocess.Popen(
        [sys.executable, str(server_py)],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for the port to accept connections (max ~10s).
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            try:
                with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                    break
            except OSError:
                if proc.poll() is not None:
                    pytest.skip("FastMCP smoke server failed to start")
                time.sleep(0.1)
        else:
            pytest.skip("FastMCP smoke server did not open its port in time")

        bot = _import_app()
        client = TestClient(bot.app)
        client.post(
            "/api/admin/mcp-servers", headers=_basic(),
            json=_server_payload(
                id="smoke-srv",
                url=f"http://127.0.0.1:{port}/mcp",
                headers={},
            ),
        )
        r = client.post("/api/admin/mcp-servers/smoke-srv/test", headers=_basic())
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["ok"] is True, body
        assert sorted(body["tools"]) == ["add", "get_weather"]
        assert body["error"] is None
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


# ---------------------------------------------------------------------------
# /api/admin/options exposure
# ---------------------------------------------------------------------------
def test_options_includes_mcp_servers():
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)
    client.post("/api/admin/mcp-servers", headers=_basic(), json=_server_payload())
    client.post(
        "/api/admin/mcp-servers", headers=_basic(),
        json=_server_payload(id="other-srv", label="Other", enabled=False, headers={}),
    )

    r = client.get("/api/admin/options", headers=_basic())
    assert r.status_code == 200
    entries = r.json()["mcp_servers"]
    by_id = {e["id"]: e for e in entries}
    assert by_id["weather-api"] == {"id": "weather-api", "label": "Weather API", "enabled": True}
    assert by_id["other-srv"] == {"id": "other-srv", "label": "Other", "enabled": False}
    # No url/headers leakage through the options payload.
    assert "url" not in by_id["weather-api"]
    assert "headers" not in by_id["weather-api"]


# ---------------------------------------------------------------------------
# Demo manifest round-trip (read + PATCH write-back)
# ---------------------------------------------------------------------------
def test_demo_manifest_mcp_servers_read(tmp_path):
    from fastapi.testclient import TestClient
    bot = _import_app()
    from demo_loader import DemoLoader

    data_root = tmp_path / "data"
    _make_demo_dir(data_root, "with-mcp", mcp_servers=["weather-api"])
    bot.DEMO_LOADER = DemoLoader(str(data_root))
    client = TestClient(bot.app)

    # Loader surfaces the field.
    assert bot.DEMO_LOADER.get("with-mcp")["mcp_servers"] == ["weather-api"]

    # Detail endpoint surfaces it.
    r = client.get("/api/admin/demos/with-mcp", headers=_basic())
    assert r.status_code == 200
    assert r.json()["mcp_servers"] == ["weather-api"]

    # List endpoint surfaces it.
    r = client.get("/api/admin/demos", headers=_basic())
    listed = next(d for d in r.json()["demos"] if d["id"] == "with-mcp")
    assert listed["mcp_servers"] == ["weather-api"]


def test_demo_without_mcp_servers_defaults_empty(tmp_path):
    from fastapi.testclient import TestClient
    bot = _import_app()
    from demo_loader import DemoLoader

    data_root = tmp_path / "data"
    _make_demo_dir(data_root, "plain")
    bot.DEMO_LOADER = DemoLoader(str(data_root))
    client = TestClient(bot.app)

    assert bot.DEMO_LOADER.get("plain")["mcp_servers"] == []
    r = client.get("/api/admin/demos/plain", headers=_basic())
    assert r.json()["mcp_servers"] == []


def test_patch_demo_writes_mcp_servers_to_store(tmp_path):
    from fastapi.testclient import TestClient
    bot = _import_app()

    data_root = tmp_path / "data"
    _make_demo_dir(data_root, "patch-me")
    _store_at(bot, data_root)
    client = TestClient(bot.app)

    r = client.patch(
        "/api/admin/demos/patch-me",
        headers=_basic(),
        json={"mcp_servers": ["weather-api", "other-srv"]},
    )
    assert r.status_code == 200, r.text
    assert r.json()["mcp_servers"] == ["weather-api", "other-srv"]

    # Store reflects it after the rescan inside PATCH (DDB-as-truth; no
    # manifest.yaml is written anymore).
    assert bot.DEMO_LOADER.get("patch-me")["mcp_servers"] == ["weather-api", "other-srv"]


def test_patch_demo_mcp_only_leaves_tools_untouched(tmp_path):
    from fastapi.testclient import TestClient
    bot = _import_app()

    data_root = tmp_path / "data"
    demo_dir = data_root / "tools-demo"
    demo_dir.mkdir(parents=True)
    (demo_dir / "kb.md").write_text("kb")
    (demo_dir / "manifest.yaml").write_text(
        "id: tools-demo\nlabel: T\nlang: en-US\n"
        "system:\n  en-US: 'sys'\n"
        "greeting:\n  en-US: 'hi'\n"
        "kb_path: kb.md\n"
        "tools:\n  - end_call\n"
    )
    _store_at(bot, data_root)
    client = TestClient(bot.app)

    r = client.patch(
        "/api/admin/demos/tools-demo",
        headers=_basic(),
        json={"mcp_servers": ["weather-api"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["mcp_servers"] == ["weather-api"]
    assert body["tools"] == ["end_call"]  # untouched

    # And the reverse: tools-only PATCH leaves mcp_servers untouched.
    r = client.patch(
        "/api/admin/demos/tools-demo",
        headers=_basic(),
        json={"tools": ["end_call", "transfer_to_human"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["tools"] == ["end_call", "transfer_to_human"]
    assert body["mcp_servers"] == ["weather-api"]


def test_patch_demo_rejects_invalid_mcp_server_ids(tmp_path):
    from fastapi.testclient import TestClient
    bot = _import_app()
    from demo_loader import DemoLoader

    data_root = tmp_path / "data"
    _make_demo_dir(data_root, "bad-patch")
    bot.DEMO_LOADER = DemoLoader(str(data_root))
    client = TestClient(bot.app)

    r = client.patch(
        "/api/admin/demos/bad-patch",
        headers=_basic(),
        json={"mcp_servers": ["Not A Slug!"]},
    )
    assert r.status_code == 400
    assert "invalid mcp server ids" in str(r.json()["detail"])


def test_patch_demo_empty_body_400(tmp_path):
    from fastapi.testclient import TestClient
    bot = _import_app()
    from demo_loader import DemoLoader

    data_root = tmp_path / "data"
    _make_demo_dir(data_root, "empty-patch")
    bot.DEMO_LOADER = DemoLoader(str(data_root))
    client = TestClient(bot.app)

    r = client.patch("/api/admin/demos/empty-patch", headers=_basic(), json={})
    assert r.status_code == 400
