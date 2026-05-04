"""Walking-skeleton smoke test for the Hegemonikon gateway.

Drives a deployed Hegemonikon's ``/gateway/sse`` endpoint through the
real MCP SSE protocol — no fakes, no in-process shortcuts. Used to
verify that the Bronze / Silver thresholds for "the skeleton walks"
hold against the actual Railway deploy.

Hierarchy of checks
-------------------

**Bronze** — gateway is reachable and authenticating.

  1. ``GET /health`` returns 200 with ``service=hegemonikon`` and the
     expected list of configured backends in ``mcp_servers``.
  2. SSE handshake against ``/gateway/sse`` with bearer succeeds
     (we receive an ``endpoint`` event).
  3. ``tools/list`` returns at least one tool, all names follow the
     ``<service>__<tool>`` pattern, every prefix appears in
     ``/health``'s ``mcp_servers`` list.

**Silver** — Bronze + an actual round-trip through one backend.

  4. ``telos__register_goal`` creates a marker goal
     (``description="_smoke_test_<random>"``).
  5. ``telos__list_active_goals`` returns a list that contains the
     marker goal we just created.

The marker tag is left in the Telos DB for inspection — Telos has no
``delete_goal`` tool. Pass ``--cleanup-warning`` to print a warning
about the residual rows; otherwise the script stays quiet.

**Gold** — Silver + cross-service composition (Praxis, Mneme).

Not implemented in this script — Gold is Phase-1 territory. Bronze +
Silver are sufficient to declare "Walking Skeleton walks".

Usage
-----

::

    export HEGEMONIKON_SECRET=<your-bearer>
    python tools/gateway_smoke.py \\
        --base-url https://noesis-hegemonikon.up.railway.app \\
        --level silver

Exit codes
----------

  0 — everything at the requested level green
  1 — at least one check failed
  2 — couldn't reach Hegemonikon at all (network / auth / DNS)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import secrets
import sys
import urllib.error
import urllib.request
from contextlib import AsyncExitStack
from dataclasses import dataclass, field
from typing import Any

EXPECTED_BACKENDS = {
    "logos",
    "mneme",
    "praxis",
    "telos",
    "episteme",
    "kosmos",
    "empiria",
    "techne",
}
"""The full eight cognitive services. ``/health`` should list this set
exactly when all eight ``NOESIS_<SVC>_URL`` env vars are set on the
Hegemonikon Railway service. A subset means partial config; the smoke
test reports the diff but doesn't fail on it (gateway is supposed to
degrade gracefully)."""


# ── ANSI colors ───────────────────────────────────────────────────────────────
GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
DIM = "\033[2m"
RESET = "\033[0m"


def _ok(msg: str) -> None:
    print(f"  {GREEN}✓{RESET} {msg}")


def _warn(msg: str) -> None:
    print(f"  {YELLOW}!{RESET} {msg}")


def _fail(msg: str) -> None:
    print(f"  {RED}✗{RESET} {msg}")


def _section(title: str) -> None:
    print(f"\n{title}")
    print(DIM + "─" * len(title) + RESET)


# ── result tracking ──────────────────────────────────────────────────────────
@dataclass
class Report:
    failures: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def fail(self, msg: str) -> None:
        self.failures.append(msg)
        _fail(msg)

    def warn(self, msg: str) -> None:
        self.warnings.append(msg)
        _warn(msg)

    def summary(self) -> str:
        if not self.failures and not self.warnings:
            return f"{GREEN}all checks passed{RESET}"
        out = []
        if self.failures:
            out.append(f"{RED}{len(self.failures)} failure(s){RESET}")
        if self.warnings:
            out.append(f"{YELLOW}{len(self.warnings)} warning(s){RESET}")
        return ", ".join(out)


# ── Bronze: health + SSE handshake + tools/list ──────────────────────────────


def check_health(base_url: str, report: Report) -> dict[str, Any] | None:
    _section("Bronze 1/3 — /health reachable")
    url = base_url.rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=10.0) as resp:
            if resp.status != 200:
                report.fail(f"GET /health returned HTTP {resp.status}")
                return None
            body = json.loads(resp.read().decode())
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as exc:
        report.fail(f"GET /health unreachable: {exc}")
        return None

    _ok(f"HTTP 200 ({url})")
    if body.get("service") != "hegemonikon":
        report.fail(
            f"service identity is {body.get('service')!r}, expected 'hegemonikon' "
            "(stale image still being served — trigger Railway rebuild)"
        )
    else:
        _ok("service=hegemonikon (deployed image is post-rename)")

    listed = set(body.get("mcp_servers", []))
    if listed == EXPECTED_BACKENDS:
        _ok(f"all 8 backends configured: {sorted(listed)}")
    else:
        missing = EXPECTED_BACKENDS - listed
        extra = listed - EXPECTED_BACKENDS
        if missing:
            report.warn(
                f"missing NOESIS_<SVC>_URL env vars on Hegemonikon for: "
                f"{sorted(missing)}"
            )
        if extra:
            report.warn(f"unknown backends listed: {sorted(extra)}")
    return body


async def _open_session(
    base_url: str, bearer: str
) -> tuple[Any, AsyncExitStack]:
    """Return an initialized MCP ClientSession plus its exit stack.

    Caller must ``await stack.aclose()`` to clean up. Two-piece return
    because the session itself is an async-context-managed handle that
    only stays alive inside the stack."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    sse_url = base_url.rstrip("/") + "/gateway/sse"
    headers = {"Authorization": f"Bearer {bearer}"}
    stack = AsyncExitStack()
    read, write = await stack.enter_async_context(sse_client(sse_url, headers=headers))
    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session, stack


