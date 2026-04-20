"""FastMCP-based HTTP/SSE transport for the Logos reasoning service.

Replaces the earlier bare-Starlette + low-level MCP Server setup. The 12
reasoning tools are re-exported as FastMCP ``@mcp.tool()`` handlers that
delegate to the existing ``logos.mcp_tools`` dict-in/dict-out functions,
so the public tool contract (JSON schema + call surface) is preserved.

Environment variables:
    PORT                  TCP port to bind (default: 8000).
    LOGOS_SECRET          Bearer token required on every non-health request.
                          Unset = open (local dev only).
    LOGOS_ALLOWED_HOSTS   Comma-separated extra Host header values accepted
                          by FastMCP's DNS-rebinding protection. Set to the
                          Railway public host in production.
    LOGOS_LOG_LEVEL       stdlib logging level (default: INFO).
    LOGOS_TRACE_ENABLED   "0"/"false" to disable Kairos span emission.
    KAIROS_URL            Base URL of the Kairos tracing service.
"""
from __future__ import annotations

import json
import logging
import os
import sys
from typing import Any, Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from logos.mcp_tools import (
    certificate_store as _raw_certificate_store,
    certify_claim as _raw_certify_claim,
    check_assumptions as _raw_check_assumptions,
    check_beliefs as _raw_check_beliefs,
    check_contract as _raw_check_contract,
    check_policy as _raw_check_policy,
    counterfactual_branch as _raw_counterfactual_branch,
    orchestrate_proof as _raw_orchestrate_proof,
    proof_carrying_action as _raw_proof_carrying_action,
    verify_argument as _raw_verify_argument,
    z3_check as _raw_z3_check,
    z3_session as _raw_z3_session,
)
from logos.tracing import get_tracer

