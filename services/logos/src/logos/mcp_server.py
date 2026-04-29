"""MCP stdio server exposing LogicBrain tools."""

# mypy: disable-error-code="import-not-found,no-untyped-call"

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import cast

try:
    import anyio
    import mcp.types as mcp_types
    from mcp.server import NotificationOptions, Server
    from mcp.server.stdio import stdio_server
except ImportError as exc:  # pragma: no cover
    raise ImportError("MCP SDK is not installed. Install with: pip install logic-brain[mcp]") from exc

from logos.mcp_tools import (
    certificate_store,
    certify_claim,
    check_assumptions,
    check_beliefs,
    check_contract,
    check_policy,
    counterfactual_branch,
    orchestrate_proof,
    proof_carrying_action,
    verify_argument,
    z3_check,
    z3_session,
)

ToolHandler = Callable[[dict[str, object]], dict[str, object]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, object]
    handler: ToolHandler


_VARIABLE_SPEC_SCHEMA: dict[str, object] = {
    "anyOf": [
        {"type": "string"},
        {
            "type": "object",
            "properties": {
                "sort": {"type": "string"},
                "size": {"type": "integer"},
            },
            "required": ["sort"],
            "additionalProperties": False,
        },
    ]
}
_ASSUMPTION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "statement": {"type": "string"},
        "kind": {"type": "string", "enum": ["fact", "assumption", "hypothesis"]},
    },
    "required": ["id", "statement", "kind"],
    "additionalProperties": False,
}
_RULE_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "name": {"type": "string"},
        "severity": {"type": "string", "enum": ["error", "warning"]},
        "message": {"type": "string"},
        "when_true": {"type": "array", "items": {"type": "string"}},
        "when_false": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["name", "severity", "message"],
    "additionalProperties": False,
}
_SESSION_ACTION_SCHEMA: dict[str, object] = {
    "type": "string",
    "enum": ["create", "declare", "assert", "check", "push", "pop", "destroy"],
}
_BELIEF_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "statement": {"type": "string"},
    },
    "required": ["id", "statement"],
    "additionalProperties": False,
}
_ORCHESTRATOR_ACTION_SCHEMA: dict[str, object] = {
    "type": "string",
    "enum": [
        "create_root",
        "add_sub_claim",
        "verify_leaf",
        "attach_certificate",
        "mark_failed",
        "propagate",
        "status",
        "get_tree",
    ],
}
_POSTCONDITION_SCHEMA: dict[str, object] = {
    "type": "object",
    "properties": {
        "path": {"type": "string"},
        "equals": {},
    },
    "required": ["path"],
    "additionalProperties": False,
}
_CERT_STORE_ACTION_SCHEMA: dict[str, object] = {
    "type": "string",
    "enum": ["store", "get", "query", "invalidate", "stats", "compact", "query_consistent"],
}


def _tool(
    name: str,
    description: str,
    properties: dict[str, object],
    required: list[str],
    handler: ToolHandler,
) -> ToolSpec:
    return ToolSpec(
        name=name,
        description=description,
        input_schema={
            "type": "object",
            "properties": properties,
            "required": required,
            "additionalProperties": False,
        },
        handler=handler,
    )


