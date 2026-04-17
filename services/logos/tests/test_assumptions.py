"""Tests for assumption state management (Issue #33)."""

from __future__ import annotations

import pytest

from logos import AssumptionKind, AssumptionSet, AssumptionStatus, CheckResult


def test_add_assumption_creates_active_entry() -> None:
    assumptions = AssumptionSet()
    entry = assumptions.add(
        assumption_id="a1",
        statement="x > 0",
        kind=AssumptionKind.ASSUMPTION,
        source="unit-test",
    )

    assert entry.status is AssumptionStatus.ACTIVE
    assert assumptions.get("a1") == entry


def test_duplicate_assumption_id_rejected() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.FACT, "test")

    with pytest.raises(ValueError, match="already exists"):
        assumptions.add("a1", "x < 10", AssumptionKind.HYPOTHESIS, "test")


def test_lifecycle_transitions_are_enforced() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.FACT, "test")

    expired = assumptions.expire("a1")
    assert expired.status is AssumptionStatus.EXPIRED

    activated = assumptions.activate("a1")
    assert activated.status is AssumptionStatus.ACTIVE


def test_invalid_lifecycle_transition_rejected() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.FACT, "test")

    with pytest.raises(ValueError, match="Only expired assumptions can be activated"):
        assumptions.activate("a1")


def test_retraction_is_idempotent() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "test")

    first = assumptions.retract("a1")
    second = assumptions.retract("a1")

    assert first.status is AssumptionStatus.RETRACTED
    assert second.status is AssumptionStatus.RETRACTED


def test_retracted_assumption_cannot_transition() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "test")
    assumptions.retract("a1")

    with pytest.raises(ValueError, match="cannot change lifecycle state"):
        assumptions.expire("a1")


def test_active_entries_and_payload_only_include_active_items() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "test")
    assumptions.add("a2", "x < 10", AssumptionKind.ASSUMPTION, "test")
    assumptions.expire("a2")

    active = assumptions.active_entries()
    payload = assumptions.belief_payload()

    assert [entry.assumption_id for entry in active] == ["a1"]
    assert payload == [{"label": "a1", "assertion": "x > 0"}]


def test_snapshot_roundtrip_preserves_semantics() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.FACT, "sensor")
    assumptions.add("a2", "x < 0", AssumptionKind.HYPOTHESIS, "agent")
    assumptions.expire("a2")

    restored = AssumptionSet.from_json(assumptions.to_json())

    assert restored.to_dict() == assumptions.to_dict()


def test_reject_invalid_json_payload() -> None:
    with pytest.raises(ValueError, match="Invalid assumptions JSON"):
        AssumptionSet.from_json("{bad json")


def test_reject_unsupported_schema_version() -> None:
    payload = {
        "schema_version": "9.9",
        "assumptions": [],
    }

    with pytest.raises(ValueError, match="Unsupported assumption schema version"):
        AssumptionSet.from_dict(payload)


def test_consistency_hook_detects_contradiction() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "test")
    assumptions.add("a2", "x < 0", AssumptionKind.ASSUMPTION, "test")

    def checker(statements: list[str]) -> bool:
        return not ("x > 0" in statements and "x < 0" in statements)

    result = assumptions.check_consistency(checker)

    assert result.consistent is False
    assert result.active_statements == ["x > 0", "x < 0"]


def test_z3_consistency_detects_contradiction() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "test")
    assumptions.add("a2", "x < 0", AssumptionKind.ASSUMPTION, "test")

    result = assumptions.check_consistency_z3(variables={"x": "Int"})

    assert result.consistent is False
    assert result.solver_status == "unsat"
    assert result.reason is None


def test_z3_consistency_passes_for_compatible_assumptions() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "test")
    assumptions.add("a2", "x < 10", AssumptionKind.ASSUMPTION, "test")

    result = assumptions.check_consistency_z3(variables={"x": "Int"})

    assert result.consistent is True
    assert result.solver_status == "sat"
    assert result.reason is None


def test_z3_consistency_with_auto_declared_variables() -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x > 0", AssumptionKind.ASSUMPTION, "test")
    assumptions.add("a2", "x < 0", AssumptionKind.ASSUMPTION, "test")

    result = assumptions.check_consistency_z3()

    assert result.consistent is False


def test_z3_consistency_empty_assumptions() -> None:
    assumptions = AssumptionSet()

    result = assumptions.check_consistency_z3()

    assert result.consistent is True
    assert result.solver_status == "sat"


def test_z3_consistency_detects_contradictions_across_all_assumption_kinds() -> None:
    assumptions = AssumptionSet()
    assumptions.add("fact", "x > 0", AssumptionKind.FACT, "test")
    assumptions.add("assumption", "x < 10", AssumptionKind.ASSUMPTION, "test")
    assumptions.add("hypothesis", "x <= 0", AssumptionKind.HYPOTHESIS, "test")

    result = assumptions.check_consistency_z3(variables={"x": "Int"})

    assert result.consistent is False
    assert result.solver_status == "unsat"


def test_z3_consistency_handles_large_assumption_sets() -> None:
    assumptions = AssumptionSet()
    for index in range(50):
        assumptions.add(
            assumption_id=f"lower-{index}",
            statement=f"x >= {-index}",
            kind=AssumptionKind.ASSUMPTION,
            source="test",
        )
    assumptions.add("upper", "x <= 25", AssumptionKind.FACT, "test")
    assumptions.add("conflict", "x > 25", AssumptionKind.HYPOTHESIS, "test")

    result = assumptions.check_consistency_z3(variables={"x": "Int"})

    assert result.consistent is False
    assert result.solver_status == "unsat"


def test_z3_consistency_surfaces_unknown_results(monkeypatch: pytest.MonkeyPatch) -> None:
    assumptions = AssumptionSet()
    assumptions.add("a1", "x * x == 2", AssumptionKind.HYPOTHESIS, "test")

    def fake_check(self: object) -> CheckResult:
        return CheckResult(status="unknown", satisfiable=None, reason="timeout")

    monkeypatch.setattr("logos.z3_session.Z3Session.check", fake_check)

    result = assumptions.check_consistency_z3(variables={"x": "Int"})

    assert result.consistent is False
    assert result.solver_status == "unknown"
    assert result.reason == "timeout"
