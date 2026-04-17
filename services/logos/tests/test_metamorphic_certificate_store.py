"""Metamorphic tests for certificate store proof memory."""

from __future__ import annotations

import pytest

from logos import CertificateStore, certify
from logos.models import LogicalExpression, Proposition


pytestmark = pytest.mark.metamorphic


def test_store_query_idempotence() -> None:
    """Storing the same certificate twice does not change query results."""
    store = CertificateStore()
    cert = certify("P -> Q, P |- Q")

    store.store(cert, tags={"domain": "budget"})
    first = store.query()
    store.store(cert, tags={"step": "1"})
    second = store.query()

    assert len(first) == len(second) == 1
    assert first[0].store_id == second[0].store_id
    assert second[0].tags == {"domain": "budget", "step": "1"}


def test_prune_monotonicity() -> None:
    """Pruning never increases the number of entries."""
    store = CertificateStore()
    first_id = store.store(certify("P -> Q, P |- Q"))
    store.store(certify("P -> Q, Q |- P"))
    store.invalidate(first_id, reason="test")

    before = store.stats().total
    store.prune(invalidated_only=True)
    after = store.stats().total

    assert after <= before


def test_invalidation_irreversibility() -> None:
    """Once invalidated, calling invalidate again is a no-op."""
    store = CertificateStore()
    cert = certify("P -> Q, P |- Q")
    store_id = store.store(cert)

    first = store.invalidate(store_id, reason="test")
    second = store.invalidate(store_id, reason="different reason")

    assert first.invalidated_at == second.invalidated_at
    assert first.invalidation_reason == second.invalidation_reason


def test_compact_never_loses_conclusions() -> None:
    """Compaction preserves entailment of all original propositional conclusions."""
    import z3

    from logos.parser import parse_argument
    from logos.verifier import PropositionalVerifier

    def conclusion(claim: str) -> Proposition | LogicalExpression:
        return parse_argument(claim).conclusion

    def entailed(remaining: list[str], target: str) -> bool:
        if not remaining:
            return False
        verifier = PropositionalVerifier()
        premise_exprs = [conclusion(claim) for claim in remaining]
        target_expr = conclusion(f"{target} |- {target}")
        atoms: set[str] = set()
        for premise in premise_exprs:
            verifier._collect_atoms_from_expr(premise, atoms)
        verifier._collect_atoms_from_expr(target_expr, atoms)
        z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}
        solver = z3.Solver()
        for premise in premise_exprs:
            solver.add(verifier._to_z3(premise, z3_vars))
        solver.add(z3.Not(verifier._to_z3(target_expr, z3_vars)))
        return bool(solver.check() == z3.unsat)

    store = CertificateStore()
    original = ["P |- P", "Q |- Q", "P & Q |- (P & Q)", "R |- R"]
    for claim in original:
        store.store(certify(claim))

    store.compact()
    remaining = [
        str(entry.certificate.claim)
        for entry in store.query(limit=20)
        if isinstance(entry.certificate.claim, str)
    ]

    for claim in original:
        assert entailed(remaining, claim.split("|-", maxsplit=1)[1].strip())


def test_compact_idempotence() -> None:
    """Compacting twice yields the same retained store as compacting once."""
    store = CertificateStore()
    for claim in ("P |- P", "Q |- Q", "P & Q |- (P & Q)", "R |- R"):
        store.store(certify(claim))

    first = store.compact()
    first_ids = tuple(entry.store_id for entry in store.query(include_invalidated=True, limit=20))
    second = store.compact()
    second_ids = tuple(entry.store_id for entry in store.query(include_invalidated=True, limit=20))

    assert first.verification_passed is True
    assert second.verification_passed is True
    assert first_ids == second_ids


def test_query_consistent_monotone_under_relaxation() -> None:
    """Removing a premise cannot decrease the number of consistent certificates."""
    store = CertificateStore()
    for claim in ("P |- P", "Q |- Q", "P & Q |- (P & Q)"):
        store.store(certify(claim))

    stricter = store.query_consistent(["P", "Q"])
    relaxed = store.query_consistent(["P"])

    assert len(relaxed.consistent) >= len(stricter.consistent)


def test_query_consistent_subset_of_query() -> None:
    """Consistency filtering can only eliminate certificates from a plain query."""
    store = CertificateStore()
    for claim in ("P |- P", "Q |- Q", "P & Q |- (P & Q)"):
        store.store(certify(claim))

    filtered_ids = {entry.store_id for entry in store.query_consistent(["P"], verified=True).consistent}
    queried_ids = {entry.store_id for entry in store.query(verified=True, limit=20)}

    assert filtered_ids <= queried_ids
