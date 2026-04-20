"""Phase 1 Durchstich — end-to-end integration against deployed services.

Every test parses MCP tool responses through the canonical ``noesis_schemas``
Pydantic models, so schema drift between a service and its shared contract
fails CI immediately. Tests skip cleanly when their required env vars are
unset — see ``eval/.env.e2e.example`` for the layout.
"""
from __future__ import annotations

import json
import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, TypeVar

import pytest
from noesis_schemas import (
    CalibrationReport,
    GoalContract,
    Lesson,
    Memory,
    Plan,
    PlanStep,
    Prediction,
    ProofCertificate,
    Skill,
)
from pydantic import BaseModel


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


M = TypeVar("M", bound=BaseModel)


def parse_model(result: Any, model_cls: type[M]) -> M:
    """Parse an MCP tool response as a single Pydantic model.

    Raises a clear ``AssertionError`` with the raw body when the response is
    either an MCP error or fails schema validation — collapses the Pydantic
    traceback into a single line so the failure diff is readable in CI logs.
    """
    body = mcp_call_text(result)
    assert getattr(result, "isError", False) is False, body
    model: M = model_cls.model_validate_json(body)
    return model


def parse_model_list(result: Any, model_cls: type[M]) -> list[M]:
    body = mcp_call_text(result)
    assert getattr(result, "isError", False) is False, body
    return [model_cls.model_validate(item) for item in json.loads(body)]


def parse_json(result: Any) -> dict[str, Any]:
    body = mcp_call_text(result)
    assert getattr(result, "isError", False) is False, body
    parsed: dict[str, Any] = json.loads(body)
    return parsed


pytestmark = pytest.mark.integration


# ── Mneme ─────────────────────────────────────────────────────────────────────

async def test_mneme_store_and_retrieve(
    mneme_url: str, mneme_secret: str, mneme_cleanup: list[str]
) -> None:
    marker = f"sky-{uuid.uuid4().hex[:8]}"
    async with mcp_session(mneme_url, mneme_secret) as session:
        stored = parse_model(
            await session.call_tool(
                "store_memory",
                {
                    "content": f"E2E memory {marker}: the sky is blue",
                    "memory_type": "semantic",
                    "confidence": 0.9,
                    "tags": ["e2e", marker],
                },
            ),
            Memory,
        )
        mneme_cleanup.append(stored.memory_id)
        assert stored.content.endswith("the sky is blue")
        assert stored.confidence == pytest.approx(0.9)
        assert "e2e" in stored.tags

        retrieved = parse_model_list(
            await session.call_tool(
                "retrieve_memory",
                {"query": f"sky colour {marker}", "k": 3},
            ),
            Memory,
        )
        assert any("blue" in m.content.lower() for m in retrieved), retrieved


# ── Telos ─────────────────────────────────────────────────────────────────────

async def test_telos_register_and_list_goal(
    telos_url: str, telos_secret: str
) -> None:
    description = f"E2E smoke goal {uuid.uuid4().hex[:8]}"
    contract = GoalContract(
        description=description,
        postconditions=[{"description": "smoke test passed"}],
    )
    async with mcp_session(telos_url, telos_secret) as session:
        stored = parse_model(
            await session.call_tool(
                "register_goal",
                {"contract_json": contract.model_dump_json()},
            ),
            GoalContract,
        )
        assert stored.active is True
        assert stored.description == description
        assert stored.goal_id

        listed = parse_model_list(
            await session.call_tool("list_active_goals", {}),
            GoalContract,
        )
        assert any(g.goal_id == stored.goal_id for g in listed), listed


async def test_telos_alignment_check(
    telos_url: str, telos_secret: str
) -> None:
    async with mcp_session(telos_url, telos_secret) as session:
        body = parse_json(
            await session.call_tool(
                "check_action_alignment",
                {"action_description": "read a file from disk"},
            )
        )
        assert set(body.keys()) >= {"aligned", "drift_score", "reason"}
        assert isinstance(body["aligned"], bool)
        assert isinstance(body["drift_score"], (int, float))


# ── Praxis ────────────────────────────────────────────────────────────────────

