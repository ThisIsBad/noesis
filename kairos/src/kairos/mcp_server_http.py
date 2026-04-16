from fastapi import FastAPI
from pydantic import BaseModel
from typing import Optional
from .core import KairosCore

app = FastAPI(title="Kairos", description="Noesis observability service")
_core = KairosCore()


class RecordSpanRequest(BaseModel):
    service: str
    operation: str
    trace_id: str
    parent_span_id: Optional[str] = None
    duration_ms: Optional[float] = None
    success: Optional[bool] = None
    metadata: dict[str, str] = {}


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/spans")
def record_span(req: RecordSpanRequest):
    span = _core.record_span(
        service=req.service,
        operation=req.operation,
        trace_id=req.trace_id,
        parent_span_id=req.parent_span_id,
        duration_ms=req.duration_ms,
        success=req.success,
        metadata=req.metadata,
    )
    return span.model_dump()


@app.get("/traces/{trace_id}")
def get_trace(trace_id: str):
    return [s.model_dump() for s in _core.get_trace(trace_id)]


@app.get("/spans/recent")
def recent_spans(limit: int = 100):
    return [s.model_dump() for s in _core.get_recent(limit)]


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
