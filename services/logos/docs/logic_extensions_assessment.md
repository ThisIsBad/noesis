# Optional Logic Extensions Assessment

This document evaluates optional roadmap candidates and proposes an implementation order that keeps LogicBrain deterministic and maintainable.

## Summary Recommendation

1. Modal logic first (best cost/benefit, close to existing parser/verifier shape)
2. Temporal logic second (higher complexity, but high practical value)
3. Many-valued logic last (largest API/semantics ripple)

## Feasibility Matrix

| Extension | Feasibility | Effort | Risk | Suggested Phase |
|---|---|---|---|---|
| Modal Logic (Box/Diamond) | High | Medium | Medium | Phase A |
| Temporal Logic (LTL/CTL) | Medium | High | High | Phase B |
| Many-valued Logic | Medium | High | Medium | Phase C |

## Modal Logic (Box / Diamond)

### Why first
- Reuses expression-tree architecture and parser techniques already present
- Can be scoped to finite Kripke models for deterministic verification
- Natural extension for agent reasoning about "necessarily" and "possibly"

### Design approach
- Add modal operators (`BOX`, `DIAMOND`) to a dedicated modal model module
- Implement finite-world Kripke frame encoding in Z3
- Start with `K` system core; keep optional axioms (`T`, `S4`, `S5`) configurable

### Milestones
1. Parser support and AST tests for modal syntax
2. Kripke model encoder + satisfiability checks
3. Rule/fallacy detection parity for common modal patterns
4. Benchmarks and examples

## Temporal Logic (LTL / CTL)

### Why second
- Strong practical value for system behavior and multi-step reasoning
- Verification can still be deterministic with bounded semantics
- Requires dedicated encodings that are more complex than modal logic

### Design approach
- Start with bounded LTL over finite traces (`X`, `F`, `G`, `U`)
- Represent traces explicitly as indexed states in Z3
- Consider CTL only after LTL baseline stabilizes

### Milestones
1. LTL AST + parser extensions
2. Bounded semantics encoder (time-indexed constraints)
3. Property test suite with generated traces
4. Optional CTL exploration doc and prototype

## Many-valued Logic

### Why last
- Introduces non-Boolean truth domains and operator semantics changes
- Affects verifier APIs and explanation formats more broadly
- Valuable, but less immediately aligned with current benchmark workflow

### Design approach
- Start with three-valued logic (Kleene) as a strict subset
- Define truth domain and connective tables explicitly
- Keep API opt-in (separate verifier/session class)

### Milestones
1. Truth-domain abstractions and connective tables
2. Dedicated verifier implementation (no mixed semantics in default verifier)
3. Compatibility layer for parser front-end
4. Benchmarks and docs

## Guardrails

- Keep each extension behind explicit modules/classes to avoid destabilizing current propositional and predicate APIs
- Preserve deterministic behavior and machine-readable diagnostics as non-negotiable requirements
- Add benchmarks before declaring each phase stable
