"""ALFWorld Planner adapter backed by a ``praxis.core.PraxisCore``.

The adapter uses PraxisCore as a plan-tree store: ``decompose`` creates a
plan, chains the canonical steps as a path, and seeds recovery
alternatives as siblings at the root with a higher risk score so the
first round of beam search picks the canonical chain. On ``replan`` it
commits the canonical first step as FAILED, calls ``backtrack`` to
surface pending siblings, and returns ``[alt, *canonical_tail]`` — the
same contract the ``ScriptedPlanner`` uses.

We keep the adapter deliberately thin: all acceptance-suite knowledge
(canonical plans + recovery hints) is handed in at construction time,
exactly as the scripted reference planner receives it. That makes the
metrics directly comparable — the only moving part is whether Praxis
can drive the same episodes to completion through its own tree + beam-
search pipeline.
"""
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from praxis.core import PraxisCore

# Risk scores: the canonical chain gets risk 0.0 (score 0.8), recovery
# siblings get risk 0.5 (score 0.5), so best_path surfaces the canonical
# chain first. After commit_step(..., success=False) the failed step's
# score is penalised by 0.3, making recovery the top candidate.
_CANONICAL_RISK = 0.0
_RECOVERY_RISK = 0.5


class PraxisCorePlanner:
    """Planner Protocol implementation driving a PraxisCore instance."""

    def __init__(
        self,
        core: "PraxisCore",
        plans: dict[str, list[str]],
        recovery: dict[str, list[str]] | None = None,
    ) -> None:
        self._core = core
        self._plans = plans
        self._recovery = recovery or {}
        self._plan_ids: dict[str, str] = {}
        self._first_step: dict[str, str] = {}

    def decompose(self, goal: str, observation: str) -> list[str]:
        steps = self._plans.get(goal, [])
        if not steps:
            return []

        plan = self._core.decompose(goal)
        self._plan_ids[goal] = plan.plan_id

        parent: str | None = None
        for i, desc in enumerate(steps):
            step = self._core.add_step(
                plan.plan_id,
                desc,
                risk_score=_CANONICAL_RISK,
                parent_step_id=parent,
            )
            if i == 0:
                self._first_step[goal] = step.step_id
            parent = step.step_id

        # Recovery steps live as leaf siblings at the root of the tree.
        # They only win in best_path after the canonical first step is
        # marked FAILED and its score drops.
        for alt in self._recovery.get(goal, []):
            self._core.add_step(
                plan.plan_id,
                alt,
                risk_score=_RECOVERY_RISK,
                parent_step_id=None,
            )

        paths = self._core.best_path(plan.plan_id, k=1)
        return [s.description for s in paths[0]] if paths else []

    def replan(self, goal: str, observation: str) -> list[str]:
        plan_id = self._plan_ids.get(goal)
        first = self._first_step.get(goal)
        if plan_id is None or first is None:
            return []

        self._core.commit_step(
            plan_id, first, outcome="injected step-failure", success=False
        )
        alternatives = self._core.backtrack(plan_id)
        if not alternatives:
            return []

        canonical_tail = self._plans.get(goal, [])[1:]
        return [alternatives[0].description, *canonical_tail]
