"""Built-in sample decision traces.

These showcase the four decision shapes that appear most often in the
Noesis ecosystem. They are intentionally small, self-contained, and
handcrafted so the UI has something meaningful to render on first load.
"""

from __future__ import annotations

from theoria.models import (
    DecisionTrace,
    Edge,
    EdgeRelation,
    Outcome,
    ReasoningStep,
    StepKind,
    StepStatus,
)


def build_samples() -> list[DecisionTrace]:
    return [
        _logos_policy_sample(),
        _praxis_plan_sample(),
        _z3_proof_sample(),
        _telos_drift_sample(),
    ]


# ---------------------------------------------------------------------------
# Sample 1 — Logos pre-action policy decision
# ---------------------------------------------------------------------------

def _logos_policy_sample() -> DecisionTrace:
    steps = [
        ReasoningStep(
            id="q",
            kind=StepKind.QUESTION,
            label="May the agent run `rm -rf /data/user-uploads`?",
            detail="Pre-action check against the deterministic policy set.",
            source_ref="services/logos/src/logos/action_policy.py:145",
        ),
        ReasoningStep(
            id="fact.destructive",
            kind=StepKind.OBSERVATION,
            label="action.destructive = true",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="fact.irreversible",
            kind=StepKind.OBSERVATION,
            label="action.irreversible = true",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="fact.authorized",
            kind=StepKind.OBSERVATION,
            label="action.authorized_by_user = false",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="rule.no_unauth_destroy",
            kind=StepKind.RULE_CHECK,
            label="Rule: no_unauthorized_destruction",
            detail="when_true = [destructive, irreversible]; when_false = [authorized_by_user]; severity=error",
            status=StepStatus.TRIGGERED,
            source_ref="services/logos/src/logos/action_policy.py:57",
        ),
        ReasoningStep(
            id="rule.prefer_dry_run",
            kind=StepKind.RULE_CHECK,
            label="Rule: prefer_dry_run_first",
            detail="when_true = [destructive]; when_false = [is_dry_run]; severity=warning",
            status=StepStatus.TRIGGERED,
        ),
        ReasoningStep(
            id="z3.consistency",
            kind=StepKind.CONSTRAINT,
            label="Z3: policy set is internally consistent",
            detail="No pair of rules is jointly UNSAT under the action constraints.",
            status=StepStatus.OK,
            confidence=1.0,
        ),
        ReasoningStep(
            id="conclusion.block",
            kind=StepKind.CONCLUSION,
            label="Decision: BLOCK",
            detail="At least one error-severity rule triggered → PolicyDecision.BLOCK",
            status=StepStatus.FAILED,
            confidence=1.0,
        ),
    ]
    edges = [
        Edge("q", "fact.destructive", EdgeRelation.CONSIDERS),
        Edge("q", "fact.irreversible", EdgeRelation.CONSIDERS),
        Edge("q", "fact.authorized", EdgeRelation.CONSIDERS),
        Edge("fact.destructive", "rule.no_unauth_destroy", EdgeRelation.SUPPORTS, "when_true"),
        Edge("fact.irreversible", "rule.no_unauth_destroy", EdgeRelation.SUPPORTS, "when_true"),
        Edge("fact.authorized", "rule.no_unauth_destroy", EdgeRelation.SUPPORTS, "when_false"),
        Edge("fact.destructive", "rule.prefer_dry_run", EdgeRelation.SUPPORTS, "when_true"),
        Edge("q", "z3.consistency", EdgeRelation.REQUIRES),
        Edge("rule.no_unauth_destroy", "conclusion.block", EdgeRelation.IMPLIES, "severity=error"),
        Edge("rule.prefer_dry_run", "conclusion.block", EdgeRelation.SUPPORTS, "severity=warning"),
        Edge("z3.consistency", "conclusion.block", EdgeRelation.SUPPORTS),
    ]
    return DecisionTrace(
        id="sample-logos-policy-block",
        title="Logos blocks an unauthorized destructive action",
        question="Is this action allowed under the current policy set?",
        source="logos",
        kind="policy",
        root="q",
        steps=steps,
        edges=edges,
        outcome=Outcome(
            verdict="block",
            summary="Unauthorized, irreversible destructive action — blocked by policy",
            confidence=1.0,
            meta={"policy_decision": "BLOCK", "triggered": 2},
        ),
        tags=["logos", "policy", "block"],
    )


# ---------------------------------------------------------------------------
# Sample 2 — Praxis hierarchical planning with beam-search pruning
# ---------------------------------------------------------------------------

