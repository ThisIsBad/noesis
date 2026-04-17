"""Confidence calibration and escalation policy for reasoning outputs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from enum import Enum
from typing import Mapping

from logos.certificate import ProofCertificate
from logos.schema_utils import (
    load_json_object,
    require_list_of_str,
    require_optional_str,
    require_str,
)

SCHEMA_VERSION = "1.0"


class ConfidenceLevel(Enum):
    """Calibrated confidence levels."""

    CERTAIN = "certain"
    SUPPORTED = "supported"
    WEAK = "weak"
    UNKNOWN = "unknown"


class RiskLevel(Enum):
    """Action risk levels used by escalation checks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EscalationDecision(Enum):
    """Escalation outcomes for a confidence/risk pair."""

    PROCEED = "proceed"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ConfidenceRecord:
    """Confidence state with provenance metadata."""

    claim: str
    level: ConfidenceLevel
    provenance: tuple[str, ...]
    linked_certificate_ref: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize confidence record to dictionary."""
        return {
            "schema_version": SCHEMA_VERSION,
            "claim": self.claim,
            "level": self.level.value,
            "provenance": list(self.provenance),
            "linked_certificate_ref": self.linked_certificate_ref,
        }

    def to_json(self) -> str:
        """Serialize confidence record to JSON."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ConfidenceRecord":
        """Deserialize confidence record from dictionary."""
        schema_version = payload.get("schema_version")
        claim = require_str(payload.get("claim"), "Confidence payload field 'claim' must be a string")
        level = require_str(payload.get("level"), "Confidence payload field 'level' must be a string")
        provenance = require_list_of_str(
            payload.get("provenance"),
            "Confidence payload field 'provenance' must be list[str]",
        )
        linked_certificate_ref = payload.get("linked_certificate_ref")
        legacy_linked_certificate = payload.get("linked_certificate")

        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported uncertainty schema version '{schema_version}'")
        linked_certificate_ref = require_optional_str(
            linked_certificate_ref,
            "Confidence payload field 'linked_certificate_ref' must be str or null",
        )
        legacy_linked_certificate = require_optional_str(
            legacy_linked_certificate,
            "Legacy confidence field 'linked_certificate' must be str or null",
        )

        resolved_ref = linked_certificate_ref
        if resolved_ref is None and isinstance(legacy_linked_certificate, str):
            resolved_ref = _certificate_ref_from_payload(legacy_linked_certificate)

        return cls(
            claim=claim,
            level=ConfidenceLevel(level),
            provenance=tuple(provenance),
            linked_certificate_ref=resolved_ref,
        )

    @classmethod
    def from_json(cls, raw_json: str) -> "ConfidenceRecord":
        """Deserialize confidence record from JSON."""
        payload = load_json_object(
            raw_json,
            invalid_error="Invalid confidence JSON",
            object_error="Confidence JSON must be an object",
        )
        return cls.from_dict(payload)


@dataclass(frozen=True)
class EscalationResult:
    """Result of applying uncertainty escalation policy."""

    decision: EscalationDecision
    reason: str


@dataclass(frozen=True)
class UncertaintyPolicy:
    """Escalation policy by risk level and confidence state."""

    high_risk_block: tuple[ConfidenceLevel, ...] = (ConfidenceLevel.WEAK, ConfidenceLevel.UNKNOWN)
    medium_risk_review: tuple[ConfidenceLevel, ...] = (ConfidenceLevel.WEAK, ConfidenceLevel.UNKNOWN)


class UncertaintyCalibrator:
    """Deterministically calibrate confidence and enforce escalation."""

    def classify(
        self,
        verified: bool,
        evidence_count: int = 1,
        conflicting_signals: bool = False,
    ) -> ConfidenceLevel:
        """Classify confidence from verification signals."""
        if conflicting_signals:
            return ConfidenceLevel.UNKNOWN
        if verified and evidence_count >= 2:
            return ConfidenceLevel.CERTAIN
        if verified:
            return ConfidenceLevel.SUPPORTED
        return ConfidenceLevel.WEAK

    def from_certificate(
        self,
        certificate: ProofCertificate,
        provenance: list[str] | None = None,
        conflicting_signals: bool = False,
    ) -> ConfidenceRecord:
        """Build confidence record from proof certificate output."""
        level = self.classify(
            verified=certificate.verified,
            evidence_count=len(provenance or [certificate.method]),
            conflicting_signals=conflicting_signals,
        )
        return ConfidenceRecord(
            claim=str(certificate.claim),
            level=level,
            provenance=tuple(provenance or [certificate.method]),
            linked_certificate_ref=certificate_reference(certificate),
        )

    def enforce(
        self,
        record: ConfidenceRecord,
        risk_level: RiskLevel,
        policy: UncertaintyPolicy | None = None,
    ) -> EscalationResult:
        """Apply escalation policy for a confidence record."""
        active_policy = policy or UncertaintyPolicy()

        if risk_level is RiskLevel.HIGH and record.level in active_policy.high_risk_block:
            return EscalationResult(
                decision=EscalationDecision.BLOCKED,
                reason="High-risk action blocked due to weak or unknown confidence",
            )

        if risk_level is RiskLevel.MEDIUM and record.level in active_policy.medium_risk_review:
            return EscalationResult(
                decision=EscalationDecision.REVIEW_REQUIRED,
                reason="Medium-risk action requires review for weak or unknown confidence",
            )

        if risk_level is RiskLevel.HIGH and record.level is ConfidenceLevel.SUPPORTED:
            return EscalationResult(
                decision=EscalationDecision.REVIEW_REQUIRED,
                reason="High-risk action requires review unless confidence is certain",
            )

        return EscalationResult(
            decision=EscalationDecision.PROCEED,
            reason="Confidence is sufficient for selected risk level",
        )

    def is_policy_compliant(
        self,
        record: ConfidenceRecord,
        risk_level: RiskLevel,
        decision: EscalationDecision,
        policy: UncertaintyPolicy | None = None,
    ) -> bool:
        """Check whether an external decision follows escalation policy."""
        expected = self.enforce(record=record, risk_level=risk_level, policy=policy)
        return decision is expected.decision


def certificate_reference(certificate: ProofCertificate) -> str:
    """Build stable certificate reference id from canonical JSON payload."""
    return _certificate_ref_from_payload(certificate.to_json())


def resolve_certificate_reference(
    record: ConfidenceRecord,
    certificates: Mapping[str, ProofCertificate],
) -> ProofCertificate | None:
    """Resolve linked certificate reference from a candidate certificate map."""
    if record.linked_certificate_ref is None:
        return None

    for certificate in certificates.values():
        if certificate_reference(certificate) == record.linked_certificate_ref:
            return certificate
    return None


def _certificate_ref_from_payload(payload: str) -> str:
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"sha256:{digest}"
