"""Translate Claude Agent SDK message stream into a live DecisionTrace.

The SDK yields four message types we care about:

* ``AssistantMessage`` — has a ``content`` list of blocks. The blocks
  we map are ``ToolUseBlock`` (Claude calls a tool) and ``TextBlock``
  (Claude says something). ``ThinkingBlock`` is captured as a NOTE
  step but not emitted to the chat pane.
* ``UserMessage`` — when ``tool_use_result`` is set, this is a tool
  return; we map the tool_result to an OBSERVATION step linked to its
  matching ToolUseBlock by ``tool_use_id``.
* ``SystemMessage`` — init events, mostly ignored for the trace; a
  few subtypes (``error``) are surfaced as INFO steps.
* ``ResultMessage`` — final summary; we use ``result`` (the assistant's
  closing text) as the trace ``Outcome.summary`` and the cost +
  duration as outcome metadata.

Mapping decisions for Phase 1 (deliberately coarse — refine when we
have real session traces to measure against):

    ToolUseBlock(name="mcp__logos__certify_claim", input=…)
        → ReasoningStep(kind=INFERENCE, source_ref="logos/certify_claim",
                        label="logos.certify_claim", detail=str(input))

    UserMessage with tool_use_result for that tool_use_id
        → ReasoningStep(kind=OBSERVATION, source_ref="logos/certify_claim",
                        status=OK if not is_error else FAILED,
                        detail=str(content))
        plus Edge(source=tool_use_step, target=tool_result_step,
                  relation=YIELDS)

    TextBlock from assistant
        → not added to the trace (chat pane only) unless it's the only
          content the SDK produced (then becomes the trace Outcome)

    ThinkingBlock
        → ReasoningStep(kind=NOTE, label="thinking", detail=text,
                        status=INFO)

The trace's root is always a synthetic QUESTION step holding the
user's original prompt — that's the natural anchor for the DAG.

The TraceBuilder is also the source of every SSE event Console emits:

    {"type": "session.start", "session_id": "..."}
    {"type": "assistant.text", "text": "..."}
    {"type": "trace.update",   "trace": {...DecisionTrace...}}
    {"type": "session.done",   "outcome": "...", "cost_usd": 0.04}
    {"type": "session.error",  "error": "..."}

The builder owns the SSE-event shape so the server doesn't have to
care about message-type translation; it just forwards what the
builder produces.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any

from theoria.models import (
    DecisionTrace,
    Edge,
    EdgeRelation,
    Outcome,
    ReasoningStep,
    StepKind,
    StepStatus,
)


@dataclass
class _ToolCall:
    """Bookkeeping for a tool_use awaiting its tool_result."""

    tool_use_id: str
    tool_name: str
    step_id: str
    service: str  # "logos", "mneme", … or "" for non-MCP tools


@dataclass
class TraceBuilder:
    """Stateful translator from SDK messages → DecisionTrace + SSE events."""

    session_id: str
    user_prompt: str

    _trace: DecisionTrace = field(init=False)
    _root_id: str = field(init=False)
    _tool_calls: dict[str, _ToolCall] = field(default_factory=dict)
    _last_step_id: str = field(init=False)
    _step_counter: int = 0
    _accumulated_text: str = ""
    _last_assistant_step_id: str | None = None

    def __post_init__(self) -> None:
        self._root_id = self._next_id("q")
        root_step = ReasoningStep(
            id=self._root_id,
            kind=StepKind.QUESTION,
            label="user prompt",
            detail=self.user_prompt,
            status=StepStatus.INFO,
        )
        self._trace = DecisionTrace(
            id=f"console-{self.session_id}",
            title=_short_title(self.user_prompt),
            question=self.user_prompt,
            source="console",
            kind="chat",
            root=self._root_id,
            steps=[root_step],
            edges=[],
            tags=["console", "phase1"],
            meta={"session_id": self.session_id},
        )
        self._last_step_id = self._root_id

    # ── public surface ─────────────────────────────────────────────────

    def start_event(self) -> dict[str, Any]:
        return {
            "type": "session.start",
            "session_id": self.session_id,
            "trace_id": self._trace.id,
        }

    def ingest(self, msg: Any) -> list[dict[str, Any]]:
        """Translate one SDK message; return the SSE events to push."""
        cls_name = type(msg).__name__
        if cls_name == "AssistantMessage":
            return self._on_assistant_message(msg)
        if cls_name == "UserMessage":
            return self._on_user_message(msg)
        if cls_name == "SystemMessage":
            return self._on_system_message(msg)
        if cls_name == "ResultMessage":
            return self._on_result_message(msg)
        # Unknown message type — record but don't fail.
        return []

    @property
    def trace(self) -> DecisionTrace:
        return self._trace

    def to_dict(self) -> dict[str, Any]:
        # Theoria's models are dataclass-based; .to_dict() is typed as Any
        # because dataclass serialization is dynamic. We know it's a dict.
        out: dict[str, Any] = self._trace.to_dict()
        return out

    # ── per-message-type handlers ──────────────────────────────────────

    def _on_assistant_message(self, msg: Any) -> list[dict[str, Any]]:
        events: list[dict[str, Any]] = []
        content = getattr(msg, "content", None) or []
        for block in content:
            block_name = type(block).__name__
            if block_name == "TextBlock":
                text = getattr(block, "text", "") or ""
                if text.strip():
                    self._accumulated_text += text + "\n"
                    events.append({"type": "assistant.text", "text": text})
            elif block_name == "ToolUseBlock":
                events.extend(self._on_tool_use(block))
            elif block_name == "ThinkingBlock":
                thinking = getattr(block, "thinking", "") or ""
                if thinking.strip():
                    events.extend(self._on_thinking(thinking))
            # ServerToolUseBlock / ServerToolResultBlock: ignore for Phase 1
        if events:
            events.append(self._trace_update_event())
        return events

    def _on_user_message(self, msg: Any) -> list[dict[str, Any]]:
        # We only care about UserMessages that carry a tool_use_result.
        # Plain user echoes (the original prompt the SDK loops back) carry
        # no tool_use_result and don't produce trace steps.
        if not getattr(msg, "tool_use_result", None):
            content = getattr(msg, "content", None) or []
            # Could be a list of ToolResultBlock if the SDK splits them out.
            tool_result_blocks = [
                b
                for b in (content if isinstance(content, list) else [])
                if type(b).__name__ == "ToolResultBlock"
            ]
            if not tool_result_blocks:
                return []
            events: list[dict[str, Any]] = []
            for block in tool_result_blocks:
                events.extend(self._on_tool_result(block))
            if events:
                events.append(self._trace_update_event())
            return events
        # The SDK tucks the result into the .tool_use_result attr;
        # find the matching ToolUseBlock from .content if present.
        return self._on_tool_use_result(msg)

    def _on_system_message(self, msg: Any) -> list[dict[str, Any]]:
        subtype = getattr(msg, "subtype", "") or ""
        if subtype == "error":
            data = getattr(msg, "data", {}) or {}
            error_text = str(data.get("error") or data.get("message") or data)
            step_id = self._next_id("err")
            self._add_step(
                ReasoningStep(
                    id=step_id,
                    kind=StepKind.NOTE,
                    label="system error",
                    detail=error_text,
                    status=StepStatus.FAILED,
                ),
                parent=self._last_step_id,
                relation=EdgeRelation.SUPPORTS,
            )
            return [
                {"type": "session.error", "error": error_text},
                self._trace_update_event(),
            ]
        return []

    def _on_result_message(self, msg: Any) -> list[dict[str, Any]]:
        is_error = bool(getattr(msg, "is_error", False))
        result_text = (
            getattr(msg, "result", None)
            or self._accumulated_text.strip()
            or "no result text"
        )
        cost = getattr(msg, "total_cost_usd", None)
        duration_ms = getattr(msg, "duration_ms", None)
        verdict = "error" if is_error else "complete"
        self._trace.outcome = Outcome(
            verdict=verdict,
            summary=str(result_text)[:2000],
            confidence=None,
            meta={
                "cost_usd": cost,
                "duration_ms": duration_ms,
                "num_turns": getattr(msg, "num_turns", None),
                "stop_reason": getattr(msg, "stop_reason", None),
            },
        )
        return [
            self._trace_update_event(),
            {
                "type": "session.done",
                "outcome": verdict,
                "summary": str(result_text)[:500],
                "cost_usd": cost,
                "duration_ms": duration_ms,
            },
        ]

    # ── block-level helpers ────────────────────────────────────────────

    def _on_tool_use(self, block: Any) -> list[dict[str, Any]]:
        tool_use_id = str(getattr(block, "id", ""))
        tool_name = str(getattr(block, "name", "")) or "unknown_tool"
        tool_input = getattr(block, "input", {}) or {}
        service = _service_from_tool(tool_name)
        step_id = self._next_id("tu")
        label = _short_tool_label(tool_name)
        detail = _short_input_detail(tool_input)
        step = ReasoningStep(
            id=step_id,
            kind=StepKind.INFERENCE,
            label=label,
            detail=detail,
            status=StepStatus.PENDING,
            source_ref=tool_name,
            meta={"tool_use_id": tool_use_id, "service": service},
        )
        self._add_step(step, parent=self._last_step_id, relation=EdgeRelation.SUPPORTS)
        self._tool_calls[tool_use_id] = _ToolCall(
            tool_use_id=tool_use_id,
            tool_name=tool_name,
            step_id=step_id,
            service=service,
        )
        self._last_assistant_step_id = step_id
        return [
            {
                "type": "tool.pending",
                "tool_use_id": tool_use_id,
                "tool_name": tool_name,
                "service": service,
                "input": tool_input,
            },
        ]

    def _on_tool_result(self, block: Any) -> list[dict[str, Any]]:
        tool_use_id = str(getattr(block, "tool_use_id", ""))
        is_error = bool(getattr(block, "is_error", False))
        content = getattr(block, "content", None)
        text = _stringify_tool_result_content(content)
        return self._record_tool_result(tool_use_id, is_error, text, content)

    def _on_tool_use_result(self, msg: Any) -> list[dict[str, Any]]:
        # The SDK stores the result on the UserMessage itself; the matching
        # tool_use_id is on the corresponding ToolResultBlock in .content.
        events: list[dict[str, Any]] = []
        content = getattr(msg, "content", None) or []
        if isinstance(content, list):
            for block in content:
                if type(block).__name__ == "ToolResultBlock":
                    events.extend(self._on_tool_result(block))
        if events:
            events.append(self._trace_update_event())
        return events

    def _on_thinking(self, thinking_text: str) -> list[dict[str, Any]]:
        step_id = self._next_id("th")
        step = ReasoningStep(
            id=step_id,
            kind=StepKind.NOTE,
            label="thinking",
            detail=thinking_text[:2000],
            status=StepStatus.INFO,
        )
        self._add_step(step, parent=self._last_step_id, relation=EdgeRelation.SUPPORTS)
        return [{"type": "assistant.thinking", "text": thinking_text}]

    # ── tracking + helpers ─────────────────────────────────────────────

    def _record_tool_result(
        self,
        tool_use_id: str,
        is_error: bool,
        result_text: str,
        raw_content: Any,
    ) -> list[dict[str, Any]]:
        call = self._tool_calls.get(tool_use_id)
        # Mark the original tool_use step's status now that we know the verdict.
        if call is not None:
            for step in self._trace.steps:
                if step.id == call.step_id:
                    step.status = StepStatus.FAILED if is_error else StepStatus.OK
                    break
        result_step_id = self._next_id("tr")
        result_step = ReasoningStep(
            id=result_step_id,
            kind=StepKind.OBSERVATION,
            label=(f"{call.tool_name} result" if call is not None else "tool result"),
            detail=result_text[:2000],
            status=StepStatus.FAILED if is_error else StepStatus.OK,
            source_ref=call.tool_name if call is not None else None,
            meta={
                "tool_use_id": tool_use_id,
                "is_error": is_error,
                "service": call.service if call is not None else "",
            },
        )
        parent = call.step_id if call is not None else self._last_step_id
        self._add_step(result_step, parent=parent, relation=EdgeRelation.YIELDS)
        self._last_step_id = result_step_id
        return [
            {
                "type": "tool.result",
                "tool_use_id": tool_use_id,
                "tool_name": call.tool_name if call is not None else "unknown",
                "service": call.service if call is not None else "",
                "is_error": is_error,
                "content": (
                    raw_content if isinstance(raw_content, (str, list)) else None
                ),
                "text": result_text[:500],
            },
        ]

    def _add_step(
        self,
        step: ReasoningStep,
        *,
        parent: str,
        relation: EdgeRelation,
    ) -> None:
        self._trace.steps.append(step)
        self._trace.edges.append(Edge(source=parent, target=step.id, relation=relation))
        self._last_step_id = step.id

    def _next_id(self, prefix: str) -> str:
        self._step_counter += 1
        return f"{prefix}-{self._step_counter:03d}-{uuid.uuid4().hex[:6]}"

    def _trace_update_event(self) -> dict[str, Any]:
        return {"type": "trace.update", "trace": self.to_dict()}


# ── pure helpers (importable by tests) ────────────────────────────────────────


def _service_from_tool(tool_name: str) -> str:
    """``mcp__logos__certify_claim`` → ``logos``.

    Non-MCP tool names ("Bash", "Read", harness-internal "ab_harness")
    return "" so the trace pane can colour them neutrally.
    """
    if not tool_name.startswith("mcp__"):
        return ""
    rest = tool_name[len("mcp__") :]
    head, _sep, _tail = rest.partition("__")
    return head


def _short_tool_label(tool_name: str) -> str:
    if tool_name.startswith("mcp__"):
        rest = tool_name[len("mcp__") :]
        head, _sep, tail = rest.partition("__")
        return f"{head}.{tail}" if tail else head
    return tool_name


def _short_input_detail(tool_input: dict[str, Any]) -> str:
    """Cap the tool-input rendering at ~400 chars for the DAG label."""
    if not tool_input:
        return ""
    items = []
    for k, v in tool_input.items():
        s = str(v)
        if len(s) > 80:
            s = s[:77] + "..."
        items.append(f"{k}={s}")
    text = ", ".join(items)
    return text[:400] + ("…" if len(text) > 400 else "")


def _short_title(prompt: str) -> str:
    text = prompt.strip().replace("\n", " ")
    return text[:80] + ("…" if len(text) > 80 else "")


def _stringify_tool_result_content(content: Any) -> str:
    if content is None:
        return "(empty)"
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    parts.append(str(item.get("text", "")))
                else:
                    parts.append(str(item))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)
