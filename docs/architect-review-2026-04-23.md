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
- [x] **T2.2 Cross-service E2E gate.** New
  `eval/tests/test_phase1_inprocess.py` instantiates real
  `TelosCore` + `PraxisCore` + `MnemeCore` (with tmp-dir storage)
  + a fake `LogosClient` and drives the canonical Phase-1
  scenario end-to-end at the tool-call layer:
  `register_goal → decompose_goal → add_step → verify_plan →
  commit_step → store → check_alignment`. Plus a counter-test for
  Logos refutation (blocks commit, Mneme stays empty) and a
  drift-detection regression. `.github/workflows/e2e.yml` runs on
  every PR without a paths filter — cross-service orchestration
  regressions from any participating service fail the PR
  immediately. Wire-format coverage is deliberately out of scope
  (already covered by `schemas/tests/test_logos_certificate_round_trip`
  and `clients/tests/test_logos.py`). —
  *landed 2026-04-23*
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
- [x] **T2.4 Shared test utilities.** New
  `noesis_clients.testing` submodule (inside the existing
  `noesis-clients` package, so every service that already depends
  on it gets the fakes for free — no new pyproject plumbing).
  Exports `FakeLogosClient` (drop-in for the async client, with
  `.calls` list and `.last_argument` convenience) plus
  `verified_certificate()` / `refuted_certificate()` factories.
  Three prior copies of the fake (Mneme, Praxis, Phase-1 E2E) now
  import from the shared module. Contract tests for the fakes live
  in `clients/tests/test_testing_helpers.py` so stand-in
  regressions fail fast. Future extractions (tracing-test
  parameterization, data-dir conftest) are straightforward follow-
  ups; deferred until they bite. — *landed 2026-04-23*
- [x] **T2.5 Add schemas + clients CI.** Both now have dedicated
  `.github/workflows/{schemas,clients}.yml` callers of the reusable
  workflow. `schemas` runs at 99.5 % coverage (10 passed, 1 skipped
  when z3 isn't available — added an `importorskip` guard on the
  Logos round-trip test). `clients` runs at 68 % coverage with the
  gate set to 65 % until SSE-transport paths get integration
  coverage. — *landed 2026-04-23*

## Tier 3 — backlog

- [x] **T3.1 Lean 4 reality check.** **My original finding was wrong**
  — Lean 4 *is* wired up: `services/logos/src/logos/lean_session.py`
  (416 lines, REPL wrapper with tactic-by-tactic application),
  `lean_verifier.py`, `diagnostics.py::LeanDiagnosticParser` (Lean
  error parser). Tests in `test_lean_session.py` (251 lines) +
  `test_lean_verifier.py` (73 lines) are guarded with
  `@pytest.mark.skipif(not is_lean_available())`. Exports are in
  `logos/__init__.py` tagged "Tier 2 / Provisional". The integration
  is real, not aspirational. The review claim was a miss — I only
  saw the method-string references and didn't grep deeper. No code
  change needed. — *verified 2026-04-23*
- [ ] **T3.2 ChromaDB consolidation.** Three services (Mneme, Techne,
  Empiria) use Chroma. Either one shared instance with service-scoped
  collections, or document the "each service owns its vector store"
  rationale explicitly.
