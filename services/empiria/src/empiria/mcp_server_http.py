import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from noesis_clients.auth import bearer_middleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from .core import EmpiriaCore
from .tracing import get_tracer

logging.basicConfig(
    level=os.getenv("EMPIRIA_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("empiria")

_secret_set = bool(os.getenv("EMPIRIA_SECRET"))
log.info(
    "empiria boot: port=%s secret_set=%s",
    os.getenv("PORT", "8000"),
    _secret_set,
)
_core = EmpiriaCore()

# FastMCP enables DNS-rebinding protection by default and only allows
# localhost Host headers. Behind Railway's edge the public host is e.g.
# empiria-production-xxxx.up.railway.app, which gets rejected with 421.
# EMPIRIA_ALLOWED_HOSTS is a comma-separated list of extra allowed Hosts;
# defaults keep localhost working for local dev.
_allowed_hosts = [
    h.strip() for h in os.getenv("EMPIRIA_ALLOWED_HOSTS", "").split(",") if h.strip()
]
_transport_security = TransportSecuritySettings(
    enable_dns_rebinding_protection=bool(_allowed_hosts),
    allowed_hosts=_allowed_hosts + ["127.0.0.1:*", "localhost:*", "[::1]:*"],
    allowed_origins=[f"https://{h}" for h in _allowed_hosts]
    + ["http://127.0.0.1:*", "http://localhost:*", "http://[::1]:*"],
)
log.info(
    "empiria transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "empiria",
    instructions=(
        "Experience accumulation and lesson retrieval for the Noesis AGI "
        "stack. Use record_experience to log an (context, action, outcome) "
        "triple with a distilled lesson, retrieve_lessons to pull the "
        "top-k lessons relevant to a new context, and successful_patterns "
        "to list all recorded successes in a domain."
    ),
    transport_security=_transport_security,
)


@mcp.tool()
def record_experience(
    context: str,
    action_taken: str,
    outcome: str,
    success: bool,
    lesson_text: str,
    confidence: float = 0.5,
    domain: str | None = None,
) -> str:
    """Record an experience and the lesson distilled from it.

    Args:
        context: Situation description at the time of the action.
        action_taken: The action or policy the agent executed.
        outcome: Observed result of the action (free-form).
        success: Whether the outcome was considered a success.
        lesson_text: Short imperative lesson for future similar contexts.
        confidence: Subjective confidence in the lesson, in [0.0, 1.0].
        domain: Optional domain tag for scoped retrieval.
    """
    with get_tracer().span("record_experience"):
        lesson = _core.record(
            context=context,
            action_taken=action_taken,
            outcome=outcome,
            success=success,
            lesson_text=lesson_text,
            confidence=confidence,
            domain=domain,
        )
        return lesson.model_dump_json()


@mcp.tool()
def retrieve_lessons(
    context: str,
    k: int = 5,
    domain: str | None = None,
) -> str:
    """Return up to ``k`` lessons most relevant to ``context``.

    Args:
        context: Current situation to match against recorded lessons.
        k: Maximum number of lessons to return, ordered by confidence.
        domain: Optional domain filter.
    """
    with get_tracer().span("retrieve_lessons"):
        lessons = _core.retrieve(context, k, domain)
        return json.dumps([lesson.model_dump(mode="json") for lesson in lessons])


@mcp.tool()
def successful_patterns(domain: str | None = None) -> str:
    """Return every recorded lesson whose ``success`` is true.

    Args:
        domain: Optional domain filter.
    """
    with get_tracer().span("successful_patterns"):
        lessons = _core.successful_patterns(domain)
        return json.dumps([lesson.model_dump(mode="json") for lesson in lessons])


# ── HTTP app ──────────────────────────────────────────────────────────────────


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "empiria"})


app = mcp.sse_app()
app.routes.insert(0, Route("/health", _health, methods=["GET"]))
# Bearer-token gate — reads EMPIRIA_SECRET + EMPIRIA_SECRET_PREV for rotation.
# See noesis_clients.auth + docs/operations/secrets.md.
app.add_middleware(bearer_middleware("EMPIRIA_SECRET"))

if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
