"""Unit tests for deploy/chime_provisioner_handler.py.

Uses botocore Stubber: every expected chime-sdk-voice call is queued explicitly,
and the Stubber raises if an *unexpected* call is made — which is exactly how we
prove the number-procurement red line (create-order / release are never queued,
so if the handler tried to call them the test would error).

The handler's pure helpers take an explicit client, so no AWS / no moto needed.
handler() itself is exercised with `send` + `make_client` monkeypatched.
"""

import os
import re
import sys
from pathlib import Path

import boto3
import pytest
from botocore.stub import Stubber

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "deploy"))
sys.path.insert(0, str(ROOT))

import chime_provisioner_handler as h  # noqa: E402


def _client():
    # A real client object (no network); Stubber intercepts all calls.
    return boto3.client(
        "chime-sdk-voice",
        region_name="us-east-1",
        aws_access_key_id="testing",
        aws_secret_access_key="testing",
    )


# ---------------------------------------------------------------------------
# find_vc_by_name / ensure_vc — idempotency
# ---------------------------------------------------------------------------
def test_ensure_vc_reuses_existing_by_name():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response(
            "list_voice_connectors",
            {"VoiceConnectors": [{"VoiceConnectorId": "vc-existing", "Name": "vbtest"}]},
        )
        vc_id = h.ensure_vc(c, "vbtest")
        assert vc_id == "vc-existing"
        stub.assert_no_pending_responses()  # NO create_voice_connector queued/called


def test_ensure_vc_creates_when_absent():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors", {"VoiceConnectors": []})
        stub.add_response(
            "create_voice_connector",
            {"VoiceConnector": {"VoiceConnectorId": "vc-new", "Name": "vbtest"}},
            {"Name": "vbtest", "AwsRegion": "us-east-1", "RequireEncryption": False},
        )
        assert h.ensure_vc(c, "vbtest") == "vc-new"
        stub.assert_no_pending_responses()


def test_find_vc_paginates():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response(
            "list_voice_connectors",
            {"VoiceConnectors": [{"VoiceConnectorId": "vc-1", "Name": "other"}],
             "NextToken": "tok"},
        )
        stub.add_response(
            "list_voice_connectors",
            {"VoiceConnectors": [{"VoiceConnectorId": "vc-2", "Name": "want"}]},
        )
        assert h.find_vc_by_name(c, "want") == "vc-2"
        stub.assert_no_pending_responses()


# ---------------------------------------------------------------------------
# set_origination — exact route shape
# ---------------------------------------------------------------------------
def test_set_origination_route_shape():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response(
            "put_voice_connector_origination",
            {},
            {
                "VoiceConnectorId": "vc-1",
                "Origination": {
                    "Routes": [
                        {"Host": "1.2.3.4", "Port": 5060, "Protocol": "UDP",
                         "Priority": 1, "Weight": 1}
                    ],
                    "Disabled": False,
                },
            },
        )
        h.set_origination(c, "vc-1", "1.2.3.4")
        stub.assert_no_pending_responses()


# ---------------------------------------------------------------------------
# Create — full path (create + origination + associate, force passthrough)
# ---------------------------------------------------------------------------
def test_create_full_path_with_number_force_false():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors", {"VoiceConnectors": []})
        stub.add_response(
            "create_voice_connector",
            {"VoiceConnector": {"VoiceConnectorId": "vc-new", "Name": "vbtest"}},
            {"Name": "vbtest", "AwsRegion": "us-east-1", "RequireEncryption": False},
        )
        stub.add_response("put_voice_connector_origination", {},
                          {"VoiceConnectorId": "vc-new", "Origination": {
                              "Routes": [{"Host": "1.2.3.4", "Port": 5060,
                                          "Protocol": "UDP", "Priority": 1, "Weight": 1}],
                              "Disabled": False}})
        stub.add_response(
            "associate_phone_numbers_with_voice_connector",
            {"PhoneNumberErrors": []},
            {"VoiceConnectorId": "vc-new", "E164PhoneNumbers": ["+15550001111"],
             "ForceAssociate": False},
        )
        pid, data = h.handle_create_update(
            c,
            {"Name": "vbtest", "OriginationIp": "1.2.3.4",
             "PhoneNumber": "+15550001111", "ForceAssociate": "false"},
            old_props=None,
        )
        assert pid == "vc-new"
        assert data["VoiceConnectorId"] == "vc-new"
        stub.assert_no_pending_responses()


