"""Example — POST a custom decision trace to a running Theoria server.

Usage:
    # Terminal 1:
    python -m theoria
    # Terminal 2:
    python services/theoria/examples/post_trace.py
"""

from __future__ import annotations

import json
import urllib.request

from theoria.ingest import trace_from_tree
from theoria.models import Outcome


def main() -> None:
    trace = trace_from_tree(
        trace_id="demo-should-we-deploy",
        title="Should we deploy on a Friday?",
        question="Is a Friday-afternoon deploy acceptable right now?",
        source="custom",
        kind="policy",
        tree={
            "id": "q",
            "kind": "question",
            "label": "Deploy now?",
            "children": [
                {
                    "id": "ci",
                    "kind": "observation",
                    "label": "CI is green on main",
                    "status": "ok",
                },
                {
                    "id": "oncall",
                    "kind": "observation",
                    "label": "On-call engineer is available",
                    "status": "ok",
                },
                {
                    "id": "time",
                    "kind": "constraint",
                    "label": "Time-of-week: Friday 16:30",
                    "status": "triggered",
                    "detail": "Within the Friday-afternoon freeze window",
                },
                {
                    "id": "decision",
                    "kind": "conclusion",
                    "label": "Block: waits until Monday",
                    "status": "failed",
                    "relation": "yields",
                },
            ],
        },
        outcome=Outcome(
            verdict="block",
            summary="Freeze window violated; deploy deferred to Monday.",
            confidence=1.0,
        ),
        tags=["demo", "deploy"],
    )

    req = urllib.request.Request(
        "http://127.0.0.1:8765/api/traces",
        data=json.dumps(trace.to_dict()).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req) as resp:
        print(resp.status, resp.read().decode())


if __name__ == "__main__":
    main()
