"""First-party AWS Transcribe presigned-URL signer with multi-language support.

PURE STDLIB — imports only ``hmac``, ``hashlib``, ``datetime`` and
``urllib.parse``. It MUST NOT import pipecat (see the import-guard test).

Why this module exists
----------------------
The earlier ``/asr-test`` build added multi-language Transcribe support by
editing the *vendored* ``pipecat/src/services/aws/{utils,stt}.py``. But
``deploy/deploy.sh`` ships the tarball with ``--exclude='pipecat'`` and CFN
UserData installs ``pipecat-ai`` from PyPI — so the running prod server imports
pipecat from ``site-packages``, never our edited ``pipecat/src``. The vendored
edits were therefore inert on prod (a local != prod trap).

This module re-implements the multi-language presigned-URL signing as
first-party code that depends on nothing in ``pipecat/src``. It is fed into the
*stock* pipecat ``AWSTranscribeSTTService`` via a thin subclass in ``bot.py``
that monkeypatches the module-level ``get_presigned_url`` seam around
``super()._connect_websocket()``.

``build_transcribe_presigned_url`` replicates stock pipecat's
``AWSTranscribePresignedURL.get_request_url`` SigV4 signing EXACTLY (canonical
querystring ordering, signature chain, host/expires/payload), then adds the
optional ``identify-language`` / ``identify-multiple-languages`` /
``language-options`` / ``preferred-language`` parameters at their correct
alphabetical positions.
"""

import datetime
import hashlib
import hmac
import urllib.parse


