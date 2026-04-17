# Roadmap v0.3 – v0.7: Agent-Centric Deterministic Tooling

## Premise

LogicBrain v0.2.0 proved that an AI agent can use Z3 and Lean as
deterministic verification backends. But verification alone is reactive —
the agent acts, then checks. The next five versions shift LogicBrain from
**reactive verifier** to **proactive reasoning infrastructure**: tools the
agent uses *during* its thinking, not just after.

The guiding question: **What would I, as an AI coding agent, build for
myself if I could guarantee certain properties about my own reasoning?**

The answer decomposes into five capabilities, each building on the last:

```
v0.3  Proof-Carrying Actions       — attach machine-checked certificates to outputs
v0.4  Reasoning Contracts           — pre/post-conditions on agent reasoning steps
v0.5  Self-Consistency Checker      — detect contradictions in the agent's own beliefs
v0.6  Policy-Guided Search          — use formal policies to prune the action space
v0.7  Compositional Proof Orchestrator — decompose complex claims, verify in parallel
```

---

## v0.3 — Proof-Carrying Actions

**Theme:** Every agent output can carry a machine-checked certificate.

### Problem

When an agent says "this refactoring preserves behavior" or "these
constraints are satisfiable," there is no way to distinguish confident
correctness from hallucination. The human (or downstream agent) must
trust or re-verify.

### Solution

A `ProofCertificate` data structure that bundles:
- The claim (as a LogicBrain expression)
- The proof method (Z3 model, Lean proof term, or tautology check)
- A serializable verification artifact that any LogicBrain instance can
  re-check independently

```python
from logic_brain import certify, verify_certificate

# Agent produces a certificate
cert = certify("P -> Q, P |- Q")
assert cert.verified is True
assert cert.method == "z3_propositional"

# Downstream consumer re-verifies (zero trust)
assert verify_certificate(cert) is True

# Serialize for transport
json_str = cert.to_json()
cert2 = ProofCertificate.from_json(json_str)
assert verify_certificate(cert2) is True
```

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| `ProofCertificate` dataclass with JSON serialization | Cryptographic signing (future) |
| `certify()` top-level function wrapping existing verifiers | Network transport / API server |
| `verify_certificate()` for independent re-checking | Certificate revocation |
| Certificates for propositional, FOL, and Z3Session results | Lean proof term extraction (needs Lean 4 API work) |
| Metamorphic tests: `certify(expr)` then `verify_certificate` always agrees | |

### Deliverables

- [ ] `logic_brain/certificate.py` — `ProofCertificate`, `certify()`, `verify_certificate()`
- [ ] JSON schema for certificate format (versioned)
- [ ] 15+ tests including MR tests (serialize/deserialize invariance)
- [ ] `examples/proof_carrying_actions.py`
- [ ] Ledger entries for new MR tests

### Why This Helps the Agent

The agent can **prove it isn't hallucinating** on verifiable claims.
Downstream consumers (humans, other agents, CI pipelines) get
zero-trust verification without re-running the full reasoning chain.

---

## v0.4 — Reasoning Contracts

**Theme:** Pre-conditions and post-conditions on agent reasoning steps,
checked deterministically.

### Problem

