"""Kosmos tracing wiring for the Kairos observability service.

A single process-wide ``KairosClient`` is lazily built from environment at
first use. It is best-effort: if ``KAIROS_URL`` is unset or
``KOSMOS_TRACE_ENABLED=0``, spans still run (timing + contextvars) but
nothing is emitted. That lets us wrap every MCP tool unconditionally
without changing call sites when tracing is off.
"""
from __future__ import annotations

import os

from kairos.client import KairosClient

_SERVICE_NAME = "kosmos"
_client: KairosClient | None = None


def _env_truthy(name: str, default: str = "1") -> bool:
    return os.getenv(name, default).strip().lower() not in {"0", "false", "no", ""}


def get_tracer() -> KairosClient:
    """Return the process-wide Kairos client, building it on first call."""
    global _client
    if _client is None:
        enabled = _env_truthy("KOSMOS_TRACE_ENABLED")
        base_url = os.getenv("KAIROS_URL") if enabled else None
        _client = KairosClient(
            base_url=base_url,
            service=_SERVICE_NAME,
            disabled=not enabled,
        )
    return _client


def reset_tracer_for_tests() -> None:
    """Drop the cached client; the next ``get_tracer()`` rereads env."""
    global _client
    if _client is not None:
        _client.close()
    _client = None
