"""Tests for the compositional proof orchestrator."""

from __future__ import annotations

import pytest

from logos import ProofOrchestrator, certify, verify_certificate
from logos.orchestrator import ClaimStatus


def _basic_tree() -> ProofOrchestrator:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")
    orchestrator.sub_claim("a", "root", "A")
    orchestrator.sub_claim("b", "root", "B")
    return orchestrator


def test_claim_creates_root_claim() -> None:
    orchestrator = ProofOrchestrator()

    claim = orchestrator.claim("root", "Main claim")
    snapshot = orchestrator.status()

    assert claim.claim_id == "root"
    assert claim.status is ClaimStatus.PENDING
    assert snapshot.total_claims == 1
    assert snapshot.pending == 1


def test_claim_rejects_second_root() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")

    with pytest.raises(ValueError, match="Root claim already exists"):
        orchestrator.claim("other", "Other claim")


def test_sub_claim_adds_child_to_existing_parent() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")

    child = orchestrator.sub_claim("leaf", "root", "Leaf claim")

    assert child.parent_id == "root"
    assert orchestrator.get_claim("root").sub_claim_ids == ["leaf"]


def test_duplicate_claim_ids_are_rejected() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")

    with pytest.raises(ValueError, match="already exists"):
        orchestrator.sub_claim("root", "root", "Duplicate")


def test_empty_claim_id_is_rejected() -> None:
    orchestrator = ProofOrchestrator()

    with pytest.raises(ValueError, match="claim_id"):
        orchestrator.claim("", "Main claim")


def test_get_claim_returns_existing_claim() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")

    claim = orchestrator.get_claim("root")

    assert claim.description == "Main claim"


def test_get_claim_rejects_unknown_claim() -> None:
    orchestrator = ProofOrchestrator()

    with pytest.raises(ValueError, match="Unknown claim"):
        orchestrator.get_claim("missing")


def test_verify_leaf_marks_valid_leaf_verified() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")
    orchestrator.sub_claim("leaf", "root", "Leaf claim")

    cert = orchestrator.verify_leaf("leaf", "P -> Q, P |- Q")

    assert cert.verified is True
    assert orchestrator.get_claim("leaf").status is ClaimStatus.VERIFIED


def test_verify_leaf_marks_invalid_leaf_failed() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")
    orchestrator.sub_claim("leaf", "root", "Leaf claim")

    cert = orchestrator.verify_leaf("leaf", "P -> Q, Q |- P")

    assert cert.verified is False
    assert orchestrator.get_claim("leaf").status is ClaimStatus.FAILED


def test_attach_certificate_sets_leaf_status() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")
    orchestrator.sub_claim("leaf", "root", "Leaf claim")

    orchestrator.attach_certificate("leaf", certify("P -> Q, P |- Q"))

    assert orchestrator.get_claim("leaf").status is ClaimStatus.VERIFIED


def test_mark_failed_marks_claim_failed() -> None:
    orchestrator = _basic_tree()

    orchestrator.mark_failed("a", "test failure")

    claim = orchestrator.get_claim("a")
    assert claim.status is ClaimStatus.FAILED
    assert claim.failure_reason == "test failure"


def test_propagate_and_rule_verifies_parent_when_all_children_verified() -> None:
    orchestrator = _basic_tree()
    orchestrator.set_composition("root", "a AND b")
    orchestrator.verify_leaf("a", "P |- P")
    orchestrator.verify_leaf("b", "Q |- Q")

    orchestrator.propagate()

    root = orchestrator.get_claim("root")
    assert root.status is ClaimStatus.VERIFIED
    assert root.certificate is not None
    assert verify_certificate(root.certificate) is True


def test_propagate_or_rule_verifies_parent_when_all_referenced_children_verified() -> None:
    orchestrator = _basic_tree()
    orchestrator.set_composition("root", "a OR b")
    orchestrator.verify_leaf("a", "P |- P")
    orchestrator.verify_leaf("b", "Q |- Q")

    orchestrator.propagate()

    assert orchestrator.get_claim("root").status is ClaimStatus.VERIFIED


