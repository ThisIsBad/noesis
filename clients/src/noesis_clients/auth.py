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

    Accepts **multiple** valid secrets so zero-downtime rotation
    works: the middleware trusts a request whose token matches any
    non-empty entry in ``secrets``. The canonical env convention is

        <SVC>_SECRET         # new / active token
        <SVC>_SECRET_PREV    # previous token during rotation window

    When *every* entry in ``secrets`` is empty the middleware is a
    no-op — that's the local-dev path. Every service logs
    ``secret_set=...`` on boot so the mode is observable without
    reading env state.

    The middleware 401s on:

    * Missing ``Authorization`` header.
    * Token that doesn't match any active secret.

    Exempt paths (default: ``/health``) always pass through. Callers
    can widen the set per service — Theoria exempts ``/``,
    ``/index.html``, ``/static/*`` and ``/api/stream`` because a
    browser fetches those before the user can authenticate.
    """

    def __init__(
        self,
        app: ASGIApp,
        *,
        secret: str | None = None,
        secrets: Iterable[str] = (),
        exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
        exempt_prefixes: Iterable[str] = (),
    ) -> None:
        self.app = app
        # Back-compat: legacy callers pass a single ``secret`` kwarg.
        # New callers pass ``secrets`` (tuple) to support rotation.
        all_secrets: list[str] = []
        if secret:
            all_secrets.append(secret)
        all_secrets.extend(s for s in secrets if s)
        # Deduplicate while preserving order — tests assert on the set.
        seen: set[str] = set()
        deduped: list[str] = []
        for s in all_secrets:
            if s in seen:
                continue
            seen.add(s)
            deduped.append(s)
        self.secrets: tuple[str, ...] = tuple(deduped)
        self.exempt_paths = frozenset(exempt_paths)
        self.exempt_prefixes = tuple(exempt_prefixes)
        self._expected: tuple[bytes, ...] = tuple(
            f"Bearer {s}".encode() for s in self.secrets
        )

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._expected:
            await self.app(scope, receive, send)
            return
        path = scope.get("path", "")
        if path in self.exempt_paths or any(
            path.startswith(p) for p in self.exempt_prefixes
        ):
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        got = headers.get(b"authorization")
        if got not in self._expected:
            if JSONResponse is None:  # pragma: no cover - starlette missing
                raise RuntimeError(
                    "starlette is required to emit 401 responses; install "
                    "starlette or wrap this middleware yourself."
                )
            await JSONResponse(
                {"error": "Unauthorized"},
                status_code=401,
                headers={"WWW-Authenticate": 'Bearer realm="noesis"'},
            )(scope, receive, send)
            return
        await self.app(scope, receive, send)


def bearer_middleware(
    env_var: str,
    *,
    prev_env_var: str | None = None,
    exempt_paths: Iterable[str] = DEFAULT_EXEMPT_PATHS,
    exempt_prefixes: Iterable[str] = (),
) -> Callable[[ASGIApp], ASGIApp]:
    """Return an ASGI middleware factory bound to env-var secret(s).

    Reads ``env_var`` (the active token) and, if provided,
    ``prev_env_var`` (the previous token kept valid during rotation).
    The convention for ``env_var="MNEME_SECRET"`` is
    ``prev_env_var="MNEME_SECRET_PREV"``; when ``prev_env_var`` is
    omitted we default to ``<env_var>_PREV``.

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

    Rotation runbook::

        1. openssl rand -hex 32 → new token
        2. Deploy with <SVC>_SECRET=<new>, <SVC>_SECRET_PREV=<old>
        3. Update every caller's config to the new token; restart each
        4. Deploy again with <SVC>_SECRET_PREV unset

    ``add_middleware`` calls the returned factory with the upstream
    app; the returned value is the wired middleware instance.
    """
    prev_name = prev_env_var if prev_env_var is not None else f"{env_var}_PREV"
    active = os.environ.get(env_var, "")
    previous = os.environ.get(prev_name, "")

    def _factory(app: ASGIApp) -> ASGIApp:
        return BearerAuthMiddleware(
            app,
            secrets=(active, previous),
            exempt_paths=exempt_paths,
            exempt_prefixes=exempt_prefixes,
        )

    return _factory


__all__ = [
    "BearerAuthMiddleware",
    "bearer_middleware",
    "DEFAULT_EXEMPT_PATHS",
]
