"""Stdlib HTTP server for Theoria.

Deliberately zero-dependency so the visualization can be launched from
a clean checkout without pip-installing anything::

    python -m theoria

Routes:
    GET  /                        → static index.html
    GET  /static/<path>           → other frontend assets
    GET  /api/traces              → list of traces (most recent first)
    GET  /api/traces/{id}         → single trace
    POST /api/traces              → ingest a trace (JSON body)
    DELETE /api/traces/{id}       → remove a trace
    POST /api/samples/load        → load built-in samples into the store
    POST /api/clear               → clear all traces
    GET  /health                  → liveness
"""

from __future__ import annotations

import json
import logging
import mimetypes
import queue
import re
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import parse_qs, urlparse

from theoria.diff import diff_to_markdown, diff_to_mermaid, diff_traces
from theoria.export import format_for
from theoria.filters import apply_filter, filter_from_query
from theoria.ingest import trace_from_trace_spans
from theoria.kairos_client import KairosClient, KairosError
from theoria.models import DecisionTrace
from theoria.patterns import parse_query, run_query
from theoria.samples import build_samples
from theoria.stats import compute_stats
from theoria.store import TraceStore

SSE_HEARTBEAT_SECONDS = 15.0

STATIC_DIR = Path(__file__).parent / "static"

logger = logging.getLogger("theoria.server")

# Paths that never require auth — browser fetches them before the user
# can provide credentials, and monitoring hits /health.
_AUTH_EXEMPT_PATHS = frozenset({
    "/", "/index.html", "/health",
})
_AUTH_EXEMPT_PREFIXES = ("/static/",)


Route = tuple[re.Pattern[str], str, Callable[..., tuple[int, dict[str, str], bytes]]]