def test_propagate_marks_parent_failed_when_and_rule_cannot_be_satisfied() -> None:
    orchestrator = _basic_tree()
    orchestrator.set_composition("root", "a AND b")
    orchestrator.verify_leaf("a", "P |- P")
    orchestrator.verify_leaf("b", "P -> Q, Q |- P")

    orchestrator.propagate()

    assert orchestrator.get_claim("root").status is ClaimStatus.FAILED


def test_propagate_marks_parent_partial_when_some_children_pending() -> None:
    orchestrator = _basic_tree()
    orchestrator.set_composition("root", "a AND b")
    orchestrator.verify_leaf("a", "P |- P")

    orchestrator.propagate()

    assert orchestrator.get_claim("root").status is ClaimStatus.PARTIAL


def test_orchestrator_json_roundtrip_preserves_tree() -> None:
    orchestrator = _basic_tree()
    orchestrator.set_composition("root", "a AND b")
    orchestrator.verify_leaf("a", "P |- P")
    orchestrator.verify_leaf("b", "Q |- Q")
    orchestrator.propagate()

    restored = ProofOrchestrator.from_json(orchestrator.to_json())

    assert restored.to_dict() == orchestrator.to_dict()
    assert restored.status().is_complete is True


def test_orchestrator_dict_roundtrip_preserves_empty_tree() -> None:
    orchestrator = ProofOrchestrator()

    restored = ProofOrchestrator.from_dict(orchestrator.to_dict())

    assert restored.to_dict() == orchestrator.to_dict()
    assert restored.status().total_claims == 0


def test_composed_certificate_survives_roundtrip_and_reverification() -> None:
    orchestrator = _basic_tree()
    orchestrator.set_composition("root", "a AND b")
    orchestrator.verify_leaf("a", "P |- P")
    orchestrator.verify_leaf("b", "Q |- Q")
    orchestrator.propagate()

    cert = orchestrator.get_claim("root").certificate
    assert cert is not None
    restored = type(cert).from_json(cert.to_json())

    assert verify_certificate(restored) is True


def test_verify_leaf_on_parent_claim_fails() -> None:
    orchestrator = _basic_tree()

    with pytest.raises(ValueError, match="not a leaf claim"):
        orchestrator.verify_leaf("root", "P |- P")


def test_propagation_without_composition_rule_keeps_parent_partial_after_progress() -> None:
    orchestrator = _basic_tree()
    orchestrator.verify_leaf("a", "P |- P")

    orchestrator.propagate()

    assert orchestrator.get_claim("root").status is ClaimStatus.PARTIAL


def test_orchestrator_supports_arbitrary_depth_trees() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")
    orchestrator.sub_claim("mid", "root", "Intermediate")
    orchestrator.sub_claim("leaf", "mid", "Leaf")
    orchestrator.set_composition("mid", "leaf")
    orchestrator.set_composition("root", "mid")
    orchestrator.verify_leaf("leaf", "P |- P")

    orchestrator.propagate()

    assert orchestrator.status().is_complete is True


def test_set_composition_rejects_unknown_subclaims() -> None:
    orchestrator = _basic_tree()

    with pytest.raises(ValueError, match="unknown sub-claims"):
        orchestrator.set_composition("root", "a AND missing")


def test_set_composition_rejects_not_operator() -> None:
    orchestrator = _basic_tree()

    with pytest.raises(ValueError, match="do not support NOT"):
        orchestrator.set_composition("root", "NOT a")


def test_pending_claims_returns_only_pending_nodes() -> None:
    orchestrator = _basic_tree()
    orchestrator.verify_leaf("a", "P |- P")

    pending_ids = tuple(claim.claim_id for claim in orchestrator.pending_claims())

    assert pending_ids == ("b", "root")
