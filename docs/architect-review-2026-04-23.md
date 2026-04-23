# Noesis — Architect Review (2026-04-23)

> Repository-wide assessment written after the Theoria visualization
> work landed on PR #77. Captures what's strong, what's mis-aligned,
> and what to do next. The **Tier 1 checklist at the bottom is the
> immediate action list** — items get ticked off as they're merged.

## Executive summary

Noesis is a serious, technically coherent project — not a weekend
prototype. Roughly 20 k lines of Python across 8 services + 3
cross-cutting packages + a real eval harness, with schema-first
design, a consistent service template, MCP as the orchestration
protocol, Kairos as proper OpenTelemetry-based tracing, production
deployments on Railway, and a Claude-Agent-SDK-driven A/B
benchmarking rig. Most of the **sharpest issues are organizational,
not technical**: the status markers in the README are out of date,
CI is duplicated 10×, and the project has no unified "what's actually
shipped vs. what's aspirational" view.

## What the numbers say

| Component | src lines | test lines | Dockerfile | Railway | CI workflow | MCP HTTP |
|-----------|-----------|-----------|-----------|---------|-------------|----------|
| **logos** | 11,894 | 10,012 | ✓ | ✓ | ✓ | ✓ |
| mneme | 592 | 821 | ✓ | ✓ | ✓ | ✓ |
| praxis | 602 | 735 | ✓ | ✓ | ✓ | ✓ |
| telos | 363 | 480 | ✓ | ✓ | ✓ | ✓ |
| episteme | 368 | 400 | ✓ | ✓ | ✓ | ✓ |
| kosmos | 228 | 220 | ✓ | ✓ | ✓ | ✓ |
| empiria | 265 | 221 | ✓ | ✓ | ✓ | ✓ |
| techne | 272 | 259 | ✓ | ✓ | ✓ | ✓ |
| **schemas** | 332 | 152 | — | — | (via consumers) | — |
| **kairos** | 374 | 451 | — | — | **NONE** | ✓ |
| **clients** | 309 | 332 | — | — | (via consumers) | — |
| **eval** | 3,077 | 4,526 | — | — | ✓ + `ab.yml` | — |
| **ui/theoria** | 2,942 | 2,330 | ✓ | ✓ | **NONE** | n/a (UI) |

Logos is the mothership — **80% of the backend code**. Every other
service is a 200–600-line skeleton with real tests. `eval/` is the
most underestimated piece: ~7.5 k lines, ALFWorld + Mneme benchmarks
+ A/B harness with budget caps.

## Critical misalignments (documentation vs. reality)

### 1. The root README is significantly out of date

`README.md` says the planned services are 🔲 not started. Reality:

- **Mneme is deployed** (`.mcp.json` points at
  `https://mneme-production-c227.up.railway.app/sse`).
- All seven have Dockerfiles, railway.toml, MCP servers, CI
  workflows, and 200–800 lines of tests each.
- Praxis has a Logos-sidecar skeleton in flight (commit `6f1f43f`).
- These are **MVPs in flight**, not "planned".

Anyone evaluating the project via the README will assume 7 services
don't exist when they demonstrably do. **Fix first.**

### 2. `.mcp.json` at the root lists only Mneme

Logos is claimed as ✅ "absorbed into `services/logos/`" and is
deployed, but is not registered as an MCP server in the repo-level
config. If this file is meant to document the Claude-facing surface,
it's incomplete.

### 3. Kairos has no CI

Kairos is a **shared dependency of every service**. A kairos
regression breaks everyone. There is `logos.yml`, `mneme.yml`, …,
`techne.yml`, `eval.yml`, `ab.yml` — but **no `kairos.yml`**. Same
gap for `schemas/` and `clients/` (they're exercised through consumer
workflows, which is defensible but slower to detect bugs).

### 4. `docs/ROADMAP.md` is in German, `README.md` in English

Not wrong, just inconsistent. Pick one. For a project documented in
English externally, the roadmap should match.

### 5. No `CLAUDE.md` at root

Given that **Claude is the designated orchestrator** (per
`architecture.md`), there is no file telling Claude what each service
does, when to call which, or error-handling norms. A single
`CLAUDE.md` at the root would be force-multiplier.

## Architectural strengths to preserve

- **Clean dependency graph.** `schemas` → consumed by everyone;
  `kairos` → consumed by everyone; `clients/noesis_clients` wraps
  cross-service HTTP (currently only LogosClient). No circular deps.
- **Service template is actually consistent.** Every service has the
  same layout, same preflight gates, same MCP wiring (FastMCP on top
  of Starlette).
- **Kairos is real observability.** Full OpenTelemetry SDK +
  exporter, not a stub. Trace-ID propagation is built into the
  service template.
