# LogicBrain

[![CI](https://github.com/ThisIsBad/LogicBrain/actions/workflows/ci.yml/badge.svg)](https://github.com/ThisIsBad/LogicBrain/actions/workflows/ci.yml)

A deterministic reasoning toolkit backed by Z3 and Lean 4 -- formal verification, assumption management, counterfactual planning, policy enforcement, and proof certificates for AI agents.

## Quick Start

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

## Local Test Quickstart

```powershell
pip install -e ".[dev]"
pytest -q
```

## Usage

```python
from logos import verify, is_tautology, is_contradiction, are_equivalent

# Verify logical arguments
result = verify("P -> Q, P |- Q")
print(result.valid)  # True
print(result.rule)   # "Modus Ponens"

# Detect fallacies
result = verify("P -> Q, Q |- P")
print(result.valid)          # False
print(result.rule)           # "Affirming the Consequent (fallacy)"
print(result.counterexample) # {'P': False, 'Q': True}

# Check tautologies and contradictions
is_tautology("P | ~P")       # True (Law of Excluded Middle)
is_contradiction("P & ~P")   # True

# Check logical equivalence
are_equivalent("~(P & Q)", "~P | ~Q")  # True (De Morgan's Law)
are_equivalent("P -> Q", "~Q -> ~P")   # True (Contraposition)
```

## CLI

```powershell
python -m logos "P -> Q, P |- Q"
python -m logos "P -> Q, Q |- P" --explain
python -m logos "P -> Q, P |- Q" --json
```

## Syntax

| Symbol | Meaning | Alternatives |
|--------|---------|--------------|
| `->` | Implication | `=>` |
| `<->` | Biconditional | `<=>` |
| `&` | Conjunction (AND) | `^` |
| `\|` | Disjunction (OR) | |
| `~` | Negation (NOT) | `!` |
| `\|-` | Turnstile (therefore) | |
| `A-Z` | Atomic propositions | |
| `()` | Grouping | |

## Examples

```python
# Valid inference rules
verify("P -> Q, P |- Q")           # Modus Ponens
verify("P -> Q, ~Q |- ~P")         # Modus Tollens
verify("P -> Q, Q -> R |- P -> R") # Hypothetical Syllogism
verify("P | Q, ~P |- Q")           # Disjunctive Syllogism
verify("P, Q |- P & Q")            # Conjunction Introduction
verify("P & Q |- P")               # Conjunction Elimination
verify("P -> Q |- ~Q -> ~P")       # Contraposition

# Common fallacies (all return valid=False)
verify("P -> Q, Q |- P")           # Affirming the Consequent
verify("P -> Q, ~P |- ~Q")         # Denying the Antecedent
```

## For AI Agents

This library is designed to be called directly via Python execution. No MCP server or API wrapper needed. The package ships a `py.typed` marker (PEP 561) so downstream type checkers see the inline types.

```python
# Agent writes this code, executes it, reads the result
from logos import verify
result = verify("P -> Q, P |- Q")
# Agent sees: valid=True, rule="Modus Ponens"
# Agent can now use this information to verify its reasoning
```

For a complete copy-paste example see [`examples/agent_integration.py`](examples/agent_integration.py).

### Proof-Carrying Actions (v0.3)

You can attach machine-checkable certificates to reasoning outputs:

```python
from logos import ProofCertificate, certify, verify_certificate

cert = certify("P -> Q, P |- Q")
assert cert.verified is True
assert verify_certificate(cert) is True

cert_json = cert.to_json()
restored = ProofCertificate.from_json(cert_json)
assert verify_certificate(restored) is True
```

See [`examples/proof_carrying_actions.py`](examples/proof_carrying_actions.py) for an end-to-end workflow.

## First-Order Logic (Predicate Logic)

For predicate logic with quantifiers, use the `PredicateVerifier`:

```python
from logos import (
    PredicateVerifier, Variable, Constant, Predicate,
    QuantifiedExpression, Quantifier, PredicateExpression,
    PredicateConnective, FOLArgument
)

v = PredicateVerifier()

# "All humans are mortal. Socrates is human. Therefore, Socrates is mortal."
x = Variable("x")
socrates = Constant("socrates")

Human = lambda t: Predicate("Human", [t])
Mortal = lambda t: Predicate("Mortal", [t])

premise1 = QuantifiedExpression(
    Quantifier.FORALL, x,
    PredicateExpression(PredicateConnective.IMPLIES, Human(x), Mortal(x))
)
premise2 = Human(socrates)
conclusion = Mortal(socrates)

arg = FOLArgument(premises=[premise1, premise2], conclusion=conclusion)
result = v.verify(arg)
print(result.valid)  # True
```

## Lean 4 Interactive Proving

For tactic-by-tactic theorem proving with Lean 4:

```python
from logos import LeanSession, is_lean_available

if is_lean_available():
    session = LeanSession()
    session.start("theorem test : 1 + 1 = 2 := by")
    
    result = session.apply("rfl")
    print(result.success)      # True
    print(session.is_complete) # True
    print(session.proof)       # "theorem test : 1 + 1 = 2 := by\n  rfl"

    bad = session.apply("reflexivity")
    if not bad.success:
        print(bad.error_type)    # e.g. "unknown_tactic"
        print(bad.suggestions)   # structured recovery hints
```

Features:
- Tactic-by-tactic proof construction with immediate feedback
- Automatic rollback on failed tactics
- Undo support
- Goal state tracking
- Automatic Lean 4 detection via elan
- Structured diagnostics (`result.diagnostic`, `result.error_type`, `result.suggestions`)

## Z3 Incremental Solving

For incremental constraint solving with backtracking:

```python
from logos import Z3Session

session = Z3Session()
session.declare("x", "Int")
session.declare("y", "Int")

session.assert_constraint("x > 0")
session.assert_constraint("y > x")
session.assert_constraint("x + y < 100")

result = session.check()
print(result.satisfiable)  # True
print(result.model)        # {'x': 1, 'y': 2}

# Backtracking with push/pop
session.push()
session.assert_constraint("x > 50")
result = session.check()  # Still satisfiable

session.assert_constraint("y < 10")
result = session.check()  # Unsatisfiable (x > 50, y > x, y < 10)

if not result.satisfiable:
    print(result.error_type)   # "unsatisfiable"
    print(result.suggestions)  # conflicting constraints / next actions

session.pop()  # Remove last two constraints
result = session.check()  # Satisfiable again
```

Features:
- Variable declaration (Int, Real, Bool, BitVec)
- Incremental constraint assertion
- Push/pop for backtracking
- Model extraction for satisfiable results
- Unsat core extraction for debugging
- Structured diagnostics for unsat/unknown/parse failures

## Project Structure

```
logos/
├── __init__.py             # Public API (see STABILITY.md for tiers)
├── __main__.py             # Module entrypoint for `python -m logos`
├── py.typed                # PEP 561 marker
├── parser.py               # String-based parser ("P -> Q, P |- Q")
├── verifier.py             # Z3-backed propositional logic verifier
├── predicate.py            # Z3-backed predicate logic verifier
├── models.py               # Core propositional data types
├── predicate_models.py     # FOL data types
├── certificate.py          # Proof certificates (certify, verify, serialize)
├── certificate_store.py    # In-memory proof memory with query API
├── assumptions.py          # Typed epistemic state manager
├── counterfactual.py       # Z3-backed counterfactual branch planner
├── action_policy.py        # Pre-action policy enforcement with Z3
├── uncertainty.py          # Confidence calibration and escalation
├── belief_graph.py         # Causal belief graph with contradiction detection
├── goal_contract.py        # Machine-checkable goal contracts
├── orchestrator.py         # Compositional proof trees
├── execution_bus.py        # Proof-carrying action envelopes
├── proof_exchange.py       # Cross-agent proof bundles
├── recovery.py             # Deterministic recovery protocols
├── trust_ledger.py         # Federated trust-domain proof ledger
├── verified_runtime.py     # Closed-loop verified agent runtime
├── adversarial_harness.py  # Adversarial self-play harness
├── z3_session.py           # Incremental Z3 solving session
├── lean_session.py         # Lean 4 interactive session
├── diagnostics.py          # Structured error diagnostics
├── generator.py            # Logic problem generator
├── mcp_tools.py            # MCP tool handler implementations
├── mcp_server.py           # MCP stdio server
├── mcp_session_store.py    # MCP Z3/orchestrator session state (internal)
├── cli.py                  # CLI entrypoint
├── schema_utils.py         # Shared schema helpers (internal)
├── loader.py               # Benchmark loader (internal)
├── runner.py               # Benchmark runner (internal)
├── analyzer.py             # Error pattern analysis (internal)
├── evaluate.py             # LLM evaluation (internal)
├── external.py             # External benchmark adapters (internal)
└── lean_verifier.py        # Non-interactive Lean verification (internal)
examples/
├── agent_integration.py  # Full agent workflow demo (copy-paste ready)
├── quick_verify.py       # Minimal verification examples
├── interactive_sessions.py # LeanSession + Z3Session demo
└── logos_demo.ipynb  # Jupyter notebook demo
tools/                  # Benchmark generation & checking
docs/
├── api/                # Generated API reference (pdoc)
├── agi_roadmap_v2.md   # Primary AGI framing and acceptance criteria
└── logicbrain_development_roadmap.md # LogicBrain roadmap derived from AGI roadmap
tests/                  # Test suite (pytest)
```

## Running Tests

```powershell
pytest -q              # Run full suite (CI default)
pytest -v              # Verbose run
pytest tests/ -v       # Test-directory run
pytest -q -m metamorphic  # Metamorphic regression gate
```

## Running Benchmarks

```powershell
python -m logos.runner

# Generate fresh benchmark files
python tools/generate_exam.py --count 10
python tools/generate_hardmode.py --vars 8 --premises 8 --count 5 --depth 3
python tools/generate_escalation.py round2 --count 5

# Check result files
python tools/check_results.py exam
python tools/check_results.py hardmode hardmode_10v_10p
python tools/check_results.py escalation round2
python tools/check_stress_results.py

# Or provide explicit files
python tools/check_results.py --benchmarks results/hardmode_8v_8p.json --answers results/hardmode_8v_8p_answers.json

# Lean and FOL answer checkers
python tools/check_lean_results.py
python tools/check_fol_results.py
```

FOL checker schema expectations:
- Benchmark file contains `problems` with `id` and `expected_valid`.
- Answers file contains `answers` keyed by problem id, each with a `valid` boolean.

All benchmark tools live under `tools/`. Legacy root-level wrappers have been removed.

## Examples

```powershell
python examples/quick_verify.py
python examples/interactive_sessions.py
python examples/agent_integration.py   # Full agent workflow demo
python examples/proof_carrying_actions.py  # v0.3 proof-carrying demo
```

Notebook demo:
- `examples/logos_demo.ipynb`

### Agent Integration

See [`examples/agent_integration.py`](examples/agent_integration.py) for a
copy-paste-ready example showing how an AI coding agent can use LogicBrain:
verify arguments, generate fresh problems, explore constraints with Z3, read
structured diagnostics, and optionally build Lean 4 proofs.

## Agent Integration (MCP)

LogicBrain also ships an MCP server for Claude Code and other MCP-compatible
agents. Install the optional dependency, register the server, and the LogicBrain
reasoning tools will be available over stdio.

Install:

```powershell
pip install -e ".[mcp]"
```

Config (`.mcp.json`):

```json
{
  "mcpServers": {
    "logos": {
      "command": "python",
      "args": ["-m", "logos.mcp_server"],
      "cwd": "<project-root>"
    }
  }
}
```

Verify: start Claude Code in this repository; the LogicBrain tools should
appear automatically.

What an agent can do:
- `verify_argument` - verify arguments and return proof-oriented summaries
- `certify_claim` - create serializable proof certificates for claims
- `check_assumptions` - detect contradictory assumption sets via Z3
- `check_beliefs` - find contradictions in belief sets with explanations
- `counterfactual_branch` - classify feasible vs infeasible branches
- `z3_check` - run direct satisfiability checks with models and unsat cores
- `check_contract` - validate goal-contract preconditions against state constraints
- `check_policy` - evaluate boolean action policies with remediation hints
- `z3_session` - manage stateful incremental Z3 sessions over MCP
- `orchestrate_proof` - build and propagate compositional proof trees
- `proof_carrying_action` - enforce certified preconditions and checked postconditions across tool calls
- `certificate_store` - store, query, invalidate, and retrieve proof certificates

For the full setup and troubleshooting guide, see `docs/mcp_setup.md`.

Further documentation:
- **API reference:** `docs/api/logos.html` (regenerate: `python -m pdoc logos -o docs/api`)
- Metamorphic relation ledger: `docs/metamorphic_ledger.md`
- Primary AGI roadmap: `docs/agi_roadmap_v2.md`
- LogicBrain roadmap: `docs/logicbrain_development_roadmap.md`
- API stability: `STABILITY.md`
- Development process: `docs/development_process.md`
- Logic extensions assessment: `docs/logic_extensions_assessment.md`

## Releases

- Follow semantic versioning (`MAJOR.MINOR.PATCH`).
- Check `CHANGELOG.md` for release notes and upgrade context.
- Follow `docs/release_playbook.md` for the release checklist and smoke tests.
- GitHub releases are published at:
  - `https://github.com/ThisIsBad/LogicBrain/releases`

## License

See `LICENSE`.
