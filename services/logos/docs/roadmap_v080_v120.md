# Roadmap v0.8 -> v1.2: Toward AGI-Grade Reasoning Infrastructure

## Purpose

After v0.3-v0.7, LogicBrain should evolve from "verified claims" to
"verified decision loops" for long-horizon autonomous agents.

This roadmap focuses on five capabilities needed for AGI-adjacent toolchains:

1. explicit epistemic state (facts vs assumptions vs hypotheses)
2. counterfactual planning before actions
3. hard policy enforcement before execution
4. calibrated uncertainty handling
5. compositional proof exchange across agents/services

---

## v0.8 - Assumption & World-State Kernel

**Theme:** Agent reasoning must carry explicit, typed assumptions.

### Problem

Agents mix facts, inferred statements, and temporary hypotheses. Without explicit
typing and lifecycle rules, contradictions and stale assumptions accumulate.

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| `AssumptionSet` with typed entries (`fact`, `assumption`, `hypothesis`) | Natural-language extraction of assumptions |
| provenance metadata (`source`, `timestamp`, `scope`) | Persistent distributed storage |
| assumption lifecycle (`activate`, `expire`, `retract`) | probabilistic belief fusion |
| consistency checks integrated with v0.5 `BeliefSet` | UI dashboards |

### Deliverables

- `logic_brain/assumptions.py` with typed assumption state model
- serialization format for assumption snapshots
- integration test with `BeliefSet` contradiction detection
- metamorphic tests (reordering assumptions does not alter consistency)

### KPI

- lower contradiction incidence in long sessions

---

## v0.9 - Counterfactual Planner

**Theme:** Simulate alternative action branches before committing edits/actions.

### Problem

Current agent workflows are mostly single-path. Failed paths are discovered only
after expensive execution.

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| branchable planning API over Z3 push/pop semantics | full autonomous planner/optimizer |
| branch scoring hooks (validity, policy violations, uncertainty) | RL training infrastructure |
| branch certificates linked to v0.3 `ProofCertificate` | latency optimization for massive trees |
| replayable plan traces | visual tree explorer |

### Deliverables

- `logic_brain/counterfactual.py` (`PlanState`, `PlanBranch`, `PlanResult`)
- deterministic branch replay interface
- tests for branch independence and rollback soundness
- examples for multi-branch decision support

### KPI

- reduced failed execution attempts per task

---

## v1.0 - Verified Action Policies

**Theme:** Convert governance and engineering standards into hard pre-action checks.

### Problem

Policy violations are often caught post-hoc in CI or code review.

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| policy schema for action-level constraints | organization-specific policy hosting |
| enforcement API (`allow`, `block`, `review_required`) | dynamic policy learning |
| integration with v0.6 policy engine and v0.9 planning | runtime production deployment blockers |
| structured violation evidence for agent self-correction | billing/compliance automation |

### Deliverables

- `logic_brain/action_policy.py` with enforcement primitives
- violation explanations + remediation hints
- metamorphic tests (removing policies cannot add violations)
- compatibility layer for existing policy definitions

### KPI

- fewer policy-related CI failures and fewer rejected PRs

---

## v1.1 - Uncertainty Calibration Layer

**Theme:** Force explicit uncertainty and escalation behavior.

### Problem

Agents can produce overconfident outputs where evidence is weak or ambiguous.

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| uncertainty model (`certain`, `supported`, `weak`, `unknown`) | probabilistic theorem proving |
| mandatory escalation hooks for low-confidence outputs | custom LLM fine-tuning |
| confidence provenance linked to certificates/contracts | UX-driven confidence visualizations |
| deterministic checks for escalation policy compliance | human labeling systems |

### Deliverables

- `logic_brain/uncertainty.py` with typed confidence states
- policy hook: block high-risk actions under weak evidence
- tests for calibration and escalation invariants
- docs: confidence protocol for downstream agents

### KPI

- lower false-positive correctness claims

---

## v1.2 - Composed Proof Exchange

**Theme:** Multi-agent and multi-service zero-trust proof interoperability.

### Problem

Independent agents/services cannot reliably exchange verifiable reasoning artifacts
without format and trust contracts.

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| transport-safe certificate bundles with dependency graph | cryptographic PKI rollout |
| proof composition + partial verification status | external orchestration platform |
| compatibility checks across schema versions | enterprise identity/access integration |
| handoff protocol for CI/agent/tool boundaries | full distributed consensus system |

### Deliverables

- `logic_brain/proof_exchange.py` with bundle schema
- verifier for partial/complete exchange bundles
- cross-process integration tests (producer/consumer)
- migration guide for schema upgrades

### KPI

- higher proof reuse rate across tools and lower duplicate verification cost

---

## Cross-Cutting Rules

- strict issue-first execution; one issue in progress at a time
- one primary issue per implementation commit
- full preflight gates before every implementation commit
- schema versioning from day one for new interchange formats
- metamorphic tests mandatory for each module-level invariant

## Suggested Execution Order

1. v0.8 (state hygiene baseline)
2. v0.9 (branch-aware planning)
3. v1.0 (hard policy gates)
4. v1.1 (uncertainty safety)
5. v1.2 (multi-agent interoperability)