def _praxis_plan_sample() -> DecisionTrace:
    steps = [
        ReasoningStep(
            id="q",
            kind=StepKind.QUESTION,
            label="Plan: migrate users table to new schema",
            detail="Tree-of-Thoughts expansion, beam width = 2.",
            source_ref="services/praxis/src/praxis/core.py",
        ),
        ReasoningStep(
            id="sub.dump",
            kind=StepKind.INFERENCE,
            label="Subgoal: dump current data",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="sub.migrate",
            kind=StepKind.INFERENCE,
            label="Subgoal: migrate schema",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="sub.verify",
            kind=StepKind.INFERENCE,
            label="Subgoal: verify row counts",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="alt.online",
            kind=StepKind.ALTERNATIVE,
            label="Branch A: zero-downtime dual-write",
            detail="score = 0.81; risk = medium",
            status=StepStatus.OK,
            confidence=0.81,
        ),
        ReasoningStep(
            id="alt.maintenance",
            kind=StepKind.ALTERNATIVE,
            label="Branch B: 10-min maintenance window",
            detail="score = 0.63; risk = low",
            status=StepStatus.OK,
            confidence=0.63,
        ),
        ReasoningStep(
            id="alt.drop_recreate",
            kind=StepKind.ALTERNATIVE,
            label="Branch C: drop + recreate",
            detail="Pruned: irreversible; fails goal-contract postcondition `no_data_loss`.",
            status=StepStatus.REJECTED,
            confidence=0.08,
        ),
        ReasoningStep(
            id="evidence.dual_write_cost",
            kind=StepKind.EVIDENCE,
            label="Dual-write cost estimate: 2 engineer-days",
            status=StepStatus.INFO,
        ),
        ReasoningStep(
            id="evidence.window_cost",
            kind=StepKind.EVIDENCE,
            label="Maintenance-window cost estimate: 30 user-minutes downtime",
            status=StepStatus.INFO,
        ),
        ReasoningStep(
            id="conclusion",
            kind=StepKind.CONCLUSION,
            label="Selected plan: Branch A (dual-write)",
            detail="Top beam-search score, risk within tolerance.",
            status=StepStatus.OK,
            confidence=0.81,
        ),
    ]
    edges = [
        Edge("q", "sub.dump", EdgeRelation.REQUIRES),
        Edge("q", "sub.migrate", EdgeRelation.REQUIRES),
        Edge("q", "sub.verify", EdgeRelation.REQUIRES),
        Edge("sub.migrate", "alt.online", EdgeRelation.CONSIDERS),
        Edge("sub.migrate", "alt.maintenance", EdgeRelation.CONSIDERS),
        Edge("sub.migrate", "alt.drop_recreate", EdgeRelation.CONSIDERS),
        Edge("evidence.dual_write_cost", "alt.online", EdgeRelation.SUPPORTS),
        Edge("evidence.window_cost", "alt.maintenance", EdgeRelation.SUPPORTS),
        Edge("alt.drop_recreate", "conclusion", EdgeRelation.PRUNES, "fails postcondition"),
        Edge("alt.online", "conclusion", EdgeRelation.YIELDS, "selected"),
        Edge("alt.maintenance", "conclusion", EdgeRelation.CONSIDERS, "runner-up"),
    ]
    return DecisionTrace(
        id="sample-praxis-plan",
        title="Praxis selects a dual-write migration plan",
        question="What is the safest plan to migrate the users table?",
        source="praxis",
        kind="plan",
        root="q",
        steps=steps,
        edges=edges,
        outcome=Outcome(
            verdict="plan-selected",
            summary="Dual-write branch chosen; drop+recreate pruned by goal-contract.",
            confidence=0.81,
            meta={"beam_width": 2, "branches": 3, "pruned": 1},
        ),
        tags=["praxis", "plan", "beam-search"],
    )


# ---------------------------------------------------------------------------
# Sample 3 — Z3 constraint proof
# ---------------------------------------------------------------------------

