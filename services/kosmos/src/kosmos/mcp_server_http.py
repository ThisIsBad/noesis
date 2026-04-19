import json
import logging
import os
import sys
from typing import Any

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .core import KosmosCore
from .tracing import get_tracer

logging.basicConfig(
    level=os.getenv("KOSMOS_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("kosmos")

_secret_set = bool(os.getenv("KOSMOS_SECRET"))
log.info(
    "kosmos boot: port=%s secret_set=%s",
    os.getenv("PORT", "8000"), _secret_set,
)
_core = KosmosCore()

# FastMCP enables DNS-rebinding protection by default and only allows
# localhost Host headers. Behind Railway's edge the public host is e.g.
# kosmos-production-xxxx.up.railway.app, which gets rejected with 421.
# KOSMOS_ALLOWED_HOSTS is a comma-separated list of extra allowed Hosts;
# defaults keep localhost working for local dev.
_allowed_hosts = [
    h.strip()
    for h in os.getenv("KOSMOS_ALLOWED_HOSTS", "").split(",")
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
    "kosmos transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "kosmos",
    instructions=(
        "Causal world-model with Do-calculus for the Noesis AGI stack. "
        "Use add_causal_edge to register a directed cause → effect edge, "
        "compute_intervention for downstream effect weights under do(X=x), "
        "counterfactual for path strength between two variables, and "
        "query_causes to enumerate direct causes of an effect."
    ),
    transport_security=_transport_security,
)


@mcp.tool()
def add_causal_edge(cause: str, effect: str, strength: float = 1.0) -> str:
    """Register a directed causal edge ``cause → effect``.

    Args:
        cause: Source variable name.
        effect: Target variable name.
        strength: Causal weight in [0, 1] — propagates multiplicatively.
    """
    with get_tracer().span("add_causal_edge"):
        _core.add_edge(cause, effect, strength)
        return json.dumps({"added": f"{cause} -> {effect}"})


@mcp.tool()
def compute_intervention(variable: str, value: Any) -> str:
    """Compute downstream effect weights for ``do(variable = value)``.

    Args:
        variable: Variable being intervened on.
        value: Post-intervention value (any JSON-serialisable type).
    """
    with get_tracer().span("compute_intervention"):
        return json.dumps(_core.compute_intervention(variable, value))


@mcp.tool()
def counterfactual(cause: str, effect: str) -> str:
    """Return cumulative causal-path strength between ``cause`` and ``effect``.

    Args:
        cause: Source variable.
        effect: Target variable. ``null`` strength means no directed path.
    """
    with get_tracer().span("counterfactual"):
        return json.dumps({"strength": _core.counterfactual(cause, effect)})


@mcp.tool()
def query_causes(effect: str) -> str:
    """Return every variable that has a direct edge into ``effect``."""
    with get_tracer().span("query_causes"):
        return json.dumps({"causes": _core.query_causes(effect)})


# ── HTTP app ──────────────────────────────────────────────────────────────────

_SECRET = os.environ.get("KOSMOS_SECRET", "")


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "kosmos"})


class _BearerAuth:
    """Pure-ASGI Bearer-token gate. BaseHTTPMiddleware buffers responses
    and breaks SSE streams, so we wrap the app at the ASGI layer instead.
    No-op when KOSMOS_SECRET is unset or the path is /health."""

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
