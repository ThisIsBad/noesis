from datetime import datetime
from typing import Optional

from fastapi import FastAPI
from pydantic import BaseModel

from .core import KairosCore

app = FastAPI(title="Kairos", description="Noesis observability service")
_core = KairosCore()


class RecordSpanRequest(BaseModel):
    service: str
    operation: str
    trace_id: str
    span_id: Optional[str] = None
    parent_span_id: Optional[str] = None
    duration_ms: Optional[float] = None
    success: Optional[bool] = None
    metadata: dict[str, str] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/spans")
def record_span(req: RecordSpanRequest):  # type: ignore[no-untyped-def]
    span = _core.record_span(
        service=req.service,
        operation=req.operation,
        trace_id=req.trace_id,
        span_id=req.span_id,
        parent_span_id=req.parent_span_id,
        duration_ms=req.duration_ms,
        success=req.success,
        metadata=req.metadata,
    )
    return span.model_dump()


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):  # type: ignore[no-untyped-def]
    return [s.model_dump() for s in _core.get_trace(trace_id)]


@app.get("/spans/recent")
def recent_spans(limit: int = 100):  # type: ignore[no-untyped-def]
    return [s.model_dump() for s in _core.get_recent(limit)]


@app.get("/spans")
def query_spans(  # type: ignore[no-untyped-def]
    service: Optional[str] = None,
    operation: Optional[str] = None,
    trace_id: Optional[str] = None,
    success: Optional[bool] = None,
    since: Optional[datetime] = None,
    min_duration_ms: Optional[float] = None,
    limit: int = 100,
):
    return [
        s.model_dump()
        for s in _core.query_spans(
            service=service,
            operation=operation,
            trace_id=trace_id,
            success=success,
            since=since,
            min_duration_ms=min_duration_ms,
            limit=limit,
        )
    ]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
