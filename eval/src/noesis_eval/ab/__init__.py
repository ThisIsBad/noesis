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

Three reference agents ship in this PR:

    * ``NullAgent`` — fixed benign action; establishes the failure floor
      and pins the env's step contract against agents that never learn.
    * ``OracleAgent`` — knows every task's canonical plan; establishes
      the ceiling you'd see from a perfect policy.
    * ``MCPAgent`` — stub awaiting ``claude-agent-sdk`` + API wiring.
      The actual experiment — Claude-with-Noesis vs. Claude-alone — is
      one follow-up PR away once that slot is filled.

Kept deliberately API-free so this PR is CI-runnable with no secrets.
The expensive piece (a real Anthropic API call per step × N tasks ×
two configurations) lands in the follow-up, behind an opt-in CLI.
"""
from .agent import ActionOutcome, Agent, MCPAgent, NullAgent, OracleAgent
from .results import EpisodeResult, SuiteDelta, SuiteResults
from .runner import run_ab, run_episode, run_suite

__all__ = [
    "ActionOutcome",
    "Agent",
    "EpisodeResult",
    "MCPAgent",
    "NullAgent",
    "OracleAgent",
    "SuiteDelta",
    "SuiteResults",
    "run_ab",
    "run_episode",
    "run_suite",
]
