# API Stability Contract

Version: 1.2 | Effective from: v0.8.0

---

## Stability Tiers

Every symbol exported from `logos` is assigned to one of three tiers.
The tier determines the guarantees you get when upgrading between releases.

### Tier 1 — Stable

**Guarantee:** No breaking changes within a major version (`0.x` series counts as pre-1.0; see Semver Rules below). Any planned removal or signature change will go through the Deprecation Policy.

| Export | Module | Description |
|---|---|---|
| `verify` | `parser` | Verify a string-based argument |
| `parse_argument` | `parser` | Parse argument string into `Argument` |
| `parse_expression` | `parser` | Parse expression string into `LogicalExpression` |
| `is_tautology` | `parser` | Check if expression is a tautology |
| `is_contradiction` | `parser` | Check if expression is a contradiction |
| `are_equivalent` | `parser` | Check if two expressions are equivalent |
| `ParseError` | `parser` | Exception for parse failures |
| `Proposition` | `models` | Atomic proposition |
| `LogicalExpression` | `models` | Compound expression |
| `Connective` | `models` | Enum of logical connectives |
| `Argument` | `models` | Premises + conclusion |
| `VerificationResult` | `models` | Verification outcome |
| `PropositionalVerifier` | `verifier` | Z3-backed propositional verifier |
| `Variable` | `predicate_models` | FOL variable |
| `Constant` | `predicate_models` | FOL constant |
| `Predicate` | `predicate_models` | FOL predicate |
| `PredicateConnective` | `predicate_models` | Enum of FOL connectives |
| `PredicateExpression` | `predicate_models` | FOL compound expression |
| `QuantifiedExpression` | `predicate_models` | Quantified FOL expression |
| `Quantifier` | `predicate_models` | Enum (FORALL, EXISTS) |
| `FOLArgument` | `predicate_models` | FOL argument |
| `PredicateVerifier` | `predicate` | Z3-backed FOL verifier |
| `Z3Session` | `z3_session` | Incremental Z3 solving session |
| `CheckResult` | `z3_session` | Result of a satisfiability check |
| `Diagnostic` | `diagnostics` | Structured error diagnostic |
| `ErrorType` | `diagnostics` | Enum of error categories |
| `ProofCertificate` | `certificate` | Serializable proof-carrying certificate |
| `certify` | `certificate` | Create a certificate from propositional or FOL verification |
| `certify_z3_session` | `certificate` | Create a certificate from a `Z3Session` check |
| `verify_certificate` | `certificate` | Re-verify a proof certificate deterministically |

### Tier 2 — Provisional

**Guarantee:** Functional and tested, but details may change between minor versions. Changes will be documented in `CHANGELOG.md`. No silent removals — at minimum a changelog entry.

