"""T6 admin REST: tools endpoint, demos↔tools augmentation, demos PATCH,
rescan ``last_skipped``, and the legacy ``/api/admin/scenarios`` alias.

Covers acceptance criteria from task 2b7d62b8 — see the
``test_ac_*`` helpers below for the explicit AC mapping. The tests use
FastAPI ``TestClient`` against the production app so we exercise the
real middleware (admin Basic Auth) and the real demo_loader / tools
registry singletons.

Two of these tests need to mutate disk state under
``data/<demo>/manifest.yaml``. They do so against a tmp_path-backed
copy and re-import bot.py so ``DEMO_LOADER`` points at the temp dir;
the repo's real ``data/it-helpdesk/manifest.yaml`` is never written.
"""

from __future__ import annotations

import base64
import importlib
import os
import shutil
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def admin_password(monkeypatch):
    """Make admin auth deterministic across tests."""
    monkeypatch.setenv("ADMIN_PASSWORD", "test-pwd")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    yield


@pytest.fixture
def fresh_runtime_json(tmp_path, monkeypatch):
    cfg_dir = tmp_path / "config"
    cfg_dir.mkdir()
    monkeypatch.setenv("RUNTIME_CFG_PATH_OVERRIDE", str(cfg_dir / "runtime.json"))
    yield


def _import_app():
    """Re-import bot.py fresh so module-level singletons (DEMO_LOADER,
    ADMIN_PASSWORD) pick up the test env."""
    for mod in list(sys.modules):
        if mod in ("bot", "runtime_config", "demo_loader", "user_store"):
            del sys.modules[mod]
    bot = importlib.import_module("bot")
    # Auth moved to JWT cookies; bypass require_user/require_admin so these
    # tests focus on tool/demo CRUD (auth is covered by test_auth.py). The
    # *_requires_admin_auth tests clear these overrides to exercise the real dep.
    _admin = {"username": "admin", "role": "admin", "disabled": False, "created_at": 0}
    bot.app.dependency_overrides[bot.require_user] = lambda: _admin
    bot.app.dependency_overrides[bot.require_admin] = lambda: _admin
    return bot


def _basic(user: str = "admin", pwd: str = "test-pwd") -> dict[str, str]:
    # No-op: auth bypassed via dependency_overrides in _import_app.
    return {}


def _seed_demo_data(target_data_dir: Path, *, source: Path) -> None:
    """Copy the repo's ``data/`` dir into ``target_data_dir`` so we can
    safely mutate manifest.yaml without dirtying the working tree."""
    if target_data_dir.exists():
        shutil.rmtree(target_data_dir)
    shutil.copytree(source, target_data_dir)


