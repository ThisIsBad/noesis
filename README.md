# Noesis

> A coordinated ecosystem of MCP services closing the gap between LLMs and AGI.

Noesis is a **monorepo** that maps the cognitive architecture needed for general
intelligence onto independently deployable MCP services. Each service addresses
one specific gap that LLMs alone cannot close.

## Repository Layout

```
noesis/
├── schemas/          # Shared data contracts (Pydantic) — install first
├── eval/             # Reproducible benchmark harness
├── kairos/           # Cross-service observability & tracing
└── services/
    ├── mneme/        # Persistent memory
    ├── praxis/       # Hierarchical planning
    ├── telos/        # Goal stability monitoring
    ├── episteme/     # Metacognition & calibration
    ├── kosmos/       # Causal world model
    ├── empiria/      # Experience accumulation
    └── techne/       # Verified skill library
```

> **Logos** lives in its own repo ([ThisIsBad/logos](https://github.com/ThisIsBad/logos))
> because it was developed independently and is already deployed. All other
> services live here.

## Services

| Service | Function | AGI Stage | Status |
|---------|----------|-----------|--------|
| **[Logos](https://github.com/ThisIsBad/logos)** | Formal verification (Z3/Lean 4), assumption management, goal contracts | Stage 2–3 | ✅ Deployed (external) |
| **Mneme** | Persistent episodic + semantic memory, verified belief storage | Stage 3–4 | 🔲 Planned |
| **Praxis** | Hierarchical planning, Tree-of-Thoughts search, backtracking | Stage 3 | 🔲 Planned |
| **Telos** | Goal stability monitoring, drift detection, alignment checks | Stage 3 | 🔲 Planned (vorgezogen) |
| **Episteme** | Metacognition, uncertainty calibration, competence mapping | Stage 3 | 🔲 Planned |
| **Kosmos** | Causal world model, Do-calculus, interventional reasoning | Stage 3–4 | 🔲 Planned |
| **Empiria** | Experience accumulation, lesson extraction, pattern mining | Stage 4 | 🔲 Planned |
| **Techne** | Verified skill library, strategy reuse across sessions | Stage 4 | 🔲 Planned |

### Cross-cutting

| Component | Function | Status |
|-----------|----------|--------|
| **schemas/** | Shared contracts: `ProofCertificate`, `GoalContract`, `Memory`, `Plan`, `Skill`, `Lesson` | ✅ Defined |
| **eval/** | Reproducible benchmarks: ARC-AGI, ALFWorld, WebArena, ECE, Drift | 🔲 Skeleton |
| **kairos/** | Cross-service tracing via OpenTelemetry | 🔲 Skeleton |

## Architecture

Each service is an **independently deployable** FastAPI + MCP HTTP service
(Railway, Port 8000). Claude orchestrates state-mutating calls — no direct
service-to-service writes.

**Exception — Logos read-only sidecar:** Services may call Logos directly for
idempotent verification (`certify_claim`, `z3_check`, `verify_argument`, etc.)
to avoid expensive Token-Roundtrips through Claude. State mutations remain
Claude-orchestrated.

See [docs/architecture.md](docs/architecture.md) for the full architecture and
[docs/ROADMAP.md](docs/ROADMAP.md) for the stage-by-stage roadmap with
acceptance criteria.

## Getting Started

```bash
# 1. Install shared schemas (required by all services)
pip install -e schemas/

# 2. Install and test a service
cd services/mneme
pip install -e .
python -m pytest -q

# 3. Run locally
python -m mneme.mcp_server_http
```

## Preflight Gates (all services)

```bash
python -m pytest -q
python -m ruff check src/ tests/
python -m mypy --strict src/
python -m pytest --cov=src/<service> --cov-fail-under=85
```
