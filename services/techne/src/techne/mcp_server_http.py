import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from noesis_schemas import ProofCertificate
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .core import TechneCore
from .tracing import get_tracer

logging.basicConfig(
    level=os.getenv("TECHNE_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("techne")

_secret_set = bool(os.getenv("TECHNE_SECRET"))
log.info(
    "techne boot: port=%s secret_set=%s",
    os.getenv("PORT", "8000"), _secret_set,
)
_core = TechneCore()

# FastMCP enables DNS-rebinding protection by default and only allows
# localhost Host headers. Behind Railway's edge the public host is e.g.
# techne-production-xxxx.up.railway.app, which gets rejected with 421.
# TECHNE_ALLOWED_HOSTS is a comma-separated list of extra allowed Hosts;
# defaults keep localhost working for local dev.
_allowed_hosts = [
    h.strip()
    for h in os.getenv("TECHNE_ALLOWED_HOSTS", "").split(",")
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
    "techne transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "techne",
    instructions=(
        "Verified skill library for the Noesis AGI stack. Use store_skill "
        "to register a reusable strategy (optionally with a Logos proof "
        "certificate), retrieve_skill to pull the top-k skills for a task "
        "description, and record_use to update a skill's rolling success "
        "rate after it runs."
    ),
    transport_security=_transport_security,
)


@mcp.tool()
def store_skill(
    name: str,
    description: str,
    strategy: str,
    certificate_json: str = "",
    domain: str | None = None,
) -> str:
    """Register a reusable skill, optionally backed by a proof certificate.

    Args:
        name: Short identifier for the skill.
        description: Natural-language description of when to use it.
        strategy: Concrete strategy text the caller will execute.
        certificate_json: Serialized Logos ``ProofCertificate``. Pass an
            empty string (the default) to store a skill without a
            certificate. When present and ``verified`` is true, the stored
            skill is marked as verified. NOTE: this must stay typed as
            plain ``str`` — not ``str | None`` — because FastMCP's
            ``pre_parse_json`` auto-decodes JSON-looking strings whenever
            the declared annotation is not *exactly* ``str``, which would
            turn a real cert into a dict before Pydantic validation.
        domain: Optional domain tag for scoped retrieval.
    """
    with get_tracer().span("store_skill"):
        certificate = (
            ProofCertificate.model_validate_json(certificate_json)
            if certificate_json
            else None
        )
        skill = _core.store(
            name=name,
            description=description,
            strategy=strategy,
            certificate=certificate,
            domain=domain,
        )
        return skill.model_dump_json()


@mcp.tool()
def retrieve_skill(
    query: str,
    k: int = 5,
    verified_only: bool = False,
) -> str:
    """Return up to ``k`` skills matching ``query`` by name or description.

    Args:
        query: Free-text task description to search against.
        k: Maximum number of skills to return, ordered by success rate.
        verified_only: If true, drop any skill without a valid proof cert.
    """
    with get_tracer().span("retrieve_skill"):
        skills = _core.retrieve(query, k, verified_only)
        return json.dumps([skill.model_dump(mode="json") for skill in skills])


@mcp.tool()
def record_use(skill_id: str, success: bool) -> str:
    """Update a skill's rolling success rate after it runs.

    Args:
        skill_id: UUID returned by store_skill.
        success: Whether the most recent invocation succeeded.
    """
    with get_tracer().span("record_use"):
        try:
            skill = _core.record_use(skill_id, success)
        except KeyError:
            return json.dumps({"error": "skill_not_found"})
        return skill.model_dump_json()


# ── HTTP app ──────────────────────────────────────────────────────────────────

_SECRET = os.environ.get("TECHNE_SECRET", "")


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "techne"})


class _BearerAuth:
    """Pure-ASGI Bearer-token gate. BaseHTTPMiddleware buffers responses
    and breaks SSE streams, so we wrap the app at the ASGI layer instead.
    No-op when TECHNE_SECRET is unset or the path is /health."""

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
