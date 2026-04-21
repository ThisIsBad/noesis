"""``Agent`` Protocol and reference implementations.

An ``Agent`` is a turn-by-turn policy: each step it sees the current
observation plus the full action/observation history so far, and picks
the next action as a string. This matches what Claude actually does
under a ReAct-style loop — no upfront plan, no oracle over the env.

The Protocol is intentionally tiny. Every reference agent below
implements it; a future Claude-via-Anthropic-API agent will too.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


@dataclass(frozen=True)
class ActionOutcome:
    """One (action, observation, reward) triple from an episode.

    Passed back to the agent on every ``act`` call so turn-by-turn
    agents can condition on their own trajectory — the same history a
    real ReAct loop would feed into a model prompt.
    """
    action: str
    observation: str
    reward: float
    info: dict[str, object]


class Agent(Protocol):
    """Policy signature: ``(observation, history) -> next_action``.

    Implementations must be stateless across episodes — per-task state
    belongs in the ``history`` parameter so the runner stays in control
    of resets. A stateful agent that leaks across tasks would make
    suite-level comparisons meaningless.
    """
    name: str

    def act(
        self, goal: str, observation: str, history: Sequence[ActionOutcome]
    ) -> str: ...


class NullAgent:
    """Fixed-action baseline. Establishes the env's failure floor.

    Always emits ``action``, regardless of observation or history. Used
    to pin that the env actually rejects nonsense (if NullAgent scored
    above zero the env contract would be broken) and to provide a
    floor reference point for ``SuiteResults.diff``.
    """
    name = "null"

    def __init__(self, action: str = "wait") -> None:
        self._action = action

    def act(
        self, goal: str, observation: str, history: Sequence[ActionOutcome]
    ) -> str:
        return self._action


class OracleAgent:
    """Returns the next canonical step. Establishes the ceiling.

    Given a ``{goal: canonical_plan}`` map (and optional recovery map
    keyed the same way), the oracle tracks how many canonical steps it
    has emitted for the current goal and returns the next one. After
    a ``failed`` step info, it switches into the recovery sequence for
    that goal, emits one recovery action, and resumes the canonical
    tail from the recovery index.

    Any Agent that scores meaningfully below the oracle on the same
    suite is losing capability somewhere — the env, the prompt, the
    tool surface, or the policy itself.
    """
    name = "oracle"

    def __init__(
        self,
        plans: dict[str, list[str]],
        recovery: dict[str, list[str]] | None = None,
    ) -> None:
        self._plans = plans
        self._recovery = recovery or {}

    def act(
        self, goal: str, observation: str, history: Sequence[ActionOutcome]
    ) -> str:
        plan = self._plans.get(goal, [])
        recovery = self._recovery.get(goal, [])

        # Replay the history to figure out where we are: count clean
        # canonical commits vs. failed commits that need replan.
        canonical_idx = 0
        recovered = False
        replan_active = False

        for h in history:
            if h.info.get("failed"):
                replan_active = True
                continue
            if h.info.get("recovered"):
                recovered = True
                replan_active = False
                canonical_idx += 1
                continue
            # Normal forward step.
            replan_active = False
            canonical_idx += 1

        if replan_active:
            # Emit the first recovery action; when it succeeds the env
            # marks ``recovered`` and we resume the canonical tail.
            if recovery:
                return recovery[0]
            return ""  # No recovery known: let the env fail the episode.

        if canonical_idx < len(plan):
            return plan[canonical_idx]

        # Plan exhausted — return empty to signal the runner to stop.
        # (In practice the env terminates before we reach this branch.)
        _ = recovered  # silence unused-var lints in edge cases
        return ""


class MCPAgent:
    """STUB — real implementation lands once ``claude-agent-sdk`` is wired up.

    The eventual contract: on each ``act`` call, run one turn of a
    Claude agent loop with a configurable set of MCP tool servers
    attached. The A/B experiment runs the *same* model in two
    configurations — one with every Noesis MCP server (Mneme, Telos,
    Praxis, Logos, Episteme, Empiria, Techne, Kosmos), one with none —
    and diffs the resulting ``SuiteResults``.

    Keeping the slot explicit (rather than deferring the whole class)
    lets the runner and suite-diff machinery be unit-tested against
    the Oracle / Null baselines in this PR, so when the real agent
    lands the only moving piece is the SDK wiring.
    """
    name = "mcp"

    def __init__(
        self,
        *,
        model: str = "claude-sonnet-4-6",
        mcp_servers: Sequence[str] = (),
    ) -> None:
        self._model = model
        self._mcp_servers = tuple(mcp_servers)

    def act(
        self, goal: str, observation: str, history: Sequence[ActionOutcome]
    ) -> str:
        raise NotImplementedError(
            "MCPAgent awaits a follow-up PR that pulls in claude-agent-sdk "
            "and wires the configured MCP servers into a real turn loop. "
            "The A/B harness itself — env, runner, suite-diff — is pinned "
            "by unit tests against the Oracle / Null baselines."
        )
