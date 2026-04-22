import json
import logging
import os
import sys

from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings
from noesis_schemas import MemoryType, ProofCertificate
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.types import ASGIApp, Receive, Scope, Send

from .core import MnemeCore
from .logos_client import LogosClient
from .tracing import get_tracer

logging.basicConfig(
    level=os.getenv("MNEME_LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s | %(message)s",
    stream=sys.stdout,
)
log = logging.getLogger("mneme")

_data_dir = os.getenv("MNEME_DATA_DIR", "/data")
_secret_set = bool(os.getenv("MNEME_SECRET"))
log.info(
    "mneme boot: data_dir=%s port=%s secret_set=%s",
    _data_dir, os.getenv("PORT", "8000"), _secret_set,
)
try:
    os.makedirs(_data_dir, exist_ok=True)
    _core = MnemeCore(
        db_path=os.path.join(_data_dir, "mneme.db"),
        chroma_path=os.path.join(_data_dir, "chroma"),
    )
    log.info("mneme core ready: db=%s/mneme.db", _data_dir)
except Exception:
    log.exception("mneme core init failed at %s", _data_dir)
    raise

# Logos sidecar: read-only verification calls go direct, bypassing
# Claude as orchestrator. Configured via LOGOS_URL / LOGOS_SECRET env;
# unset → certify_memory returns a clear "not configured" payload
# instead of a broken call.
_logos_client: LogosClient | None = LogosClient.from_env()
log.info("mneme logos sidecar: configured=%s", _logos_client is not None)

# FastMCP enables DNS-rebinding protection by default and only allows
# localhost Host headers. Behind Railway's edge the public host is e.g.
# mneme-production-c227.up.railway.app, which gets rejected with 421.
# MNEME_ALLOWED_HOSTS is a comma-separated list of extra allowed Hosts;
# defaults keep localhost working for local dev.
_allowed_hosts = [
    h.strip()
    for h in os.getenv("MNEME_ALLOWED_HOSTS", "").split(",")
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
    "mneme transport_security: allowed_hosts=%s",
    _transport_security.allowed_hosts,
)

mcp = FastMCP(
    "mneme",
    instructions=(
        "Persistent episodic and semantic memory for the Noesis AGI stack. "
        "Use store_memory to save facts or events, retrieve_memory to search them, "
        "list_proven_beliefs to inspect Logos-verified knowledge."
    ),
    transport_security=_transport_security,
)


@mcp.tool()
def store_memory(
    content: str,
    memory_type: str,
    confidence: float = 0.5,
    tags: list[str] | None = None,
    source: str | None = None,
    certificate_json: str = "",
) -> str:
    """Store a memory.

    Args:
        content: Text to remember.
        memory_type: "episodic" (what happened) or "semantic" (what is known).
        confidence: 0.0–1.0 belief strength.
        tags: Optional labels for filtering.
        source: Where this memory came from.
        certificate_json: JSON-serialised ProofCertificate from Logos. Pass
            an empty string (the default) to store a memory without a
            certificate. NOTE: this must stay typed as plain ``str`` — not
            ``str | None`` — because FastMCP's ``pre_parse_json`` auto-decodes
            JSON-looking strings whenever the declared annotation is not
            *exactly* ``str`` (it's a Claude Desktop accommodation), which
            would turn our serialised cert into a ``dict`` before Pydantic
            validation and reject it as "Input should be a valid string".
    """
    with get_tracer().span(
        "store_memory",
        metadata={
            "memory_type": memory_type,
            "has_certificate": str(bool(certificate_json)),
        },
    ):
        cert: ProofCertificate | None = None
        if certificate_json:
            cert = ProofCertificate.model_validate_json(certificate_json)

        mem = _core.store(
            content=content,
            memory_type=MemoryType(memory_type),
            confidence=confidence,
            certificate=cert,
            tags=tags or [],
            source=source,
        )
        return mem.model_dump_json()


@mcp.tool()
def retrieve_memory(query: str, k: int = 5, min_confidence: float = 0.0) -> str:
    """Retrieve memories semantically similar to query.

    Args:
        query: Natural-language search query.
        k: Maximum number of results.
        min_confidence: Only return memories at or above this confidence.
    """
    with get_tracer().span(
        "retrieve_memory",
        metadata={"k": str(k), "min_confidence": f"{min_confidence:.2f}"},
    ):
        results = _core.retrieve(query, k=k, min_confidence=min_confidence)
        return json.dumps([m.model_dump() for m in results], default=str)


@mcp.tool()
def forget_memory(memory_id: str, reason: str) -> str:
    """Delete a memory and record why in the audit log.

    Args:
        memory_id: ID returned by store_memory.
        reason: Why this memory is being removed (stored in audit log).
    """
    with get_tracer().span("forget_memory", metadata={"memory_id": memory_id}):
        ok = _core.forget(memory_id, reason)
        return json.dumps({"forgotten": ok, "memory_id": memory_id})


@mcp.tool()
def list_proven_beliefs() -> str:
    """List all memories backed by a Logos ProofCertificate (proven=True)."""
    with get_tracer().span("list_proven_beliefs"):
        beliefs = _core.list_proven()
        return json.dumps([b.model_dump() for b in beliefs], default=str)


async def _certify_memory_impl(
    memory_id: str,
    core: MnemeCore,
    logos_client: LogosClient | None,
) -> str:
    """Pure async implementation of the ``certify_memory`` MCP tool.

    Lives outside the ``@mcp.tool`` decorator so unit tests can call
    it directly with a tmp ``MnemeCore`` and a fake ``LogosClient``,
    without going through FastMCP's transport plumbing.
    """
    if logos_client is None:
        return json.dumps({"status": "logos_unconfigured"})

    memory = core.get(memory_id)
    if memory is None:
        return json.dumps({"status": "not_found", "memory_id": memory_id})

    cert = await logos_client.certify_claim(memory.content)
    if cert is None:
        return json.dumps({
            "status": "logos_unreachable",
            "memory_id": memory_id,
            "error": logos_client.last_error or "unknown",
        })

    updated = core.attach_certificate(memory_id, cert)
    if updated is None:  # pragma: no cover — forget-race after the get()
        return json.dumps({"status": "not_found", "memory_id": memory_id})

    return json.dumps({
        "status": "certified" if cert.verified else "refuted",
        "memory_id": memory_id,
        "verified": cert.verified,
        "method": cert.method,
        "proven": updated.proven,
    })


@mcp.tool()
async def certify_memory(memory_id: str) -> str:
    """Ask Logos to verify an existing memory and stamp the result.

    Calls Logos's ``certify_claim`` over the configured sidecar with
    the memory's ``content`` as the argument. On success, attaches
    the returned ``ProofCertificate`` to the memory in place,
    setting ``proven`` to the certificate's ``verified`` flag.

    Returns a JSON payload with one of:
        {"status": "certified",  "memory_id": ..., "verified": bool,
         "method": "...", "proven": bool}
        {"status": "refuted",    "memory_id": ..., "method": "...",
         "proven": false}
        {"status": "not_found",  "memory_id": ...}
        {"status": "logos_unconfigured"}                    (no LOGOS_URL)
        {"status": "logos_unreachable", "error": "..."}     (network etc.)

    Never raises — the caller's orchestration loop must keep working
    even when Logos is down or the claim isn't well-formed enough to
    parse. ``last_error`` from the underlying client is surfaced in
    the ``error`` field so logs stay diagnostic.
    """
    with get_tracer().span(
        "certify_memory", metadata={"memory_id": memory_id}
    ):
        return await _certify_memory_impl(memory_id, _core, _logos_client)


@mcp.tool()
def consolidate_memories(similarity_threshold: float = 0.5) -> str:
    """Merge near-duplicate memories, keeping the higher-confidence copy.

    Args:
        similarity_threshold: Cosine distance below which two memories are
            considered duplicates (0.0–1.0; lower = stricter).
    """
    with get_tracer().span(
        "consolidate_memories",
        metadata={"similarity_threshold": f"{similarity_threshold:.2f}"},
    ):
        merged = _core.consolidate(similarity_threshold=similarity_threshold)
        return json.dumps({"merged": merged})


# ── HTTP app ──────────────────────────────────────────────────────────────────

_SECRET = os.environ.get("MNEME_SECRET", "")


async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mneme"})


class _BearerAuth:
    """Pure-ASGI Bearer-token gate. BaseHTTPMiddleware buffers responses
    and breaks SSE streams, so we wrap the app at the ASGI layer instead.
    No-op when MNEME_SECRET is unset or the path is /health."""

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