- **Eval harness is serious.** `eval/` has ALFWorld, Mneme recall
  benchmarks, A/B testing with budget caps
  (`NOESIS_AB_MAX_BUDGET_USD`), retry helpers, history pooling. This
  is what proves the hypothesis — it's the right place to invest.
- **Logos-as-sidecar pattern.** Direct read-only calls for
  verification, state mutations through Claude. Cleanly documented in
  `architecture.md` and enforced by `noesis_clients`.
- **ProofCertificate round-trip test.**
  `schemas/tests/test_schemas.py::test_logos_certificate_round_trip`
  is the kind of cross-service contract test every architecture needs
  and most skip.

## Tier 1 — immediate fixes (this week)

> Small, mechanical, close the biggest trust / safety gaps at once.
> Marked off as they land on master.

- [x] **T1.1 Unify the status page.** Automate a top-level
  `STATUS.md` from per-service filesystem state (Dockerfile +
  railway.toml + MCP server + CI workflow + test count + LOC). The
  generator (`tools/generate_status.py`, stdlib-only) writes
  `STATUS.md`. `.github/workflows/status.yml` runs the generator on
  every push to master (auto-commits the result) and in check-mode
  on every PR (fails the build if `STATUS.md` drifted out of sync
  with the repo). Linked from the root README. —
  *landed 2026-04-23*
- [x] **T1.2 Add `kairos.yml` CI.** Lint + typecheck + test +
  coverage gate. Kairos is load-bearing for every service. —
  *landed 2026-04-23*
- [x] **T1.3 Add `theoria.yml` CI.** 147 tests and 91 % coverage
  were added on PR #77 and currently run nowhere. Workflow covers
  pytest+coverage, ruff, mypy --strict, Playwright browser smoke
  tests, and a Docker build job. — *landed 2026-04-23*
- [x] **T1.4 Orchestrator guide.** `docs/orchestration.md`
  (intentionally *not* at `CLAUDE.md` — the repo's `.gitignore`
  reserves that path for per-developer local instructions). Covers
  the service directory with every MCP tool listed, canonical
  orchestration patterns (belief storage, plan verification,
  calibration loop, skill reuse), error-handling norms, auth
  conventions, and where to add new capabilities. Linked from the
  root README. — *landed 2026-04-23*
- [x] **T1.5 Update README status table.** Mneme ✅ (deployed);
  Praxis / Telos / Episteme / Kosmos / Empiria / Techne 🟡 MVP
  (matches reality). — *landed 2026-04-23*

## Tier 2 — next month

- [x] **T2.1 Reusable CI workflow.** New
  `.github/workflows/_python-component.yml` accepts service-path /
  -name / coverage args / dep-flags / Docker flag /
  `coverage-fail-under` / extra pytest args / Python versions. Every
  per-service / per-package workflow is now a 26-line caller.
  Workflows shrank 1,617 → 938 lines (-42 %). Python-version bumps
  are now a one-line change. — *landed 2026-04-23*
- [ ] **T2.2 Cross-service E2E gate.** The architecture doc calls
  for ≥ 3-service E2E per phase. Today that lives in `eval/` and
  runs on its own schedule. Promote the Phase-1 scenario
  (`register_goal → decompose_goal → verify_plan → commit_step +
  store_memory`) to a PR gate using stub/mock services.
- [x] **T2.3 Praxis Logos-sidecar wiring.** `PraxisCore.__init__`
  now accepts an optional `LogosClient`. `verify_plan` runs local
  fast-fail checks first (no steps / risk ≥ 0.8), then asks Logos
  to certify the rendered plan: verified ⇒ pass with method noted,
  refuted ⇒ block, sidecar unreachable ⇒ pass with degraded note
  (architecture rule: a sidecar outage must not break the primary
  call). 5 new tests + 21 preexisting tests all green, 67 total
  Praxis tests pass. The MCP server reads `LOGOS_URL` /
  `LOGOS_SECRET` via `LogosClient.from_env()`. —
  *landed 2026-04-23*
- [ ] **T2.4 Shared test utilities.** Every service has fixtures
  for "fake Kairos", "fake MCP server", auth-header helpers.
  Extract into `testing/` or `clients/noesis_testing/` to DRY
  ~500 lines.
- [x] **T2.5 Add schemas + clients CI.** Both now have dedicated
  `.github/workflows/{schemas,clients}.yml` callers of the reusable
  workflow. `schemas` runs at 99.5 % coverage (10 passed, 1 skipped
  when z3 isn't available — added an `importorskip` guard on the
  Logos round-trip test). `clients` runs at 68 % coverage with the
  gate set to 65 % until SSE-transport paths get integration
  coverage. — *landed 2026-04-23*

## Tier 3 — backlog

