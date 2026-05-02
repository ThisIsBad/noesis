"""Scenario tests for the Praxis MCP tool wrappers.

The ``test_core.py`` suite covers the ``PraxisCore`` layer directly;
this module drives the ``@mcp.tool()`` HTTP wrappers through every
success path and every error branch, which is where the Stage-3
user-facing behaviour lives (plan-not-found, parent-not-found, JSON
shape of responses, `alternatives` / `paths` envelopes).
"""

from __future__ import annotations

import json
from typing import Any, cast

import praxis.mcp_server_http as server


def _tool(name: str) -> Any:
    return server.mcp._tool_manager._tools[name].fn


def _new_plan(goal: str = "ship the feature") -> str:
    payload = json.loads(cast(str, _tool("decompose_goal")(goal)))
    return cast(str, payload["plan_id"])


# ── decompose_goal ────────────────────────────────────────────────────────────


def test_decompose_goal_returns_plan_json_with_id_and_goal() -> None:
    payload = json.loads(_tool("decompose_goal")("write the RFC"))
    assert payload["goal"] == "write the RFC"
    assert payload["plan_id"]
    assert payload["depth"] == 0
    assert payload["parent_plan_id"] is None


def test_decompose_goal_nested_plan_inherits_depth_plus_one() -> None:
    parent_id = _new_plan("epic parent")
    child_payload = json.loads(
        _tool("decompose_goal")("sub-goal", parent_plan_id=parent_id)
    )
    assert child_payload["depth"] == 1
    assert child_payload["parent_plan_id"] == parent_id


def test_decompose_goal_with_unknown_parent_returns_error_envelope() -> None:
    payload = json.loads(
        _tool("decompose_goal")("orphan", parent_plan_id="does-not-exist")
    )
    assert payload == {"error": "parent plan not found"}


# ── evaluate_step ─────────────────────────────────────────────────────────────


def test_evaluate_step_happy_path_returns_step_json() -> None:
    plan_id = _new_plan()
    raw = _tool("evaluate_step")(
        plan_id=plan_id,
        description="draft the API",
        tool_call="logos.verify_argument",
        risk_score=0.2,
    )
    step = json.loads(raw)
    assert step["description"] == "draft the API"
    assert step["tool_call"] == "logos.verify_argument"
    assert step["status"] == "pending"
    assert step["risk_score"] == 0.2
    assert step["step_id"]


def test_evaluate_step_with_unknown_plan_returns_error() -> None:
    payload = json.loads(
        _tool("evaluate_step")(plan_id="no-such-plan", description="x")
    )
    assert "error" in payload


def test_evaluate_step_with_unknown_parent_step_returns_error() -> None:
    plan_id = _new_plan()
    payload = json.loads(
        _tool("evaluate_step")(
            plan_id=plan_id,
            description="child",
            parent_step_id="missing",
        )
    )
    assert "error" in payload


# ── commit_step ───────────────────────────────────────────────────────────────


def test_commit_step_success_marks_completed() -> None:
    plan_id = _new_plan()
    step = json.loads(_tool("evaluate_step")(plan_id, "do X"))
    committed = json.loads(
        _tool("commit_step")(plan_id, step["step_id"], "done", success=True)
    )
    assert committed["status"] == "completed"
    assert committed["outcome"] == "done"


def test_commit_step_failure_marks_failed_and_penalises_score() -> None:
    plan_id = _new_plan()
    step = json.loads(_tool("evaluate_step")(plan_id, "risky", risk_score=0.0))
    committed = json.loads(
        _tool("commit_step")(plan_id, step["step_id"], "boom", success=False)
    )
    assert committed["status"] == "failed"


def test_commit_step_with_unknown_step_returns_error() -> None:
    plan_id = _new_plan()
    payload = json.loads(
        _tool("commit_step")(plan_id, "bogus-step", "n/a", success=True)
    )
    assert "error" in payload


