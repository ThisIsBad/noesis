"""Unit tests for the MCPAgent SDK-driven policy.

The SDK spawns a ``claude`` subprocess, so tests pass a scripted
``query_fn`` that fakes the async message stream and drives the
harness-side ``emit_action`` tool directly. These tests pin:

* ``MCPAgent.act`` extracts the action string the LLM emits via
  ``emit_action`` and returns it to the runner.
* Missing ``emit_action`` (LLM refuses / times out) returns empty
  string, which ``runner.run_episode`` treats as a graceful stop.
* Treatment and baseline factories differ only in their ``mcp_servers``
  dict — same model, same prompt, same max_turns — so any outcome
  delta is attributable to Noesis tooling.
* ``noesis_mcp_servers_from_env`` respects the
  ``NOESIS_<SERVICE>_URL/SECRET`` envelope and silently skips services
  whose URL is unset.
* ``build_treatment_agent`` refuses to build when no services are
  configured (a treatment with zero tools is just another baseline).
"""
from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

import pytest

from noesis_eval.ab import (
    MCPAgent,
    build_baseline_agent,
    build_treatment_agent,
    noesis_mcp_servers_from_env,
)
from noesis_eval.ab.agent import ActionOutcome

pytestmark = pytest.mark.unit


# ── SDK fake ──────────────────────────────────────────────────────────────────


class _FakeSdk:
    """Drives ``MCPAgent._act_async`` without spawning the Claude CLI.

    ``action`` is the string the fake LLM will pass to ``emit_action``.
    ``captured_options`` keeps the last ``ClaudeAgentOptions`` the
    agent constructed so assertions can verify the MCP-server dict,
    prompt, etc.
    ``invocations`` counts how many times the fake was called — one
    per ``act`` turn.
    """

    def __init__(self, action: str | None = "look around") -> None:
        self.action = action
        self.captured_prompt: str | None = None
        self.captured_options: Any = None
        self.invocations = 0

    async def query_fn(
        self, *, prompt: str, options: Any
    ) -> AsyncIterator[dict[str, Any]]:
        self.invocations += 1
        self.captured_prompt = prompt
        self.captured_options = options

        if self.action is not None:
            # Invoke emit_action through the real MCP call_tool handler
            # on the server instance the agent built. This exercises
            # the closure-over-captured path exactly as Claude Code
            # would when streaming a tool call back from the LLM.
            from mcp.types import CallToolRequest, CallToolRequestParams

            server = options.mcp_servers["ab_harness"]["instance"]
            handler = server.request_handlers[CallToolRequest]
            await handler(
                CallToolRequest(
                    method="tools/call",
                    params=CallToolRequestParams(
                        name="emit_action",
                        arguments={"action": self.action},
                    ),
                )
            )

        if False:  # pragma: no cover — need yield to keep this an async gen
            yield {}


@pytest.fixture
def fake_sdk() -> _FakeSdk:
    return _FakeSdk()


# ── act() contract ────────────────────────────────────────────────────────────


def test_act_returns_action_emitted_via_sdk_tool(fake_sdk: _FakeSdk) -> None:
    fake_sdk.action = "go to kitchen"
    agent = MCPAgent(query_fn=fake_sdk.query_fn)
    result = agent.act("find the apple", "you are in the hallway", [])
    assert result == "go to kitchen"
    assert fake_sdk.invocations == 1


def test_act_returns_empty_string_when_emit_action_never_called(
    fake_sdk: _FakeSdk,
) -> None:
    """Runner treats empty-string as 'agent has nothing to say' and
    breaks the loop — better than garbage-stepping the env."""
    fake_sdk.action = None
    agent = MCPAgent(query_fn=fake_sdk.query_fn)
    assert agent.act("goal", "obs", []) == ""


