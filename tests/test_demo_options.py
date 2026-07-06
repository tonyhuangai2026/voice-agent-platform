"""T4 acceptance tests — demo options + system-prompt assembly.

Covers the 5 AC items beyond the bare grep check:

1. ``/api/admin/options`` first entry is ``id="default"``, the rest match
   ``DEMO_LOADER.list()`` 1:1 (in order).
2. ``demo=it-helpdesk`` + ``lang=zh-HK`` → ``_resolve_system_greeting``
   appends the 【掛線守則】 blurb at the system prompt's tail.
3. ``demo=default`` → ``_resolve_demo_tools`` returns ``[]`` and no blurb
   is appended to the resulting system prompt.
4. ``PHONE_TOOLS_ENABLED=0`` → ``_resolve_demo_tools`` returns ``[]`` for
   every demo (kill switch dominates the demo opt-in).
5. ``/api/admin/options`` and ``/api/config`` both return HTTP 200 with a
   well-formed body.

The tests treat ``bot.py`` as the unit under test — they import the
module, mutate ``PHONE_TOOLS_ENABLED`` directly (no separate process), and
hit the FastAPI endpoints via ``TestClient``.
"""

from __future__ import annotations

import base64
import importlib
import os

import pytest


@pytest.fixture(autouse=True)
def _common_env(monkeypatch):
    """Make module-level imports resolve cleanly without prod credentials."""
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pwd")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    monkeypatch.setenv("SITE_PASSWORD", "")
    yield