class TheoriaHandler(BaseHTTPRequestHandler):
    """HTTP request handler bound to a ``TraceStore`` and a ``KairosClient``."""

    store: TraceStore
    kairos: KairosClient             # bound per-server; see make_handler()
    # Tuple of accepted bearer tokens. Empty = auth disabled (open mode,
    # local-dev). Multiple entries enable zero-downtime secret rotation:
    # the active ``THEORIA_SECRET`` and the previous ``THEORIA_SECRET_PREV``
    # both pass during the rotation window. Mirrors the
    # ``noesis_clients.auth.bearer_middleware`` rotation contract used by
    # the eight ASGI services — Theoria stays stdlib-only on purpose
    # (the visualization launches without ``pip install``), so it can't
    # share the middleware code itself.
    secrets: tuple[str, ...] = ()
    server_version = "Theoria/0.1"

    # Silence default stderr access logging; re-route through logging module.
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        logger.info("%s - %s", self.address_string(), format % args)

    # ---- routing -----------------------------------------------------

    def do_GET(self) -> None:  # noqa: N802
        # SSE and export require streaming/non-JSON responses — bypass _dispatch.
        parsed = urlparse(self.path)
        if not self._check_auth(parsed.path):
            return
        if parsed.path == "/api/stream":
            self._handle_sse()
            return
        export_match = re.fullmatch(r"/api/traces/([^/]+)/export", parsed.path)
        if export_match:
            self._handle_export(export_match.group(1), parsed.query)
            return
        diff_match = re.fullmatch(r"/api/traces/([^/]+)/diff/([^/]+)", parsed.path)
        if diff_match:
            self._handle_diff(diff_match.group(1), diff_match.group(2), parsed.query)
            return
        self._dispatch("GET")

    def do_POST(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._check_auth(parsed.path):
            return
        self._dispatch("POST")

    def do_DELETE(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        if not self._check_auth(parsed.path):
            return
        self._dispatch("DELETE")

    # ---- auth --------------------------------------------------------

    def _check_auth(self, path: str) -> bool:
        """Enforce bearer-token auth if ``self.secrets`` is non-empty.

        Returns True when the request may proceed. When False, a 401 has
        already been written to the wire.

        Accepts any token in ``self.secrets`` so a rotation deploy
        (``THEORIA_SECRET`` flipped, ``THEORIA_SECRET_PREV`` still set)
        keeps in-flight clients working until they pick up the new value.

        /health, /, /index.html, /static/* and the SSE stream are always
        public — a browser fetches them before the user can authenticate
        and monitors need /health to work.
        """
        if not self.secrets:
            return True
        if path in _AUTH_EXEMPT_PATHS or any(
            path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES
        ):
            return True
        header = self.headers.get("Authorization", "") or ""
        if not any(header == f"Bearer {s}" for s in self.secrets):
            body = _json_error("unauthorized")
            self.send_response(int(HTTPStatus.UNAUTHORIZED))
            self.send_header("Content-Type", "application/json")
            self.send_header("WWW-Authenticate", 'Bearer realm="theoria"')
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return False
        return True

    def _dispatch(self, method: str) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        query = parsed.query
        try:
            status, headers, body = self._route(method, path, query)
        except _HTTPError as exc:
            status, headers, body = exc.status, {"Content-Type": "application/json"}, _json_error(exc.message)
        except Exception:  # pragma: no cover - defensive
            logger.exception("Unhandled error in request %s %s", method, path)
            status, headers, body = HTTPStatus.INTERNAL_SERVER_ERROR, {"Content-Type": "application/json"}, _json_error(
                "internal server error"
            )

        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        if method != "HEAD":
            self.wfile.write(body)

    def _route(
        self, method: str, path: str, query: str = "",
    ) -> tuple[int, dict[str, str], bytes]:
        if method == "GET" and (path == "/" or path == "/index.html"):
            return _serve_file(STATIC_DIR / "index.html")
        if method == "GET" and path.startswith("/static/"):
            return _serve_static(path[len("/static/"):])
        if method == "GET" and path == "/health":
            return _json_response({"ok": True, "traces": len(self.store)})

        if method == "GET" and path == "/api/stats":
            parsed_query = parse_qs(query or "")
            top_n_raw = parsed_query.get("top_n", ["5"])[0]
            top_n = int(top_n_raw) if top_n_raw.isdigit() else 5
            stats = compute_stats(self.store.list(), top_n=top_n)
            return _json_response(stats.to_dict())

        kairos_match = re.fullmatch(r"/api/kairos/traces/([^/]+)", path)
        if method == "GET" and kairos_match:
            kairos_trace_id = kairos_match.group(1)
            try:
                spans = self.kairos.fetch_trace(kairos_trace_id)
            except KairosError as exc:
                raise _HTTPError(
                    HTTPStatus.BAD_GATEWAY,
                    f"Kairos fetch failed: {exc}",
                ) from exc
            if not spans:
                raise _HTTPError(
                    HTTPStatus.NOT_FOUND,
                    f"no spans for Kairos trace '{kairos_trace_id}'",
                )
            # trace_from_trace_spans is duck-typed on the TraceSpan Protocol;
            # KairosSpan exposes the same attributes but isn't a Protocol
            # subclass, so help mypy past the structural-match gap.
            trace = trace_from_trace_spans(cast(Any, spans))
            return _json_response(trace.to_dict())

        if method == "GET" and path == "/api/traces":
            parsed_query = parse_qs(query or "")
            flt, limit = filter_from_query(parsed_query)
            filtered = apply_filter(self.store.list(), flt, limit=limit)
            return _json_response({"traces": [t.to_dict() for t in filtered]})
        if method == "POST" and path == "/api/traces":
            payload = self._read_json_body()
            trace = DecisionTrace.from_dict(payload)
            self.store.put(trace)
            return _json_response(trace.to_dict(), status=HTTPStatus.CREATED)
        if method == "POST" and path == "/api/traces/search":
            payload = self._read_json_body()
            try:
                compiled = parse_query(payload)
            except ValueError as exc:
                raise _HTTPError(HTTPStatus.BAD_REQUEST, str(exc)) from exc
            parsed_query = parse_qs(query or "")
            limit = int(parsed_query["limit"][0]) if "limit" in parsed_query else None
            results = run_query(self.store.list(), compiled, limit=limit)
            return _json_response({"traces": [t.to_dict() for t in results]})

        if method == "POST" and path == "/api/samples/load":
            count = self.store.put_many(build_samples())
            return _json_response({"loaded": count})
        if method == "POST" and path == "/api/clear":
            self.store.clear()
            return _json_response({"ok": True})

        trace_match = re.fullmatch(r"/api/traces/([^/]+)", path)
        if trace_match:
            trace_id = trace_match.group(1)
            if method == "GET":
                found = self.store.get(trace_id)
                if found is None:
                    raise _HTTPError(HTTPStatus.NOT_FOUND, f"trace '{trace_id}' not found")
                return _json_response(found.to_dict())
            if method == "DELETE":
                deleted = self.store.delete(trace_id)
                if not deleted:
                    raise _HTTPError(HTTPStatus.NOT_FOUND, f"trace '{trace_id}' not found")
                return _json_response({"deleted": trace_id})

        raise _HTTPError(HTTPStatus.NOT_FOUND, f"no route for {method} {path}")

    # ---- streaming endpoints -----------------------------------------

    def _handle_sse(self) -> None:
        """Server-Sent Events — emit an event for every store mutation."""
        self.send_response(int(HTTPStatus.OK))
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        q = self.store.subscribe()
        try:
            # Initial comment establishes the stream for browsers.
            self.wfile.write(b": connected\n\n")
            self.wfile.flush()
            while True:
                try:
                    msg = q.get(timeout=SSE_HEARTBEAT_SECONDS)
                except queue.Empty:
                    self.wfile.write(b": heartbeat\n\n")
                    self.wfile.flush()
                    continue
                event = msg.get("type", "message").replace(".", "_")
                payload = json.dumps(msg, sort_keys=True)
                self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            self.store.unsubscribe(q)

    def _handle_export(self, trace_id: str, query_str: str) -> None:
        """Render a trace in a human-readable format (Mermaid / DOT)."""
        query = parse_qs(query_str or "")
        fmt = (query.get("format", ["mermaid"])[0]).lower()
        trace = self.store.get(trace_id)
        if trace is None:
            status, headers, body = int(HTTPStatus.NOT_FOUND), {
                "Content-Type": "application/json"
            }, _json_error(f"trace '{trace_id}' not found")
        else:
            try:
                rendered = format_for(trace, fmt)
            except ValueError as exc:
                status, headers, body = int(HTTPStatus.BAD_REQUEST), {
                    "Content-Type": "application/json"
                }, _json_error(str(exc))
            else:
                status = int(HTTPStatus.OK)
                headers = {
                    "Content-Type": _content_type_for(fmt),
                    "Cache-Control": "no-store",
                    "Content-Disposition": f'inline; filename="{trace_id}.{_ext_for(fmt)}"',
                }
                body = rendered.encode("utf-8")

        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_diff(self, a_id: str, b_id: str, query_str: str) -> None:
        """Compare two traces and return a structured diff."""
        query = parse_qs(query_str or "")
        fmt = (query.get("format", ["json"])[0]).lower()

        a = self.store.get(a_id)
        b = self.store.get(b_id)
        missing = [i for i, t in ((a_id, a), (b_id, b)) if t is None]
        if missing:
            self._write_response(
                int(HTTPStatus.NOT_FOUND),
                {"Content-Type": "application/json"},
                _json_error(f"trace(s) not found: {', '.join(missing)}"),
            )
            return
        assert a is not None and b is not None  # narrowed by the missing check above

        diff = diff_traces(a, b)
        if fmt == "json":
            self._write_response(
                int(HTTPStatus.OK),
                {"Content-Type": "application/json", "Cache-Control": "no-store"},
                json.dumps(diff.to_dict(), sort_keys=True).encode("utf-8"),
            )
            return
        if fmt in ("markdown", "md"):
            body = diff_to_markdown(diff).encode("utf-8")
            self._write_response(
                int(HTTPStatus.OK),
                {
                    "Content-Type": "text/markdown; charset=utf-8",
                    "Content-Disposition": f'inline; filename="{a_id}-vs-{b_id}.md"',
                },
                body,
            )
            return
        if fmt == "mermaid":
            body = diff_to_mermaid(diff).encode("utf-8")
            self._write_response(
                int(HTTPStatus.OK),
                {
                    "Content-Type": "text/plain; charset=utf-8",
                    "Content-Disposition": f'inline; filename="{a_id}-vs-{b_id}.mmd"',
                },
                body,
            )
            return
        self._write_response(
            int(HTTPStatus.BAD_REQUEST),
            {"Content-Type": "application/json"},
            _json_error(f"unknown diff format: {fmt!r}"),
        )

    def _write_response(self, status: int, headers: dict[str, str], body: bytes) -> None:
        self.send_response(status)
        for key, value in headers.items():
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _read_json_body(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or 0)
        if length <= 0:
            raise _HTTPError(HTTPStatus.BAD_REQUEST, "empty request body")
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise _HTTPError(HTTPStatus.BAD_REQUEST, f"invalid JSON body: {exc}") from exc
        if not isinstance(payload, dict):
            raise _HTTPError(HTTPStatus.BAD_REQUEST, "JSON body must be an object")
        return payload


class _HTTPError(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.message = message


def _json_response(
    payload: Any,
    status: int = int(HTTPStatus.OK),
) -> tuple[int, dict[str, str], bytes]:
    body = json.dumps(payload, sort_keys=True).encode("utf-8")
    headers = {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
    }
    return status, headers, body


def _json_error(message: str) -> bytes:
    return json.dumps({"error": message}).encode("utf-8")


def _content_type_for(fmt: str) -> str:
    if fmt in ("markdown", "md"):
        return "text/markdown; charset=utf-8"
    return "text/plain; charset=utf-8"


def _ext_for(fmt: str) -> str:
    if fmt == "mermaid":
        return "mmd"
    if fmt in ("dot", "graphviz"):
        return "dot"
    if fmt in ("markdown", "md"):
        return "md"
    return "txt"


def _serve_file(path: Path) -> tuple[int, dict[str, str], bytes]:
    if not path.is_file():
        raise _HTTPError(HTTPStatus.NOT_FOUND, f"file not found: {path.name}")
    data = path.read_bytes()
    ctype, _ = mimetypes.guess_type(path.name)
    headers = {
        "Content-Type": ctype or "application/octet-stream",
        "Cache-Control": "no-cache",
    }
    return int(HTTPStatus.OK), headers, data


def _serve_static(relpath: str) -> tuple[int, dict[str, str], bytes]:
    # Defend against path traversal — join + resolve, then check containment.
    base = STATIC_DIR.resolve()
    target = (base / relpath).resolve()
    try:
        target.relative_to(base)
    except ValueError as exc:
        raise _HTTPError(HTTPStatus.FORBIDDEN, "path escapes static root") from exc
    return _serve_file(target)


def make_handler(
    store: TraceStore,
    *,
    secret: str | None = None,
    previous_secret: str | None = None,
    kairos: KairosClient | None = None,
) -> type[TheoriaHandler]:
    """Return a ``TheoriaHandler`` subclass bound to ``store`` + auth + ``kairos``.

    ``secret`` is the active bearer token (``None`` = open mode).
    ``previous_secret`` keeps the old token valid during rotation so a
    live deploy doesn't 401 in-flight clients before they pick up the
    new value.
    """
    secrets = tuple(s for s in (secret, previous_secret) if s)
    return type(
        "BoundTheoriaHandler",
        (TheoriaHandler,),
        {
            "store": store,
            "secrets": secrets,
            "kairos": kairos if kairos is not None else KairosClient(),
        },
    )


def make_server(
    host: str = "127.0.0.1",
    port: int = 8765,
    store: TraceStore | None = None,
    secret: str | None = None,
    previous_secret: str | None = None,
    kairos: KairosClient | None = None,
) -> tuple[ThreadingHTTPServer, TraceStore]:
    """Build (but don't start) a ``ThreadingHTTPServer`` plus its store.

    When ``secret`` is set (or the ``THEORIA_SECRET`` env var is set and
    the caller doesn't override), all non-public endpoints require
    ``Authorization: Bearer <secret>``. During rotation, set
    ``THEORIA_SECRET_PREV`` (or pass ``previous_secret``) — both tokens
    pass until the rotation window closes. Mirrors the
    ``noesis_clients.auth.bearer_middleware`` rotation contract used by
    the eight ASGI services. ``kairos`` defaults to a client pointed at
    ``$KAIROS_URL`` (or localhost).
    """
    import os as _os
    # NB: use `is None` — an empty TraceStore is falsy because __len__ returns 0.
    resolved_store = TraceStore() if store is None else store
    resolved_secret = (
        secret if secret is not None
        else _os.environ.get("THEORIA_SECRET") or None
    )
    resolved_prev = (
        previous_secret if previous_secret is not None
        else _os.environ.get("THEORIA_SECRET_PREV") or None
    )
    handler_cls = make_handler(
        resolved_store,
        secret=resolved_secret,
        previous_secret=resolved_prev,
        kairos=kairos,
    )
    server = ThreadingHTTPServer((host, port), handler_cls)
    return server, resolved_store


def serve(
    host: str = "127.0.0.1",
    port: int = 8765,
    store: TraceStore | None = None,
    load_samples: bool = True,
    secret: str | None = None,
    previous_secret: str | None = None,
    kairos: KairosClient | None = None,
) -> None:
    """Run the Theoria server until SIGINT."""
    server, resolved_store = make_server(
        host=host,
        port=port,
        store=store,
        secret=secret,
        previous_secret=previous_secret,
        kairos=kairos,
    )
    if load_samples and len(resolved_store) == 0:
        resolved_store.put_many(build_samples())
    bound_secrets = server.RequestHandlerClass.secrets  # type: ignore[attr-defined]
    if not bound_secrets:
        auth_note = "auth=off"
    elif len(bound_secrets) > 1:
        auth_note = f"auth=on (rotation: {len(bound_secrets)} valid tokens)"
    else:
        auth_note = "auth=on"
    logger.info(
        "Theoria listening on http://%s:%d (traces=%d, %s)",
        host, port, len(resolved_store), auth_note,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down Theoria")
    finally:
        server.server_close()
