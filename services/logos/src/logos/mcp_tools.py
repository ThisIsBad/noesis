"""Thin dict-in/dict-out wrappers for agent-facing logic tools."""

from __future__ import annotations

from collections.abc import Mapping
import hashlib

from logos.action_policy import ActionPolicyEngine, ActionPolicyRule
from logos.assumptions import AssumptionKind, AssumptionSet
from logos.belief_graph import BeliefGraph
from logos.certificate import ProofCertificate, certify
from logos.certificate_store import CertificateStore
from logos.counterfactual import CounterfactualPlanner
from logos.execution_bus import ActionEnvelope, execute_action_envelope
from logos.goal_contract import (
    SCHEMA_VERSION as GOAL_CONTRACT_SCHEMA_VERSION,
    GoalContract,
    verify_contract_preconditions_z3,
)
from logos.mcp_session_store import (
    ORCHESTRATOR_STORE,
    ExpiredSessionError,
    SessionLimitError,
    UnknownSessionError,
    Z3SessionStore,
)
from logos.orchestrator import ProofOrchestrator
from logos.parser import ParseError, verify
from logos.z3_session import Z3Session as SolverSession

ToolResult = dict[str, object]

_SESSION_STORE = Z3SessionStore()
_CERTIFICATE_STORE = CertificateStore()


