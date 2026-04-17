# Changelog

All notable changes to this project are documented in this file.

## [Unreleased]

### Added
- `explain.py` module with `truth_table()` and `render_truth_table()` for human-readable proof verification.
- `TruthTable` and `TruthTableRow` dataclasses for truth table results.

## [0.9.0] - 2026-03-29

Stage 4 verification substrate hardened with Z3-backed compaction,
consistency-filtered retrieval, relevance ranking, and a domain-specific
exception hierarchy. Nine exports promoted to Tier 1.

### Added
- `CertificateStore.compact()` - Z3-verified redundancy removal for propositional certificates.
- `CompactionResult` dataclass for compaction outcomes.
- `CertificateStore.query_consistent()` - Z3 consistency-filtered retrieval for propositional certificates.
- `ConsistencyFilterResult` dataclass for consistency-filtered query outcomes.
- `CertificateStore.query_ranked()` - Token-overlap relevance-ranked retrieval using Jaccard similarity.
- `RankedCertificate` and `RelevanceResult` dataclasses for relevance-ranked query outcomes.
- MCP `certificate_store` tool now supports `compact`, `query_consistent`, and `query_ranked` actions.
- `exceptions.py` module with domain-specific exception hierarchy: `LogicBrainError`, `VerificationError`, `ConstraintError`, `SessionError`, `CertificateError`, `PolicyViolationError`. All new exceptions inherit from `ValueError` where appropriate for backward compatibility.
- Proof template transfer experiment validating Gap 4 (strategy transfer) with 100% transfer rate across 7 valid and 2 invalid reasoning patterns.

### Changed
- `ParseError` now inherits from `LogicBrainError` (previously `Exception`). Existing `except ParseError` handlers are unaffected.
- `UnknownSessionError`, `ExpiredSessionError`, `SessionLimitError` now inherit from `SessionError` (previously `Exception`).
- Z3 constraint parsing errors in `Z3Session` now raise `ConstraintError` instead of `ValueError`. `ConstraintError` inherits from `ValueError`, so existing handlers are unaffected.
- Promoted `Z3Session`, `CheckResult`, `Diagnostic`, `ErrorType`, `ProofCertificate`, `certify`, `certify_z3_session`, and `verify_certificate` from Tier 2 to Tier 1 in `STABILITY.md`.

## [0.8.0] - 2026-03-21

Stage 3 fully validated, Stage 4 verification substrate complete. This release
adds 15+ modules, 12 MCP tools, and 500+ tests.