- [ ] **T3.1 Lean 4 reality check.** Architecture claims Z3 + Lean 4;
  code shows Z3 heavily used, Lean 4 only referenced as a method
  string. Either wire it up or document it as aspirational.
- [ ] **T3.2 ChromaDB consolidation.** Three services (Mneme, Techne,
  Empiria) use Chroma. Either one shared instance with service-scoped
  collections, or document the "each service owns its vector store"
  rationale explicitly.
- [ ] **T3.3 Secrets story.** Every service has a bearer-token check
  (`LOGOS_SECRET`, `MNEME_SECRET`, now `THEORIA_SECRET`). No central
  rotation, no mTLS despite the architecture doc mentioning it.
- [ ] **T3.4 OTLP receiver story.** Kairos emits OpenTelemetry spans
  into the void unless `OTEL_EXPORTER_OTLP_ENDPOINT` is set. Either
  document the expected deployment or bundle an exporter default.
- [ ] **T3.5 Persistence consolidation.** Every service uses SQLite or
  embedded Chroma. At scale this is a bottleneck. Postgres with
  pgvector would consolidate persistence and give replication.
- [ ] **T3.6 Central API gateway / auth proxy.** At 8+ services, a
  gateway (Traefik, nginx with `auth_request`, Railway edge) would
  give you per-service tokens + rate limiting + central observability
  without code changes.
- [ ] **T3.7 Job queue.** Mneme's `consolidate` and Empiria's
  lesson-mining look like candidates for async jobs (Celery /
  Dramatiq / Temporal).
- [ ] **T3.8 LLM-as-judge for eval.** `eval/` is strong on
  deterministic metrics (ALFWorld success rate, recall@10). Cheap to
  add LLM-as-judge for regressions that aren't binary pass/fail.
- [ ] **T3.9 Kosmos / Empiria / Techne triage.** These services are
  ~200-300 src lines each. Decide which ship next, which get put on
  ice. Without a forcing function they'll all drift at 300 lines
  forever.
- [ ] **T3.10 Move Theoria persistence to Mneme** once Mneme is
  promoted to the general durable-store layer.

## External services / tools — assessment

**Have and using well:**
Z3 (Logos), ChromaDB (×3 services), NetworkX (Praxis + Kosmos),
SQLite (Praxis persistence), pgmpy (Kosmos causal), scipy (Episteme
calibration), OpenTelemetry (Kairos), FastAPI + FastMCP (every
service), Claude Agent SDK (eval), Railway (deploy),
GitHub Actions (CI).

**Missing or under-used:** see T3.3–T3.8.

**Do NOT add:**

- Additional MCP/agent framework (LangGraph / CrewAI / Autogen) —
  fragments the architecture.
- Second vector DB (Qdrant / Weaviate alongside Chroma) —
  consolidate, don't duplicate.
- Another tracing system (Sentry, LogRocket) unless piped through
  Kairos.

## Code-quality read (per service)

From sampling `core.py` in each:

- **Logos** — mature, well-factored. 12 k lines is a warning sign on
  its own; might be due for an internal refactor (extract
  `action_policy/` as a submodule, split `verifier/` by method).
- **Mneme** — FastMCP server is idiomatic, clean. `MNEME_SECRET` auth
  in place.
- **Praxis** — NetworkX DAG + SQLite; simple scoring heuristic
  (`_W_RISK=0.6`, `_W_TOOL=0.4`). Beam search is real. `verify_plan`
  is still a stub (see T2.3).
- **Telos** — lexical similarity (Jaccard) with
  `_CONFLICT_THRESHOLD=0.3`. Docstring openly acknowledges this is v1
  and should be replaced by a sentence-transformer. Good taste.
- **Episteme** — basic calibration (ECE), no Bayesian posterior yet.
  Matches the "MVP" read.
- **Kosmos, Empiria, Techne** — 200-ish src lines each; these are the
  thinnest. Worth triaging (T3.9).

## Overall verdict

- **Strategic direction:** correct. MCP-per-service + Claude
  orchestration + Logos sidecar + Kairos tracing is the right
  architecture for LLM-adjacent cognitive systems.
- **Execution quality:** high on the parts that exist. Logos is
  production-grade, eval is real, the service template scales.
- **Biggest single improvement:** fix the docs/reality gap. Automate
  the status view, fix the root README, add `CLAUDE.md`.
- **Biggest technical gap:** Kairos has no CI + the OTLP pipeline has
  no receiver documented. Observability is architecturally central
  but operationally under-finished.
- **Biggest organizational gap:** 6 of 8 services are in "MVP + tests"
  state. Without a forcing function (phase gate, eval-driven
  "next service to promote"), they'll all drift at 300 lines forever.
  Pick one, ship it to ✅, repeat.
