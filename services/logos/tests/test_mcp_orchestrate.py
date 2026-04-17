"""Tests for the orchestrate_proof MCP handler."""

from __future__ import annotations

import pytest

from logos import certify
from logos.mcp_session_store import ORCHESTRATOR_STORE
from logos.mcp_tools import orchestrate_proof


@pytest.fixture(autouse=True)
def clear_orchestrator_store() -> None:
    ORCHESTRATOR_STORE.clear()


def test_orchestrate_proof_create_root_and_status() -> None:
    create = orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )
    status = orchestrate_proof({"action": "status", "session_id": "demo"})

    assert create["status"] == "created"
    assert status == {
        "status": "ok",
        "total": 1,
        "verified": 0,
        "failed": 0,
        "pending": 1,
        "is_complete": False,
    }


def test_orchestrate_proof_add_sub_claim() -> None:
    orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )

    result = orchestrate_proof(
        {
            "action": "add_sub_claim",
            "session_id": "demo",
            "claim_id": "leaf",
            "parent_id": "root",
            "description": "Leaf claim",
        }
    )
    tree = orchestrate_proof({"action": "get_tree", "session_id": "demo"})
    root_claim = next(claim for claim in tree["tree"]["claims"] if claim["claim_id"] == "root")

    assert result["status"] == "added"
    assert root_claim["sub_claim_ids"] == ["leaf"]


def test_orchestrate_proof_verify_leaf() -> None:
    orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )
    orchestrate_proof(
        {
            "action": "add_sub_claim",
            "session_id": "demo",
            "claim_id": "leaf",
            "parent_id": "root",
            "description": "Leaf claim",
        }
    )

    result = orchestrate_proof(
        {"action": "verify_leaf", "session_id": "demo", "claim_id": "leaf", "expression": "P |- P"}
    )

    assert result["status"] == "verified"
    assert result["verified"] is True


def test_orchestrate_proof_attach_certificate() -> None:
    orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )
    orchestrate_proof(
        {
            "action": "add_sub_claim",
            "session_id": "demo",
            "claim_id": "leaf",
            "parent_id": "root",
            "description": "Leaf claim",
        }
    )

    result = orchestrate_proof(
        {
            "action": "attach_certificate",
            "session_id": "demo",
            "claim_id": "leaf",
            "certificate_json": certify("P |- P").to_json(),
        }
    )

    assert result["status"] == "attached"


def test_orchestrate_proof_propagates_all_verified_to_parent() -> None:
    orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )
    orchestrate_proof(
        {
            "action": "add_sub_claim",
            "session_id": "demo",
            "claim_id": "a",
            "parent_id": "root",
            "description": "A",
            "composition_rule": "a AND b",
        }
    )
    orchestrate_proof(
        {
            "action": "add_sub_claim",
            "session_id": "demo",
            "claim_id": "b",
            "parent_id": "root",
            "description": "B",
            "composition_rule": "a AND b",
        }
    )
    orchestrate_proof({"action": "verify_leaf", "session_id": "demo", "claim_id": "a", "expression": "P |- P"})
    orchestrate_proof({"action": "verify_leaf", "session_id": "demo", "claim_id": "b", "expression": "Q |- Q"})

    result = orchestrate_proof({"action": "propagate", "session_id": "demo"})

    assert result["status"] == "propagated"
    assert result["is_complete"] is True


def test_orchestrate_proof_propagates_failed_child_to_parent() -> None:
    orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )
    orchestrate_proof(
        {
            "action": "add_sub_claim",
            "session_id": "demo",
            "claim_id": "a",
            "parent_id": "root",
            "description": "A",
            "composition_rule": "a AND b",
        }
    )
    orchestrate_proof(
        {
            "action": "add_sub_claim",
            "session_id": "demo",
            "claim_id": "b",
            "parent_id": "root",
            "description": "B",
            "composition_rule": "a AND b",
        }
    )
    orchestrate_proof({"action": "verify_leaf", "session_id": "demo", "claim_id": "a", "expression": "P |- P"})
    orchestrate_proof(
        {"action": "verify_leaf", "session_id": "demo", "claim_id": "b", "expression": "P -> Q, Q |- P"}
    )

    result = orchestrate_proof({"action": "propagate", "session_id": "demo"})

    assert result["failed"] == 2
    assert result["is_complete"] is False


def test_orchestrate_proof_mark_failed() -> None:
    orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )

    result = orchestrate_proof(
        {"action": "mark_failed", "session_id": "demo", "claim_id": "root", "reason": "manual"}
    )

    assert result["status"] == "marked_failed"


def test_orchestrate_proof_get_tree_returns_serialized_tree() -> None:
    orchestrate_proof(
        {
            "action": "create_root",
            "session_id": "demo",
            "claim_id": "root",
            "description": "Main claim",
        }
    )

    result = orchestrate_proof({"action": "get_tree", "session_id": "demo"})

    assert result["status"] == "ok"
    assert result["tree"]["root_id"] == "root"


def test_orchestrate_proof_rejects_unknown_session() -> None:
    result = orchestrate_proof({"action": "status", "session_id": "missing"})

    assert result["error"] == "Invalid input"
