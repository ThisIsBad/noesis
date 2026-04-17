"""Tests for federated trust-domain proof ledger."""

from __future__ import annotations

from logos import FederatedProofLedger, TrustPolicy, create_proof_bundle, certify


def test_acceptance_requires_explicit_trust_policy() -> None:
    bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])
    trusted = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("remote",)))
    untrusted = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("other",)))

    trusted_record = trusted.evaluate_bundle(bundle_id="b1", remote_domain_id="remote", bundle=bundle)
    untrusted_record = untrusted.evaluate_bundle(bundle_id="b1", remote_domain_id="remote", bundle=bundle)

    assert trusted_record.accepted is True
    assert untrusted_record.accepted is False
    assert untrusted_record.diagnostics[0]["code"] == "untrusted_domain"


def test_revoked_bundle_is_blocked_deterministically() -> None:
    bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])
    ledger = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("remote",)))
    ledger.evaluate_bundle(bundle_id="b1", remote_domain_id="remote", bundle=bundle)
    ledger.revoke_bundle("b1", revoked_at="2026-03-20T00:00:00+00:00", reason="domain_revoked")

    query = ledger.query_bundle("b1", as_of="2026-03-21T00:00:00+00:00")

    assert query.accepted is True
    assert query.usable is False
    assert "revoked" in query.reasons
    assert "revocation_recorded" in query.what_changed


def test_expired_bundle_is_blocked_deterministically() -> None:
    bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])
    ledger = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("remote",)))
    ledger.evaluate_bundle(
        bundle_id="b1",
        remote_domain_id="remote",
        bundle=bundle,
        expires_at="2026-03-20T00:00:00+00:00",
    )

    query = ledger.query_bundle("b1", as_of="2026-03-21T00:00:00+00:00")

    assert query.accepted is True
    assert query.usable is False
    assert "expired" in query.reasons
    assert "expiry_reached" in query.what_changed


def test_cross_domain_diagnostics_are_machine_readable() -> None:
    bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["missing_root"])
    ledger = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("remote",)))

    record = ledger.evaluate_bundle(bundle_id="b1", remote_domain_id="remote", bundle=bundle)

    assert record.accepted is False
    assert any(item["code"] == "invalid_root" for item in record.diagnostics)


def test_query_bundle_explains_acceptance_reason() -> None:
    bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])
    ledger = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("remote",)))
    ledger.evaluate_bundle(bundle_id="b1", remote_domain_id="remote", bundle=bundle)

    query = ledger.query_bundle("b1")

    assert query.accepted is True
    assert query.usable is True
    assert query.reasons == ("accepted_by_explicit_trust_policy",)