def build_transcribe_presigned_url(
    *,
    region: str,
    credentials: dict,
    sample_rate: int,
    media_encoding: str = "pcm",
    language_code: str | None = None,
    identify_language: bool = False,
    identify_multiple_languages: bool = False,
    language_options: str | None = None,
    preferred_language: str | None = None,
    enable_partial_results_stabilization: bool = True,
    partial_results_stability: str = "high",
) -> str:
    """Build a SigV4 presigned WebSocket URL for AWS Transcribe streaming.

    Replicates stock pipecat's ``AWSTranscribePresignedURL.get_request_url``
    signing byte-for-byte for the single-language case, and adds the
    multi-language identification parameters for the identify-* case.

    Args:
        region: AWS region (e.g. ``"us-east-1"``).
        credentials: Dict with ``access_key`` + ``secret_key`` (required) and an
            optional ``session_token`` (temporary creds).
        sample_rate: Audio sample rate in Hz.
        media_encoding: Audio encoding (default ``"pcm"``).
        language_code: Fixed language code for single-language mode. Required
            when neither identify-* flag is set; MUST be omitted when an
            identify-* flag is set.
        identify_language: Enable single dominant-language identification.
        identify_multiple_languages: Enable multi-language (code-switching)
            identification.
        language_options: Comma-joined candidate languages for identify-* modes,
            e.g. ``"zh-HK,en-US"``. Required + non-empty when an identify-* flag
            is on. The comma is NOT percent-encoded (matches AWS's own example).
        preferred_language: Optional preferred language biasing identify-*.
        enable_partial_results_stabilization: Enable partial-result stabilization.
        partial_results_stability: Stability level for partial results.

    Returns:
        The fully signed ``wss://`` presigned URL.

    Raises:
        ValueError: missing credentials; both ``language_code`` and an
            identify-* flag set (mutually exclusive); identify-* on with
            empty/whitespace ``language_options``; or neither identify-* flag
            set and no ``language_code``.
    """
    access_key = credentials.get("access_key")
    secret_key = credentials.get("secret_key")
    session_token = credentials.get("session_token")

    if not access_key or not secret_key:
        raise ValueError("AWS credentials are required")

    identify_on = bool(identify_multiple_languages or identify_language)

    # Mutual exclusion: language-code vs identify-* (AWS rejects both).
    if identify_on and language_code:
        raise ValueError(
            "language_code is mutually exclusive with identify_language / "
            "identify_multiple_languages"
        )
    # identify-* requires a non-empty language_options list.
    if identify_on and not (language_options and language_options.strip()):
        raise ValueError(
            "language_options is required (non-empty) when identify_language "
            "or identify_multiple_languages is set"
        )
    # Single-language mode requires a language code.
    if not identify_on and not language_code:
        raise ValueError("language_code is required when no identify-* mode is set")

    method = "GET"
    service = "transcribe"
    canonical_uri = "/stream-transcription-websocket"
    signed_headers = "host"
    algorithm = "AWS4-HMAC-SHA256"

    endpoint = f"wss://transcribestreaming.{region}.amazonaws.com:8443"
    host = f"transcribestreaming.{region}.amazonaws.com:8443"

    now = datetime.datetime.utcnow()
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    datestamp = now.strftime("%Y%m%d")
    canonical_headers = f"host:{host}\n"
    credential_scope_qs = f"{datestamp}%2F{region}%2F{service}%2Faws4_request"

    # --- Canonical querystring -------------------------------------------
    # Preamble (SigV4 signing params), matching stock ordering exactly:
    # X-Amz-Algorithm, X-Amz-Credential, X-Amz-Date, X-Amz-Expires,
    # [X-Amz-Security-Token only when a session token is present],
    # X-Amz-SignedHeaders.
    canonical_querystring = "X-Amz-Algorithm=" + algorithm
    canonical_querystring += "&X-Amz-Credential=" + access_key + "%2F" + credential_scope_qs
    canonical_querystring += "&X-Amz-Date=" + amz_date
    canonical_querystring += "&X-Amz-Expires=300"
    if session_token:
        canonical_querystring += "&X-Amz-Security-Token=" + urllib.parse.quote(
            session_token, safe=""
        )
    canonical_querystring += "&X-Amz-SignedHeaders=" + signed_headers

    # Request params in strict ALPHABETICAL order, only those present:
    #   enable-partial-results-stabilization
    #   identify-language
    #   identify-multiple-languages
    #   language-code
    #   language-options
    #   media-encoding
    #   partial-results-stability
    #   preferred-language
    #   sample-rate
    if enable_partial_results_stabilization:
        canonical_querystring += "&enable-partial-results-stabilization=true"
    if identify_language:
        canonical_querystring += "&identify-language=true"
    if identify_multiple_languages:
        canonical_querystring += "&identify-multiple-languages=true"
    if language_code:
        canonical_querystring += "&language-code=" + language_code
    if language_options:
        # Comma MUST be percent-encoded as %2C. AWS canonicalizes the received
        # query string before verifying the signature: it expects
        # "language-options=zh-HK%2Cen-US" in BOTH the canonical string it signs
        # and the URL on the wire (confirmed verbatim from a SignatureDoesNotMatch
        # error's "Canonical String should have been"). A raw comma signs a
        # different canonical string than AWS computes → SignatureDoesNotMatch.
        # Since this querystring is both signed and sent, encoding it here keeps
        # the two byte-identical.
        canonical_querystring += "&language-options=" + urllib.parse.quote(
            language_options, safe=""
        )
    if media_encoding:
        canonical_querystring += "&media-encoding=" + media_encoding
    if partial_results_stability:
        canonical_querystring += "&partial-results-stability=" + partial_results_stability
    if preferred_language:
        canonical_querystring += "&preferred-language=" + preferred_language
    if sample_rate:
        canonical_querystring += "&sample-rate=" + str(sample_rate)

    # --- SigV4 signature chain -------------------------------------------
    payload_hash = hashlib.sha256(b"").hexdigest()
    canonical_request = (
        f"{method}\n{canonical_uri}\n{canonical_querystring}\n"
        f"{canonical_headers}\n{signed_headers}\n{payload_hash}"
    )

    credential_scope = f"{datestamp}/{region}/{service}/aws4_request"
    string_to_sign = (
        f"{algorithm}\n{amz_date}\n{credential_scope}\n"
        + hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    )

    k_date = hmac.new(
        f"AWS4{secret_key}".encode(), datestamp.encode("utf-8"), hashlib.sha256
    ).digest()
    k_region = hmac.new(k_date, region.encode("utf-8"), hashlib.sha256).digest()
    k_service = hmac.new(k_region, service.encode("utf-8"), hashlib.sha256).digest()
    k_signing = hmac.new(k_service, b"aws4_request", hashlib.sha256).digest()
    signature = hmac.new(
        k_signing, string_to_sign.encode("utf-8"), hashlib.sha256
    ).hexdigest()

    canonical_querystring += "&X-Amz-Signature=" + signature

    return endpoint + canonical_uri + "?" + canonical_querystring
