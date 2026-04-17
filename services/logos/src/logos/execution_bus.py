"""Proof-carrying action envelopes for cross-tool execution."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from typing import Any

from logos.certificate import ProofCertificate, verify_certificate
from logos.proof_exchange import ProofBundle, create_proof_bundle, verify_proof_bundle
from logos.schema_utils import (
    require_dict,
    require_list,
    require_optional_str,
    require_str,
)

JSONValue = Any
SCHEMA_VERSION = "1.0"

ToolAdapter = Callable[[Mapping[str, object]], dict[str, object]]


@dataclass(frozen=True)
class PostconditionCheck:
    """One expected property of an action result."""

    path: str
    equals: JSONValue

    def to_dict(self) -> dict[str, JSONValue]:
        return {"path": self.path, "equals": self.equals}

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "PostconditionCheck":
        path = require_str(
            payload.get("path"),
            "Postcondition field 'path' must be a string",
        )
        if not path.strip():
            raise ValueError("Postcondition field 'path' must be a non-empty string")
        return cls(path=path, equals=payload.get("equals"))


@dataclass(frozen=True)
class ActionEnvelope:
    """Serializable proof-carrying action request."""

    intent: str
    action: str
    payload: dict[str, object]
    preconditions: tuple[str, ...] = ()
    expected_postconditions: tuple[PostconditionCheck, ...] = ()
    cert_refs: dict[str, ProofCertificate] = field(default_factory=dict)
    metadata: dict[str, JSONValue] = field(default_factory=dict)
    schema_version: str = SCHEMA_VERSION

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "schema_version": self.schema_version,
            "intent": self.intent,
            "action": self.action,
            "payload": self.payload,
            "preconditions": list(self.preconditions),
            "expected_postconditions": [item.to_dict() for item in self.expected_postconditions],
            "cert_refs": {
                ref: certificate.to_dict() for ref, certificate in sorted(self.cert_refs.items())
            },
            "metadata": dict(self.metadata),
        }

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "ActionEnvelope":
        schema_version = require_optional_str(
            payload.get("schema_version"),
            "Envelope field 'schema_version' must be a string or null",
        )
        if schema_version is None:
            schema_version = SCHEMA_VERSION
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported action envelope schema version '{schema_version}'")

        intent = require_str(payload.get("intent"), "Envelope field 'intent' must be a string")
        action = require_str(payload.get("action"), "Envelope field 'action' must be a string")
        payload_dict = require_dict(
            payload.get("payload", {}),
            "Envelope field 'payload' must be an object",
        )
        preconditions = tuple(
            require_str(item, "Envelope field 'preconditions' must be list[str]")
            for item in require_list(
                payload.get("preconditions", []),
                "Envelope field 'preconditions' must be a list",
            )
        )
        expected_postconditions = tuple(
            PostconditionCheck.from_dict(
                require_dict(item, "Envelope field 'expected_postconditions' must contain objects")
            )
            for item in require_list(
                payload.get("expected_postconditions", []),
                "Envelope field 'expected_postconditions' must be a list",
            )
        )
        cert_ref_payload = require_dict(
            payload.get("cert_refs", {}),
            "Envelope field 'cert_refs' must be an object",
        )
        cert_refs = {
            ref: _certificate_from_value(value) for ref, value in sorted(cert_ref_payload.items())
        }
        metadata = require_dict(
            payload.get("metadata", {}),
            "Envelope field 'metadata' must be an object",
        )

        if not intent.strip():
            raise ValueError("Envelope field 'intent' must be a non-empty string")
        if not action.strip():
            raise ValueError("Envelope field 'action' must be a non-empty string")

        return cls(
            schema_version=schema_version,
            intent=intent.strip(),
            action=action.strip(),
            payload=payload_dict,
            preconditions=tuple(item.strip() for item in preconditions),
            expected_postconditions=expected_postconditions,
            cert_refs=cert_refs,
            metadata=metadata,
        )


@dataclass(frozen=True)
class ActionBusResult:
    """Structured result of executing an action envelope."""

    status: str
    accepted: bool
    diagnostics: tuple[dict[str, JSONValue], ...]
    trace: dict[str, JSONValue]
    action_result: dict[str, JSONValue] | None
    rollback_recommendations: tuple[str, ...]
    proof_bundle: ProofBundle | None
    bundle_diagnostics: tuple[dict[str, str], ...]

    def to_dict(self) -> dict[str, JSONValue]:
        return {
            "status": self.status,
            "accepted": self.accepted,
            "diagnostics": [dict(item) for item in self.diagnostics],
            "trace": dict(self.trace),
            "action_result": self.action_result,
            "rollback_recommendations": list(self.rollback_recommendations),
            "proof_bundle_json": None if self.proof_bundle is None else self.proof_bundle.to_json(),
            "bundle_diagnostics": [dict(item) for item in self.bundle_diagnostics],
        }


def execute_action_envelope(
    envelope: ActionEnvelope,
    adapters: Mapping[str, ToolAdapter],
) -> ActionBusResult:
    """Execute an action only if certificates and postconditions validate."""
    precondition_trace, precondition_diagnostics = _validate_preconditions(envelope)
    trace: dict[str, JSONValue] = {
        "schema_version": envelope.schema_version,
        "intent": envelope.intent,
        "action": envelope.action,
        "payload": dict(envelope.payload),
        "preconditions": precondition_trace,
        "metadata": dict(envelope.metadata),
    }
    if precondition_diagnostics:
        diagnostics = tuple(precondition_diagnostics)
        trace["decision"] = "rejected_preconditions"
        trace["postconditions"] = []
        return ActionBusResult(
            status="rejected_preconditions",
            accepted=False,
            diagnostics=diagnostics,
            trace=trace,
            action_result=None,
            rollback_recommendations=(
                "Refresh or regenerate every referenced precondition certificate before retrying the action.",
                "Do not execute downstream actions until all required certificates independently verify "
                "with verified=True.",
            ),
            proof_bundle=None,
            bundle_diagnostics=(),
        )

    adapter = adapters.get(envelope.action)
    if adapter is None:
        diagnostic = {
            "code": "unknown_action",
            "message": f"No action adapter registered for '{envelope.action}'",
            "action": envelope.action,
        }
        trace["decision"] = "rejected_unknown_action"
        trace["postconditions"] = []
        return ActionBusResult(
            status="rejected_unknown_action",
            accepted=False,
            diagnostics=(diagnostic,),
            trace=trace,
            action_result=None,
            rollback_recommendations=(
                "Register an adapter for the requested action or change the envelope to a supported action.",
            ),
            proof_bundle=None,
            bundle_diagnostics=(),
        )

    action_result = adapter(envelope.payload)
    normalized_action_result = {str(key): value for key, value in action_result.items()}
    trace["action_result"] = normalized_action_result

    postcondition_trace, postcondition_diagnostics = _evaluate_postconditions(
        envelope.expected_postconditions,
        normalized_action_result,
    )
    trace["postconditions"] = postcondition_trace

    proof_bundle, bundle_diagnostics = _build_proof_bundle(envelope, normalized_action_result)
    if proof_bundle is not None:
        trace["proof_bundle_roots"] = list(proof_bundle.roots)

    if postcondition_diagnostics:
        trace["decision"] = "postcondition_mismatch"
        return ActionBusResult(
            status="postcondition_mismatch",
            accepted=True,
            diagnostics=tuple(postcondition_diagnostics),
            trace=trace,
            action_result=normalized_action_result,
            rollback_recommendations=_postcondition_recommendations(postcondition_trace),
            proof_bundle=proof_bundle,
            bundle_diagnostics=tuple(bundle_diagnostics),
        )

    trace["decision"] = "completed"
    return ActionBusResult(
        status="completed",
        accepted=True,
        diagnostics=(),
        trace=trace,
        action_result=normalized_action_result,
        rollback_recommendations=(),
        proof_bundle=proof_bundle,
        bundle_diagnostics=tuple(bundle_diagnostics),
    )


def _certificate_from_value(value: object) -> ProofCertificate:
    if isinstance(value, str):
        return ProofCertificate.from_json(value)
    if isinstance(value, dict):
        return ProofCertificate.from_dict({str(key): item for key, item in value.items()})
    raise ValueError("Certificate references must map to certificate JSON strings or objects")


def _validate_preconditions(
    envelope: ActionEnvelope,
) -> tuple[list[dict[str, JSONValue]], list[dict[str, JSONValue]]]:
    trace: list[dict[str, JSONValue]] = []
    diagnostics: list[dict[str, JSONValue]] = []

    for ref in sorted(envelope.preconditions):
        certificate = envelope.cert_refs.get(ref)
        if certificate is None:
            trace.append({"ref": ref, "present": False, "verified": False})
            diagnostics.append(
                {
                    "code": "missing_precondition_certificate",
                    "message": f"Precondition '{ref}' has no attached certificate",
                    "ref": ref,
                }
            )
            continue

        independent_verification = verify_certificate(certificate)
        verified = certificate.verified and independent_verification is True
        trace.append(
            {
                "ref": ref,
                "present": True,
                "verified": verified,
                "claim_type": certificate.claim_type,
                "method": certificate.method,
            }
        )
        if not verified:
            diagnostics.append(
                {
                    "code": "invalid_precondition_certificate",
                    "message": f"Precondition '{ref}' does not carry a valid verified certificate",
                    "ref": ref,
                }
            )

    return trace, diagnostics


def _evaluate_postconditions(
    checks: tuple[PostconditionCheck, ...],
    action_result: Mapping[str, JSONValue],
) -> tuple[list[dict[str, JSONValue]], list[dict[str, JSONValue]]]:
    trace: list[dict[str, JSONValue]] = []
    diagnostics: list[dict[str, JSONValue]] = []

    for check in checks:
        actual = _resolve_path(action_result, check.path)
        matched = actual == check.equals
        trace.append(
            {
                "path": check.path,
                "expected": check.equals,
                "actual": actual,
                "matched": matched,
            }
        )
        if not matched:
            diagnostics.append(
                {
                    "code": "postcondition_mismatch",
                    "message": f"Postcondition '{check.path}' did not match expected value",
                    "path": check.path,
                    "expected": check.equals,
                    "actual": actual,
                }
            )

    return trace, diagnostics


def _resolve_path(value: JSONValue, path: str) -> JSONValue:
    current = value
    for part in path.split("."):
        if isinstance(current, dict):
            if part not in current:
                return None
            current = current[part]
            continue
        if isinstance(current, list) and part.isdigit():
            index = int(part)
            if index >= len(current):
                return None
            current = current[index]
            continue
        return None
    return current


def _build_proof_bundle(
    envelope: ActionEnvelope,
    action_result: Mapping[str, JSONValue],
) -> tuple[ProofBundle | None, list[dict[str, str]]]:
    nodes: dict[str, ProofCertificate] = {}
    dependencies: dict[str, list[str]] = {}

    for ref in sorted(envelope.preconditions):
        certificate = envelope.cert_refs.get(ref)
        if certificate is not None:
            nodes[ref] = certificate

    output_certificate = action_result.get("certificate_json")
    if isinstance(output_certificate, str):
        nodes["action_output"] = ProofCertificate.from_json(output_certificate)
        dependencies["action_output"] = list(sorted(envelope.preconditions))

    if not nodes:
        return None, []

    roots = ["action_output"] if "action_output" in nodes else sorted(nodes)
    bundle = create_proof_bundle(nodes, dependencies=dependencies, roots=roots)
    verification = verify_proof_bundle(bundle)
    return bundle, verification.diagnostics


def _postcondition_recommendations(
    postcondition_trace: list[dict[str, JSONValue]],
) -> tuple[str, ...]:
    mismatched_paths = sorted(
        str(item["path"]) for item in postcondition_trace if item.get("matched") is False
    )
    joined_paths = ", ".join(mismatched_paths)
    return (
        f"Rollback or defer side effects until the postconditions hold for: {joined_paths}.",
        "Re-run the prerequisite verification or planning step and compare the new action trace "
        "against the failing envelope.",
    )
