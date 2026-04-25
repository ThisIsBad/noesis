"""Probe a live Noesis stack and print a green/red dashboard.

Reads service URLs from `.mcp.json` at the repo root (or `--mcp-json`)
and probes each one. For each service:

* GET  ``<url>/health``                      — unauth'd liveness probe
* HEAD ``<url>/sse``  (Bearer <token>)        — auth'd MCP-surface probe

The token comes from one of (in order):

    1. ``--token-env`` CLI flag (e.g. ``--token-env LOGOS_SECRET``)
    2. ``<SVC>_SECRET`` env var (default convention)
    3. ``--secrets-file`` (a shell-style ``KEY=VAL`` file)
    4. None — auth'd probe is skipped

Output is a fixed-width table to stdout. Exit code is 0 iff every
service passes both probes (or the auth'd probe is skipped because no
token was found).

This is the post-deploy sanity-check counterpart to
``deploy_all_services.py`` and the day-2 ops counterpart to
``docs/operations/deploy-runbook.md`` Phase 4.

Usage::

    # Probe whichever endpoints .mcp.json points at
    python tools/probe_live_stack.py

    # Probe a different mcp.json (e.g. while testing local docker-compose)
    python tools/probe_live_stack.py --mcp-json /tmp/local.mcp.json

    # Probe with secrets from a shell-style env file
    python tools/probe_live_stack.py --secrets-file ~/.noesis-secrets

    # Quiet mode (only prints failures)
    python tools/probe_live_stack.py -q
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MCP_JSON = REPO_ROOT / ".mcp.json"
TIMEOUT_S = 10.0


@dataclass(frozen=True)
class Result:
    name: str
    url: str
    health: str        # "200" / "TIMEOUT" / "CONN" / "<other>"
    auth: str          # "200" / "401" / "skipped" / etc
    ok: bool

    def emoji(self) -> str:
        return "✅" if self.ok else "❌"


def _load_mcp_servers(mcp_json: Path) -> dict[str, str]:
    """Return ``{service_name: base_url}`` from `.mcp.json`.

    Strips the ``/mcp`` or ``/sse`` suffix that Claude Code expects so
    we can re-attach `/health` and `/sse` cleanly.
    """
    data = json.loads(mcp_json.read_text())
    servers = data.get("mcpServers") or {}
    out: dict[str, str] = {}
    for name, cfg in servers.items():
        url = (cfg.get("url") or "").rstrip("/")
        # Claude Code config typically points at /mcp or /sse — drop it.
        for suffix in ("/mcp", "/sse"):
            if url.endswith(suffix):
                url = url[: -len(suffix)]
                break
        if url:
            out[name] = url
    return out


def _load_secrets_file(path: Path | None) -> dict[str, str]:
    if path is None:
        return {}
    secrets: dict[str, str] = {}
    pattern = re.compile(r"^\s*([A-Z_][A-Z0-9_]*)\s*=\s*(.+?)\s*$")
    for raw in path.read_text().splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        m = pattern.match(raw)
        if not m:
            continue
        secrets[m.group(1)] = m.group(2).strip().strip("'\"")
    return secrets


def _resolve_token(
    name: str,
    *,
    token_env: str | None,
    secrets_file: dict[str, str],
) -> str | None:
    """Find the bearer token for service ``name`` (case-insensitive)."""
    candidate = token_env or f"{name.upper()}_SECRET"
    return os.environ.get(candidate) or secrets_file.get(candidate)


def _probe_health(url: str) -> str:
    try:
        with urllib.request.urlopen(  # noqa: S310 — caller-supplied URL is trusted
            f"{url}/health",
            timeout=TIMEOUT_S,
        ) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            return "TIMEOUT"
        return "CONN"
    except TimeoutError:
        return "TIMEOUT"
    except Exception as e:  # noqa: BLE001 - last-ditch fallback for the dashboard
        return f"ERR:{type(e).__name__}"


def _probe_sse(url: str, token: str | None) -> str:
    """Probe the bearer-gated SSE endpoint.

    With a token we expect 200 (open SSE stream — we abandon the read
    almost immediately). Without a token we *also* expect 200 if the
    service is in fail-open mode (no ``<SVC>_SECRET`` set), or 401 if
    the service is gated. Either way a 502 / 5xx is bad.
    """
    req = urllib.request.Request(f"{url}/sse")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:  # noqa: S310
            # Read one byte to confirm the stream actually opened, then bail.
            try:
                resp.read(1)
            except Exception:  # noqa: BLE001
                pass
            return str(resp.status)
    except urllib.error.HTTPError as e:
        return str(e.code)
    except urllib.error.URLError as e:
        if "timed out" in str(e).lower():
            return "TIMEOUT"
        return "CONN"
    except TimeoutError:
        return "TIMEOUT"
    except Exception as e:  # noqa: BLE001
        return f"ERR:{type(e).__name__}"


def probe(
    servers: dict[str, str],
    *,
    secrets_file: dict[str, str],
    token_env: str | None,
) -> list[Result]:
    results: list[Result] = []
    for name, url in sorted(servers.items()):
        token = _resolve_token(
            name, token_env=token_env, secrets_file=secrets_file
        )
        health = _probe_health(url)
        auth = _probe_sse(url, token) if token else "skipped"
        ok = health == "200" and (
            auth in {"200", "skipped"} or auth.startswith("2")
        )
        results.append(Result(name=name, url=url, health=health, auth=auth, ok=ok))
    return results


def render(results: Iterable[Result], *, quiet: bool) -> str:
    rows = list(results)
    if quiet:
        rows = [r for r in rows if not r.ok]
    if not rows:
        return "All probes green.\n" if not quiet else ""
    name_w = max(len(r.name) for r in rows)
    url_w = max(len(r.url) for r in rows)
    header = (
        f"{'':2}  {'service':<{name_w}}  {'url':<{url_w}}  "
        f"{'/health':<8}  {'auth':<8}"
    )
    lines = [header, "-" * len(header)]
    for r in rows:
        lines.append(
            f"{r.emoji()}  {r.name:<{name_w}}  {r.url:<{url_w}}  "
            f"{r.health:<8}  {r.auth:<8}"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n", 1)[0])
    p.add_argument(
        "--mcp-json",
        type=Path,
        default=DEFAULT_MCP_JSON,
        help="Path to .mcp.json (default: repo-root .mcp.json)",
    )
    p.add_argument(
        "--secrets-file",
        type=Path,
        default=None,
        help="KEY=VAL file with <SVC>_SECRET entries.",
    )
    p.add_argument(
        "--token-env",
        default=None,
        help=(
            "Override the per-service env-var convention. Useful when "
            "every service shares one shared-dev-secret in local mode."
        ),
    )
    p.add_argument("-q", "--quiet", action="store_true", help="Only print failures")
    args = p.parse_args(argv)

    if not args.mcp_json.exists():
        print(f"ERROR: {args.mcp_json} does not exist", file=sys.stderr)
        return 2

    servers = _load_mcp_servers(args.mcp_json)
    if not servers:
        print(f"ERROR: no mcpServers in {args.mcp_json}", file=sys.stderr)
        return 2

    secrets_file = _load_secrets_file(args.secrets_file)

    results = probe(servers, secrets_file=secrets_file, token_env=args.token_env)
    sys.stdout.write(render(results, quiet=args.quiet))
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
