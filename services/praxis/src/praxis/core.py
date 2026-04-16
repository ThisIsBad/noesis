from typing import Optional
from noesis_schemas import Plan, PlanStep, StepStatus


class PraxisCore:
    def __init__(self) -> None:
        # Production: persist to SQLite; use NetworkX for graph search
        self._plans: dict[str, Plan] = {}

    def decompose(self, goal: str, depth: int = 0, parent_plan_id: Optional[str] = None) -> Plan:
        plan = Plan(goal=goal, depth=depth, parent_plan_id=parent_plan_id)
        self._plans[plan.plan_id] = plan
        return plan

    def add_step(self, plan_id: str, description: str, tool_call: Optional[str] = None, risk_score: float = 0.0) -> PlanStep:
        plan = self._plans[plan_id]
        step = PlanStep(description=description, tool_call=tool_call, risk_score=risk_score)
        plan.steps.append(step)
        return step

    def commit_step(self, plan_id: str, step_id: str, outcome: str, success: bool) -> PlanStep:
        plan = self._plans[plan_id]
        for step in plan.steps:
            if step.step_id == step_id:
                step.status = StepStatus.COMPLETED if success else StepStatus.FAILED
                step.outcome = outcome
                return step
        raise KeyError(step_id)

    def backtrack(self, plan_id: str) -> list[PlanStep]:
        plan = self._plans[plan_id]
        failed = [s for s in plan.steps if s.status == StepStatus.FAILED]
        for step in failed:
            step.status = StepStatus.PENDING
            step.outcome = None
        return failed

    def get_plan(self, plan_id: str) -> Plan:
        return self._plans[plan_id]