def verify_argument(payload: Mapping[str, object]) -> ToolResult:
    """Verify a propositional argument and return certificate metadata."""
    try:
        data = _require_payload(payload)
        argument = _require_non_empty_str(data, "argument")

        result = verify(argument)
        certify(argument)
        return {
            "valid": result.valid,
            "rule": result.rule,
            "certificate_id": _certificate_id(argument),
            "explanation": result.explanation,
        }
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def check_assumptions(payload: Mapping[str, object]) -> ToolResult:
    """Check a set of assumptions for Z3-detectable contradictions."""
    try:
        data = _require_payload(payload)
        raw_assumptions = _require_list(data, "assumptions")
        variables = _optional_variables(data.get("variables"))

        assumptions = AssumptionSet()
        normalized: list[dict[str, str]] = []
        for item in raw_assumptions:
            assumption = _require_assumption(item)
            assumptions.add(
                assumption_id=assumption["id"],
                statement=assumption["statement"],
                kind=AssumptionKind(assumption["kind"]),
                source="mcp_tool",
            )
            normalized.append(assumption)

        consistency = assumptions.check_consistency_z3(variables=variables)
        return {
            "consistent": consistency.consistent,
            "conflict_ids": [] if consistency.consistent else _find_conflict_ids(normalized, variables),
            "explanation": _assumption_explanation(consistency.consistent, assumptions.active_statements()),
        }
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def counterfactual_branch(payload: Mapping[str, object]) -> ToolResult:
    """Evaluate multiple counterfactual branches against shared constraints."""
    try:
        data = _require_payload(payload)
        variables = _require_variable_specs(data, "variables")
        base_constraints = _require_str_list(data, "base_constraints")
        raw_branches = _require_dict(data, "branches")

        planner = CounterfactualPlanner()
        for name, spec in variables.items():
            sort, size = spec
            planner.declare(name, sort, size=size)
        for constraint in base_constraints:
            planner.assert_constraint(constraint)
        _validate_constraints(variables, base_constraints)

        branch_results: dict[str, dict[str, object | None]] = {}
        for branch_id, constraints_value in sorted(raw_branches.items()):
            if not isinstance(branch_id, str) or not branch_id:
                raise ValueError("Branch ids must be non-empty strings")
            constraints = _require_str_list_from_value(
                constraints_value,
                f"Branch '{branch_id}' must map to list[str] constraints",
            )
            branch = planner.branch(branch_id, additional_constraints=constraints)
            branch_results[branch_id] = {
                "satisfiable": branch.satisfiable,
                "status": branch.status,
                "model": None if branch.model is None else dict(branch.model),
            }

        return {"branches": branch_results}
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def z3_check(payload: Mapping[str, object]) -> ToolResult:
    """Run a satisfiability check over declared variables and constraints."""
    try:
        data = _require_payload(payload)
        variables = _require_variable_specs(data, "variables")
        constraints = _require_str_list(data, "constraints")

        session = SolverSession(track_unsat_core=True)
        for name, spec in variables.items():
            sort, size = spec
            session.declare(name, sort, size=size)
        for index, constraint in enumerate(constraints):
            session.assert_constraint(constraint, name=f"constraint_{index}")

        result = session.check()
        return {
            "satisfiable": result.satisfiable,
            "model": result.model,
            "unsat_core": result.unsat_core,
        }
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def z3_session(payload: Mapping[str, object]) -> ToolResult:
    """Manage a stateful Z3 session across multiple MCP tool calls."""
    try:
        data = _require_payload(payload)
        action = _require_non_empty_str(data, "action")
        session_id = _require_non_empty_str(data, "session_id")

        if action == "create":
            created = _SESSION_STORE.create(session_id)
            return {"session_id": created}
        if action == "destroy":
            _SESSION_STORE.destroy(session_id)
            return {"session_id": session_id, "destroyed": True}
        if action == "declare":
            variables = _require_variable_specs(data, "variables")
            declared = _SESSION_STORE.declare(session_id, variables)
            return {"session_id": session_id, "declared": declared}
        if action == "assert":
            constraints = _require_str_list(data, "constraints")
            added = _SESSION_STORE.assert_constraints(session_id, constraints)
            return {"session_id": session_id, "constraints_added": added}
        if action == "check":
            result = _SESSION_STORE.check(session_id)
            return {
                "session_id": session_id,
                "satisfiable": result.satisfiable,
                "model": result.model,
                "unsat_core": result.unsat_core,
            }
        if action == "push":
            depth = _SESSION_STORE.push(session_id)
            return {"session_id": session_id, "scope_depth": depth}
        if action == "pop":
            count = _optional_positive_int(data.get("count"), default=1)
            depth = _SESSION_STORE.pop(session_id, count=count)
            return {"session_id": session_id, "scope_depth": depth}

        raise ValueError("Field 'action' must be one of: create, declare, assert, check, push, pop, destroy")
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def certify_claim(payload: Mapping[str, object]) -> ToolResult:
    """Verify a logical claim and return a serialized certificate."""
    try:
        data = _require_payload(payload)
        argument = _require_non_empty_str(data, "argument")
        cert = certify(argument)
        serialized = cert.to_json()
        return {
            "status": "certified" if cert.verified else "refuted",
            "verified": cert.verified,
            "method": cert.method,
            "certificate_json": serialized,
            "certificate_id": _certificate_id(argument),
        }
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def certificate_store(payload: Mapping[str, object]) -> ToolResult:
    """Manage the certificate store: store, get, query, invalidate, stats."""
    try:
        data = _require_payload(payload)
        action = _require_non_empty_str(data, "action")

        if action == "store":
            certificate, duplicate = _certificate_from_store_payload(data)
            store_id = _CERTIFICATE_STORE.store(certificate, tags=_optional_tags(data.get("tags")))
            entry = _CERTIFICATE_STORE.get(store_id)
            if entry is None:  # pragma: no cover
                raise RuntimeError("Stored certificate could not be retrieved")
            return {
                "store_id": store_id,
                "stored_at": entry.stored_at,
                "duplicate": duplicate,
            }

        if action == "get":
            store_id = _require_non_empty_str(data, "store_id")
            entry = _CERTIFICATE_STORE.get(store_id)
            if entry is None:
                return {"found": False}
            return {"found": True, "entry": entry.to_dict()}

        if action == "query":
            entries = _CERTIFICATE_STORE.query(
                claim_pattern=_optional_non_empty_str(data.get("claim_pattern"), "claim_pattern"),
                method=_optional_non_empty_str(data.get("method"), "method"),
                verified=_optional_bool(data.get("verified"), "verified"),
                tags=_optional_tags(data.get("tags")),
                include_invalidated=_optional_bool(data.get("include_invalidated"), "include_invalidated") or False,
                since=_optional_non_empty_str(data.get("since"), "since"),
                limit=_optional_non_negative_int(data.get("limit"), default=50),
            )
            return {"count": len(entries), "entries": [entry.to_dict() for entry in entries]}

        if action == "invalidate":
            store_id = _require_non_empty_str(data, "store_id")
            reason = _require_non_empty_str(data, "reason")
            return _CERTIFICATE_STORE.invalidate(store_id, reason=reason).to_dict()

        if action == "stats":
            return _CERTIFICATE_STORE.stats().to_dict()

        if action == "compact":
            result = _CERTIFICATE_STORE.compact()
            return {
                "removed_count": result.removed_count,
                "retained_count": result.retained_count,
                "removed_ids": list(result.removed_ids),
                "verification_passed": result.verification_passed,
            }

        if action == "query_consistent":
            premises = _require_str_list(data, "premises")
            consistent_result = _CERTIFICATE_STORE.query_consistent(
                premises,
                verified=_optional_bool(data.get("verified"), "verified"),
                tags=_optional_tags(data.get("tags")),
                include_invalidated=_optional_bool(data.get("include_invalidated"), "include_invalidated") or False,
                limit=_optional_non_negative_int(data.get("limit"), default=50),
            )
            return {
                "consistent_count": len(consistent_result.consistent),
                "inconsistent_count": consistent_result.inconsistent_count,
                "premises_contradictory": consistent_result.premises_contradictory,
                "entries": [entry.to_dict() for entry in consistent_result.consistent],
            }

        if action == "query_ranked":
            query_text = _require_non_empty_str(data, "query")
            ranked_result = _CERTIFICATE_STORE.query_ranked(
                query_text,
                verified=_optional_bool(data.get("verified"), "verified"),
                tags=_optional_tags(data.get("tags")),
                include_invalidated=_optional_bool(data.get("include_invalidated"), "include_invalidated") or False,
                limit=_optional_non_negative_int(data.get("limit"), default=10),
            )
            return {
                "count": len(ranked_result.results),
                "total_candidates": ranked_result.total_candidates,
                "entries": [{"score": r.score, "entry": r.entry.to_dict()} for r in ranked_result.results],
            }

        raise ValueError(
            "Field 'action' must be one of: store, get, query, invalidate,"
            " stats, compact, query_consistent, query_ranked"
        )
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def check_beliefs(payload: Mapping[str, object]) -> ToolResult:
    """Check a set of beliefs for Z3 contradictions and explanations."""
    try:
        data = _require_payload(payload)
        beliefs_raw = _require_list(data, "beliefs")
        variables = _optional_variables(data.get("variables"))

        graph = BeliefGraph()
        for belief_data in beliefs_raw:
            if not isinstance(belief_data, dict):
                raise ValueError("Each belief must be an object")
            belief_id = belief_data.get("id")
            statement = belief_data.get("statement")
            if not isinstance(belief_id, str) or not isinstance(statement, str):
                raise ValueError("Belief requires string fields 'id' and 'statement'")
            graph.add_belief(belief_id=belief_id, statement=statement)

        contradictions = graph.detect_contradictions_z3(variables=variables)
        explanations = []
        for left_id, right_id in contradictions:
            explanation = graph.explain_contradiction(left_id, right_id)
            explanations.append(
                {
                    "left_id": explanation.left_id,
                    "right_id": explanation.right_id,
                    "left_support_path": list(explanation.left_support_path),
                    "right_support_path": list(explanation.right_support_path),
                    "witness_ids": list(explanation.witness_ids),
                }
            )

        status = (
            "unknown"
            if contradictions.status.value == "unknown"
            else ("consistent" if not contradictions else "contradictions_found")
        )

        return {
            "status": status,
            "belief_count": len(beliefs_raw),
            "contradiction_count": len(contradictions),
            "contradictions": [{"left": left_id, "right": right_id} for left_id, right_id in contradictions],
            "explanations": explanations,
            "reason": contradictions.reason,
        }
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def check_contract(payload: Mapping[str, object]) -> ToolResult:
    """Verify goal contract preconditions against Z3 state constraints."""
    try:
        data = _require_payload(payload)
        contract_raw = _require_dict(data, "contract")
        state_constraints = _require_str_list(data, "state_constraints")
        variables = _optional_variables(data.get("variables"))

        if "schema_version" not in contract_raw:
            contract_raw = {"schema_version": GOAL_CONTRACT_SCHEMA_VERSION, **contract_raw}
        contract = GoalContract.from_dict(contract_raw)
        result = verify_contract_preconditions_z3(contract, state_constraints, variables=variables)

        return {
            "status": result.status.value,
            "diagnostics": [
                {"code": diagnostic.code, "message": diagnostic.message} for diagnostic in result.diagnostics
            ],
            "unsat_core": list(result.unsat_core),
            "solver_status": result.solver_status,
            "reason": result.reason,
        }
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def orchestrate_proof(payload: Mapping[str, object]) -> ToolResult:
    """Manage a stateful compositional proof tree across MCP calls."""
    try:
        data = _require_payload(payload)
        action = _require_non_empty_str(data, "action")
        session_id = _require_non_empty_str(data, "session_id")

        if action == "create_root":
            claim_id = _require_non_empty_str(data, "claim_id")
            description = _require_non_empty_str(data, "description")
            orchestrator = ProofOrchestrator()
            orchestrator.claim(claim_id, description)
            ORCHESTRATOR_STORE[session_id] = orchestrator
            return {"status": "created", "session_id": session_id, "root_claim_id": claim_id}

        existing_orchestrator = ORCHESTRATOR_STORE.get(session_id)
        if existing_orchestrator is None:
            raise ValueError(f"Unknown orchestrator session '{session_id}'")
        orchestrator = existing_orchestrator

        if action == "add_sub_claim":
            claim_id = _require_non_empty_str(data, "claim_id")
            parent_id = _require_non_empty_str(data, "parent_id")
            description = _require_non_empty_str(data, "description")
            orchestrator.sub_claim(claim_id, parent_id, description)
            composition_rule = data.get("composition_rule")
            if isinstance(composition_rule, str) and composition_rule.strip():
                orchestrator.set_composition(parent_id, composition_rule)
            return {"status": "added", "claim_id": claim_id, "parent_id": parent_id}

        if action == "verify_leaf":
            claim_id = _require_non_empty_str(data, "claim_id")
            expression = _require_non_empty_str(data, "expression")
            cert = orchestrator.verify_leaf(claim_id, expression)
            return {
                "status": "verified" if cert.verified else "refuted",
                "claim_id": claim_id,
                "verified": cert.verified,
                "certificate_id": _certificate_id(cert.to_json()),
            }

        if action == "attach_certificate":
            claim_id = _require_non_empty_str(data, "claim_id")
            certificate_json = _require_non_empty_str(data, "certificate_json")
            certificate = ProofCertificate.from_json(certificate_json)
            orchestrator.attach_certificate(claim_id, certificate)
            return {"status": "attached", "claim_id": claim_id}

        if action == "mark_failed":
            claim_id = _require_non_empty_str(data, "claim_id")
            reason = str(data.get("reason", ""))
            orchestrator.mark_failed(claim_id, reason)
            return {"status": "marked_failed", "claim_id": claim_id}

        if action == "propagate":
            orchestrator.propagate()
            snapshot = orchestrator.status()
            return {
                "status": "propagated",
                "total": snapshot.total_claims,
                "verified": snapshot.verified,
                "failed": snapshot.failed,
                "pending": snapshot.pending,
                "is_complete": snapshot.is_complete,
            }

        if action == "status":
            snapshot = orchestrator.status()
            return {
                "status": "ok",
                "total": snapshot.total_claims,
                "verified": snapshot.verified,
                "failed": snapshot.failed,
                "pending": snapshot.pending,
                "is_complete": snapshot.is_complete,
            }

        if action == "get_tree":
            return {"status": "ok", "tree": orchestrator.to_dict()}

        raise ValueError(
            "Field 'action' must be one of: create_root, add_sub_claim, "
            "verify_leaf, attach_certificate, mark_failed, propagate, status, get_tree"
        )
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def proof_carrying_action(payload: Mapping[str, object]) -> ToolResult:
    """Execute a proof-carrying action envelope across existing tool adapters."""
    try:
        data = _require_payload(payload)
        envelope = ActionEnvelope.from_dict(data)
        result = execute_action_envelope(
            envelope,
            adapters={
                "verify_argument": verify_argument,
                "certify_claim": certify_claim,
                "counterfactual_branch": counterfactual_branch,
                "z3_check": z3_check,
                "check_contract": check_contract,
                "check_policy": check_policy,
                "orchestrate_proof": orchestrate_proof,
            },
        )
        return result.to_dict()
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def check_policy(payload: Mapping[str, object]) -> ToolResult:
    """Evaluate an action against policy rules."""
    try:
        data = _require_payload(payload)
        raw_rules = _require_list(data, "rules")
        action = _require_bool_map(data, "action")

        engine = ActionPolicyEngine()
        for item in raw_rules:
            engine.add_rule(_build_policy_rule(item))

        result = engine.evaluate(action)
        violations = [
            {
                "policy_name": violation.policy_name,
                "severity": violation.severity,
                "message": violation.message,
                "triggered_fields": violation.triggered_fields,
                "z3_witness": violation.z3_witness,
            }
            for violation in result.violations
        ]
        return {
            "decision": result.decision.name,
            "violations": violations,
            "remediation_hints": result.remediation_hints,
            "solver_status": result.solver_status,
            "reason": result.reason,
        }
    except Exception as exc:  # pragma: no cover - exercised via tests
        return _error_response(exc)


