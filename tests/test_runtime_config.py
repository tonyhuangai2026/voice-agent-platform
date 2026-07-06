"""Unit tests for runtime_config.RuntimeConfig — covers all 5 mandated scenarios."""

import json
import os
import threading

import pytest

from runtime_config import RuntimeConfig


@pytest.fixture
def fallback() -> dict:
    return {
        "web": {
            "lang": "en-US",
            "engine": "nova-sonic",
            "scenario": "default",
            "model": "nova-2-lite",
            "provider": "minimax",
            "voice": "Cantonese_GentleLady",
            "minimax_model": "speech-2.8-turbo",
        },
        "phone": {
            "engine": "nova-sonic",
            "lang": "en-US",
            "scenario": "acme-security-support",
            "voice": "tiffany",
            "provider": "minimax",
            "model": "nova-2-lite",
            "minimax_model": "speech-2.8-turbo",
        },
    }


@pytest.fixture
def cfg_path(tmp_path) -> str:
    return str(tmp_path / "config" / "runtime.json")


# Scenario 1: file missing -> get_web_defaults returns fallback (and seeds file)
def test_seed_when_file_missing(cfg_path, fallback):
    rc = RuntimeConfig(cfg_path, fallback)
    web = rc.get_web_defaults()
    assert web == fallback["web"]
    # seed file should now exist
    assert os.path.exists(cfg_path)
    with open(cfg_path) as f:
        on_disk = json.load(f)
    assert on_disk["web"] == fallback["web"]
    assert on_disk["phone"] == fallback["phone"]
    assert on_disk["_meta"]["version"] == 1


# Scenario 2: write -> reconstruct -> read same value
def test_persists_across_instances(cfg_path, fallback):
    rc1 = RuntimeConfig(cfg_path, fallback)
    rc1.update_phone({"engine": "pipeline", "lang": "zh-HK"})

    rc2 = RuntimeConfig(cfg_path, fallback)
    phone = rc2.get_phone_defaults()
    assert phone["engine"] == "pipeline"
    assert phone["lang"] == "zh-HK"
    # untouched fields keep fallback
    assert phone["voice"] == fallback["phone"]["voice"]


# Scenario 3: partial update — other fields not overwritten
def test_partial_update_preserves_others(cfg_path, fallback):
    rc = RuntimeConfig(cfg_path, fallback)
    rc.update_web({"engine": "pipeline"})
    rc.update_web({"lang": "ja-JP"})
    web = rc.get_web_defaults()
    assert web["engine"] == "pipeline"
    assert web["lang"] == "ja-JP"
    assert web["voice"] == fallback["web"]["voice"]
    assert web["model"] == fallback["web"]["model"]


# Scenario 4: corrupt JSON — no error, reseed
def test_corrupt_json_reseeds(cfg_path, fallback):
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w") as f:
        f.write("{ this is not valid json")

    rc = RuntimeConfig(cfg_path, fallback)
    web = rc.get_web_defaults()
    assert web == fallback["web"]
    # file rewritten as valid JSON
    with open(cfg_path) as f:
        on_disk = json.load(f)
    assert on_disk["web"] == fallback["web"]


# Scenario 5: concurrent update + read does not deadlock
def test_concurrent_access_no_deadlock(cfg_path, fallback):
    rc = RuntimeConfig(cfg_path, fallback)
    errors: list = []

    def writer(value: str):
        try:
            for _ in range(20):
                rc.update_web({"lang": value})
        except Exception as e:
            errors.append(e)

    def reader():
        try:
            for _ in range(40):
                rc.get_web_defaults()
                rc.get_phone_defaults()
        except Exception as e:
            errors.append(e)

    threads = [
        threading.Thread(target=writer, args=("zh-HK",)),
        threading.Thread(target=writer, args=("en-US",)),
        threading.Thread(target=reader),
        threading.Thread(target=reader),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=5.0)
        assert not t.is_alive(), "thread did not terminate -> likely deadlock"
    assert errors == []
    # final state is one of the writer values
    assert rc.get_web_defaults()["lang"] in {"zh-HK", "en-US"}


# Bonus: missing field fallback per-segment
def test_missing_field_falls_back(cfg_path, fallback):
    os.makedirs(os.path.dirname(cfg_path), exist_ok=True)
    with open(cfg_path, "w") as f:
        json.dump({"web": {"engine": "pipeline"}, "phone": {}}, f)
    rc = RuntimeConfig(cfg_path, fallback)
    web = rc.get_web_defaults()
    assert web["engine"] == "pipeline"  # from disk
    assert web["lang"] == fallback["web"]["lang"]  # from fallback
