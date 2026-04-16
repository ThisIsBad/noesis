from praxis.core import PraxisCore
from noesis_schemas import StepStatus


def test_decompose_and_add_steps():
    core = PraxisCore()
    plan = core.decompose("Deploy service")
    core.add_step(plan.plan_id, "Build image", tool_call="docker_build")
    core.add_step(plan.plan_id, "Push to registry", tool_call="docker_push")
    retrieved = core.get_plan(plan.plan_id)
    assert len(retrieved.steps) == 2


def test_commit_step_success():
    core = PraxisCore()
    plan = core.decompose("Write tests")
    step = core.add_step(plan.plan_id, "Run pytest")
    updated = core.commit_step(plan.plan_id, step.step_id, outcome="All passed", success=True)
    assert updated.status == StepStatus.COMPLETED


def test_backtrack_resets_failed_steps():
    core = PraxisCore()
    plan = core.decompose("Fix bug")
    step = core.add_step(plan.plan_id, "Apply patch")
    core.commit_step(plan.plan_id, step.step_id, outcome="Conflict", success=False)
    reset = core.backtrack(plan.plan_id)
    assert len(reset) == 1
    assert reset[0].status == StepStatus.PENDING


def test_nested_plan_depth():
    core = PraxisCore()
    parent = core.decompose("Top-level goal")
    child = core.decompose("Sub-goal", depth=1, parent_plan_id=parent.plan_id)
    assert child.depth == 1
    assert child.parent_plan_id == parent.plan_id