def _import_bot():
    """Re-import bot.py so any env mutation in a test is reflected by
    module-level singletons (PHONE_TOOLS_ENABLED, RUNTIME_CONFIG, ...)."""
    import sys

    for mod in ("bot", "runtime_config", "demo_store", "demo_loader", "user_store"):
        sys.modules.pop(mod, None)
    bot = importlib.import_module("bot")
    # DEMO_LOADER is now the DDB-backed DemoStore (T3); its cache is normally
    # prewarmed from DynamoDB by the FastAPI lifespan. There is no DDB in unit
    # tests, so seed the cache from the on-disk data/ demos via DemoLoader —
    # exactly the data the T4 migration loads into the table. This keeps these
    # demo-assembly tests exercising the real demo content without a live table.
    from demo_loader import DemoLoader

    _disk = DemoLoader(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
    bot.DEMO_LOADER._cache = {d["id"]: d for d in _disk._cache.values()}
    # Auth moved to JWT cookies; bypass require_user/require_admin so these
    # option/config tests don't need a login (auth is covered by test_auth.py).
    _admin = {"username": "admin", "role": "admin", "disabled": False, "created_at": 0}
    bot.app.dependency_overrides[bot.require_user] = lambda: _admin
    bot.app.dependency_overrides[bot.require_admin] = lambda: _admin
    return bot


def _basic(pwd: str = "test-pwd") -> dict[str, str]:
    # No-op: auth bypassed via dependency_overrides in _import_bot.
    return {}


# --- AC #1: bot.py grep ---------------------------------------------------


def test_bot_py_no_scenarios_or_kb_scenarios_dict_definitions():
    """bot.py contains DEFAULT_DEMO_ID but no SCENARIOS / KB_SCENARIOS dict
    literals (the in-code dicts were removed in T4)."""
    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = open(os.path.join(repo_root, "bot.py"), encoding="utf-8").read()
    # Hard rules: zero residual references to the legacy symbol names.
    assert "SCENARIOS" not in src
    assert "KB_SCENARIOS" not in src
    # The intended replacement constant must be present.
    assert "DEFAULT_DEMO_ID" in src


# --- AC #2: /api/admin/options layout -------------------------------------


def test_admin_options_first_entry_is_default_then_matches_demo_loader():
    """/api/admin/options scenarios[0] == default sentinel; the rest mirror
    DEMO_LOADER.list() in order with kind=='demo'."""
    bot = _import_bot()
    from fastapi.testclient import TestClient

    client = TestClient(bot.app)
    resp = client.get("/api/admin/options", headers=_basic())
    assert resp.status_code == 200, resp.text
    scenarios = resp.json()["scenarios"]
    assert scenarios, "scenarios list must not be empty"

    # Head: default sentinel
    assert scenarios[0]["id"] == "default"
    assert scenarios[0]["kind"] == "default"

    # Tail: 1:1 with DEMO_LOADER.list() (skipping any demo whose id is also
    # "default" since the sentinel takes that slot).
    loader_demos = [d for d in bot.DEMO_LOADER.list() if d["id"] != "default"]
    tail = scenarios[1:]
    assert [s["id"] for s in tail] == [d["id"] for d in loader_demos]
    assert all(s["kind"] == "demo" for s in tail)


# --- AC #3: it-helpdesk + zh-HK appends 掛線守則 blurb --------------------


def test_resolve_system_greeting_appends_hangup_blurb_for_it_helpdesk_zh_hk():
    """Selecting demo=it-helpdesk + lang=zh-HK with the matching tool_defs
    appends the registry's 【掛線守則】 blurb to the end of the system text.
    """
    bot = _import_bot()
    # The disk demo opts into both tools; the registry filters to entries
    # whose scope includes "phone" (both do here).
    tool_defs = bot._resolve_demo_tools("it-helpdesk", scope="phone")
    assert tool_defs, "it-helpdesk should opt into at least end_call/transfer"
    assert any(d.id == "end_call" for d in tool_defs)

    system, _ = bot._resolve_system_greeting(
        lang_key="zh-HK",
        scenario_key="it-helpdesk",
        system_override=None,
        greeting_override=None,
        tool_defs=tool_defs,
    )

    # The Cantonese hangup blurb is identifiable by its 【掛線守則】 heading.
    assert "【掛線守則】" in system, "expected 【掛線守則】 to be appended to system"
    # The registry-injected blurb is the LAST 【掛線守則】 occurrence (the
    # disk manifest may still carry an inline copy until T3 strips it; T4
    # only owns the assembly path). The injected copy must:
    #   (a) be preceded by a blank-line separator, and
    #   (b) be the closing block — the system text ends inside the
    #       transfer-policy section that follows it (or the blurb itself
    #       when only end_call is registered).
    last_blurb_idx = system.rindex("【掛線守則】")
    assert last_blurb_idx > 0, "blurb must come after the demo's own system text"
    assert system[last_blurb_idx - 2 : last_blurb_idx] == "\n\n", (
        "registry-injected blurb must be separated from the demo system by a blank line"
    )
    # Sanity: the very last 200 chars belong to the registry blurb, not
    # the demo's inline body — the blurb's stable trailing tokens are the
    # registry's exact closing punctuation. The transfer_to_human blurb
    # ends with `回電。` (no callback time promise) and the end_call-only
    # tail ends with the literal `end_call。`.
    tail = system.rstrip()
    assert tail.endswith("回電。") or tail.endswith("end_call。"), (
        f"unexpected system tail: {tail[-120:]!r}"
    )


# --- AC #4: default demo → no tools, no blurb ----------------------------


def test_resolve_demo_tools_returns_empty_for_default():
    """demo=default → _resolve_demo_tools yields []; no blurb is appended."""
    bot = _import_bot()
    defs = bot._resolve_demo_tools(bot.DEFAULT_DEMO_ID, scope="phone")
    assert defs == []
    defs_web = bot._resolve_demo_tools(bot.DEFAULT_DEMO_ID, scope="web")
    assert defs_web == []

    # System prompt for default demo with empty tool_defs equals the
    # plain per-language default — i.e. no [Hangup ...] / 【掛線...】 marker.
    system, _ = bot._resolve_system_greeting(
        lang_key="zh-HK",
        scenario_key=bot.DEFAULT_DEMO_ID,
        system_override=None,
        greeting_override=None,
        tool_defs=defs,
    )
    assert "【掛線守則】" not in system
    assert "[Hangup policy]" not in system


# --- AC #5: PHONE_TOOLS_ENABLED=0 kills tools globally -------------------


def test_phone_tools_kill_switch_forces_empty_tool_list(monkeypatch):
    """PHONE_TOOLS_ENABLED=0 → every demo's _resolve_demo_tools returns []."""
    monkeypatch.setenv("PHONE_TOOLS_ENABLED", "0")
    bot = _import_bot()
    assert bot.PHONE_TOOLS_ENABLED is False

    # Even an opted-in demo gets [] when the switch is OFF.
    assert bot._resolve_demo_tools("it-helpdesk", scope="phone") == []
    assert bot._resolve_demo_tools("it-helpdesk", scope="web") == []
    # Default sentinel obviously also empty.
    assert bot._resolve_demo_tools("default", scope="phone") == []


# --- AC #6: /api/admin/options + /api/config both 200 --------------------


def test_admin_options_and_api_config_both_return_200():
    """Bringing the FastAPI app up locally — /api/admin/options + /api/config
    both respond 200 and carry the expected top-level keys."""
    bot = _import_bot()
    from fastapi.testclient import TestClient

    client = TestClient(bot.app)

    r1 = client.get("/api/admin/options", headers=_basic())
    assert r1.status_code == 200, r1.text
    body1 = r1.json()
    for key in ("languages", "engines", "providers", "models", "scenarios"):
        assert key in body1

    r2 = client.get("/api/config")
    assert r2.status_code == 200, r2.text
    body2 = r2.json()
    for key in ("languages", "engines", "providers", "scenarios"):
        assert key in body2
    # /api/config also surfaces the demo selector under the same legacy key.
    assert body2["scenarios"][0]["id"] == "default"


# --- Bonus: per-tool scope filter behaves -------------------------------


def test_get_tool_defs_filters_unknown_and_wrong_scope():
    """The registry helper drops unknown ids and ids whose scope doesn't
    match — surfacing a warning but still returning the valid tail."""
    from tools.registry import REGISTRY, get_tool_defs

    # Smoke: known id + scope match.
    defs = get_tool_defs(["end_call", "definitely_not_a_tool"], scope="phone")
    assert [d.id for d in defs] == ["end_call"]

    # Smoke: scope-shaped filter — patch a tool's scope to phone-only and
    # confirm it disappears from a "web" lookup.
    original = REGISTRY["transfer_to_human"]
    try:
        # frozen=True dataclass — replace the entry, don't mutate the field.
        from dataclasses import replace

        REGISTRY["transfer_to_human"] = replace(original, scope=frozenset({"phone"}))
        web_defs = get_tool_defs(["end_call", "transfer_to_human"], scope="web")
        assert [d.id for d in web_defs] == ["end_call"]
    finally:
        REGISTRY["transfer_to_human"] = original