logging.basicConfig(
    level=os.getenv("LOGOS_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("logos")

_SECRET = os.environ.get("LOGOS_SECRET", "")
log.info(
    "logos boot: port=%s secret_set=%s",
    os.getenv("PORT", "8000"),
    bool(_SECRET),
)

_allowed_hosts = [
    h.strip()
    for h in os.getenv("LOGOS_ALLOWED_HOSTS", "").split(",")
    if h.strip()
]
_transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=bool(_allowed_hosts),
    allowed_hosts=_allowed_hosts
    + ["127.0.0.1:*", "localhost:*", "[::1]:*"],
    allowed_origins=[f"https://{h}" for h in _allowed_hosts]
    + ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
)
log.info(
    "logos transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "logos",
    instructions=(
        "Logos exposes deterministic reasoning tools backed by Z3: "
        "argument verification, proof certification, assumption/belief "
        "consistency, goal-contract checking, policy evaluation, stateful "
        "Z3 sessions, counterfactual branching, and proof-carrying actions."
    ),
    transport_security=_transport_security,
)


def _pack(**kwargs: Any) -> dict[str, Any]:
    """Pack keyword arguments into a payload dict, dropping ``None`` values.

    Preserves the exact semantics of the legacy JSON schemas where optional
    fields were simply absent from the payload when unused.
    """
    return {k: v for k, v in kwargs.items() if v is not None}


def _dispatch(name: str, handler: Any, payload: dict[str, Any]) -> str:
    """Invoke a dict-in/dict-out tool handler inside a Kairos span."""
    with get_tracer().span(
        name,
        metadata={"payload_keys": ",".join(sorted(payload.keys()))},
    ):
        result = handler(payload)
    return json.dumps(result, default=str)


# ── Tool wrappers ────────────────────────────────────────────────────────────


@mcp.tool()
def verify_argument(argument: str) -> str:
    """Verify a propositional argument; return {valid, rule, certificate_id, explanation}."""
    return _dispatch("verify_argument", _raw_verify_argument, {"argument": argument})


@mcp.tool()
def certify_claim(argument: str) -> str:
    """Verify an argument and return a serialised ProofCertificate."""
    return _dispatch("certify_claim", _raw_certify_claim, {"argument": argument})


@mcp.tool()
def certificate_store(
    action: str,
    certificate: Optional[dict[str, Any]] = None,
    certificate_json: Optional[str] = None,
    tags: Optional[dict[str, str]] = None,
    store_id: Optional[str] = None,
    claim_pattern: Optional[str] = None,
    method: Optional[str] = None,
    verified: Optional[bool] = None,
    include_invalidated: Optional[bool] = None,
    since: Optional[str] = None,
    limit: Optional[int] = None,
    reason: Optional[str] = None,
    premises: Optional[list[str]] = None,
) -> str:
    """Manage proof memory: store/get/query/invalidate/stats/compact/query_consistent."""
    payload = _pack(
        action=action,
        certificate=certificate,
        certificate_json=certificate_json,
        tags=tags,
        store_id=store_id,
        claim_pattern=claim_pattern,
        method=method,
        verified=verified,
        include_invalidated=include_invalidated,
        since=since,
        limit=limit,
        reason=reason,
        premises=premises,
    )
    return _dispatch("certificate_store", _raw_certificate_store, payload)


@mcp.tool()
def check_assumptions(
    assumptions: list[dict[str, Any]],
    variables: Optional[dict[str, str]] = None,
) -> str:
    """Check whether assumptions are jointly Z3-satisfiable."""
    return _dispatch(
        "check_assumptions",
        _raw_check_assumptions,
        _pack(assumptions=assumptions, variables=variables),
    )


@mcp.tool()
def check_beliefs(
    beliefs: list[dict[str, Any]],
    variables: Optional[dict[str, str]] = None,
) -> str:
    """Detect Z3 contradictions in a set of beliefs."""
    return _dispatch(
        "check_beliefs",
        _raw_check_beliefs,
        _pack(beliefs=beliefs, variables=variables),
    )


@mcp.tool()
def check_contract(
    contract: dict[str, Any],
    state_constraints: list[str],
    variables: Optional[dict[str, str]] = None,
) -> str:
    """Verify goal-contract preconditions against Z3 state constraints."""
    return _dispatch(
        "check_contract",
        _raw_check_contract,
        _pack(contract=contract, state_constraints=state_constraints, variables=variables),
    )


@mcp.tool()
def check_policy(
    rules: list[dict[str, Any]],
    action: dict[str, bool],
) -> str:
    """Evaluate an action against policy rules; return decision + violations."""
    return _dispatch(
        "check_policy",
        _raw_check_policy,
        {"rules": rules, "action": action},
    )


@mcp.tool()
def counterfactual_branch(
    variables: dict[str, Any],
    base_constraints: list[str],
    branches: dict[str, list[str]],
) -> str:
    """Evaluate named branches against shared base constraints."""
    return _dispatch(
        "counterfactual_branch",
        _raw_counterfactual_branch,
        {
            "variables": variables,
            "base_constraints": base_constraints,
            "branches": branches,
        },
    )


@mcp.tool()
def z3_check(
    variables: dict[str, Any],
    constraints: list[str],
    timeout_ms: Optional[int] = None,
) -> str:
    """Run a direct Z3 satisfiability check."""
    return _dispatch(
        "z3_check",
        _raw_z3_check,
        _pack(variables=variables, constraints=constraints, timeout_ms=timeout_ms),
    )


@mcp.tool()
def z3_session(
    action: str,
    session_id: str,
    variables: Optional[dict[str, Any]] = None,
    constraints: Optional[list[str]] = None,
    count: Optional[int] = None,
) -> str:
    """Manage a stateful Z3 session (create/declare/assert/check/push/pop/destroy)."""
    return _dispatch(
        "z3_session",
        _raw_z3_session,
        _pack(
            action=action,
            session_id=session_id,
            variables=variables,
            constraints=constraints,
            count=count,
        ),
    )


@mcp.tool()
def orchestrate_proof(
    action: str,
    session_id: str,
    claim_id: Optional[str] = None,
    parent_id: Optional[str] = None,
    description: Optional[str] = None,
    expression: Optional[str] = None,
    composition_rule: Optional[str] = None,
    certificate_json: Optional[str] = None,
    reason: Optional[str] = None,
) -> str:
    """Manage a compositional proof tree across sub-claims."""
    return _dispatch(
        "orchestrate_proof",
        _raw_orchestrate_proof,
        _pack(
            action=action,
            session_id=session_id,
            claim_id=claim_id,
            parent_id=parent_id,
            description=description,
            expression=expression,
            composition_rule=composition_rule,
            certificate_json=certificate_json,
            reason=reason,
        ),
    )


@mcp.tool()
def proof_carrying_action(
    intent: str,
    action: str,
    payload: dict[str, Any],
    schema_version: Optional[str] = None,
    preconditions: Optional[list[str]] = None,
    expected_postconditions: Optional[list[dict[str, Any]]] = None,
    cert_refs: Optional[dict[str, Any]] = None,
    metadata: Optional[dict[str, Any]] = None,
) -> str:
    """Execute an action envelope, verifying precondition certificates + postconditions."""
    return _dispatch(
        "proof_carrying_action",
        _raw_proof_carrying_action,
        _pack(
            intent=intent,
            action=action,
            payload=payload,
            schema_version=schema_version,
            preconditions=preconditions,
            expected_postconditions=expected_postconditions,
            cert_refs=cert_refs,
            metadata=metadata,
        ),
    )


# ── HTTP app ─────────────────────────────────────────────────────────────────


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "logos"})


class _BearerAuth:
    """Pure-ASGI Bearer-token gate. BaseHTTPMiddleware buffers responses
    and breaks SSE streams, so we wrap the app at the ASGI layer instead.
    No-op when LOGOS_SECRET is unset or the path is /health."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not _SECRET or scope.get("path") == "/health":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        expected = f"Bearer {_SECRET}".encode()
        if headers.get(b"authorization") != expected:
            await JSONResponse({"error": "Unauthorized"}, status_code=401)(
                scope, receive, send
            )
            return
        await self.app(scope, receive, send)


app = mcp.sse_app()
app.routes.insert(0, Route("/health", _health, methods=["GET"]))
app.add_middleware(_BearerAuth)


def main() -> None:
    """Entry point for ``logos-mcp-http`` / ``python -m logos.mcp_server_http``."""
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


if __name__ == "__main__":
    main()