| Export | Module | Description |
|---|---|---|
| `LogicBrainError` | `exceptions` | Base exception for all LogicBrain errors |
| `VerificationError` | `exceptions` | Verification operation failure |
| `ConstraintError` | `exceptions` | Invalid or unparseable Z3 constraint |
| `SessionError` | `exceptions` | Base for session-management failures |
| `CertificateError` | `exceptions` | Certificate creation or store failure |
| `PolicyViolationError` | `exceptions` | Policy evaluation error |
| `truth_table` | `explain` | Generate a complete truth table for a propositional argument |
| `render_truth_table` | `explain` | Render a truth table as a human-readable string |
| `TruthTable` | `explain` | Frozen result dataclass for truth-table explanations |
| `TruthTableRow` | `explain` | Frozen dataclass representing one truth-table row |
| `LeanSession` | `lean_session` | Lean 4 interactive proof session |
| `TacticResult` | `lean_session` | Result of applying a tactic |
| `is_lean_available` | `lean_session` | Check if Lean 4 is installed |
| `LeanDiagnosticParser` | `diagnostics` | Parser for Lean error output |
| `Z3DiagnosticParser` | `diagnostics` | Parser for Z3 error output |
| `ProblemGenerator` | `generator` | Fresh logic problem generator |
| `GeneratorConfig` | `generator` | Configuration for problem difficulty |
| `CertificateStore` | `certificate_store` | In-memory proof memory with hash-dedup, tagging, query, invalidation, and pruning |
| `RankedCertificate` | `certificate_store` | A stored certificate with relevance score |
| `RelevanceResult` | `certificate_store` | Result of a relevance-ranked query |
| `CompactionResult` | `certificate_store` | Result of Z3-verified store compaction |
| `ConsistencyFilterResult` | `certificate_store` | Result of Z3 consistency-filtered retrieval |
| `StoredCertificate` | `certificate_store` | Frozen dataclass representing one stored certificate entry |
| `StoreStats` | `certificate_store` | Frozen dataclass with aggregate store statistics |
| `AssumptionKind` | `assumptions` | Enum of typed assumption categories |
| `AssumptionStatus` | `assumptions` | Enum of assumption lifecycle states |
| `AssumptionEntry` | `assumptions` | Assumption record with provenance and lifecycle metadata |
| `AssumptionConsistency` | `assumptions` | Consistency result over active assumptions |
| `AssumptionSet` | `assumptions` | Deterministic typed assumption state manager |
| `VariableDecl` | `counterfactual` | Variable declaration for planning state snapshots |
| `PlanState` | `counterfactual` | Immutable state snapshot for a plan branch |
| `PlanBranch` | `counterfactual` | Evaluated branch in a counterfactual plan tree |
| `PlanResult` | `counterfactual` | Snapshot of counterfactual planner branches |
| `CounterfactualPlanner` | `counterfactual` | Deterministic branch planner over `Z3Session` semantics |
| `UtilityModel` | `counterfactual` | Explicit expected-value/cost/risk/confidence utility terms |
| `SafetyBound` | `counterfactual` | Hard safety caps for planner ranking |
| `RankedBranch` | `counterfactual` | Explainable ranking record with utility decomposition |
| `PolicyDecision` | `action_policy` | Enum of action policy enforcement outcomes |
| `ActionPolicyRule` | `action_policy` | Policy rule with explicit trigger conditions |
| `PolicyViolationEvidence` | `action_policy` | Structured evidence for a triggered policy rule |
| `ActionPolicyResult` | `action_policy` | Deterministic policy evaluation result |
| `ActionPolicyEngine` | `action_policy` | Deterministic pre-action policy evaluator |
| `ConfidenceLevel` | `uncertainty` | Enum of calibrated confidence levels |
| `RiskLevel` | `uncertainty` | Enum of escalation risk levels |
| `EscalationDecision` | `uncertainty` | Enum of escalation policy outcomes |
| `ConfidenceRecord` | `uncertainty` | Confidence record with provenance metadata |
| `EscalationResult` | `uncertainty` | Result of applying uncertainty escalation policy |
| `UncertaintyPolicy` | `uncertainty` | Risk-to-escalation mapping policy |
| `UncertaintyCalibrator` | `uncertainty` | Deterministic confidence calibration engine |
| `certificate_reference` | `uncertainty` | Create a stable certificate reference token |
| `resolve_certificate_reference` | `uncertainty` | Resolve certificate references from a store |
| `ProofExchangeNode` | `proof_exchange` | One proof bundle node with dependency links |
| `ProofBundle` | `proof_exchange` | Versioned proof exchange bundle |
| `ProofExchangeResult` | `proof_exchange` | Verification result for a received proof bundle |
| `create_proof_bundle` | `proof_exchange` | Build a transport-safe proof bundle |
| `verify_proof_bundle` | `proof_exchange` | Validate proof bundle integrity and dependencies |
| `BeliefEdgeType` | `belief_graph` | Enum of typed belief graph edge labels |
| `BeliefNode` | `belief_graph` | Belief node with temporal validity metadata |
| `BeliefEdge` | `belief_graph` | Directed typed relation between beliefs |
| `ContradictionExplanation` | `belief_graph` | Support-path explanation for a contradiction |
| `BeliefGraph` | `belief_graph` | Deterministic causal and temporal belief graph |
| `GoalContractStatus` | `goal_contract` | Enum of goal contract evaluation states |
| `GoalContractDiagnostic` | `goal_contract` | Structured goal contract violation diagnostic |
| `GoalContract` | `goal_contract` | Machine-checkable goal contract definition |
| `GoalContractResult` | `goal_contract` | Deterministic goal contract evaluation result |
| `build_branch_context` | `goal_contract` | Build contract context from a planner branch |
| `evaluate_goal_contract` | `goal_contract` | Evaluate a goal contract against a context |
| `verify_contract_preconditions_z3` | `goal_contract` | Check contract preconditions against Z3 constraints |
| `ActionEnvelope` | `execution_bus` | Proof-carrying action request spanning tool boundaries |
| `PostconditionCheck` | `execution_bus` | Expected postcondition check over an action result |
| `ActionBusResult` | `execution_bus` | Structured execution-bus result with trace and diagnostics |
| `execute_action_envelope` | `execution_bus` | Execute a proof-carrying action envelope via registered adapters |
| `ClaimStatus` | `orchestrator` | Enum of claim verification states |
| `Claim` | `orchestrator` | One claim node in a proof orchestration tree |
| `OrchestrationStatus` | `orchestrator` | Frozen status snapshot for a proof orchestration tree |
| `ProofOrchestrator` | `orchestrator` | Compositional proof tree with claim decomposition and propagation |
| `FailureCategory` | `recovery` | Unified failure taxonomy across planner/proof/policy modules |
| `RecoveryProtocol` | `recovery` | Deterministic recovery actions after failure |
| `FailureContext` | `recovery` | Auditable failure input used for protocol selection |
| `RecoveryCertificate` | `recovery` | Deterministic evidence that a recovery decision was compliant |
| `RecoveryDecision` | `recovery` | Selected recovery protocol with audit trace |
| `failure_context_from_dict` | `recovery` | Deserialize a failure context |
| `choose_recovery` | `recovery` | Select allowed recovery protocols deterministically |
| `verify_recovery_certificate` | `recovery` | Re-check recovery certificate consistency |
| `classify_action_bus_failure` | `recovery` | Normalize action-bus failures into the shared taxonomy |
| `classify_claim_failure` | `recovery` | Normalize orchestrator claim failures into the shared taxonomy |
| `classify_plan_failure` | `recovery` | Normalize planner branch failures into the shared taxonomy |
| `classify_goal_contract_failure` | `recovery` | Normalize goal-contract failures into the shared taxonomy |
| `TrustPolicy` | `trust_ledger` | Explicit trust-domain policy for cross-domain proof acceptance |
| `LedgerRecord` | `trust_ledger` | One accepted or rejected cross-domain proof decision |
| `LedgerQueryResult` | `trust_ledger` | Explainable answer to why a bundle is accepted or rejected |
| `FederatedProofLedger` | `trust_ledger` | Deterministic ledger for trust-scoped proof exchange |
| `RuntimePhase` | `verified_runtime` | Deterministic phase labels for the closed-loop runtime |
| `RuntimeEvent` | `verified_runtime` | One auditable runtime event |
| `RuntimeTrace` | `verified_runtime` | Ordered event log for one runtime cycle |
| `RuntimeRequest` | `verified_runtime` | Inputs for one verified runtime iteration |
| `RuntimeOutcome` | `verified_runtime` | Deterministic runtime result with trace and recovery state |
| `VerifiedAgentRuntime` | `verified_runtime` | Closed-loop runtime composing planning, contracts, uncertainty, and execution |
| `AttackTemplate` | `adversarial_harness` | Deterministic adversarial attack families |
| `DefensiveScore` | `adversarial_harness` | Explainable defense score decomposition |
| `SelfPlayEpisode` | `adversarial_harness` | One reproducible adversarial episode |
| `SelfPlayReport` | `adversarial_harness` | Regression artifact for adversarial campaigns |
| `AdversarialSelfPlayHarness` | `adversarial_harness` | Deterministic self-play/red-team harness over the runtime stack |

