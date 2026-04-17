"""Sequential composition tests for VerifiedAgentRuntime with CertificateStore."""

from __future__ import annotations

from collections.abc import Mapping
from typing import cast

from logos import (
    ActionEnvelope,
    CertificateStore,
    GoalContract,
    PostconditionCheck,
    ProofCertificate,
    RiskLevel,
    RuntimePhase,
    RuntimeRequest,
    VariableDecl,
    VerifiedAgentRuntime,
    certify,
)
from logos.counterfactual import CounterfactualPlanner


def _make_planner() -> CounterfactualPlanner:
    """Create a planner with safe and risky branches for composition tests."""
    planner = CounterfactualPlanner()
    for decl in (
        VariableDecl(name="budget", sort="Int"),
        VariableDecl(name="risk", sort="Int"),
    ):
        planner.declare(decl.name, decl.sort, size=decl.size)
    planner.assert_constraint("budget >= 0")
    planner.assert_constraint("risk >= 0")
    planner.branch("safe", additional_constraints=["budget == 80", "risk == 1"])
    planner.branch("risky", additional_constraints=["budget == 150", "risk == 3"])
    return planner


def _make_contract() -> GoalContract:
    """Create a contract that safe passes and risky fails via context overrides."""
    return GoalContract(
        contract_id="deploy",
        preconditions=("budget_ok", "risk_ok"),
        invariants=("sat",),
    )


def _certify_adapter(payload: Mapping[str, object]) -> dict[str, object]:
    """Simple adapter that certifies a propositional claim."""
    argument = payload.get("argument", "")
    if not isinstance(argument, str):
        return {"error": "argument must be a string"}
    cert = certify(argument)
    return {
        "verified": cert.verified,
        "status": "certified" if cert.verified else "failed",
        "certificate_json": cert.to_json(),
    }


def _extract_certificate(outcome_certificate_json: object) -> ProofCertificate:
    if not isinstance(outcome_certificate_json, str):
        raise AssertionError("Expected certificate_json to be a string")
    return ProofCertificate.from_json(outcome_certificate_json)


def test_runtime_sequential_composition_uses_stored_certificate_from_prior_request() -> None:
    runtime = VerifiedAgentRuntime(_make_planner())
    store = CertificateStore()

    request_1 = RuntimeRequest(
        request_id="req-1",
        branch_id="safe",
        strategy="default",
        contract=_make_contract(),
        action_envelope=ActionEnvelope(
            intent="prove base claim",
            action="certify_claim",
            payload={"argument": "P -> Q, P |- Q"},
            expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
        ),
        proof_certificate=certify("P |- P"),
        risk_level=RiskLevel.LOW,
        context_overrides={"budget_ok": True, "risk_ok": True},
    )

    outcome_1 = runtime.run(request_1, adapters={"certify_claim": _certify_adapter})

    assert outcome_1.phase is RuntimePhase.COMPLETED
    assert outcome_1.completed is True
    assert outcome_1.action_result is not None
    first_action_payload = cast(dict[str, object], outcome_1.action_result.action_result)

    first_cert = _extract_certificate(first_action_payload["certificate_json"])
    first_store_id = store.store(first_cert, tags={"step": "1", "domain": "logic"})
    assert store.stats().total == 1

    stored_first = store.get(first_store_id)
    assert stored_first is not None

    request_2 = RuntimeRequest(
        request_id="req-2",
        branch_id="safe",
        strategy="default",
        contract=_make_contract(),
        action_envelope=ActionEnvelope(
            intent="use stored proof as precondition",
            action="certify_claim",
            payload={"argument": "Q -> R, Q |- R"},
            preconditions=("step1",),
            cert_refs={"step1": stored_first.certificate},
            expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
        ),
        proof_certificate=certify("Q |- Q"),
        risk_level=RiskLevel.MEDIUM,
        context_overrides={"budget_ok": True, "risk_ok": True},
    )

    outcome_2 = runtime.run(request_2, adapters={"certify_claim": _certify_adapter})

    assert outcome_2.phase is RuntimePhase.COMPLETED
    assert outcome_2.completed is True
    assert outcome_2.action_result is not None
    assert outcome_2.action_result.status == "completed"
    assert outcome_2.action_result.trace["preconditions"][0]["verified"] is True
    assert store.stats().total >= 1
    assert outcome_1.trace.request_id == "req-1"
    assert outcome_2.trace.request_id == "req-2"
    assert outcome_1.trace.events[-1].phase is RuntimePhase.COMPLETED
    assert outcome_2.trace.events[-1].phase is RuntimePhase.COMPLETED


