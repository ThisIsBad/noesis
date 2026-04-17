# Formal Guarantees and Mathematical Limits

This document states what LogicBrain can prove, what it cannot prove,
and why. Every contributor and every downstream agent must understand
these boundaries before relying on verification results.

## Background: What Z3 Is

Z3 is an SMT (Satisfiability Modulo Theories) solver. It decides whether
a logical formula is satisfiable, unsatisfiable, or unknown. LogicBrain
uses Z3 as its verification backend in two ways:

1. **Proof by refutation** — assert premises, negate conclusion, check
   for UNSAT. If UNSAT, the argument is valid. If SAT, the model is a
   counterexample.
2. **Constraint satisfaction** — declare variables, assert constraints,
   check for SAT/UNSAT.

Z3 is a correct implementation of the SMT-LIB standard. We inherit its
guarantees and its limits.

## Guarantee Table

| Domain | Module | Sound? | Complete? | Decidable? | Notes |
|--------|--------|--------|-----------|------------|-------|
| Propositional logic | `verifier`, `parser.verify` | Yes | Yes | Yes (co-NP) | Finite truth tables. Z3 decides all cases. |
| FOL (uninterpreted sorts) | `predicate` | Yes | **No** | **No** (semi-decidable) | Gödel/Church: no algorithm can decide all FOL validity. Z3 may return `unknown`. |
| QF_LIA (quantifier-free linear integer arithmetic) | `z3_session` | Yes | Yes | Yes | Typical `x > 0, y < 10` constraints. |
| QF_LRA (quantifier-free linear real arithmetic) | `z3_session` | Yes | Yes | Yes | Same, over reals. |
| QF_BV (quantifier-free bitvectors) | `z3_session` | Yes | Yes | Yes (NP-complete) | Fixed-width bitvector arithmetic. |
| QF_NIA (quantifier-free nonlinear integer arithmetic) | `z3_session` | Yes | **No** | **No** (undecidable) | Z3 uses heuristics. May return `unknown`. |
| LIA/LRA with quantifiers | `z3_session` | Yes | **No** | Depends on fragment | Quantifier elimination works for some fragments. |
| Mixed theories with quantifiers | `z3_session`, `predicate` | Yes | **No** | **No** | General undecidability applies. |

### What "Sound" Means

If LogicBrain says an argument is **valid**, it is valid. Z3 never
produces a false `unsat` result. This guarantee holds for all rows
in the table above.

### What "Not Complete" Means

If LogicBrain says an argument is **invalid**, it might be wrong — but
only in the `unknown` case. When Z3 returns `sat`, the counterexample
is genuine. When Z3 returns `unknown`, LogicBrain cannot determine
validity. The code reports this honestly (`verifier.py:100-106`,
`predicate.py:140-146`).

### What "Not Decidable" Means

There exist valid formulas in FOL and nonlinear integer arithmetic that
**no algorithm** can verify in finite time. This is not a limitation of
Z3 or LogicBrain — it is a mathematical fact (Church 1936, Gödel 1931,
Matiyasevich 1970). LogicBrain handles this by returning `unknown`
instead of looping forever (Z3 has internal timeouts).

## What the Higher-Level Modules Guarantee

The modules added in v0.8+ (`assumptions`, `counterfactual`,
`action_policy`, `uncertainty`, `belief_graph`, `goal_contract`) are
**data management layers**, not independent reasoning engines. Their
guarantees depend on whether they are connected to Z3:

| Module | Z3-connected? | Formal guarantee |
|--------|--------------|------------------|
| `certificate` | Yes (via `verify_certificate`) | Re-verification is sound: if it says the certificate is valid, it is. |
| `counterfactual` | Yes (via `Z3Session`) | Branch sat/unsat classification inherits Z3 soundness. |
| `assumptions` | **Partial** (`check_consistency` accepts external checker) | Only as strong as the checker you plug in. |
| `action_policy` | **Yes** (boolean policy formulas via Z3) | Boolean policy consistency and subsumption checks inherit Z3 soundness; runtime flag evaluation remains a structural fast path. |
| `uncertainty` | **No** (classification heuristic) | Deterministic but not formally grounded. |
| `belief_graph` | **No** (manual edge annotation) | Graph structure is correct; contradiction detection is manual, not Z3-derived. |
| `goal_contract` | **No** (string clause matching) | Deterministic but not formally grounded. |

### Implication

Modules marked "No" above provide **structural** guarantees (determinism,
serialization correctness, lifecycle enforcement) but not **logical**
guarantees. An `ActionPolicyEngine` that says "allow" does not mean the
action is logically safe — it means the boolean flags matched no blocking
rule.

To get formal guarantees from these modules, they must be wired to Z3.
This is the next planned step (see below).

## Planned: Z3-Connected Higher-Level Reasoning

The following connections are planned to lift data-management modules
into formally grounded reasoning:

1. **AssumptionSet + Z3Session**: Parse assumption statements as Z3
   constraints and check satisfiability of the active set. Detect real
   contradictions, not just manually flagged ones.

2. **GoalContract + Z3**: Express preconditions and invariants as Z3
   formulas evaluated against planner state, not boolean string matching.

3. **BeliefGraph + Z3**: Automatically detect contradictions by checking
   whether two belief statements are Z3-unsatisfiable together.

4. **ActionPolicyEngine + Z3**: Implemented for boolean policy formulas.
   The engine can now prove properties like "no two policies contradict"
   or "policy A subsumes policy B" while keeping the existing fast boolean
   evaluation path.

Each connection preserves the soundness guarantee: if Z3 says unsat,
the contradiction/subsumption/violation is real.

## What LogicBrain Will Never Do

These are hard mathematical limits, not engineering gaps:

- **Decide all FOL validity.** Impossible (Church's theorem).
- **Decide all nonlinear integer arithmetic.** Impossible
  (Matiyasevich/MRDP theorem).
- **Verify its own consistency.** Impossible for any sufficiently
  powerful system (Gödel's second incompleteness theorem).
- **Guarantee termination for arbitrary Z3 queries.** Z3 uses timeouts
  as a practical bound, but some queries may hit them.

## References

- Church, A. (1936). "A note on the Entscheidungsproblem."
- Gödel, K. (1931). "Über formal unentscheidbare Sätze."
- Matiyasevich, Y. (1970). "Enumerable sets are Diophantine."
- de Moura, L. & Bjørner, N. (2008). "Z3: An Efficient SMT Solver."
- Barrett et al. (2010). "SMT-LIB: The Satisfiability Modulo Theories Library."
