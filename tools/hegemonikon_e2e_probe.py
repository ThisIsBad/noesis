"""End-to-end smoke probe against a live Hegemonikon.

Drives ``http://127.0.0.1:$PORT`` with a canned prompt, consumes the
SSE stream until ``session.done`` (or ``session.error``), and validates
the resulting ``DecisionTrace`` in the trailing ``trace.update`` event.

The validation mirrors what ``test_hegemonikon_inprocess.py`` checks at the
in-process layer, but against a *real* Hegemonikon process — so this
covers ASGI bootstrap, bearer middleware, MCP env wiring, and TraceBuilder
end-to-end.

Default mode runs against ``HEGEMONIKON_FAKE_QUERY=1`` (Hegemonikon returns the
canned scripted iterator from ``hegemonikon._fake_query``) so the probe is
deterministic. Set ``--real`` to drive Claude for real (the Hegemonikon
process must be booted with ``HEGEMONIKON_FAKE_QUERY`` unset and a
logged-in ``claude`` CLI on PATH).

Exit codes:
  0  — full session: session.start → tool events → session.done with
       Outcome.complete and ≥5 trace steps.
  1  — protocol mismatch (missing event, bad order, wrong shape).
  2  — Hegemonikon unreachable / non-2xx status / SSE never finished.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from typing import Any

import httpx


def _parse_sse_chunks(buf: str) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for chunk in buf.split("\n\n"):
        if not chunk.strip():
            continue
        data_line = None
        for line in chunk.splitlines():
            if line.startswith("data:"):
                data_line = line[len("data:"):].strip()
        if data_line is None:
            continue
        try:
            events.append(json.loads(data_line))
        except json.JSONDecodeError:
            continue
    return events


async def run(
    base_url: str,
    bearer: str,
    prompt: str,
    *,
    timeout_s: float = 60.0,
) -> int:
    headers = {"Authorization": f"Bearer {bearer}"} if bearer else {}
    async with httpx.AsyncClient(
        base_url=base_url, headers=headers, timeout=timeout_s,
    ) as client:
        # 1. Health.
        try:
            health = await client.get("/health")
        except httpx.HTTPError as exc:
            print(f"E2E-PROBE: hegemonikon unreachable: {exc}", file=sys.stderr)
            return 2
        if health.status_code != 200:
            print(
                f"E2E-PROBE: /health returned {health.status_code}: "
                f"{health.text[:200]}",
                file=sys.stderr,
            )
            return 2
        print(f"E2E-PROBE: /health ok — {health.json()}")

        # 2. Open session.
        chat_resp = await client.post("/api/chat", json={"prompt": prompt})
        if chat_resp.status_code != 202:
            print(
                f"E2E-PROBE: /api/chat returned {chat_resp.status_code}: "
                f"{chat_resp.text[:200]}",
                file=sys.stderr,
            )
            return 2
        session_id = chat_resp.json()["session_id"]
        print(f"E2E-PROBE: session_id = {session_id}")

        # 3. Drain stream.
        chunks: list[bytes] = []
        async with client.stream(
            "GET", f"/api/stream?session_id={session_id}",
        ) as stream_resp:
            if stream_resp.status_code != 200:
                print(
                    f"E2E-PROBE: /api/stream returned "
                    f"{stream_resp.status_code}",
                    file=sys.stderr,
                )
                return 2
            try:
                async for chunk in stream_resp.aiter_bytes():
                    chunks.append(chunk)
                    joined = b"".join(chunks)
                    if b"session.done" in joined or b"session.error" in joined:
                        break
            except httpx.HTTPError as exc:
                print(f"E2E-PROBE: stream broken: {exc}", file=sys.stderr)
                return 2

    text = b"".join(chunks).decode(errors="replace")
    events = _parse_sse_chunks(text)
    if not events:
        print("E2E-PROBE: no SSE events parsed", file=sys.stderr)
        return 1

    types = [e.get("type", "?") for e in events]
    print(f"E2E-PROBE: SSE event sequence: {types}")

    if types[0] != "session.start":
        print(
            f"E2E-PROBE: expected first event session.start, got {types[0]}",
            file=sys.stderr,
        )
        return 1

    if "session.error" in types:
        err = next(e for e in events if e["type"] == "session.error")
        print(f"E2E-PROBE: session.error: {err.get('error')}", file=sys.stderr)
        return 1

    if "session.done" not in types:
        print("E2E-PROBE: stream ended without session.done", file=sys.stderr)
        return 1

    trace_updates = [e for e in events if e["type"] == "trace.update"]
    if not trace_updates:
        print("E2E-PROBE: no trace.update events seen", file=sys.stderr)
        return 1

    final = trace_updates[-1].get("trace") or {}
    steps = final.get("steps") or []
    if len(steps) < 5:
        print(
            f"E2E-PROBE: expected ≥5 trace steps, got {len(steps)}",
            file=sys.stderr,
        )
        return 1

    if final.get("question") != prompt:
        print(
            f"E2E-PROBE: trace.question mismatch ({final.get('question')!r} "
            f"!= {prompt!r})",
            file=sys.stderr,
        )
        return 1

    outcome = final.get("outcome") or {}
    if outcome.get("verdict") != "complete":
        print(
            f"E2E-PROBE: outcome.verdict = {outcome.get('verdict')!r} "
            "(expected 'complete')",
            file=sys.stderr,
        )
        return 1

    print(
        f"E2E-PROBE: trace ok — {len(steps)} steps, outcome={outcome['verdict']}, "
        f"summary={outcome.get('summary', '')[:60]!r}"
    )
    return 0


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--base-url", default="http://127.0.0.1:8010")
    p.add_argument("--bearer", default="dev-hegemonikon-secret")
    p.add_argument(
        "--prompt",
        default=(
            "Refactor the auth gate: register the goal with telos, "
            "decompose it with praxis, and report what you'd verify."
        ),
    )
    p.add_argument("--timeout", type=float, default=60.0)
    args = p.parse_args()

    code = asyncio.run(
        run(args.base_url, args.bearer, args.prompt, timeout_s=args.timeout)
    )
    sys.exit(code)


if __name__ == "__main__":
    main()