def test_act_formats_prompt_with_goal_observation_and_history(
    fake_sdk: _FakeSdk,
) -> None:
    agent = MCPAgent(query_fn=fake_sdk.query_fn)
    history = [
        ActionOutcome("open door", "door creaks open", 0.0, {}),
        ActionOutcome("look", "you see a key", 0.0, {}),
    ]
    agent.act("retrieve the key", "you are inside", history)

    prompt = fake_sdk.captured_prompt or ""
    assert "retrieve the key" in prompt
    assert "you are inside" in prompt
    assert "open door" in prompt
    assert "you see a key" in prompt
    # History order matters: the most-recent action should appear after
    # the earlier one so the LLM sees trajectory direction.
    assert prompt.index("open door") < prompt.index("you see a key")


def test_act_marks_empty_history_explicitly(fake_sdk: _FakeSdk) -> None:
    """First-turn prompts say 'empty' instead of listing nothing, so
    a bug that silently drops history can't masquerade as the first
    turn."""
    agent = MCPAgent(query_fn=fake_sdk.query_fn)
    agent.act("goal", "obs", [])
    assert "empty" in (fake_sdk.captured_prompt or "")


# ── mcp_servers wiring ────────────────────────────────────────────────────────


def test_mcp_servers_dict_passed_through_to_sdk_options(
    fake_sdk: _FakeSdk,
) -> None:
    """A/B correctness hinges on treatment vs. baseline differing only
    in mcp_servers. If the agent ever dropped, renamed, or reordered
    the dict, the A/B would silently run something else."""
    servers = {
        "mneme": {"type": "sse", "url": "http://example/sse"},
        "praxis": {"type": "sse", "url": "http://example2/sse"},
    }
    agent = MCPAgent(mcp_servers=servers, query_fn=fake_sdk.query_fn)
    agent.act("g", "o", [])

    # Agent always adds its own ab_harness server; everything else
    # must be preserved verbatim.
    passed = fake_sdk.captured_options.mcp_servers
    assert passed["mneme"] == servers["mneme"]
    assert passed["praxis"] == servers["praxis"]
    assert "ab_harness" in passed


def test_allowed_tools_covers_every_mcp_server_and_emit_action(
    fake_sdk: _FakeSdk,
) -> None:
    """If `allowed_tools` is too tight the LLM gets `PermissionDenied`
    every time it tries to call a Noesis tool, which looks identical
    to 'the tool wasn't useful' — but poisons the A/B."""
    servers = {
        "mneme": {"type": "sse", "url": "http://m/sse"},
        "telos": {"type": "sse", "url": "http://t/sse"},
    }
    agent = MCPAgent(mcp_servers=servers, query_fn=fake_sdk.query_fn)
    agent.act("g", "o", [])

    allowed = fake_sdk.captured_options.allowed_tools
    assert any("mneme" in t for t in allowed)
    assert any("telos" in t for t in allowed)
    assert any("ab_harness" in t for t in allowed)


# ── env-driven server discovery ───────────────────────────────────────────────


def test_noesis_servers_from_env_builds_sse_configs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOESIS_MNEME_URL", "https://mneme.example/")
    monkeypatch.setenv("NOESIS_MNEME_SECRET", "s3cret")
    monkeypatch.setenv("NOESIS_PRAXIS_URL", "https://praxis.example")
    monkeypatch.delenv("NOESIS_PRAXIS_SECRET", raising=False)
    monkeypatch.delenv("NOESIS_TELOS_URL", raising=False)

    servers = noesis_mcp_servers_from_env()

    assert set(servers) == {"mneme", "praxis"}  # telos dropped, URL unset
    assert servers["mneme"]["type"] == "sse"
    assert servers["mneme"]["url"] == "https://mneme.example/sse"
    assert servers["mneme"]["headers"] == {"Authorization": "Bearer s3cret"}
    # No secret set → no Authorization header, not an empty one.
    assert "headers" not in servers["praxis"]