class _MemStore:
    """In-memory stand-in for the DDB-backed DemoStore exposing the interface
    the PATCH endpoint uses (get/list/rescan + async put). DDB-as-truth means
    PATCH no longer writes manifest.yaml, so the legacy disk DemoLoader (no
    ``put``) can't back the PATCH path; this shim exercises the real
    merge → put → rescan flow without a moto round-trip. ``put`` normalizes
    through the SAME shared helper as DemoStore (canonical ``tool_ids`` key)."""

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
    (DDB-as-truth replacement for the legacy disk loader on the PATCH path)."""
    store = _MemStore(data_root)
    bot.DEMO_LOADER = store
    return store


@pytest.fixture
def isolated_data_dir(tmp_path, monkeypatch):
    """Re-point DEMO_LOADER at a tmp_path copy of the real ``data/`` dir.

    This works by monkey-patching the module path that ``bot.py`` reads
    on import — which means callers must use ``_import_app()`` AFTER
    the fixture runs (the fixture sets up the env / patches first).
    """
    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "data"
    dst = tmp_path / "data"
    _seed_demo_data(dst, source=src)

    # bot.py uses os.path.dirname(__file__)/data for the loader. Easier
    # than threading an env var: monkey-patch DemoLoader's data_root
    # via the module after import, because reimport would reuse the
    # bot.py default. We do that by importing bot first, then swapping
    # DEMO_LOADER for a fresh one rooted at our tmp dir.
    bot = _import_app()
    from demo_loader import DemoLoader

    bot.DEMO_LOADER = DemoLoader(str(dst))
    yield bot, dst


# ---------------------------------------------------------------------------
# AC #1 — GET /api/admin/tools returns at least end_call + transfer_to_human,
# scope is a sorted JSON list (not a frozenset, not null)
# ---------------------------------------------------------------------------
def test_ac1_tools_endpoint_returns_registry(fresh_runtime_json):
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)

    r = client.get("/api/admin/tools", headers=_basic())
    assert r.status_code == 200, r.text
    body = r.json()
    assert "tools" in body and isinstance(body["tools"], list)

    by_id = {t["id"]: t for t in body["tools"]}
    assert "end_call" in by_id
    assert "transfer_to_human" in by_id

    for tid in ("end_call", "transfer_to_human"):
        entry = by_id[tid]
        # Required keys per spec.
        for k in (
            "id",
            "label",
            "description",
            "scope",
            "default_enabled",
            "supported_langs",
            "hangup_blurb_keys",
        ):
            assert k in entry, f"{tid}: missing key {k!r} in {entry!r}"

        # scope must be a JSON list (not frozenset string, not null) and
        # must be sorted.
        scope = entry["scope"]
        assert isinstance(scope, list), f"{tid}: scope should be list, got {type(scope)}"
        assert scope == sorted(scope)
        assert all(isinstance(x, str) for x in scope)
        # Both bundled tools currently apply to phone+web — sanity check
        # the registry hasn't drifted to an unexpected scope.
        assert set(scope) == {"phone", "web"}

        # description is non-empty (it falls back to the schema desc).
        assert isinstance(entry["description"], str) and entry["description"]

        # default_enabled is hardcoded False for now.
        assert entry["default_enabled"] is False

        # supported_langs covers all four languages from the registry.
        assert set(entry["supported_langs"]) >= {"en-US", "zh-CN", "zh-HK", "ja-JP"}
        # hangup_blurb_keys mirrors supported_langs today.
        assert entry["hangup_blurb_keys"] == entry["supported_langs"]


def test_ac1_tools_endpoint_requires_admin_auth(fresh_runtime_json):
    from fastapi.testclient import TestClient
    bot = _import_app()
    bot.app.dependency_overrides.clear()  # exercise the real require_admin
    client = TestClient(bot.app, base_url="https://testserver")
    r = client.get("/api/admin/tools")
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# AC #2 — PATCH /api/admin/demos/{id} writes the tools list to the DDB-backed
# store (DDB is the single source of truth; manifest.yaml is no longer written)
# ---------------------------------------------------------------------------
def test_ac2_patch_demo_writes_tools_to_store(
    tmp_path, fresh_runtime_json, monkeypatch,
):
    from fastapi.testclient import TestClient

    data_root = tmp_path / "data"
    data_root.mkdir()
    demo_dir = data_root / "comment-demo"
    demo_dir.mkdir()
    (demo_dir / "kb.md").write_text("kb body")
    manifest = """\
id: comment-demo
label: Comment Demo
lang: en-US
tools: []
system:
  en-US: |
    you are a bot
greeting:
  en-US: hi