### Added
- Add `certificate.py` with `ProofCertificate`, `certify`, `certify_z3_session`, and `verify_certificate` for proof-carrying verification (#63).
- Add `assumptions.py` with `AssumptionSet` for typed epistemic state and Z3-backed consistency checks (#63).
- Add `counterfactual.py` with `CounterfactualPlanner`, branch replay, utility ranking, and safety bounds for counterfactual planning (#47).
- Add `action_policy.py` with `ActionPolicyEngine`, structured violation evidence, and Z3-backed consistency/subsumption checks (#50, #66).
- Add `uncertainty.py` with `UncertaintyCalibrator`, confidence records, and risk-based escalation hooks (#47).
- Add `belief_graph.py` with `BeliefGraph` and Z3-backed contradiction detection plus support-path explanations (#64).
- Add `goal_contract.py` with `GoalContract`, machine-checkable contracts, and Z3-backed precondition verification (#48, #65).
- Add `orchestrator.py` with `ProofOrchestrator`, claim decomposition, propagation, and composed certificates (#43).
- Add `execution_bus.py` with `ActionEnvelope`, `ActionBusResult`, postcondition checks, and proof-carrying execution traces (#43).
- Add `proof_exchange.py` with `ProofBundle`, `ProofExchangeNode`, and cross-agent proof exchange with schema versioning (#37).
- Add `recovery.py` with `RecoveryProtocol`, deterministic failure classification, and recovery certificates (#50).
- Add `trust_ledger.py` with `FederatedProofLedger` and trust-domain scoped proof acceptance for exchanged bundles (#49).
- Add `verified_runtime.py` with `VerifiedAgentRuntime` for closed-loop planning, contracts, uncertainty, execution, and recovery (#48).
- Add `adversarial_harness.py` with `AdversarialSelfPlayHarness` for deterministic red-team campaigns over runtime traces (#45).
- Add `certificate_store.py` with `CertificateStore`, `StoredCertificate`, and `StoreStats` for hash-deduped proof memory with tagging, invalidation, and query APIs (#69).
- Add MCP tools `check_beliefs`, `counterfactual_branch`, `check_contract`, `check_policy`, `z3_session`, `orchestrate_proof`, `proof_carrying_action`, and `certificate_store`, expanding the MCP surface from 5 to 12 tools (#64, #65, #66, #70).
- Add `examples/reflective_agent.py` as a runnable Stage 3 reflective verification workflow example (#67).
- Add `tests/test_stage3_criteria.py` as the Stage 3 benchmark harness with local criteria checks and external benchmark placeholders (#68).
- Add `tests/test_cross_agent_exchange.py` for end-to-end cross-agent proof exchange across bundle verification, trust evaluation, and execution (#71).
- Add `tests/test_runtime_composition.py` for sequential `VerifiedAgentRuntime` composition with persistent certificates across requests (#72).
- Add metamorphic suites `tests/test_metamorphic_certificate_store.py`, `tests/test_metamorphic_belief_graph.py`, and `tests/test_metamorphic_goal_contract.py` to lock in new invariants across Stage 3 and Stage 4 primitives (#64, #65, #69).
- Add Z3 grounding closure across `AssumptionSet`, `BeliefGraph`, `GoalContract`, and `ActionPolicyEngine`, eliminating Python-only fallbacks in formal checks (#63, #64, #65, #66).
- Add 330+ tests since `v0.2.0`, growing the suite from about 185 tests to 500+ tests with coverage and metamorphic gates in CI.

### Changed
- Change `AssumptionSet`, `BeliefGraph`, `GoalContract`, and `ActionPolicyEngine` to surface explicit solver status and `unknown` outcomes instead of silently treating them as success (#63, #64, #65, #66).
- Change MCP server and tool wiring to expose the expanded agent-facing workflow surface, including persistent proof memory (#67, #70).
- Change runtime and validation coverage from isolated unit checks to end-to-end reflective, cross-agent, and sequential-composition workflows (#67, #68, #71, #72).

## [0.2.0] - 2026-03-13

First release with an explicit API stability contract. Agent developers can
rely on Tier 1/2 exports per `STABILITY.md`.

### Added
- **`STABILITY.md`** — API stability contract with 3-tier classification (Stable / Provisional / Internal), semver rules, and deprecation policy.
- **`examples/agent_integration.py`** — Copy-paste-ready example showing full agent workflow: verify arguments, generate problems, Z3 sessions, diagnostics, and Lean proofs.
- **`py.typed` marker** — PEP 561 compliance for downstream type-checking.
- **`ProblemGenerator` and `GeneratorConfig`** exported from `logic_brain` (Tier 2 — Provisional).
- **API reference** generated via pdoc at `docs/api/`.
- **32 new tests** for `generator`, `analyzer`, `external`, and `lean_verifier` modules (total: 185+).
- **ruff linting** in CI pipeline.
- **Python 3.12** in CI test matrix.
- **Benchmark regression gate** (`tools/check_results.py exam`) in CI.
- `__all__` defined in 8 internal modules; internal parser classes prefixed with `_`.
- `schema_version` field on `Diagnostic` dataclass.

### Changed
- Internal parser classes renamed: `Token` → `_Token`, `Lexer` → `_Lexer`, `Parser` → `_Parser`.
- Broad `except Exception` narrowed to specific types in `predicate.py` and `lean_verifier.py`.
- `z3-solver` dependency pinned to `>=4.12,<5.0`.
- `pdoc` added to dev dependencies.
- `README.md` updated with new project structure, agent integration section, and API reference link.

### Removed
- 9 deprecated root-level scripts (moved to `tools/` in v0.1.2).
- Dead `SortType` enum from `z3_session.py`.
- `todo.md` replaced with pointer to `docs/roadmap_v013_v020.md`; original archived to `docs/archive/todo_v012.md`.

## [0.1.2] - 2026-03-13

### Added
- Safe AST-based constraint parsing in `Z3Session` (replaces `eval`) with explicit operator/function allow-listing.
- New tooling entrypoints: `tools/generate_exam.py`, `tools/generate_hardmode.py`, `tools/generate_escalation.py`, `tools/check_stress_results.py`, `tools/check_fol_results.py`.
- Additional Z3 session tests for implication operators and malformed/unsupported syntax handling.

### Changed
- `tools/check_predicate_results.py` now acts as a legacy wrapper and forwards to `tools/check_fol_results.py`.
- Root scripts `generate_exam.py`, `hardmode.py`, `escalate.py`, `verify_stress.py` now act as deprecated wrappers to `tools/` commands.
- README and release playbook now document canonical `tools/` flows for generation and checking (including FOL and stress).

## [0.1.1] - 2026-03-12

### Added
- CLI entrypoint via `python -m logic_brain` with `--json` and `--explain` output modes.
- Structured diagnostics exports in public API (`Diagnostic`, `ErrorType`, parser helpers).
- Property-based and fuzz testing with Hypothesis.
- Example scripts in `examples/` and notebook demo in `examples/logic_brain_demo.ipynb`.
- Extension feasibility document at `docs/logic_extensions_assessment.md`.

### Changed
- `Z3Session` now provides structured diagnostics for unsat/unknown and parse failures.
- Improved parser and diagnostics coverage with additional tests.
- Consolidated result checking scripts into `tools/check_results.py`.

### Fixed
- Editable install (`pip install -e ".[dev]"`) by constraining setuptools package discovery.
