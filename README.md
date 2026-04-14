# Noesis

> A coordinated ecosystem of MCP services closing the gap between LLMs and AGI.

Noesis is not a single service — it is a **hub** that maps the cognitive
architecture needed for general intelligence onto independently deployable
MCP services. Each service addresses one specific gap that LLMs alone cannot close.

## Services

| Service | Function | AGI Stage | Status | Repo |
|---------|----------|-----------|--------|------|
| **Logos** | Formal verification (Z3/Lean 4), assumption management, goal contracts, counterfactual reasoning | Stage 2–3 | ✅ Deployed | [ThisIsBad/logos] |
| **Mneme** | Persistent episodic + semantic memory, verified belief storage | Stage 3–4 | 🔲 Planned | — |
| **Praxis** | Hierarchical planning, Tree-of-Thoughts search, backtracking | Stage 3 | 🔲 Planned | — |
| **Episteme** | Metacognition, uncertainty calibration, competence mapping | Stage 3 | 🔲 Planned | — |
| **Kosmos** | Causal world model, Do-calculus, interventional reasoning | Stage 3–4 | 🔲 Planned | — |
| **Empiria** | Experience accumulation, lesson extraction, pattern mining | Stage 4 | 🔲 Planned | — |
| **Techne** | Verified skill library, strategy reuse across sessions | Stage 4 | 🔲 Planned | — |
| **Telos** | Goal stability monitoring, drift detection, alignment checks | Stage 4 | 🔲 Planned | — |

## Architecture

Each service is an **independent repository** deployed as an MCP HTTP service
(e.g. on Railway). Claude orchestrates them — no direct service-to-service calls.
Logos acts as the optional **verification bus**: any service can request a formal
proof or policy check from Logos before committing to a state change.

```
Claude
  ├── Logos    (verify_argument, z3_check, check_policy, ...)
  ├── Mneme    (store_memory, retrieve_memory, ...)
  ├── Praxis   (decompose_goal, evaluate_step, backtrack, ...)
  ├── Episteme (log_prediction, get_calibration, should_escalate, ...)
  ├── Kosmos   (add_causal_edge, compute_intervention, ...)
  ├── Empiria  (record_experience, retrieve_lessons, ...)
  ├── Techne   (store_skill, retrieve_skill, ...)
  └── Telos    (register_goal, check_action_alignment, ...)
```

## AGI Roadmap

See [docs/ROADMAP.md](docs/ROADMAP.md) for the full stage-by-stage roadmap
with acceptance criteria and build priorities.

See [docs/architecture.md](docs/architecture.md) for the technical architecture
and deployment model.

## Background

The theoretical foundation is documented in the Logos repo at
`docs/agi_roadmap_v2.md` — a research-anchored, falsifiable roadmap from
current LLMs to AGI-like cognitive architectures (Claude Opus 4.6, 2026-03-20).