# ── backtrack ────────────────────────────────────────────────────────────────


def test_backtrack_after_failure_surfaces_pending_sibling() -> None:
    plan_id = _new_plan()
    failed = json.loads(_tool("evaluate_step")(plan_id, "path A"))
    alt = json.loads(_tool("evaluate_step")(plan_id, "path B"))
    _tool("commit_step")(plan_id, failed["step_id"], "nope", success=False)

    payload = json.loads(_tool("backtrack")(plan_id))
    alt_ids = {s["step_id"] for s in payload["alternatives"]}
    assert alt["step_id"] in alt_ids


def test_backtrack_on_unknown_plan_returns_error() -> None:
    payload = json.loads(_tool("backtrack")("no-plan"))
    assert payload == {"error": "plan not found"}


# ── verify_plan ──────────────────────────────────────────────────────────────


def test_verify_plan_passes_low_risk_plan() -> None:
    plan_id = _new_plan()
    _tool("evaluate_step")(plan_id, "safe step", risk_score=0.1)
    payload = json.loads(_tool("verify_plan")(plan_id))
    assert payload["verified"] is True
    assert "message" in payload


def test_verify_plan_rejects_high_risk_plan() -> None:
    plan_id = _new_plan()
    _tool("evaluate_step")(plan_id, "yolo step", risk_score=0.95)
    payload = json.loads(_tool("verify_plan")(plan_id))
    assert payload["verified"] is False


def test_verify_plan_rejects_empty_plan() -> None:
    plan_id = _new_plan()
    payload = json.loads(_tool("verify_plan")(plan_id))
    assert payload["verified"] is False
    assert "no steps" in payload["message"].lower()


def test_verify_plan_on_unknown_plan_returns_error() -> None:
    payload = json.loads(_tool("verify_plan")("missing"))
    assert payload == {"error": "plan not found"}


# ── get_next_step ────────────────────────────────────────────────────────────


def test_get_next_step_returns_first_pending_on_best_path() -> None:
    plan_id = _new_plan()
    step = json.loads(_tool("evaluate_step")(plan_id, "do this"))
    payload = json.loads(_tool("get_next_step")(plan_id))
    assert payload["step_id"] == step["step_id"]


def test_get_next_step_returns_none_when_all_completed() -> None:
    plan_id = _new_plan()
    step = json.loads(_tool("evaluate_step")(plan_id, "only step"))
    _tool("commit_step")(plan_id, step["step_id"], "done", success=True)
    payload = json.loads(_tool("get_next_step")(plan_id))
    assert payload == {"step": None, "message": "all steps completed"}


def test_get_next_step_unknown_plan_returns_error() -> None:
    payload = json.loads(_tool("get_next_step")("nope"))
    assert payload == {"error": "plan not found"}


# ── best_path ────────────────────────────────────────────────────────────────


def test_best_path_returns_top_k_paths() -> None:
    plan_id = _new_plan()
    _tool("evaluate_step")(plan_id, "option A", risk_score=0.1)
    _tool("evaluate_step")(plan_id, "option B", risk_score=0.9)
    payload = json.loads(_tool("best_path")(plan_id, k=2))
    assert "paths" in payload
    assert isinstance(payload["paths"], list)


def test_best_path_unknown_plan_returns_error() -> None:
    payload = json.loads(_tool("best_path")("nope"))
    assert payload == {"error": "plan not found"}


# ── get_plan ─────────────────────────────────────────────────────────────────


def test_get_plan_returns_full_plan_payload() -> None:
    plan_id = _new_plan("build the thing")
    _tool("evaluate_step")(plan_id, "first")
    payload = json.loads(_tool("get_plan")(plan_id))
    assert payload["plan_id"] == plan_id
    assert payload["goal"] == "build the thing"


def test_get_plan_unknown_plan_returns_error() -> None:
    payload = json.loads(_tool("get_plan")("nope"))
    assert payload == {"error": "plan not found"}
