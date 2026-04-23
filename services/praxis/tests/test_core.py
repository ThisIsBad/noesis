import pytest
from noesis_clients.testing import (
    FakeLogosClient,
    refuted_certificate,
    verified_certificate,
)
from noesis_schemas import StepStatus

from praxis.core import PraxisCore


@pytest.fixture
def core(tmp_path):
    return PraxisCore(db_path=str(tmp_path / "test.db"))


# ── Basic plan lifecycle ───────────────────────────────────────────────────────

def test_decompose_creates_plan(core):
    plan = core.decompose("Deploy service")
    assert plan.goal == "Deploy service"
    assert plan.depth == 0
    assert plan.parent_plan_id is None


def test_add_sequential_steps(core):
    plan = core.decompose("Write and test code")
    s1 = core.add_step(plan.plan_id, "Write code", tool_call="editor", risk_score=0.1)
    s2 = core.add_step(plan.plan_id, "Run tests", tool_call="pytest", risk_score=0.1,
                       parent_step_id=s1.step_id)
    retrieved = core.get_plan(plan.plan_id)
    # best_path returns s1 → s2
    assert [s.step_id for s in retrieved.steps] == [s1.step_id, s2.step_id]


def test_commit_step_completed(core):
    plan = core.decompose("Task")
    step = core.add_step(plan.plan_id, "Do thing")
    updated = core.commit_step(plan.plan_id, step.step_id, outcome="done", success=True)
    assert updated.status == StepStatus.COMPLETED
    assert updated.outcome == "done"


def test_commit_step_failed_penalises_score(core):
    plan = core.decompose("Task")
    step = core.add_step(plan.plan_id, "Risky action", risk_score=0.2)
    score_before = core._trees[plan.plan_id].nodes[step.step_id]["score"]
    core.commit_step(plan.plan_id, step.step_id, outcome="exploded", success=False)
    score_after = core._trees[plan.plan_id].nodes[step.step_id]["score"]
    assert score_after < score_before


def test_nested_plan_depth(core):
    parent = core.decompose("Top-level goal")
    child = core.decompose("Sub-goal", depth=1, parent_plan_id=parent.plan_id)
    assert child.depth == 1
    assert child.parent_plan_id == parent.plan_id


def test_add_step_unknown_parent_raises(core):
    plan = core.decompose("Task")
    with pytest.raises(KeyError):
        core.add_step(plan.plan_id, "Step", parent_step_id="nonexistent-id")


# ── Tree-of-Thoughts: branching & beam search ─────────────────────────────────

def test_best_path_picks_lower_risk(core):
    """Two alternative first steps; best_path should pick the lower-risk one."""
    plan = core.decompose("Solve problem")
    safe = core.add_step(
        plan.plan_id, "Safe approach", tool_call="tool_a", risk_score=0.1,
    )
    core.add_step(
        plan.plan_id, "Risky approach", tool_call="tool_b", risk_score=0.7,
    )
    paths = core.best_path(plan.plan_id, k=1)
    assert paths[0][0].step_id == safe.step_id


def test_best_path_traverses_chain(core):
    """Sequential chain A → B → C: best_path returns [A, B, C]."""
    plan = core.decompose("Chain")
    a = core.add_step(plan.plan_id, "A", risk_score=0.1)
    b = core.add_step(plan.plan_id, "B", risk_score=0.1, parent_step_id=a.step_id)
    c = core.add_step(plan.plan_id, "C", risk_score=0.1, parent_step_id=b.step_id)
    paths = core.best_path(plan.plan_id, k=1)
    assert [s.step_id for s in paths[0]] == [a.step_id, b.step_id, c.step_id]


def test_beam_search_returns_k_paths(core):
    """With two competing branches, beam_search(k=2) returns both."""
    plan = core.decompose("Choose strategy")
    core.add_step(plan.plan_id, "Strategy A", risk_score=0.2)
    core.add_step(plan.plan_id, "Strategy B", risk_score=0.3)
    paths = core.best_path(plan.plan_id, k=2)
    assert len(paths) == 2


def test_beam_score_ordering(core):
    """best_path(k=2) orders paths by score (best first)."""
    plan = core.decompose("Rank paths")
    core.add_step(plan.plan_id, "Worse", risk_score=0.9)
    core.add_step(plan.plan_id, "Better", risk_score=0.05)
    paths = core.best_path(plan.plan_id, k=2)
    # First path should have lower risk (higher score)
    assert paths[0][0].risk_score < paths[1][0].risk_score


# ── Backtracking ──────────────────────────────────────────────────────────────

def test_backtrack_returns_sibling(core):
    """Fail branch A; backtrack should return sibling B."""
    plan = core.decompose("Try alternatives")
    a = core.add_step(plan.plan_id, "Approach A")
    b = core.add_step(plan.plan_id, "Approach B")
    core.commit_step(plan.plan_id, a.step_id, outcome="failed", success=False)
    alternatives = core.backtrack(plan.plan_id)
    assert any(s.step_id == b.step_id for s in alternatives)


def test_backtrack_resets_failed_to_pending(core):
    """After backtrack, the failed step is PENDING again."""
    plan = core.decompose("Task")
    step = core.add_step(plan.plan_id, "Attempt")
    core.commit_step(plan.plan_id, step.step_id, outcome="error", success=False)
    core.backtrack(plan.plan_id)
    status = core._trees[plan.plan_id].nodes[step.step_id]["status"]
    assert status == StepStatus.PENDING


def test_backtrack_no_siblings_returns_empty(core):
    """Single step with no siblings → backtrack returns [] (no alternatives)."""
    plan = core.decompose("Task")
    step = core.add_step(plan.plan_id, "Only option")
    core.commit_step(plan.plan_id, step.step_id, outcome="failed", success=False)
    alternatives = core.backtrack(plan.plan_id)
    assert alternatives == []


