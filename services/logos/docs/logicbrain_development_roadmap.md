# LogicBrain Development Roadmap

**Anchored to:** [agi_roadmap_v2.md](file:///d:/AgenticAI/LogicBrain/docs/agi_roadmap_v2.md)
**Date:** 2026-03-29 · **Status:** Living document

---

## Purpose

This document is the **single actionable roadmap** for LogicBrain development.
It maps every LogicBrain milestone to the 5-stage AGI architecture defined in
`agi_roadmap_v2.md`, making visible *why* each module exists and *which AGI
capability* it enables.

### Guiding Principle

> LogicBrain is the **Verifier module** of a cognitive architecture.
> Its job is to provide formal guarantees — soundness, consistency,
> policy compliance, and proof certificates — that no LLM can provide
> alone. Every version must strengthen this role.

---

## Architecture Mapping

```
AGI Stage           LogicBrain Role              Versions
─────────────────────────────────────────────────────────────
Stage 1: Language   (not applicable)             —
Stage 2: Tool       MCP tool endpoints           v0.2.0 ✅
Stage 3: Reflective Verification + Contracts     v0.3–v0.7
Stage 4: Learning   Verified Memory + Exchange   v0.8–v1.2
Stage 5: Cognitive  Integration Kernel contrib.   v1.5+
```

---

## Current State (v0.7-era repository) — Stage 2 complete, Stage 3 substantially implemented

LogicBrain is a working MCP tool surface with most Stage 3 reflective primitives already present in the repository.

| Capability | Module | Status |
|------------|--------|--------|
| Propositional logic verification | `PropositionalVerifier` | ✅ Stable |
| First-order logic verification | `PredicateVerifier` | ✅ Stable |
| Incremental Z3 sessions | `Z3Session` | ✅ Stable |
| Lean 4 theorem proving | `LeanSession` | ✅ Stable |
| MCP server (12 tools) | `mcp_server.py`, `mcp_tools.py` | ✅ Stable |
| API stability contract | `STABILITY.md` | ✅ Published |
| Structured diagnostics | `Diagnostic` | ✅ Stable |

**What Stage 2 enables:** An agent can call LogicBrain as a tool to
verify claims, check satisfiability, manage Z3 state, and inspect policy
or contract conditions.

**What is now also true:** The repository already contains several Stage 3
building blocks, including contracts, belief checks, uncertainty hooks,
proof orchestration, and a proof-carrying action bus. The remaining gap is less "missing modules" and
more "closing the loop with agent workflows, validation, and issue hygiene".

---

## Stage 3: Reflective Agent (v0.3 – v0.7)

> **Goal:** Transform LogicBrain from reactive verifier to proactive
> reasoning infrastructure — tools the agent uses *during* thinking.

### Version Overview

| Version | Module | AGI Capability | Status |
|---------|--------|----------------|--------|
| **v0.3** | `ProofCertificate` | Verified outputs — prove you're not hallucinating | ✅ Implemented |
| **v0.4** | `GoalContract` | Reasoning contracts — pre/postconditions on steps | ✅ Implemented |
| **v0.5** | `BeliefGraph` | Self-consistency — detect contradictions in beliefs | ✅ Implemented |
| **v0.6** | `ActionPolicyEngine` | Policy enforcement — prune actions before execution | ✅ Implemented |
| **v0.7** | Proof Orchestrator | Compositional proofs — decompose and compose claims | ✅ Implemented |

### What's Done

The core Stage 3 modules exist and are tested:

- **`certificate.py`** — `ProofCertificate` with JSON serialization, `certify()`, `verify_certificate()`
- **`goal_contract.py`** — Machine-checkable pre/postconditions for reasoning steps
- **`belief_graph.py`** — Contradiction detection with Z3-backed consistency checks
- **`action_policy.py`** — Boolean policy engine with Z3 consistency and subsumption
- **`orchestrator.py`** — `ProofOrchestrator` for claim decomposition, propagation, and composed certificates
- **`execution_bus.py`** — `ActionEnvelope` and `execute_action_envelope()` for certified preconditions, validated postconditions, traces, and proof-bundle compatibility
- **`mcp_tools.py` / `mcp_server.py`** — MCP exposure for `certify_claim`, `check_beliefs`, `check_contract`, `z3_session`, and `orchestrate_proof`

### What's Missing for Stage 3 Closure

| Gap | What's Needed | Priority |
|-----|---------------|----------|
| End-to-end proof-carrying bus validation | Reconcile Issue `#43` against the current code and close remaining acceptance-criteria gaps | 🔴 High |
| Agent workflow examples | Real-world examples showing reflective verification loops | 🟡 Medium |
| Acceptance criteria validation | Run Stage 3 criteria from [agi_roadmap_v2.md §4.3](file:///d:/AgenticAI/LogicBrain/docs/agi_roadmap_v2.md) against LogicBrain-assisted agent workflows | 🟡 Medium |

---

## Stage 4: Learning Agent (v0.8 – v1.2)

> **Goal:** Enable verified learning — an agent that remembers *proven*
> conclusions and exchanges proofs across boundaries.

### Version Overview

| Version | Module | AGI Capability | Status |
|---------|--------|----------------|--------|
| **v0.8** | `AssumptionSet` | Typed epistemic state (fact / assumption / hypothesis) | ✅ Implemented |
| **v0.9** | `CounterfactualPlanner` | Branch-aware planning with Z3 push/pop | ✅ Implemented |
| **v1.0** | `ActionPolicyEngine` v2 | Hard pre-action enforcement with violation evidence | ✅ Implemented |
| **v1.1** | `UncertaintyCalibrator` | Typed confidence + mandatory escalation hooks | ✅ Implemented |
| **v1.2** | `ProofExchangeNode` | Multi-agent proof bundles with schema versioning | ✅ Implemented |

### Critical Caveat (from Consensus Review)

> These modules are **primitives toward verified memory**, not a full
> learning system. A true Stage 4 Learning Agent requires:
> - Selective retrieval with relevance weighting (not just storage)
> - Forgetting policies (not just accumulation)
> - Cross-task transfer of strategies (not just proofs)
>
> LogicBrain provides the *verification substrate* — the guarantee that
> stored knowledge is sound. The retrieval, weighting, and transfer
> logic belongs in the agent, not in LogicBrain.

### What's Missing for Stage 4 Contribution

| Gap | What's Needed | Priority |
|-----|---------------|----------|
| Verified memory retrieval API | Expose proof certificates as queryable memory with relevance metadata | 🔴 High |
| Schema migration tooling | `ProofExchangeNode` schema versioning + migration for long-lived stores | 🟡 Medium |
| Cross-agent integration test | End-to-end: Agent A produces proofs, Agent B verifies and reuses | 🟡 Medium |
| Verifier-Learner interface spec | Document exactly what Z3 can/cannot check about learned knowledge (per [§5.7](file:///d:/AgenticAI/LogicBrain/docs/agi_roadmap_v2.md)) | 🟢 Done in v2 |

---

## Stage 5: General Cognitive Agent (v1.5+)

> **Goal:** Contribute to the Integration Kernel — the coordination
> layer that binds all modules of a cognitive architecture.

This stage is **research-grade** and depends on breakthroughs outside
LogicBrain's scope. However, LogicBrain can prepare specific primitives:

| Contribution | Description | Dependency |
|-------------|-------------|------------|
| **Meta-verification** | Can Z3 verify properties of the integration kernel itself? (e.g., "no action executes without Governor approval") | Requires formal model of kernel |
| **Neuro-symbolic bridge** | State encoder that maps LLM outputs to Z3-compatible symbolic variables | Requires embedding alignment research |
| **Governor-grade policy enforcement** | Extend `ActionPolicyEngine` to constrain not just actions but learning/goal-setting processes | Requires Governor architecture design |
| **Compositional certificates at scale** | Proof orchestration across 100+ sub-claims with partial verification | Requires v0.7 foundation |

### Not Planned (and Why)

| Feature | Reason |
|---------|--------|
| World model implementation | Agent's responsibility; LogicBrain verifies, doesn't simulate |
| Foundation model training | Out of scope — LogicBrain is model-agnostic |
| Embodiment / robotics | Explicitly scoped out (see agi_roadmap_v2.md §1) |
| Full episodic memory system | Agent's responsibility; LogicBrain provides verified storage primitives |
| MCTS / tree search | Agent strategy; LogicBrain prunes via policies, doesn't search |

---

## Consolidated Next Steps (Priority Order)

**Strategic direction (2026-03-29):** Stage 3 fully closed. Stage 4 substrate
complete (#81–#82, MCP exposure, exception hierarchy). Next: API stabilization
(Tier-1 promotion), relevance retrieval, then PyPI publication.

### Wave 1: Z3 Grounding Closure (Issues #63–#66)

These issues make the formal guarantees real. Until these are closed, modules
claim soundness they don't fully deliver.

| # | Issue | Module | Acceptance Criteria | Effort |
|---|-------|--------|---------------------|--------|
| [**#63**](https://github.com/ThisIsBad/LogicBrain/issues/63) | Full Z3 grounding for `AssumptionSet` consistency | `assumptions.py` | All consistency checks backed by Z3 solver; `unknown` results surfaced explicitly; metamorphic tests for large assumption sets | ~1 week |
| [**#64**](https://github.com/ThisIsBad/LogicBrain/issues/64) | Full Z3 grounding for `BeliefGraph` contradiction detection | `belief_graph.py` | Contradiction detection via Z3 for all supported graph topologies; no Python-only fallback that silently passes; metamorphic tests | ~1 week |
| [**#65**](https://github.com/ThisIsBad/LogicBrain/issues/65) | Full Z3 grounding for `GoalContract` preconditions | `goal_contract.py` | Nested contract preconditions verified via Z3; composite contracts correctly compose; metamorphic tests | ~1 week |
| [**#66**](https://github.com/ThisIsBad/LogicBrain/issues/66) | Full Z3 consistency + subsumption for `ActionPolicyEngine` | `action_policy.py` | Policy consistency and subsumption checked via Z3 (not structural comparison); metamorphic tests for policy order invariance | ~1 week |

### Wave 2: MCP End-to-End Validation (Issues #67–#68)

Proof that the tool surface works in real agent workflows, not just unit tests.

| # | Issue | Description | Acceptance Criteria | Effort |
|---|-------|-------------|---------------------|--------|
| [**#67**](https://github.com/ThisIsBad/LogicBrain/issues/67) | Stage 3 reflective workflow example | `examples/reflective_agent.py` | Runnable example: agent calls `verify_argument` → `check_assumptions` → `check_contract` → `proof_carrying_action` in a reflective loop; maps to Stage 3 criteria in `agi_roadmap_v2.md §4.3` | ~1 week |
| [**#68**](https://github.com/ThisIsBad/LogicBrain/issues/68) | Stage 3 benchmark harness | `tests/test_stage3_criteria.py` | Automated test that validates LogicBrain-assisted workflows against the measurable Stage 3 acceptance criteria from `agi_roadmap_v2.md` | ~1 week |

### Wave 3: Stage 4 Verification Substrate (Issues #69–#72)

Turn LogicBrain from stateless verification tools into stateful verification
memory — the foundation a Stage 4 Learning Agent needs for persistent,
queryable, cross-boundary reasoning.

| # | Issue | Module | Acceptance Criteria | Effort |
|---|-------|--------|---------------------|--------|
| [**#69**](https://github.com/ThisIsBad/LogicBrain/issues/69) | CertificateStore with query API | `certificate_store.py` (new) | In-memory store with hash-dedup, tagging, query, invalidation, pruning; metamorphic tests for idempotence, monotonicity, irreversibility | ~1 week |
| [**#70**](https://github.com/ThisIsBad/LogicBrain/issues/70) | MCP certificate_store tool | `mcp_tools.py`, `mcp_server.py` | store/get/query/invalidate/stats actions via MCP; follows z3_session dispatch pattern | ~3–4 days |
| [**#71**](https://github.com/ThisIsBad/LogicBrain/issues/71) | Cross-agent proof exchange E2E | `tests/test_cross_agent_exchange.py` | Happy path + tampered bundle + trust mismatch + missing dependency; no new production code | ~1 week |
| [**#72**](https://github.com/ThisIsBad/LogicBrain/issues/72) | VerifiedAgentRuntime composition test | `tests/test_runtime_composition.py` | Sequential composition (Request 2 uses Request 1 certs) + recovery chain (store survives failure); depends on #69 | ~1 week |

### Completed

| # | Action | Stage | Status |
|---|--------|-------|--------|
| [#69](https://github.com/ThisIsBad/LogicBrain/issues/69) | CertificateStore with query API | 4 | ✅ Done |
| [#70](https://github.com/ThisIsBad/LogicBrain/issues/70) | MCP certificate_store tool | 4 | ✅ Done |
| [#71](https://github.com/ThisIsBad/LogicBrain/issues/71) | Cross-agent proof exchange E2E | 4 | ✅ Done |
| [#72](https://github.com/ThisIsBad/LogicBrain/issues/72) | VerifiedAgentRuntime composition test | 4 | ✅ Done |
| [#63](https://github.com/ThisIsBad/LogicBrain/issues/63) | Full Z3 grounding: `AssumptionSet` | 3 | ✅ Done |
| [#64](https://github.com/ThisIsBad/LogicBrain/issues/64) | Full Z3 grounding: `BeliefGraph` | 3 | ✅ Done |
| [#65](https://github.com/ThisIsBad/LogicBrain/issues/65) | Full Z3 grounding: `GoalContract` | 3 | ✅ Done |
| [#66](https://github.com/ThisIsBad/LogicBrain/issues/66) | Full Z3 grounding: `ActionPolicyEngine` | 3 | ✅ Done |
| [#67](https://github.com/ThisIsBad/LogicBrain/issues/67) | Stage 3 reflective workflow example | 3 | ✅ Done |
| [#68](https://github.com/ThisIsBad/LogicBrain/issues/68) | Stage 3 benchmark harness | 3 | ✅ Done |
| #47 | Cost-risk-utility planning layer | 4 | ✅ Done |
| #50 | Autonomous recovery protocols | 4 | ✅ Done |
| #49 | Federated trust-domain proof ledger | 4 | ✅ Done |
| #48 | Verified runtime loop | 5 | ✅ Done |
| #45 | Adversarial self-play harness | 5 | ✅ Done |

---

## How This Connects to `agi_roadmap_v2.md`

```mermaid
graph TD
    AGI["AGI Roadmap v2<br/>(Theoretical Framework)"]
    LB["LogicBrain Roadmap<br/>(This Document)"]
    
    AGI -->|"Module 5: Verifier"| LB
    AGI -->|"Module 3: Planner (primitives)"| LB
    AGI -->|"Module 8: Governor (primitives)"| LB
    AGI -->|"Module 2: Memory (primitives)"| LB
    
    LB -->|"Stage 2 ✅"| S2["MCP Tool Endpoints"]
    LB -->|"Stage 3 mostly implemented"| S3["Reflective Verification"]
    LB -->|"Stage 4 🔧"| S4["Verified Memory"]
    LB -->|"Stage 5 🔬"| S5["Integration Kernel"]
    
    S3 -->|"needs closure"| V7["Issue #43 validation"]
    S3 -->|"needs benchmarks"| MCP3["Stage 3 workflow validation"]
    S4 -->|"v1.3 needed"| V13["Memory Retrieval API"]
```

---

## References

| Document | Role |
|----------|------|
| [agi_roadmap_v2.md](file:///d:/AgenticAI/LogicBrain/docs/agi_roadmap_v2.md) | Theoretical framework (AGI stages + modular architecture) |
| [roadmap_v013_v020.md](file:///d:/AgenticAI/LogicBrain/docs/roadmap_v013_v020.md) | Historical — API stabilization (completed) |
| [roadmap_v030_v070.md](file:///d:/AgenticAI/LogicBrain/docs/roadmap_v030_v070.md) | Detailed specs for v0.3–v0.7 modules |
| [roadmap_v080_v120.md](file:///d:/AgenticAI/LogicBrain/docs/roadmap_v080_v120.md) | Detailed specs for v0.8–v1.2 modules |
| [STABILITY.md](file:///d:/AgenticAI/LogicBrain/STABILITY.md) | API stability contract |
| [formal_guarantees.md](file:///d:/AgenticAI/LogicBrain/docs/formal_guarantees.md) | Soundness/completeness properties |
