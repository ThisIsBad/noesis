"""``MCPAgent`` — turn-by-turn Claude agent driven by ``claude-agent-sdk``.

Each ``act`` call runs one fresh ``query()`` against the local Claude
Code CLI: the SDK spawns the CLI as a subprocess, the CLI authenticates
against whatever session the host is using (e.g. a Claude Max seat),
and the LLM streams back tool calls and messages until it invokes the
harness-side ``emit_action`` tool with its chosen next action.

The MCP servers passed via ``mcp_servers`` are the treatment / baseline
knob: the canonical A/B holds model + prompt + env fixed and flips only
this dict. Treatment gets Mneme / Praxis / Telos wired in as tools;
baseline gets nothing but the ``emit_action`` slot and has to reason
from prompt context alone. Any delta between the two runs is the
value-added of the Noesis MCP stack.

Unit tests pass a scripted ``query_fn`` that fakes SDK messages so the
harness can be pinned without a running CLI. The live integration
lives behind ``pytest.mark.slow`` and expects ``claude`` on PATH plus
``NOESIS_*_URL`` env vars for the services.
"""
from __future__ import annotations

import asyncio
import os
from typing import Any, AsyncIterator, Awaitable, Callable, Sequence, cast

from claude_agent_sdk import (
    ClaudeAgentOptions,
    create_sdk_mcp_server,
    query,
    tool,
)
from claude_agent_sdk.types import (
    McpServerConfig,
    McpSSEServerConfig,
)

from .agent import ActionOutcome

DEFAULT_MAX_TURNS = 8
"""Ceiling on LLM turns per agent step. High enough to let Claude
chain a memory lookup → a plan lookup → an ``emit_action``, low enough
that a stuck model can't spin indefinitely. Matches the rough depth
of tool use we observed in the Durchstich probes."""


SYSTEM_PROMPT = """\
You are a turn-by-turn agent in a text-adventure-style environment.

On each turn you receive a goal, the current observation, and the
history of (action, observation) pairs so far. Your job is to choose
exactly ONE next action string for the environment.

If MCP tools are available (memory lookup, planning, goal alignment,
etc.) you may use them to reason. When you have decided, call the
`emit_action` tool with the exact action string — do not emit the
action as prose. Call `emit_action` exactly once per turn.
"""


QueryFn = Callable[..., AsyncIterator[Any]]


class MCPAgent:
    """Claude agent with a pluggable set of MCP tool servers.

    Stateless across episodes — the runner hands back the full history
    on every call, so this class holds no per-task mutable state. That
    matters for suite-level A/B: an agent that remembers the *previous*
    task's observations would muddy the per-task delta.

    ``max_budget_usd`` is a per-``act`` cost cap. The Claude CLI's
    ``ClaudeAgentOptions.max_budget_usd`` aborts the subprocess once
    its accounting crosses the threshold — a backstop for runaway
    tool-use loops. Default None (no cap). Set this when running
    real A/B sweeps to bound the damage from a misbehaving turn.
    """

    def __init__(
        self,
        *,
        name: str = "mcp",
        model: str = "claude-sonnet-4-6",
        mcp_servers: dict[str, McpServerConfig] | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        system_prompt: str = SYSTEM_PROMPT,
        query_fn: QueryFn | None = None,
        max_budget_usd: float | None = None,
    ) -> None:
        self.name = name
        self._model = model
        self._mcp_servers = dict(mcp_servers or {})
        self._max_turns = max_turns
        self._system_prompt = system_prompt
        self._query_fn: QueryFn = query_fn if query_fn is not None else query
        if max_budget_usd is not None and max_budget_usd <= 0:
            raise ValueError(
                f"max_budget_usd must be positive, got {max_budget_usd}"
            )
        self._max_budget_usd = max_budget_usd

    def act(
        self, goal: str, observation: str, history: Sequence[ActionOutcome]
    ) -> str:
        return asyncio.run(self._act_async(goal, observation, history))

    async def _act_async(
        self, goal: str, observation: str, history: Sequence[ActionOutcome]
    ) -> str:
        captured: dict[str, str] = {}

        @tool(  # type: ignore[untyped-decorator]
            "emit_action",
            "Emit the single action string the environment should execute next.",
            {"action": str},
        )
        async def emit_action(args: dict[str, Any]) -> dict[str, Any]:
            captured["action"] = str(args.get("action", ""))
            return {
                "content": [
                    {"type": "text", "text": "action recorded"}
                ]
            }

        ab_server = create_sdk_mcp_server(
            name="ab_harness", tools=[emit_action]
        )

        servers: dict[str, McpServerConfig] = dict(self._mcp_servers)
        servers["ab_harness"] = ab_server

        allowed_tools = [f"mcp__{name}" for name in servers] + [
            f"mcp__{name}__*" for name in servers
        ]

        options = ClaudeAgentOptions(
            model=self._model,
            mcp_servers=servers,
            system_prompt=self._system_prompt,
            max_turns=self._max_turns,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            max_budget_usd=self._max_budget_usd,
        )

        prompt = _format_prompt(goal, observation, history)
        async for _msg in self._query_fn(prompt=prompt, options=options):
            # Drain the stream; the SDK invokes `emit_action` as a
            # side effect and populates `captured`.
            pass

        return captured.get("action", "")