_TOOLS: tuple[ToolSpec, ...] = (
    _tool(
        "verify_argument",
        "Verify a logical argument and return a proof summary. Example: {'argument': 'P -> Q, P |- Q'}",
        {"argument": {"type": "string", "description": "Argument string to verify."}},
        ["argument"],
        verify_argument,
    ),
    _tool(
        "certify_claim",
        "Verify a logical argument and return a serializable proof certificate. "
        "Example: {'argument': 'P -> Q, P |- Q'}",
        {"argument": {"type": "string", "description": "Argument to certify."}},
        ["argument"],
        certify_claim,
    ),
    _tool(
        "certificate_store",
        "Manage proof memory for stored certificates. Actions: store, get, query, invalidate, stats, "
        "compact (Z3-verified redundancy removal), query_consistent (Z3 consistency-filtered retrieval). "
        "Example: {'action': 'stats'}",
        {
            "action": _CERT_STORE_ACTION_SCHEMA,
            "certificate": {
                "type": "object",
                "description": "ProofCertificate payload for the 'store' action.",
            },
            "certificate_json": {
                "type": "string",
                "description": "Serialized ProofCertificate JSON for the 'store' action.",
            },
            "tags": {
                "type": "object",
                "description": "Optional string tags merged onto the stored entry.",
                "additionalProperties": {"type": "string"},
            },
            "store_id": {"type": "string", "description": "Stored certificate identifier."},
            "claim_pattern": {"type": "string", "description": "Substring to match against the claim."},
            "method": {"type": "string", "description": "Exact certificate method to match."},
            "verified": {"type": "boolean", "description": "Optional verified-state filter."},
            "include_invalidated": {"type": "boolean", "description": "Include invalidated entries in query results."},
            "since": {"type": "string", "description": "Only return entries stored at or after this ISO timestamp."},
            "limit": {"type": "integer", "description": "Maximum number of query results to return."},
            "reason": {"type": "string", "description": "Invalidation reason for the 'invalidate' action."},
            "premises": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Propositional premises for the 'query_consistent' action.",
            },
        },
        ["action"],
        certificate_store,
    ),
    _tool(
        "check_assumptions",
        "Check whether assumptions are jointly satisfiable via Z3. "
        "Example: {'assumptions': [{'id': 'a1', 'statement': 'x > 0', "
        "'kind': 'assumption'}], 'variables': {'x': 'Int'}}",
        {
            "assumptions": {
                "type": "array",
                "description": "Assumptions to load into an AssumptionSet.",
                "items": _ASSUMPTION_SCHEMA,
            },
            "variables": {
                "type": "object",
                "description": "Optional Z3 sorts keyed by variable name.",
                "additionalProperties": {"type": "string"},
            },
        },
        ["assumptions"],
        check_assumptions,
    ),
    _tool(
        "check_beliefs",
        "Check a set of beliefs for Z3 consistency and identify contradictions. "
        "Example: {'beliefs': [{'id': 'b1', 'statement': 'x > 0'}, "
        "{'id': 'b2', 'statement': 'x < -5'}], 'variables': {'x': 'Int'}}",
        {
            "beliefs": {
                "type": "array",
                "description": "Beliefs to check for consistency.",
                "items": _BELIEF_SCHEMA,
            },
            "variables": {
                "type": "object",
                "description": "Optional Z3 sorts keyed by variable name.",
                "additionalProperties": {"type": "string"},
            },
        },
        ["beliefs"],
        check_beliefs,
    ),
    _tool(
        "counterfactual_branch",
        "Evaluate named branches against shared base constraints. "
        "Example: {'variables': {'x': 'Int'}, 'base_constraints': ['x > 0'], "
        "'branches': {'b1': ['x < 10']}}",
        {
            "variables": {
                "type": "object",
                "description": "Variable declarations keyed by name.",
                "additionalProperties": _VARIABLE_SPEC_SCHEMA,
            },
            "base_constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Constraints applied to every branch.",
            },
            "branches": {
                "type": "object",
                "description": "Named branch constraints.",
                "additionalProperties": {"type": "array", "items": {"type": "string"}},
            },
        },
        ["variables", "base_constraints", "branches"],
        counterfactual_branch,
    ),
    _tool(
        "z3_check",
        "Run a direct satisfiability check. Example: {'variables': {'x': 'Int'}, 'constraints': ['x > 0', 'x < 10']}",
        {
            "variables": {
                "type": "object",
                "description": "Variable declarations keyed by name.",
                "additionalProperties": _VARIABLE_SPEC_SCHEMA,
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Constraints to assert into one Z3 session.",
            },
        },
        ["variables", "constraints"],
        z3_check,
    ),
    _tool(
        "check_contract",
        "Verify goal contract preconditions against Z3 state constraints. "
        "Example: {'contract': {'contract_id': 'c1', 'preconditions': ['x > 0']}, "
        "'state_constraints': ['x == 5'], 'variables': {'x': 'Int'}}",
        {
            "contract": {
                "type": "object",
                "description": "Goal contract with preconditions, invariants, etc.",
                "properties": {
                    "contract_id": {"type": "string"},
                    "preconditions": {"type": "array", "items": {"type": "string"}},
                    "invariants": {"type": "array", "items": {"type": "string"}},
                    "completion_criteria": {"type": "array", "items": {"type": "string"}},
                    "abort_criteria": {"type": "array", "items": {"type": "string"}},
                    "permitted_strategies": {"type": "array", "items": {"type": "string"}},
                },
                "required": ["contract_id"],
            },
            "state_constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Z3-parseable state constraints.",
            },
            "variables": {
                "type": "object",
                "description": "Optional Z3 sorts keyed by variable name.",
                "additionalProperties": {"type": "string"},
            },
        },
        ["contract", "state_constraints"],
        check_contract,
    ),
    _tool(
        "check_policy",
        "Evaluate an action against policy rules. Example: {'rules': "
        "[{'name': 'needs_tests', 'severity': 'error', 'message': 'Add tests'}], "
        "'action': {'public_api': True}}",
        {
            "rules": {"type": "array", "items": _RULE_SCHEMA},
            "action": {
                "type": "object",
                "description": "Boolean action flags keyed by field name.",
                "additionalProperties": {"type": "boolean"},
            },
        },
        ["rules", "action"],
        check_policy,
    ),
    _tool(
        "z3_session",
        "Manage a stateful Z3 session across multiple MCP calls. Example: {'action': 'create', 'session_id': 'demo'}",
        {
            "action": _SESSION_ACTION_SCHEMA,
            "session_id": {"type": "string", "description": "Stable session identifier."},
            "variables": {
                "type": "object",
                "description": "Variables to declare for the 'declare' action.",
                "additionalProperties": _VARIABLE_SPEC_SCHEMA,
            },
            "constraints": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Constraints to assert for the 'assert' action.",
            },
            "count": {
                "type": "integer",
                "description": "Optional number of scopes to pop for the 'pop' action.",
            },
        },
        ["action", "session_id"],
        z3_session,
    ),
    _tool(
        "orchestrate_proof",
        "Manage a compositional proof tree. Create claims, verify sub-claims, "
        "propagate results. Example: {'action': 'create_root', 'session_id': "
        "'demo', 'claim_id': 'main', 'description': 'Main claim'}",
        {
            "action": _ORCHESTRATOR_ACTION_SCHEMA,
            "session_id": {"type": "string", "description": "Stable orchestrator session ID."},
            "claim_id": {"type": "string", "description": "Claim identifier."},
            "parent_id": {"type": "string", "description": "Parent claim ID for sub-claims."},
            "description": {"type": "string", "description": "Human-readable claim description."},
            "expression": {"type": "string", "description": "Logical expression to verify (for verify_leaf)."},
            "composition_rule": {"type": "string", "description": "Boolean rule over sub-claim IDs."},
            "certificate_json": {"type": "string", "description": "Serialized ProofCertificate JSON."},
            "reason": {"type": "string", "description": "Failure reason (for mark_failed)."},
        },
        ["action", "session_id"],
        orchestrate_proof,
    ),
    _tool(
        "proof_carrying_action",
        "Execute an action envelope only when precondition certificates verify and expected postconditions hold.",
        {
            "schema_version": {"type": "string"},
            "intent": {"type": "string", "description": "Why the action is being executed."},
            "action": {
                "type": "string",
                "description": "Registered action adapter such as verify_argument or check_policy.",
            },
            "payload": {
                "type": "object",
                "description": "Action-specific payload passed to the adapter.",
            },
            "preconditions": {
                "type": "array",
                "items": {"type": "string"},
                "description": "Certificate refs that must be present and independently verified.",
            },
            "expected_postconditions": {
                "type": "array",
                "items": _POSTCONDITION_SCHEMA,
                "description": "Expected fields in the action result.",
            },
            "cert_refs": {
                "type": "object",
                "description": "Certificate refs keyed by name. Values may be certificate objects or JSON strings.",
            },
            "metadata": {
                "type": "object",
                "description": "Optional trace metadata preserved in the execution trace.",
            },
        },
        ["intent", "action", "payload"],
        proof_carrying_action,
    ),
)