def test_runtime_recovery_chain_preserves_store_and_reuses_prior_certificate_after_failure() -> None:
    runtime = VerifiedAgentRuntime(_make_planner())
    store = CertificateStore()

    request_1 = RuntimeRequest(
        request_id="req-1",
        branch_id="safe",
        strategy="default",
        contract=_make_contract(),
        action_envelope=ActionEnvelope(
            intent="seed reusable proof",
            action="certify_claim",
            payload={"argument": "P -> Q, P |- Q"},
            expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
        ),
        proof_certificate=certify("P |- P"),
        risk_level=RiskLevel.LOW,
        context_overrides={"budget_ok": True, "risk_ok": True},
    )
    outcome_1 = runtime.run(request_1, adapters={"certify_claim": _certify_adapter})
    assert outcome_1.completed is True
    assert outcome_1.action_result is not None
    first_action_payload = cast(dict[str, object], outcome_1.action_result.action_result)

    first_cert = _extract_certificate(first_action_payload["certificate_json"])
    store_id = store.store(first_cert, tags={"step": "1", "domain": "logic"})
    stored_first = store.get(store_id)
    assert stored_first is not None

    request_2 = RuntimeRequest(
        request_id="req-2",
        branch_id="risky",
        strategy="default",
        contract=_make_contract(),
        action_envelope=ActionEnvelope(
            intent="attempt risky action",
            action="certify_claim",
            payload={"argument": "Q -> R, Q |- R"},
            expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
        ),
        proof_certificate=certify("Q |- Q"),
        risk_level=RiskLevel.LOW,
        context_overrides={"budget_ok": False, "risk_ok": False},
    )
    outcome_2 = runtime.run(request_2, adapters={"certify_claim": _certify_adapter})

    assert outcome_2.phase is RuntimePhase.BLOCKED
    assert outcome_2.blocked is True
    assert outcome_2.action_result is None
    assert outcome_2.contract_result is not None
    assert store.get(store_id) == stored_first
    assert store.stats().total == 1

    request_3 = RuntimeRequest(
        request_id="req-3",
        branch_id="safe",
        strategy="default",
        contract=_make_contract(),
        action_envelope=ActionEnvelope(
            intent="replan with stored proof",
            action="certify_claim",
            payload={"argument": "R -> S, R |- S"},
            preconditions=("step1",),
            cert_refs={"step1": stored_first.certificate},
            expected_postconditions=(PostconditionCheck(path="verified", equals=True),),
        ),
        proof_certificate=certify("R |- R"),
        risk_level=RiskLevel.LOW,
        context_overrides={"budget_ok": True, "risk_ok": True},
    )
    outcome_3 = runtime.run(request_3, adapters={"certify_claim": _certify_adapter})

    assert outcome_3.phase is RuntimePhase.COMPLETED
    assert outcome_3.completed is True
    assert outcome_3.action_result is not None
    assert outcome_3.action_result.trace["preconditions"][0]["verified"] is True
    assert [outcome_1.trace.request_id, outcome_2.trace.request_id, outcome_3.trace.request_id] == [
        "req-1",
        "req-2",
        "req-3",
    ]
    assert outcome_1.trace.events[-1].phase is RuntimePhase.COMPLETED
    assert outcome_2.trace.events[-1].phase is RuntimePhase.RECOVERY
    assert outcome_3.trace.events[-1].phase is RuntimePhase.COMPLETED
