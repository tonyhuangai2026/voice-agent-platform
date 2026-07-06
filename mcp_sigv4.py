"""AWS SigV4 auth for config-driven MCP servers (e.g. Bedrock AgentCore).

This module adds SigV4 request signing to pipecat's MCP streamable-HTTP client
**without patching pipecat**. The mechanism, in two pieces:

1. :class:`SigV4HttpxAuth` — an ``httpx.Auth`` subclass whose ``auth_flow``
   signs the outgoing httpx request with botocore's ``SigV4Auth`` (credentials
   from the boto3 default chain — env / profile / EC2 instance role) and copies
   the resulting ``Authorization`` / ``X-Amz-Date`` / ``X-Amz-Security-Token``
   headers back onto the request before yielding it.

2. :func:`make_sigv4_streamable_params` — a tiny ``StreamableHttpParameters``
   subclass whose ``model_dump()`` returns the usual five fields **plus**
   ``auth=<SigV4HttpxAuth>``. pipecat's ``MCPClient.start()`` does
   ``streamablehttp_client(**self._server_params.model_dump())`` and the
   underlying ``mcp.client.streamable_http.streamablehttp_client`` natively
   accepts an ``auth: httpx.Auth`` kwarg — so the signer is injected with zero
   pipecat changes and we reuse pipecat's full SSE / double-parse /
   FunctionSchema handling. ``MCPClient.__init__`` accepts the subclass because
   its type check is ``isinstance(server_params, StreamableHttpParameters)``.

All heavy imports (boto3/botocore/httpx/mcp) are lazy so importing this module
(and bot.py) never hard-requires them; a missing dep / missing credentials is
surfaced as a clear exception the caller degrades on. Because ``httpx.Auth`` is
a concrete class (not duck-typed by httpx — its client does
``isinstance(auth, httpx.Auth)``), the signer is built as a *real* subclass
lazily via :func:`build_sigv4_httpx_auth`.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_SERVICE = "bedrock-agentcore"
DEFAULT_REGION = "us-east-1"


class MissingCredentialsError(RuntimeError):
    """Raised when the boto3 default credential chain yields no credentials.

    The caller (bot.py) catches this to skip the sigv4 server with a WARNING
    rather than crashing the call.
    """


def resolve_credentials():
    """Return frozen botocore credentials from the boto3 default chain.

    Raises :class:`MissingCredentialsError` if none are available.
    """
    import boto3  # lazy

    creds = boto3.Session().get_credentials()
    if creds is None:
        raise MissingCredentialsError(
            "no AWS credentials in the default chain (env / profile / instance role)"
        )
    # get_frozen_credentials() snapshots access key / secret / token so the
    # signer works against a stable view even if the chain refreshes mid-flow.
    return creds.get_frozen_credentials()


def sign_request_headers(credentials, service: str, region: str, request) -> dict[str, str]:
    """SigV4-sign an httpx ``request`` and return the headers to copy back.

    Pure-ish helper (no httpx import needed): builds a botocore ``AWSRequest``
    from the httpx request's method / url / body bytes / headers, calls
    ``SigV4Auth.add_auth``, and returns the SigV4 headers (Authorization,
    X-Amz-Date, and — for temporary creds — X-Amz-Security-Token, plus any
    X-Amz-Content-SHA256). Signs the actual body bytes with the correct
    host/path so the signature matches what the server receives.

    Only a small allowlist of stable headers is fed into the signature.
    Signing the *full* httpx header bag breaks SigV4: httpx adds/rewrites
    hop-by-hop headers (``connection``, ``accept-encoding``, ``content-length``,
    ``user-agent``…) AFTER auth_flow runs, so any of those that botocore folded
    into ``SignedHeaders`` no longer match the bytes on the wire and the service
    rejects with "signature we calculated does not match". botocore derives
    ``host`` from the URL itself, so the minimal set below is sufficient and
    stable across the MCP initialize / tools/list / tools/call handshake.
    """
    from botocore.auth import SigV4Auth  # lazy
    from botocore.awsrequest import AWSRequest  # lazy

    # request.read() returns the encoded body bytes (httpx buffers it because
    # SigV4HttpxAuth sets requires_request_body = True).
    body = request.read()
    _SIGNED_HEADER_ALLOWLIST = ("content-type", "accept")
    sign_headers = {
        k: v
        for k, v in request.headers.items()
        if k.lower() in _SIGNED_HEADER_ALLOWLIST
    }
    aws_request = AWSRequest(
        method=request.method,
        url=str(request.url),
        data=body,
        headers=sign_headers,
    )
    SigV4Auth(credentials, service, region).add_auth(aws_request)

    signed = aws_request.headers
    out: dict[str, str] = {}
    for key in (
        "Authorization",
        "X-Amz-Date",
        "X-Amz-Security-Token",
        "X-Amz-Content-SHA256",
    ):
        if key in signed:
            out[key] = signed[key]
    return out


# Cache the dynamically-built httpx.Auth subclass so repeated connects don't
# rebuild the class object.
_AUTH_CLASS_CACHE: type | None = None


def _sigv4_httpx_auth_class() -> type:
    """Build (once) and return a real ``httpx.Auth`` subclass that signs with
    SigV4. Defined lazily so httpx is only imported when sigv4 is used."""
    global _AUTH_CLASS_CACHE
    if _AUTH_CLASS_CACHE is not None:
        return _AUTH_CLASS_CACHE

    import httpx  # lazy

    class SigV4HttpxAuth(httpx.Auth):
        """httpx.Auth that signs each request with AWS SigV4.

        httpx checks ``requires_request_body`` to decide whether to buffer the
        body before calling ``auth_flow`` — we need the bytes to sign, so it is
        True. ``auth_flow`` signs and copies headers back, then yields.
        """

        requires_request_body = True
        requires_response_body = False

        def __init__(self, credentials, *, service: str, region: str):
            self._credentials = credentials
            self._service = service
            self._region = region

        def auth_flow(self, request):
            headers = sign_request_headers(
                self._credentials, self._service, self._region, request
            )
            for key, value in headers.items():
                request.headers[key] = value
            yield request

    _AUTH_CLASS_CACHE = SigV4HttpxAuth
    return SigV4HttpxAuth


def build_sigv4_httpx_auth(service: str, region: str, credentials=None):
    """Construct a SigV4 ``httpx.Auth``. Resolves credentials from the boto3
    default chain when ``credentials`` is None (raising MissingCredentialsError
    so the caller can skip the server)."""
    if credentials is None:
        credentials = resolve_credentials()
    cls = _sigv4_httpx_auth_class()
    return cls(credentials, service=service, region=region)


def make_sigv4_streamable_params(
    url: str,
    *,
    service: str = DEFAULT_SERVICE,
    region: str = DEFAULT_REGION,
    headers: dict[str, str] | None = None,
    credentials=None,
):
    """Return a ``StreamableHttpParameters`` subclass instance whose
    ``model_dump()`` carries an extra ``auth=SigV4HttpxAuth(...)`` field.

    Hand the result to ``pipecat.services.mcp_service.MCPClient`` exactly like
    a normal ``StreamableHttpParameters``: ``MCPClient.start()`` splats the dump
    into ``streamablehttp_client(**dump)`` and the ``auth`` kwarg signs every
    HTTP request. Maximum reuse of pipecat's transport — no pipecat patch.

    Raises :class:`MissingCredentialsError` if credentials cannot be resolved.
    """
    from mcp.client.session_group import StreamableHttpParameters  # lazy

    auth = build_sigv4_httpx_auth(service, region, credentials=credentials)

    class _SigV4StreamableParams(StreamableHttpParameters):
        """StreamableHttpParameters that injects ``auth`` into model_dump().

        The SigV4 auth object is stashed as a plain attribute (NOT a pydantic
        field, via object.__setattr__) so it survives without model-config
        changes, then merged into the dict ``model_dump`` produces.
        """

        def model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:  # type: ignore[override]
            data = super().model_dump(*args, **kwargs)
            data["auth"] = self._sigv4_auth
            return data

    params = _SigV4StreamableParams(url=url, headers=headers or None)
    object.__setattr__(params, "_sigv4_auth", auth)
    return params