def create_server() -> Server[object, object]:
    """Create the low-level MCP server with registered LogicBrain tools."""
    server: Server[object, object] = Server(
        name="logic-brain",
        instructions="LogicBrain exposes deterministic reasoning tools backed by Z3.",
    )

    list_tools_decorator = cast(
        Callable[[Callable[[], object]], Callable[[], object]],
        server.list_tools(),
    )

    @list_tools_decorator
    async def list_tools() -> list[mcp_types.Tool]:
        return [
            mcp_types.Tool(
                name=tool.name,
                description=tool.description,
                inputSchema=tool.input_schema,
            )
            for tool in _TOOLS
        ]

    call_tool_decorator = cast(
        Callable[[Callable[[str, dict[str, object]], object]], Callable[[str, dict[str, object]], object]],
        server.call_tool(),
    )

    @call_tool_decorator
    async def call_tool(name: str, arguments: dict[str, object]) -> dict[str, object]:
        for tool in _TOOLS:
            if tool.name == name:
                return tool.handler(arguments)
        raise ValueError(f"Unknown tool '{name}'")

    return server


async def _serve_stdio() -> None:
    server = create_server()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(
                notification_options=NotificationOptions(),
            ),
        )


def main() -> None:
    """Run the LogicBrain MCP server over stdio."""
    anyio.run(_serve_stdio)


if __name__ == "__main__":
    main()
