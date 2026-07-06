"""MCP tool-call filler — speak a short ack BEFORE the real tool runs.

Problem (see proposal tech_design §0): a connect-repair turn that hits an MCP
tool does **two** Bedrock round-trips — (1) the LLM emits a `tool_use` block
with empty text, (2) the MCP tool executes, (3) the LLM runs again to produce
the spoken reply. The user hears ~2s of silence across (1)→(3) (verifyCustomer
turns measured at ~3.6s E2E in prod).

Fix (code-level filler): wrap the MCP `tool_wrapper` so that, **before** the
real tool is invoked, we push a `TTSSpeakFrame` carrying a per-tool / per-lang
ack ("好的，正在为您核验身份…"). The LLM service is already inside the running
pipeline, so `push_frame` flows straight downstream to TTS — the ack plays
*while* the MCP call is in flight, turning dead air into "speak-while-looking-up".

This module is **pure new code** — `bot.py` wiring is T2. It mirrors the
env-gate style of `asr_filter.py` (`*_ENABLED` env var, default on).

Verified against real pipecat source (AC#5):
  - `FunctionCallParams.llm: LLMService[Any]`  (llm_service.py:127)
  - `LLMService.push_frame(self, frame, direction=DOWNSTREAM)`  (llm_service.py:475)
  - `TTSSpeakFrame(text: str, append_to_context: bool | None)`  (frames.py:697-709)
"""

import os

from loguru import logger

from pipecat.frames.frames import TTSSpeakFrame


def filler_enabled() -> bool:
    """Whether tool-call fillers are active.

    Reads ``TOOL_FILLER_ENABLED`` (default **true**). Falsy values
    (``0``/``false``/``no``/``off``/empty) disable it. Mirrors the
    ``ASR_FILTER_*`` env-gate convention.
    """
    return (
        os.environ.get("TOOL_FILLER_ENABLED", "true").strip().lower()
        not in ("0", "false", "no", "off", "")
    )


# Per-language, per-tool ack text. A turn that calls a tool not listed here
# falls back to that language's "_default"; a language not listed at all falls
# back to the en-US table (see filler_text). Covers the six connect-repair
# tools plus a generic default per language.
TOOL_ACKS: dict[str, dict[str, str]] = {
    "zh-CN": {
        "_default": "好的，请稍等…",
        "verifyCustomer": "好的，正在为您核验身份…",
        "verifyCustomerByPhoneAndName": "好的，正在为您核验身份…",
        "requestRepair": "好的，正在为您创建报修工单…",
        "trackRepair": "好的，正在为您查询工单进度…",
        "cancelRepair": "好的，正在为您取消工单…",
        "faqSearch": "好的，让我帮您查一下…",
    },
    "zh-HK": {
        "_default": "好嘅，請稍等…",
        "verifyCustomer": "好嘅，幫緊你核實身份…",
        "verifyCustomerByPhoneAndName": "好嘅，幫緊你核實身份…",
        "requestRepair": "好嘅，幫緊你開維修單…",
        "trackRepair": "好嘅，幫緊你查維修單進度…",
        "cancelRepair": "好嘅，幫緊你取消維修單…",
        "faqSearch": "好嘅，等我幫你查一查…",
    },
    "en-US": {
        "_default": "Okay, one moment…",
        "verifyCustomer": "Sure, verifying your identity…",
        "verifyCustomerByPhoneAndName": "Sure, verifying your identity…",
        "requestRepair": "Okay, creating your repair ticket…",
        "trackRepair": "Okay, checking your repair status…",
        "cancelRepair": "Okay, cancelling your repair ticket…",
        "faqSearch": "Sure, let me look that up…",
    },
}

# Language used when ``lang_key`` is absent from TOOL_ACKS entirely.
DEFAULT_LANG_FALLBACK = "en-US"


def filler_text(tool_name: str, lang_key: str) -> str:
    """Pick the ack text for a tool in a language.

    Resolution order:
      1. the language's per-tool text (``TOOL_ACKS[lang][tool]``), else
      2. that language's ``"_default"``, with the language table itself
         falling back to the ``en-US`` table when ``lang_key`` is unknown, else
      3. a hard-coded ``"OK."`` (only if the tables are empty/misconfigured).
    """
    table = TOOL_ACKS.get(lang_key) or TOOL_ACKS.get(DEFAULT_LANG_FALLBACK) or {}
    return table.get(tool_name) or table.get("_default") or "OK."


def with_filler(inner_wrapper, tool_name: str, lang_key: str):
    """Wrap a tool wrapper so a ``TTSSpeakFrame`` is pushed BEFORE the real call.

    Args:
        inner_wrapper: the existing async tool wrapper to wrap — either
            ``client._tool_wrapper`` (pipeline engine) or
            ``_nova_mcp_tool_wrapper(client)`` (Nova Sonic). Called as
            ``await inner_wrapper(params)``.
        tool_name: the MCP tool name (selects the ack text).
        lang_key: the session language key (selects the ack table).

    Returns:
        When fillers are enabled, a new async wrapper that first pushes the
        filler frame then awaits ``inner_wrapper``. When disabled, the original
        ``inner_wrapper`` unchanged (no wrapping, no push, identity preserved).

    The filler push is wrapped in try/except and only debug-logged on failure —
    a filler is a nicety and must **never** block or drop the real tool call.
    """
    if not filler_enabled():
        return inner_wrapper

    async def _wrapped(params):
        try:
            await params.llm.push_frame(
                TTSSpeakFrame(
                    text=filler_text(tool_name, lang_key),
                    append_to_context=False,
                )
            )
        except Exception as e:  # filler failure must not block the tool
            logger.debug(f"tool filler push failed for {tool_name}/{lang_key}: {e}")
        await inner_wrapper(params)

    return _wrapped