An agent performing multi-step reasoning (e.g., "simplify this expression,
then substitute, then verify") has no way to ensure each step's
assumptions are met. Step 3 might silently depend on something Step 1
invalidated. In software engineering this is solved by contracts
(preconditions, postconditions, invariants). Agents need the same.

### Solution

A `ReasoningContract` that wraps a callable reasoning step with:
- **Requires:** Z3 constraints that must hold before execution
- **Ensures:** Z3 constraints that must hold after execution
- **Invariant:** constraints preserved across the step

```python
from logic_brain import ReasoningContract, Z3Session

session = Z3Session()
session.declare("x", "Int")
session.declare("y", "Int")

contract = ReasoningContract(
    requires=["x > 0", "y > 0"],
    ensures=["x + y > 0"],
    invariant=["x * y >= 0"],
)

# Check whether the contract's ensures follows from its requires
result = contract.verify(session)
assert result.holds is True
assert result.proof_certificate is not None  # v0.3 integration

# Runtime enforcement during agent execution
with contract.enforce(session) as ctx:
    session.assert_constraint("x == 5")
    session.assert_constraint("y == 3")
    # on exit: postconditions and invariants are checked
# raises ContractViolation if ensures/invariant fails
```

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| `ReasoningContract` with requires/ensures/invariant | Temporal contracts (sequence of steps) — that's v0.6 |
| Static verification (prove ensures from requires) | Automatic contract inference |
| Runtime enforcement via context manager | Performance optimization of Z3 calls |
| Integration with `ProofCertificate` from v0.3 | Lean-backed contract verification |
| Contract composition (contract A's ensures satisfies contract B's requires) | |

### Deliverables

- [ ] `logic_brain/contracts.py` — `ReasoningContract`, `ContractViolation`
- [ ] Static verification: does `ensures` follow from `requires`?
- [ ] Runtime enforcement: context manager checks on exit
- [ ] Contract composition: chain contracts for multi-step reasoning
- [ ] 20+ tests including contract violation scenarios
- [ ] MR tests: adding redundant requires doesn't change ensures verification

### Why This Helps the Agent

The agent can **decompose complex reasoning into verified steps**, where
each step's assumptions are machine-checked. This is the difference
between "I think this is right" and "each step provably follows from the
previous one." Contract violations surface exactly where reasoning breaks,
not 10 steps later.

---

## v0.5 — Self-Consistency Checker

**Theme:** Detect contradictions in the agent's accumulated beliefs.

### Problem

Over a long conversation or multi-file code analysis, an agent accumulates
beliefs: "variable X is always positive," "this function is pure," "these
two modules don't share state." These beliefs may contradict each other,
but the agent has no systematic way to detect this. Contradictions in the
belief set mean *anything* can be "proven" (ex falso quodlibet), which is
catastrophic for reasoning quality.

### Solution

A `BeliefSet` backed by Z3 incremental solving that:
- Accepts beliefs as logical assertions
- Continuously checks satisfiability (are all beliefs simultaneously possible?)
- On contradiction: identifies the minimal unsatisfiable core
- Supports hypothetical reasoning (push/pop for "what if" exploration)

```python
from logic_brain import BeliefSet

beliefs = BeliefSet()
beliefs.declare("x", "Int")
beliefs.declare("is_positive", "Bool")

beliefs.assert_belief("x > 0", label="from_type_analysis")
beliefs.assert_belief("is_positive == (x > 0)", label="definition")
beliefs.assert_belief("x < -5", label="from_error_log")

result = beliefs.check_consistency()
assert result.consistent is False
assert set(result.conflict_labels) == {"from_type_analysis", "from_error_log"}
# Agent action: one of these beliefs is wrong. Re-examine sources.

# Hypothetical reasoning
beliefs.push()
beliefs.retract("from_error_log")
assert beliefs.check_consistency().consistent is True
beliefs.pop()
```

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| `BeliefSet` with labeled assertions | Probabilistic beliefs / confidence scores |
| Consistency checking via Z3 | Natural language belief extraction |
| Minimal unsat-core for conflict identification | Belief revision strategies (which to drop) |
| Push/pop for hypothetical reasoning | Persistent belief storage across sessions |
| Belief retraction by label | |
| Integration with `ProofCertificate` (consistency proof as certificate) | |

### Deliverables

- [ ] `logic_brain/beliefs.py` — `BeliefSet`, `ConsistencyResult`
- [ ] Labeled assertions with unsat-core tracking
- [ ] `retract()` and `push()`/`pop()` for hypothetical reasoning
- [ ] 20+ tests including conflict detection and minimal core
- [ ] MR tests: adding a tautology never creates inconsistency
- [ ] `examples/self_consistency.py`

### Why This Helps the Agent

This is arguably the single most impactful tool for agent reasoning
quality. **An agent that can detect its own contradictions can
self-correct before producing wrong output.** The unsat-core tells the
agent exactly which beliefs conflict, turning a vague "something is
wrong" into a precise "belief A from source X contradicts belief B from
source Y."

---

## v0.6 — Policy-Guided Search

**Theme:** Formal policies that prune the agent's action space.

### Problem

An agent choosing between N possible actions (which file to edit, which
refactoring to apply, which test to write) currently uses heuristics and
pattern matching. It has no way to express or enforce hard constraints like
"never introduce a circular dependency," "maintain backward compatibility,"
or "every public function must have a docstring." These are policies — they
constrain the search space, and violations should be caught *before* the
action, not after.

### Solution

A `PolicyEngine` that:
- Accepts policies as logical formulas over a declared action vocabulary
- Given a proposed action (as a set of assertions), checks whether the
  action violates any policy
- Returns which policies would be violated and why
- Supports policy composition and priority

```python
from logic_brain import PolicyEngine

engine = PolicyEngine()

# Declare the vocabulary
engine.declare("adds_dependency", "Bool")
engine.declare("target_is_public_api", "Bool")
engine.declare("has_tests", "Bool")
engine.declare("breaking_change", "Bool")

# Define policies
engine.add_policy(
    name="test_coverage",
    rule="target_is_public_api AND NOT has_tests -> VIOLATION",
    severity="error",
)
engine.add_policy(
    name="no_breaking_changes",
    rule="breaking_change AND target_is_public_api -> VIOLATION",
    severity="error",
)
engine.add_policy(
    name="dependency_review",
    rule="adds_dependency -> REVIEW_REQUIRED",
    severity="warning",
)

# Agent proposes an action
result = engine.check_action({
    "target_is_public_api": True,
    "has_tests": False,
    "breaking_change": False,
    "adds_dependency": False,
})

assert result.violations == [("test_coverage", "error")]
# Agent action: write tests before proceeding.
```

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| `PolicyEngine` with named, typed policies | Policy learning / inference from codebase |
| Action checking against policy set | Integration with specific CI systems |
| Violation reporting with policy name and severity | Natural language policy definition |
| Policy composition (AND/OR over policies) | Runtime policy enforcement (blocking actions) |
| Serializable policy sets (JSON) | |
| Integration with `ReasoningContract` (policies as contract requires) | |

### Deliverables

- [ ] `logic_brain/policy.py` — `PolicyEngine`, `Policy`, `PolicyCheckResult`
- [ ] Policy definition DSL (reuse LogicBrain parser where possible)
- [ ] Action checking with violation reporting
- [ ] JSON serialization for policy sets
- [ ] 20+ tests including multi-policy interaction
- [ ] MR tests: removing a policy never adds violations
- [ ] `examples/policy_guided_search.py`

### Why This Helps the Agent

Policies turn implicit coding standards into **formally checkable
constraints**. The agent can pre-filter its action space: "Of the 5
refactorings I'm considering, only 3 satisfy all policies." This is
cheaper and more reliable than generating an action, applying it, running
CI, and discovering the violation after the fact.

---

## v0.7 — Compositional Proof Orchestrator

**Theme:** Decompose complex claims into sub-claims, verify independently,
compose results.

### Problem

Real-world verification tasks are rarely atomic. "This refactoring is
correct" decomposes into: (1) the type signatures are preserved, (2) the
behavior on known inputs is preserved, (3) no new exceptions are possible.
Currently the agent must manually decompose, verify each piece, and
mentally track which pieces are done. This doesn't scale and is error-prone.

### Solution

A `ProofOrchestrator` that:
- Accepts a top-level claim and its decomposition into sub-claims
- Verifies sub-claims independently (potentially in parallel)
- Tracks a proof tree: which sub-claims are verified, pending, or failed
- Composes sub-proofs: if the decomposition is valid AND all sub-claims
  are proven, the top-level claim gets a certificate

```python
from logic_brain import ProofOrchestrator

orch = ProofOrchestrator()

# Define the top-level claim
top = orch.claim("refactoring_correct")

# Decompose into sub-claims
sub1 = top.sub_claim("types_preserved")
sub2 = top.sub_claim("behavior_preserved")
sub3 = top.sub_claim("no_new_exceptions")

# Define how sub-claims compose into the top claim
top.set_composition("types_preserved AND behavior_preserved AND no_new_exceptions")

# Verify sub-claims (agent or LogicBrain does this)
sub1.verify_with("P -> P")  # trivial example
sub2.verify_with("(A -> B) AND A |- B")
sub3.verify_with("NOT (C AND NOT C)")

# Check if the top-level claim is now proven
status = orch.status()
assert status["refactoring_correct"].verified is True
assert status["refactoring_correct"].certificate is not None  # composed certificate
```

### Scope

| In Scope | Out of Scope |
|----------|-------------|
| `ProofOrchestrator` with claim/sub-claim tree | Automatic claim decomposition (agent's job) |
| Composition rules (how sub-proofs combine) | Parallel verification execution (use async externally) |
| Proof tree status tracking | Visualization / UI |
| Composed certificates from v0.3 | Lean-backed composition (future) |
| Incomplete proof tracking (which sub-claims remain) | |

### Deliverables

- [ ] `logic_brain/orchestrator.py` — `ProofOrchestrator`, `Claim`, `ProofTree`
- [ ] Claim decomposition and composition rules
- [ ] Proof tree status tracking
- [ ] Certificate composition (v0.3 integration)
- [ ] 20+ tests including partial proof trees
- [ ] MR tests: verifying a sub-claim never invalidates sibling sub-claims
- [ ] `examples/compositional_proof.py`

### Why This Helps the Agent

This is the capstone: **structured reasoning at scale.** The agent can
take a complex claim, decompose it into independently verifiable pieces,
and track progress through a proof tree. Failed sub-claims tell the agent
exactly where its reasoning breaks down. Successful composition gives a
certificate for the whole claim that no single verification could provide.

---

## Cross-Cutting Concerns

### Dependency Chain

Each version builds on the previous:

```
v0.3 ProofCertificate
 └── v0.4 ReasoningContract (uses certificates for contract proofs)
      └── v0.5 BeliefSet (contracts on belief consistency)
           └── v0.6 PolicyEngine (policies as belief constraints)
                └── v0.7 ProofOrchestrator (composes certificates from all layers)
```

### Versioning & Stability

All new modules enter as **Tier 2 (Provisional)** per `STABILITY.md`.
Promotion to Tier 1 (Stable) requires:
- At least one minor version of real agent usage
- No breaking API changes needed
- Metamorphic test coverage

### Testing Strategy

Each version adds:
- Unit tests (15–25 per module)
- Metamorphic relation tests (3–5 per module, registered in ledger)
- Integration test with previous version's API
- Example script in `examples/`

Target: maintain 85%+ coverage throughout.

### Logic Extensions Integration

The modal/temporal/many-valued logic extensions from
`docs/logic_extensions_assessment.md` are **orthogonal** to this roadmap.
They extend the *logic capabilities*; this roadmap extends the *agent
tooling*. They can be interleaved but are not dependencies.

### Risk Analysis

| Risk | Impact | Mitigation |
|------|--------|-----------|
| Z3 performance with large belief sets | v0.5 slowdown | Incremental solving, belief set size limits |
| Certificate format changes between versions | Breaking serialization | Versioned JSON schema from v0.3 |
| Policy DSL complexity creep | Usability | Reuse existing parser, keep it propositional |
| Orchestrator composability edge cases | Incorrect proof composition | Conservative composition rules, explicit soundness tests |
| Scope creep within each version | Delayed delivery | Strict non-scope enforcement, one issue per commit |

---

## KPIs

| Version | Tests Added | Coverage Target | Key Metric |
|---------|-------------|-----------------|------------|
| v0.3 | 15+ | 85% | Certificates survive serialize/deserialize roundtrip |
| v0.4 | 20+ | 85% | Static contract verification matches runtime enforcement |
| v0.5 | 20+ | 85% | Contradiction detection with minimal unsat-core |
| v0.6 | 20+ | 85% | Policy violations caught before action execution |
| v0.7 | 20+ | 87% | Composed certificates are independently re-verifiable |

---

## Summary

This roadmap transforms LogicBrain from a **verification library** into a
**deterministic reasoning toolkit for AI agents**. The progression is:

1. **v0.3** — Prove your outputs are correct (certificates)
2. **v0.4** — Prove each reasoning step is sound (contracts)
3. **v0.5** — Prove your beliefs are consistent (self-consistency)
4. **v0.6** — Prove your actions satisfy constraints (policies)
5. **v0.7** — Prove complex claims by decomposition (orchestration)

Each tool addresses a real failure mode of current AI agents:
hallucination (v0.3), broken reasoning chains (v0.4), accumulated
contradictions (v0.5), policy violations (v0.6), and inability to tackle
complex multi-part verification (v0.7).

The agent that has all five is not just a code generator with a spell
checker. It is a reasoning system with **formal guarantees about its own
output** — and that is the foundation on which trustworthy AI is built.
