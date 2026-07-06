"""Runtime MCP wiring tests for bot.py (task 2ddf06df — T2).

Covers the two seams introduced by T2's double-engine MCP runtime wiring,
hermetically (no network, no real MCP server):

- ``_merge_mcp_tools`` (the pure merge/conflict helper):
    a) a registry-vs-MCP name conflict drops the MCP tool (registry wins)
    b) MCP-vs-MCP name conflict drops the later duplicate (first-seen wins)
    c) the no-tools path returns ``(None, [])`` byte-identically to before MCP
    d) the registry-only path is unchanged when there are no MCP tools
- ``_connect_mcp_clients`` (the connect helper):
    e) a demo with no ``mcp_servers`` returns ``([], [])`` with zero work
    f) a server whose ``start()`` raises is swallowed (WARNING) and skipped,
       its ``close()`` is still called, and the call is not aborted
    g) a connected server's tools are collected
"""

from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def bot_mod(monkeypatch):
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pwd")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    for mod in list(sys.modules):
        if mod in ("bot", "runtime_config", "demo_loader", "mcp_config"):
            del sys.modules[mod]
    return importlib.import_module("bot")


def _fs(name: str):
    from pipecat.adapters.schemas.function_schema import FunctionSchema

    return FunctionSchema(name=name, description=name, properties={}, required=[])


def _tools_schema(*names):
    from pipecat.adapters.schemas.tools_schema import ToolsSchema

    return ToolsSchema(standard_tools=[_fs(n) for n in names])


# --- _merge_mcp_tools ----------------------------------------------------


def test_merge_registry_wins_on_conflict(bot_mod):
    """(a) MCP tool colliding with a registry name is dropped; registry kept."""
    registry = _tools_schema("end_call", "get_weather")
    client = object()
    mcp = [(client, [_fs("get_weather"), _fs("lookup_order")])]

    combined, kept = bot_mod._merge_mcp_tools(registry, mcp)

    names = [fs.name for fs in combined.standard_tools]
    # registry's get_weather stays; MCP get_weather dropped; lookup_order added
    assert names == ["end_call", "get_weather", "lookup_order"]
    assert [fs.name for _c, fs in kept] == ["lookup_order"]


def test_merge_mcp_vs_mcp_first_seen_wins(bot_mod):
    """(b) Duplicate name across MCP servers: first-seen kept, later dropped."""
    c1, c2 = object(), object()
    mcp = [(c1, [_fs("search")]), (c2, [_fs("search"), _fs("other")])]

    combined, kept = bot_mod._merge_mcp_tools(None, mcp)

    assert [fs.name for fs in combined.standard_tools] == ["search", "other"]
    # the kept "search" belongs to the first client, not the second
    kept_by_name = {fs.name: c for c, fs in kept}
    assert kept_by_name["search"] is c1
    assert kept_by_name["other"] is c2


def test_merge_no_tools_returns_none(bot_mod):
    """(c) No registry tools + no MCP tools -> (None, []) — pre-MCP no-tools path."""
    combined, kept = bot_mod._merge_mcp_tools(None, [])
    assert combined is None
    assert kept == []


def test_merge_registry_only_unchanged(bot_mod):
    """(d) Registry tools + no MCP -> same tool set, nothing registered."""
    registry = _tools_schema("end_call", "transfer_to_human")
    combined, kept = bot_mod._merge_mcp_tools(registry, [])
    assert [fs.name for fs in combined.standard_tools] == ["end_call", "transfer_to_human"]
    assert kept == []


# --- _connect_mcp_clients ------------------------------------------------


@pytest.mark.asyncio
async def test_connect_no_servers_zero_overhead(bot_mod, monkeypatch):
    """(e) Demo with no mcp_servers -> ([], []) and no MCPClient import touched."""
    monkeypatch.setattr(bot_mod.DEMO_LOADER, "get", lambda k: {"mcp_servers": []})
    clients, schemas = await bot_mod._connect_mcp_clients("demo", "web")
    assert clients == []
    assert schemas == []


