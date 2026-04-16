import json
import os
from typing import Optional

from mcp.server.fastmcp import FastMCP
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from noesis_schemas import MemoryType, ProofCertificate
from .core import MnemeCore

_data_dir = os.getenv("MNEME_DATA_DIR", "/data")
_core = MnemeCore(
    db_path=os.path.join(_data_dir, "mneme.db"),
    chroma_path=os.path.join(_data_dir, "chroma"),
)

mcp = FastMCP("mneme", instructions=(
    "Persistent episodic and semantic memory for the Noesis AGI stack. "
    "Use store_memory to save facts or events, retrieve_memory to search them, "
    "list_proven_beliefs to inspect Logos-verified knowledge."
))


@mcp.tool()
def store_memory(
    content: str,
    memory_type: str,
    confidence: float = 0.5,
    tags: Optional[list[str]] = None,
    source: Optional[str] = None,
    certificate_json: Optional[str] = None,
) -> str:
    """Store a memory.

    Args:
        content: Text to remember.
        memory_type: "episodic" (what happened) or "semantic" (what is known).
        confidence: 0.0–1.0 belief strength.
        tags: Optional labels for filtering.
        source: Where this memory came from.
        certificate_json: JSON-serialised ProofCertificate from Logos (optional).
    """
    cert: Optional[ProofCertificate] = None
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
    results = _core.retrieve(query, k=k, min_confidence=min_confidence)
    return json.dumps([m.model_dump() for m in results], default=str)


@mcp.tool()
def forget_memory(memory_id: str, reason: str) -> str:
    """Delete a memory and record why in the audit log.

    Args:
        memory_id: ID returned by store_memory.
        reason: Why this memory is being removed (stored in audit log).
    """
    ok = _core.forget(memory_id, reason)
    return json.dumps({"forgotten": ok, "memory_id": memory_id})


@mcp.tool()
def list_proven_beliefs() -> str:
    """List all memories backed by a Logos ProofCertificate (proven=True)."""
    beliefs = _core.list_proven()
    return json.dumps([b.model_dump() for b in beliefs], default=str)


@mcp.tool()
def consolidate_memories(similarity_threshold: float = 0.15) -> str:
    """Merge near-duplicate memories, keeping the higher-confidence copy.

    Args:
        similarity_threshold: Cosine distance below which two memories are
            considered duplicates (0.0–1.0; lower = stricter).
    """
    merged = _core.consolidate(similarity_threshold=similarity_threshold)
    return json.dumps({"merged": merged})


# ── HTTP app ──────────────────────────────────────────────────────────────────

async def _health(_: Request) -> JSONResponse:
    return JSONResponse({"status": "ok", "service": "mneme"})


app = mcp.streamable_http_app()
app.routes.insert(0, Route("/health", _health, methods=["GET"]))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