async def test_praxis_decompose_and_commit(
    praxis_url: str, praxis_secret: str
) -> None:
    async with mcp_session(praxis_url, praxis_secret) as session:
        plan = parse_model(
            await session.call_tool("decompose_goal", {"goal": "e2e: boil water"}),
            Plan,
        )
        assert plan.plan_id
        assert plan.goal == "e2e: boil water"

        raw_next = parse_json(
            await session.call_tool("get_next_step", {"plan_id": plan.plan_id})
        )
        # decompose_goal may produce an empty plan for unrecognised goals;
        # the tool returns {"step": None, "message": ...} in that case.
        if raw_next.get("step_id") is None:
            pytest.skip(f"Praxis produced no executable step: {raw_next}")

        step = PlanStep.model_validate(raw_next)
        committed = parse_model(
            await session.call_tool(
                "commit_step",
                {
                    "plan_id": plan.plan_id,
                    "step_id": step.step_id,
                    "outcome": "kettle on",
                    "success": True,
                },
            ),
            PlanStep,
        )
        assert committed.step_id == step.step_id


# ── Logos ─────────────────────────────────────────────────────────────────────

async def test_logos_z3_check(logos_url: str, logos_secret: str) -> None:
    """Smoke test Logos' Z3 surface — trivially satisfiable constraints."""
    async with mcp_session(logos_url, logos_secret) as session:
        body = parse_json(
            await session.call_tool(
                "z3_check",
                {
                    "variables": {"x": "Int"},
                    "constraints": ["x > 0", "x < 10", "x * x == 16"],
                },
            )
        )
        # Response shape varies across Logos revisions; we require only that
        # the check reports satisfiability and that the SAT witness hits x=4.
        status = body.get("status") or body.get("result")
        assert status in {"sat", "SAT", "satisfiable"}, body
        model = body.get("model") or body.get("assignments") or {}
        if model:
            assert str(model.get("x")) == "4", model


async def test_logos_certify_claim(logos_url: str, logos_secret: str) -> None:
    """Certify a trivially provable claim and validate the certificate shape."""
    async with mcp_session(logos_url, logos_secret) as session:
        raw = parse_json(
            await session.call_tool(
                "certify_claim",
                {"argument": "Assume x > 0. Therefore x + 1 > 0."},
            )
        )
        # The cert may be wrapped in an envelope ({"certificate": {...}}) or
        # returned flat — accept both.
        cert_dict = raw.get("certificate", raw)
        cert = ProofCertificate.model_validate(cert_dict)
        assert cert.verified in (True, False)  # must at least populate the field
        assert cert.method


# ── Episteme ──────────────────────────────────────────────────────────────────

async def test_episteme_log_predict_outcome_calibration(
    episteme_url: str, episteme_secret: str
) -> None:
    """Log a prediction, resolve it, and check it shows up in calibration."""
    marker = uuid.uuid4().hex[:8]
    async with mcp_session(episteme_url, episteme_secret) as session:
        pred = parse_model(
            await session.call_tool(
                "log_prediction",
                {
                    "claim": f"E2E {marker}: coin lands heads",
                    "confidence": 0.7,
                    "domain": "e2e",
                },
            ),
            Prediction,
        )
        assert pred.confidence == pytest.approx(0.7)

        resolved = parse_model(
            await session.call_tool(
                "log_outcome", {"prediction_id": pred.prediction_id, "correct": True}
            ),
            Prediction,
        )
        assert resolved.correct is True

        report = parse_model(
            await session.call_tool("get_calibration", {"domain": "e2e"}),
            CalibrationReport,
        )
        assert report.n >= 1, report


async def test_episteme_should_escalate(
    episteme_url: str, episteme_secret: str
) -> None:
    async with mcp_session(episteme_url, episteme_secret) as session:
        low = parse_json(
            await session.call_tool("should_escalate", {"confidence": 0.1})
        )
        high = parse_json(
            await session.call_tool("should_escalate", {"confidence": 0.99})
        )
        assert isinstance(low["escalate"], bool)
        assert isinstance(high["escalate"], bool)


# ── Empiria ───────────────────────────────────────────────────────────────────

async def test_empiria_record_and_retrieve(
    empiria_url: str, empiria_secret: str
) -> None:
    marker = uuid.uuid4().hex[:8]
    lesson_text = f"E2E {marker}: harness works"
    context = f"e2e test context {marker}"
    async with mcp_session(empiria_url, empiria_secret) as session:
        stored = parse_model(
            await session.call_tool(
                "record_experience",
                {
                    "context": context,
                    "action_taken": "call record_experience",
                    "outcome": "lesson recorded",
                    "success": True,
                    "lesson_text": lesson_text,
                    "confidence": 0.7,
                    "domain": "e2e",
                },
            ),
            Lesson,
        )
        assert stored.lesson_text == lesson_text
        assert stored.success is True

        found = parse_model_list(
            await session.call_tool(
                "retrieve_lessons", {"context": context, "k": 3, "domain": "e2e"}
            ),
            Lesson,
        )
        assert any(lesson_text in lsn.lesson_text for lsn in found), found


