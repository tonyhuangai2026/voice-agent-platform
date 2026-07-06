"""Unit tests for demo_loader.DemoLoader covering the 7 mandated scenarios.

Scenario 7 (regression) is the byte-equal check of new demo_loader path vs
the legacy KB_SCENARIOS path for the migrated acme-security-support demo.
"""

import os
import pytest
import yaml

from demo_loader import DemoLoader


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture
def real_loader() -> DemoLoader:
    """DemoLoader pointing at the real project data/ directory."""
    return DemoLoader(os.path.join(PROJECT_ROOT, "data"))


# Scenario 1: scans data/, discovers acme-security-support
def test_finds_acme_security(real_loader):
    ids = [d["id"] for d in real_loader.list()]
    assert "acme-security-support" in ids
    summary = next(d for d in real_loader.list() if d["id"] == "acme-security-support")
    assert summary["lang"] == "zh-HK"
    assert summary["kb_chars"] > 1000


# Scenario 2: get(id).system is per-language dict, all 4 langs non-empty
def test_system_has_all_4_languages(real_loader):
    demo = real_loader.get("acme-security-support")
    assert demo is not None
    assert isinstance(demo["system"], dict)
    for lang in ("zh-HK", "zh-CN", "en-US", "ja-JP"):
        assert lang in demo["system"]
        assert demo["system"][lang]
        assert isinstance(demo["system"][lang], str)
        assert len(demo["system"][lang]) > 100


# Scenario 3: greeting same coverage
def test_greeting_has_all_4_languages(real_loader):
    demo = real_loader.get("acme-security-support")
    assert isinstance(demo["greeting"], dict)
    for lang in ("zh-HK", "zh-CN", "en-US", "ja-JP"):
        assert lang in demo["greeting"]
        assert demo["greeting"][lang]


# Scenario 4: missing id returns None
def test_unknown_id_returns_none(real_loader):
    assert real_loader.get("not-a-real-demo") is None


# Scenario 5: missing manifest skips silently
def test_missing_manifest_skipped(tmp_path):
    (tmp_path / "broken").mkdir()
    (tmp_path / "broken" / "kb.md").write_text("body")
    # no manifest.yaml in broken/
    (tmp_path / "good").mkdir()
    (tmp_path / "good" / "kb.md").write_text("hello")
    yaml_text = yaml.safe_dump({
        "id": "good",
        "label": "Good",
        "lang": "en-US",
        "system": {"en-US": "you are good"},
        "greeting": {"en-US": "hi"},
    }, allow_unicode=True)
    (tmp_path / "good" / "manifest.yaml").write_text(yaml_text)

    loader = DemoLoader(str(tmp_path))
    ids = [d["id"] for d in loader.list()]
    assert ids == ["good"]


# Scenario 6: rescan picks up new demos
def test_rescan_finds_new(tmp_path):
    loader = DemoLoader(str(tmp_path))
    assert loader.list() == []
    (tmp_path / "fresh").mkdir()
    (tmp_path / "fresh" / "kb.md").write_text("kb body")
    (tmp_path / "fresh" / "manifest.yaml").write_text(yaml.safe_dump({
        "id": "fresh",
        "label": "Fresh demo",
        "lang": "en-US",
        "system": {"en-US": "system"},
        "greeting": {"en-US": "greet"},
    }, allow_unicode=True))
    n = loader.rescan()
    assert n == 1
    assert loader.get("fresh") is not None


# Scenario 7 (deleted in T4): the legacy KB_SCENARIOS dict no longer exists,
# so there is nothing to byte-equal-compare the disk demo against. The disk
# manifest under data/acme-security-support/ is now the single source of truth.


# Bonus: invalid manifest (system not a dict) skipped with warning
def test_invalid_system_field_skipped(tmp_path, caplog):
    (tmp_path / "bad").mkdir()
    (tmp_path / "bad" / "kb.md").write_text("kb")
    (tmp_path / "bad" / "manifest.yaml").write_text(yaml.safe_dump({
        "id": "bad",
        "label": "Bad",
        "lang": "en-US",
        "system": "not a dict",  # invalid
        "greeting": {"en-US": "hi"},
    }, allow_unicode=True))
    import logging
    with caplog.at_level(logging.WARNING):
        loader = DemoLoader(str(tmp_path))
    assert loader.get("bad") is None
    assert any("must be a non-empty per-language dict" in r.message for r in caplog.records)
