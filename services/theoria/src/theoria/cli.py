"""Theoria command-line interface.

Subcommands::

    theoria                          # serve (default)
    theoria serve [--host ...]       # explicit serve
    theoria post  <file>             # POST a trace from a JSON file
    theoria export --id <id> --format {mermaid,dot,markdown}
    theoria list  [--source ... --verdict ... --q ... --limit N]
    theoria tail                     # subscribe to /api/stream, print events
    theoria sample                   # print a sample trace as JSON
    theoria diff  <a_id> <b_id> [--format {json,markdown,mermaid}]

Every subcommand reads ``THEORIA_URL`` (default ``http://127.0.0.1:8765``)
for remote calls.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import IO, Any, Sequence

from theoria.samples import build_samples
from theoria.server import serve
from theoria.store import TraceStore


DEFAULT_URL = "http://127.0.0.1:8765"


def main(argv: Sequence[str] | None = None, *, stdout: IO[str] | None = None) -> int:
    """Dispatch a Theoria CLI command. Returns a shell exit code."""
    stdout = stdout or sys.stdout
    # Back-compat: `theoria` (no args) and `theoria --port N` both serve.
    raw = list(argv) if argv is not None else sys.argv[1:]
    if not raw or raw[0] not in _COMMANDS:
        if not raw or raw[0].startswith("-"):
            raw = ["serve", *raw]
    parser = _build_parser()
    args = parser.parse_args(raw)

    command = args.command or "serve"
    handler = _COMMANDS[command]
    return handler(args, stdout)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="theoria",
        description="Decision-logic visualization server and client.",
    )
    sub = parser.add_subparsers(dest="command")

    # serve
    p_serve = sub.add_parser("serve", help="Run the Theoria HTTP server (default).")
    p_serve.add_argument("--host", default=os.environ.get("THEORIA_HOST", "127.0.0.1"))
    p_serve.add_argument("--port", type=int, default=int(os.environ.get("THEORIA_PORT", "8765")))
    p_serve.add_argument("--persist", default=os.environ.get("THEORIA_PERSIST"))
    p_serve.add_argument("--no-samples", action="store_true")
    p_serve.add_argument("--log-level", default=os.environ.get("THEORIA_LOG_LEVEL", "INFO"))

    # post
    p_post = sub.add_parser("post", help="POST a trace from a JSON file (or stdin).")
    p_post.add_argument("file", help='Path to a JSON file, or "-" for stdin.')
    p_post.add_argument("--url", default=os.environ.get("THEORIA_URL", DEFAULT_URL))

    # export
    p_export = sub.add_parser("export", help="Fetch + render a trace as text.")
    p_export.add_argument("--id", required=True, help="Trace id.")
    p_export.add_argument("--format", default="markdown",
                          choices=["json", "mermaid", "dot", "graphviz", "markdown", "md"])
    p_export.add_argument("--url", default=os.environ.get("THEORIA_URL", DEFAULT_URL))

    # list
    p_list = sub.add_parser("list", help="List traces with optional filters.")
    p_list.add_argument("--source")
    p_list.add_argument("--kind")
    p_list.add_argument("--verdict")
    p_list.add_argument("--tag", action="append", default=[])
    p_list.add_argument("--q", help="Full-text substring search.")
    p_list.add_argument("--limit", type=int)
    p_list.add_argument("--format", default="table", choices=["table", "json", "ids"])
    p_list.add_argument("--url", default=os.environ.get("THEORIA_URL", DEFAULT_URL))

    # tail
    p_tail = sub.add_parser("tail", help="Subscribe to the /api/stream SSE feed.")
    p_tail.add_argument("--url", default=os.environ.get("THEORIA_URL", DEFAULT_URL))

    # diff
    p_diff = sub.add_parser("diff", help="Diff two traces.")
    p_diff.add_argument("a_id")
    p_diff.add_argument("b_id")
    p_diff.add_argument("--format", default="markdown",
                        choices=["json", "markdown", "md", "mermaid"])
    p_diff.add_argument("--url", default=os.environ.get("THEORIA_URL", DEFAULT_URL))

    # sample — print one of the built-in sample traces as JSON
    p_sample = sub.add_parser("sample", help="Print a built-in sample trace as JSON.")
    p_sample.add_argument("--index", type=int, default=0,
                          help="Index into build_samples() (default: 0).")

    return parser


# ---------------------------------------------------------------------------
# subcommand handlers
# ---------------------------------------------------------------------------

def _cmd_serve(args: argparse.Namespace, stdout: IO[str]) -> int:
    logging.basicConfig(
        level=getattr(args, "log_level", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    persist_path = Path(args.persist) if getattr(args, "persist", None) else None
    store = TraceStore(persist_path=persist_path)
    serve(
        host=args.host,
        port=args.port,
        store=store,
        load_samples=not getattr(args, "no_samples", False),
    )
    return 0


def _cmd_post(args: argparse.Namespace, stdout: IO[str]) -> int:
    raw = sys.stdin.read() if args.file == "-" else Path(args.file).read_text(encoding="utf-8")
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"error: invalid JSON: {exc}", file=sys.stderr)
        return 2
    status, body = _http(args.url + "/api/traces", method="POST", body=payload)
    if status >= 400:
        print(f"error: HTTP {status}: {body}", file=sys.stderr)
        return 1
    print(f"POST /api/traces → {status}", file=stdout)
    if isinstance(body, dict) and "id" in body:
        print(f"id: {body['id']}", file=stdout)
    return 0


def _cmd_export(args: argparse.Namespace, stdout: IO[str]) -> int:
    if args.format == "json":
        url = f"{args.url}/api/traces/{urllib.parse.quote(args.id)}"
    else:
        url = (f"{args.url}/api/traces/{urllib.parse.quote(args.id)}"
               f"/export?format={urllib.parse.quote(args.format)}")
    status, body = _http(url)
    if status >= 400:
        print(f"error: HTTP {status}: {body}", file=sys.stderr)
        return 1
    if isinstance(body, (dict, list)):
        stdout.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
    else:
        stdout.write(body if body.endswith("\n") else body + "\n")
    return 0


def _cmd_list(args: argparse.Namespace, stdout: IO[str]) -> int:
    params: list[tuple[str, str]] = []
    for name in ("source", "kind", "verdict", "q"):
        value = getattr(args, name, None)
        if value:
            params.append((name, value))
    for tag in args.tag or []:
        params.append(("tag", tag))
    if args.limit is not None:
        params.append(("limit", str(args.limit)))
    url = args.url + "/api/traces" + ("?" + urllib.parse.urlencode(params) if params else "")
    status, body = _http(url)
    if status >= 400:
        print(f"error: HTTP {status}: {body}", file=sys.stderr)
        return 1
    traces: list[dict[str, Any]] = body["traces"] if isinstance(body, dict) else []
    if args.format == "ids":
        for trace in traces:
            stdout.write(f"{trace['id']}\n")
        return 0
    if args.format == "json":
        stdout.write(json.dumps(traces, indent=2, sort_keys=True) + "\n")
        return 0
    # table
    if not traces:
        stdout.write("(no traces match)\n")
        return 0
    id_w = max(len(t["id"]) for t in traces)
    src_w = max(len(t.get("source", "")) for t in traces)
    kind_w = max(len(t.get("kind", "")) for t in traces)
    for trace in traces:
        verdict = (trace.get("outcome") or {}).get("verdict", "—")
        stdout.write(
            f"{trace['id']:<{id_w}}  "
            f"{trace.get('source', ''):<{src_w}}  "
            f"{trace.get('kind', ''):<{kind_w}}  "
            f"{verdict:<15}  {trace.get('title', '')}\n"
        )
    return 0


def _cmd_tail(args: argparse.Namespace, stdout: IO[str]) -> int:
    url = args.url + "/api/stream"
    try:
        with urllib.request.urlopen(url) as resp:
            for raw in resp:
                line = raw.decode("utf-8", errors="replace").rstrip()
                if line:
                    stdout.write(line + "\n")
                    stdout.flush()
    except KeyboardInterrupt:
        return 0
    except urllib.error.URLError as exc:
        print(f"error: could not connect to {url}: {exc}", file=sys.stderr)
        return 1
    return 0


def _cmd_diff(args: argparse.Namespace, stdout: IO[str]) -> int:
    url = (f"{args.url}/api/traces/{urllib.parse.quote(args.a_id)}"
           f"/diff/{urllib.parse.quote(args.b_id)}?format={urllib.parse.quote(args.format)}")
    status, body = _http(url)
    if status >= 400:
        print(f"error: HTTP {status}: {body}", file=sys.stderr)
        return 1
    if isinstance(body, (dict, list)):
        stdout.write(json.dumps(body, indent=2, sort_keys=True) + "\n")
    else:
        stdout.write(body if body.endswith("\n") else body + "\n")
    return 0


def _cmd_sample(args: argparse.Namespace, stdout: IO[str]) -> int:
    samples = build_samples()
    index = max(0, min(args.index, len(samples) - 1))
    stdout.write(json.dumps(samples[index].to_dict(), indent=2, sort_keys=True) + "\n")
    return 0


_COMMANDS = {
    "serve": _cmd_serve,
    "post": _cmd_post,
    "export": _cmd_export,
    "list": _cmd_list,
    "tail": _cmd_tail,
    "diff": _cmd_diff,
    "sample": _cmd_sample,
}


# ---------------------------------------------------------------------------
# minimal HTTP helper (stdlib only)
# ---------------------------------------------------------------------------

def _http(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout: float = 10.0,
) -> tuple[int, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if body is not None else {}
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            ctype = resp.headers.get("Content-Type", "")
            status = resp.status
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        ctype = exc.headers.get("Content-Type", "") if exc.headers else ""
        status = exc.code
    except urllib.error.URLError as exc:
        return 599, f"connection error: {exc}"

    if "application/json" in ctype:
        try:
            return status, json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            return status, raw
    return status, raw
