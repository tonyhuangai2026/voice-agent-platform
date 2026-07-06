"""Unit tests for call_control_tools (end_call + transfer_to_human).

These tests exercise the schema and async handlers using lightweight in-file
fakes (FakeLLM, FakeTask, FakeParams) so they do NOT need bot.py, AWS
credentials, or any real Pipecat pipeline construction.
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

import call_control_tools
from call_control_tools import (
    VALID_END_REASONS,
    call_control_tool_schemas,
    register_call_control_handlers,
)
from pipecat.frames.frames import EndTaskFrame


# ---------------------------------------------------------------------------
# In-file test fakes
# ---------------------------------------------------------------------------
class FakeLLM:
    """Records calls to register_function so tests can grab the handlers."""

    def __init__(self) -> None:
        self.handlers: dict[str, Any] = {}
        self.register_calls: list[str] = []

    def register_function(self, name: str, handler) -> None:
        self.register_calls.append(name)
        self.handlers[name] = handler


class FakeTask:
    """Captures every frame list passed to queue_frames (async)."""

    def __init__(self) -> None:
        self.queued: list[Any] = []

    async def queue_frames(self, frames):
        self.queued.extend(frames)


class FakeParams:
    """Mimics Pipecat's FunctionCallParams shape (arguments + result_callback)."""

    def __init__(self, arguments: dict[str, Any] | None = None) -> None:
        self.arguments = arguments or {}
        self.results: list[Any] = []

        async def _cb(result):
            self.results.append(result)

        self.result_callback = _cb


async def _make_emit_recorder():
    """Returns (emit_fn, captured_list)."""
    captured: list[dict[str, Any]] = []

    async def emit(payload):
        captured.append(payload)

    return emit, captured


# ---------------------------------------------------------------------------
# Auto-apply: speed up the grace delay for every test in this module.
# ---------------------------------------------------------------------------
@pytest.fixture(autouse=True)
def _fast_grace(monkeypatch):
    monkeypatch.setattr(call_control_tools, "GRACE_SECONDS", 0.01)


# ---------------------------------------------------------------------------
# 1. Schema shape
# ---------------------------------------------------------------------------
def test_schemas_present():
    schemas = call_control_tool_schemas()
    tools = schemas.standard_tools
    assert len(tools) == 2
    names = {t.name for t in tools}
    assert names == {"end_call", "transfer_to_human"}


# ---------------------------------------------------------------------------
# 2. end_call.reason enum covers all 4 valid reasons
# ---------------------------------------------------------------------------
def test_end_call_reason_enum():
    schemas = call_control_tool_schemas()
    end_call = next(t for t in schemas.standard_tools if t.name == "end_call")
    enum = set(end_call.properties["reason"]["enum"])
    expected = {"user_requested", "task_completed", "transfer_requested", "abusive"}
    assert expected <= enum
    assert expected == set(VALID_END_REASONS)


# ---------------------------------------------------------------------------
# 3. end_call queues exactly one EndTaskFrame with the right reason
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_end_call_handler_queues_endtaskframe():
    llm = FakeLLM()
    task = FakeTask()
    emit, captured = await _make_emit_recorder()

    register_call_control_handlers(
        llm, task, call_id="c1", emit=emit
    )
    assert llm.register_calls == ["end_call", "transfer_to_human"]

    params = FakeParams(arguments={"reason": "user_requested"})
    await llm.handlers["end_call"](params)
    await asyncio.sleep(0.1)  # let _grace_then_end fire

    end_frames = [f for f in task.queued if isinstance(f, EndTaskFrame)]
    assert len(end_frames) == 1
    assert end_frames[0].reason == "tool:end_call:user_requested"
    assert len(params.results) == 1
    assert params.results[0] == {"status": "ending", "reason": "user_requested"}
    assert captured and captured[0]["name"] == "end_call"


# ---------------------------------------------------------------------------
# 4. Invalid reason falls back to user_requested
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_end_call_invalid_reason_falls_back():
    llm = FakeLLM()
    task = FakeTask()
    emit, _ = await _make_emit_recorder()

    register_call_control_handlers(llm, task, call_id="c2", emit=emit)
    params = FakeParams(arguments={"reason": "garbage"})
    await llm.handlers["end_call"](params)
    await asyncio.sleep(0.1)

    end_frames = [f for f in task.queued if isinstance(f, EndTaskFrame)]
    assert len(end_frames) == 1
    assert isinstance(end_frames[0], EndTaskFrame)
    assert end_frames[0].reason == "tool:end_call:user_requested"


