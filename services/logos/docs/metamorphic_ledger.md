# Metamorphic Relation Ledger

Version: 1.0  
Status: Active

This ledger tracks metamorphic relations (MRs) as versioned "super-axioms" for
regression safety. Every MR entry must point to executable tests.

## Risk Taxonomy

- `core-semantics`: logical soundness of verification outcomes.
- `parser-robustness`: stability under syntax-preserving input transformations.
- `session-safety`: state and satisfiability invariants in incremental solving.

## Entry Schema

Each MR entry should include:

- `id`: stable identifier (e.g. `MR-V01`)
- `title`: short descriptive name
- `module`: primary module under test
- `risk_level`: one of the taxonomy values above
- `transform`: source -> transformed input relation
- `expected_relation`: invariant that must hold
- `tolerance`: exact, approximate, or bounded (with details)
- `status`: active, pending, deprecated
- `test_refs`: concrete pytest node references

## Seed Entries (MR-1..MR-3)

| id | title | module | risk_level | transform | expected_relation | tolerance | status | test_refs |
|---|---|---|---|---|---|---|---|---|
| MR-V01 | Implication rewrite (MP) | `verifier` | core-semantics | `A -> B` -> `(~A | B)` in premise | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_verifier.py::test_metamorphic_relations_preserve_validity[implication-rewrite-mp]` |
| MR-V02 | Implication rewrite (MT) | `verifier` | core-semantics | `A -> B` -> `(~A | B)` in premise | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_verifier.py::test_metamorphic_relations_preserve_validity[implication-rewrite-mt]` |
| MR-V03 | Double negation elimination | `verifier` | core-semantics | `~~A` -> `A` | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_verifier.py::test_metamorphic_relations_preserve_validity[double-negation-elim]` |
| MR-V04 | De Morgan conjunction form | `verifier` | core-semantics | `~(A & B)` -> `(~A | ~B)` | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_verifier.py::test_metamorphic_relations_preserve_validity[de-morgan-and]` |
| MR-P01 | Whitespace invariance | `parser` | parser-robustness | normalize spacing/newlines | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[whitespace-padding]`, `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[newline-premise-break]` |
| MR-P02 | Parentheses invariance (safe) | `parser` | parser-robustness | add redundant parentheses | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[parentheses-redundant]`, `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[parentheses-unary-binary]` |
| MR-P03 | Operator alias invariance | `parser` | parser-robustness | `->/=>`, `<->/<=>`, `~/!`, `&/^` | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[alias-imp-not]`, `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[alias-iff]`, `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[alias-and]` |
| MR-P04 | Premise order invariance | `parser` | parser-robustness | reorder comma-separated premises | `verify(...).valid` unchanged | exact | active | `tests/test_metamorphic_parser.py::test_parser_metamorphic_relations_preserve_outcome[premise-order]` |
| MR-Z01 | Push/pop restoration | `z3_session` | session-safety | add contradictory scope then `pop()` | baseline satisfiability restored | exact | active | `tests/test_metamorphic_z3_session.py::test_mr_push_pop_restores_baseline_sat` |
| MR-Z02 | Constraint order invariance (SAT/UNSAT) | `z3_session` | session-safety | reorder independent / contradictory constraints | `check().status` and `satisfiable` unchanged | exact | active | `tests/test_metamorphic_z3_session.py::test_mr_reordering_independent_constraints_preserves_sat`, `tests/test_metamorphic_z3_session.py::test_mr_reordering_contradictory_constraints_preserves_unsat` |
| MR-Z03 | Integer bound equivalence | `z3_session` | session-safety | `x > 5` <-> `x >= 6` | sat classification unchanged | exact | active | `tests/test_metamorphic_z3_session.py::test_mr_equivalent_integer_bounds_preserve_classification` |
| MR-Z04 | Reset-to-fresh equivalence | `z3_session` | session-safety | `reset(); redeclare; reassert` | behaves like fresh session | exact | active | `tests/test_metamorphic_z3_session.py::test_mr_reset_clears_state_and_redeclaration_behaves_like_fresh_session` |
| MR-C01 | Certificate roundtrip invariance | `certificate` | core-semantics | `cert` -> `ProofCertificate.from_json(cert.to_json())` | `verify_certificate` remains true and `verified` unchanged | exact | active | `tests/test_metamorphic_certificate.py::test_mr_c1_certificate_roundtrip_preserves_reverification` |
| MR-C02 | Equivalent argument invariance | `certificate` | core-semantics | rewrite argument with a logically equivalent form | certificate `verified` status unchanged | exact | active | `tests/test_metamorphic_certificate.py::test_mr_c2_equivalent_transforms_preserve_certificate_validity` |
| MR-C03 | Redundant premise invariance | `certificate` | core-semantics | add duplicate premise | certificate `verified` status unchanged | exact | active | `tests/test_metamorphic_certificate.py::test_mr_c3_redundant_premises_preserve_certificate_validity` |
| MR-C04 | Valid certification soundness | `certificate` | core-semantics | certify multiple independently valid arguments | every resulting certificate keeps `verified=True` | exact | active | `tests/test_metamorphic_orchestrator.py::test_mr_c4_valid_argument_certification_always_sets_verified_true` |
| MR-A01 | Assumption order invariance | `assumptions` | core-semantics | reorder insertion order of contradictory assumptions | consistency classification unchanged | exact | active | `tests/test_metamorphic_assumptions.py::test_mr_a01_assumption_order_invariance_for_consistency` |
| MR-A02 | Retraction idempotence | `assumptions` | session-safety | repeat `retract()` on same assumption | lifecycle status unchanged after first retract | exact | active | `tests/test_metamorphic_assumptions.py::test_mr_a02_redundant_retraction_is_idempotent` |
| MR-CP01 | Branch creation order invariance | `counterfactual` | session-safety | create sat/unsat branches in different order | branch classification unchanged | exact | active | `tests/test_metamorphic_counterfactual.py::test_mr_cp01_branch_creation_order_preserves_classification` |
| MR-CP02 | Replay idempotence | `counterfactual` | session-safety | replay the same branch repeatedly | replay classification unchanged | exact | active | `tests/test_metamorphic_counterfactual.py::test_mr_cp02_repeated_replay_preserves_classification` |
| MR-AP01 | Policy removal monotonicity | `action_policy` | core-semantics | remove one active policy | no new violations and no stricter decision | exact | active | `tests/test_metamorphic_action_policy.py::test_mr_ap01_removing_policy_cannot_introduce_new_violations` |
| MR-AP02 | Policy order invariance | `action_policy` | core-semantics | reorder policy registration order | final decision unchanged | exact | active | `tests/test_metamorphic_action_policy.py::test_mr_ap02_evaluation_order_does_not_change_decision` |
| MR-U01 | Risk monotonicity | `uncertainty` | core-semantics | increase risk level for same confidence record | escalation strictness does not decrease | exact | active | `tests/test_metamorphic_uncertainty.py::test_mr_u01_increasing_risk_does_not_reduce_strictness` |
| MR-U02 | Provenance order invariance | `uncertainty` | parser-robustness | reorder provenance entries | escalation decision unchanged | exact | active | `tests/test_metamorphic_uncertainty.py::test_mr_u02_provenance_order_does_not_change_escalation` |
| MR-PX01 | Bundle node order invariance | `proof_exchange` | core-semantics | reorder node insertion order in bundle construction | verification result unchanged | exact | active | `tests/test_metamorphic_proof_exchange.py::test_mr_px01_node_order_invariance` |
| MR-PX02 | Independent node extension invariance | `proof_exchange` | core-semantics | add an independent valid node to bundle | bundle validity remains true | exact | active | `tests/test_metamorphic_proof_exchange.py::test_mr_px02_adding_independent_valid_node_preserves_validity` |
| MR-BG01 | Support order invariance | `belief_graph` | core-semantics | reorder edge insertion for same support chain | minimal support set unchanged | exact | active | `tests/test_metamorphic_belief_graph.py::test_mr_bg01_support_order_invariance` |
| MR-BG02 | Temporal shift consistency | `belief_graph` | session-safety | shift all timestamps and query time by same delta | stale dependency classification unchanged | exact | active | `tests/test_metamorphic_belief_graph.py::test_mr_bg02_temporal_shift_consistency` |
| MR-GC01 | Equivalent clause formulation invariance | `goal_contract` | core-semantics | use equivalent invariant clauses (`sat` vs `!unsat`) | contract status unchanged | exact | active | `tests/test_metamorphic_goal_contract.py::test_mr_gc01_equivalent_clause_formulations_preserve_outcome` |
| MR-GC02 | Clause order invariance | `goal_contract` | core-semantics | reorder precondition/invariant clauses | contract status unchanged | exact | active | `tests/test_metamorphic_goal_contract.py::test_mr_gc02_clause_order_invariance` |
| MR-O01 | Sibling isolation under verification | `orchestrator` | session-safety | verify one sub-claim in a shared parent tree | sibling claim statuses remain unchanged | exact | active | `tests/test_metamorphic_orchestrator.py::test_mr_or01_verifying_subclaim_does_not_invalidate_siblings` |

## Maintenance Rule

When a metamorphic test is added, changed, or removed:

1. Update/add the corresponding ledger entry in this file.
2. Keep `test_refs` accurate and executable.
3. Reflect status changes (`active`, `pending`, `deprecated`).
