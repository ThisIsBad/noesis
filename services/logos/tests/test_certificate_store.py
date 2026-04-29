"""Tests for certificate store proof memory."""

from __future__ import annotations

import pytest

from logos import (
    CertificateStore,
    CompactionResult,
    ConsistencyFilterResult,
    RankedCertificate,
    RelevanceResult,
    ProofCertificate,
    StoreStats,
    StoredCertificate,
    certify,
)


def _valid_cert() -> ProofCertificate:
    return certify("P -> Q, P |- Q")


def _invalid_cert() -> ProofCertificate:
    return certify("P -> Q, Q |- P")


def _dict_claim_cert() -> ProofCertificate:
    return ProofCertificate(
        claim={"goal": "budget", "value": "<= 100"},
        method="z3_session",
        verified=True,
        timestamp="2026-03-21T00:00:00+00:00",
        verification_artifact={"status": "sat"},
        claim_type="z3_session",
    )


def _store_from_entries(*entries: StoredCertificate) -> CertificateStore:
    return CertificateStore.from_dict(
        {
            "schema_version": "1.0",
            "entries": [entry.to_dict() for entry in entries],
        }
    )


def _conclusion(claim: str) -> str:
    from logos.parser import parse_argument
    from logos.models import Connective, LogicalExpression, Proposition

    def expression_to_ascii(expr: Proposition | LogicalExpression) -> str:
        if isinstance(expr, Proposition):
            return expr.label
        if expr.connective is Connective.NOT:
            return f"~({expression_to_ascii(expr.left)})"
        if expr.right is None:
            raise AssertionError("Binary expression requires right operand")
        left = expression_to_ascii(expr.left)
        right = expression_to_ascii(expr.right)
        if expr.connective is Connective.AND:
            return f"({left} & {right})"
        if expr.connective is Connective.OR:
            return f"({left} | {right})"
        if expr.connective is Connective.IMPLIES:
            return f"({left} -> {right})"
        if expr.connective is Connective.IFF:
            return f"({left} <-> {right})"
        raise AssertionError("Unsupported connective")

    return expression_to_ascii(parse_argument(claim).conclusion)


def _entailed(remaining: list[str], target: str) -> bool:
    import z3

    from logos.parser import parse_argument
    from logos.verifier import PropositionalVerifier

    if not remaining:
        return False

    verifier = PropositionalVerifier()
    premise_exprs = [parse_argument(f"{claim} |- {claim}").conclusion for claim in remaining]
    target_expr = parse_argument(f"{target} |- {target}").conclusion
    atoms: set[str] = set()
    for premise in premise_exprs:
        verifier._collect_atoms_from_expr(premise, atoms)
    verifier._collect_atoms_from_expr(target_expr, atoms)
    z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}
    solver = z3.Solver()
    for premise in premise_exprs:
        solver.add(verifier._to_z3(premise, z3_vars))
    solver.add(z3.Not(verifier._to_z3(target_expr, z3_vars)))
    return solver.check() == z3.unsat


def test_store_is_idempotent_and_merges_tags() -> None:
    store = CertificateStore()
    cert = _valid_cert()

    first_id = store.store(cert, tags={"domain": "budget"})
    second_id = store.store(cert, tags={"step": "1"})

    assert first_id == second_id
    stored = store.get(first_id)
    assert stored is not None
    assert stored.tags == {"domain": "budget", "step": "1"}
    assert store.stats().total == 1


def test_get_returns_none_for_unknown_store_id() -> None:
    assert CertificateStore().get("missing") is None


def test_query_filters_by_method_verified_tags_and_invalidated_state() -> None:
    valid = StoredCertificate(
        store_id="a",
        certificate=_valid_cert(),
        tags={"domain": "budget", "env": "prod"},
        stored_at="2026-03-21T01:00:00+00:00",
    )
    invalid = StoredCertificate(
        store_id="b",
        certificate=_invalid_cert(),
        tags={"domain": "budget", "env": "dev"},
        stored_at="2026-03-21T02:00:00+00:00",
        invalidated_at="2026-03-21T03:00:00+00:00",
        invalidation_reason="superseded",
    )
    store = _store_from_entries(valid, invalid)

    assert [entry.store_id for entry in store.query(method="z3_propositional", verified=True)] == ["a"]
    assert [entry.store_id for entry in store.query(tags={"domain": "budget", "env": "prod"})] == ["a"]
    assert [entry.store_id for entry in store.query(include_invalidated=True, verified=False)] == ["b"]