def test_noesis_servers_from_env_strips_trailing_slash(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("NOESIS_MNEME_URL", "https://mneme.example/")
    monkeypatch.delenv("NOESIS_PRAXIS_URL", raising=False)
    monkeypatch.delenv("NOESIS_TELOS_URL", raising=False)
    servers = noesis_mcp_servers_from_env()
    # Trailing slash on base URL would produce "//sse"; the helper must strip.
    assert servers["mneme"]["url"] == "https://mneme.example/sse"


def test_noesis_servers_from_env_returns_empty_when_nothing_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("MNEME", "PRAXIS", "TELOS"):
        monkeypatch.delenv(f"NOESIS_{name}_URL", raising=False)
        monkeypatch.delenv(f"NOESIS_{name}_SECRET", raising=False)
    assert noesis_mcp_servers_from_env() == {}


# ── factory helpers ───────────────────────────────────────────────────────────


def test_build_baseline_has_empty_server_dict(fake_sdk: _FakeSdk) -> None:
    agent = build_baseline_agent(query_fn=fake_sdk.query_fn)
    agent.act("g", "o", [])
    # Only the ab_harness server the agent always adds — nothing else.
    assert set(fake_sdk.captured_options.mcp_servers) == {"ab_harness"}
    assert agent.name == "mcp-baseline"


def test_build_treatment_raises_when_no_services_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("MNEME", "PRAXIS", "TELOS"):
        monkeypatch.delenv(f"NOESIS_{name}_URL", raising=False)
    with pytest.raises(RuntimeError, match="NOESIS_.*_URL"):
        build_treatment_agent()


def test_build_treatment_names_and_wires_services(
    monkeypatch: pytest.MonkeyPatch, fake_sdk: _FakeSdk
) -> None:
    monkeypatch.setenv("NOESIS_MNEME_URL", "https://mneme.example")
    monkeypatch.setenv("NOESIS_MNEME_SECRET", "tok")
    monkeypatch.delenv("NOESIS_PRAXIS_URL", raising=False)
    monkeypatch.delenv("NOESIS_TELOS_URL", raising=False)

    agent = build_treatment_agent(query_fn=fake_sdk.query_fn)
    assert agent.name == "mcp-treatment"
    agent.act("g", "o", [])
    assert "mneme" in fake_sdk.captured_options.mcp_servers


def test_treatment_and_baseline_share_model_prompt_and_max_turns(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The canonical A/B's validity hinges on this. If the two agents
    diverged on model, system prompt, or max_turns, a positive delta
    could be anything — not just 'Noesis helped'."""
    monkeypatch.setenv("NOESIS_MNEME_URL", "https://mneme.example")

    treatment_sdk = _FakeSdk(action="a")
    baseline_sdk = _FakeSdk(action="a")
    treatment = build_treatment_agent(query_fn=treatment_sdk.query_fn)
    baseline = build_baseline_agent(query_fn=baseline_sdk.query_fn)

    treatment.act("g", "o", [])
    baseline.act("g", "o", [])

    t_opts = treatment_sdk.captured_options
    b_opts = baseline_sdk.captured_options
    assert t_opts.model == b_opts.model
    assert t_opts.system_prompt == b_opts.system_prompt
    assert t_opts.max_turns == b_opts.max_turns


# ── asyncio isolation ────────────────────────────────────────────────────────


def test_act_runs_fresh_event_loop_per_turn(fake_sdk: _FakeSdk) -> None:
    """``asyncio.run`` creates/destroys a loop per call. If MCPAgent
    leaked loops across turns the runner's 16-step episodes would blow
    up with 'loop already running'."""
    agent = MCPAgent(query_fn=fake_sdk.query_fn)
    for _ in range(3):
        assert agent.act("g", "o", []) == fake_sdk.action
    assert fake_sdk.invocations == 3
    # Sanity: we aren't smuggling a loop out.
    with pytest.raises(RuntimeError):
        asyncio.get_running_loop()