class _FakeClient:
    """Minimal MCPClient stand-in. start() may raise; close() is always safe."""

    instances: list = []

    def __init__(self, server_params=None):
        self.server_params = server_params
        self.started = False
        self.closed = False
        self.fail = False
        self.tool_names: list[str] = []
        _FakeClient.instances.append(self)

    async def start(self):
        if self.fail:
            raise RuntimeError("boom")
        self.started = True

    async def get_tools_schema(self):
        return _tools_schema(*self.tool_names)

    async def close(self):
        self.closed = True


def _install_fake_mcp(monkeypatch, configure):
    """Patch the lazily-imported MCPClient + param classes with fakes."""
    import pipecat.services.mcp_service as mcp_service
    import mcp.client.session_group as sg

    _FakeClient.instances = []

    def _factory(server_params=None):
        c = _FakeClient(server_params=server_params)
        configure(c)
        return c

    monkeypatch.setattr(mcp_service, "MCPClient", _factory)
    # Param classes just need to be constructable with url/headers kwargs.
    monkeypatch.setattr(sg, "SseServerParameters", lambda **kw: ("sse", kw), raising=False)
    monkeypatch.setattr(
        sg, "StreamableHttpParameters", lambda **kw: ("http", kw), raising=False
    )


@pytest.mark.asyncio
async def test_connect_failure_is_swallowed(bot_mod, monkeypatch):
    """(f) A server whose start() raises is skipped, closed, call not aborted."""
    monkeypatch.setattr(
        bot_mod.DEMO_LOADER, "get", lambda k: {"mcp_servers": ["bad"]}
    )
    monkeypatch.setattr(
        bot_mod.MCP_CONFIG,
        "get",
        lambda sid: {"transport": "streamable_http", "url": "https://x/mcp", "enabled": True},
    )

    def _configure(c):
        c.fail = True

    _install_fake_mcp(monkeypatch, _configure)

    clients, schemas = await bot_mod._connect_mcp_clients("demo", "web")

    assert clients == []
    assert schemas == []
    # the failed client was still close()d
    assert len(_FakeClient.instances) == 1
    assert _FakeClient.instances[0].closed is True


@pytest.mark.asyncio
async def test_connect_collects_tools(bot_mod, monkeypatch):
    """(g) A reachable server's tools are collected into (clients, schemas)."""
    monkeypatch.setattr(
        bot_mod.DEMO_LOADER, "get", lambda k: {"mcp_servers": ["good"]}
    )
    monkeypatch.setattr(
        bot_mod.MCP_CONFIG,
        "get",
        lambda sid: {"transport": "sse", "url": "https://x/mcp", "enabled": True},
    )

    def _configure(c):
        c.tool_names = ["get_weather", "lookup_order"]

    _install_fake_mcp(monkeypatch, _configure)

    clients, schemas = await bot_mod._connect_mcp_clients("demo", "web")

    assert len(clients) == 1 and clients[0].started is True
    assert len(schemas) == 1
    client, fns = schemas[0]
    assert client is clients[0]
    assert [fs.name for fs in fns] == ["get_weather", "lookup_order"]


@pytest.mark.asyncio
async def test_connect_skips_disabled_server(bot_mod, monkeypatch):
    """A disabled/missing server config is skipped without constructing a client."""
    monkeypatch.setattr(
        bot_mod.DEMO_LOADER, "get", lambda k: {"mcp_servers": ["off", "absent"]}
    )

    def _get(sid):
        if sid == "off":
            return {"transport": "sse", "url": "https://x/mcp", "enabled": False}
        return None  # "absent" not in registry

    monkeypatch.setattr(bot_mod.MCP_CONFIG, "get", _get)
    _install_fake_mcp(monkeypatch, lambda c: None)

    clients, schemas = await bot_mod._connect_mcp_clients("demo", "web")

    assert clients == []
    assert schemas == []
    assert _FakeClient.instances == []  # never constructed