def test_create_force_associate_true_passthrough():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors",
                          {"VoiceConnectors": [{"VoiceConnectorId": "vc-1", "Name": "vbtest"}]})
        stub.add_response("put_voice_connector_origination", {},
                          {"VoiceConnectorId": "vc-1", "Origination": {
                              "Routes": [{"Host": "9.9.9.9", "Port": 5060,
                                          "Protocol": "UDP", "Priority": 1, "Weight": 1}],
                              "Disabled": False}})
        stub.add_response(
            "associate_phone_numbers_with_voice_connector",
            {"PhoneNumberErrors": []},
            {"VoiceConnectorId": "vc-1", "E164PhoneNumbers": ["+1555"],
             "ForceAssociate": True},  # <- proves force passthrough
        )
        h.handle_create_update(
            c, {"Name": "vbtest", "OriginationIp": "9.9.9.9",
                "PhoneNumber": "+1555", "ForceAssociate": "true"}, old_props=None)
        stub.assert_no_pending_responses()


def test_create_no_number_skips_associate():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors", {"VoiceConnectors": []})
        stub.add_response(
            "create_voice_connector",
            {"VoiceConnector": {"VoiceConnectorId": "vc-new", "Name": "vbtest"}},
            {"Name": "vbtest", "AwsRegion": "us-east-1", "RequireEncryption": False})
        stub.add_response("put_voice_connector_origination", {},
                          {"VoiceConnectorId": "vc-new", "Origination": {
                              "Routes": [{"Host": "1.2.3.4", "Port": 5060,
                                          "Protocol": "UDP", "Priority": 1, "Weight": 1}],
                              "Disabled": False}})
        # NO associate queued — if handler called it, Stubber would raise.
        h.handle_create_update(
            c, {"Name": "vbtest", "OriginationIp": "1.2.3.4", "PhoneNumber": ""},
            old_props=None)
        stub.assert_no_pending_responses()


# ---------------------------------------------------------------------------
# Update — IP change re-origination; number change dis+assoc
# ---------------------------------------------------------------------------
def test_update_ip_change_reorigination():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors",
                          {"VoiceConnectors": [{"VoiceConnectorId": "vc-1", "Name": "vbtest"}]})
        stub.add_response("put_voice_connector_origination", {},
                          {"VoiceConnectorId": "vc-1", "Origination": {
                              "Routes": [{"Host": "5.6.7.8", "Port": 5060,
                                          "Protocol": "UDP", "Priority": 1, "Weight": 1}],
                              "Disabled": False}})
        # no number → no associate
        h.handle_create_update(
            c, {"Name": "vbtest", "OriginationIp": "5.6.7.8", "PhoneNumber": ""},
            old_props={"Name": "vbtest", "OriginationIp": "1.2.3.4", "PhoneNumber": ""})
        stub.assert_no_pending_responses()


def test_update_ip_unchanged_skips_reorigination():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors",
                          {"VoiceConnectors": [{"VoiceConnectorId": "vc-1", "Name": "vbtest"}]})
        # NO put_voice_connector_origination queued — IP unchanged.
        h.handle_create_update(
            c, {"Name": "vbtest", "OriginationIp": "1.2.3.4", "PhoneNumber": ""},
            old_props={"Name": "vbtest", "OriginationIp": "1.2.3.4", "PhoneNumber": ""})
        stub.assert_no_pending_responses()