- [x] **T3.3 Secrets story.** Documented the current state honestly
  in [`docs/operations/secrets.md`](operations/secrets.md): nine
  per-service bearer tokens read from Railway env, no rotation, no
  granularity, no mTLS despite the architecture doc claiming it,
  and near-duplicate middleware in every service. Proposed a
  three-stage forward path.

  **Stages 1 + 2 landed.** `noesis_clients.auth.bearer_middleware`
  + `BearerAuthMiddleware` (SSE-safe pure ASGI, env-var-driven,
  configurable exempt paths & prefixes, **rotatable secrets**).
  Stage 2: reads both `<SVC>_SECRET` (active) and
  `<SVC>_SECRET_PREV` (grace-period) — the middleware accepts
  either during rotation. Ops runbook in
  `docs/operations/secrets.md`. 38 contract tests in
  `clients/tests/test_auth.py` pin both stages. Clients: ruff
  clean, mypy --strict clean on 4 source files, 38 tests green.
  Per-service migration of the non-production services (Telos,
  Episteme, Kosmos, Empiria, Techne, Praxis) landed in Phase 2 of
  this push; Logos and Mneme deferred to their own PRs.

  Stage 3 (mTLS or gateway-JWT) remains on the roadmap — planned
  recommendation: Cloudflare Access in front of the Railway edge.
  — *documented + Stages 1-2 landed 2026-04-23*
- [x] **T3.4 OTLP receiver story.** **My review over-stated Kairos's
  OTEL integration.** Kairos lists `opentelemetry-exporter-otlp` as
  a dependency but never wires a `TracerProvider` or
  `OTLPSpanExporter` — services HTTP-POST spans to Kairos's custom
  JSON API and Kairos stores them in RAM. Documented this honestly
  in [`docs/operations/observability.md`](operations/observability.md)
  with the current pipeline, gaps (no OTLP, no persistence, no UI),
  a local-dev recipe (Jaeger docker-compose), and a forward path
  with a recommendation (option 2: services emit OTLP, collector
  fans out to Kairos + Jaeger). Kept as a planning artifact, not a
  this-week implementation — the architectural choice needs
  buy-in. — *landed 2026-04-23*
