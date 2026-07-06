"""Unit tests for bot._list_chime_vc_numbers (admin VC↔phone-number view).

Uses botocore Stubber so no AWS / no moto: we queue exactly the chime-sdk-voice
ListVoiceConnectors + ListPhoneNumbers responses and assert the join. The
function builds its own client internally, so we monkeypatch boto3.client to
hand it our stubbed client.
"""

import sys
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import bot  # noqa: E402


def _stubbed(monkeypatch):
    """Return (client, stubber); patch bot's boto3.client to return this client
    regardless of the args _list_chime_vc_numbers passes (service/region/config)."""
    client = boto3.client(
        "chime-sdk-voice",
        region_name="us-east-1",
        aws_access_key_id="t",
        aws_secret_access_key="t",
    )
    stub = Stubber(client)
    monkeypatch.setattr(bot.boto3, "client", lambda *a, **k: client)
    return client, stub


def test_join_two_vcs_two_numbers(monkeypatch):
    client, stub = _stubbed(monkeypatch)
    stub.add_response(
        "list_voice_connectors",
        {"VoiceConnectors": [
            {"VoiceConnectorId": "vc-a", "Name": "yue-test"},
            {"VoiceConnectorId": "vc-b", "Name": "nova-bot-test"},
        ]},
    )
    stub.add_response(
        "list_phone_numbers",
        {"PhoneNumbers": [
            {"E164PhoneNumber": "+15550001111", "Status": "Assigned",
             "Associations": [{"Name": "VoiceConnectorId", "Value": "vc-a"}]},
            {"E164PhoneNumber": "+15550002222", "Status": "Assigned",
             "Associations": [{"Name": "VoiceConnectorId", "Value": "vc-b"}]},
        ]},
    )
    with stub:
        out = bot._list_chime_vc_numbers()
    assert out["error"] is None
    rows = {r["e164"]: r for r in out["voice_connectors"]}
    assert rows["+15550001111"]["voice_connector_id"] == "vc-a"
    assert rows["+15550001111"]["voice_connector_name"] == "yue-test"
    assert rows["+15550001111"]["status"] == "Assigned"
    assert rows["+15550002222"]["voice_connector_name"] == "nova-bot-test"
    stub.assert_no_pending_responses()


def test_number_with_no_association_has_null_vc(monkeypatch):
    client, stub = _stubbed(monkeypatch)
    stub.add_response("list_voice_connectors", {"VoiceConnectors": [
        {"VoiceConnectorId": "vc-a", "Name": "yue-test"}]})
    stub.add_response("list_phone_numbers", {"PhoneNumbers": [
        {"E164PhoneNumber": "+19998887777", "Status": "Unassigned", "Associations": []}]})
    with stub:
        out = bot._list_chime_vc_numbers()
    # the unassociated number row + the number-less vc-a row
    by_e164 = {r["e164"]: r for r in out["voice_connectors"]}
    assert by_e164["+19998887777"]["voice_connector_id"] is None
    assert by_e164["+19998887777"]["voice_connector_name"] is None
    # vc-a had no number → a row with e164 None
    vc_rows = [r for r in out["voice_connectors"] if r["voice_connector_id"] == "vc-a"]
    assert vc_rows and vc_rows[0]["e164"] is None
    stub.assert_no_pending_responses()


def test_vc_without_number_is_listed(monkeypatch):
    client, stub = _stubbed(monkeypatch)
    stub.add_response("list_voice_connectors", {"VoiceConnectors": [
        {"VoiceConnectorId": "vc-empty", "Name": "no-number-vc"}]})
    stub.add_response("list_phone_numbers", {"PhoneNumbers": []})
    with stub:
        out = bot._list_chime_vc_numbers()
    assert out["error"] is None
    assert out["voice_connectors"] == [
        {"voice_connector_id": "vc-empty", "voice_connector_name": "no-number-vc",
         "e164": None, "status": None}]
    stub.assert_no_pending_responses()


def test_multi_vc_join_does_not_cross(monkeypatch):
    client, stub = _stubbed(monkeypatch)
    stub.add_response("list_voice_connectors", {"VoiceConnectors": [
        {"VoiceConnectorId": "vc-a", "Name": "A"},
        {"VoiceConnectorId": "vc-b", "Name": "B"}]})
    stub.add_response("list_phone_numbers", {"PhoneNumbers": [
        {"E164PhoneNumber": "+1111", "Status": "Assigned",
         "Associations": [{"Name": "VoiceConnectorId", "Value": "vc-b"}]}]})
    with stub:
        out = bot._list_chime_vc_numbers()
    row = next(r for r in out["voice_connectors"] if r["e164"] == "+1111")
    assert row["voice_connector_id"] == "vc-b" and row["voice_connector_name"] == "B"
    # vc-a (no number) still listed with e164 None, NOT bound to +1111
    assert any(r["voice_connector_id"] == "vc-a" and r["e164"] is None
               for r in out["voice_connectors"])
    stub.assert_no_pending_responses()


def test_pagination_both_calls(monkeypatch):
    client, stub = _stubbed(monkeypatch)
    # VCs across 2 pages
    stub.add_response("list_voice_connectors",
                      {"VoiceConnectors": [{"VoiceConnectorId": "vc-a", "Name": "A"}],
                       "NextToken": "t1"})
    stub.add_response("list_voice_connectors",
                      {"VoiceConnectors": [{"VoiceConnectorId": "vc-b", "Name": "B"}]})
    # numbers across 2 pages
    stub.add_response("list_phone_numbers",
                      {"PhoneNumbers": [{"E164PhoneNumber": "+1", "Status": "Assigned",
                                         "Associations": [{"Name": "VoiceConnectorId", "Value": "vc-a"}]}],
                       "NextToken": "t2"})
    stub.add_response("list_phone_numbers",
                      {"PhoneNumbers": [{"E164PhoneNumber": "+2", "Status": "Assigned",
                                         "Associations": [{"Name": "VoiceConnectorId", "Value": "vc-b"}]}]})
    with stub:
        out = bot._list_chime_vc_numbers()
    e = {r["e164"]: r["voice_connector_name"] for r in out["voice_connectors"] if r["e164"]}
    assert e == {"+1": "A", "+2": "B"}
    stub.assert_no_pending_responses()


def test_chime_error_degrades_to_empty(monkeypatch):
    client, stub = _stubbed(monkeypatch)
    stub.add_client_error("list_voice_connectors", service_error_code="AccessDeniedException",
                          service_message="not authorized", http_status_code=403)
    with stub:
        out = bot._list_chime_vc_numbers()
    assert out["voice_connectors"] == []
    assert out["error"] and "AccessDenied" in out["error"]


def test_client_construction_failure_degrades(monkeypatch):
    # boto3.client itself raising must still degrade, not propagate.
    def _boom(*a, **k):
        raise RuntimeError("no creds")
    monkeypatch.setattr(bot.boto3, "client", _boom)
    out = bot._list_chime_vc_numbers()
    assert out["voice_connectors"] == []
    assert "no creds" in out["error"]
