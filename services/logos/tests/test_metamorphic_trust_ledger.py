"""Metamorphic tests for federated trust-domain ledger."""

from __future__ import annotations

import pytest

from logos import FederatedProofLedger, TrustPolicy, create_proof_bundle, certify


pytestmark = pytest.mark.metamorphic


def test_mr_tl01_trusted_domain_order_does_not_change_acceptance() -> None:
    bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])
    first = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("a", "remote", "z")))
    second = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("z", "remote", "a")))

    first_record = first.evaluate_bundle(bundle_id="b1", remote_domain_id="remote", bundle=bundle)
    second_record = second.evaluate_bundle(bundle_id="b1", remote_domain_id="remote", bundle=bundle)

    assert first_record.accepted == second_record.accepted is True
    assert first.query_bundle("b1").usable == second.query_bundle("b1").usable is True
