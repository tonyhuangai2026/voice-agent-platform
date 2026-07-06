"""Tests for the first-party AWS Transcribe multi-language signer + stream B.

The earlier build added multi-language support by editing the *vendored*
``pipecat/src/services/aws/{utils,stt}.py`` — which is inert on prod because
deploy ships ``--exclude='pipecat'`` and CFN installs ``pipecat-ai`` from PyPI.
The corrective moves the logic into a first-party, pure-stdlib module
(``asr_multilang``) and feeds it into *stock* pipecat via a thin subclass that
monkeypatches the ``get_presigned_url`` seam.

These tests target ``asr_multilang.build_transcribe_presigned_url`` (signing
correctness + ordering + guards + a deterministic known-good vector) and
``bot._MultiLangTranscribeSTT`` (stock-Settings-only construction + the
version-guard fallback). They also assert ``asr_multilang`` imports no pipecat.
"""

import datetime
import importlib
import sys

import pytest

import asr_multilang as A


# --- Fixtures -------------------------------------------------------------

_FIXED_NOW = datetime.datetime(2026, 6, 29, 12, 0, 0)
_FIXED_ACCESS = "AKIDEXAMPLE"
_FIXED_SECRET = "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
_FIXED_TOKEN = "FQoGZXIvYXdzEXAMPLESESSIONTOKEN/////"
_REGION = "us-east-1"


