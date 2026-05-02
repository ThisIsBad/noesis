"""Confidence and escalation vocabulary — shared with Logos uncertainty layer.

Mirrors the schema from services/logos/src/logos/uncertainty.py so that
downstream services can validate and emit ConfidenceRecords without
importing Logos internals.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"


class ConfidenceLevel(str, Enum):
    """Calibrated confidence levels (four-state discrete scale)."""

    CERTAIN = "certain"
    SUPPORTED = "supported"
    WEAK = "weak"
    UNKNOWN = "unknown"


class RiskLevel(str, Enum):
    """Action risk levels used by escalation checks."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class EscalationDecision(str, Enum):
    """Escalation outcomes for a confidence/risk pair."""

    PROCEED = "proceed"
    REVIEW_REQUIRED = "review_required"
    BLOCKED = "blocked"


class ConfidenceRecord(BaseModel):
    """Confidence state with provenance metadata."""

    schema_version: str = SCHEMA_VERSION
    claim: str
    level: ConfidenceLevel
    provenance: list[str] = Field(default_factory=list)
    linked_certificate_ref: Optional[str] = None


def confidence_from_float(score: float) -> ConfidenceLevel:
    """Map a 0-1 float confidence to a discrete ConfidenceLevel.

    Boundary convention:
      >= 0.95 → CERTAIN
      >= 0.70 → SUPPORTED
      >  0.30 → WEAK
      else    → UNKNOWN
    """
    if not 0.0 <= score <= 1.0:
        raise ValueError(f"confidence score out of range [0,1]: {score}")
    if score >= 0.95:
        return ConfidenceLevel.CERTAIN
    if score >= 0.70:
        return ConfidenceLevel.SUPPORTED
    if score > 0.30:
        return ConfidenceLevel.WEAK
    return ConfidenceLevel.UNKNOWN