kb_path: kb.md
"""
    (demo_dir / "manifest.yaml").write_text(manifest)

    bot = _import_app()
    store = _store_at(bot, data_root)
    assert store.get("comment-demo") is not None

    client = TestClient(bot.app)
    r = client.patch(
        "/api/admin/demos/comment-demo",
        headers=_basic(),
        json={"tools": ["end_call"]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "comment-demo"
    assert body["tools"] == ["end_call"]
    assert any(td["id"] == "end_call" for td in body["tool_defs"])

    # Store reflects the new tool ids after the rescan inside PATCH; the
    # internal canonical key is ``tool_ids`` (BLOCKER #1), never ``tools``.
    refreshed = bot.DEMO_LOADER.get("comment-demo")
    assert refreshed is not None
    assert refreshed["tool_ids"] == ["end_call"]


def test_ac2_patch_demo_404_when_unknown(tmp_path, fresh_runtime_json):
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)
    r = client.patch(
        "/api/admin/demos/does-not-exist",
        headers=_basic(),
        json={"tools": []},
    )
    assert r.status_code == 404


def test_ac2_patch_demo_requires_admin_auth(fresh_runtime_json):
    from fastapi.testclient import TestClient
    bot = _import_app()
    bot.app.dependency_overrides.clear()  # exercise the real require_admin
    client = TestClient(bot.app, base_url="https://testserver")
    r = client.patch("/api/admin/demos/anything", json={"tools": []})
    assert r.status_code == 401


# ---------------------------------------------------------------------------
# AC #3 — PATCH with unknown tool id returns 400 + the offending id(s) in
# the error message
# ---------------------------------------------------------------------------
def test_ac3_patch_demo_rejects_unknown_tool_id(
    tmp_path, fresh_runtime_json, monkeypatch,
):
    from fastapi.testclient import TestClient

    data_root = tmp_path / "data"
    data_root.mkdir()
    demo_dir = data_root / "reject-demo"
    demo_dir.mkdir()
    (demo_dir / "kb.md").write_text("body")
    (demo_dir / "manifest.yaml").write_text(
        "id: reject-demo\nlabel: Reject\nlang: en-US\n"
        "system:\n  en-US: 'sys'\n"
        "greeting:\n  en-US: 'hi'\n"
        "kb_path: kb.md\n"
    )
    bot = _import_app()
    from demo_loader import DemoLoader
    bot.DEMO_LOADER = DemoLoader(str(data_root))

    client = TestClient(bot.app)
    r = client.patch(
        "/api/admin/demos/reject-demo",
        headers=_basic(),
        json={"tools": ["foo_bar", "end_call"]},
    )
    assert r.status_code == 400, r.text
    detail = r.json().get("detail", "")
    # Must mention the unknown id specifically; the second (valid) id
    # should NOT have leaked into the error.
    assert "foo_bar" in str(detail)
    assert "unknown" in str(detail).lower()


# ---------------------------------------------------------------------------
# AC #4 — GET /api/admin/demos and /api/admin/demos/{id} both include
# `tools` and `tool_defs`
# ---------------------------------------------------------------------------
def test_ac4_demos_list_includes_tools_and_tool_defs(
    tmp_path, fresh_runtime_json, monkeypatch,
):
    """Materialise a demo with two known tools and verify both list +
    detail responses surface the augmentation."""
    from fastapi.testclient import TestClient

    data_root = tmp_path / "data"
    data_root.mkdir()
    demo_dir = data_root / "tooly"
    demo_dir.mkdir()
    (demo_dir / "kb.md").write_text("body")
    (demo_dir / "manifest.yaml").write_text(
        "id: tooly\nlabel: Tooly\nlang: en-US\n"
        "system:\n  en-US: 'sys'\n"
        "greeting:\n  en-US: 'hi'\n"
        "kb_path: kb.md\n"
        "tools:\n  - end_call\n  - transfer_to_human\n"
    )
    bot = _import_app()
    from demo_loader import DemoLoader
    bot.DEMO_LOADER = DemoLoader(str(data_root))

    client = TestClient(bot.app)

    # GET list
    r = client.get("/api/admin/demos", headers=_basic())
    assert r.status_code == 200
    demos = r.json()["demos"]
    by_id = {d["id"]: d for d in demos}
    assert "tooly" in by_id
    listed = by_id["tooly"]
    assert listed["tools"] == ["end_call", "transfer_to_human"]
    assert isinstance(listed["tool_defs"], list)
    tdef_ids = [td["id"] for td in listed["tool_defs"]]
    assert tdef_ids == ["end_call", "transfer_to_human"]
    # tool_def dicts include at minimum id/label/description.
    for td in listed["tool_defs"]:
        assert "id" in td and "label" in td and "description" in td

    # GET detail
    r = client.get("/api/admin/demos/tooly", headers=_basic())
    assert r.status_code == 200
    detail = r.json()
    assert detail["tools"] == ["end_call", "transfer_to_human"]
    assert [td["id"] for td in detail["tool_defs"]] == [
        "end_call",
        "transfer_to_human",
    ]


def test_ac4_demos_list_handles_demo_with_no_tools(
    tmp_path, fresh_runtime_json,
):
    from fastapi.testclient import TestClient

    data_root = tmp_path / "data"
    data_root.mkdir()
    demo_dir = data_root / "bare"
    demo_dir.mkdir()
    (demo_dir / "kb.md").write_text("body")
    (demo_dir / "manifest.yaml").write_text(
        "id: bare\nlabel: Bare\nlang: en-US\n"
        "system:\n  en-US: 'sys'\n"
        "greeting:\n  en-US: 'hi'\n"
        "kb_path: kb.md\n"
    )
    bot = _import_app()
    from demo_loader import DemoLoader
    bot.DEMO_LOADER = DemoLoader(str(data_root))

    client = TestClient(bot.app)
    r = client.get("/api/admin/demos", headers=_basic())
    assert r.status_code == 200
    demos = r.json()["demos"]
    listed = next(d for d in demos if d["id"] == "bare")
    assert listed["tools"] == []
    assert listed["tool_defs"] == []


# ---------------------------------------------------------------------------
# AC #5 — GET /api/admin/scenarios (legacy) returns the same structure as
# GET /api/admin/demos, so the legacy SPA keeps working
# ---------------------------------------------------------------------------
def test_ac5_scenarios_alias_matches_demos(fresh_runtime_json):
    from fastapi.testclient import TestClient
    bot = _import_app()
    client = TestClient(bot.app)

    r_demos = client.get("/api/admin/demos", headers=_basic())
    r_scenarios = client.get("/api/admin/scenarios", headers=_basic())
    assert r_demos.status_code == 200
    assert r_scenarios.status_code == 200
    # Same shape, same payload — the scenarios route is a thin alias.
    assert r_scenarios.json() == r_demos.json()


# ---------------------------------------------------------------------------
# AC #6 — POST /api/admin/demos/rescan returns last_skipped (empty when
# everything loaded, populated when something was rejected)
# ---------------------------------------------------------------------------
def test_ac6_rescan_returns_empty_last_skipped_on_clean_dir(
    tmp_path, fresh_runtime_json,
):
    from fastapi.testclient import TestClient

    data_root = tmp_path / "data"
    data_root.mkdir()
    demo_dir = data_root / "ok"
    demo_dir.mkdir()
    (demo_dir / "kb.md").write_text("body")
    (demo_dir / "manifest.yaml").write_text(
        "id: ok\nlabel: OK\nlang: en-US\n"
        "system:\n  en-US: 'sys'\n"
        "greeting:\n  en-US: 'hi'\n"
        "kb_path: kb.md\n"
    )
    bot = _import_app()
    from demo_loader import DemoLoader
    bot.DEMO_LOADER = DemoLoader(str(data_root))

    client = TestClient(bot.app)
    r = client.post("/api/admin/demos/rescan", headers=_basic())
    assert r.status_code == 200
    body = r.json()
    assert "last_skipped" in body
    assert body["last_skipped"] == []
    # Standard rescan response contract still in place.
    assert body["count"] == 1
    assert any(d["id"] == "ok" for d in body["demos"])


def test_ac6_rescan_returns_skipped_entries_for_broken_demo(
    tmp_path, fresh_runtime_json,
):
    from fastapi.testclient import TestClient

    data_root = tmp_path / "data"
    data_root.mkdir()
    # One good demo so the loader has something to return alongside.
    good = data_root / "good"
    good.mkdir()
    (good / "kb.md").write_text("body")
    (good / "manifest.yaml").write_text(
        "id: good\nlabel: Good\nlang: en-US\n"
        "system:\n  en-US: 'sys'\n"
        "greeting:\n  en-US: 'hi'\n"
        "kb_path: kb.md\n"
    )
    # And a broken one (missing required `system`).
    bad = data_root / "bad"
    bad.mkdir()
    (bad / "manifest.yaml").write_text(
        "id: bad\nlabel: Bad\nlang: en-US\n"
        "greeting:\n  en-US: 'hi'\n"
    )

    bot = _import_app()
    from demo_loader import DemoLoader
    bot.DEMO_LOADER = DemoLoader(str(data_root))

    client = TestClient(bot.app)
    r = client.post("/api/admin/demos/rescan", headers=_basic())
    assert r.status_code == 200
    body = r.json()
    assert body["count"] == 1
    skipped = body["last_skipped"]
    assert isinstance(skipped, list) and len(skipped) >= 1
    entry = next((s for s in skipped if s["id"] == "bad"), None)
    assert entry is not None, skipped
    assert "system" in entry["reason"]


def test_ac6_rescan_requires_admin_auth(fresh_runtime_json):
    from fastapi.testclient import TestClient
    bot = _import_app()
    bot.app.dependency_overrides.clear()  # exercise the real require_admin
    client = TestClient(bot.app, base_url="https://testserver")
    r = client.post("/api/admin/demos/rescan")
    assert r.status_code == 401