def _z3_proof_sample() -> DecisionTrace:
    steps = [
        ReasoningStep(
            id="q",
            kind=StepKind.QUESTION,
            label="Prove: `x > 0 ∧ y > 0` implies `x + y > 0`",
            source_ref="services/logos/src/logos/z3_session.py",
        ),
        ReasoningStep(
            id="decl",
            kind=StepKind.PREMISE,
            label="Declare: x : Int, y : Int",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="assert.x",
            kind=StepKind.CONSTRAINT,
            label="Assert: x > 0",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="assert.y",
            kind=StepKind.CONSTRAINT,
            label="Assert: y > 0",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="assert.negconcl",
            kind=StepKind.CONSTRAINT,
            label="Assert (negated goal): not (x + y > 0)",
            detail="We prove by refutation: UNSAT on the negated goal ≡ theorem holds.",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="z3.check",
            kind=StepKind.INFERENCE,
            label="Z3 check() → UNSAT",
            status=StepStatus.OK,
            confidence=1.0,
        ),
        ReasoningStep(
            id="conclusion",
            kind=StepKind.CONCLUSION,
            label="Theorem holds",
            detail="Negated goal is unsatisfiable under the premises ⇒ proof by refutation.",
            status=StepStatus.OK,
            confidence=1.0,
        ),
    ]
    edges = [
        Edge("q", "decl", EdgeRelation.REQUIRES),
        Edge("decl", "assert.x", EdgeRelation.SUPPORTS),
        Edge("decl", "assert.y", EdgeRelation.SUPPORTS),
        Edge("q", "assert.negconcl", EdgeRelation.CONSIDERS, "negated goal"),
        Edge("assert.x", "z3.check", EdgeRelation.SUPPORTS),
        Edge("assert.y", "z3.check", EdgeRelation.SUPPORTS),
        Edge("assert.negconcl", "z3.check", EdgeRelation.SUPPORTS),
        Edge("z3.check", "conclusion", EdgeRelation.IMPLIES),
    ]
    return DecisionTrace(
        id="sample-z3-proof",
        title="Z3 proves `x>0 ∧ y>0 ⇒ x+y>0`",
        question="Is the implication valid over integers?",
        source="logos",
        kind="proof",
        root="q",
        steps=steps,
        edges=edges,
        outcome=Outcome(
            verdict="proved",
            summary="Refutation on negated goal returned UNSAT — theorem holds.",
            confidence=1.0,
            meta={"solver": "z3", "status": "unsat"},
        ),
        tags=["logos", "z3", "proof"],
    )


# ---------------------------------------------------------------------------
# Sample 4 — Telos goal-drift detection
# ---------------------------------------------------------------------------

def _telos_drift_sample() -> DecisionTrace:
    steps = [
        ReasoningStep(
            id="q",
            kind=StepKind.QUESTION,
            label="Is the agent still pursuing the original goal?",
            detail="Goal contract: 'Refactor auth module, preserve public API'",
            source_ref="services/telos/src/telos/core.py",
        ),
        ReasoningStep(
            id="goal.anchor",
            kind=StepKind.PREMISE,
            label="Anchor embedding: goal statement",
            status=StepStatus.OK,
        ),
        ReasoningStep(
            id="step.recent.rename",
            kind=StepKind.OBSERVATION,
            label="Recent action: renamed public `authenticate()` → `do_auth()`",
            status=StepStatus.INFO,
        ),
        ReasoningStep(
            id="step.recent.chromadb",
            kind=StepKind.OBSERVATION,
            label="Recent action: added ChromaDB dependency",
            detail="Unrelated to the auth refactor goal.",
            status=StepStatus.INFO,
        ),
        ReasoningStep(
            id="similarity",
            kind=StepKind.INFERENCE,
            label="Cosine similarity vs goal anchor",
            detail="rename: 0.72 (on-goal); chromadb: 0.21 (off-goal)",
            status=StepStatus.INFO,
            confidence=0.83,
        ),
        ReasoningStep(
            id="post.preserve_api",
            kind=StepKind.CONSTRAINT,
            label="Forbidding postcondition: public API signature preserved",
            status=StepStatus.FAILED,
            detail="Rename changes the public API — postcondition violated.",
        ),
        ReasoningStep(
            id="drift",
            kind=StepKind.INFERENCE,
            label="Drift score: 0.58 (threshold 0.40)",
            status=StepStatus.TRIGGERED,
            confidence=0.58,
        ),
        ReasoningStep(
            id="conclusion",
            kind=StepKind.CONCLUSION,
            label="Drift detected — escalate to operator",
            status=StepStatus.FAILED,
            confidence=0.58,
        ),
    ]
    edges = [
        Edge("q", "goal.anchor", EdgeRelation.REQUIRES),
        Edge("goal.anchor", "similarity", EdgeRelation.SUPPORTS),
        Edge("step.recent.rename", "similarity", EdgeRelation.SUPPORTS),
        Edge("step.recent.chromadb", "similarity", EdgeRelation.SUPPORTS),
        Edge("step.recent.rename", "post.preserve_api", EdgeRelation.CONTRADICTS),
        Edge("similarity", "drift", EdgeRelation.IMPLIES),
        Edge("post.preserve_api", "drift", EdgeRelation.SUPPORTS),
        Edge("drift", "conclusion", EdgeRelation.YIELDS),
    ]
    return DecisionTrace(
        id="sample-telos-drift",
        title="Telos detects goal drift during an auth refactor",
        question="Is the agent still aligned with its declared goal?",
        source="telos",
        kind="goal",
        root="q",
        steps=steps,
        edges=edges,
        outcome=Outcome(
            verdict="drift",
            summary="Public-API-preservation postcondition violated and drift score exceeds threshold.",
            confidence=0.58,
            meta={"threshold": 0.40, "drift_score": 0.58},
        ),
        tags=["telos", "goal", "drift"],
    )