def test_query_filters_by_claim_pattern_since_and_descending_order() -> None:
    older = StoredCertificate(
        store_id="older",
        certificate=_valid_cert(),
        tags={"domain": "logic"},
        stored_at="2026-03-21T01:00:00+00:00",
    )
    newer = StoredCertificate(
        store_id="newer",
        certificate=_dict_claim_cert(),
        tags={"domain": "budget"},
        stored_at="2026-03-21T02:00:00+00:00",
    )
    store = _store_from_entries(older, newer)

    assert [entry.store_id for entry in store.query(claim_pattern="budget", include_invalidated=True)] == ["newer"]
    assert [entry.store_id for entry in store.query(since="2026-03-21T01:30:00+00:00", include_invalidated=True)] == [
        "newer"
    ]
    assert [entry.store_id for entry in store.query(include_invalidated=True)] == ["newer", "older"]


def test_query_limit_zero_and_negative_limit_handling() -> None:
    store = CertificateStore()
    store.store(_valid_cert())

    assert store.query(limit=0) == []

    try:
        store.query(limit=-1)
    except ValueError as exc:
        assert "non-negative" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for negative limit")


def test_invalidate_is_irreversible_and_requires_existing_entry() -> None:
    store = CertificateStore()
    cert = _valid_cert()
    store_id = store.store(cert)

    first = store.invalidate(store_id, reason="retracted")
    second = store.invalidate(store_id, reason="ignored")

    assert first.invalidated_at is not None
    assert second.invalidated_at == first.invalidated_at
    assert second.invalidation_reason == "retracted"

    try:
        store.invalidate("missing", reason="x")
    except ValueError as exc:
        assert "Unknown certificate store id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError for missing store id")


def test_prune_removes_entries_and_supports_and_semantics() -> None:
    old_valid = StoredCertificate(
        store_id="old-valid",
        certificate=_valid_cert(),
        tags={},
        stored_at="2000-01-01T00:00:00+00:00",
    )
    old_invalid = StoredCertificate(
        store_id="old-invalid",
        certificate=_invalid_cert(),
        tags={},
        stored_at="2000-01-01T00:00:00+00:00",
        invalidated_at="2000-01-02T00:00:00+00:00",
        invalidation_reason="old",
    )
    recent_invalid = StoredCertificate(
        store_id="recent-invalid",
        certificate=_invalid_cert(),
        tags={},
        stored_at="2999-01-01T00:00:00+00:00",
        invalidated_at="2999-01-02T00:00:00+00:00",
        invalidation_reason="future",
    )
    store = _store_from_entries(old_valid, old_invalid, recent_invalid)

    assert store.prune(max_age_seconds=1.0, invalidated_only=True) == 1
    assert store.get("old-invalid") is None
    assert store.get("old-valid") is not None
    assert store.get("recent-invalid") is not None

    assert store.prune(invalidated_only=True) == 1
    assert store.get("recent-invalid") is None


def test_stats_counts_total_valid_invalidated_and_breakdowns() -> None:
    store = _store_from_entries(
        StoredCertificate("a", _valid_cert(), {}, "2026-03-21T01:00:00+00:00"),
        StoredCertificate(
            "b",
            _dict_claim_cert(),
            {},
            "2026-03-21T02:00:00+00:00",
            invalidated_at="2026-03-21T03:00:00+00:00",
            invalidation_reason="superseded",
        ),
    )

    stats = store.stats()

    assert stats.total == 2
    assert stats.valid == 1
    assert stats.invalidated == 1
    assert stats.by_claim_type == {"propositional": 1, "z3_session": 1}
    assert stats.by_method == {"z3_propositional": 1, "z3_session": 1}


def test_serialization_round_trip_for_stored_certificate_stats_and_store() -> None:
    cert = _valid_cert()
    entry = StoredCertificate(
        store_id="entry-1",
        certificate=cert,
        tags={"domain": "budget"},
        stored_at="2026-03-21T01:00:00+00:00",
    )
    restored_entry = StoredCertificate.from_dict(entry.to_dict())
    assert restored_entry == entry

    stats = StoreStats(
        total=1,
        valid=1,
        invalidated=0,
        by_claim_type={"propositional": 1},
        by_method={"z3_propositional": 1},
    )
    restored_stats = StoreStats.from_dict(stats.to_dict())
    assert restored_stats == stats

    store = CertificateStore()
    store.store(cert, tags={"domain": "budget"})
    restored_store = CertificateStore.from_json(store.to_json())
    assert restored_store.to_dict() == store.to_dict()


