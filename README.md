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
    ├── logos/        # Formal verification (Z3/Lean 4)
    ├── mneme/        # Persistent memory
    ├── praxis/       # Hierarchical planning
    ├── telos/        # Goal stability monitoring
    ├── episteme/     # Metacognition & calibration
    ├── kosmos/       # Causal world model
    ├── empiria/      # Experience accumulation
    └── techne/       # Verified skill library
```

> **Logos** was absorbed from its former standalone repo
> ([ThisIsBad/logos](https://github.com/ThisIsBad/logos)) into `services/logos/`
> to eliminate schema drift on `ProofCertificate`/`ConfidenceLevel` and unify
> deployment. See [services/logos/RAILWAY_MIGRATION.md](services/logos/RAILWAY_MIGRATION.md)
> for the migration path.

## Services

Status legend: ✅ deployed · 🟡 MVP in progress (code + tests, not yet deployed)
· 🔲 not started. See [STATUS.md](STATUS.md) for the auto-generated
per-service detail, and [docs/architect-review-2026-04-23.md](docs/architect-review-2026-04-23.md)
for the most recent architecture review.

| Service | Function | AGI Stage | Status |
|---------|----------|-----------|--------|
| **Logos** | Formal verification (Z3/Lean 4), assumption management, goal contracts | Stage 2–3 | ✅ Deployed |
| **Mneme** | Persistent episodic + semantic memory, verified belief storage | Stage 3–4 | ✅ Deployed |
| **Praxis** | Hierarchical planning, Tree-of-Thoughts search, backtracking | Stage 3 | 🟡 MVP (Logos sidecar WIP) |
| **Telos** | Goal stability monitoring, drift detection, alignment checks | Stage 3 | 🟡 MVP |
| **Episteme** | Metacognition, uncertainty calibration, competence mapping | Stage 3 | 🟡 MVP |
| **Kosmos** | Causal world model, Do-calculus, interventional reasoning | Stage 3–4 | 🟡 MVP (thin) |
| **Empiria** | Experience accumulation, lesson extraction, pattern mining | Stage 4 | 🟡 MVP (thin) |
| **Techne** | Verified skill library, strategy reuse across sessions | Stage 4 | 🟡 MVP (thin) |

### Cross-cutting

| Component | Function | Status |
|-----------|----------|--------|
| **schemas/** | Shared contracts: `ProofCertificate`, `GoalContract`, `Memory`, `Plan`, `Skill`, `Lesson`, `TraceSpan` | ✅ Defined |
| **kairos/** | Cross-service tracing via OpenTelemetry | 🟡 MVP (no dedicated CI) |
| **clients/** | Shared HTTP clients (`LogosClient`, ...) | 🟡 MVP |
| **eval/** | Reproducible benchmarks + A/B harness (ALFWorld, Mneme recall, MCP agent) | 🟡 MVP |
| **ui/theoria/** | Decision-logic visualizer (UI client, not a service) | 🟡 MVP |

## Architecture

Each service is an **independently deployable** FastAPI + MCP HTTP service
(Railway, Port 8000). Claude orchestrates state-mutating calls — no direct
service-to-service writes.

**Exception — Logos read-only sidecar:** Services may call Logos directly for
idempotent verification (`certify_claim`, `z3_check`, `verify_argument`, etc.)
to avoid expensive Token-Roundtrips through Claude. State mutations remain
Claude-orchestrated.

See:

- [docs/architecture.md](docs/architecture.md) — full architecture and design rationale
- [docs/ROADMAP.md](docs/ROADMAP.md) — stage-by-stage roadmap with acceptance criteria
- [docs/orchestration.md](docs/orchestration.md) — orchestrator's guide (what to call when, per-service MCP-tool index, canonical patterns)
- [docs/architect-review-2026-04-23.md](docs/architect-review-2026-04-23.md) — most recent repo-wide architecture review + action checklist
- [STATUS.md](STATUS.md) — auto-generated per-component status (Dockerfile / Railway / MCP / CI / LOC)

## Getting Started

```bash
# 1. Install shared schemas (required by all services)
pip install -e schemas/

# 2. Install and test a service
cd services/mneme
pip install -e .
python -m pytest -q

# 3. Run locally
MNEME_DATA_DIR=./tmp/mneme python -m mneme.mcp_server_http
# → MCP endpoint: http://localhost:8000/mcp
# → Health:       http://localhost:8000/health
```

## Deploying on Railway

Every service is an independent Railway service reading from a persistent
volume. All services share the **same** Railway project.

### One-time setup per service

1. **New Service → GitHub repo → `ThisIsBad/noesis`**
2. **Settings → Build**
   - Root Directory: *(leave empty — repo root)*
   - Dockerfile Path: `services/<name>/Dockerfile`
   (e.g. `services/mneme/Dockerfile`)
3. **Settings → Variables** — add:
   ```
   MNEME_DATA_DIR=/data
   PORT=8000
   ```
4. **Settings → Volumes** — mount `/data` (persists DB + ChromaDB across deploys)

### Connecting to Claude Code as MCP

After deploy, copy the Railway public URL and add it to your Claude Code
`~/.claude/settings.json`:

```json
{
  "mcpServers": {
    "mneme": {
      "type": "http",
      "url": "https://<your-mneme-url>.railway.app/mcp"
    }
  }
}
```

Logos is already connected? Same pattern — check its URL in Railway and
verify it's in your `mcpServers` config.

## Preflight Gates (all services)

```bash
python -m pytest -q
python -m ruff check src/ tests/
python -m mypy --strict src/
python -m pytest --cov=src/<service> --cov-fail-under=85
```
