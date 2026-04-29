"""Compositional proof orchestrator for multi-part claims."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

from logos.certificate import ProofCertificate, certify, verify_certificate

SCHEMA_VERSION = "1.0"

JSONValue = Any


class ClaimStatus(Enum):
    """Verification status of a claim node."""

    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class Claim:
    """A single claim node in the proof tree."""

    claim_id: str
    description: str
    parent_id: str | None = None
    sub_claim_ids: list[str] = field(default_factory=list)
    certificate: ProofCertificate | None = None
    status: ClaimStatus = ClaimStatus.PENDING
    expression: str | None = None
    composition_rule: str | None = None
    failure_reason: str = ""


@dataclass(frozen=True)
class OrchestrationStatus:
    """Overall proof tree status snapshot."""

    total_claims: int
    verified: int
    failed: int
    pending: int
    is_complete: bool
    root_certificate: ProofCertificate | None


class _RuleNode:
    pass


@dataclass(frozen=True)
class _IdentifierNode(_RuleNode):
    claim_id: str


@dataclass(frozen=True)
class _BinaryNode(_RuleNode):
    operator: str
    left: _RuleNode
    right: _RuleNode


class ProofOrchestrator:
    """Manage compositional proof trees."""

    def __init__(self) -> None:
        self._claims: dict[str, Claim] = {}
        self._root_id: str | None = None

    def claim(self, claim_id: str, description: str) -> Claim:
        """Create the root claim. Must be called first, exactly once."""
        if self._root_id is not None:
            raise ValueError("Root claim already exists")
        claim = self._create_claim(claim_id, description, parent_id=None)
        self._root_id = claim.claim_id
        return claim

    def sub_claim(self, claim_id: str, parent_id: str, description: str) -> Claim:
        """Add a sub-claim under an existing parent claim."""
        parent = self.get_claim(parent_id)
        claim = self._create_claim(claim_id, description, parent_id=parent.claim_id)
        parent.sub_claim_ids.append(claim.claim_id)
        return claim

    def set_composition(self, claim_id: str, rule: str) -> None:
        """Set how sub-claims compose for a parent claim."""
        claim = self.get_claim(claim_id)
        normalized_rule = self._require_non_empty_value(rule, "rule")
        parsed = _parse_rule(normalized_rule)
        referenced_ids = _collect_identifiers(parsed)
        unknown = sorted(referenced_ids - set(claim.sub_claim_ids))
        if unknown:
            raise ValueError("Composition rule references unknown sub-claims: " + ", ".join(unknown))
        claim.composition_rule = normalized_rule

    def verify_leaf(self, claim_id: str, expression: str) -> ProofCertificate:
        """Verify a leaf claim using LogicBrain's certify()."""
        claim = self.get_claim(claim_id)
        if claim.sub_claim_ids:
            raise ValueError(f"Claim '{claim_id}' is not a leaf claim")

        normalized_expression = self._require_non_empty_value(expression, "expression")
        certificate = certify(normalized_expression)
        claim.expression = normalized_expression
        claim.certificate = certificate
        claim.failure_reason = ""
        claim.status = ClaimStatus.VERIFIED if certificate.verified else ClaimStatus.FAILED
        if claim.status is ClaimStatus.FAILED:
            claim.failure_reason = "Leaf verification returned verified=False"
        return certificate

    def attach_certificate(self, claim_id: str, certificate: ProofCertificate) -> None:
        """Attach an externally-produced certificate to a leaf claim."""
        claim = self.get_claim(claim_id)
        if claim.sub_claim_ids:
            raise ValueError(f"Claim '{claim_id}' is not a leaf claim")
        if verify_certificate(certificate) is not True:
            raise ValueError("Attached certificate failed independent verification")
        claim.certificate = certificate
        claim.failure_reason = ""
        claim.status = ClaimStatus.VERIFIED if certificate.verified else ClaimStatus.FAILED
        if claim.status is ClaimStatus.FAILED:
            claim.failure_reason = "Attached certificate has verified=False"

    def mark_failed(self, claim_id: str, reason: str = "") -> None:
        """Explicitly mark a claim as failed."""
        claim = self.get_claim(claim_id)
        claim.status = ClaimStatus.FAILED
        claim.failure_reason = reason
        claim.certificate = None

    def propagate(self) -> None:
        """Re-evaluate all parent claims based on sub-claim states."""
        if self._root_id is None:
            return

        for claim_id in self._topological_order():
            claim = self._claims[claim_id]
            if not claim.sub_claim_ids:
                continue
            self._propagate_claim(claim)

    def status(self) -> OrchestrationStatus:
        """Return current proof tree status."""
        verified_count = sum(1 for claim in self._claims.values() if claim.status is ClaimStatus.VERIFIED)
        failed_count = sum(1 for claim in self._claims.values() if claim.status is ClaimStatus.FAILED)
        pending_count = sum(1 for claim in self._claims.values() if claim.status is ClaimStatus.PENDING)
        root_claim = self._claims.get(self._root_id) if self._root_id is not None else None
        return OrchestrationStatus(
            total_claims=len(self._claims),
            verified=verified_count,
            failed=failed_count,
            pending=pending_count,
            is_complete=root_claim is not None and root_claim.status is ClaimStatus.VERIFIED,
            root_certificate=None if root_claim is None else root_claim.certificate,
        )

    def get_claim(self, claim_id: str) -> Claim:
        """Get claim by ID. Raises ValueError if not found."""
        normalized = self._require_non_empty_value(claim_id, "claim_id")
        claim = self._claims.get(normalized)
        if claim is None:
            raise ValueError(f"Unknown claim '{normalized}'")
        return claim

    def pending_claims(self) -> tuple[Claim, ...]:
        """Return all claims that are still PENDING."""
        return tuple(
            self._claims[claim_id]
            for claim_id in sorted(self._claims)
            if self._claims[claim_id].status is ClaimStatus.PENDING
        )

    def to_dict(self) -> dict[str, JSONValue]:
        """Serialize full proof tree to dictionary."""
        return {
            "schema_version": SCHEMA_VERSION,
            "root_id": self._root_id,
            "claims": [self._claim_to_dict(self._claims[claim_id]) for claim_id in sorted(self._claims)],
        }

    def to_json(self) -> str:
        """Serialize full proof tree to JSON."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, JSONValue]) -> "ProofOrchestrator":
        """Deserialize proof tree from dictionary."""
        schema_version = data.get("schema_version")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported orchestrator schema version '{schema_version}'")

        raw_claims = data.get("claims")
        if not isinstance(raw_claims, list):
            raise ValueError("Orchestrator payload requires list field 'claims'")

        orchestrator = cls()
        root_id = data.get("root_id")
        if root_id is not None and not isinstance(root_id, str):
            raise ValueError("Orchestrator field 'root_id' must be a string or null")

        for item in raw_claims:
            if not isinstance(item, dict):
                raise ValueError("Orchestrator claim entries must be objects")
            claim = _claim_from_dict(item)
            if claim.claim_id in orchestrator._claims:
                raise ValueError(f"Duplicate claim id '{claim.claim_id}' in payload")
            orchestrator._claims[claim.claim_id] = claim

        orchestrator._root_id = root_id
        orchestrator._validate_tree()
        return orchestrator

    @classmethod
    def from_json(cls, raw_json: str) -> "ProofOrchestrator":
        """Deserialize proof tree from JSON string."""
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid orchestrator JSON") from exc
        if not isinstance(parsed, dict):
            raise ValueError("Orchestrator JSON must be an object")
        return cls.from_dict({str(key): value for key, value in parsed.items()})

    def _create_claim(self, claim_id: str, description: str, parent_id: str | None) -> Claim:
        normalized_id = self._require_non_empty_value(claim_id, "claim_id")
        normalized_description = self._require_non_empty_value(description, "description")
        if normalized_id in self._claims:
            raise ValueError(f"Claim '{normalized_id}' already exists")
        claim = Claim(
            claim_id=normalized_id,
            description=normalized_description,
            parent_id=parent_id,
        )
        self._claims[normalized_id] = claim
        return claim

    def _propagate_claim(self, claim: Claim) -> None:
        sub_claims = [self._claims[sub_id] for sub_id in claim.sub_claim_ids]
        if claim.composition_rule is None:
            if all(sub_claim.status is ClaimStatus.PENDING for sub_claim in sub_claims):
                claim.status = ClaimStatus.PENDING
            else:
                claim.status = ClaimStatus.PARTIAL
            claim.certificate = None
            return

        parsed_rule = _parse_rule(claim.composition_rule)
        referenced_ids = _collect_identifiers(parsed_rule)
        status_map = {sub_claim.claim_id: sub_claim.status for sub_claim in sub_claims}
        if referenced_ids - set(status_map):
            missing = sorted(referenced_ids - set(status_map))
            raise ValueError(
                f"Claim '{claim.claim_id}' composition rule references unknown sub-claims: {', '.join(missing)}"
            )

        evaluation = _evaluate_rule(parsed_rule, status_map)
        all_referenced_verified = all(status_map[claim_id] is ClaimStatus.VERIFIED for claim_id in referenced_ids)
        if evaluation is True and all_referenced_verified:
            claim.status = ClaimStatus.VERIFIED
            claim.failure_reason = ""
            claim.certificate = _compose_certificate(claim, sub_claims, referenced_ids)
            return

        claim.certificate = None
        if evaluation is False:
            claim.status = ClaimStatus.FAILED
            claim.failure_reason = "Composition rule cannot be satisfied"
            return

        if any(
            sub_claim.status in {ClaimStatus.VERIFIED, ClaimStatus.FAILED, ClaimStatus.PARTIAL}
            for sub_claim in sub_claims
        ):
            claim.status = ClaimStatus.PARTIAL
        else:
            claim.status = ClaimStatus.PENDING

    def _topological_order(self) -> list[str]:
        ordered: list[str] = []

        def visit(claim_id: str) -> None:
            claim = self._claims[claim_id]
            for sub_claim_id in claim.sub_claim_ids:
                visit(sub_claim_id)
            ordered.append(claim_id)

        if self._root_id is not None:
            visit(self._root_id)
        return ordered

    def _validate_tree(self) -> None:
        if self._root_id is None:
            if self._claims:
                raise ValueError("Orchestrator payload with claims requires a root_id")
            return
        if self._root_id not in self._claims:
            raise ValueError(f"Orchestrator root claim '{self._root_id}' does not exist")

        root_claim = self._claims[self._root_id]
        if root_claim.parent_id is not None:
            raise ValueError("Root claim may not have a parent_id")

        for claim in self._claims.values():
            if claim.parent_id is not None and claim.parent_id not in self._claims:
                raise ValueError(f"Claim '{claim.claim_id}' references unknown parent '{claim.parent_id}'")
            for sub_id in claim.sub_claim_ids:
                if sub_id not in self._claims:
                    raise ValueError(f"Claim '{claim.claim_id}' references unknown sub-claim '{sub_id}'")
                if self._claims[sub_id].parent_id != claim.claim_id:
                    raise ValueError(f"Claim '{sub_id}' parent mismatch for parent '{claim.claim_id}'")
            if claim.composition_rule is not None:
                referenced_ids = _collect_identifiers(_parse_rule(claim.composition_rule))
                unknown = sorted(referenced_ids - set(claim.sub_claim_ids))
                if unknown:
                    raise ValueError("Composition rule references unknown sub-claims: " + ", ".join(unknown))

    @staticmethod
    def _require_non_empty_value(value: object, field_name: str) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"Field '{field_name}' must be a non-empty string")
        return value.strip()

    @staticmethod
    def _claim_to_dict(claim: Claim) -> dict[str, JSONValue]:
        return {
            "claim_id": claim.claim_id,
            "description": claim.description,
            "parent_id": claim.parent_id,
            "sub_claim_ids": list(claim.sub_claim_ids),
            "certificate": None if claim.certificate is None else claim.certificate.to_dict(),
            "status": claim.status.value,
            "expression": claim.expression,
            "composition_rule": claim.composition_rule,
            "failure_reason": claim.failure_reason,
        }


def _claim_from_dict(data: dict[str, JSONValue]) -> Claim:
    claim_id = data.get("claim_id")
    description = data.get("description")
    parent_id = data.get("parent_id")
    sub_claim_ids = data.get("sub_claim_ids", [])
    status_value = data.get("status")
    expression = data.get("expression")
    composition_rule = data.get("composition_rule")
    failure_reason = data.get("failure_reason", "")
    certificate_data = data.get("certificate")

    if not isinstance(claim_id, str) or not claim_id:
        raise ValueError("Claim field 'claim_id' must be a non-empty string")
    if not isinstance(description, str) or not description:
        raise ValueError("Claim field 'description' must be a non-empty string")
    if parent_id is not None and not isinstance(parent_id, str):
        raise ValueError("Claim field 'parent_id' must be a string or null")
    if not isinstance(sub_claim_ids, list) or any(not isinstance(item, str) for item in sub_claim_ids):
        raise ValueError("Claim field 'sub_claim_ids' must be list[str]")
    if not isinstance(status_value, str):
        raise ValueError("Claim field 'status' must be a string")
    if expression is not None and not isinstance(expression, str):
        raise ValueError("Claim field 'expression' must be a string or null")
    if composition_rule is not None and not isinstance(composition_rule, str):
        raise ValueError("Claim field 'composition_rule' must be a string or null")
    if not isinstance(failure_reason, str):
        raise ValueError("Claim field 'failure_reason' must be a string")

    certificate: ProofCertificate | None = None
    if certificate_data is not None:
        if not isinstance(certificate_data, dict):
            raise ValueError("Claim field 'certificate' must be an object or null")
        certificate = ProofCertificate.from_dict(certificate_data)

    return Claim(
        claim_id=claim_id,
        description=description,
        parent_id=parent_id,
        sub_claim_ids=list(sub_claim_ids),
        certificate=certificate,
        status=ClaimStatus(status_value),
        expression=expression,
        composition_rule=composition_rule,
        failure_reason=failure_reason,
    )


def _compose_certificate(
    claim: Claim,
    sub_claims: list[Claim],
    referenced_ids: set[str],
) -> ProofCertificate:
    sub_certificates: list[dict[str, JSONValue]] = []
    for sub_claim in sub_claims:
        if sub_claim.claim_id not in referenced_ids:
            continue
        if sub_claim.status is not ClaimStatus.VERIFIED or sub_claim.certificate is None:
            raise ValueError(f"Verified claim '{claim.claim_id}' requires certificates for verified sub-claims")
        sub_certificates.append(sub_claim.certificate.to_dict())

    timestamp = datetime.now(timezone.utc).isoformat()
    return ProofCertificate(
        claim_type="composed",
        claim={
            "root_claim_id": claim.claim_id,
            "composition_rule": claim.composition_rule,
            "sub_certificates": sub_certificates,
        },
        method="composition",
        verified=True,
        timestamp=timestamp,
        verification_artifact={
            "composition_rule": claim.composition_rule,
            "sub_claim_count": len(sub_certificates),
            "all_sub_verified": True,
        },
    )


def _tokenize_rule(rule: str) -> list[str]:
    tokens: list[str] = []
    current: list[str] = []
    for char in rule:
        if char.isspace():
            if current:
                tokens.append("".join(current))
                current.clear()
            continue
        if char in {"(", ")"}:
            if current:
                tokens.append("".join(current))
                current.clear()
            tokens.append(char)
            continue
        current.append(char)
    if current:
        tokens.append("".join(current))
    return tokens


def _parse_rule(rule: str) -> _RuleNode:
    tokens = _tokenize_rule(rule)
    if not tokens:
        raise ValueError("Composition rule cannot be empty")
    parser = _RuleParser(tokens)
    parsed = parser.parse_expression()
    if parser.position != len(tokens):
        raise ValueError(f"Unexpected token '{tokens[parser.position]}' in composition rule")
    return parsed


def _collect_identifiers(node: _RuleNode) -> set[str]:
    if isinstance(node, _IdentifierNode):
        return {node.claim_id}
    if isinstance(node, _BinaryNode):
        return _collect_identifiers(node.left) | _collect_identifiers(node.right)
    raise TypeError(f"Unsupported rule node type: {type(node)!r}")


def _evaluate_rule(node: _RuleNode, statuses: dict[str, ClaimStatus]) -> bool | None:
    if isinstance(node, _IdentifierNode):
        status = statuses[node.claim_id]
        if status is ClaimStatus.VERIFIED:
            return True
        if status is ClaimStatus.FAILED:
            return False
        return None
    if isinstance(node, _BinaryNode):
        left_value = _evaluate_rule(node.left, statuses)
        right_value = _evaluate_rule(node.right, statuses)
        if node.operator == "AND":
            if left_value is False or right_value is False:
                return False
            if left_value is True and right_value is True:
                return True
            return None
        if node.operator == "OR":
            if left_value is True or right_value is True:
                return True
            if left_value is False and right_value is False:
                return False
            return None
    raise TypeError(f"Unsupported rule node type: {type(node)!r}")


class _RuleParser:
    def __init__(self, tokens: list[str]) -> None:
        self.tokens = tokens
        self.position = 0

    def parse_expression(self) -> _RuleNode:
        node = self.parse_term()
        while self._match("OR"):
            node = _BinaryNode("OR", node, self.parse_term())
        return node

    def parse_term(self) -> _RuleNode:
        node = self.parse_factor()
        while self._match("AND"):
            node = _BinaryNode("AND", node, self.parse_factor())
        return node

    def parse_factor(self) -> _RuleNode:
        token = self._peek()
        if token == "(":
            self.position += 1
            node = self.parse_expression()
            if self._peek() != ")":
                raise ValueError("Unbalanced parentheses in composition rule")
            self.position += 1
            return node
        if token is None:
            raise ValueError("Unexpected end of composition rule")
        if token.upper() == "NOT":
            raise ValueError("Composition rules do not support NOT")
        if token in {"AND", "OR", ")"}:
            raise ValueError(f"Unexpected token '{token}' in composition rule")
        self.position += 1
        return _IdentifierNode(token)

    def _match(self, keyword: str) -> bool:
        token = self._peek()
        if token is None:
            return False
        if token.upper() != keyword:
            return False
        self.position += 1
        return True

    def _peek(self) -> str | None:
        if self.position >= len(self.tokens):
            return None
        return self.tokens[self.position]