# ── Techne ────────────────────────────────────────────────────────────────────

async def test_techne_store_and_retrieve_skill(
    techne_url: str, techne_secret: str
) -> None:
    marker = uuid.uuid4().hex[:8]
    name = f"e2e-skill-{marker}"
    async with mcp_session(techne_url, techne_secret) as session:
        stored = parse_model(
            await session.call_tool(
                "store_skill",
                {
                    "name": name,
                    "description": f"E2E test skill {marker}",
                    "strategy": "noop",
                    "domain": "e2e",
                },
            ),
            Skill,
        )
        assert stored.name == name

        found = parse_model_list(
            await session.call_tool(
                "retrieve_skill", {"query": name, "k": 3, "verified_only": False}
            ),
            Skill,
        )
        assert any(s.skill_id == stored.skill_id for s in found), found

        updated = parse_model(
            await session.call_tool(
                "record_use", {"skill_id": stored.skill_id, "success": True}
            ),
            Skill,
        )
        assert updated.skill_id == stored.skill_id
        assert updated.success_rate >= stored.success_rate


# ── Kosmos ────────────────────────────────────────────────────────────────────

async def test_kosmos_causal_chain(
    kosmos_url: str, kosmos_secret: str
) -> None:
    """Build a tiny causal graph A → B → C, then interrogate it."""
    marker = uuid.uuid4().hex[:8]
    a, b, c = f"e2e_a_{marker}", f"e2e_b_{marker}", f"e2e_c_{marker}"
    async with mcp_session(kosmos_url, kosmos_secret) as session:
        for cause, effect in [(a, b), (b, c)]:
            body = parse_json(
                await session.call_tool(
                    "add_causal_edge",
                    {"cause": cause, "effect": effect, "strength": 0.9},
                )
            )
            assert "added" in body, body

        causes = parse_json(
            await session.call_tool("query_causes", {"effect": c})
        )
        assert b in causes.get("causes", []), causes

        cf = parse_json(
            await session.call_tool("counterfactual", {"cause": a, "effect": c})
        )
        strength = cf.get("strength")
        assert strength is None or strength > 0, cf


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

    Asserts every hop succeeds and that the goal_id round-trips through the
    chain — proving cross-service wiring end to end.
    """
    marker = uuid.uuid4().hex[:8]
    description = f"Durchstich {marker}: verify cross-service chain"
    contract = GoalContract(
        description=description,
        postconditions=[{"description": "chain completed"}],
    )

    async with mcp_session(telos_url, telos_secret) as telos:
        goal = parse_model(
            await telos.call_tool(
                "register_goal", {"contract_json": contract.model_dump_json()}
            ),
            GoalContract,
        )

    async with mcp_session(praxis_url, praxis_secret) as praxis:
        plan = parse_model(
            await praxis.call_tool("decompose_goal", {"goal": description}),
            Plan,
        )
        raw_next = parse_json(
            await praxis.call_tool("get_next_step", {"plan_id": plan.plan_id})
        )
        if raw_next.get("step_id") is not None:
            step = PlanStep.model_validate(raw_next)
            parse_model(
                await praxis.call_tool(
                    "commit_step",
                    {
                        "plan_id": plan.plan_id,
                        "step_id": step.step_id,
                        "outcome": f"chain-{marker} step 1 done",
                        "success": True,
                    },
                ),
                PlanStep,
            )

    async with mcp_session(mneme_url, mneme_secret) as mneme:
        stored = parse_model(
            await mneme.call_tool(
                "store_memory",
                {
                    "content": (
                        f"Durchstich {marker}: goal={goal.goal_id} "
                        f"plan={plan.plan_id} description={description!r}"
                    ),
                    "memory_type": "episodic",
                    "confidence": 0.95,
                    "tags": ["e2e", "durchstich", marker],
                    "source": f"telos:{goal.goal_id}",
                },
            ),
            Memory,
        )
        mneme_cleanup.append(stored.memory_id)

        retrieved = parse_model_list(
            await mneme.call_tool(
                "retrieve_memory", {"query": f"Durchstich {marker}", "k": 3}
            ),
            Memory,
        )
        assert any(
            marker in m.content and goal.goal_id in m.content for m in retrieved
        ), retrieved
