"""CFN custom-resource handler that provisions a Chime SDK Voice Connector.

Backs the ``Custom::ChimeVoiceConnector`` resource in
``deploy/cloudformation.yaml``. CloudFormation has no native
``AWS::Chime::VoiceConnector`` type, so this Lambda drives the
``chime-sdk-voice`` API to:

  * create (or idempotently reuse) a Voice Connector by name,
  * point its origination route at the EC2 public IP (UDP 5060),
  * associate an *already-owned* phone number.

HARD RED LINE — number lifecycle:
  This handler only ``associate``/``disassociate`` phone numbers. It NEVER
  orders, creates, or releases a number (no ``create-phone-number-order`` /
  ``release-phone-number`` / ``delete-phone-number``). Phone numbers are scarce
  stateful resources; ordering/releasing them from a CFN delete/rollback would
  lose the number. Number procurement stays manual.

This module is the source of truth; the template's inline ``Code.ZipFile`` is
kept byte-for-byte in sync and guarded by ``test_chime_inline_matches_handler``.

VC lives only in ``us-east-1`` (the client region is hard-coded).
"""

import json
import urllib.request

REGION = "us-east-1"


# ---------------------------------------------------------------------------
# Minimal cfnresponse (inlined so the Lambda needs no extra layer/dependency).
# ---------------------------------------------------------------------------
SUCCESS = "SUCCESS"
FAILED = "FAILED"


def send(event, context, status, data=None, physical_id=None, reason=None):
    """POST a CloudFormation custom-resource response to the pre-signed URL."""
    body = {
        "Status": status,
        "Reason": reason
        or "See CloudWatch Log Stream: "
        + (getattr(context, "log_stream_name", "") or "n/a"),
        "PhysicalResourceId": physical_id or "chime-voice-connector",
        "StackId": event.get("StackId", ""),
        "RequestId": event.get("RequestId", ""),
        "LogicalResourceId": event.get("LogicalResourceId", ""),
        "NoEcho": False,
        "Data": data or {},
    }
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        event["ResponseURL"],
        data=payload,
        method="PUT",
        headers={"content-type": "", "content-length": str(len(payload))},
    )
    urllib.request.urlopen(req)  # noqa: S310 — URL is the CFN-provided callback


# ---------------------------------------------------------------------------
# chime-sdk-voice helpers (pure; take an explicit client so they unit-test with
# a botocore Stubber — no AWS, no moto needed).
# ---------------------------------------------------------------------------
def find_vc_by_name(client, name):
    """Return the VoiceConnectorId of the VC named ``name``, or None.

    Paginates ``list_voice_connectors``; match is exact on ``Name``.
    """
    next_token = None
    while True:
        kwargs = {"MaxResults": 99}
        if next_token:
            kwargs["NextToken"] = next_token
        resp = client.list_voice_connectors(**kwargs)
        for vc in resp.get("VoiceConnectors", []):
            if vc.get("Name") == name:
                return vc.get("VoiceConnectorId")
        next_token = resp.get("NextToken")
        if not next_token:
            return None


def ensure_vc(client, name):
    """Idempotently return a VoiceConnectorId for ``name`` (reuse else create)."""
    existing = find_vc_by_name(client, name)
    if existing:
        print(f"[chime] reusing existing VoiceConnector {existing} (name={name})")
        return existing
    resp = client.create_voice_connector(
        Name=name, AwsRegion=REGION, RequireEncryption=False
    )
    vc_id = resp["VoiceConnector"]["VoiceConnectorId"]
    print(f"[chime] created VoiceConnector {vc_id} (name={name})")
    return vc_id


def set_origination(client, vc_id, ip):
    """Point the VC's origination at ``ip``:5060 over UDP (single route)."""
    client.put_voice_connector_origination(
        VoiceConnectorId=vc_id,
        Origination={
            "Routes": [
                {
                    "Host": ip,
                    "Port": 5060,
                    "Protocol": "UDP",
                    "Priority": 1,
                    "Weight": 1,
                }
            ],
            "Disabled": False,
        },
    )
    print(f"[chime] origination set: {vc_id} -> {ip}:5060/UDP")


def assoc_number(client, vc_id, e164, force=False):
    """Associate an already-owned number. NEVER orders/creates a number."""
    client.associate_phone_numbers_with_voice_connector(
        VoiceConnectorId=vc_id,
        E164PhoneNumbers=[e164],
        ForceAssociate=bool(force),
    )
    print(f"[chime] associated {e164} -> {vc_id} (force={bool(force)})")


