"""Shared bearer-token ASGI middleware for Noesis services.

Every MCP service (Logos, Mneme, Praxis, Telos, Episteme, Kosmos,
Empiria, Techne) plus Theoria independently implements the same
pattern:

* Read a secret from an env var (``LOGOS_SECRET``, ``MNEME_SECRET``, ...).
* Mount an ASGI middleware that 401s any non-``/health`` request
  whose ``Authorization`` header doesn't match ``Bearer <secret>``.
* No-op when the env var is unset (local-dev open mode).

Prior to this module every service had its own ~30-line copy. This
module is the single canonical implementation — see
[`docs/operations/secrets.md`](../../../docs/operations/secrets.md)
for the auth model and the planned rotation story.

Note: we use a **pure ASGI** middleware rather than
``starlette.middleware.BaseHTTPMiddleware`` because the latter
buffers responses, which breaks Server-Sent Events. Several services
rely on SSE (Theoria's live stream, future Kairos streams), so the
shared helper has to stay SSE-safe too.
"""

from __future__ import annotations

import os
from typing import Any, Awaitable, Callable, Iterable, MutableMapping

try:
    # Soft import — the helper is strictly typed but starlette is the only
    # ASGI framework any Noesis service actually uses, so a hard import here
    # would force every caller to declare starlette as a dep even if they
    # only consume ``bearer_middleware`` via duck typing.
    from starlette.responses import JSONResponse
except ImportError:  # pragma: no cover - starlette is always present in practice
    JSONResponse = None  # type: ignore[assignment,misc]


# ASGI protocol types — defined inline rather than imported from
# ``starlette.types`` so this module is usable by any ASGI app.
# Scope uses MutableMapping[str, Any] to satisfy Starlette's expectation
# when we forward to JSONResponse (which is stricter than dict).
Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]

DEFAULT_EXEMPT_PATHS: frozenset[str] = frozenset({"/health"})


class BearerAuthMiddleware:
    """Pure-ASGI bearer-token gate.

    Construct via :func:`bearer_middleware` so the env-var lookup
    happens once at service-boot time; the class is exported too for
    callers that want to bind directly (e.g. tests).

    When ``secret`` is an empty string the middleware is a no-op —
    that's the local-dev path. Every service logs ``secret_set=...``
    on boot so the mode is observable without reading env state.

    The middleware 401s on:

    * Missing ``Authorization`` header.
    * Mismatched token.

    Exempt paths (default: ``/health``) always pass through. Callers
    can widen the set per service — Theoria exempts ``/``,
    ``/index.html``, ``/static/*`` and ``/api/stream`` because a
    browser fetches those before the user can authenticate.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        secret: str,
        exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
        exempt_prefixes: Iterable[str] = (),
    ) -> None:
        self.app = app
        self.secret = secret
        self.exempt_paths = frozenset(exempt_paths)
        self.exempt_prefixes = tuple(exempt_prefixes)
        self._expected = f"Bearer {secret}".encode() if secret else None

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self._expected is None:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self.exempt_paths or any(
            path.startswith(p) for p in self.exempt_prefixes
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        if headers.get(b"authorization") != self._expected:
            if JSONResponse is None:   # pragma: no cover - starlette missing
                raise RuntimeError(
                    "starlette is required to emit 401 responses; install "
                    "starlette or wrap this middleware yourself."
                )
            await JSONResponse(
                {"error": "Unauthorized"}, status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="noesis"'},
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


def bearer_middleware(
    env_var: str,
    *,
    exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
    exempt_prefixes: Iterable[str] = (),
) -> Callable[[ASGIApp], ASGIApp]:
    """Return an ASGI middleware factory bound to an env-var secret.

    Usage::

        from starlette.applications import Starlette
        from noesis_clients.auth import bearer_middleware

        app = Starlette(...)
        app.add_middleware(
            bearer_middleware(
                "MNEME_SECRET",
                exempt_paths={"/health", "/"},
            )
        )

    ``add_middleware`` calls the returned factory with the upstream
    app; the returned value is the wired middleware instance.
    """
    secret = os.environ.get(env_var, "")

    def _factory(app: ASGIApp) -> ASGIApp:
        return BearerAuthMiddleware(
            app,
            secret=secret,
            exempt_paths=exempt_paths,
            exempt_prefixes=exempt_prefixes,
        )

    return _factory


__all__ = [
    "BearerAuthMiddleware",
    "bearer_middleware",
    "DEFAULT_EXEMPT_PATHS",
]
