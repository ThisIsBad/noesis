"""Tests for the proof_carrying_action MCP handler."""

from __future__ import annotations

from logos import ProofBundle, certify, verify_proof_bundle
from logos.mcp_tools import proof_carrying_action


def test_proof_carrying_action_rejects_missing_precondition_certificates() -> None:
    result = proof_carrying_action(
        {
            "intent": "verify a claim",
            "action": "verify_argument",
            "payload": {"argument": "P |- P"},
            "preconditions": ["root-cert"],
        }
    )

    assert result["status"] == "rejected_preconditions"
    assert result["accepted"] is False
    assert result["diagnostics"][0]["code"] == "missing_precondition_certificate"


def test_proof_carrying_action_detects_postcondition_mismatch() -> None:
    result = proof_carrying_action(
        {
            "intent": "verify an intentionally invalid claim",
            "action": "verify_argument",
            "payload": {"argument": "P -> Q, Q |- P"},
            "expected_postconditions": [{"path": "valid", "equals": True}],
        }
    )

    assert result["status"] == "postcondition_mismatch"
    assert result["diagnostics"][0]["code"] == "postcondition_mismatch"
    assert result["diagnostics"][0]["path"] == "valid"


def test_proof_carrying_action_returns_trace_and_bundle_for_certified_action() -> None:
    precondition = certify("P |- P")
    result = proof_carrying_action(
        {
            "intent": "certify a downstream claim",
            "action": "certify_claim",
            "payload": {"argument": "P -> Q, P |- Q"},
            "preconditions": ["root-cert"],
            "cert_refs": {"root-cert": precondition.to_json()},
            "expected_postconditions": [{"path": "verified", "equals": True}],
            "metadata": {"workflow": "issue-43"},
        }
    )

    assert result["status"] == "completed"
    assert result["trace"]["intent"] == "certify a downstream claim"
    assert result["trace"]["action"] == "certify_claim"
    assert result["trace"]["metadata"] == {"workflow": "issue-43"}
    bundle = ProofBundle.from_json(str(result["proof_bundle_json"]))
    assert verify_proof_bundle(bundle).valid_bundle is True