async def check_gateway_handshake_and_tools(
    base_url: str, bearer: str, report: Report
) -> list[Any]:
    """Bronze 2 + 3: SSE handshake + tools/list. Returns the discovered tools."""
    _section("Bronze 2/3 — /gateway/sse handshake")
    try:
        session, stack = await _open_session(base_url, bearer)
    except Exception as exc:
        report.fail(
            f"SSE handshake failed: {type(exc).__name__}: {exc}\n"
            "  hint: is HEGEMONIKON_SECRET set correctly? is /gateway/sse exposed?"
        )
        return []
    _ok("MCP session initialized")

    try:
        _section("Bronze 3/3 — tools/list across all backends")
        result = await asyncio.wait_for(session.list_tools(), timeout=30.0)
        tools = list(result.tools)
        if not tools:
            report.fail(
                "tools/list returned empty — gateway can't reach any backend.\n"
                "  hint: backends might require bearer auth that the gateway "
                "doesn't have. Check Hegemonikon logs for 'tools/list failed' warnings."
            )
            return []

        _ok(f"discovered {len(tools)} tools")

        prefixes: dict[str, int] = {}
        bad_names: list[str] = []
        for t in tools:
            if "__" not in t.name:
                bad_names.append(t.name)
                continue
            prefix = t.name.split("__", 1)[0]
            prefixes[prefix] = prefixes.get(prefix, 0) + 1

        if bad_names:
            report.fail(
                f"{len(bad_names)} tool(s) without service prefix: "
                f"{bad_names[:3]}{'...' if len(bad_names) > 3 else ''}"
            )

        for svc, count in sorted(prefixes.items()):
            tag = f"{GREEN}✓{RESET}" if svc in EXPECTED_BACKENDS else f"{YELLOW}?{RESET}"
            print(f"    {tag} {svc:10s} {count} tool(s)")

        unreachable = EXPECTED_BACKENDS - prefixes.keys()
        if unreachable:
            report.warn(
                f"backends configured but contributed no tools: {sorted(unreachable)}"
                "\n  (gateway tried to discover them but they returned empty / "
                "rejected the handshake — check those backends' /health and auth)"
            )
        return tools
    finally:
        await stack.aclose()


# ── Silver: telos round-trip ─────────────────────────────────────────────────


