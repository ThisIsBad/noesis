"""Deterministic adversarial self-play harness for robustness regression."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum

from logos import certify, create_proof_bundle
from logos.action_policy import ActionPolicyEngine, ActionPolicyRule
from logos.counterfactual import CounterfactualPlanner
from logos.goal_contract import GoalContract
from logos.trust_ledger import FederatedProofLedger, TrustPolicy
from logos.uncertainty import RiskLevel
from logos.verified_runtime import RuntimeRequest, VerifiedAgentRuntime
from logos.execution_bus import ActionEnvelope

SCHEMA_VERSION = "1.0"


class AttackTemplate(Enum):
    """Deterministic adversarial attack families."""

    CONTRADICTION_INJECTION = "contradiction_injection"
    STALE_PROOF_REPLAY = "stale_proof_replay"
    POLICY_BYPASS = "policy_bypass"


@dataclass(frozen=True)
class DefensiveScore:
    """Explainable defense score decomposition."""

    recovery_speed: float
    violation_containment: float
    proof_integrity_retention: float

    @property
    def total(self) -> float:
        return round(
            (self.recovery_speed + self.violation_containment + self.proof_integrity_retention) / 3.0,
            6,
        )


@dataclass(frozen=True)
class SelfPlayEpisode:
    """One reproducible adversarial episode."""

    seed: int
    attack: AttackTemplate
    passed: bool
    blocked_safely: bool
    score: DefensiveScore
    details: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {
            "seed": self.seed,
            "attack": self.attack.value,
            "passed": self.passed,
            "blocked_safely": self.blocked_safely,
            "score": {
                "recovery_speed": self.score.recovery_speed,
                "violation_containment": self.score.violation_containment,
                "proof_integrity_retention": self.score.proof_integrity_retention,
                "total": self.score.total,
            },
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class SelfPlayReport:
    """Regression-ready artifact for adversarial runs."""

    episodes: tuple[SelfPlayEpisode, ...]
    average_score: float
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "episodes": [episode.to_dict() for episode in self.episodes],
            "average_score": self.average_score,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


class AdversarialSelfPlayHarness:
    """Run deterministic red-team episodes against the current runtime stack."""

    def __init__(self) -> None:
        policy_engine = ActionPolicyEngine(
            [ActionPolicyRule(name="block_unsafe", severity="error", message="unsafe", when_true=("unsafe",))]
        )
        planner = CounterfactualPlanner()
        planner.declare("x", "Int")
        planner.assert_constraint("x > 0")
        planner.branch("safe", additional_constraints=["x < 10"])
        planner.branch("bad", additional_constraints=["x < 0"])
        self._runtime = VerifiedAgentRuntime(planner, policy_engine=policy_engine)
        self._ledger = FederatedProofLedger(TrustPolicy(domain_id="local", trusted_domains=("remote",)))

    def run_episode(self, seed: int) -> SelfPlayEpisode:
        """Run one deterministic episode chosen from a stable seed."""
        attack = _attack_for_seed(seed)
        if attack is AttackTemplate.CONTRADICTION_INJECTION:
            return self._run_contradiction(seed)
        if attack is AttackTemplate.STALE_PROOF_REPLAY:
            return self._run_stale_proof(seed)
        return self._run_policy_bypass(seed)

    def run_campaign(self, seeds: list[int]) -> SelfPlayReport:
        """Run a deterministic regression campaign."""
        episodes = tuple(self.run_episode(seed) for seed in seeds)
        average_score = round(sum(episode.score.total for episode in episodes) / len(episodes), 6)
        return SelfPlayReport(episodes=episodes, average_score=average_score)

    def _run_contradiction(self, seed: int) -> SelfPlayEpisode:
        request = RuntimeRequest(
            request_id=f"contradiction-{seed}",
            branch_id="bad",
            strategy="default",
            contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
            action_envelope=ActionEnvelope(
                intent="contradiction",
                action="verify_argument",
                payload={"argument": "P |- P"},
            ),
            proof_certificate=certify("P |- P"),
            risk_level=RiskLevel.LOW,
        )
        outcome = self._runtime.run(request, adapters={"verify_argument": _valid_adapter})
        blocked = outcome.blocked and outcome.recovery_decision is not None
        score = DefensiveScore(
            recovery_speed=1.0 if blocked and len(outcome.trace.events) <= 2 else 0.0,
            violation_containment=1.0 if outcome.action_result is None else 0.0,
            proof_integrity_retention=1.0,
        )
        return SelfPlayEpisode(
            seed=seed,
            attack=AttackTemplate.CONTRADICTION_INJECTION,
            passed=blocked,
            blocked_safely=blocked,
            score=score,
            details={
                "phase": outcome.phase.value,
                "selected_protocol": None
                if outcome.recovery_decision is None
                else outcome.recovery_decision.selected_protocol.value,
            },
        )

    def _run_stale_proof(self, seed: int) -> SelfPlayEpisode:
        bundle = create_proof_bundle(nodes={"root": certify("P |- P")}, roots=["root"])
        self._ledger.evaluate_bundle(
            bundle_id=f"bundle-{seed}",
            remote_domain_id="remote",
            bundle=bundle,
            accepted_at="2026-03-20T00:00:00+00:00",
            expires_at="2026-03-21T00:00:00+00:00",
        )
        self._ledger.revoke_bundle(
            f"bundle-{seed}",
            revoked_at="2026-03-22T00:00:00+00:00",
            reason="stale_proof_replay",
        )
        query = self._ledger.query_bundle(f"bundle-{seed}", as_of="2026-03-23T00:00:00+00:00")
        blocked = query.usable is False
        score = DefensiveScore(
            recovery_speed=1.0,
            violation_containment=1.0 if blocked else 0.0,
            proof_integrity_retention=1.0 if "revoked" in query.reasons else 0.0,
        )
        return SelfPlayEpisode(
            seed=seed,
            attack=AttackTemplate.STALE_PROOF_REPLAY,
            passed=blocked,
            blocked_safely=blocked,
            score=score,
            details={"reasons": list(query.reasons), "what_changed": list(query.what_changed)},
        )

    def _run_policy_bypass(self, seed: int) -> SelfPlayEpisode:
        request = RuntimeRequest(
            request_id=f"policy-{seed}",
            branch_id="safe",
            strategy="default",
            contract=GoalContract(contract_id="ship", preconditions=("sat",), invariants=("sat",)),
            action_envelope=ActionEnvelope(intent="bypass", action="verify_argument", payload={"argument": "P |- P"}),
            proof_certificate=certify("P |- P"),
            risk_level=RiskLevel.LOW,
            policy_action={"unsafe": True},
        )
        outcome = self._runtime.run(request, adapters={"verify_argument": _valid_adapter})
        blocked = outcome.blocked and outcome.action_result is None
        score = DefensiveScore(
            recovery_speed=1.0 if blocked else 0.0,
            violation_containment=1.0 if blocked else 0.0,
            proof_integrity_retention=1.0,
        )
        return SelfPlayEpisode(
            seed=seed,
            attack=AttackTemplate.POLICY_BYPASS,
            passed=blocked,
            blocked_safely=blocked,
            score=score,
            details={
                "phase": outcome.phase.value,
                "policy_decision": None
                if outcome.contract_result is None or outcome.contract_result.policy_decision is None
                else outcome.contract_result.policy_decision.value,
            },
        )


def _attack_for_seed(seed: int) -> AttackTemplate:
    attacks = (
        AttackTemplate.CONTRADICTION_INJECTION,
        AttackTemplate.STALE_PROOF_REPLAY,
        AttackTemplate.POLICY_BYPASS,
    )
    return attacks[seed % len(attacks)]


def _valid_adapter(payload: Mapping[str, object]) -> dict[str, object]:
    _ = payload
    return {"valid": True}
