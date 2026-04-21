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
        span_id: Optional[str] = None,
    ) -> TraceSpan:
        kwargs: dict[str, object] = dict(
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            service=service,
            operation=operation,
            ended_at=datetime.utcnow(),
            duration_ms=duration_ms,
            success=success,
            metadata=metadata or {},
        )
        if span_id is not None:
            kwargs["span_id"] = span_id
        span = TraceSpan(**kwargs)  # type: ignore[arg-type]
        self._spans.append(span)
        return span

    def get_trace(self, trace_id: str) -> list[TraceSpan]:
        return [s for s in self._spans if s.trace_id == trace_id]

    def get_recent(self, limit: int = 100) -> list[TraceSpan]:
        return self._spans[-limit:]

    def query_spans(
        self,
        *,
        service: Optional[str] = None,
        operation: Optional[str] = None,
        trace_id: Optional[str] = None,
        success: Optional[bool] = None,
        since: Optional[datetime] = None,
        min_duration_ms: Optional[float] = None,
        limit: int = 100,
    ) -> list[TraceSpan]:
        """Return the most-recent spans matching all non-None filters.

        Filters combine with AND semantics. ``limit`` caps the result
        size; matches are returned oldest-first within the capped
        window so the caller sees chronological order.
        """
        matched: list[TraceSpan] = []
        for span in self._spans:
            if service is not None and span.service != service:
                continue
            if operation is not None and span.operation != operation:
                continue
            if trace_id is not None and span.trace_id != trace_id:
                continue
            if success is not None and span.success is not success:
                continue
            if (
                since is not None
                and span.ended_at is not None
                and span.ended_at < since
            ):
                continue
            if (
                min_duration_ms is not None
                and (span.duration_ms is None or span.duration_ms < min_duration_ms)
            ):
                continue
            matched.append(span)
        return matched[-limit:]