async def check_telos_roundtrip(
    base_url: str, bearer: str, report: Report
) -> None:
    _section("Silver — telos round-trip (register_goal → list_active_goals)")
    try:
        session, stack = await _open_session(base_url, bearer)
    except Exception as exc:
        report.fail(f"could not open MCP session: {exc}")
        return

    try:
        marker = f"_smoke_test_{secrets.token_hex(4)}"
        contract = {"description": marker}
        contract_json = json.dumps(contract)

        try:
            register_result = await asyncio.wait_for(
                session.call_tool(
                    "telos__register_goal",
                    {"contract_json": contract_json},
                ),
                timeout=15.0,
            )
        except Exception as exc:
            report.fail(
                f"telos__register_goal failed: {type(exc).__name__}: {exc}"
            )
            return
        if getattr(register_result, "isError", False):
            report.fail(
                f"telos__register_goal returned isError=true: "
                f"{_text_of(register_result)}"
            )
            return
        registered_payload = _text_of(register_result)
        _ok(f"register_goal ok ({DIM}{registered_payload[:80]}...{RESET})")

        try:
            list_result = await asyncio.wait_for(
                session.call_tool("telos__list_active_goals", {}),
                timeout=15.0,
            )
        except Exception as exc:
            report.fail(
                f"telos__list_active_goals failed: {type(exc).__name__}: {exc}"
            )
            return
        if getattr(list_result, "isError", False):
            report.fail(
                f"telos__list_active_goals returned isError=true: "
                f"{_text_of(list_result)}"
            )
            return

        listed_payload = _text_of(list_result)
        try:
            goals = json.loads(listed_payload)
        except json.JSONDecodeError as exc:
            report.fail(
                f"telos__list_active_goals payload not JSON: {exc}\n"
                f"  raw: {listed_payload[:200]}"
            )
            return

        marker_goals = [
            g for g in goals if isinstance(g, dict) and g.get("description") == marker
        ]
        if not marker_goals:
            report.fail(
                f"freshly-registered marker goal {marker!r} not found in "
                f"list_active_goals output (saw {len(goals)} other goals)"
            )
            return
        _ok(
            f"list_active_goals returns the marker goal ({len(goals)} active goal(s) total)"
        )
        report.warn(
            f"marker goal {marker!r} left in Telos DB — Telos has no delete_goal "
            "tool. Manual cleanup needed if you mind the residue."
        )
    finally:
        await stack.aclose()


def _text_of(call_result: Any) -> str:
    """Best-effort extract of textual content from a CallToolResult."""
    content = getattr(call_result, "content", None) or []
    chunks: list[str] = []
    for c in content:
        text = getattr(c, "text", None)
        if text is not None:
            chunks.append(text)
    return "\n".join(chunks)


# ── runner ───────────────────────────────────────────────────────────────────


async def run(base_url: str, bearer: str, level: str) -> int:
    report = Report()

    health = check_health(base_url, report)
    if health is None:
        print(f"\n{RED}aborted — Hegemonikon unreachable at /health{RESET}")
        return 2

    tools = await check_gateway_handshake_and_tools(base_url, bearer, report)
    if not tools:
        print(f"\n{RED}aborted — gateway returned no tools, can't run Silver{RESET}")
        return 1

    if level in ("silver", "gold"):
        await check_telos_roundtrip(base_url, bearer, report)

    if level == "gold":
        _section("Gold")
        report.warn(
            "Gold checks not implemented yet — Phase-1 territory. "
            "Bronze + Silver pass = Walking Skeleton walks."
        )

    print()
    _section("Summary")
    print(f"  {report.summary()}")
    if report.failures:
        for f in report.failures:
            print(f"    {RED}-{RESET} {f}")
    return 1 if report.failures else 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Walking-skeleton smoke test for the Hegemonikon gateway.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Hegemonikon base URL, e.g. https://noesis-hegemonikon.up.railway.app",
    )
    parser.add_argument(
        "--bearer",
        default=os.environ.get("HEGEMONIKON_SECRET", ""),
        help="HEGEMONIKON_SECRET (defaults to the env var of that name)",
    )
    parser.add_argument(
        "--level",
        choices=("bronze", "silver", "gold"),
        default="silver",
        help="how deep to probe (default: silver)",
    )
    args = parser.parse_args()

    if not args.bearer:
        print(
            f"{RED}error:{RESET} no bearer — set HEGEMONIKON_SECRET env var or "
            "pass --bearer",
            file=sys.stderr,
        )
        return 2

    return asyncio.run(run(args.base_url, args.bearer, args.level))


if __name__ == "__main__":
    sys.exit(main())
