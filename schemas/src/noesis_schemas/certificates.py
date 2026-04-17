"""Shared proof certificate schema — aligned with Logos service output.

This module mirrors the JSON-serialized shape of a Logos ProofCertificate
(see services/logos/src/logos/certificate.py). Other services consume
certificates as Pydantic models for validation, while Logos produces them
as frozen dataclasses internally.

Round-trip guarantee:
    >>> logos_cert.to_dict() == ProofCertificate.model_validate(
    ...     logos_cert.to_dict()
    ... ).model_dump()
"""

from typing import Any, Literal
from pydantic import BaseModel, Field

SCHEMA_VERSION = "1.0"

# Claim types — match logos.certificate constants.
PROPOSITIONAL_CLAIM = "propositional"
FOL_CLAIM = "fol"
Z3_SESSION_CLAIM = "z3_session"
COMPOSED_CLAIM = "composed"


class ProofCertificate(BaseModel):
    """Serializable proof-carrying certificate from Logos."""

    schema_version: Literal["1.0"] = SCHEMA_VERSION
    claim_type: str
    claim: Any
    method: str
    verified: bool
    timestamp: str
    verification_artifact: dict[str, Any] = Field(default_factory=dict)
