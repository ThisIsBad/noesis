"""Phase 1 Durchstich — end-to-end integration against deployed services.

Every test parses MCP tool responses through the canonical ``noesis_schemas``
Pydantic models, so schema drift between a service and its shared contract
fails CI immediately. Tests skip cleanly when their required env vars are
unset — see ``eval/.env.e2e.example`` for the layout.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Any, TypeVar

import httpx
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

from tests._retry_helpers import retry_on_transient_mcp_error

# Railway edge returns 502/503/504 while a service container is cold-starting
# (first request after an idle spin-down). The MCP SDK surfaces that as an
# httpx.HTTPStatusError from the SSE handshake — before any RPC runs — so a
# one-shot retry on the handshake is enough. Don't retry inside the yield:
# those failures are test logic, not cold-start.
#
# ``sse_client`` runs the handshake inside an anyio TaskGroup, so the real
# failure arrives wrapped in a BaseExceptionGroup. We walk the group tree
# to find a retryable leaf — otherwise the previous top-level isinstance
# check never matches and every cold-start kills the whole CI run.
_RETRY_STATUS = {502, 503, 504}
_RETRY_EXCEPTIONS: tuple[type[BaseException], ...] = (
    httpx.ConnectError,
    httpx.ConnectTimeout,
    httpx.ReadError,
    httpx.ReadTimeout,
    httpx.RemoteProtocolError,
)


def _is_retryable_leaf(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in _RETRY_STATUS
    return isinstance(exc, _RETRY_EXCEPTIONS)


def _is_retryable(exc: BaseException) -> bool:
    """True if ``exc`` (or any nested exception in an ExceptionGroup) is
    a transient Railway/network failure worth retrying."""
    if _is_retryable_leaf(exc):
        return True
    if isinstance(exc, BaseExceptionGroup):
        return any(_is_retryable(e) for e in exc.exceptions)
    return False


@asynccontextmanager
async def mcp_session(url: str, secret: str = "") -> AsyncIterator[Any]:
    """Open an MCP SSE session against ``{url}/sse`` and yield a ready session."""
    from mcp import ClientSession
    from mcp.client.sse import sse_client

    headers = {"Authorization": f"Bearer {secret}"} if secret else None
    backoff = 2.0
    async with AsyncExitStack() as outer:
        session: Any = None
        for attempt in range(3):
            inner = AsyncExitStack()
            try:
                read, write = await inner.enter_async_context(
                    sse_client(f"{url}/sse", headers=headers)
                )
                session = await inner.enter_async_context(ClientSession(read, write))
                await session.initialize()
            except BaseException as exc:
                await inner.aclose()
                if attempt < 2 and _is_retryable(exc):
                    await asyncio.sleep(backoff)
                    backoff *= 2
                    continue
                raise
            outer.push_async_callback(inner.aclose)
            break
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


async def test_praxis_backtrack_surfaces_pending_sibling_after_failure(
    praxis_url: str, praxis_secret: str
) -> None:
    """Stage 3 replanning probe: after a step fails, ``backtrack`` must
    surface a pending sibling as an alternative candidate.

    This is the minimum-viable wiring test for the "Replanning after
    failure ≥ 50%" acceptance criterion in the ROADMAP — it doesn't score
    the policy, it just proves the end-to-end mechanism is connected
    through the MCP surface on the deployed service.
    """
    async with mcp_session(praxis_url, praxis_secret) as session:
        plan = parse_model(
            await session.call_tool(
                "decompose_goal", {"goal": "e2e: backtrack probe"}
            ),
            Plan,
        )

        # Two alternative first steps, both children of the plan root
        # (parent_step_id omitted ⇒ root child per praxis.core contract).
        risky = parse_model(
            await session.call_tool(
                "evaluate_step",
                {
                    "plan_id": plan.plan_id,
                    "description": "risky first approach",
                    "risk_score": 0.9,
                },
            ),
            PlanStep,
        )
        safe = parse_model(
            await session.call_tool(
                "evaluate_step",
                {
                    "plan_id": plan.plan_id,
                    "description": "safe fallback approach",
                    "risk_score": 0.1,
                },
            ),
            PlanStep,
        )
        assert risky.step_id != safe.step_id

        # Fail the risky branch.
        failed = parse_model(
            await session.call_tool(
                "commit_step",
                {
                    "plan_id": plan.plan_id,
                    "step_id": risky.step_id,
                    "outcome": "timed out",
                    "success": False,
                },
            ),
            PlanStep,
        )
        assert failed.status.value == "failed"

        # backtrack must return the pending sibling as an alternative.
        alts_body = parse_json(
            await session.call_tool("backtrack", {"plan_id": plan.plan_id})
        )
        alt_ids = {a["step_id"] for a in alts_body.get("alternatives", [])}
        assert safe.step_id in alt_ids, (
            f"expected pending sibling {safe.step_id} in backtrack alternatives, "
            f"got {alts_body}"
        )


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
        assert body.get("satisfiable") is True, body
        assert str(body.get("model", {}).get("x")) == "4", body


async def test_logos_certify_claim(logos_url: str, logos_secret: str) -> None:
    """Certify a trivially provable claim and validate the certificate shape."""
    async with mcp_session(logos_url, logos_secret) as session:
        raw = parse_json(
            await session.call_tool(
                "certify_claim",
                {"argument": "P -> Q, P |- Q"},
            )
        )
        # The serialised cert is returned as a JSON string in certificate_json.
        cert = ProofCertificate.model_validate(json.loads(raw["certificate_json"]))
        assert cert.verified is True
        assert cert.method == "z3_propositional"


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
        assert report.sample_size >= 1, report


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

@retry_on_transient_mcp_error()
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

@retry_on_transient_mcp_error()
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


@retry_on_transient_mcp_error()
async def test_durchstich_kosmos_counterfactual_consistency(
    kosmos_url: str, kosmos_secret: str
) -> None:
    """Deep probe of the Kosmos causal surface on a three-hop chain.

    Builds ``A →0.8→ B →0.9→ C →0.7→ D`` then asks every Kosmos tool
    about different slices of the graph and pins that their answers stay
    consistent with each other:

    1. ``query_causes`` surfaces *only* the direct parent — not
       transitive ancestors.
    2. ``counterfactual`` returns the product of edge weights along the
       path (within float tolerance) for every multi-hop query.
    3. ``compute_intervention`` enumerates every downstream node with
       the same multiplicative weights ``counterfactual`` would give.
    4. An unrelated variable returns ``strength=None`` and is absent
       from the intervention set.

    If Kosmos swaps the lexical adjacency store for pgmpy (per the core
    module's TODO) the numbers will change, but the *internal*
    consistency properties must still hold — that's what this probe
    pins.  Catches silent surface drift where one tool returns stale or
    transitive-inflated results while the others stay correct.
    """
    marker = uuid.uuid4().hex[:8]
    a = f"kk_a_{marker}"
    b = f"kk_b_{marker}"
    c = f"kk_c_{marker}"
    d = f"kk_d_{marker}"
    unrelated = f"kk_x_{marker}"
    ab, bc, cd = 0.8, 0.9, 0.7

    async with mcp_session(kosmos_url, kosmos_secret) as session:
        for cause, effect, strength in [(a, b, ab), (b, c, bc), (c, d, cd)]:
            body = parse_json(
                await session.call_tool(
                    "add_causal_edge",
                    {"cause": cause, "effect": effect, "strength": strength},
                )
            )
            assert "added" in body, body

        # (1) Direct parents only — no transitive ancestors.
        d_causes = parse_json(
            await session.call_tool("query_causes", {"effect": d})
        ).get("causes", [])
        assert d_causes == [c], (
            f"query_causes(D) must return only the direct parent C; "
            f"got {d_causes!r} — transitive inflation would break the "
            f"Do-calculus contract."
        )
        c_causes = parse_json(
            await session.call_tool("query_causes", {"effect": c})
        ).get("causes", [])
        assert c_causes == [b], c_causes

        # (2) Multi-hop counterfactual == product of edge weights.
        ad_strength = parse_json(
            await session.call_tool(
                "counterfactual", {"cause": a, "effect": d}
            )
        ).get("strength")
        assert ad_strength == pytest.approx(ab * bc * cd, rel=1e-6), (
            f"counterfactual(A, D) expected {ab * bc * cd}, got {ad_strength}"
        )
        ac_strength = parse_json(
            await session.call_tool(
                "counterfactual", {"cause": a, "effect": c}
            )
        ).get("strength")
        assert ac_strength == pytest.approx(ab * bc, rel=1e-6)
        bd_strength = parse_json(
            await session.call_tool(
                "counterfactual", {"cause": b, "effect": d}
            )
        ).get("strength")
        assert bd_strength == pytest.approx(bc * cd, rel=1e-6)

        # (3) Intervention agrees with counterfactual on every reachable node.
        intervention = parse_json(
            await session.call_tool(
                "compute_intervention", {"variable": a, "value": True}
            )
        )
        assert intervention.get(b) == pytest.approx(ab, rel=1e-6)
        assert intervention.get(c) == pytest.approx(ab * bc, rel=1e-6)
        assert intervention.get(d) == pytest.approx(ab * bc * cd, rel=1e-6)
        assert unrelated not in intervention

        # (4) No path ⇒ strength=None and unreachable from intervention.
        raw_unrelated = parse_json(
            await session.call_tool(
                "counterfactual", {"cause": unrelated, "effect": d}
            )
        )
        assert raw_unrelated.get("strength") is None, raw_unrelated


# ── Full Durchstich chain ─────────────────────────────────────────────────────

@retry_on_transient_mcp_error()
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


@retry_on_transient_mcp_error()
async def test_durchstich_five_hop_telos_praxis_logos_mneme_empiria(
    telos_url: str,
    telos_secret: str,
    praxis_url: str,
    praxis_secret: str,
    logos_url: str,
    logos_secret: str,
    mneme_url: str,
    mneme_secret: str,
    empiria_url: str,
    empiria_secret: str,
    mneme_cleanup: list[str],
) -> None:
    """Full five-hop Durchstich: Goal → Plan → Verify → Store → Lesson.

    Extends the three-hop chain with Logos certification and Empiria lesson
    recording, so the whole "think → prove → remember → learn" loop is
    exercised. Each hop feeds artifacts from the previous one:

    1. Telos registers the goal (``goal_id``).
    2. Praxis decomposes it into a plan (``plan_id``) and commits one step.
    3. Logos certifies a trivially provable claim and hands back a
       serialised ``ProofCertificate``.
    4. Mneme stores the memory *with* the certificate attached, so the
       returned record's ``certificate`` field must round-trip as a
       verified ``ProofCertificate``.
    5. Empiria records a lesson whose ``context`` mentions the goal and
       whose ``outcome`` references the stored memory_id.

    The ``marker`` token threads through every service so the final
    retrieval asserts that the whole chain wired up end to end.
    """
    marker = uuid.uuid4().hex[:8]
    description = f"Durchstich5 {marker}: full loop through all five services"
    contract = GoalContract(
        description=description,
        postconditions=[{"description": "five-hop chain completed"}],
    )

    # Hop 1: Telos — register goal.
    async with mcp_session(telos_url, telos_secret) as telos:
        goal = parse_model(
            await telos.call_tool(
                "register_goal", {"contract_json": contract.model_dump_json()}
            ),
            GoalContract,
        )

    # Hop 2: Praxis — decompose and commit one step.
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
                        "outcome": f"five-hop-{marker} step 1 done",
                        "success": True,
                    },
                ),
                PlanStep,
            )

    # Hop 3: Logos — certify a trivially provable claim.
    # ``P -> Q, P |- Q`` is modus ponens — Logos's z3_propositional method
    # verifies it in constant time, giving us a real verified certificate
    # to thread through the chain rather than a fabricated one.
    async with mcp_session(logos_url, logos_secret) as logos:
        raw_cert = parse_json(
            await logos.call_tool(
                "certify_claim", {"argument": "P -> Q, P |- Q"}
            )
        )
        assert raw_cert.get("verified") is True, raw_cert
        certificate_json = raw_cert["certificate_json"]
        cert = ProofCertificate.model_validate(json.loads(certificate_json))
        assert cert.verified is True
        assert cert.method == "z3_propositional"

    # Hop 4: Mneme — store memory with the Logos certificate attached.
    async with mcp_session(mneme_url, mneme_secret) as mneme:
        stored = parse_model(
            await mneme.call_tool(
                "store_memory",
                {
                    "content": (
                        f"Durchstich5 {marker}: goal={goal.goal_id} "
                        f"plan={plan.plan_id} certified_by=logos"
                    ),
                    "memory_type": "episodic",
                    "confidence": 0.95,
                    "tags": ["e2e", "durchstich5", marker],
                    "source": f"telos:{goal.goal_id}",
                    "certificate_json": certificate_json,
                },
            ),
            Memory,
        )
        mneme_cleanup.append(stored.memory_id)
        # The certificate must survive the round-trip into Mneme so
        # downstream consumers can trust the memory's provenance.
        assert stored.certificate is not None
        assert stored.certificate.verified is True
        assert stored.certificate.method == "z3_propositional"

    # Hop 5: Empiria — distill a lesson from the whole chain.
    context = f"Durchstich5 {marker} context: goal={goal.goal_id}"
    lesson_text = (
        f"Durchstich5 {marker}: five-hop loop completes when a certified "
        f"memory is reachable from the originating goal."
    )
    async with mcp_session(empiria_url, empiria_secret) as empiria:
        lesson = parse_model(
            await empiria.call_tool(
                "record_experience",
                {
                    "context": context,
                    "action_taken": (
                        f"plan={plan.plan_id} cert={cert.claim_type} "
                        f"stored={stored.memory_id}"
                    ),
                    "outcome": f"memory {stored.memory_id} retained",
                    "success": True,
                    "lesson_text": lesson_text,
                    "confidence": 0.9,
                    "domain": "durchstich5",
                },
            ),
            Lesson,
        )
        assert lesson.success is True
        assert lesson.lesson_text == lesson_text

        # Closing retrieval asserts the marker threaded all the way
        # through — if any hop dropped context, this would miss.
        found = parse_model_list(
            await empiria.call_tool(
                "retrieve_lessons",
                {"context": context, "k": 3, "domain": "durchstich5"},
            ),
            Lesson,
        )
        assert any(marker in lsn.lesson_text for lsn in found), found