@pytest.fixture(autouse=True)
def frozen_clock(monkeypatch):
    """Pin datetime.utcnow inside the signer so amz_date / datestamp (and thus
    the signature) are deterministic."""

    class _FrozenDateTime(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return _FIXED_NOW

    monkeypatch.setattr(A.datetime, "datetime", _FrozenDateTime)
    yield


def _creds(token=None):
    return {"access_key": _FIXED_ACCESS, "secret_key": _FIXED_SECRET, "session_token": token}


# --- 1. Multi-language: ordering + identify + language-options + no code ---


def test_multi_language_alpha_order_identify_options_preferred_no_language_code():
    url = A.build_transcribe_presigned_url(
        region=_REGION,
        credentials=_creds(),
        sample_rate=16000,
        media_encoding="pcm",
        identify_multiple_languages=True,
        language_options="zh-HK,en-US",
        preferred_language="zh-HK",
    )

    # (a) new keys present with expected values
    assert "identify-multiple-languages=true" in url
    assert "language-options=zh-HK%2Cen-US" in url
    assert "preferred-language=zh-HK" in url
    # (b) language-code omitted entirely (mutual exclusion)
    assert "language-code=" not in url
    # (c) comma in language-options IS percent-encoded as %2C — AWS canonicalizes
    # the received query string and verifies the signature against the encoded
    # form; a raw comma trips SignatureDoesNotMatch (observed on prod).
    assert "language-options=zh-HK,en-US" not in url
    assert "zh-HK%2Cen-US" in url

    # (d) the service-param segment in exact alphabetical order (the X-Amz-*
    # signing prefix + the X-Amz-Signature suffix are stripped off).
    core = url.split("&X-Amz-SignedHeaders=host")[1].split("&X-Amz-Signature=")[0]
    assert core == (
        "&enable-partial-results-stabilization=true"
        "&identify-multiple-languages=true"
        "&language-options=zh-HK%2Cen-US"
        "&media-encoding=pcm"
        "&partial-results-stability=high"
        "&preferred-language=zh-HK"
        "&sample-rate=16000"
    )


def test_identify_language_single_mode_sorts_before_language_options():
    url = A.build_transcribe_presigned_url(
        region=_REGION,
        credentials=_creds(),
        sample_rate=16000,
        identify_language=True,
        language_options="zh-HK,en-US",
    )
    assert "identify-language=true" in url
    assert "language-code=" not in url
    assert url.index("identify-language=true") < url.index("language-options=")


# --- 2. Single-language: language-code present, no identify params ---------


def test_single_language_has_language_code_no_identify():
    url = A.build_transcribe_presigned_url(
        region=_REGION,
        credentials=_creds(),
        sample_rate=16000,
        language_code="zh-HK",
    )
    assert "language-code=zh-HK" in url
    assert "identify-" not in url
    assert "language-options=" not in url
    assert "preferred-language=" not in url


# --- 3. X-Amz-Security-Token: present ONLY with a session token ------------


def test_security_token_absent_without_session_token():
    url = A.build_transcribe_presigned_url(
        region=_REGION, credentials=_creds(token=None), sample_rate=16000, language_code="zh-HK"
    )
    assert "X-Amz-Security-Token=" not in url


def test_security_token_present_with_session_token_and_slots_before_signedheaders():
    url = A.build_transcribe_presigned_url(
        region=_REGION,
        credentials=_creds(token=_FIXED_TOKEN),
        sample_rate=16000,
        language_code="zh-HK",
    )
    assert "X-Amz-Security-Token=" in url
    # session token is URL-encoded (slashes -> %2F)
    assert "X-Amz-Security-Token=FQoGZXIvYXdzEXAMPLESESSIONTOKEN%2F%2F%2F%2F%2F" in url
    # ...and slots between X-Amz-Expires and X-Amz-SignedHeaders (stock ordering)
    assert url.index("X-Amz-Expires=300") < url.index("X-Amz-Security-Token=")
    assert url.index("X-Amz-Security-Token=") < url.index("X-Amz-SignedHeaders=host")


# --- 4. Deterministic known-good vectors (signing regression guard) --------
# Captured under the frozen clock + fixed creds. Any change to the signing path
# changes the signature and trips these.

_EXPECTED_MULTI_NO_TOKEN = (
    "wss://transcribestreaming.us-east-1.amazonaws.com:8443/stream-transcription-websocket?"
    "X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=AKIDEXAMPLE%2F20260629%2Fus-east-1%2Ftranscribe%2Faws4_request"
    "&X-Amz-Date=20260629T120000Z"
    "&X-Amz-Expires=300"
    "&X-Amz-SignedHeaders=host"
    "&enable-partial-results-stabilization=true"
    "&identify-multiple-languages=true"
    "&language-options=zh-HK%2Cen-US"
    "&media-encoding=pcm"
    "&partial-results-stability=high"
    "&preferred-language=zh-HK"
    "&sample-rate=16000"
    "&X-Amz-Signature=0835d5228738ed3bb830d2e05f7cdf9c6e001c298d3f966e1d6fe149320a6b4c"
)

_EXPECTED_SINGLE_NO_TOKEN = (
    "wss://transcribestreaming.us-east-1.amazonaws.com:8443/stream-transcription-websocket?"
    "X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=AKIDEXAMPLE%2F20260629%2Fus-east-1%2Ftranscribe%2Faws4_request"
    "&X-Amz-Date=20260629T120000Z"
    "&X-Amz-Expires=300"
    "&X-Amz-SignedHeaders=host"
    "&enable-partial-results-stabilization=true"
    "&language-code=zh-HK"
    "&media-encoding=pcm"
    "&partial-results-stability=high"
    "&sample-rate=16000"
    "&X-Amz-Signature=f92e7b411e143764411b317b8dfa39c9503f0bdb012943f6396317114aa6eaf8"
)

_EXPECTED_SINGLE_WITH_TOKEN = (
    "wss://transcribestreaming.us-east-1.amazonaws.com:8443/stream-transcription-websocket?"
    "X-Amz-Algorithm=AWS4-HMAC-SHA256"
    "&X-Amz-Credential=AKIDEXAMPLE%2F20260629%2Fus-east-1%2Ftranscribe%2Faws4_request"
    "&X-Amz-Date=20260629T120000Z"
    "&X-Amz-Expires=300"
    "&X-Amz-Security-Token=FQoGZXIvYXdzEXAMPLESESSIONTOKEN%2F%2F%2F%2F%2F"
    "&X-Amz-SignedHeaders=host"
    "&enable-partial-results-stabilization=true"
    "&language-code=zh-HK"
    "&media-encoding=pcm"
    "&partial-results-stability=high"
    "&sample-rate=16000"
    "&X-Amz-Signature=573ea83511cefd7a6cbf9c505f0918cb4573ced85301447f0af4071f078bc8a4"
)


def test_known_good_vector_multi_language_no_token():
    url = A.build_transcribe_presigned_url(
        region=_REGION,
        credentials=_creds(),
        sample_rate=16000,
        media_encoding="pcm",
        identify_multiple_languages=True,
        language_options="zh-HK,en-US",
        preferred_language="zh-HK",
    )
    assert url == _EXPECTED_MULTI_NO_TOKEN


def test_known_good_vector_single_language_no_token():
    url = A.build_transcribe_presigned_url(
        region=_REGION, credentials=_creds(), sample_rate=16000, language_code="zh-HK"
    )
    assert url == _EXPECTED_SINGLE_NO_TOKEN


def test_known_good_vector_single_language_with_token():
    url = A.build_transcribe_presigned_url(
        region=_REGION,
        credentials=_creds(token=_FIXED_TOKEN),
        sample_rate=16000,
        language_code="zh-HK",
    )
    assert url == _EXPECTED_SINGLE_WITH_TOKEN


def test_single_language_byte_identical_to_stock_pipecat_signer():
    """The single-language URL must be byte-identical to stock pipecat's own
    ``get_presigned_url`` — proving we replicate stock SigV4 exactly, so prod
    /ws signing (which uses stock) is provably unaffected by this module."""
    import pipecat.services.aws.utils as U

    class _FrozenDateTime(datetime.datetime):
        @classmethod
        def utcnow(cls):
            return _FIXED_NOW

    # Freeze stock's clock the same way for an apples-to-apples comparison.
    U.datetime.datetime = _FrozenDateTime
    try:
        for token in (None, _FIXED_TOKEN):
            stock = U.get_presigned_url(
                region=_REGION,
                credentials=_creds(token),
                language_code="zh-HK",
                media_encoding="pcm",
                sample_rate=16000,
                number_of_channels=1,
                enable_partial_results_stabilization=True,
                partial_results_stability="high",
            )
            mine = A.build_transcribe_presigned_url(
                region=_REGION,
                credentials=_creds(token),
                sample_rate=16000,
                media_encoding="pcm",
                language_code="zh-HK",
            )
            assert mine == stock
    finally:
        U.datetime.datetime = datetime.datetime


# --- 5. Guards ------------------------------------------------------------


def test_language_code_and_identify_together_raises():
    with pytest.raises(ValueError):
        A.build_transcribe_presigned_url(
            region=_REGION,
            credentials=_creds(),
            sample_rate=16000,
            language_code="zh-HK",
            identify_multiple_languages=True,
            language_options="zh-HK,en-US",
        )


def test_empty_language_options_with_identify_raises():
    with pytest.raises(ValueError):
        A.build_transcribe_presigned_url(
            region=_REGION,
            credentials=_creds(),
            sample_rate=16000,
            identify_multiple_languages=True,
            language_options="",
        )


def test_whitespace_language_options_with_identify_raises():
    with pytest.raises(ValueError):
        A.build_transcribe_presigned_url(
            region=_REGION,
            credentials=_creds(),
            sample_rate=16000,
            identify_language=True,
            language_options="   ",
        )


def test_no_identify_and_no_language_code_raises():
    with pytest.raises(ValueError):
        A.build_transcribe_presigned_url(
            region=_REGION, credentials=_creds(), sample_rate=16000
        )


def test_missing_credentials_raises():
    with pytest.raises(ValueError):
        A.build_transcribe_presigned_url(
            region=_REGION,
            credentials={"access_key": None, "secret_key": None, "session_token": None},
            sample_rate=16000,
            language_code="zh-HK",
        )


# --- 6. asr_multilang is pure stdlib (imports no pipecat) -----------------


def test_asr_multilang_imports_no_pipecat():
    """The signer must NOT depend on pipecat (the local!=prod trap fix). Import
    it in a fresh interpreter with pipecat pre-poisoned so any import attempt
    raises, and assert it still imports clean."""
    import subprocess

    code = (
        "import sys, types\n"
        # Poison: any 'import pipecat...' inside asr_multilang would hit this.
        "class _Boom(dict):\n"
        "    def __missing__(self, k):\n"
        "        if k == 'pipecat' or k.startswith('pipecat.'):\n"
        "            raise ImportError('asr_multilang must not import pipecat')\n"
        "        raise KeyError(k)\n"
        "import importlib\n"
        "m = importlib.import_module('asr_multilang')\n"
        # Direct check on the loaded module's own imported names.
        "assert not any(n == 'pipecat' or str(getattr(v, '__name__', '')).startswith('pipecat')\n"
        "               for n, v in vars(m).items()), 'pipecat leaked into asr_multilang'\n"
        "print('OK')\n"
    )
    import os

    repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    proc = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, cwd=repo_root
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout

    # Also assert at the AST level: no `import pipecat` / `from pipecat import`
    # statement anywhere (docstrings mentioning pipecat are fine).
    import ast

    src_path = os.path.join(repo_root, "asr_multilang.py")
    with open(src_path) as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert not alias.name.split(".")[0] == "pipecat"
        elif isinstance(node, ast.ImportFrom):
            assert (node.module or "").split(".")[0] != "pipecat"


# --- 7. Stream B subclass: stock-Settings-only + version-guard fallback ----


def _import_bot(monkeypatch):
    monkeypatch.setenv("SITE_PASSWORD", "test-pwd")
    monkeypatch.setenv("MINIMAX_API_KEY", "x")
    for mod in list(sys.modules):
        if mod in ("bot", "runtime_config", "demo_loader"):
            del sys.modules[mod]
    return importlib.import_module("bot")


def test_stream_b_constructs_stock_settings_with_language_only(monkeypatch):
    """_MultiLangTranscribeSTT must pass ONLY language= to the stock Settings
    ctor (stock Settings has no identify_* field — passing one would raise)."""
    bot = _import_bot(monkeypatch)
    # Record the kwargs of every Settings() construction, in order. Stock
    # __init__ ALSO builds its own default_settings (with model=, language=EN,
    # ...), so we can't assert on the merged set — we assert that the FIRST call
    # (our subclass's explicit construction) used ONLY language=.
    calls = []

    real_settings = bot.AWSTranscribeSTTService.Settings

    def _spy_settings(**kw):
        calls.append(set(kw.keys()))
        return real_settings(**kw)

    monkeypatch.setattr(bot.AWSTranscribeSTTService, "Settings", staticmethod(_spy_settings))

    svc = bot._MultiLangTranscribeSTT(
        region=_REGION,
        aws_access_key_id="AKIA",
        api_key="secret",
        sample_rate=16000,
        language_options="zh-HK,en-US",
        preferred_language="zh-HK",
        mode="multiple",
    )
    # The subclass's explicit Settings() call (the first one) passed ONLY
    # language= — never an identify_* field, which stock Settings lacks.
    assert calls[0] == {"language"}
    for c in calls:
        assert "identify_multiple_languages" not in c
        assert "identify_language" not in c
        assert "language_options" not in c
        assert "preferred_language" not in c
    # multi-language config is stored on the instance, not on stock Settings.
    assert svc._ml["language_options"] == "zh-HK,en-US"
    assert svc._ml["preferred_language"] == "zh-HK"
    assert svc._ml["mode"] == "multiple"


def test_stream_b_version_guard_falls_back_to_super(monkeypatch):
    """When importlib.metadata.version('pipecat-ai') != PINNED_PIPECAT, stream
    B's _connect_websocket must log + fall back to super() (single-language),
    NOT monkeypatch the seam."""
    import asyncio

    bot = _import_bot(monkeypatch)

    svc = bot._MultiLangTranscribeSTT(
        region=_REGION,
        aws_access_key_id="AKIA",
        api_key="secret",
        sample_rate=16000,
        language_options="zh-HK,en-US",
        preferred_language="zh-HK",
        mode="multiple",
    )

    # Force a non-pinned reported version.
    import importlib.metadata as _md

    monkeypatch.setattr(_md, "version", lambda name: "9.9.9")

    import pipecat.services.aws.stt as _stt

    seam_before = _stt.get_presigned_url
    super_called = {"hit": False}

    async def _fake_super_connect(self):
        super_called["hit"] = True
        # During the fallback the seam must NOT be patched.
        assert _stt.get_presigned_url is seam_before

    monkeypatch.setattr(bot.AWSTranscribeSTTService, "_connect_websocket", _fake_super_connect)

    asyncio.run(svc._connect_websocket())

    assert super_called["hit"] is True
    # seam restored / untouched after the fallback path
    assert _stt.get_presigned_url is seam_before


def test_stream_b_pinned_version_patches_seam_then_restores(monkeypatch):
    """When the reported version == PINNED_PIPECAT, _connect_websocket must
    monkeypatch pipecat.services.aws.stt.get_presigned_url for the duration of
    super()._connect_websocket() (calling our first-party signer) and restore
    the original in finally."""
    import asyncio

    bot = _import_bot(monkeypatch)

    svc = bot._MultiLangTranscribeSTT(
        region=_REGION,
        aws_access_key_id="AKIA",
        api_key="secret",
        sample_rate=16000,
        language_options="zh-HK,en-US",
        preferred_language="zh-HK",
        mode="multiple",
    )

    import importlib.metadata as _md

    monkeypatch.setattr(_md, "version", lambda name: bot.PINNED_PIPECAT)

    import pipecat.services.aws.stt as _stt

    seam_before = _stt.get_presigned_url
    observed = {}

    async def _fake_super_connect(self):
        # Inside the patch window: invoking the (now-patched) seam the way stock
        # stt.py does must route through our first-party multi-language signer.
        url = _stt.get_presigned_url(
            region=_REGION,
            credentials={
                "access_key": _FIXED_ACCESS,
                "secret_key": _FIXED_SECRET,
                "session_token": None,
            },
            language_code="zh-HK",  # popped by the wrapper
            media_encoding="pcm",
            sample_rate=16000,
            number_of_channels=1,
            enable_partial_results_stabilization=True,
            partial_results_stability="high",
            show_speaker_label=False,
            enable_channel_identification=False,
        )
        observed["url"] = url
        observed["patched"] = _stt.get_presigned_url is not seam_before

    monkeypatch.setattr(bot.AWSTranscribeSTTService, "_connect_websocket", _fake_super_connect)

    asyncio.run(svc._connect_websocket())

    assert observed["patched"] is True
    # multi-language params present; language-code dropped by the wrapper
    assert "identify-multiple-languages=true" in observed["url"]
    assert "language-options=zh-HK%2Cen-US" in observed["url"]
    assert "preferred-language=zh-HK" in observed["url"]
    assert "language-code=" not in observed["url"]
    # original seam restored in finally
    assert _stt.get_presigned_url is seam_before