def test_clear_empties_store() -> None:
    store = CertificateStore()
    store.store(_valid_cert())
    store.clear()
    assert store.stats().total == 0


def test_invalid_inputs_raise_descriptive_errors() -> None:
    try:
        StoredCertificate.from_dict({})
    except ValueError as exc:
        assert "store_id" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected StoredCertificate.from_dict to fail")

    try:
        StoreStats.from_dict({"total": 1, "valid": 1, "invalidated": 0, "by_claim_type": {"a": "x"}, "by_method": {}})
    except ValueError as exc:
        assert "integers" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected StoreStats.from_dict to fail")

    try:
        CertificateStore.from_dict({"schema_version": "2.0", "entries": []})
    except ValueError as exc:
        assert "Unsupported certificate store schema version" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected CertificateStore.from_dict to fail")

    try:
        CertificateStore().store(_valid_cert(), tags={"domain": 1})  # type: ignore[dict-item]
    except ValueError as exc:
        assert "dict[str, str]" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("Expected invalid tags to fail")


def test_compact_removes_redundant_certificates() -> None:
    store = CertificateStore()
    store.store(certify("P |- P"))
    store.store(certify("Q |- Q"))
    store.store(certify("P & Q |- (P & Q)"))
    store.store(certify("R |- R"))
    store.store(certify("P | R |- (P | R)"))

    result = store.compact()

    assert isinstance(result, CompactionResult)
    assert result.removed_count > 0
    assert result.verification_passed is True
    remaining = [
        str(entry.certificate.claim) for entry in store.query(limit=20) if isinstance(entry.certificate.claim, str)
    ]
    assert len(remaining) < 5
    for original in ["P |- P", "Q |- Q", "P & Q |- (P & Q)", "R |- R", "P | R |- (P | R)"]:
        assert _entailed([_conclusion(claim) for claim in remaining], _conclusion(original))


def test_compact_preserves_non_propositional() -> None:
    store = CertificateStore()
    propositional_id = store.store(certify("P |- P"))
    z3_id = store.store(_dict_claim_cert())

    result = store.compact()

    assert result.verification_passed is True
    assert store.get(z3_id) is not None
    assert store.get(propositional_id) is not None


def test_compact_empty_store() -> None:
    result = CertificateStore().compact()

    assert result == CompactionResult(removed_count=0, retained_count=0, removed_ids=(), verification_passed=True)


def test_compact_single_certificate() -> None:
    store = CertificateStore()
    store.store(certify("P |- P"))

    result = store.compact()

    assert result.removed_count == 0
    assert result.retained_count == 1
    assert result.removed_ids == ()
    assert result.verification_passed is True


def test_compact_skips_invalidated() -> None:
    store = CertificateStore()
    active_id = store.store(certify("P & Q |- (P & Q)"))
    invalidated_id = store.store(certify("P |- P"))
    store.invalidate(invalidated_id, reason="already retracted")

    result = store.compact()

    assert result.verification_passed is True
    assert invalidated_id not in result.removed_ids
    assert store.get(invalidated_id) is not None
    assert store.get(active_id) is not None


def test_compact_skips_unverified_certificates() -> None:
    store = CertificateStore()
    unverified_id = store.store(_invalid_cert())
    store.store(certify("P |- P"))
    store.store(certify("P & Q |- (P & Q)"))

    result = store.compact()

    assert result.verification_passed is True
    assert store.get(unverified_id) is not None


def test_query_consistent_filters_inconsistent() -> None:
    store = CertificateStore()
    consistent_id = store.store(certify("P |- P"), tags={"domain": "logic"})
    inconsistent_id = store.store(certify("~P |- ~P"), tags={"domain": "logic"})

    result = store.query_consistent(["P"], verified=True, tags={"domain": "logic"})

    assert isinstance(result, ConsistencyFilterResult)
    assert [entry.store_id for entry in result.consistent] == [consistent_id]
    assert inconsistent_id not in [entry.store_id for entry in result.consistent]
    assert result.inconsistent_count == 1
    assert result.premises_contradictory is False


def test_query_consistent_contradictory_premises() -> None:
    store = CertificateStore()
    store.store(certify("P |- P"))

    result = store.query_consistent(["P", "~P"])

    assert result.consistent == []
    assert result.inconsistent_count == 0
    assert result.premises_contradictory is True


