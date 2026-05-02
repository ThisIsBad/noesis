"""Claude Agent SDK wrapper that yields each message as it arrives.

The eval harness's ``MCPAgent._act_async()`` (eval/src/noesis_eval/ab/
mcp_agent.py) drains the SDK's message stream for the side effect of
the in-process ``emit_action`` tool — it returns one final action
string per call. That's the right shape for batch A/B benchmarks; it's
the wrong shape for a chat UI that needs to display intermediate
reasoning as it happens.

``StreamingMCPAgent`` is a *parallel* implementation, deliberately not
a subclass. It:

* binds the same ClaudeAgentOptions surface (model, mcp_servers,
  max_turns, max_budget_usd) the harness uses;
* skips the harness's ``emit_action`` mechanism — Console doesn't
  need a single emitted action; it consumes the whole stream;
* yields each ``Message`` from ``claude_agent_sdk.query()`` directly
  to the caller, which turns the orchestration into an async iterator.

For dependency injection (and tests), ``query_fn`` defaults to
``claude_agent_sdk.query`` but accepts any callable returning an
``AsyncIterator``. Tests inject a scripted iterator without spawning
the real ``claude`` CLI.
"""

from __future__ import annotations

from typing import Any, AsyncIterator, Callable, Sequence, cast

from claude_agent_sdk import ClaudeAgentOptions, query
from claude_agent_sdk.types import (
    McpServerConfig,
    McpSSEServerConfig,
)

DEFAULT_MAX_TURNS = 12
"""Higher than the eval harness's 8 because Console runs are
multi-step orchestration scenarios (register goal → decompose →
verify → commit → store → calibrate → …) where 8 turns is tight."""

DEFAULT_SYSTEM_PROMPT = """\
You are the orchestrator of the Noesis cognitive stack — a verified
agent architecture made of nine MCP services:

* logos     — formal verification (Z3 / Lean) of claims and policies
* mneme     — persistent episodic + semantic memory with proof certs
* praxis    — hierarchical planning + Tree-of-Thoughts search
* telos     — goal contracts + drift / alignment monitoring
* episteme  — confidence calibration + competence mapping
* kosmos    — causal world model (do-calculus)
* empiria   — experience accumulation + lesson extraction
* techne    — verified skill library (cert-backed strategies)

Use the tools liberally. The user is watching the trace as it
unfolds — each tool call shows up immediately in their UI. When you
write durable state (mneme.store, praxis.commit_step, techne.store,
empiria.record), prefer to verify the underlying claim with Logos
first; the user paid for the proof, surface it.

When you're done, give a short plain-English summary of what you did
and what you learned, in 2-3 sentences. Don't restate every tool
call — the trace pane already shows that.
"""


QueryFn = Callable[..., AsyncIterator[Any]]


class StreamingMCPAgent:
    """Yields each Claude SDK message as it arrives; no draining."""

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        mcp_servers: dict[str, McpServerConfig] | None = None,
        max_turns: int = DEFAULT_MAX_TURNS,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
        max_budget_usd: float | None = None,
        query_fn: QueryFn | None = None,
    ) -> None:
        self._model = model
        self._mcp_servers = dict(mcp_servers or {})
        self._max_turns = max_turns
        self._system_prompt = system_prompt
        if max_budget_usd is not None and max_budget_usd <= 0:
            raise ValueError(f"max_budget_usd must be positive, got {max_budget_usd}")
        self._max_budget_usd = max_budget_usd
        self._query_fn: QueryFn = query_fn if query_fn is not None else query

    async def chat(self, prompt: str) -> AsyncIterator[Any]:
        """Drive Claude with the configured MCP servers; yield each SDK message.

        The caller owns the loop — Console's session task consumes this
        async-iterator and translates each message into trace + SSE events.
        Yielding instead of returning keeps the streaming-UX latency low:
        the first text chunk hits the browser before Claude has finished
        thinking.
        """
        allowed_tools = [f"mcp__{name}" for name in self._mcp_servers] + [
            f"mcp__{name}__*" for name in self._mcp_servers
        ]

        options = ClaudeAgentOptions(
            model=self._model,
            mcp_servers=self._mcp_servers,
            system_prompt=self._system_prompt,
            max_turns=self._max_turns,
            allowed_tools=allowed_tools,
            permission_mode="bypassPermissions",
            max_budget_usd=self._max_budget_usd,
        )

        async for msg in self._query_fn(prompt=prompt, options=options):
            yield msg


def _sse_config(url: str, secret: str) -> McpSSEServerConfig:
    """Build an SSE MCP server config with bearer auth.

    Mirror of the helper in ``eval/src/noesis_eval/ab/mcp_agent.py``;
    duplicated here rather than imported because eval is a peer
    package, not a dependency, and we don't want to drag the harness
    into the Console install.
    """
    config: dict[str, Any] = {"type": "sse", "url": f"{url}/sse"}
    if secret:
        config["headers"] = {"Authorization": f"Bearer {secret}"}
    return cast(McpSSEServerConfig, config)


# Phase-1 surface: every Noesis service Console knows about. Each
# entry becomes an SSE-MCP wiring iff its NOESIS_<NAME>_URL env var
# is set; unset URLs are silently skipped so a partial deploy still
# yields a working Console (just with fewer tools).
NOESIS_SERVICE_NAMES: tuple[str, ...] = (
    "logos",
    "mneme",
    "praxis",
    "telos",
    "episteme",
    "kosmos",
    "empiria",
    "techne",
)


def noesis_mcp_servers_from_env(
    names: Sequence[str] = NOESIS_SERVICE_NAMES,
    *,
    env: dict[str, str] | None = None,
) -> dict[str, McpServerConfig]:
    """Build SSE configs for each reachable Noesis service.

    Reads ``NOESIS_<SERVICE>_URL`` / ``NOESIS_<SERVICE>_SECRET``. The
    explicit ``env`` arg lets tests pass a synthetic environment
    instead of monkey-patching ``os.environ``.
    """
    import os

    env_map = env if env is not None else dict(os.environ)
    servers: dict[str, McpServerConfig] = {}
    for name in names:
        url = env_map.get(f"NOESIS_{name.upper()}_URL")
        if not url:
            continue
        secret = env_map.get(f"NOESIS_{name.upper()}_SECRET", "")
        servers[name] = _sse_config(url, secret)
    return servers
