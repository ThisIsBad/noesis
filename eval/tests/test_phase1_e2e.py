"""Phase 1 Durchstich — end-to-end integration against deployed services.

Exercises the full vertical slice over real MCP SSE transport::

    Telos.register_goal
      → Praxis.decompose_goal + commit_step
      → Mneme.store_memory + retrieve_memory
      → Empiria.record_experience     (REST, optional)

Each test skips cleanly when its required service env var is unset, so
running ``pytest -m integration`` with only ``NOESIS_MNEME_URL`` exercises
the Mneme-only subset. See ``eval/.env.e2e.example`` for env layout.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import pytest


@asynccontextmanager
async def mcp_session(url: str, secret: str = "") -> AsyncIterator[Any]:
    """Open an MCP SSE session against ``{url}/sse`` and yield a ready session."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    headers = {"Authorization": f"Bearer {secret}"} if secret else None
    async with sse_client(f"{url}/sse", headers=headers) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()
            yield session


def mcp_call_text(result: Any) -> str:
    """Flatten an MCP CallToolResult into a single text blob for assertions."""
    parts: list[str] = []
    for item in getattr(result, "content", []) or []:
        text = getattr(item, "text", None)
        if text is not None:
            parts.append(text)
    return "\n".join(parts)

pytestmark = pytest.mark.integration


# ── Per-service smoke tests ───────────────────────────────────────────────────

async def test_mneme_store_and_retrieve(
    mneme_url: str, mneme_secret: str, mneme_cleanup: list[str]
) -> None:
    marker = f"sky-{uuid.uuid4().hex[:8]}"
    async with mcp_session(mneme_url, mneme_secret) as session:
        stored = await session.call_tool(
            "store_memory",
            {
                "content": f"E2E memory {marker}: the sky is blue",
                "memory_type": "semantic",
                "confidence": 0.9,
                "tags": ["e2e", marker],
            },
        )
        assert stored.isError is False, mcp_call_text(stored)
        mneme_cleanup.append(json.loads(mcp_call_text(stored))["memory_id"])

        retrieved = await session.call_tool(
            "retrieve_memory",
            {"query": f"sky colour {marker}", "k": 3},
        )
        body = mcp_call_text(retrieved).lower()
        assert "blue" in body, body


async def test_telos_register_goal(telos_url: str, telos_secret: str) -> None:
    contract = {
        "description": f"E2E smoke goal {uuid.uuid4().hex[:8]}",
        "preconditions": [],
        "postconditions": [{"description": "smoke test passed"}],
    }
    async with mcp_session(telos_url, telos_secret) as session:
        result = await session.call_tool(
            "register_goal", {"contract_json": json.dumps(contract)}
        )
        assert result.isError is False, mcp_call_text(result)
        payload = json.loads(mcp_call_text(result))
        assert payload.get("goal_id")
        assert payload.get("active") is True


async def test_praxis_decompose_and_commit(praxis_url: str, praxis_secret: str) -> None:
    async with mcp_session(praxis_url, praxis_secret) as session:
        plan_result = await session.call_tool(
            "decompose_goal", {"goal": "e2e: boil water"}
        )
        assert plan_result.isError is False, mcp_call_text(plan_result)
        plan = json.loads(mcp_call_text(plan_result))
        plan_id = plan.get("plan_id") or plan.get("id")
        assert plan_id, plan

        step = await session.call_tool(
            "get_next_step", {"plan_id": plan_id}
        )
        assert step.isError is False, mcp_call_text(step)
        step_data = json.loads(mcp_call_text(step))
        step_id = step_data.get("step_id") or step_data.get("id")
        if step_id is None:
            pytest.skip(f"Praxis returned no next step: {step_data}")

        commit = await session.call_tool(
            "commit_step",
            {
                "plan_id": plan_id,
                "step_id": step_id,
                "outcome": "kettle on",
                "success": True,
            },
        )
        assert commit.isError is False, mcp_call_text(commit)


# ── Full Durchstich chain ─────────────────────────────────────────────────────

async def test_durchstich_telos_praxis_mneme(
    telos_url: str,
    telos_secret: str,
    praxis_url: str,
    praxis_secret: str,
    mneme_url: str,
    mneme_secret: str,
    mneme_cleanup: list[str],
) -> None:
    """Register a goal, plan against it, record the outcome in memory.

    Asserts every hop succeeds and that the goal description is retrievable
    from Mneme afterwards — proving cross-service wiring end to end.
    """
    marker = uuid.uuid4().hex[:8]
    description = f"Durchstich {marker}: verify cross-service chain"
    contract = {
        "description": description,
        "preconditions": [],
        "postconditions": [{"description": "chain completed"}],
    }

    # 1. Telos — register contract
    async with mcp_session(telos_url, telos_secret) as telos:
        reg = await telos.call_tool(
            "register_goal", {"contract_json": json.dumps(contract)}
        )
        assert reg.isError is False, mcp_call_text(reg)
        goal = json.loads(mcp_call_text(reg))
        goal_id = goal["goal_id"]

    # 2. Praxis — decompose and commit first step
    async with mcp_session(praxis_url, praxis_secret) as praxis:
        plan_resp = await praxis.call_tool(
            "decompose_goal", {"goal": description}
        )
        assert plan_resp.isError is False, mcp_call_text(plan_resp)
        plan = json.loads(mcp_call_text(plan_resp))
        plan_id = plan.get("plan_id") or plan.get("id")
        assert plan_id, plan

        next_step = await praxis.call_tool(
            "get_next_step", {"plan_id": plan_id}
        )
        step = json.loads(mcp_call_text(next_step))
        step_id = step.get("step_id") or step.get("id")
        if step_id is not None:
            commit = await praxis.call_tool(
                "commit_step",
                {
                    "plan_id": plan_id,
                    "step_id": step_id,
                    "outcome": f"chain-{marker} step 1 done",
                    "success": True,
                },
            )
            assert commit.isError is False, mcp_call_text(commit)

    # 3. Mneme — persist and retrieve a summary linked to the goal
    async with mcp_session(mneme_url, mneme_secret) as mneme:
        store = await mneme.call_tool(
            "store_memory",
            {
                "content": (
                    f"Durchstich {marker}: goal={goal_id} plan={plan_id} "
                    f"description={description!r}"
                ),
                "memory_type": "episodic",
                "confidence": 0.95,
                "tags": ["e2e", "durchstich", marker],
                "source": f"telos:{goal_id}",
            },
        )
        assert store.isError is False, mcp_call_text(store)
        mneme_cleanup.append(json.loads(mcp_call_text(store))["memory_id"])

        retrieved = await mneme.call_tool(
            "retrieve_memory",
            {"query": f"Durchstich {marker}", "k": 3},
        )
        body = mcp_call_text(retrieved)
        assert marker in body, body
        assert goal_id in body, body


# ── Empiria ───────────────────────────────────────────────────────────────────

async def test_empiria_record_experience(
    empiria_url: str, empiria_secret: str
) -> None:
    marker = uuid.uuid4().hex[:8]
    async with mcp_session(empiria_url, empiria_secret) as session:
        result = await session.call_tool(
            "record_experience",
            {
                "context": "e2e test context",
                "action_taken": "call record_experience",
                "outcome": "lesson recorded",
                "success": True,
                "lesson_text": f"E2E {marker}: harness works",
                "confidence": 0.7,
                "domain": "e2e",
            },
        )
        assert result.isError is False, mcp_call_text(result)
        body = json.loads(mcp_call_text(result))
        assert body.get("lesson_text", "").startswith("E2E"), body