def test_query_consistent_empty_premises() -> None:
    store = CertificateStore()
    first_id = store.store(certify("P |- P"))
    second_id = store.store(certify("Q |- Q"))
    store.store(_dict_claim_cert())

    result = store.query_consistent([])

    assert {entry.store_id for entry in result.consistent} == {first_id, second_id}
    assert len(result.consistent) == 2
    assert result.inconsistent_count == 0
    assert result.premises_contradictory is False


def test_query_consistent_excludes_non_propositional() -> None:
    store = CertificateStore()
    propositional_id = store.store(certify("P |- P"))
    store.store(_dict_claim_cert())

    result = store.query_consistent(["P"])

    assert [entry.store_id for entry in result.consistent] == [propositional_id]
    assert all(entry.certificate.claim_type == "propositional" for entry in result.consistent)


def test_query_consistent_respects_limit() -> None:
    store = CertificateStore()
    for claim in ("P |- P", "P & Q |- (P & Q)", "P | R |- (P | R)"):
        store.store(certify(claim))

    result = store.query_consistent(["P"], limit=2)

    assert len(result.consistent) == 2
    assert result.inconsistent_count == 0


def test_query_consistent_respects_tags() -> None:
    store = CertificateStore()
    wanted_id = store.store(certify("P |- P"), tags={"domain": "wanted"})
    store.store(certify("P & Q |- (P & Q)"), tags={"domain": "other"})

    result = store.query_consistent(["P"], tags={"domain": "wanted"})

    assert [entry.store_id for entry in result.consistent] == [wanted_id]
    assert result.inconsistent_count == 0


# --- query_ranked ---


def test_query_ranked_returns_relevance_result() -> None:
    store = CertificateStore()
    store.store(certify("P -> Q, P |- Q"))

    result = store.query_ranked("P Q")

    assert isinstance(result, RelevanceResult)
    assert result.total_candidates >= 1
    assert all(isinstance(r, RankedCertificate) for r in result.results)


def test_query_ranked_scores_are_between_zero_and_one() -> None:
    store = CertificateStore()
    store.store(certify("P -> Q, P |- Q"))
    store.store(certify("A -> B, A |- B"))

    result = store.query_ranked("P Q A B")

    for r in result.results:
        assert 0.0 < r.score <= 1.0


def test_query_ranked_sorts_by_descending_score() -> None:
    store = CertificateStore()
    store.store(certify("P |- P"))
    store.store(certify("P -> Q, P |- Q"))
    store.store(certify("A -> B, A |- B"))

    result = store.query_ranked("P Q")

    scores = [r.score for r in result.results]
    assert scores == sorted(scores, reverse=True)


def test_query_ranked_excludes_zero_score_entries() -> None:
    store = CertificateStore()
    store.store(certify("X -> Y, X |- Y"))

    result = store.query_ranked("completely unrelated tokens zzz")

    # X/Y tokens don't overlap with query tokens
    assert result.total_candidates == 0
    assert result.results == []


def test_query_ranked_respects_limit() -> None:
    store = CertificateStore()
    for claim in ("P |- P", "P & Q |- (P & Q)", "P | R |- (P | R)"):
        store.store(certify(claim))

    result = store.query_ranked("P Q R", limit=1)

    assert len(result.results) <= 1
    assert result.total_candidates >= 1


def test_query_ranked_rejects_empty_query() -> None:
    store = CertificateStore()

    with pytest.raises(ValueError, match="non-empty"):
        store.query_ranked("   ")


def test_query_ranked_rejects_negative_limit() -> None:
    store = CertificateStore()

    with pytest.raises(ValueError, match="non-negative"):
        store.query_ranked("P", limit=-1)


def test_query_ranked_respects_tags_filter() -> None:
    store = CertificateStore()
    store.store(certify("P |- P"), tags={"domain": "wanted"})
    store.store(certify("P & Q |- (P & Q)"), tags={"domain": "other"})

    result = store.query_ranked("P", tags={"domain": "wanted"})

    assert all(r.entry.tags.get("domain") == "wanted" for r in result.results)


def test_query_ranked_excludes_invalidated_by_default() -> None:
    store = CertificateStore()
    sid = store.store(certify("P |- P"))
    store.invalidate(sid, reason="retracted")

    result = store.query_ranked("P")

    assert result.total_candidates == 0
