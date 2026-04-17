"""Tests for proof-carrying action envelopes."""

from __future__ import annotations

from logos import ActionEnvelope, PostconditionCheck, certify, execute_action_envelope, verify_proof_bundle


def test_execute_action_envelope_rejects_missing_precondition_certificate() -> None:
    envelope = ActionEnvelope(
        intent="verify a claim",
        action="verify_argument",
        payload={"argument": "P |- P"},
        preconditions=("root-cert",),
    )

    result = execute_action_envelope(envelope, adapters={"verify_argument": lambda payload: {"valid": True}})

    assert result.status == "rejected_preconditions"
    assert result.accepted is False
    assert result.diagnostics[0]["code"] == "missing_precondition_certificate"


def test_execute_action_envelope_rejects_unverified_precondition_certificate() -> None:
    envelope = ActionEnvelope(
        intent="verify a claim",
        action="verify_argument",
        payload={"argument": "P |- P"},
        preconditions=("root-cert",),
        cert_refs={"root-cert": certify("P -> Q, Q |- P")},
    )

    result = execute_action_envelope(envelope, adapters={"verify_argument": lambda payload: {"valid": True}})

    assert result.status == "rejected_preconditions"
    assert result.accepted is False
    assert result.diagnostics[0]["code"] == "invalid_precondition_certificate"


def test_execute_action_envelope_detects_postcondition_mismatch() -> None:
    envelope = ActionEnvelope(
        intent="verify a claim",
        action="verify_argument",
        payload={"argument": "P -> Q, Q |- P"},
        expected_postconditions=(PostconditionCheck(path="valid", equals=True),),
    )

    result = execute_action_envelope(
        envelope,
        adapters={"verify_argument": lambda payload: {"valid": False, "rule": "Affirming the Consequent"}},
    )

    assert result.status == "postcondition_mismatch"
    assert result.accepted is True
    assert result.diagnostics[0] == {
        "code": "postcondition_mismatch",
        "message": "Postcondition 'valid' did not match expected value",
        "path": "valid",
        "expected": True,
        "actual": False,
    }


def test_execute_action_envelope_returns_trace_and_proof_bundle() -> None:
    precondition = certify("P |- P")
    output = certify("P -> Q, P |- Q")
    envelope = ActionEnvelope(
        intent="certify a downstream claim",
        action="certify_claim",
        payload={"argument": "P -> Q, P |- Q"},
        preconditions=("root-cert",),
        cert_refs={"root-cert": precondition},
        expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
        metadata={"issue": "#43"},
    )

    result = execute_action_envelope(
        envelope,
        adapters={
            "certify_claim": lambda payload: {
                "status": "certified",
                "verified": True,
                "certificate_json": output.to_json(),
            }
        },
    )

    assert result.status == "completed"
    assert result.trace["intent"] == "certify a downstream claim"
    assert result.trace["action"] == "certify_claim"
    assert result.trace["preconditions"][0]["ref"] == "root-cert"
    assert result.trace["postconditions"][0]["matched"] is True
    assert result.proof_bundle is not None
    assert verify_proof_bundle(result.proof_bundle).valid_bundle is True


def test_execute_action_envelope_preserves_decision_for_equivalent_envelopes() -> None:
    first = ActionEnvelope(
        intent="certify a downstream claim",
        action="certify_claim",
        payload={"argument": "P -> Q, P |- Q"},
        preconditions=("a", "b"),
        cert_refs={"a": certify("P |- P"), "b": certify("Q |- Q")},
        expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
    )
    second = ActionEnvelope(
        intent="certify a downstream claim",
        action="certify_claim",
        payload={"argument": "P -> Q, P |- Q"},
        preconditions=("b", "a"),
        cert_refs={"b": certify("Q |- Q"), "a": certify("P |- P")},
        expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
    )

    adapter = {
        "certify_claim": lambda payload: {
            "verified": True,
            "certificate_json": certify("P -> Q, P |- Q").to_json(),
        }
    }

    first_result = execute_action_envelope(first, adapters=adapter)
    second_result = execute_action_envelope(second, adapters=adapter)

    assert first_result.status == second_result.status == "completed"
    assert first_result.diagnostics == second_result.diagnostics == ()
    assert first_result.trace["decision"] == second_result.trace["decision"] == "completed"