### Tier 3 — Internal

**No stability guarantee.** These modules are importable but not part of the public API. They may change or be removed without notice.

| Module | Description |
|---|---|
| `analyzer` | Error pattern analysis |
| `evaluate` | LLM evaluation script |
| `external` | External benchmark adapters |
| `generator` | Problem generation (presets `EASY`/`MEDIUM`/`HARD`/`EXTREME` are internal) |
| `lean_verifier` | Non-interactive Lean verification |
| `loader` | Benchmark JSON loader |
| `runner` | Benchmark runner |
| `schema_utils` | Shared schema and JSON validation helpers |

Within `parser.py`, the classes `Lexer`, `Parser`, and `Token` are implementation details. Do not import them directly.

---

## Semver Rules

LogicBrain follows [Semantic Versioning](https://semver.org/) with the following clarifications for the pre-1.0 period:

| Change Type | Version Bump | Example |
|---|---|---|
| Bug fix, no API change | Patch (`0.1.x`) | Fix incorrect rule identification |
| New export or optional parameter | Minor (`0.x.0`) | Add `ProblemGenerator` to `__all__` |
| Remove/rename Tier 1 export | Minor (`0.x.0`) + Deprecation Policy | Rename `verify` to `check` |
| Remove/rename Tier 2 export | Minor (`0.x.0`) + Changelog entry | Change `CheckResult` fields |
| Change Tier 3 internals | Patch (`0.1.x`) | Refactor `loader.py` |

**Pre-1.0 rule:** During the `0.x` series, minor version bumps (`0.x.0`) may contain breaking changes to Tier 1 exports, but only after the Deprecation Policy has been followed. Once `1.0.0` is released, Tier 1 breaking changes require a major version bump.

---

## Deprecation Policy

When a Tier 1 or Tier 2 symbol needs to change:

1. **Announce:** Add a `DeprecationWarning` via `warnings.warn()` in the current release.
2. **Document:** Note the deprecation in `CHANGELOG.md` with the planned removal version.
3. **Grace period:** The deprecated symbol must remain functional for at least one minor release.
4. **Remove:** Remove in the next minor release (or later). Document in `CHANGELOG.md`.

Example timeline:
- `v0.1.3`: `verify()` deprecated, `check_argument()` added. `verify()` still works, emits warning.
- `v0.1.4` (or later): `verify()` removed.

---

## What Counts as a Breaking Change

**Breaking (requires Deprecation Policy for Tier 1):**
- Removing an export from `__all__`
- Renaming a function, class, or method
- Changing required parameters of a function/method
- Changing the type of a return value
- Removing a field from a dataclass

**Not breaking:**
- Adding a new export to `__all__`
- Adding an optional parameter with a default value
- Adding a field to a dataclass with a default value
- Fixing a bug that changes behavior to match documentation
- Changing Tier 3 internals

---

## Downstream Integration Contract

If you integrate LogicBrain into an agent or tool:

1. **Import only from `logos`** — e.g., `from logos import verify`. Do not import from submodules directly (e.g., `from logos.parser import Lexer`).
2. **Check the tier** of each symbol you use. Tier 1 is safe for production. Tier 2 may change.
3. **Pin your version** in `requirements.txt` or `pyproject.toml` (e.g., `logos>=0.1.3,<0.2`).
4. **Read `CHANGELOG.md`** before upgrading.

---

## References

- Public API: `logos/__init__.py`
- Changelog: `CHANGELOG.md`
- Roadmaps: `docs/agi_roadmap_v2.md`, `docs/logicbrain_development_roadmap.md`, `docs/roadmap_v013_v020.md`, `docs/roadmap_v030_v070.md`, `docs/roadmap_v080_v120.md`
