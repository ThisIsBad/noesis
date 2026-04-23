# Orchestration guide — calling the Noesis services

> **Audience: whoever is orchestrating the Noesis services.** In
> practice that's Claude, talking to the MCP tools each service
> exposes. This document is terse on purpose — "what to call when",
> not another architecture essay.
>
> **You are the orchestrator.** Noesis is a coordinated set of
> MCP services that together close the cognitive gaps between LLM-only
> agents and AGI. Each service owns one gap. You do not have direct
> service-to-service calls (with one documented exception). You are
> the glue.
>
> Read [`docs/architecture.md`](docs/architecture.md) for the full
> architecture and [`docs/architect-review-2026-04-23.md`](docs/architect-review-2026-04-23.md)
> for the current status. This file is the terse "what to call when".

## Non-negotiable rules

1. **State mutations go through you.** No service directly mutates
   another service's state. If Mneme needs a belief certified, you
   call Logos, get a `ProofCertificate`, then pass it to Mneme.
2. **One exception — Logos as read-only sidecar.** Services may call
   Logos directly for idempotent verification only:
   `certify_claim`, `z3_check`, `check_policy`, `verify_argument`,
   `check_assumptions`, `check_beliefs`, `check_contract`. Any
   state-mutating Logos call (`assume`, `register_goal`, persisted
   `counterfactual_branch`) still goes through you.
3. **Kairos traces everything.** Every cross-service call propagates
   a `trace_id` and emits a span. Do not suppress tracing.
4. **Preflight gates must stay green.** Before shipping a change to
   any service: `pytest`, `ruff`, `mypy --strict`, `coverage ≥ 85 %`.
5. **Prefer existing tools over new ones.** If a capability exists in
   Logos / Mneme / Praxis / ..., use it. Only add a new MCP tool when
   the gap is real.

## Service directory

| Service | Gap it closes | MCP tools |
|---------|--------------|-----------|
| **Logos** ✅ | Verification — plausible ≠ correct | `verify_argument`, `certify_claim`, `certificate_store`, `check_assumptions`, `check_beliefs`, `check_contract`, `check_policy`, `counterfactual_branch`, `z3_check`, `z3_session`, `orchestrate_proof`, `proof_carrying_action` |
| **Mneme** ✅ | Persistent memory — context windows are ephemeral | `store_memory`, `retrieve_memory`, `forget_memory`, `list_proven_beliefs`, `certify_memory`, `consolidate_memories` |
| **Praxis** 🟡 | Planning & search — autoregressive ≠ state-space | `decompose_goal`, `evaluate_step`, `commit_step`, `backtrack`, `verify_plan`, `get_next_step`, `best_path`, `get_plan` |
| **Telos** 🟡 | Goal governance — without explicit goals, drift | `register_goal`, `check_action_alignment`, `get_drift_score`, `list_active_goals` |
| **Episteme** 🟡 | Calibration — models don't know what they don't know | `log_prediction`, `log_outcome`, `get_calibration`, `should_escalate`, `get_competence_map` |
| **Kosmos** 🟡 | Causality — correlations ≠ causal structure | `add_causal_edge`, `compute_intervention`, `counterfactual`, `query_causes` |
| **Empiria** 🟡 | Active learning — no explore/exploit loop post-deploy | `record_experience`, `retrieve_lessons`, `successful_patterns` |
| **Techne** 🟡 | Skill accumulation — strategies aren't persistent | `store_skill`, `retrieve_skill`, `record_use` |

Cross-cutting:

| Component | Role |
|-----------|------|
| **schemas/** | Pydantic contracts — `ProofCertificate`, `GoalContract`, `Plan`, `Memory`, `TraceSpan`, etc. |
| **kairos/** | OpenTelemetry tracing — records every cross-service call |
| **clients/** | Shared HTTP clients (`LogosClient`) |
| **eval/** | A/B benchmark harness — do not hand-roll new benchmarks outside this |
| **ui/theoria/** | Decision-logic visualizer for humans — not an MCP tool |

## Canonical orchestration patterns

### Pattern 1: Belief storage with verification

```
claim comes in
  ↓
Logos.certify_claim  →  ProofCertificate
  ↓
Mneme.store_memory(content=claim, certificate=ProofCertificate)
     (memory gets proven=True because it carries a certificate)
```

### Pattern 2: Plan with goal-contract verification

```
user goal
  ↓
Telos.register_goal(description, preconditions, postconditions)
  ↓
Praxis.decompose_goal → Plan with steps
  ↓
Logos.check_contract(plan.contract)          ← sidecar, read-only
  ↓
(for each step)
  Telos.check_action_alignment(step.description)
    if drift: abort + escalate
  else: execute, Praxis.commit_step(outcome)
```

### Pattern 3: Predict → outcome → calibrate

```
Agent makes a prediction
  ↓
Episteme.log_prediction(claim, confidence, domain)
  ↓
(later, when the outcome is known)
  Episteme.log_outcome(prediction_id, correct)
  ↓
Periodically: Episteme.get_calibration(domain) → ECE report
  ↓
Use Episteme.should_escalate(confidence, risk) before any
destructive action.
```

### Pattern 4: Skill reuse

```
Before planning a new task:
  Techne.retrieve_skill(goal)  →  past strategy if one exists
  Empiria.successful_patterns → heuristics that worked before
  ↓
If a skill was used: Techne.record_use(skill_id, outcome)
```

## Error-handling norms

- **Deterministic failures (contract violation, blocked policy):**
  surface immediately to the user; do not retry. Example: Logos
  `check_policy` returns `BLOCK` → do not run the action.
- **Transient failures (network, 5xx):** exponential backoff with
  jitter, max 3 retries. Propagate the original Kairos trace_id on
  the retry so the chain stays linked.
- **Kairos down:** continue the primary call but log a warning.
  Observability is best-effort; it must never block the agent.
- **Logos `UNKNOWN` verdict:** treat as `REVIEW_REQUIRED`, not as
  success. A solver timeout is not a proof.
- **Calibration drift (Episteme reports rising ECE):** raise this to
  the user before taking high-risk actions.

## Auth

Every service may be protected by a bearer token (`LOGOS_SECRET`,
`MNEME_SECRET`, `THEORIA_SECRET`, etc.). Read the token from Railway
environment variables — never commit them. When calling a service
use `Authorization: Bearer <token>`; Kairos propagates trace IDs
independently and does not need the service secret.

## Development gates (per service, before merge)

```bash
cd services/<name>    # or ui/theoria, kairos, schemas, etc.
python -m pytest -q
python -m ruff check src/ tests/
python -m mypy --strict src/
python -m pytest --cov=src/<name> --cov-fail-under=85
```

All four must pass. No `--no-verify` commits. No amending pushed
commits. Create a new commit when a hook fails.

## Where to add new capabilities

- **New MCP tool** for an existing service → that service's
  `mcp_server_http.py` + `core.py` + tests.
- **New cognitive gap** → decide if it fits an existing service or
  needs a new one. Before creating a new service, ask: does this
  close a gap the current eight don't?
- **New benchmark** → `eval/src/noesis_eval/` (not a service).
- **New shared contract** → `schemas/src/noesis_schemas/`. Add a
  round-trip test in `schemas/tests/`.
- **New visualization** → `ui/theoria/`. Theoria is a reader, not a
  service — do not give it an MCP endpoint.

## Recent architecture review

See [`docs/architect-review-2026-04-23.md`](docs/architect-review-2026-04-23.md)
for the most recent end-to-end read of the repo, including the Tier
1 / 2 / 3 improvement checklist.
