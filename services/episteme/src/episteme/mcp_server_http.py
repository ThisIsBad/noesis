import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .core import EpistemeCore
from .tracing import get_tracer

logging.basicConfig(
    level=os.getenv("EPISTEME_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("episteme")

_secret_set = bool(os.getenv("EPISTEME_SECRET"))
log.info(
    "episteme boot: port=%s secret_set=%s",
    os.getenv("PORT", "8000"), _secret_set,
)
_core = EpistemeCore()

# FastMCP enables DNS-rebinding protection by default and only allows
# localhost Host headers. Behind Railway's edge the public host is e.g.
# episteme-production-xxxx.up.railway.app, which gets rejected with 421.
# EPISTEME_ALLOWED_HOSTS is a comma-separated list of extra allowed Hosts;
# defaults keep localhost working for local dev.
_allowed_hosts = [
    h.strip()
    for h in os.getenv("EPISTEME_ALLOWED_HOSTS", "").split(",")
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
    "episteme transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "episteme",
    instructions=(
        "Metacognition and calibration for the Noesis AGI stack. "
        "Use log_prediction to record a claim with a confidence estimate, "
        "log_outcome to resolve it, get_calibration for ECE/Brier/bias/"
        "sharpness per domain, and should_escalate to decide whether a "
        "low-confidence decision should be handed off."
    ),
    transport_security=_transport_security,
)


@mcp.tool()
def log_prediction(
    claim: str,
    confidence: float,
    domain: str | None = None,
) -> str:
    """Record a prediction that will later be resolved with log_outcome.

    Args:
        claim: Natural-language statement being predicted.
        confidence: Probability in [0.0, 1.0] that the claim is correct.
        domain: Optional domain tag for per-domain calibration.
    """
    with get_tracer().span("log_prediction"):
        pred = _core.log_prediction(claim, confidence, domain)
        return pred.model_dump_json()


@mcp.tool()
def log_outcome(prediction_id: str, correct: bool) -> str:
    """Resolve a previously-logged prediction with the observed outcome.

    Args:
        prediction_id: UUID returned by log_prediction.
        correct: Whether the claim turned out to be true.
    """
    with get_tracer().span("log_outcome"):
        try:
            pred = _core.log_outcome(prediction_id, correct)
        except KeyError:
            return json.dumps({"error": "prediction_not_found"})
        return pred.model_dump_json()


@mcp.tool()
def get_calibration(domain: str | None = None) -> str:
    """Return ECE, Brier score, bias and sharpness for resolved predictions.

    Args:
        domain: If given, restrict to predictions tagged with this domain.
    """
    metadata = {"domain": domain} if domain else None
    with get_tracer().span("get_calibration", metadata=metadata):
        return _core.get_calibration(domain).model_dump_json()


@mcp.tool()
def should_escalate(confidence: float, domain: str | None = None) -> str:
    """Decide whether a decision at this confidence should be escalated.

    Args:
        confidence: Probability estimate in [0.0, 1.0].
        domain: Optional domain tag — calibration bias is applied per domain.
    """
    with get_tracer().span("should_escalate"):
        return json.dumps(
            {"escalate": _core.should_escalate(confidence, domain)}
        )


@mcp.tool()
def get_competence_map(
    min_samples: int = 10,
    weakness_threshold: float = 0.15,
) -> str:
    """Return per-domain competence stats plus ranked strengths and weaknesses.

    Aggregates resolved predictions by domain and reports accuracy, average
    confidence, confidence gap (avg_confidence - accuracy; positive means
    overconfident), and Brier score per domain. Domains whose absolute
    confidence gap exceeds ``weakness_threshold`` are listed as weaknesses
    (ranked by |gap|). Domains with small gap and high accuracy are listed
    as strengths. Only domains with at least ``min_samples`` resolved
    predictions are eligible for either label.

    Args:
        min_samples: Minimum resolved-prediction count for a domain to be
            eligible as a strength or weakness. Defaults to 10.
        weakness_threshold: Absolute confidence-gap threshold for labelling
            a domain as a weakness. Defaults to 0.15.
    """
    metadata = {
        "min_samples": str(min_samples),
        "weakness_threshold": str(weakness_threshold),
    }
    with get_tracer().span("get_competence_map", metadata=metadata):
        return _core.get_competence_map(
            min_samples, weakness_threshold
        ).model_dump_json()


# ── HTTP app ──────────────────────────────────────────────────────────────────

_SECRET = os.environ.get("EPISTEME_SECRET", "")


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "episteme"})


class _BearerAuth:
    """Pure-ASGI Bearer-token gate. BaseHTTPMiddleware buffers responses
    and breaks SSE streams, so we wrap the app at the ASGI layer instead.
    No-op when EPISTEME_SECRET is unset or the path is /health."""

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