def test_update_number_change_dis_then_assoc():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors",
                          {"VoiceConnectors": [{"VoiceConnectorId": "vc-1", "Name": "vbtest"}]})
        # IP unchanged → no origination
        stub.add_response(
            "disassociate_phone_numbers_from_voice_connector",
            {"PhoneNumberErrors": []},
            {"VoiceConnectorId": "vc-1", "E164PhoneNumbers": ["+1old"]})
        stub.add_response(
            "associate_phone_numbers_with_voice_connector",
            {"PhoneNumberErrors": []},
            {"VoiceConnectorId": "vc-1", "E164PhoneNumbers": ["+1new"],
             "ForceAssociate": False})
        h.handle_create_update(
            c, {"Name": "vbtest", "OriginationIp": "1.2.3.4", "PhoneNumber": "+1new"},
            old_props={"Name": "vbtest", "OriginationIp": "1.2.3.4", "PhoneNumber": "+1old"})
        stub.assert_no_pending_responses()


# ---------------------------------------------------------------------------
# Delete — retain vs delete; number always disassociated, NEVER released
# ---------------------------------------------------------------------------
def test_delete_retain_true_disassociates_but_keeps_vc():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response(
            "disassociate_phone_numbers_from_voice_connector",
            {"PhoneNumberErrors": []},
            {"VoiceConnectorId": "vc-1", "E164PhoneNumbers": ["+1555"]})
        # NO delete_voice_connector queued — retain=true.
        h.handle_delete(
            c, {"Name": "vbtest", "PhoneNumber": "+1555", "Retain": "true"}, "vc-1")
        stub.assert_no_pending_responses()


def test_delete_retain_false_deletes_vc():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response(
            "disassociate_phone_numbers_from_voice_connector",
            {"PhoneNumberErrors": []},
            {"VoiceConnectorId": "vc-1", "E164PhoneNumbers": ["+1555"]})
        stub.add_response("delete_voice_connector", {}, {"VoiceConnectorId": "vc-1"})
        h.handle_delete(
            c, {"Name": "vbtest", "PhoneNumber": "+1555", "Retain": "false"}, "vc-1")
        stub.assert_no_pending_responses()


def test_delete_no_vc_found_is_noop():
    c = _client()
    with Stubber(c) as stub:
        stub.add_response("list_voice_connectors", {"VoiceConnectors": []})
        pid, data = h.handle_delete(
            c, {"Name": "gone", "PhoneNumber": "", "Retain": "false"},
            "chime-voice-connector")
        assert pid == "chime-voice-connector"
        stub.assert_no_pending_responses()


# ---------------------------------------------------------------------------
# RED LINE: the handler module must not reference number-order/release APIs.
# (Static guard complementing the Stubber dynamic guard above.)
# ---------------------------------------------------------------------------
def test_no_number_order_or_release_apis_referenced():
    src = (ROOT / "deploy" / "chime_provisioner_handler.py").read_text()
    # Forbid actual CALLS (client.<api>(...)), not doc mentions of the names —
    # the module docstring deliberately explains the red line by naming them.
    for forbidden in (
        "create_phone_number_order",
        "release_phone_number",
        "delete_phone_number",
    ):
        assert (
            f".{forbidden}(" not in src
        ), f"forbidden number-lifecycle API call: client.{forbidden}(...)"


def test_truthy_helper():
    assert h._truthy("true") and h._truthy("True") and h._truthy("1")
    assert not h._truthy("false") and not h._truthy("") and not h._truthy("no")


# ---------------------------------------------------------------------------
# handler() entrypoint — always answers CFN (send monkeypatched)
# ---------------------------------------------------------------------------
class _Ctx:
    log_stream_name = "test-stream"