def _format_prompt(
    goal: str, observation: str, history: Sequence[ActionOutcome]
) -> str:
    lines = [f"Goal: {goal}", f"Current observation: {observation}"]
    if history:
        lines.append("History (most recent last):")
        for i, h in enumerate(history, start=1):
            lines.append(
                f"  {i}. action={h.action!r} -> obs={h.observation!r}"
            )
    else:
        lines.append("History: (empty — this is the first turn)")
    lines.append(
        "Call the emit_action tool with the next action string."
    )
    return "\n".join(lines)


def _sse_config(url: str, secret: str) -> McpSSEServerConfig:
    config: dict[str, Any] = {"type": "sse", "url": f"{url}/sse"}
    if secret:
        config["headers"] = {"Authorization": f"Bearer {secret}"}
    return cast(McpSSEServerConfig, config)


NOESIS_SERVICE_NAMES = ("mneme", "praxis", "telos")
"""Phase-1 services exposed to the treatment agent. Additional services
(episteme, kosmos, etc.) can be plumbed in by extending this tuple
once their MCP surface stabilises — for now the A/B focuses on
Stage-3 foundations."""


def noesis_mcp_servers_from_env(
    names: Sequence[str] = NOESIS_SERVICE_NAMES,
) -> dict[str, McpServerConfig]:
    """Build SSE configs for each reachable Noesis service.

    Reads ``NOESIS_<SERVICE>_URL`` / ``NOESIS_<SERVICE>_SECRET`` — the
    same envelope the integration fixtures already use. Services whose
    URL isn't set are silently dropped; callers that need at least one
    service should check the returned dict.
    """
    servers: dict[str, McpServerConfig] = {}
    for name in names:
        url = os.getenv(f"NOESIS_{name.upper()}_URL")
        if not url:
            continue
        secret = os.getenv(f"NOESIS_{name.upper()}_SECRET", "")
        servers[name] = _sse_config(url.rstrip("/"), secret)
    return servers


_BUDGET_ENV_VAR = "NOESIS_AB_MAX_BUDGET_USD"
"""Env-var override for the per-``act`` cost cap on the SDK agents.

Set to a positive float to put a safety rail under both
``build_treatment_agent`` and ``build_baseline_agent`` without
plumbing a CLI flag through the wrapper. Intentionally named with
the ``NOESIS_`` prefix so it matches the service-URL env envelope
the rest of the harness follows.
"""


def _max_budget_from_env() -> float | None:
    raw = os.getenv(_BUDGET_ENV_VAR)
    if raw is None or not raw.strip():
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{_BUDGET_ENV_VAR}={raw!r} is not a valid float"
        ) from exc
    if value <= 0:
        raise RuntimeError(
            f"{_BUDGET_ENV_VAR}={raw!r} must be positive"
        )
    return value


def build_treatment_agent(
    *,
    model: str = "claude-sonnet-4-6",
    max_turns: int = DEFAULT_MAX_TURNS,
    query_fn: QueryFn | None = None,
    max_budget_usd: float | None = None,
) -> MCPAgent:
    """MCPAgent with every reachable Noesis service wired in.

    Raises ``RuntimeError`` if no service URLs are configured — running
    the 'treatment' side of the A/B without any Noesis tools would be
    the same experiment as baseline, which is almost certainly a
    misconfiguration, not an intention.

    If ``max_budget_usd`` is None, falls back to the
    ``NOESIS_AB_MAX_BUDGET_USD`` env var so CI and the wrapper can
    set a cap without threading a CLI flag.
    """
    servers = noesis_mcp_servers_from_env()
    if not servers:
        raise RuntimeError(
            "treatment agent needs at least one NOESIS_<SERVICE>_URL "
            "env var set (tried: "
            + ", ".join(f"NOESIS_{n.upper()}_URL" for n in NOESIS_SERVICE_NAMES)
            + ")"
        )
    return MCPAgent(
        name="mcp-treatment",
        model=model,
        mcp_servers=servers,
        max_turns=max_turns,
        query_fn=query_fn,
        max_budget_usd=(
            max_budget_usd if max_budget_usd is not None
            else _max_budget_from_env()
        ),
    )


def build_baseline_agent(
    *,
    model: str = "claude-sonnet-4-6",
    max_turns: int = DEFAULT_MAX_TURNS,
    query_fn: QueryFn | None = None,
    max_budget_usd: float | None = None,
) -> MCPAgent:
    """MCPAgent with no Noesis servers — same model / prompt, no memory
    / planning / goal tooling. The baseline side of the canonical A/B.

    Same env-var fallback for ``max_budget_usd`` as the treatment
    factory so both sides share a budget rail by default.
    """
    return MCPAgent(
        name="mcp-baseline",
        model=model,
        mcp_servers={},
        max_turns=max_turns,
        query_fn=query_fn,
        max_budget_usd=(
            max_budget_usd if max_budget_usd is not None
            else _max_budget_from_env()
        ),
    )


__all__ = [
    "DEFAULT_MAX_TURNS",
    "MCPAgent",
    "NOESIS_SERVICE_NAMES",
    "SYSTEM_PROMPT",
    "build_baseline_agent",
    "build_treatment_agent",
    "noesis_mcp_servers_from_env",
]

# Silence unused-import warnings on helpers that only exist for public re-use.
_ = Awaitable
