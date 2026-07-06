"""Nova Sonic voice table tests for bot.py (task b4f4f827 — T4).

Hermetic (no network, no boto3 calls): only inspects the module-level
``NOVA_SONIC_VOICES`` table, the ``NOVA_SONIC_VOICE_ALIASES`` migration map,
and the alias+fallback resolution logic shared by the two voice-resolution
points (``_build_nova_sonic_pipeline`` and the ``/ws`` entry).
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


# The official AWS Nova 2 Sonic 16-voice roster (sonic-language-support.html).
EXPECTED_VOICES = {
    "tiffany", "matthew", "amy", "olivia", "kiara", "arjun",
    "ambre", "florian", "beatrice", "lorenzo", "tina", "lennart",
    "lupe", "carlos", "carolina", "leo",
}
REQUIRED_FIELDS = {"label", "gender", "locale", "lang_label"}


def _resolve(bot_mod, voice):
    """Mirror the alias-then-fallback logic used at both resolution points."""
    voice = bot_mod.NOVA_SONIC_VOICE_ALIASES.get(voice, voice)
    return voice if voice in bot_mod.NOVA_SONIC_VOICES else bot_mod.DEFAULT_NOVA_SONIC_VOICE


def test_all_16_voices_present(bot_mod):
    assert set(bot_mod.NOVA_SONIC_VOICES) == EXPECTED_VOICES
    assert len(bot_mod.NOVA_SONIC_VOICES) == 16


def test_each_voice_has_required_fields(bot_mod):
    for vid, v in bot_mod.NOVA_SONIC_VOICES.items():
        missing = REQUIRED_FIELDS - set(v)
        assert not missing, f"{vid} missing fields: {missing}"
        assert v["gender"] in ("F", "M"), vid
        assert "-" in v["locale"], vid
        assert v["label"], vid


def test_polyglot_flags(bot_mod):
    voices = bot_mod.NOVA_SONIC_VOICES
    # Only tiffany + matthew are polyglot.
    assert voices["tiffany"].get("polyglot") is True
    assert voices["matthew"].get("polyglot") is True
    for vid, v in voices.items():
        if vid not in ("tiffany", "matthew"):
            assert not v.get("polyglot"), vid


def test_kiara_arjun_dual_lang_label(bot_mod):
    voices = bot_mod.NOVA_SONIC_VOICES
    assert voices["kiara"]["lang_label"] == "English (IN) / Hindi"
    assert voices["arjun"]["lang_label"] == "English (IN) / Hindi"
    assert voices["kiara"]["locale"] == "en-IN"
    assert voices["arjun"]["locale"] == "en-IN"


def test_alias_map_resolves_old_ids(bot_mod):
    assert bot_mod.NOVA_SONIC_VOICE_ALIASES == {
        "marie": "ambre",
        "sofia": "lupe",
        "ana": "carolina",
    }
    # greta was never in the old 10-voice dict (tech_design B.1 Rev 2) — not aliased.
    assert "greta" not in bot_mod.NOVA_SONIC_VOICE_ALIASES


def test_aliases_point_at_real_voices(bot_mod):
    for old, new in bot_mod.NOVA_SONIC_VOICE_ALIASES.items():
        assert new in bot_mod.NOVA_SONIC_VOICES, f"alias {old}->{new} dangling"
        assert old not in bot_mod.NOVA_SONIC_VOICES, f"alias {old} should be retired"


def test_resolution_aliased(bot_mod):
    assert _resolve(bot_mod, "marie") == "ambre"
    assert _resolve(bot_mod, "sofia") == "lupe"
    assert _resolve(bot_mod, "ana") == "carolina"


def test_resolution_valid_passthrough(bot_mod):
    assert _resolve(bot_mod, "lorenzo") == "lorenzo"
    assert _resolve(bot_mod, "tiffany") == "tiffany"


def test_resolution_unknown_falls_back_to_default(bot_mod):
    assert bot_mod.DEFAULT_NOVA_SONIC_VOICE in bot_mod.NOVA_SONIC_VOICES
    assert _resolve(bot_mod, "does-not-exist") == bot_mod.DEFAULT_NOVA_SONIC_VOICE
    # An old id that is neither valid nor aliased also falls back.
    assert _resolve(bot_mod, "greta") == bot_mod.DEFAULT_NOVA_SONIC_VOICE
