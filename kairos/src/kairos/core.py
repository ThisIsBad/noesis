from datetime import datetime
from typing import Optional
from noesis_schemas import TraceSpan


class KairosCore:
    """In-memory span store. Production: swap for OTLP exporter."""

    def __init__(self) -> None:
        self._spans: list[TraceSpan] = []

    def record_span(
        self,
        service: str,
        operation: str,
        trace_id: str,
        parent_span_id: Optional[str] = None,
        duration_ms: Optional[float] = None,
        success: Optional[bool] = None,
        metadata: Optional[dict[str, str]] = None,
    ) -> TraceSpan:
        span = TraceSpan(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            service=service,
            operation=operation,
            ended_at=datetime.utcnow(),
            duration_ms=duration_ms,
            success=success,
            metadata=metadata or {},
        )
        self._spans.append(span)
        return span

    def get_trace(self, trace_id: str) -> list[TraceSpan]:
        return [s for s in self._spans if s.trace_id == trace_id]

    def get_recent(self, limit: int = 100) -> list[TraceSpan]:
        return self._spans[-limit:]
