import json
import logging
import os
import sys
from typing import Optional

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .core import PraxisCore
from .tracing import get_tracer

logging.basicConfig(
    level=os.getenv("PRAXIS_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("praxis")

_data_dir = os.getenv("PRAXIS_DATA_DIR", "/data")
_secret_set = bool(os.getenv("PRAXIS_SECRET"))
log.info(
    "praxis boot: data_dir=%s port=%s secret_set=%s",
    _data_dir, os.getenv("PORT", "8000"), _secret_set,
)
try:
    os.makedirs(_data_dir, exist_ok=True)
    _core = PraxisCore(db_path=os.path.join(_data_dir, "praxis.db"))
    log.info("praxis core ready: db=%s/praxis.db", _data_dir)
except Exception:
    log.exception("praxis core init failed at %s", _data_dir)
    raise

# FastMCP enables DNS-rebinding protection by default and only allows
# localhost Host headers. Behind Railway's edge the public host is e.g.
# praxis-production-xxxx.up.railway.app, which gets rejected with 421.
# PRAXIS_ALLOWED_HOSTS is a comma-separated list of extra allowed Hosts;
# defaults keep localhost working for local dev.
_allowed_hosts = [
    h.strip()
    for h in os.getenv("PRAXIS_ALLOWED_HOSTS", "").split(",")
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
    "praxis transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "praxis",
    instructions=(
        "Hierarchical planner for the Noesis AGI stack. "
        "Use decompose_goal to open a new plan, evaluate_step to propose "
        "candidate steps (alternatives share a parent for Tree-of-Thoughts "
        "search), commit_step to record execution outcomes, backtrack after "
        "failures to surface alternative branches, and verify_plan before "
        "acting."
    ),
    transport_security=_transport_security,
)


@mcp.tool()
def decompose_goal(goal: str, parent_plan_id: Optional[str] = None) -> str:
    """Open a new plan for a goal.

    Args:
        goal: Natural-language objective (e.g. "ship the feature by Friday").
        parent_plan_id: If this plan is a sub-plan of another, its id.
    """
    with get_tracer().span(
        "decompose_goal",
        metadata={"has_parent": str(bool(parent_plan_id))},
    ):
        depth = 0
        if parent_plan_id:
            try:
                depth = _core.get_plan(parent_plan_id).depth + 1
            except KeyError:
                return json.dumps({"error": "parent plan not found"})
        plan = _core.decompose(goal, depth=depth, parent_plan_id=parent_plan_id)
        return plan.model_dump_json()


@mcp.tool()
def evaluate_step(
    plan_id: str,
    description: str,
    tool_call: Optional[str] = None,
    risk_score: float = 0.0,
    parent_step_id: Optional[str] = None,
) -> str:
    """Propose a candidate step; stored with a Tree-of-Thoughts score.

    Args:
        plan_id: Plan returned from decompose_goal.
        description: What this step does.
        tool_call: Optional MCP tool that will execute it.
        risk_score: 0.0–1.0 estimated failure likelihood.
        parent_step_id: Chain after this step (None = child of root, i.e. an
            alternative first step).
    """
    with get_tracer().span(
        "evaluate_step",
        metadata={"risk_score": f"{risk_score:.2f}", "has_tool": str(bool(tool_call))},
    ):
        try:
            step = _core.add_step(
                plan_id, description, tool_call, risk_score, parent_step_id
            )
        except KeyError as exc:
            return json.dumps({"error": str(exc)})
        return step.model_dump_json()


@mcp.tool()
def commit_step(plan_id: str, step_id: str, outcome: str, success: bool) -> str:
    """Record a step's execution outcome. Failure penalises the branch score.

    Args:
        plan_id: Plan the step belongs to.
        step_id: Step id from evaluate_step.
        outcome: Free-form result description.
        success: True = completed, False = failed (penalises beam search).
    """
    with get_tracer().span(
        "commit_step",
        metadata={"success": str(success)},
    ):
        try:
            step = _core.commit_step(plan_id, step_id, outcome, success)
        except KeyError as exc:
            return json.dumps({"error": str(exc)})
        return step.model_dump_json()


@mcp.tool()
def backtrack(plan_id: str) -> str:
    """After a failure, surface pending sibling alternatives to failed steps."""
    with get_tracer().span("backtrack"):
        try:
            alts = _core.backtrack(plan_id)
        except KeyError:
            return json.dumps({"error": "plan not found"})
        return json.dumps({"alternatives": [s.model_dump() for s in alts]}, default=str)


@mcp.tool()
def verify_plan(plan_id: str) -> str:
    """Safety-check a plan before execution. Logos GoalContract stub."""
    with get_tracer().span("verify_plan"):
        try:
            ok, message = _core.verify_plan(plan_id)
        except KeyError:
            return json.dumps({"error": "plan not found"})
        return json.dumps({"verified": ok, "message": message})


@mcp.tool()
def get_next_step(plan_id: str) -> str:
    """Return the first PENDING step on the current best path."""
    with get_tracer().span("get_next_step"):
        try:
            step = _core.get_next_step(plan_id)
        except KeyError:
            return json.dumps({"error": "plan not found"})
        if step is None:
            return json.dumps({"step": None, "message": "all steps completed"})
        return step.model_dump_json()


@mcp.tool()
def best_path(plan_id: str, k: int = 1) -> str:
    """Return the top-k highest-scoring root-to-leaf paths through the tree."""
    with get_tracer().span("best_path", metadata={"k": str(k)}):
        try:
            paths = _core.best_path(plan_id, k=k)
        except KeyError:
            return json.dumps({"error": "plan not found"})
        return json.dumps(
            {"paths": [[s.model_dump() for s in path] for path in paths]},
            default=str,
        )


@mcp.tool()
def get_plan(plan_id: str) -> str:
    """Fetch a plan with its best path populated."""
    with get_tracer().span("get_plan"):
        try:
            plan = _core.get_plan(plan_id)
        except KeyError:
            return json.dumps({"error": "plan not found"})
        return plan.model_dump_json()


# ── HTTP app ──────────────────────────────────────────────────────────────────

_SECRET = os.environ.get("PRAXIS_SECRET", "")


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "praxis"})


class _BearerAuth:
    """Pure-ASGI Bearer-token gate. BaseHTTPMiddleware buffers responses
    and breaks SSE streams, so we wrap the app at the ASGI layer instead.
    No-op when PRAXIS_SECRET is unset or the path is /health."""

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

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
