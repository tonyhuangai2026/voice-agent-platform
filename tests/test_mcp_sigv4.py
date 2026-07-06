"""Unit tests for mcp_sigv4 — SigV4 request signing + params injection.

Hermetic: no real AgentCore / network calls (that's T3). Credentials are a
fake frozen-credentials object so SigV4Auth produces a deterministic signature
without touching the AWS metadata service.
"""

from __future__ import annotations

import httpx
import pytest

import mcp_sigv4


class _FakeFrozenCreds:
    """Mimics botocore frozen credentials (access_key/secret_key/token)."""

    access_key = "AKIDEXAMPLE"
    secret_key = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
    token = None


class _FakeTempCreds(_FakeFrozenCreds):
    token = "FAKE-SESSION-TOKEN"


# ---------------------------------------------------------------------------
# SigV4HttpxAuth — signs requests
# ---------------------------------------------------------------------------
def test_sigv4_auth_adds_authorization_and_date():
    auth = mcp_sigv4.build_sigv4_httpx_auth(
        "bedrock-agentcore", "us-east-1", credentials=_FakeFrozenCreds()
    )
    # It must be a real httpx.Auth subclass (httpx does isinstance, not duck).
    assert isinstance(auth, httpx.Auth)

    req = httpx.Request(
        "POST",
        "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/foo/invocations?qualifier=DEFAULT",
        json={"jsonrpc": "2.0", "method": "tools/list"},
    )
    signed = next(auth.auth_flow(req))
    assert "Authorization" in signed.headers
    assert signed.headers["Authorization"].startswith("AWS4-HMAC-SHA256 ")
    assert "AKIDEXAMPLE" in signed.headers["Authorization"]
    assert "X-Amz-Date" in signed.headers
    # No session token header when using long-lived credentials.
    assert "X-Amz-Security-Token" not in signed.headers


def test_sigv4_auth_adds_security_token_for_temp_creds():
    auth = mcp_sigv4.build_sigv4_httpx_auth(
        "bedrock-agentcore", "us-east-1", credentials=_FakeTempCreds()
    )
    req = httpx.Request("POST", "https://bedrock-agentcore.us-east-1.amazonaws.com/x", content=b"{}")
    signed = next(auth.auth_flow(req))
    assert signed.headers["X-Amz-Security-Token"] == "FAKE-SESSION-TOKEN"


def test_sigv4_signature_covers_body():
    # Different bodies -> different signatures (the body is signed).
    auth = mcp_sigv4.build_sigv4_httpx_auth("bedrock-agentcore", "us-east-1", credentials=_FakeFrozenCreds())
    r1 = httpx.Request("POST", "https://x.amazonaws.com/y", content=b'{"a":1}')
    r2 = httpx.Request("POST", "https://x.amazonaws.com/y", content=b'{"a":2}')
    s1 = next(auth.auth_flow(r1)).headers["Authorization"]
    s2 = next(auth.auth_flow(r2)).headers["Authorization"]
    assert s1 != s2


def test_signed_headers_excludes_volatile_httpx_headers():
    """Regression: signing the FULL httpx header bag breaks SigV4.

    httpx appends/rewrites hop-by-hop headers (content-length, accept-encoding,
    connection, user-agent, host) AFTER auth_flow runs. If any of those land in
    SignedHeaders, the on-the-wire bytes no longer match and AgentCore returns
    403 "signature we calculated does not match". Only content-type + accept
    (both stable across the MCP handshake) may be signed; host is derived by
    botocore from the URL. This caused every bot-path connect to 403 until the
    allowlist was added to sign_request_headers.
    """
    auth = mcp_sigv4.build_sigv4_httpx_auth(
        "bedrock-agentcore", "us-east-1", credentials=_FakeFrozenCreds()
    )
    # httpx.Request auto-populates host / content-length / accept-encoding /
    # connection / user-agent — exactly the volatile headers that must NOT be
    # folded into the signature.
    req = httpx.Request(
        "POST",
        "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/foo/invocations?qualifier=DEFAULT",
        content=b'{"jsonrpc":"2.0","method":"tools/list"}',
        headers={"Content-Type": "application/json",
                 "Accept": "application/json, text/event-stream"},
    )
    auth_header = next(auth.auth_flow(req)).headers["Authorization"]
    # Authorization looks like: AWS4-HMAC-SHA256 Credential=..., SignedHeaders=a;b;c, Signature=...
    signed_part = [p for p in auth_header.split(", ") if p.startswith("SignedHeaders=")][0]
    signed_headers = set(signed_part.split("=", 1)[1].split(";"))
    assert "content-type" in signed_headers
    assert "accept" in signed_headers
    for volatile in ("content-length", "accept-encoding", "connection", "user-agent"):
        assert volatile not in signed_headers, f"{volatile} must not be signed"


# ---------------------------------------------------------------------------
# make_sigv4_streamable_params — pipecat-compatible params w/ injected auth
# ---------------------------------------------------------------------------
def test_params_is_streamable_subclass_with_auth_in_dump():
    from mcp.client.session_group import StreamableHttpParameters

    params = mcp_sigv4.make_sigv4_streamable_params(
        "https://bedrock-agentcore.us-east-1.amazonaws.com/runtimes/foo/invocations?qualifier=DEFAULT",
        credentials=_FakeFrozenCreds(),
    )
    # isinstance passes -> pipecat MCPClient.__init__ accepts it unchanged.
    assert isinstance(params, StreamableHttpParameters)
    dump = params.model_dump()
    # model_dump carries the standard fields PLUS auth.
    assert dump["url"].startswith("https://bedrock-agentcore")
    assert isinstance(dump["auth"], httpx.Auth)


def test_params_accepted_by_pipecat_mcpclient():
    from pipecat.services.mcp_service import MCPClient

    params = mcp_sigv4.make_sigv4_streamable_params("https://x.amazonaws.com/mcp", credentials=_FakeFrozenCreds())
    # Must not raise TypeError (the __init__ isinstance check passes).
    MCPClient(server_params=params)


# ---------------------------------------------------------------------------
# Graceful degradation when credentials are missing
# ---------------------------------------------------------------------------
def test_missing_credentials_raises_typed_error(monkeypatch):
    import boto3

    class _NoCredSession:
        def get_credentials(self):
            return None

    monkeypatch.setattr(boto3, "Session", lambda *a, **k: _NoCredSession())
    with pytest.raises(mcp_sigv4.MissingCredentialsError):
        mcp_sigv4.resolve_credentials()
    # And the higher-level builder surfaces the same typed error.
    with pytest.raises(mcp_sigv4.MissingCredentialsError):
        mcp_sigv4.make_sigv4_streamable_params("https://x.amazonaws.com/mcp")
