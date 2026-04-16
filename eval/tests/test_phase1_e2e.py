"""
Phase 1 end-to-end scenario:
  register_goal (Telos) → decompose_goal (Praxis) → verify_plan (Logos)
  → commit_step + store_memory (Mneme)

All tests marked integration — require deployed services via env vars.
"""
import pytest

pytestmark = pytest.mark.integration


def test_telos_registers_goal(telos_url, http):
    resp = http.post(f"{telos_url}/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "register_goal", "arguments": {
            "description": "E2E smoke test goal",
            "preconditions": [],
            "postconditions": [{"description": "test passed"}],
        }},
    })
    assert resp.status_code == 200
    result = resp.json()
    assert "goal_id" in str(result)


def test_mneme_store_and_retrieve(mneme_url, http):
    store = http.post(f"{mneme_url}/mcp", json={
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": "store_memory", "arguments": {
            "content": "E2E test memory: the sky is blue",
            "memory_type": "semantic",
            "confidence": 0.9,
        }},
    })
    assert store.status_code == 200

    retrieve = http.post(f"{mneme_url}/mcp", json={
        "jsonrpc": "2.0", "id": 2, "method": "tools/call",
        "params": {"name": "retrieve_memory", "arguments": {
            "query": "sky colour",
            "k": 1,
        }},
    })
    assert retrieve.status_code == 200
    assert "blue" in str(retrieve.json()).lower()
