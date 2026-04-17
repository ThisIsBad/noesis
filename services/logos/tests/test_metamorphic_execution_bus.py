"""Metamorphic tests for proof-carrying action envelopes."""

from __future__ import annotations

import pytest

from logos import ActionEnvelope, PostconditionCheck, certify, execute_action_envelope


pytestmark = pytest.mark.metamorphic


def test_mr_bus01_equivalent_envelope_reference_order_preserves_decision() -> None:
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
    assert first_result.trace["decision"] == second_result.trace["decision"] == "completed"
