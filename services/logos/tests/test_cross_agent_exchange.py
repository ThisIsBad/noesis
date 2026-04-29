"""End-to-end tests for cross-agent proof exchange."""

from __future__ import annotations

import json
from collections.abc import Mapping

from logos import (
    ActionEnvelope,
    FederatedProofLedger,
    PostconditionCheck,
    ProofBundle,
    ProofCertificate,
    ProofOrchestrator,
    TrustPolicy,
    Z3Session,
    certify,
    execute_action_envelope,
    verify_proof_bundle,
)
from logos.proof_exchange import create_proof_bundle


def _certify_claim_adapter(payload: Mapping[str, object]) -> dict[str, object]:
    """Minimal adapter that certifies a claim and returns the result."""
    argument = payload.get("argument")
    if not isinstance(argument, str):
        return {"error": "argument must be a string"}
    cert = certify(argument)
    return {
        "verified": cert.verified,
        "status": "certified" if cert.verified else "failed",
        "certificate_json": cert.to_json(),
    }


def _build_agent_a_bundle() -> tuple[ProofBundle, dict[str, ProofCertificate]]:
    cert_prop = certify("P -> Q, P |- Q")

    session = Z3Session()
    session.declare("x", "Int")
    session.assert_constraint("x > 0")
    session.assert_constraint("x < 100")
    cert_z3 = certify(session)

    orchestrator = ProofOrchestrator()
    orchestrator.claim("root", "Composed claim")
    orchestrator.sub_claim("prop", "root", "Propositional proof")
    orchestrator.sub_claim("z3", "root", "Range proof")
    orchestrator.set_composition("root", "prop AND z3")
    orchestrator.attach_certificate("prop", cert_prop)
    orchestrator.attach_certificate("z3", cert_z3)
    orchestrator.propagate()

    cert_composed = orchestrator.get_claim("root").certificate
    assert cert_composed is not None

    bundle = create_proof_bundle(
        nodes={"prop": cert_prop, "z3": cert_z3, "composed": cert_composed},
        dependencies={"composed": ["prop", "z3"]},
        roots=["composed"],
    )
    return bundle, {"prop": cert_prop, "z3": cert_z3, "composed": cert_composed}


def test_cross_agent_exchange_happy_path_roundtrip_trust_and_action_execution() -> None:
    bundle, original_nodes = _build_agent_a_bundle()
    wire_json = bundle.to_json()

    received_bundle = ProofBundle.from_json(wire_json)
    for node_id, certificate in original_nodes.items():
        assert ProofCertificate.from_json(certificate.to_json()) == certificate
        assert received_bundle.nodes[node_id].certificate == certificate

    verification = verify_proof_bundle(received_bundle)

    assert verification.valid_bundle is True
    assert verification.complete is True
    assert verification.invalid_nodes == []

    ledger = FederatedProofLedger(TrustPolicy(domain_id="production", trusted_domains=("research-lab",)))
    record = ledger.evaluate_bundle(
        bundle_id="exchange-1",
        remote_domain_id="research-lab",
        bundle=received_bundle,
    )

    assert record.accepted is True
    assert record.verification.valid_bundle is True

    envelope = ActionEnvelope(
        intent="deploy verified claim",
        action="certify_claim",
        payload={"argument": "P -> Q, P |- Q"},
        preconditions=("proof",),
        cert_refs={"proof": received_bundle.nodes["prop"].certificate},
        expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
    )
    result = execute_action_envelope(
        envelope,
        adapters={"certify_claim": _certify_claim_adapter},
    )

    assert result.status == "completed"
    assert result.accepted is True
    assert result.proof_bundle is not None
    assert verify_proof_bundle(result.proof_bundle).valid_bundle is True


def test_cross_agent_exchange_detects_tampered_bundle_node() -> None:
    bundle, _ = _build_agent_a_bundle()
    tampered_payload = json.loads(bundle.to_json())
    nodes = tampered_payload["nodes"]
    assert isinstance(nodes, list)
    for node in nodes:
        if isinstance(node, dict) and node.get("node_id") == "prop":
            certificate = node.get("certificate")
            assert isinstance(certificate, dict)
            certificate["claim"] = "P -> Q, Q |- P"
            break

    tampered_bundle = ProofBundle.from_dict(tampered_payload)
    verification = verify_proof_bundle(tampered_bundle)

    assert verification.valid_bundle is False
    assert verification.complete is True
    assert verification.invalid_nodes == ["prop"]

    ledger = FederatedProofLedger(TrustPolicy(domain_id="production", trusted_domains=("research-lab",)))
    record = ledger.evaluate_bundle(
        bundle_id="exchange-2",
        remote_domain_id="research-lab",
        bundle=tampered_bundle,
    )

    assert record.accepted is False
    assert any(item["node_id"] == "prop" for item in record.diagnostics)


def test_cross_agent_exchange_rejects_untrusted_domain_despite_valid_bundle() -> None:
    bundle, _ = _build_agent_a_bundle()
    received_bundle = ProofBundle.from_json(bundle.to_json())
    verification = verify_proof_bundle(received_bundle)

    assert verification.valid_bundle is True
    assert verification.complete is True

    ledger = FederatedProofLedger(TrustPolicy(domain_id="production", trusted_domains=("research-lab",)))
    record = ledger.evaluate_bundle(
        bundle_id="exchange-3",
        remote_domain_id="untrusted-lab",
        bundle=received_bundle,
    )

    assert record.accepted is False
    assert record.verification.valid_bundle is True
    assert any(item["code"] == "untrusted_domain" for item in record.diagnostics)


def test_cross_agent_exchange_reports_missing_dependency_in_incomplete_bundle() -> None:
    bundle, certificates = _build_agent_a_bundle()
    incomplete_bundle = create_proof_bundle(
        nodes={"prop": certificates["prop"], "composed": certificates["composed"]},
        dependencies={"composed": ["prop", "z3"]},
        roots=["composed"],
    )
    wire_bundle = ProofBundle.from_json(incomplete_bundle.to_json())

    verification = verify_proof_bundle(wire_bundle)

    assert verification.valid_bundle is True
    assert verification.complete is False
    assert verification.missing_dependencies == ["composed->z3"]

    ledger = FederatedProofLedger(TrustPolicy(domain_id="production", trusted_domains=("research-lab",)))
    record = ledger.evaluate_bundle(
        bundle_id="exchange-4",
        remote_domain_id="research-lab",
        bundle=wire_bundle,
    )

    assert record.accepted is False
    assert any(item["code"] == "missing_dependency" for item in record.diagnostics)