# ---------------------------------------------------------------------------
# 5. transfer_to_human emits the right event AND ends the call with
#    reason=transfer_requested
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transfer_to_human_emits_event_and_ends():
    llm = FakeLLM()
    task = FakeTask()
    emit, captured = await _make_emit_recorder()

    register_call_control_handlers(llm, task, call_id="c3", emit=emit)
    params = FakeParams(arguments={"topic": "billing"})
    await llm.handlers["transfer_to_human"](params)
    await asyncio.sleep(0.1)

    assert captured, "emit was never called"
    payload = captured[0]
    assert payload["name"] == "transfer_to_human"
    assert payload["args"] == {"topic": "billing"}

    end_frames = [f for f in task.queued if isinstance(f, EndTaskFrame)]
    assert len(end_frames) == 1
    assert isinstance(end_frames[0], EndTaskFrame)
    assert end_frames[0].reason == "tool:end_call:transfer_requested"

    assert params.results == [
        {"status": "ending", "reason": "transfer_requested"}
    ]


# ---------------------------------------------------------------------------
# 5b. transfer_to_human invokes mark_transfer with the topic, exactly once,
#     before the EndTaskFrame is queued.
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_transfer_to_human_calls_mark_transfer():
    llm = FakeLLM()
    task = FakeTask()
    emit, _ = await _make_emit_recorder()
    seen: list[str] = []

    register_call_control_handlers(
        llm, task,
        call_id="c3b",
        emit=emit,
        mark_transfer=lambda topic: seen.append(topic),
    )
    params = FakeParams(arguments={"topic": "NVR wifi setup"})
    await llm.handlers["transfer_to_human"](params)
    await asyncio.sleep(0.1)

    assert seen == ["NVR wifi setup"]

    # end_call must NOT trigger mark_transfer
    seen.clear()
    await llm.handlers["end_call"](FakeParams(arguments={"reason": "user_requested"}))
    await asyncio.sleep(0.1)
    assert seen == []


# ---------------------------------------------------------------------------
# 6. emit() failure is swallowed: handler still ends the call and
#    invokes result_callback exactly once
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_emit_failure_swallowed():
    llm = FakeLLM()
    task = FakeTask()

    async def bad_emit(_payload):
        raise RuntimeError("boom")

    register_call_control_handlers(llm, task, call_id="c4", emit=bad_emit)
    params = FakeParams(arguments={"reason": "task_completed"})
    await llm.handlers["end_call"](params)
    await asyncio.sleep(0.1)

    end_frames = [f for f in task.queued if isinstance(f, EndTaskFrame)]
    assert len(end_frames) == 1
    assert isinstance(end_frames[0], EndTaskFrame)
    assert end_frames[0].reason == "tool:end_call:task_completed"
    assert len(params.results) == 1


# ---------------------------------------------------------------------------
# 7. Two end_call invocations on the same handler -> only ONE EndTaskFrame,
#    second result_callback receives {"status": "already_ending"}
# ---------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_idempotent_double_end_call():
    llm = FakeLLM()
    task = FakeTask()
    emit, captured = await _make_emit_recorder()

    register_call_control_handlers(llm, task, call_id="c5", emit=emit)

    params1 = FakeParams(arguments={"reason": "user_requested"})
    params2 = FakeParams(arguments={"reason": "user_requested"})

    handler = llm.handlers["end_call"]
    await handler(params1)
    await handler(params2)
    await asyncio.sleep(0.1)

    end_frames = [f for f in task.queued if isinstance(f, EndTaskFrame)]
    assert len(end_frames) == 1
    assert isinstance(end_frames[0], EndTaskFrame)
    assert end_frames[0].reason == "tool:end_call:user_requested"

    assert params1.results == [
        {"status": "ending", "reason": "user_requested"}
    ]
    assert params2.results == [{"status": "already_ending"}]
    # emit should have been called only for the first invocation
    assert len(captured) == 1