def test_handler_create_sends_success(monkeypatch):
    sent = {}
    monkeypatch.setattr(h, "send", lambda ev, ctx, status, **kw: sent.update(
        {"status": status, **kw}))
    c = _client()
    stub = Stubber(c)
    stub.add_response("list_voice_connectors", {"VoiceConnectors": []})
    stub.add_response(
        "create_voice_connector",
        {"VoiceConnector": {"VoiceConnectorId": "vc-new", "Name": "vbtest"}},
        {"Name": "vbtest", "AwsRegion": "us-east-1", "RequireEncryption": False})
    stub.add_response("put_voice_connector_origination", {},
                      {"VoiceConnectorId": "vc-new", "Origination": {
                          "Routes": [{"Host": "1.2.3.4", "Port": 5060, "Protocol": "UDP",
                                      "Priority": 1, "Weight": 1}], "Disabled": False}})
    stub.activate()
    monkeypatch.setattr(h, "make_client", lambda: c)
    h.handler(
        {"RequestType": "Create", "ResponseURL": "http://x", "StackId": "s",
         "RequestId": "r", "LogicalResourceId": "L",
         "ResourceProperties": {"Name": "vbtest", "OriginationIp": "1.2.3.4",
                                "PhoneNumber": ""}},
        _Ctx())
    assert sent["status"] == h.SUCCESS
    assert sent["physical_id"] == "vc-new"
    stub.assert_no_pending_responses()


def test_handler_failure_still_sends(monkeypatch):
    sent = {}
    monkeypatch.setattr(h, "send", lambda ev, ctx, status, **kw: sent.update(
        {"status": status, **kw}))

    def _boom():
        raise RuntimeError("boom")

    monkeypatch.setattr(h, "make_client", _boom)
    h.handler(
        {"RequestType": "Create", "ResponseURL": "http://x",
         "ResourceProperties": {"Name": "vbtest"}}, _Ctx())
    assert sent["status"] == h.FAILED


def test_handler_unknown_request_type_fails(monkeypatch):
    sent = {}
    monkeypatch.setattr(h, "send", lambda ev, ctx, status, **kw: sent.update(
        {"status": status, **kw}))
    monkeypatch.setattr(h, "make_client", lambda: _client())
    h.handler({"RequestType": "Frobnicate", "ResponseURL": "http://x",
               "ResourceProperties": {"Name": "x"}}, _Ctx())
    assert sent["status"] == h.FAILED


# ---------------------------------------------------------------------------
# Drift guard: the template's inline ZipFile must match this handler.
# T1 ships this SKIPPING until the inline block exists (T2 adds it); T2 flips it
# to a hard assert. We detect the inline block by the handler's docstring marker.
# ---------------------------------------------------------------------------
def _extract_inline_zipfile():
    import yaml

    tpl = (ROOT / "deploy" / "cloudformation.yaml").read_text()
    # CFN intrinsic tags (!Sub, !Ref, !GetAtt, !If ...) break plain yaml.safe_load.
    # The ZipFile is a literal block scalar; pull it out textually instead.
    m = re.search(r"ZipFile:\s*\|[\-+]?\s*\n((?:[ \t].*\n|\n)+)", tpl)
    if not m:
        return None
    block = m.group(1)
    # Dedent by the indentation of the first non-blank line.
    lines = block.splitlines()
    first = next((ln for ln in lines if ln.strip()), "")
    indent = len(first) - len(first.lstrip())
    return "\n".join(ln[indent:] if len(ln) >= indent else ln for ln in lines)


def _normalize(code):
    # Compare on the meaningful core: the chime API call surface + red-line.
    return re.sub(r"\s+", " ", code).strip()


def test_chime_inline_matches_handler():
    inline = _extract_inline_zipfile()
    if inline is None:
        pytest.skip("inline ZipFile not in cloudformation.yaml yet (added in T2)")
    handler_src = (ROOT / "deploy" / "chime_provisioner_handler.py").read_text()
    # The inline copy must contain the same core helper signatures + the route
    # shape + the red-line absence. We assert the key invariants rather than a
    # brittle byte match (the inline may add an env-shim header).
    for marker in (
        "def set_origination(",
        "def assoc_number(",
        "def disassoc_number(",
        "def handle_create_update(",
        "def handle_delete(",
        '"Protocol": "UDP"',
    ):
        assert marker in inline, f"inline ZipFile missing: {marker}"
    for forbidden in ("create_phone_number_order", "release_phone_number"):
        assert forbidden not in inline, f"inline has forbidden API: {forbidden}"
    # sanity: handler.py has the same markers (keeps the two in lock-step)
    for marker in ("def set_origination(", "def handle_delete("):
        assert marker in handler_src
