"""Scripted SDK message iterator for live-stack smoke tests.

Used when ``CONSOLE_FAKE_QUERY=1`` is set on the Console process. The
iterator emits the same canonical sequence the in-process test
``eval/tests/test_console_inprocess.py`` uses — register goal →
decompose plan → result — without spawning the ``claude`` CLI or
calling Anthropic. That makes ``scripts/sandbox-smoke.sh`` fully
reproducible and runnable in any environment that has Python.

The dataclass shapes mirror ``claude_agent_sdk.types`` exactly because
``TraceBuilder`` dispatches on ``type(msg).__name__``; using identical
names lets us avoid pulling the SDK into a sandbox that may not have
it installed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator


@dataclass
class TextBlock:
    text: str


@dataclass
class ToolUseBlock:
    id: str
    name: str
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class ToolResultBlock:
    tool_use_id: str
    content: Any = None
    is_error: bool | None = None


@dataclass
class AssistantMessage:
    content: list[Any] = field(default_factory=list)
    model: str = "claude"


@dataclass
class UserMessage:
    content: Any = None
    tool_use_result: dict[str, Any] | None = None


@dataclass
class ResultMessage:
    subtype: str = "success"
    duration_ms: int = 1234
    duration_api_ms: int = 1000
    is_error: bool = False
    num_turns: int = 4
    session_id: str = "sess"
    stop_reason: str | None = "end_turn"
    total_cost_usd: float | None = 0.04
    usage: dict[str, Any] | None = None
    result: str | None = "registered the goal and verified the plan"


def _scripted_messages() -> list[Any]:
    return [
        AssistantMessage(
            content=[
                TextBlock(text="I'll register the goal first."),
                ToolUseBlock(
                    id="tu_1",
                    name="mcp__telos__register_goal",
                    input={"contract_json": "{}"},
                ),
            ]
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="tu_1",
                    content="goal registered",
                    is_error=False,
                ),
            ]
        ),
        AssistantMessage(
            content=[
                ToolUseBlock(
                    id="tu_2",
                    name="mcp__praxis__decompose_goal",
                    input={"goal": "refactor auth"},
                ),
            ]
        ),
        UserMessage(
            content=[
                ToolResultBlock(
                    tool_use_id="tu_2",
                    content="plan ready",
                    is_error=False,
                ),
            ]
        ),
        ResultMessage(
            result="registered the goal and verified the plan",
            total_cost_usd=0.07,
        ),
    ]


async def fake_query(*, prompt: str, options: Any) -> AsyncIterator[Any]:
    """Drop-in replacement for ``claude_agent_sdk.query``.

    Ignores the prompt + options — the canned sequence is the same on
    every call by design (the smoke test's job is to verify the wire
    format and the trace structure, not Claude's response).
    """
    for msg in _scripted_messages():
        yield msg