def disassoc_number(client, vc_id, e164):
    """Disassociate a number (it stays in the account; NEVER released)."""
    client.disassociate_phone_numbers_from_voice_connector(
        VoiceConnectorId=vc_id,
        E164PhoneNumbers=[e164],
    )
    print(f"[chime] disassociated {e164} from {vc_id} (number kept in account)")


def _truthy(v):
    return str(v).strip().lower() in ("1", "true", "yes", "on")


# ---------------------------------------------------------------------------
# Per-event logic (return (physical_id, data) or raise).
# ---------------------------------------------------------------------------
def handle_create_update(client, props, old_props=None):
    name = props["Name"]
    ip = props.get("OriginationIp") or ""
    number = (props.get("PhoneNumber") or "").strip()
    force = _truthy(props.get("ForceAssociate", "false"))

    vc_id = ensure_vc(client, name)

    # Origination: (re)set on create, or on update when the IP changed.
    old_ip = (old_props or {}).get("OriginationIp")
    if old_props is None or old_ip != ip:
        if ip:
            set_origination(client, vc_id, ip)

    # Number association: associate the (new) number; on update where the number
    # changed, disassociate the old one first.
    old_number = ((old_props or {}).get("PhoneNumber") or "").strip()
    if old_props is not None and old_number and old_number != number:
        try:
            disassoc_number(client, vc_id, old_number)
        except Exception as e:  # noqa: BLE001 — best-effort cleanup of old number
            print(f"[chime] disassociate old number {old_number} ignored: {e}")
    if number and number != old_number:
        assoc_number(client, vc_id, number, force=force)

    return vc_id, {"VoiceConnectorId": vc_id, "OriginationIp": ip}


def handle_delete(client, props, physical_id):
    name = props["Name"]
    number = (props.get("PhoneNumber") or "").strip()
    retain = _truthy(props.get("Retain", "true"))

    # Prefer the stored physical id (a real "vc-..." id from Create); fall back
    # to a name lookup when it's the pre-create sentinel or missing.
    if physical_id and physical_id.startswith("vc-"):
        vc_id = physical_id
    else:
        vc_id = find_vc_by_name(client, name)

    if not vc_id:
        print(f"[chime] delete: no VC found for name={name}; nothing to do")
        return physical_id or "chime-voice-connector", {}

    # ALWAYS disassociate the number first (it returns to the account, free to
    # re-associate elsewhere). The number is never released/deleted.
    if number:
        try:
            disassoc_number(client, vc_id, number)
        except Exception as e:  # noqa: BLE001 — idempotent delete
            print(f"[chime] delete: disassociate {number} ignored: {e}")

    if retain:
        print(f"[chime] delete: RETAIN policy — leaving VC {vc_id} in place")
    else:
        try:
            client.delete_voice_connector(VoiceConnectorId=vc_id)
            print(f"[chime] delete: removed VC {vc_id}")
        except Exception as e:  # noqa: BLE001 — idempotent delete
            print(f"[chime] delete: delete_voice_connector ignored: {e}")

    return vc_id, {}


# ---------------------------------------------------------------------------
# Lambda entrypoint.
# ---------------------------------------------------------------------------
def make_client():
    import boto3

    return boto3.client("chime-sdk-voice", region_name=REGION)


def handler(event, context):
    request_type = event.get("RequestType")
    props = event.get("ResourceProperties", {}) or {}
    old_props = event.get("OldResourceProperties") or None
    physical_id = event.get("PhysicalResourceId")
    print(f"[chime] {request_type} props={json.dumps(props)}")
    try:
        client = make_client()
        if request_type in ("Create", "Update"):
            pid, data = handle_create_update(
                client, props, old_props if request_type == "Update" else None
            )
            send(event, context, SUCCESS, data=data, physical_id=pid)
        elif request_type == "Delete":
            pid, data = handle_delete(client, props, physical_id)
            send(event, context, SUCCESS, data=data, physical_id=pid)
        else:
            send(
                event,
                context,
                FAILED,
                reason=f"unknown RequestType: {request_type}",
                physical_id=physical_id,
            )
    except Exception as e:  # noqa: BLE001 — must always answer CFN
        print(f"[chime] ERROR: {e}")
        send(event, context, FAILED, reason=str(e), physical_id=physical_id)
