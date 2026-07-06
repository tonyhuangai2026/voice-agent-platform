"""LLM tools that let the pipeline gracefully end the active session.

Used from all four pipeline entry points (phone Nova Sonic, phone three-stage,
web Nova Sonic, web three-stage). The ``scope`` kwarg of
``register_call_control_handlers`` selects between the channels: phone scope
expects DDB / SIP-BYE callbacks (``mark_transfer`` / ``write_outcome`` /
``history_append``), web scope passes ``None`` for those — the handlers
are tolerant of any combination so the same code path covers both.

The tool *description* text the LLM sees still differs by channel (the
registry in ``tools/registry.py`` mentions both phone and web semantics).
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger as log

from pipecat.adapters.schemas.function_schema import FunctionSchema
from pipecat.adapters.schemas.tools_schema import ToolsSchema
from pipecat.frames.frames import EndTaskFrame

GRACE_SECONDS: float = 2.0

VALID_END_REASONS: frozenset[str] = frozenset(
    {"user_requested", "task_completed", "transfer_requested", "abusive"}
)

EmitFn = Callable[[dict[str, Any]], Awaitable[None]]
HistoryAppendFn = Callable[[str, dict[str, Any]], None]
MarkTransferFn = Callable[[str], None]
WriteOutcomeFn = Callable[[], Awaitable[bool]]


def call_control_tool_schemas() -> ToolsSchema:
    """Return the cross-provider tool schema for end_call + transfer_to_human.

    Kept for backwards compatibility; T5 pipelines normally pull schemas
    via ``tools.registry.assemble_tools_schema`` instead, which honors the
    demo's per-id allow-list.
    """
    return ToolsSchema(
        standard_tools=[
            FunctionSchema(
                name="end_call",
                description=(
                    "End the current call. Call ONLY when the user clearly "
                    "asks to hang up / says they are done, OR when the "
                    "support task is fully resolved AND the user has "
                    "acknowledged. Always speak a brief polite farewell "
                    "BEFORE calling this tool. "
                    # scope=web 时 end_call 关闭 WS,scope=phone 时触发 SIP BYE.
                    "On phone leg this terminates the PSTN call (SIP BYE); "
                    "on web it closes the WebSocket session and only "
                    "records intent."
                ),
                properties={
                    "reason": {
                        "type": "string",
                        "enum": sorted(VALID_END_REASONS),
                        "description": "Why the call is ending.",
                    }
                },
                required=["reason"],
            ),
            FunctionSchema(
                name="transfer_to_human",
                description=(
                    "Indicate the caller wants a human agent. The system "
                    "logs the request and ends the call. Do NOT promise a "
                    "callback time. On phone leg the call hangs up via "
                    "SIP BYE; on web the WebSocket is closed and only the "
                    "intent is recorded."
                ),
                properties={
                    "topic": {
                        "type": "string",
                        "description": "Short reason the caller wants a human.",
                    }
                },
                required=[],
            ),
        ]
    )


def register_call_control_handlers(
    llm,
    task,
    *,
    call_id: str,
    emit: EmitFn,
    scope: str = "phone",
    history_append: HistoryAppendFn | None = None,
    mark_transfer: MarkTransferFn | None = None,
    write_outcome: WriteOutcomeFn | None = None,
) -> None:
    """Register async end_call / transfer_to_human handlers on ``llm``.

    ``scope`` selects the channel ("phone" or "web"). It is used purely
    for log breadcrumbs — the actual side-effects are driven by which
    callbacks the caller passed:

      * ``write_outcome``  — phone-only DDB outcome row writer; awaited
        inside the grace-period task BEFORE the EndTaskFrame is queued.
      * ``mark_transfer``  — phone-only DDB top-level flag setter.
      * ``history_append`` — phone-only chronological event recorder.

    For ``scope="web"`` the caller is expected to pass ``None`` for all
    three; every handler treats ``None`` as a noop so the same code path
    covers both channels.

    Pipecat's EndFrame propagation drives the WS close (which on phone
    becomes the SIP BYE), so completing the DDB write first guarantees
    the row exists by the time a Connect Flow Lambda fires after the BYE.

    Closure-scoped state ensures only one EndTaskFrame is queued per call
    even if the LLM invokes the tool multiple times.
    """
    state = {"ending": False}

    async def _grace_then_end(reason: str) -> None:
        try:
            await asyncio.sleep(GRACE_SECONDS)
            if write_outcome is not None:
                try:
                    await write_outcome()
                except Exception:
                    log.exception(f"write_outcome failed call_id={call_id}")
            # write_outcome is None on web scope → just skip; the WS close
            # driven by EndTaskFrame is the only thing the web leg needs.
            await task.queue_frames(
                [EndTaskFrame(reason=f"tool:end_call:{reason}")]
            )
        except Exception:
            log.exception(f"grace-then-end failed call_id={call_id}")

    async def _emit_event(payload: dict[str, Any]) -> None:
        try:
            await emit(payload)
        except Exception:
            log.exception(f"tool event emit failed call_id={call_id}")

    async def _handle_end_call(params):
        if state["ending"]:
            await params.result_callback({"status": "already_ending"})
            return
        raw_reason = (getattr(params, "arguments", None) or {}).get("reason") or "user_requested"
        reason = raw_reason if raw_reason in VALID_END_REASONS else "user_requested"
        state["ending"] = True
        log.info(f"end_call call_id={call_id} reason={reason}")
        await _emit_event(
            {"type": "tool_call", "name": "end_call", "args": {"reason": reason}}
        )
        if history_append is not None:
            try:
                history_append("tool_call", {"name": "end_call", "reason": reason})
            except Exception:
                log.exception(f"history_append failed call_id={call_id}")
        asyncio.create_task(_grace_then_end(reason))
        await params.result_callback({"status": "ending", "reason": reason})

    async def _handle_transfer(params):
        if state["ending"]:
            await params.result_callback({"status": "already_ending"})
            return
        topic = (getattr(params, "arguments", None) or {}).get("topic") or ""
        state["ending"] = True
        log.info(f"transfer_to_human call_id={call_id} topic={topic!r}")
        if mark_transfer is not None:
            try:
                mark_transfer(topic)
            except Exception:
                log.exception(f"mark_transfer failed call_id={call_id}")
        await _emit_event(
            {
                "type": "tool_call",
                "name": "transfer_to_human",
                "args": {"topic": topic},
            }
        )
        if history_append is not None:
            try:
                history_append(
                    "tool_call", {"name": "transfer_to_human", "topic": topic}
                )
            except Exception:
                log.exception(f"history_append failed call_id={call_id}")
        asyncio.create_task(_grace_then_end("transfer_requested"))
        await params.result_callback(
            {"status": "ending", "reason": "transfer_requested"}
        )

    log.info(
        f"registering call-control tools call_id={call_id} scope={scope}"
    )
    llm.register_function("end_call", _handle_end_call)
    llm.register_function("transfer_to_human", _handle_transfer)
