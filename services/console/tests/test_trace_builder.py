"""TraceBuilder contract.

Pinned behaviours (see trace_builder.py for the full mapping spec):

* Builder seeds a synthetic QUESTION step holding the user prompt.
* Each ToolUseBlock from an AssistantMessage adds an INFERENCE step.
* The matching ToolResultBlock from a UserMessage adds an OBSERVATION
  step linked to the call by an Edge(relation=YIELDS) and updates the
  call step's status to OK / FAILED based on is_error.
* TextBlocks become assistant.text SSE events but not trace steps.
* ResultMessage finalises the DecisionTrace.outcome with cost +
  duration metadata.

All tests use plain ``object()`` stand-ins for the SDK message
classes; TraceBuilder dispatches on ``type(msg).__name__`` so the
real classes aren't required.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from console.trace_builder import (
    TraceBuilder,
    _service_from_tool,
    _short_input_detail,
    _short_tool_label,
    _stringify_tool_result_content,
)

# ── SDK-shaped fakes ───────────────────────────────────────────────────────────


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
class ThinkingBlock:
    thinking: str
    signature: str = ""


@dataclass
class AssistantMessage:
    content: list[Any] = field(default_factory=list)
    model: str = "claude"


@dataclass
class UserMessage:
    content: Any = None
    tool_use_result: dict[str, Any] | None = None


@dataclass
class SystemMessage:
    subtype: str = ""
    data: dict[str, Any] = field(default_factory=dict)


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
    result: str | None = "all done"


# ── tests ─────────────────────────────────────────────────────────────────────


def test_builder_seeds_root_question_step() -> None:
    b = TraceBuilder(session_id="sess-1", user_prompt="hello world")
    trace = b.trace
    assert len(trace.steps) == 1
    root = trace.steps[0]
    assert root.kind.value == "question"
    assert root.detail == "hello world"
    assert trace.root == root.id
    assert trace.source == "console"
    assert trace.kind == "chat"


def test_assistant_text_block_emits_event_but_no_step() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    msg = AssistantMessage(content=[TextBlock(text="hi there")])
    events = b.ingest(msg)
    types = [e["type"] for e in events]
    assert "assistant.text" in types
    assert "trace.update" in types
    # No new step beyond the root question.
    assert len(b.trace.steps) == 1


def test_tool_use_adds_pending_inference_step() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    msg = AssistantMessage(content=[
        ToolUseBlock(
            id="tu_1",
            name="mcp__logos__certify_claim",
            input={"argument": "all swans are white"},
        ),
    ])
    events = b.ingest(msg)
    steps = b.trace.steps
    # root + the new tool_use step
    assert len(steps) == 2
    new_step = steps[1]
    assert new_step.kind.value == "inference"
    assert new_step.status.value == "pending"
    assert new_step.source_ref == "mcp__logos__certify_claim"
    assert new_step.label == "logos.certify_claim"
    assert new_step.meta["tool_use_id"] == "tu_1"
    assert new_step.meta["service"] == "logos"
    # An edge from root to the new step.
    edges = b.trace.edges
    assert len(edges) == 1
    assert edges[0].source == b.trace.root
    assert edges[0].target == new_step.id
    # And a tool.pending event.
    assert any(e["type"] == "tool.pending" for e in events)


def test_tool_result_links_to_use_and_updates_status_ok() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    use = AssistantMessage(content=[
        ToolUseBlock(
            id="tu_1",
            name="mcp__mneme__store_memory",
            input={"content": "x"},
        ),
    ])
    b.ingest(use)
    res = UserMessage(content=[
        ToolResultBlock(tool_use_id="tu_1", content="ok", is_error=False),
    ])
    events = b.ingest(res)
    steps = b.trace.steps
    # root + tool_use + tool_result
    assert len(steps) == 3
    use_step = next(
        s for s in steps
        if s.meta.get("tool_use_id") == "tu_1" and s.kind.value == "inference"
    )
    res_step = next(s for s in steps if s.kind.value == "observation")
    assert use_step.status.value == "ok"
    assert res_step.status.value == "ok"
    # Edge use_step → res_step with relation YIELDS
    edges = b.trace.edges
    yields_edges = [
        e for e in edges
        if e.source == use_step.id and e.target == res_step.id
    ]
    assert len(yields_edges) == 1
    assert yields_edges[0].relation.value == "yields"
    # Event surfaced.
    assert any(e["type"] == "tool.result" for e in events)


def test_tool_result_with_is_error_marks_failed() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    b.ingest(AssistantMessage(content=[
        ToolUseBlock(
            id="tu_1",
            name="mcp__logos__certify_claim",
            input={"argument": "P"},
        ),
    ]))
    b.ingest(UserMessage(content=[
        ToolResultBlock(tool_use_id="tu_1", content="refuted", is_error=True),
    ]))
    use_step = next(
        s for s in b.trace.steps if s.kind.value == "inference"
    )
    res_step = next(
        s for s in b.trace.steps if s.kind.value == "observation"
    )
    assert use_step.status.value == "failed"
    assert res_step.status.value == "failed"
    assert res_step.meta["is_error"] is True


def test_thinking_block_adds_note_step() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    msg = AssistantMessage(content=[
        ThinkingBlock(thinking="hmm, swans …"),
    ])
    events = b.ingest(msg)
    steps = b.trace.steps
    assert len(steps) == 2
    note = steps[1]
    assert note.kind.value == "note"
    assert note.label == "thinking"
    assert any(e["type"] == "assistant.thinking" for e in events)


def test_result_message_finalises_outcome() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    events = b.ingest(ResultMessage(result="job done", total_cost_usd=0.07))
    assert b.trace.outcome is not None
    assert b.trace.outcome.verdict == "complete"
    assert b.trace.outcome.summary.startswith("job done")
    assert b.trace.outcome.meta["cost_usd"] == 0.07
    assert any(e["type"] == "session.done" for e in events)


def test_result_message_is_error_marks_outcome_error() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    b.ingest(ResultMessage(result=None, is_error=True))
    assert b.trace.outcome is not None
    assert b.trace.outcome.verdict == "error"


def test_system_error_message_appends_failed_step() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")
    events = b.ingest(SystemMessage(
        subtype="error",
        data={"error": "rate limited"},
    ))
    types = [e["type"] for e in events]
    assert "session.error" in types
    err_steps = [s for s in b.trace.steps if s.label == "system error"]
    assert len(err_steps) == 1
    assert err_steps[0].status.value == "failed"


def test_unknown_message_type_is_silently_ignored() -> None:
    b = TraceBuilder(session_id="s", user_prompt="p")

    class Surprise:
        pass

    assert b.ingest(Surprise()) == []
    assert len(b.trace.steps) == 1  # unchanged


def test_to_dict_returns_serialisable_trace() -> None:
    b = TraceBuilder(session_id="s", user_prompt="hi")
    b.ingest(AssistantMessage(content=[
        ToolUseBlock(
            id="tu_1",
            name="mcp__telos__register_goal",
            input={"contract_json": "{}"},
        ),
    ]))
    d = b.to_dict()
    assert d["source"] == "console"
    assert d["kind"] == "chat"
    assert d["question"] == "hi"
    assert isinstance(d["steps"], list) and len(d["steps"]) == 2
    assert isinstance(d["edges"], list) and len(d["edges"]) == 1


def test_start_event_carries_session_and_trace_ids() -> None:
    b = TraceBuilder(session_id="abc123", user_prompt="hi")
    e = b.start_event()
    assert e["type"] == "session.start"
    assert e["session_id"] == "abc123"
    assert e["trace_id"] == "console-abc123"


# ── pure helpers ──────────────────────────────────────────────────────────────


def test_service_from_tool_strips_mcp_prefix() -> None:
    assert _service_from_tool("mcp__logos__certify_claim") == "logos"
    assert _service_from_tool("mcp__mneme__store_memory") == "mneme"
    # Non-MCP / harness-internal: empty service.
    assert _service_from_tool("Bash") == ""
    assert _service_from_tool("Read") == ""
    assert _service_from_tool("mcp__ab_harness__emit_action") == "ab_harness"


def test_short_tool_label_keeps_dotted_form() -> None:
    assert _short_tool_label("mcp__logos__certify_claim") == "logos.certify_claim"
    assert _short_tool_label("mcp__telos") == "telos"
    assert _short_tool_label("Bash") == "Bash"


def test_short_input_detail_caps_long_strings() -> None:
    long_value = "x" * 200
    detail = _short_input_detail({"k": long_value})
    assert "k=" in detail
    # Values truncated at ~80 chars + "..."
    assert "..." in detail


def test_stringify_tool_result_handles_text_block_list() -> None:
    content = [{"type": "text", "text": "verified"}, {"type": "text", "text": "ok"}]
    assert _stringify_tool_result_content(content) == "verified\nok"


def test_stringify_tool_result_handles_str_and_none() -> None:
    assert _stringify_tool_result_content("plain") == "plain"
    assert _stringify_tool_result_content(None) == "(empty)"
