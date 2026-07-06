"""Global tool registry for LLM-callable functions.

This module is the single source of truth for the cross-channel tool catalog
(end_call, transfer_to_human, ...). Both phone and web pipelines consume the
schemas from here so we never duplicate the FunctionSchema definitions that
used to live inline in ``call_control_tools.py``.

A scenario's manifest references tools by id (e.g. ``["end_call",
"transfer_to_human"]``). At pipeline build time, ``bot.py`` calls
:func:`get_tool_defs` with the requested ids + the channel scope (``"phone"``
or ``"web"``), then feeds the result through :func:`assemble_tools_schema`
(into the LLM service config) and :func:`assemble_policy_blurb` (into the
system prompt as a multi-language hangup/transfer policy section).

Per project §3.1:

- Every registered tool MUST have a non-empty ``policy_blurb`` for each of
  the four supported languages: en-US, zh-CN, zh-HK, ja-JP. The blurbs are
  short imperative paragraphs distilled from the canonical manifest text in
  ``data/it-helpdesk/manifest.yaml``.
- ``scope`` is a frozenset; both bundled tools currently apply to phone and
  web because the LLM-driven hangup/transfer flow is identical on each
  channel (the underlying transport handler differs, but the prompt-side
  contract does not).
- Adding a new tool: define a new ``ToolDefinition`` with all four language
  blurbs and append it to ``REGISTRY``. Do NOT add a tool with missing
  language coverage — the registry is intentionally strict so the prompt
  assembly step never silently drops a language.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Iterable

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema

# Re-use the canonical reason set from call_control_tools so the runtime
# handler and the registered schema stay in lockstep.
from call_control_tools import VALID_END_REASONS

logger = logging.getLogger(__name__)

SUPPORTED_LANGS: tuple[str, ...] = ("en-US", "zh-CN", "zh-HK", "ja-JP")
FALLBACK_LANG: str = "en-US"


@dataclass(frozen=True)
class ToolDefinition:
    """Static metadata + schema for a single LLM-callable tool.

    Attributes:
        id: Stable tool name. Must match ``schema.name`` and the string the
            LLM sees in its tool list.
        label: Human-friendly label for the admin UI.
        description_short: One-line summary surfaced in admin pickers.
        schema: The pipecat ``FunctionSchema`` handed to the LLM adapter.
        policy_blurb: Per-language imperative paragraph injected into the
            system prompt. Keys MUST be a superset of the requested
            language at prompt-assembly time; in practice we always
            populate all four supported languages.
        scope: Channel scope. ``"phone"`` and/or ``"web"``. ``get_tool_defs``
            filters by this set so a manifest can request the same tool id
            in either channel.
    """

    id: str
    label: str
    description_short: str
    schema: FunctionSchema
    policy_blurb: dict[str, str] = field(default_factory=dict)
    scope: frozenset[str] = field(default_factory=lambda: frozenset({"phone", "web"}))


# ---------------------------------------------------------------------------
# Tool: end_call
# Schema body kept identical to call_control_tools.call_control_tool_schemas
# so existing handler registration in bot.py continues to match.
# ---------------------------------------------------------------------------
_END_CALL_SCHEMA = FunctionSchema(
    name="end_call",
    description=(
        "End the current call. Call ONLY when the user clearly asks to hang "
        "up / says they are done, OR when the support task is fully "
        "resolved AND the user has acknowledged. Always speak a brief "
        "polite farewell BEFORE calling this tool. "
        "Cross-channel: the same tool works for phone (PSTN/SIP BYE) and "
        "web (WebSocket close)."
    ),
    properties={
        "reason": {
            "type": "string",
            "enum": sorted(VALID_END_REASONS),
            "description": "Why the call is ending.",
        }
    },
    required=["reason"],
)

_END_CALL_BLURB = {
    "en-US": (
        "[Hangup policy] When the caller clearly asks to hang up (e.g. "
        '"Goodbye", "I\'m done", "Nothing else"), first speak a brief '
        'polite farewell ("Glad to help — thanks for calling, goodbye.") '
        'and then immediately call end_call(reason="user_requested"). '
        "Once the issue is fully resolved AND the caller has confirmed "
        'they are satisfied, say a short farewell and call '
        'end_call(reason="task_completed"). A bare "thank you" alone is '
        "NOT a hangup signal — keep the conversation going and ask if "
        "there is anything else you can help with."
    ),
    "zh-CN": (
        "【挂线规则】客户明确表示要挂电话(例如「再见」「就这样吧」"
        "「没事了」)时,先讲一句简短礼貌的告别(例如「好的,谢谢您的"
        "来电,再见」),然后立刻调用 "
        'end_call(reason="user_requested")。当 IT 问题已经完全解决并且'
        "客户确认满意时,先讲一句告别,再调用 "
        'end_call(reason="task_completed")。如果客户只是单纯说一句'
        "「谢谢」,但没说要挂线也没确认问题搞定,这不代表要挂线——继续"
        "对话,问一句「请问还有其他需要帮忙的吗?」不要直接调用 end_call。"
    ),
    "zh-HK": (
        "【掛線守則】客戶明確表示想收線(例如「再見」「byebye」「冇嘢"
        "喇」)嗰陣,先講一句簡短禮貌嘅道別(例如「好嘅,多謝你嘅來電,"
        "再見」),然後即刻 call end_call(reason=\"user_requested\")。"
        "當 IT 問題已經完全解決,而且客戶確認滿意,先講一句道別,再 "
        'call end_call(reason="task_completed")。如果客戶只係單純講一句'
        "「多謝」,但冇話想收線又冇話搞掂,呢個唔代表要掛線——繼續對話,"
        "問番「請問仲有冇其他要幫手?」唔好直接 call end_call。"
    ),
    "ja-JP": (
        "【通話終了ポリシー】お客様がはっきりと電話を切りたいと意思表示"
        "した場合(例:「失礼します」「もう大丈夫です」「以上です」)、"
        "まず短く丁寧なお別れの挨拶を述べ(例:「お電話ありがとうござい"
        'ました、失礼いたします」)、その直後に '
        'end_call(reason="user_requested") を呼び出します。問題が完全に'
        "解決し、お客様から満足の確認が取れた場合は、短くお礼と挨拶を"
        'してから end_call(reason="task_completed") を呼び出します。'
        "お客様が単に「ありがとう」とだけ仰っても、明確な別れの言葉や"
        "解決確認が伴わない場合は通話終了を意味しません。会話を続け、"
        "「他にお困りのことはございますか?」と確認してください。"
    ),
}

END_CALL = ToolDefinition(
    id="end_call",
    label="End Call",
    description_short=(
        "Let the LLM hang up the call after a polite farewell. "
        "Cross-channel (phone + web)."
    ),
    schema=_END_CALL_SCHEMA,
    policy_blurb=_END_CALL_BLURB,
    scope=frozenset({"phone", "web"}),
)


# ---------------------------------------------------------------------------
# Tool: transfer_to_human
# ---------------------------------------------------------------------------
_TRANSFER_SCHEMA = FunctionSchema(
    name="transfer_to_human",
    description=(
        "Indicate the caller wants a human agent. The system logs the "
        "request and ends the call. Do NOT promise a callback time. "
        "Cross-channel: works the same for phone (PSTN transfer signal) "
        "and web (WS handoff signal)."
    ),
    properties={
        "topic": {
            "type": "string",
            "description": "Short reason the caller wants a human.",
        }
    },
    required=[],
)

_TRANSFER_BLURB = {
    "en-US": (
        "[Transfer policy] When the caller explicitly asks for a human "
        '(e.g. "transfer me to an agent", "I want to talk to a real '
        'person", "get me a human"), first acknowledge briefly ("Sure, '
        'transferring you to a human agent now.") and then call '
        "transfer_to_human(topic=...) with the topic set to the caller's "
        "current issue. Do NOT promise a callback time."
    ),
    "zh-CN": (
        "【转人工规则】客户明确要求转人工(例如「我要人工」「转真人客服」"
        "「找个人来跟我说」)时,先简短应一声(例如「好的,我现在帮您"
        "转人工同事」),然后调用 transfer_to_human(topic=...),topic 填"
        "客户本次要解决的问题。不要承诺具体回拨时间。"
    ),
    "zh-HK": (
        "【轉真人守則】客戶明確要求轉真人客服(例如「我要真人」「搵真人"
        "客服」「轉人工」)嗰陣,先簡短應一句(例如「好,我而家幫你轉"
        "真人同事」),然後 call transfer_to_human(topic=...),topic 填番"
        "客戶今次要解決嘅問題。唔好答應幾時會回電。"
    ),
    "ja-JP": (
        "【有人転送ポリシー】お客様が明確に有人対応を希望された場合"
        "(例:「人間と話したい」「オペレーターにつないでください」"
        "「担当者をお願いします」)、まず短く応答し(例:「かしこまり"
        "ました、ただいま担当者へお繋ぎいたします」)、その上で "
        "transfer_to_human(topic=...) を呼び出します。topic には今回の"
        "ご相談内容を入れてください。折り返し時刻の約束はしないで"
        "ください。"
    ),
}

TRANSFER_TO_HUMAN = ToolDefinition(
    id="transfer_to_human",
    label="Transfer to Human",
    description_short=(
        "Hand the caller off to a human agent and end the bot leg. "
        "Cross-channel (phone + web)."
    ),
    schema=_TRANSFER_SCHEMA,
    policy_blurb=_TRANSFER_BLURB,
    scope=frozenset({"phone", "web"}),
)


# ---------------------------------------------------------------------------
# Registry: the canonical, ordered map of tool id -> ToolDefinition.
# ---------------------------------------------------------------------------
REGISTRY: dict[str, ToolDefinition] = {
    END_CALL.id: END_CALL,
    TRANSFER_TO_HUMAN.id: TRANSFER_TO_HUMAN,
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def get_tool_defs(ids: Iterable[str], scope: str) -> list[ToolDefinition]:
    """Resolve ``ids`` against :data:`REGISTRY`, preserving order.

    Args:
        ids: Tool ids requested by the scenario manifest.
        scope: Channel scope, ``"phone"`` or ``"web"``. Tool defs whose
            ``scope`` does not contain this value are dropped silently
            (the manifest may legitimately list a tool that only one
            channel supports).

    Returns:
        List of matching :class:`ToolDefinition`s in input order.
        Unknown ids are dropped and produce a single ``logger.warning``
        each so misconfigurations surface in CloudWatch / stderr without
        blocking pipeline construction.
    """
    out: list[ToolDefinition] = []
    for tool_id in ids:
        defn = REGISTRY.get(tool_id)
        if defn is None:
            logger.warning(
                "tool_registry: unknown tool id %r requested (scope=%s); skipping",
                tool_id,
                scope,
            )
            continue
        if scope not in defn.scope:
            # Not a misconfiguration per se — just out of scope for this
            # channel. Info-level so it shows up only when debugging.
            logger.info(
                "tool_registry: tool %r out of scope for %r; skipping",
                tool_id,
                scope,
            )
            continue
        out.append(defn)
    return out


def assemble_tools_schema(defs: Iterable[ToolDefinition]) -> ToolsSchema:
    """Bundle a sequence of tool defs into a Pipecat ``ToolsSchema``.

    The resulting ``ToolsSchema.standard_tools`` is in the same order as
    ``defs``. ``custom_tools`` is left unset; we don't currently expose
    adapter-specific (Gemini/OpenAI search) tools through this registry.
    """
    return ToolsSchema(standard_tools=[d.schema for d in defs])


def assemble_policy_blurb(defs: Iterable[ToolDefinition], lang: str) -> str:
    """Join each tool's ``policy_blurb[lang]`` into one string.

    Falls back to :data:`FALLBACK_LANG` (en-US) when a tool is missing the
    requested language. Returns ``""`` when ``defs`` is empty.

    Paragraphs are separated by a blank line so the system prompt reads as
    distinct, well-spaced sections.
    """
    chunks: list[str] = []
    for defn in defs:
        blurb = defn.policy_blurb.get(lang)
        if not blurb:
            blurb = defn.policy_blurb.get(FALLBACK_LANG)
            if blurb:
                logger.info(
                    "tool_registry: tool %r missing blurb for %r; using %s",
                    defn.id,
                    lang,
                    FALLBACK_LANG,
                )
        if blurb:
            chunks.append(blurb.strip())
        else:
            logger.warning(
                "tool_registry: tool %r has no blurb for %r or fallback %s; "
                "omitting from policy section",
                defn.id,
                lang,
                FALLBACK_LANG,
            )
    return "\n\n".join(chunks)