# ── get_next_step ─────────────────────────────────────────────────────────────

def test_get_next_step_first_pending(core):
    plan = core.decompose("Sequential")
    s1 = core.add_step(plan.plan_id, "Step 1")
    core.add_step(plan.plan_id, "Step 2", parent_step_id=s1.step_id)
    nxt = core.get_next_step(plan.plan_id)
    assert nxt is not None
    assert nxt.step_id == s1.step_id


def test_get_next_step_skips_completed(core):
    plan = core.decompose("Sequential")
    s1 = core.add_step(plan.plan_id, "Step 1")
    s2 = core.add_step(plan.plan_id, "Step 2", parent_step_id=s1.step_id)
    core.commit_step(plan.plan_id, s1.step_id, "done", True)
    nxt = core.get_next_step(plan.plan_id)
    assert nxt is not None
    assert nxt.step_id == s2.step_id


def test_get_next_step_none_when_all_done(core):
    plan = core.decompose("Done")
    step = core.add_step(plan.plan_id, "Only step")
    core.commit_step(plan.plan_id, step.step_id, "done", True)
    assert core.get_next_step(plan.plan_id) is None


def test_get_next_step_empty_plan(core):
    plan = core.decompose("Empty")
    assert core.get_next_step(plan.plan_id) is None


# ── Plan verification ─────────────────────────────────────────────────────────

def test_verify_plan_passes(core):
    plan = core.decompose("Safe plan")
    core.add_step(plan.plan_id, "Safe step", risk_score=0.2)
    ok, msg = core.verify_plan(plan.plan_id)
    assert ok
    assert "safe" in msg.lower()


def test_verify_plan_rejects_high_risk(core):
    plan = core.decompose("Dangerous plan")
    core.add_step(plan.plan_id, "Drop production DB", risk_score=0.9)
    ok, msg = core.verify_plan(plan.plan_id)
    assert not ok
    assert "high-risk" in msg.lower()


def test_verify_plan_rejects_empty(core):
    plan = core.decompose("Empty plan")
    ok, _ = core.verify_plan(plan.plan_id)
    assert not ok


# ── Persistence ───────────────────────────────────────────────────────────────

def test_persistence_survives_restart(tmp_path):
    db = str(tmp_path / "praxis.db")
    c1 = PraxisCore(db_path=db)
    plan = c1.decompose("Persistent goal")
    step = c1.add_step(plan.plan_id, "Persistent step", risk_score=0.1)
    c1.commit_step(plan.plan_id, step.step_id, "done", True)

    c2 = PraxisCore(db_path=db)
    retrieved = c2.get_plan(plan.plan_id)
    assert retrieved.goal == "Persistent goal"
    assert retrieved.steps[0].status == StepStatus.COMPLETED


# ── Logos sidecar (verify_plan) ───────────────────────────────────────────────
#
# Stand-ins come from the shared ``noesis_clients.testing`` module so
# this file stays focused on Praxis-specific assertions and the fake's
# contract is validated in one place (clients/tests/test_testing_helpers.py).


def test_verify_plan_with_logos_pass(tmp_path):
    fake = FakeLogosClient(verified_certificate())
    core = PraxisCore(db_path=str(tmp_path / "logos.db"), logos_client=fake)
    plan = core.decompose("Migrate users")
    core.add_step(plan.plan_id, "dump data", risk_score=0.1)

    ok, msg = core.verify_plan(plan.plan_id)
    assert ok is True
    assert "verified by Logos" in msg
    # Sanity: the rendered claim was actually shipped to Logos.
    assert len(fake.calls) == 1
    assert "Migrate users" in fake.calls[0]
    assert "dump data" in fake.calls[0]


def test_verify_plan_with_logos_refutation_blocks(tmp_path):
    fake = FakeLogosClient(refuted_certificate())
    core = PraxisCore(db_path=str(tmp_path / "logos.db"), logos_client=fake)
    plan = core.decompose("Risky plan")
    core.add_step(plan.plan_id, "weird step", risk_score=0.1)

    ok, msg = core.verify_plan(plan.plan_id)
    assert ok is False
    assert "Logos refuted" in msg


def test_verify_plan_with_logos_unreachable_degrades_to_local(tmp_path):
    fake = FakeLogosClient(None, last_error="connection refused")
    core = PraxisCore(db_path=str(tmp_path / "logos.db"), logos_client=fake)
    plan = core.decompose("OK plan")
    core.add_step(plan.plan_id, "safe step", risk_score=0.2)

    ok, msg = core.verify_plan(plan.plan_id)
    # Sidecar outage must not break the primary call (architecture rule).
    assert ok is True
    assert "connection refused" in msg


def test_verify_plan_local_high_risk_skips_logos(tmp_path):
    """High-risk fast-fail must short-circuit before touching Logos."""
    fake = FakeLogosClient(verified_certificate())
    core = PraxisCore(db_path=str(tmp_path / "logos.db"), logos_client=fake)
    plan = core.decompose("Dangerous plan")
    core.add_step(plan.plan_id, "Drop production DB", risk_score=0.9)

    ok, msg = core.verify_plan(plan.plan_id)
    assert ok is False
    assert "high-risk" in msg.lower()
    assert fake.calls == []   # no Logos round-trip


def test_verify_plan_no_client_preserves_legacy_behavior(tmp_path):
    """Default constructor (no client) returns the original local verdict."""
    core = PraxisCore(db_path=str(tmp_path / "logos.db"))   # no client
    plan = core.decompose("Plain plan")
    core.add_step(plan.plan_id, "easy step", risk_score=0.1)

    ok, msg = core.verify_plan(plan.plan_id)
    assert ok is True
    assert msg == "Plan passes basic safety check"