- [~] **T3.5 Persistence consolidation — prep landed, migration deferred.**
  My architect's call: **defer the actual Postgres move** until
  single-node scale starts hurting (currently nowhere near the
  ROADMAP's 100k-entries @ 200ms p99 target). Cheap prep landed now
  so the eventual flip is a config change, not a code refactor:
  `noesis_clients.persistence.resolve_sqlite_path` parses
  `<SVC>_DATABASE_URL` (SQLAlchemy form, e.g. `sqlite:////data/mneme.db`)
  with a graceful fallback to the legacy `<SVC>_DATA_DIR` convention
  and explicit rejection of non-SQLite URLs (don't silently accept
  a `postgresql://` we can't yet open). 8 contract tests in
  `clients/tests/test_persistence.py`. Documented in
  [`docs/operations/persistence.md`](operations/persistence.md) with
  the adoption checklist (Mneme + Praxis migration to the helper is
  a separate PR with your eyes on it). — *prep landed 2026-04-23*
- [ ] **T3.6 Central API gateway / auth proxy.** At 8+ services, a
  gateway (Traefik, nginx with `auth_request`, Railway edge) would
  give you per-service tokens + rate limiting + central observability
  without code changes.
- [~] **T3.7 Async consolidation — design landed, implementation
  deferred.** Wrote [`docs/operations/async-consolidation.md`](operations/async-consolidation.md)
  arguing against a job queue and for in-process
  `asyncio.create_task` + a polling status endpoint. Two new MCP
  tools (`consolidate_memories_async`, `get_consolidation_status`)
  with task state in a new SQLite table, stuck-task sweep on boot,
  one-task-at-a-time concurrency. Keeps the existing sync
  `consolidate_memories` tool as-is for back-compat. Recommended
  sequencing: profile the sync path at 10 k / 100 k memories first,
  optimise the O(N²) loop (batched Chroma query + union-find) before
  going async — that alone buys an order of magnitude. Ship async
  only if the optimised sync path still blocks past 5 s at realistic
  scale. Implementation deliberately **not** shipped — Mneme is
  production-deployed and the refactor wants its own reviewed PR.
  — *designed 2026-04-23*
- [~] **T3.8 LLM-as-judge for eval — rubric designed, implementation
  gated on review.** Wrote [`docs/eval/llm-judge-rubric.md`](eval/llm-judge-rubric.md):
  7 testable invariants (verification before durable writes,
  backtracking on failure, verify-plan before risky commits,
  goal-contract on multi-step plans, drift-check on destructive
  actions, calibration logging on low-confidence claims, skill
  reuse on repeat work), `{pass, fail, not_applicable}` verdicts
  per dimension (no aggregate quality score), structured JSON
  output, Haiku 4.5 with temperature 0, `NOESIS_AB_JUDGE_MAX_BUDGET_USD`
  cap ($0.50 default per eval invocation), cache by
  `(trace_id, rubric_version)` hash, 5–10 % sampling.
  Five open questions at the bottom of the doc for review.
  Implementation deliberately **not** shipped in this commit —
  writing the code first would commit us to a rubric we haven't
  agreed on. Post-review effort estimate: ~1 day judge module +
  tests, ~½ day CI wiring. — *designed 2026-04-23*
- [x] **T3.9 Kosmos / Empiria / Techne triage.** Audited all three.
  Every one is an in-memory dict + substring-match MVP with a
  "Production: ChromaDB / pgmpy" TODO comment. Honest status:

  - **Kosmos** (36 LOC core) — adjacency-dict causal graph with
    weight propagation. `counterfactual()` is a one-line wrapper
    around `compute_intervention`. No Bayesian network, no real
    do-calculus. Thinnest of the three.
  - **Empiria** (55 LOC core) — dict-of-Lesson with substring
    retrieval sorted by confidence.
  - **Techne** (51 LOC core) — dict-of-Skill, substring retrieval,
    plus running-average `success_rate` update. Also accepts a
    `ProofCertificate` on store so skills can be verified — the
    most interesting wiring of the three.

  Recommended ship order:

  1. **Techne first** — completes the Stage-4 loop
     (decompose → verify → commit → memory → skill) and the
     verified-skill certificate hook is a real differentiator.
     ChromaDB upgrade is a well-understood lift (Mneme already
     did it).
  2. **Empiria second** — same ChromaDB pattern, slightly weaker
     type story.
  3. **Kosmos last** — needs pgmpy + thoughtful do-calculus API
     design *and* a concrete consumer (e.g. Praxis scoring plans
     with causal priors). Speculative until there's a user.

  No code change needed on the triage itself; recommendation lives
  here for planning. — *landed 2026-04-23*

  **Techne ChromaDB promotion landed.** `TechneCore` now uses
  SQLite for structured rows + ChromaDB for semantic retrieval,
  mirroring Mneme's split. `store`, `retrieve`, `record_use` keep
  their signatures; new `get(skill_id)` helper. Retrieval uses
  Chroma k-nearest and re-ranks by `success_rate` so proven skills
  outrank marginally-better-matching unproven ones. Tests cover
  store + retrieve, semantic-beyond-substring (pins "retry" query
  hitting "attempt repeatedly"), verified-only filtering (3 cases),
  record-use rate updates + raises on unknown id, success-rate
  ranking, persistence across reopen. 12 new core tests + the 7
  auth tests + 11 preexisting = 30 Techne tests, all green.
  Dockerfile updated to install `noesis-clients` and document the
  new volume requirement. Empiria + Kosmos follow the same pattern
  when their turn comes. — *Techne promoted 2026-04-23*
- [x] **T3.10 ~~Move Theoria persistence to Mneme~~** — **retracted**.
  My original recommendation was wrong: Mneme's schema is "memory +
  optional certificate"; Theoria's is "DAG of reasoning steps +
  edges + outcome". Forcing one into the other loses the DAG
  structure (you'd serialize as JSON in Mneme's ``content`` field
  and re-parse every query — strictly worse than Theoria's current
  JSONL). When T3.5 lands, Theoria gets a proper ``decision_traces``
  Postgres table with JSONB for the DAG. Until then, its own
  JSONL is correct. — *retracted 2026-04-23*

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
