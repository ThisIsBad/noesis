import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from noesis_clients.auth import bearer_middleware
from noesis_schemas import GoalContract
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .core import TelosCore
from .tracing import get_tracer

logging.basicConfig(
    level=os.getenv("TELOS_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("telos")

_secret_set = bool(os.getenv("TELOS_SECRET"))
log.info(
    "telos boot: port=%s secret_set=%s",
    os.getenv("PORT", "8000"), _secret_set,
)
_core = TelosCore()

# FastMCP enables DNS-rebinding protection by default and only allows
# localhost Host headers. Behind Railway's edge the public host is e.g.
# telos-production-xxxx.up.railway.app, which gets rejected with 421.
# TELOS_ALLOWED_HOSTS is a comma-separated list of extra allowed Hosts;
# defaults keep localhost working for local dev.
_allowed_hosts = [
    h.strip()
    for h in os.getenv("TELOS_ALLOWED_HOSTS", "").split(",")
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
    "telos transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "telos",
    instructions=(
        "Goal stability and drift monitoring for the Noesis AGI stack. "
        "Use register_goal to declare a GoalContract, check_action_alignment "
        "to test whether a proposed action conflicts with active goals, "
        "get_drift_score for a rolling-window drift estimate, and "
        "list_active_goals to enumerate currently-active contracts."
    ),
    transport_security=_transport_security,
)


@mcp.tool()
def register_goal(contract_json: str) -> str:
    """Register a GoalContract that future actions will be checked against.

    Args:
        contract_json: JSON-serialised GoalContract (see noesis_schemas).
    """
    with get_tracer().span("register_goal"):
        contract = GoalContract.model_validate_json(contract_json)
        stored = _core.register(contract)
        return stored.model_dump_json()


@mcp.tool()
def check_action_alignment(action_description: str) -> str:
    """Check whether a proposed action conflicts with any active goal.

    Returns aligned=true with drift_score=0.0 when no active goals exist or
    when no postcondition conflict is detected. Every call is appended to
    the drift log.

    Args:
        action_description: Natural-language description of the action.
    """
    with get_tracer().span("check_action_alignment"):
        result = _core.check_alignment(action_description)
        return json.dumps({
            "aligned": result.aligned,
            "drift_score": result.drift_score,
            "reason": result.reason,
        })


@mcp.tool()
def get_drift_score(window: int = 20) -> str:
    """Return the mean drift score over the last `window` alignment checks.

    Args:
        window: Number of most-recent alignment checks to average (default 20).
    """
    with get_tracer().span("get_drift_score", metadata={"window": str(window)}):
        return json.dumps({"drift_score": _core.get_drift_score(window)})


@mcp.tool()
def list_active_goals() -> str:
    """List every currently-active GoalContract."""
    with get_tracer().span("list_active_goals"):
        goals = _core.list_active()
        return json.dumps([g.model_dump() for g in goals], default=str)


# ── HTTP app ──────────────────────────────────────────────────────────────────

async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "telos"})


app = mcp.sse_app()
app.routes.insert(0, Route("/health", _health, methods=["GET"]))
# Bearer-token gate — reads TELOS_SECRET + TELOS_SECRET_PREV for rotation.
# See noesis_clients.auth + docs/operations/secrets.md.
app.add_middleware(bearer_middleware("TELOS_SECRET"))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
