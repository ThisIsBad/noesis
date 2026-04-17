"""Proof certificates for independent re-verification."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import z3

from logos.models import VerificationResult
from logos.parser import verify
from logos.predicate import PredicateVerifier
from logos.predicate_models import (
    Constant,
    FOLArgument,
    Predicate,
    PredicateConnective,
    PredicateExpression,
    QuantifiedExpression,
    Quantifier,
    Variable,
)
from logos.z3_session import CheckResult, Z3Session

JSONValue = Any

SCHEMA_VERSION = "1.0"

PROPOSITIONAL_CLAIM = "propositional"
FOL_CLAIM = "fol"
Z3_SESSION_CLAIM = "z3_session"
COMPOSED_CLAIM = "composed"


@dataclass(frozen=True)
class ProofCertificate:
    """Serializable proof-carrying certificate."""

    claim: JSONValue
    method: str
    verified: bool
    timestamp: str
    verification_artifact: dict[str, JSONValue]
    claim_type: str
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, JSONValue]:
        """Convert to JSON-safe dictionary."""
        return {
            "schema_version": self.schema_version,
            "claim_type": self.claim_type,
            "claim": self.claim,
            "method": self.method,
            "verified": self.verified,
            "timestamp": self.timestamp,
            "verification_artifact": self.verification_artifact,
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, JSONValue]) -> "ProofCertificate":
        """Create a certificate from dict payload."""
        required_keys = {
            "schema_version",
            "claim_type",
            "claim",
            "method",
            "verified",
            "timestamp",
            "verification_artifact",
        }
        missing = sorted(required_keys - set(data.keys()))
        if missing:
            raise ValueError(f"Certificate payload missing fields: {', '.join(missing)}")

        schema_version = data["schema_version"]
        if not isinstance(schema_version, str):
            raise ValueError("Certificate field 'schema_version' must be a string")
        if schema_version != SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported certificate schema version '{schema_version}'"
            )

        claim_type = data["claim_type"]
        if not isinstance(claim_type, str):
            raise ValueError("Certificate field 'claim_type' must be a string")

        method = data["method"]
        if not isinstance(method, str):
            raise ValueError("Certificate field 'method' must be a string")

        verified = data["verified"]
        if not isinstance(verified, bool):
            raise ValueError("Certificate field 'verified' must be a bool")

        timestamp = data["timestamp"]
        if not isinstance(timestamp, str):
            raise ValueError("Certificate field 'timestamp' must be a string")

        artifact = data["verification_artifact"]
        if not isinstance(artifact, dict):
            raise ValueError("Certificate field 'verification_artifact' must be an object")

        return cls(
            schema_version=schema_version,
            claim_type=claim_type,
            claim=data["claim"],
            method=method,
            verified=verified,
            timestamp=timestamp,
            verification_artifact=artifact,
        )

    @classmethod
    def from_json(cls, raw_json: str) -> "ProofCertificate":
        """Deserialize from JSON string."""
        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError("Invalid certificate JSON") from exc

        if not isinstance(parsed, dict):
            raise ValueError("Certificate JSON must be an object")

        payload = {str(k): v for k, v in parsed.items()}
        return cls.from_dict(payload)


def certify(claim: str | FOLArgument | Z3Session) -> ProofCertificate:
    """Create a proof certificate from a supported claim type."""
    timestamp = datetime.now(timezone.utc).isoformat()

    if isinstance(claim, str):
        result = verify(claim)
        return ProofCertificate(
            schema_version=SCHEMA_VERSION,
            claim_type=PROPOSITIONAL_CLAIM,
            claim=claim,
            method="z3_propositional",
            verified=result.valid,
            timestamp=timestamp,
            verification_artifact=_verification_result_artifact(result),
        )

    if isinstance(claim, FOLArgument):
        verifier = PredicateVerifier()
        result = verifier.verify(claim)
        return ProofCertificate(
            schema_version=SCHEMA_VERSION,
            claim_type=FOL_CLAIM,
            claim=_serialize_fol_argument(claim),
            method="z3_fol",
            verified=result.valid,
            timestamp=timestamp,
            verification_artifact=_verification_result_artifact(result),
        )

    if isinstance(claim, Z3Session):
        check_result = claim.check()
        return certify_z3_session(claim, check_result=check_result, timestamp=timestamp)

    raise TypeError("Unsupported claim type for certify()")


def certify_z3_session(
    session: Z3Session,
    check_result: CheckResult,
    timestamp: str | None = None,
) -> ProofCertificate:
    """Create a Z3 session certificate from an existing check result."""
    cert_timestamp = timestamp or datetime.now(timezone.utc).isoformat()
    return ProofCertificate(
        schema_version=SCHEMA_VERSION,
        claim_type=Z3_SESSION_CLAIM,
        claim=_serialize_session_claim(session),
        method="z3_session",
        verified=check_result.satisfiable is True,
        timestamp=cert_timestamp,
        verification_artifact=_check_result_artifact(check_result),
    )


def verify_certificate(certificate: ProofCertificate) -> bool:
    """Independently re-check and validate certificate integrity."""
    if certificate.schema_version != SCHEMA_VERSION:
        raise ValueError(
            f"Unsupported certificate schema version '{certificate.schema_version}'"
        )

    if certificate.claim_type == PROPOSITIONAL_CLAIM:
        if not isinstance(certificate.claim, str):
            raise ValueError("Propositional claim must be a string")
        return verify(certificate.claim).valid == certificate.verified

    if certificate.claim_type == FOL_CLAIM:
        if not isinstance(certificate.claim, dict):
            raise ValueError("FOL claim must be an object")
        argument = _deserialize_fol_argument(certificate.claim)
        return PredicateVerifier().verify(argument).valid == certificate.verified

    if certificate.claim_type == Z3_SESSION_CLAIM:
        if not isinstance(certificate.claim, dict):
            raise ValueError("Z3 session claim must be an object")
        session = _deserialize_session_claim(certificate.claim)
        return (session.check().satisfiable is True) == certificate.verified

    if certificate.claim_type == COMPOSED_CLAIM:
        if not isinstance(certificate.claim, dict):
            raise ValueError("Composed claim must be an object")
        sub_certs_data = certificate.claim.get("sub_certificates")
        if not isinstance(sub_certs_data, list):
            raise ValueError("Composed claim requires 'sub_certificates' list")
        all_valid = all(
            verify_certificate(ProofCertificate.from_dict(sub_cert))
            for sub_cert in sub_certs_data
            if isinstance(sub_cert, dict)
        )
        if len(sub_certs_data) != sum(1 for sub_cert in sub_certs_data if isinstance(sub_cert, dict)):
            raise ValueError("Composed claim sub_certificates must contain only objects")
        return all_valid == certificate.verified

    raise ValueError(f"Unknown certificate claim_type '{certificate.claim_type}'")


def _verification_result_artifact(result: VerificationResult) -> dict[str, JSONValue]:
    return {
        "rule": result.rule,
        "explanation": result.explanation,
        "counterexample": result.counterexample,
    }


def _check_result_artifact(result: CheckResult) -> dict[str, JSONValue]:
    artifact: dict[str, JSONValue] = {
        "status": result.status,
        "satisfiable": result.satisfiable,
        "model": result.model,
        "unsat_core": result.unsat_core,
        "reason": result.reason,
    }
    if result.diagnostic is not None:
        artifact["diagnostic"] = {
            "error_type": result.diagnostic.error_type.value,
            "message": result.diagnostic.message,
            "suggestions": result.diagnostic.suggestions,
            "context": result.diagnostic.context,
        }
    return artifact


def _serialize_fol_argument(argument: FOLArgument) -> dict[str, JSONValue]:
    return {
        "premises": [_serialize_fol_formula(formula) for formula in argument.premises],
        "conclusion": _serialize_fol_formula(argument.conclusion),
    }


def _deserialize_fol_argument(data: dict[str, JSONValue]) -> FOLArgument:
    premises = data.get("premises")
    conclusion = data.get("conclusion")

    if not isinstance(premises, list):
        raise ValueError("FOL claim requires list field 'premises'")
    if not isinstance(conclusion, dict):
        raise ValueError("FOL claim requires object field 'conclusion'")

    deserialized_premises = tuple(_deserialize_fol_formula(item) for item in premises)
    return FOLArgument(
        premises=deserialized_premises,
        conclusion=_deserialize_fol_formula(conclusion),
    )


def _serialize_fol_formula(formula: Any) -> dict[str, JSONValue]:
    if isinstance(formula, Predicate):
        return {
            "kind": "predicate",
            "name": formula.name,
            "terms": [_serialize_term(term) for term in formula.terms],
        }

    if isinstance(formula, PredicateExpression):
        data: dict[str, JSONValue] = {
            "kind": "expression",
            "connective": formula.connective.name,
            "left": _serialize_fol_formula(formula.left),
        }
        if formula.right is not None:
            data["right"] = _serialize_fol_formula(formula.right)
        return data

    if isinstance(formula, QuantifiedExpression):
        return {
            "kind": "quantified",
            "quantifier": formula.quantifier.name,
            "variable": formula.variable.name,
            "expression": _serialize_fol_formula(formula.expression),
        }

    raise ValueError(f"Unsupported FOL formula type: {type(formula)}")


def _deserialize_fol_formula(data: JSONValue) -> Any:
    if not isinstance(data, dict):
        raise ValueError("FOL formula must be an object")

    kind = data.get("kind")
    if kind == "predicate":
        name = data.get("name")
        terms = data.get("terms")
        if not isinstance(name, str) or not isinstance(terms, list):
            raise ValueError("Invalid predicate payload")
        return Predicate(name=name, terms=tuple(_deserialize_term(t) for t in terms))

    if kind == "expression":
        connective = data.get("connective")
        left = data.get("left")
        if not isinstance(connective, str):
            raise ValueError("Expression payload requires 'connective'")
        if left is None:
            raise ValueError("Expression payload requires 'left'")
        right = data.get("right")
        right_formula = _deserialize_fol_formula(right) if right is not None else None
        return PredicateExpression(
            connective=PredicateConnective[connective],
            left=_deserialize_fol_formula(left),
            right=right_formula,
        )

    if kind == "quantified":
        quantifier = data.get("quantifier")
        variable = data.get("variable")
        expression = data.get("expression")
        if not isinstance(quantifier, str) or not isinstance(variable, str):
            raise ValueError("Quantified payload requires 'quantifier' and 'variable'")
        if expression is None:
            raise ValueError("Quantified payload requires 'expression'")
        return QuantifiedExpression(
            quantifier=Quantifier[quantifier],
            variable=Variable(variable),
            expression=_deserialize_fol_formula(expression),
        )

    raise ValueError(f"Unsupported FOL formula kind: {kind}")


def _serialize_term(term: Variable | Constant) -> dict[str, JSONValue]:
    if isinstance(term, Variable):
        return {"kind": "variable", "name": term.name}
    return {"kind": "constant", "name": term.name}


def _deserialize_term(data: JSONValue) -> Variable | Constant:
    if not isinstance(data, dict):
        raise ValueError("FOL term must be an object")
    kind = data.get("kind")
    name = data.get("name")
    if not isinstance(name, str):
        raise ValueError("FOL term requires string field 'name'")
    if kind == "variable":
        return Variable(name)
    if kind == "constant":
        return Constant(name)
    raise ValueError(f"Unsupported FOL term kind: {kind}")


def _serialize_session_claim(session: Z3Session) -> dict[str, JSONValue]:
    constraints = list(getattr(session, "_assertions", []))
    serialized_variables: list[dict[str, JSONValue]] = []
    variables = getattr(session, "_variables", {})
    for name, variable in variables.items():
        sort_name, size = _serialize_sort(variable)
        serialized_variables.append({"name": name, "sort": sort_name, "size": size})

    return {
        "variables": serialized_variables,
        "constraints": constraints,
        "timeout_ms": session.timeout_ms,
        "track_unsat_core": session.track_unsat_core,
    }


def _deserialize_session_claim(data: dict[str, JSONValue]) -> Z3Session:
    timeout_ms = data.get("timeout_ms")
    track_unsat_core = data.get("track_unsat_core")
    variables = data.get("variables")
    constraints = data.get("constraints")

    if not isinstance(timeout_ms, int):
        raise ValueError("Z3 claim requires integer field 'timeout_ms'")
    if not isinstance(track_unsat_core, bool):
        raise ValueError("Z3 claim requires bool field 'track_unsat_core'")
    if not isinstance(variables, list):
        raise ValueError("Z3 claim requires list field 'variables'")
    if not isinstance(constraints, list):
        raise ValueError("Z3 claim requires list field 'constraints'")

    session = Z3Session(timeout_ms=timeout_ms, track_unsat_core=track_unsat_core)

    for variable_data in variables:
        if not isinstance(variable_data, dict):
            raise ValueError("Variable declarations must be objects")
        name = variable_data.get("name")
        sort = variable_data.get("sort")
        size = variable_data.get("size")
        if not isinstance(name, str) or not isinstance(sort, str):
            raise ValueError("Variable declarations require string fields 'name' and 'sort'")
        if size is not None and not isinstance(size, int):
            raise ValueError("Variable declaration field 'size' must be int or null")
        session.declare(name=name, sort=sort, size=size)

    for constraint in constraints:
        if not isinstance(constraint, str):
            raise ValueError("Constraint entries must be strings")
        session.assert_constraint(constraint)

    return session


def _serialize_sort(variable: Any) -> tuple[str, int | None]:
    sort = variable.sort()
    if z3.is_int(variable):
        return "Int", None
    if z3.is_real(variable):
        return "Real", None
    if z3.is_bool(variable):
        return "Bool", None
    if z3.is_bv(variable):
        return "BitVec", sort.size()
    raise ValueError(f"Unsupported Z3 variable sort: {sort}")
