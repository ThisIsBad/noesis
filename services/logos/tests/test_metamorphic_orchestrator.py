"""Metamorphic tests for proof orchestration and certification."""

from __future__ import annotations

import pytest

from logos import ProofOrchestrator, certify
from logos.orchestrator import ClaimStatus


pytestmark = pytest.mark.metamorphic


def test_mr_or01_verifying_subclaim_does_not_invalidate_siblings() -> None:
    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Main claim")
    orchestrator.sub_claim("a", "root", "A")
    orchestrator.sub_claim("b", "root", "B")

    before = orchestrator.get_claim("b").status
    orchestrator.verify_leaf("a", "P |- P")
    after = orchestrator.get_claim("b").status

    assert before is ClaimStatus.PENDING
    assert after is ClaimStatus.PENDING


def test_mr_c4_valid_argument_certification_always_sets_verified_true() -> None:
    cert_a = certify("P |- P")
    cert_b = certify("P -> Q, P |- Q")

    assert cert_a.verified is True
    assert cert_b.verified is True
