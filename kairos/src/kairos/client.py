"""Kairos client for services emitting TraceSpans.

A service instantiates ``KairosClient`` once at boot, then wraps its
unit-of-work blocks with ``with client.span("op"): ...``. Spans
propagate through ``contextvars`` so nested calls share a trace_id
and link via parent_span_id.

The client is best-effort: transport errors are logged, never raised.
If ``base_url`` is unset (or ``disabled=True``), ``span`` still measures
duration and updates contextvars — it just doesn't POST to Kairos.
That way tracing can be switched off in dev without touching call sites.
"""
from __future__ import annotations

import contextlib
import logging
import time
import uuid
from contextvars import ContextVar
from typing import Iterator, Mapping, Optional

import httpx

log = logging.getLogger("kairos.client")

# HTTP headers used for cross-service trace propagation. Downstream
# services extract these on inbound requests (via ``continue_trace``)
# so their spans land under the same trace_id and link to the caller's
# span as parent.
TRACE_ID_HEADER = "X-Kairos-Trace-Id"
PARENT_SPAN_HEADER = "X-Kairos-Parent-Span-Id"

_current_trace_id: ContextVar[Optional[str]] = ContextVar(
    "kairos_trace_id", default=None
)
_current_span_id: ContextVar[Optional[str]] = ContextVar(
    "kairos_span_id", default=None
)


def current_trace_id() -> Optional[str]:
    """The trace_id active in the calling context, or None."""
    return _current_trace_id.get()


def current_span_id() -> Optional[str]:
    """The span_id active in the calling context, or None."""
    return _current_span_id.get()


def inject_headers(headers: Optional[Mapping[str, str]] = None) -> dict[str, str]:
    """Return a copy of ``headers`` with the current trace context attached.

    Callers about to issue an outbound request should feed the result
    into their HTTP client so the downstream service can continue the
    trace. If no trace is active, the headers are returned unchanged.
    """
    out: dict[str, str] = dict(headers or {})
    trace_id = _current_trace_id.get()
    if trace_id is not None:
        out[TRACE_ID_HEADER] = trace_id
        span_id = _current_span_id.get()
        if span_id is not None:
            out[PARENT_SPAN_HEADER] = span_id
    return out


def extract_trace_context(
    headers: Mapping[str, str],
) -> tuple[Optional[str], Optional[str]]:
    """Pull ``(trace_id, parent_span_id)`` out of inbound request headers.

    Header lookup is case-insensitive. Returns ``(None, None)`` if no
    trace context is present. ``parent_span_id`` may be ``None`` even
    when ``trace_id`` is set (e.g. the caller started a fresh trace
    without a parent).
    """
    lowered = {k.lower(): v for k, v in headers.items()}
    trace_id = lowered.get(TRACE_ID_HEADER.lower())
    parent_span_id = lowered.get(PARENT_SPAN_HEADER.lower())
    return trace_id, parent_span_id


class KairosClient:
    def __init__(
        self,
        base_url: Optional[str],
        service: str,
        *,
        timeout: float = 2.0,
        disabled: bool = False,
        _http: Optional[httpx.Client] = None,
    ) -> None:
        self._service = service
        self._base_url = (base_url or "").rstrip("/")
        self._disabled = disabled or not self._base_url
        self._http: Optional[httpx.Client]
        if self._disabled:
            self._http = None
        elif _http is not None:
            self._http = _http
        else:
            self._http = httpx.Client(timeout=timeout)

    @property
    def disabled(self) -> bool:
        return self._disabled

    def close(self) -> None:
        if self._http is not None:
            self._http.close()
            self._http = None

    @contextlib.contextmanager
    def continue_trace(
        self,
        trace_id: Optional[str],
        parent_span_id: Optional[str],
    ) -> Iterator[None]:
        """Adopt an inbound ``(trace_id, parent_span_id)`` as the current context.

        Typical use: a service extracts headers from an incoming
        request, enters ``continue_trace(...)`` for the duration of the
        handler, and any ``span()`` blocks inside inherit the adopted
        trace/parent. Passing ``None`` for both is a no-op — the caller
        probably has nothing to adopt (fresh trace).
        """
        trace_token = None
        span_token = None
        if trace_id is not None:
            trace_token = _current_trace_id.set(trace_id)
            if parent_span_id is not None:
                span_token = _current_span_id.set(parent_span_id)
        try:
            yield
        finally:
            if span_token is not None:
                _current_span_id.reset(span_token)
            if trace_token is not None:
                _current_trace_id.reset(trace_token)

    @contextlib.contextmanager
    def span(
        self,
        operation: str,
        *,
        metadata: Optional[dict[str, str]] = None,
    ) -> Iterator[str]:
        """Record a span around a block. Yields the active trace_id."""
        trace_id = _current_trace_id.get() or str(uuid.uuid4())
        parent_span_id = _current_span_id.get()
        span_id = str(uuid.uuid4())

        trace_token = _current_trace_id.set(trace_id)
        span_token = _current_span_id.set(span_id)
        t0 = time.perf_counter()
        success = True
        try:
            yield trace_id
        except BaseException:
            success = False
            raise
        finally:
            duration_ms = (time.perf_counter() - t0) * 1000.0
            _current_trace_id.reset(trace_token)
            _current_span_id.reset(span_token)
            self._emit(
                trace_id=trace_id,
                span_id=span_id,
                parent_span_id=parent_span_id,
                operation=operation,
                duration_ms=duration_ms,
                success=success,
                metadata=metadata or {},
            )

    def _emit(
        self,
        *,
        trace_id: str,
        span_id: str,
        parent_span_id: Optional[str],
        operation: str,
        duration_ms: float,
        success: bool,
        metadata: dict[str, str],
    ) -> None:
        if self._disabled or self._http is None:
            return
        payload = {
            "service": self._service,
            "operation": operation,
            "trace_id": trace_id,
            "span_id": span_id,
            "parent_span_id": parent_span_id,
            "duration_ms": duration_ms,
            "success": success,
            "metadata": metadata,
        }
        try:
            self._http.post(f"{self._base_url}/spans", json=payload)
        except Exception as exc:
            log.warning(
                "kairos span emit failed (service=%s op=%s): %s",
                self._service,
                operation,
                exc,
            )
