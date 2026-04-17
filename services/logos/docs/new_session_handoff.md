# Session Handoff

Last updated: 2026-03-29

## Last Completed Work

**v0.8.0 released (2026-03-22).** Release Polishing wave (#73–#75) complete.

### Relevance Retrieval, Tier-1 Promotion, Docs Sync (2026-03-29)

- `CertificateStore.query_ranked()` — Jaccard token-overlap relevance scoring. MCP `query_ranked` action.
- `RankedCertificate`, `RelevanceResult` dataclasses (Tier 2).
- Tier-1 promotions: `Z3Session`, `CheckResult`, `Diagnostic`, `ErrorType`, `ProofCertificate`, `certify`, `certify_z3_session`, `verify_certificate`. STABILITY.md v1.2.
- Docs synchronized.

Recent commit: `792fbed` — "Add relevance-ranked retrieval, Tier-1 promotions, and docs sync"

### MCP Exposure + Exception Hierarchy (2026-03-29)

- MCP `certificate_store` tool now supports `compact`, `query_consistent`, and `query_ranked` actions.
- Domain-specific exception hierarchy: `LogicBrainError` → `VerificationError`, `ConstraintError`, `SessionError`, `CertificateError`, `PolicyViolationError`. Backward-compatible via `ValueError` inheritance.
- `ParseError` reparented under `LogicBrainError`.
- MCP session errors (`UnknownSessionError`, `ExpiredSessionError`, `SessionLimitError`) reparented under `SessionError`.

Commit: `b7679b8` — "Add MCP compact/query_consistent actions and exception hierarchy"

### Stage 4 Production Modules (#81–#82) — complete

- `#81` closed: `CertificateStore.compact()` — Z3-verified redundancy removal.
- `#82` closed: `CertificateStore.query_consistent()` — Z3 consistency-filtered retrieval.

### Stage 4 Experiments (#77–#80) — complete

Experimental validation of the v0.8.0 verification substrate. All experiment
code under `tests/experiments/` — no production code changes.

- `#77` closed: Memory consistency stress test — 500 certs in 1.89s, 5/5 contradictions detected, 0 false positives.
- `#78` closed: Proof entailment compaction — EASY: 98.75% compaction (80 → 1 cert), all conclusions preserved.
- `#79` closed: Compaction curve across difficulty levels — 96–98% compaction at ALL levels (EASY through EXTREME), linear time scaling (2.7s → 11.4s).
- `#80` closed: Context-aware retrieval — Z3 consistency filter achieves 70% mean reduction; for non-contradictory queries, consistency = applicability (precision 100%).

**Key findings:**
- Z3-based compaction is production-ready (Gap 3 trigger condition met).
- Z3 consistency filtering is a viable retrieval pre-filter (Gap 2 partially met).
- Details and production module recommendations in `docs/stage4_research_watch.md`.

### Earlier work (collapsed)

- Release Polishing (#73–#75): STABILITY.md, CHANGELOG.md, README.md, LICENSE, version bump, tag, GitHub release.
- CI Modernization (#76): Python 3.13, pip cache, smoke tests.
- Wave 3 (#69–#72): Stage 4 Verification Substrate (CertificateStore, MCP, cross-agent exchange, runtime composition).
- Wave 2 (#67–#68): MCP End-to-End Validation.
- Wave 1 (#63–#66): Z3 Grounding Closure.
- Stage 4/5 primitives (#45, #47–#50).

## Current WIP

**#83 - Add explain.py with truth table generator**

- `logic_brain/explain.py` implemented with `TruthTable`, `TruthTableRow`, `truth_table()`, and `render_truth_table()`.
- Public exports, `STABILITY.md`, `CHANGELOG.md`, and new tests are in place.
- Full local preflight is now green after clearing local disk pressure and stabilizing Lean timeouts.
- Remaining local-only pricing tool files were reformatted so the repo-wide Ruff gate passes in this workspace.

## Issue Queue

### Open — Human-Readable Explain Wave

| # | Title | Depends on | Status |
|---|-------|------------|--------|
| [#83](https://github.com/ThisIsBad/LogicBrain/issues/83) | explain.py + truth table generator | — | Open |
| [#84](https://github.com/ThisIsBad/LogicBrain/issues/84) | Proof step chain | #83 | Open |
| [#85](https://github.com/ThisIsBad/LogicBrain/issues/85) | Mermaid proof graph export | #84 | Open |
| [#86](https://github.com/ThisIsBad/LogicBrain/issues/86) | Counterexample narration + labels | #83, #84 | Open |
| [#87](https://github.com/ThisIsBad/LogicBrain/issues/87) | MCP explain_argument tool | #86 | Open |

### Closed

- Wave 1 (#63–#66): Z3 Grounding Closure — ✅
- Wave 2 (#67–#68): MCP End-to-End Validation — ✅
- Wave 3 (#69–#72): Stage 4 Verification Substrate — ✅
- Stage 4/5 primitives (#45, #47–#50): Previously closed — ✅
- Release Polishing (#73–#75): v0.8.0 release — ✅
- CI Modernization (#76): Python 3.13 + smoke tests — ✅
- Stage 4 Experiments (#77–#80): Substrate validation — ✅
- Stage 4 Production Modules (#81–#82): compact() + query_consistent() — ✅
- MCP Exposure + Exception Hierarchy (untracked): — ✅
- v0.9.0 finalization (untracked): version bump, ProofTemplate experiment, docs — ✅

### After this wave

1. **PyPI publication** — v0.9.0 is ready; actual PyPI upload pending.
2. **Stage 4 research monitoring** — Track Gaps 1 (Stable Learning). See `docs/stage4_research_watch.md`.

## MCP Status

- **Claude Code:** uses `.mcp.json` in the project root
- **OpenCode:** uses `.opencode.json` in the project root
- **AntiGravity:** uses `~/.gemini/antigravity/mcp_config.json`
- **Server transport:** stdio with newline-delimited JSON-RPC
- **Exposed tools:** `verify_argument`, `certify_claim`, `certificate_store`, `check_assumptions`, `check_beliefs`, `counterfactual_branch`, `z3_check`, `check_contract`, `check_policy`, `z3_session`, `orchestrate_proof`, `proof_carrying_action`

## Important Notes

- Do not use `.claude/mcp.json` for Claude Code v2.1+; it is ignored.
- AntiGravity stores MCP config outside the repo, so that setup cannot be fully checked in.
- `.gitignore` now suppresses common local scratch/config files such as `AGENTS.md`, `CLAUDE.md`, `architektur-stefano.md`, `claude_mcp_debug.log`, `docs/gemini_review_prompt_de.md`, `nul`, and `.claude/`.

## Process Rules

- Treat `docs/agi_roadmap_v2.md` as the primary AGI framing document and `docs/logicbrain_development_roadmap.md` as the actionable LogicBrain roadmap.
- Read `docs/agent_collaboration.md` for role definitions and the Head-Agent / Implementer workflow.
- Read `docs/development_process.md` for the canonical workflow.
- One issue at a time, with full preflight gates before each implementation commit.
- Keep `docs/new_session_handoff.md` current after each completed issue, at WIP changes, and when queue or blocker state materially changes.
- If implementing a new issue: run pytest, ruff, mypy strict, coverage gate, and metamorphic tests before commit.
- Commit and push autonomously once gates pass.
