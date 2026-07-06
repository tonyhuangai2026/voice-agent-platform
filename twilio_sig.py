"""Twilio webhook request-signature verification (``X-Twilio-Signature``).

Standard-library only (``hmac`` / ``hashlib`` / ``base64``) — deliberately does
NOT depend on the ``twilio`` SDK. Audio / μ-law / resampling is out of scope
here; pipecat's built-in ``TwilioFrameSerializer`` handles media.

Twilio's algorithm (https://www.twilio.com/docs/usage/security):

    1. Start with the *full* URL Twilio requested, exactly as Twilio saw it
       (scheme + host + path + query). For us that is ``TWILIO_PUBLIC_BASE_URL``
       + path + query — NOT the CloudFront-rewritten internal Host.
    2. For an ``application/x-www-form-urlencoded`` POST, sort the POST params
       by key (lexicographic) and append ``key + value`` (no separators) for
       each, in that order, to the URL string.
    3. HMAC-SHA1 that string using the account AuthToken as the key.
    4. base64-encode the raw digest.
    5. Compare to the ``X-Twilio-Signature`` header in constant time.

Everything here is a pure function: ``full_url`` is supplied by the caller, and
nothing reads environment variables or touches request objects — keeping it
trivially testable.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from urllib.parse import urlencode


def compute_twilio_signature(
    auth_token: str, full_url: str, post_params: dict[str, str]
) -> str:
    """Return the base64 ``X-Twilio-Signature`` for the given request.

    ``full_url`` must be the EXTERNAL URL Twilio actually signed (public base +
    path + query), not any internally rewritten host. POST params are appended
    as ``key + value`` concatenated in lexicographic key order.
    """
    signing_string = full_url + "".join(
        key + post_params[key] for key in sorted(post_params)
    )
    digest = hmac.new(
        auth_token.encode("utf-8"),
        signing_string.encode("utf-8"),
        hashlib.sha1,
    ).digest()
    return base64.b64encode(digest).decode("ascii")


def verify_twilio_signature(
    auth_token: str,
    full_url: str,
    post_params: dict[str, str],
    header_sig: str,
) -> bool:
    """Verify an inbound Twilio webhook's ``X-Twilio-Signature``.

    Returns ``True`` only when the recomputed signature matches ``header_sig``.
    The comparison uses :func:`hmac.compare_digest` (constant time). A missing
    or empty ``header_sig`` (or missing ``auth_token``) returns ``False``
    without raising.
    """
    if not header_sig or not auth_token:
        return False
    expected = compute_twilio_signature(auth_token, full_url, post_params)
    return hmac.compare_digest(expected, header_sig)


def build_signed_url(base: str, path: str, query: str = "") -> str:
    """Assemble the full URL Twilio signs from ``base`` + ``path`` + ``query``.

    Convenience helper for callers: joins the public base (e.g.
    ``TWILIO_PUBLIC_BASE_URL``) with the request path and optional raw query
    string. ``query`` may be a pre-encoded string (``"a=1&b=2"``) or a mapping,
    which will be urlencoded. A single ``?`` separator is inserted only when a
    non-empty query is present; the verifier still treats the result as opaque.
    """
    url = base.rstrip("/") + "/" + path.lstrip("/")
    if isinstance(query, dict):
        query = urlencode(query)
    if query:
        url = f"{url}?{query}"
    return url
