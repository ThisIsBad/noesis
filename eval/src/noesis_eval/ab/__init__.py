"""A/B harness: does Noesis actually help an agent solve tasks?

The existing ``alfworld_bench`` scaffold measures whether a ``Planner``
(ScriptedPlanner, PraxisCorePlanner) can *execute* a plan it's handed.
It's a regression gate on the plan-tree machinery, not an answer to the
question the ROADMAP is built around: does Claude solve more tasks when
the Noesis services are available than when they aren't?

This package closes that gap. An ``Agent`` is anything that, given an
observation and the action/outcome history so far, chooses the next
action — the real ReAct-style loop Claude actually runs. The harness
drives the same ``MockAlfworldEnv`` suite against two ``Agent``
implementations and diffs their ``SuiteResults``.

Four reference agents ship:

    * ``NullAgent`` — fixed benign action; establishes the failure floor
      and pins the env's step contract against agents that never learn.
    * ``OracleAgent`` — knows every task's canonical plan; establishes
      the ceiling you'd see from a perfect policy.
    * ``MCPAgent`` — turn-by-turn Claude agent via ``claude-agent-sdk``
      with a pluggable set of MCP tool servers. The same ``MCPAgent``
      class powers both treatment (Noesis servers wired in) and
      baseline (no Noesis servers) so the only variable in the A/B is
      the MCP surface.
"""
from .agent import (
    ActionOutcome,
    Agent,
    AgentTelemetry,
    NullAgent,
    OracleAgent,
)
from .mcp_agent import (
    MCPAgent,
    build_baseline_agent,
    build_treatment_agent,
    noesis_mcp_servers_from_env,
)
from .results import EpisodeResult, SuiteDelta, SuiteResults
from .runner import run_ab, run_episode, run_suite

__all__ = [
    "ActionOutcome",
    "Agent",
    "AgentTelemetry",
    "EpisodeResult",
    "MCPAgent",
    "NullAgent",
    "OracleAgent",
    "SuiteDelta",
    "SuiteResults",
    "build_baseline_agent",
    "build_treatment_agent",
    "noesis_mcp_servers_from_env",
    "run_ab",
    "run_episode",
    "run_suite",
]
