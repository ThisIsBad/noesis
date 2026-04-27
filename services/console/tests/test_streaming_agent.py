"""StreamingMCPAgent contract.

Verifies that the wrapper:
* Forwards every SDK message to the caller (no draining).
* Doesn't add or drop messages.
* Honours the model / max_turns / max_budget_usd kwargs by passing
  them into ClaudeAgentOptions.
* Honours the env-driven service discovery.

The Claude SDK is dependency-injected via ``query_fn``, so these
tests don't spawn the real ``claude`` CLI subprocess.
"""
from __future__ import annotations

from typing import Any, AsyncIterator

import pytest

from console.streaming_agent import (
    NOESIS_SERVICE_NAMES,
    StreamingMCPAgent,
    noesis_mcp_servers_from_env,
)


def _scripted(messages: list[Any]):
    """Return an SDK-shaped query_fn that yields ``messages`` in order."""
    captured: dict[str, Any] = {}

    async def query_fn(*, prompt: str, options: Any) -> AsyncIterator[Any]:
        captured["prompt"] = prompt
        captured["options"] = options
        for m in messages:
            yield m

    return query_fn, captured


async def test_yields_every_message_in_order() -> None:
    sentinel = [object(), object(), object()]
    query_fn, _ = _scripted(sentinel)
    agent = StreamingMCPAgent(query_fn=query_fn)
    seen = [m async for m in agent.chat("hello")]
    assert seen == sentinel


async def test_options_carry_model_max_turns_budget() -> None:
    query_fn, captured = _scripted([])
    agent = StreamingMCPAgent(
        model="claude-haiku-4-5-20251001",
        max_turns=3,
        max_budget_usd=0.10,
        query_fn=query_fn,
    )
    _ = [m async for m in agent.chat("hi")]
    opts = captured["options"]
    assert opts.model == "claude-haiku-4-5-20251001"
    assert opts.max_turns == 3
    assert opts.max_budget_usd == 0.10


async def test_options_wires_mcp_servers_into_allowed_tools() -> None:
    query_fn, captured = _scripted([])
    agent = StreamingMCPAgent(
        mcp_servers={
            "logos": {"type": "sse", "url": "http://x/sse"},
            "mneme": {"type": "sse", "url": "http://y/sse"},
        },
        query_fn=query_fn,
    )
    _ = [m async for m in agent.chat("hi")]
    opts = captured["options"]
    # Both mcp__<name> and mcp__<name>__* are allowed.
    assert "mcp__logos" in opts.allowed_tools
    assert "mcp__logos__*" in opts.allowed_tools
    assert "mcp__mneme__*" in opts.allowed_tools


async def test_prompt_is_forwarded_unchanged() -> None:
    query_fn, captured = _scripted([])
    agent = StreamingMCPAgent(query_fn=query_fn)
    _ = [m async for m in agent.chat("explicit prompt text")]
    assert captured["prompt"] == "explicit prompt text"


def test_negative_budget_rejected() -> None:
    with pytest.raises(ValueError):
        StreamingMCPAgent(max_budget_usd=-0.01)


def test_noesis_mcp_servers_from_env_skips_unset() -> None:
    env = {
        "NOESIS_LOGOS_URL": "http://logos:8000",
        "NOESIS_LOGOS_SECRET": "lsecret",
        "NOESIS_MNEME_URL": "http://mneme:8000",
        # MNEME_SECRET deliberately unset → empty string → still wired
        # but with no Authorization header.
    }
    servers = noesis_mcp_servers_from_env(env=env)
    assert set(servers.keys()) == {"logos", "mneme"}
    assert servers["logos"]["url"] == "http://logos:8000/sse"
    assert servers["logos"]["headers"] == {"Authorization": "Bearer lsecret"}
    assert "headers" not in servers["mneme"]


def test_noesis_mcp_servers_default_names_cover_all_eight() -> None:
    assert set(NOESIS_SERVICE_NAMES) == {
        "logos", "mneme", "praxis", "telos",
        "episteme", "kosmos", "empiria", "techne",
    }
