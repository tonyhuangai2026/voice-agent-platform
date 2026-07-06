"""Unit tests for twilio_sig — X-Twilio-Signature verification.

Hermetic, standard-library only: no twilio SDK, no network, no env, no request
objects. Mirrors the plain-pytest style of tests/test_demo_translate.py and
tests/test_engine_languages.py (module-level functions, direct import of the
sibling module under test).

The "known vector" is a fixed, self-contained example: a frozen AuthToken,
full URL, and POST param set, whose expected base64 signature was computed once
with Twilio's documented algorithm (base64(HMAC-SHA1(token, url + sorted
key+value))) and hardcoded below. The implementation is additionally
cross-checked against an inline hand-rolled HMAC computation
(``test_compute_matches_independent_hand_rolled_hmac``) so the expectation is
pinned by two independent paths.
"""

from __future__ import annotations

import base64
import hashlib
import hmac

import twilio_sig


# Fixed, self-contained vector (expected sig computed once via the documented
# algorithm and pinned here; also cross-checked by an inline HMAC below).
_DOC_TOKEN = "12345"
_DOC_URL = "https://mycompany.com/myapp.php?foo=1&bar=2"
_DOC_PARAMS = {
    "CallSid": "CA1234567890ABCDE",
    "Caller": "+14158675309",
    "Digits": "1234",
    "From": "+14158675309",
    "To": "+18005551212",
}
_DOC_EXPECTED_SIG = "RSOYDt4T1cUTdK1PDd93/VVr8B8="


# ---------------------------------------------------------------------------
# Known-vector match
# ---------------------------------------------------------------------------
def test_known_vector_matches_documented_signature():
    sig = twilio_sig.compute_twilio_signature(_DOC_TOKEN, _DOC_URL, _DOC_PARAMS)
    assert sig == _DOC_EXPECTED_SIG
    assert twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, _DOC_URL, _DOC_PARAMS, _DOC_EXPECTED_SIG
    )


def test_compute_matches_independent_hand_rolled_hmac():
    """Cross-check the implementation against an inline reference computation
    of the exact documented algorithm (independent of the module internals)."""
    signing = _DOC_URL + "".join(
        k + _DOC_PARAMS[k] for k in sorted(_DOC_PARAMS)
    )
    expected = base64.b64encode(
        hmac.new(_DOC_TOKEN.encode(), signing.encode(), hashlib.sha1).digest()
    ).decode()
    assert expected == _DOC_EXPECTED_SIG
    assert twilio_sig.compute_twilio_signature(_DOC_TOKEN, _DOC_URL, _DOC_PARAMS) == expected


# ---------------------------------------------------------------------------
# Tampering / wrong-token / missing-header rejection
# ---------------------------------------------------------------------------
def test_tampered_param_value_rejected():
    bad = dict(_DOC_PARAMS, Digits="9999")
    assert not twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, _DOC_URL, bad, _DOC_EXPECTED_SIG
    )


def test_extra_param_rejected():
    extra = dict(_DOC_PARAMS, Extra="x")
    assert not twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, _DOC_URL, extra, _DOC_EXPECTED_SIG
    )


def test_wrong_auth_token_rejected():
    assert not twilio_sig.verify_twilio_signature(
        "wrong-token", _DOC_URL, _DOC_PARAMS, _DOC_EXPECTED_SIG
    )


def test_empty_header_rejected():
    assert not twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, _DOC_URL, _DOC_PARAMS, ""
    )


def test_none_header_rejected():
    assert not twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, _DOC_URL, _DOC_PARAMS, None  # type: ignore[arg-type]
    )


def test_empty_auth_token_rejected():
    assert not twilio_sig.verify_twilio_signature(
        "", _DOC_URL, _DOC_PARAMS, _DOC_EXPECTED_SIG
    )


def test_garbage_signature_rejected():
    assert not twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, _DOC_URL, _DOC_PARAMS, "not-a-real-signature"
    )


# ---------------------------------------------------------------------------
# Param input order is irrelevant (impl sorts by key)
# ---------------------------------------------------------------------------
def test_param_input_order_does_not_matter():
    # A dict built in a deliberately reversed / shuffled key order must still
    # verify, because the algorithm sorts keys lexicographically.
    shuffled = {k: _DOC_PARAMS[k] for k in reversed(list(_DOC_PARAMS))}
    assert list(shuffled) != list(_DOC_PARAMS)  # sanity: order really differs
    assert twilio_sig.compute_twilio_signature(_DOC_TOKEN, _DOC_URL, shuffled) == _DOC_EXPECTED_SIG
    assert twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, _DOC_URL, shuffled, _DOC_EXPECTED_SIG
    )


# ---------------------------------------------------------------------------
# Host participates in the signature — wrong host -> different sig -> reject
# ---------------------------------------------------------------------------
def test_different_host_yields_different_signature():
    internal = "https://d28jyp0rnkqvcx.cloudfront.net/myapp.php?foo=1&bar=2"
    sig_internal = twilio_sig.compute_twilio_signature(_DOC_TOKEN, internal, _DOC_PARAMS)
    assert sig_internal != _DOC_EXPECTED_SIG


def test_verify_with_wrong_host_rejected():
    # Signature was made for the public host; verifying against the internal
    # CloudFront host must fail. This is the canonical Round-1 pitfall.
    internal = "https://d28jyp0rnkqvcx.cloudfront.net/myapp.php?foo=1&bar=2"
    assert not twilio_sig.verify_twilio_signature(
        _DOC_TOKEN, internal, _DOC_PARAMS, _DOC_EXPECTED_SIG
    )


# ---------------------------------------------------------------------------
# build_signed_url helper
# ---------------------------------------------------------------------------
def test_build_signed_url_joins_base_path_query():
    url = twilio_sig.build_signed_url(
        "https://mycompany.com", "/myapp.php", "foo=1&bar=2"
    )
    assert url == "https://mycompany.com/myapp.php?foo=1&bar=2"
    # And a signature built off that assembled URL verifies.
    sig = twilio_sig.compute_twilio_signature(_DOC_TOKEN, url, _DOC_PARAMS)
    assert sig == _DOC_EXPECTED_SIG


def test_build_signed_url_handles_trailing_and_leading_slashes():
    assert (
        twilio_sig.build_signed_url("https://x.com/", "path", "")
        == "https://x.com/path"
    )
    assert (
        twilio_sig.build_signed_url("https://x.com", "/twilio/incoming-call")
        == "https://x.com/twilio/incoming-call"
    )


def test_build_signed_url_encodes_mapping_query():
    url = twilio_sig.build_signed_url("https://x.com", "/p", {"a": "1", "b": "2"})
    assert url == "https://x.com/p?a=1&b=2"