def _require_payload(payload: object) -> dict[str, object]:
    if not isinstance(payload, Mapping):
        raise TypeError("Tool input must be a dictionary")
    return {str(name): value for name, value in payload.items()}


def _require_dict(payload: dict[str, object], key: str) -> dict[str, object]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"Field '{key}' must be an object")
    return {str(name): item for name, item in value.items()}


def _require_list(payload: dict[str, object], key: str) -> list[object]:
    value = payload.get(key)
    if not isinstance(value, list):
        raise ValueError(f"Field '{key}' must be a list")
    return value


def _require_non_empty_str(payload: dict[str, object], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{key}' must be a non-empty string")
    return value


def _require_str_list(payload: dict[str, object], key: str) -> list[str]:
    return _require_str_list_from_value(payload.get(key), f"Field '{key}' must be a list of strings")


def _require_str_list_from_value(value: object, message: str) -> list[str]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise ValueError(message)
    return list(value)


def _optional_variables(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Field 'variables' must be an object")
    normalized: dict[str, str] = {}
    for name, sort in value.items():
        if not isinstance(name, str) or not name:
            raise ValueError("Variable names must be non-empty strings")
        if not isinstance(sort, str) or not sort:
            raise ValueError(f"Variable '{name}' must declare a non-empty sort string")
        normalized[name] = sort
    return normalized


def _require_variable_specs(
    payload: dict[str, object],
    key: str,
) -> dict[str, tuple[str, int | None]]:
    raw_variables = _require_dict(payload, key)
    normalized: dict[str, tuple[str, int | None]] = {}
    for name, spec in sorted(raw_variables.items()):
        if not name:
            raise ValueError("Variable names must be non-empty strings")
        normalized[name] = _normalize_variable_spec(name, spec)
    return normalized


def _normalize_variable_spec(name: str, spec: object) -> tuple[str, int | None]:
    if isinstance(spec, str):
        return spec, None
    if not isinstance(spec, dict):
        raise ValueError(f"Variable '{name}' must be a sort string or object")

    sort = spec.get("sort")
    if not isinstance(sort, str) or not sort:
        raise ValueError(f"Variable '{name}' requires a non-empty 'sort' string")

    size = spec.get("size")
    if size is not None and not isinstance(size, int):
        raise ValueError(f"Variable '{name}' field 'size' must be an integer")

    return sort, size


def _validate_constraints(
    variables: dict[str, tuple[str, int | None]],
    constraints: list[str],
) -> None:
    session = SolverSession()
    for name, (sort, size) in variables.items():
        session.declare(name, sort, size=size)
    for constraint in constraints:
        session.assert_constraint(constraint)


def _require_assumption(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError("Assumption entries must be objects")

    assumption_id = value.get("id")
    statement = value.get("statement")
    kind = value.get("kind")

    if not isinstance(assumption_id, str) or not assumption_id:
        raise ValueError("Assumption field 'id' must be a non-empty string")
    if not isinstance(statement, str) or not statement:
        raise ValueError("Assumption field 'statement' must be a non-empty string")
    if not isinstance(kind, str) or not kind:
        raise ValueError("Assumption field 'kind' must be a non-empty string")
    if kind not in {item.value for item in AssumptionKind}:
        raise ValueError("Assumption field 'kind' must be one of: fact, assumption, hypothesis")

    return {"id": assumption_id, "statement": statement, "kind": kind}


def _find_conflict_ids(
    assumptions: list[dict[str, str]],
    variables: dict[str, str] | None,
) -> list[str]:
    if len(assumptions) <= 1:
        return [item["id"] for item in assumptions]

    conflict_ids: list[str] = []
    for candidate in assumptions:
        reduced = [item for item in assumptions if item["id"] != candidate["id"]]
        reduced_set = AssumptionSet()
        for item in reduced:
            reduced_set.add(
                assumption_id=item["id"],
                statement=item["statement"],
                kind=AssumptionKind(item["kind"]),
                source="mcp_tool",
            )
        if reduced_set.check_consistency_z3(variables=variables).consistent:
            conflict_ids.append(candidate["id"])

    return conflict_ids or [item["id"] for item in assumptions]


def _assumption_explanation(consistent: bool, statements: list[str]) -> str:
    if consistent:
        return f"All {len(statements)} active assumptions are jointly satisfiable."
    return "The active assumptions contain a contradiction under the supplied variable declarations."


def _require_bool_map(payload: dict[str, object], key: str) -> dict[str, bool]:
    raw = _require_dict(payload, key)
    normalized: dict[str, bool] = {}
    for name, value in raw.items():
        if not isinstance(value, bool):
            raise ValueError(f"Action field '{name}' must be a boolean")
        normalized[name] = value
    return normalized


def _optional_tags(value: object) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError("Field 'tags' must be an object")
    normalized: dict[str, str] = {}
    for name, item in value.items():
        if not isinstance(name, str) or not isinstance(item, str):
            raise ValueError("Field 'tags' must be dict[str, str]")
        normalized[name] = item
    return normalized


def _optional_non_empty_str(value: object, field_name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Field '{field_name}' must be a non-empty string")
    return value


def _optional_bool(value: object, field_name: str) -> bool | None:
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"Field '{field_name}' must be a boolean")
    return value


def _optional_non_negative_int(value: object, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value < 0:
        raise ValueError("Field 'limit' must be an integer >= 0")
    return value


def _certificate_from_store_payload(data: dict[str, object]) -> tuple[ProofCertificate, bool]:
    has_dict = "certificate" in data
    has_json = "certificate_json" in data
    if has_dict == has_json:
        raise ValueError("Exactly one of 'certificate' or 'certificate_json' must be provided")

    if has_dict:
        certificate_raw = _require_dict(data, "certificate")
        certificate = ProofCertificate.from_dict(certificate_raw)
    else:
        certificate_json = _require_non_empty_str(data, "certificate_json")
        certificate = ProofCertificate.from_json(certificate_json)

    store_id = _certificate_id(certificate.to_json())
    duplicate = _CERTIFICATE_STORE.get(store_id) is not None
    return certificate, duplicate


def _optional_positive_int(value: object, default: int) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or value < 1:
        raise ValueError("Field 'count' must be an integer >= 1")
    return value


def _build_policy_rule(value: object) -> ActionPolicyRule:
    if not isinstance(value, dict):
        raise ValueError("Policy rule entries must be objects")

    name = value.get("name")
    severity = value.get("severity")
    message = value.get("message")
    when_true = value.get("when_true", [])
    when_false = value.get("when_false", [])

    if not isinstance(name, str) or not name:
        raise ValueError("Policy field 'name' must be a non-empty string")
    if not isinstance(severity, str) or not severity:
        raise ValueError("Policy field 'severity' must be a non-empty string")
    if not isinstance(message, str) or not message:
        raise ValueError("Policy field 'message' must be a non-empty string")

    return ActionPolicyRule(
        name=name,
        severity=severity,
        message=message,
        when_true=tuple(
            _require_str_list_from_value(
                when_true,
                "Policy field 'when_true' must be a list of strings",
            )
        ),
        when_false=tuple(
            _require_str_list_from_value(
                when_false,
                "Policy field 'when_false' must be a list of strings",
            )
        ),
    )


def _certificate_id(serialized_certificate: str) -> str:
    return hashlib.sha256(serialized_certificate.encode("utf-8")).hexdigest()


def _error_response(exc: Exception) -> ToolResult:
    if isinstance(exc, UnknownSessionError):
        return {"error": "Unknown session", "details": str(exc)}
    if isinstance(exc, ExpiredSessionError):
        return {"error": "Expired session", "details": str(exc)}
    if isinstance(exc, SessionLimitError):
        return {"error": "Session limit reached", "details": str(exc)}
    if isinstance(exc, (ParseError, TypeError, ValueError)):
        return {"error": "Invalid input", "details": str(exc)}
    return {"error": exc.__class__.__name__, "details": str(exc)}
