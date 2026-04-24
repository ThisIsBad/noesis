"""Thin HTTP client for Kairos, the Noesis observability service.

Theoria does **not** persist TraceSpans — Kairos owns that data. When
an operator wants to visualise what happened in a distributed trace,
Theoria fetches the spans live from Kairos, converts them to a
``DecisionTrace`` on the fly, and returns the rendered view. Nothing
is written to Theoria's own store.

This keeps the two services aligned with their actual roles:
Kairos = raw spans; Theoria = curated decision-reasoning artifacts.
"""

from __future__ import annotations

import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Sequence

logger = logging.getLogger("theoria.kairos")

DEFAULT_KAIROS_URL = "http://127.0.0.1:8000"


@dataclass(frozen=True)
class KairosSpan:
    """Subset of ``noesis_schemas.TraceSpan`` we need for visualization.

    Kept as a plain frozen dataclass so the Kairos client has no hard
    dependency on pydantic or noesis_schemas — the wire format is JSON
    either way.
    """

    trace_id: str
    span_id: str
    parent_span_id: str | None
    service: str
    operation: str
    duration_ms: float | None
    success: bool | None
    metadata: dict[str, str]


class KairosError(Exception):
    """Raised when a Kairos call fails (network, HTTP, or parse)."""


class KairosClient:
    """Minimal read-only client for Kairos ``/traces/{id}`` and ``/spans``."""

    def __init__(
        self,
        base_url: str | None = None,
        *,
        timeout: float = 5.0,
    ) -> None:
        self.base_url = (base_url or os.environ.get("KAIROS_URL") or DEFAULT_KAIROS_URL).rstrip("/")
        self.timeout = timeout

    def fetch_trace(self, trace_id: str) -> list[KairosSpan]:
        """Return every span for ``trace_id`` in the order Kairos sent them."""
        url = f"{self.base_url}/traces/{urllib.parse.quote(trace_id)}"
        payload = self._get_json(url)
        if not isinstance(payload, list):
            raise KairosError(
                f"expected list from {url}, got {type(payload).__name__}"
            )
        return [_parse_span(item) for item in payload]

    def recent_spans(self, limit: int = 100) -> list[KairosSpan]:
        """Return the last N spans across all traces (mostly for debugging)."""
        url = f"{self.base_url}/spans/recent?limit={int(limit)}"
        payload = self._get_json(url)
        if not isinstance(payload, list):
            raise KairosError(f"expected list, got {type(payload).__name__}")
        return [_parse_span(item) for item in payload]

    # ---- internals ---------------------------------------------------

    def _get_json(self, url: str) -> Any:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                raw = resp.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            raise KairosError(f"HTTP {exc.code} from {url}: {exc.reason}") from exc
        except urllib.error.URLError as exc:
            raise KairosError(f"connection to {url} failed: {exc.reason}") from exc
        try:
            return json.loads(raw) if raw else None
        except json.JSONDecodeError as exc:
            raise KairosError(f"invalid JSON from {url}: {exc}") from exc


def _parse_span(raw: Any) -> KairosSpan:
    if not isinstance(raw, dict):
        raise KairosError(f"span entry must be an object, got {type(raw).__name__}")
    missing = {"trace_id", "span_id", "service", "operation"} - raw.keys()
    if missing:
        raise KairosError(f"span missing required fields: {sorted(missing)}")
    duration = raw.get("duration_ms")
    success = raw.get("success")
    return KairosSpan(
        trace_id=str(raw["trace_id"]),
        span_id=str(raw["span_id"]),
        parent_span_id=raw.get("parent_span_id"),
        service=str(raw["service"]),
        operation=str(raw["operation"]),
        duration_ms=float(duration) if duration is not None else None,
        success=bool(success) if success is not None else None,
        metadata={str(k): str(v) for k, v in (raw.get("metadata") or {}).items()},
    )


__all__: Sequence[str] = ("KairosSpan", "KairosClient", "KairosError", "DEFAULT_KAIROS_URL")
