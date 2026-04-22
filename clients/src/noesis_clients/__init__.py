"""Cross-service Python clients for the Noesis stack.

Consumers (``services/<svc>``) import the client they need and plug
it into their core. The clients live here rather than inside each
consumer to remove the duplication that built up when Mneme and
Praxis each ended up with their own copy of ``logos_client.py``.

A client module in this package must:

* Be **read-only / idempotent** from the callee's perspective —
  these are sidecars, not control-plane calls.
* Return ``None`` (or an equivalent sentinel) on any failure rather
  than raising; the rule is that a service outage must not break the
  caller's primary operation.
* Surface diagnostic info through a ``last_error`` attribute so
  logging stays useful without changing the return contract.
* Accept an injectable ``session_factory`` so callers can test
  without standing up a real SSE connection.
"""

from .logos import LogosClient, SessionFactory

__all__ = ["LogosClient", "SessionFactory"]
