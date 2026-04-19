import sqlite3
from datetime import datetime
from typing import Optional

import networkx as nx
from noesis_schemas import Plan, PlanStep, StepStatus

# Scoring weights
_W_RISK = 0.6
_W_TOOL = 0.4
_FAIL_PENALTY = 0.3


def _score(
    risk_score: float,
    tool_call: Optional[str],
    previously_failed: bool = False,
) -> float:
    base = (1.0 - risk_score) * _W_RISK + (_W_TOOL if tool_call else _W_TOOL * 0.5)
    return max(0.0, base - (_FAIL_PENALTY if previously_failed else 0.0))


class PraxisCore:
    """
    Hierarchical planner with Tree-of-Thoughts search.

    Plans are stored as NetworkX DiGraphs where each root node is a plan_id and
    child nodes are PlanStep IDs. Multiple children of the same parent represent
    alternative branches (competing strategies). Beam search selects the highest-
    scoring path; backtrack returns siblings of failed steps.
    """

    def __init__(self, db_path: str = "praxis.db") -> None:
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._setup_schema()
        self._trees: dict[str, nx.DiGraph] = {}
        self._load_trees()

    def _setup_schema(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS plans (
                plan_id        TEXT PRIMARY KEY,
                goal           TEXT NOT NULL,
                depth          INTEGER NOT NULL DEFAULT 0,
                parent_plan_id TEXT,
                created_at     TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS steps (
                step_id        TEXT PRIMARY KEY,
                plan_id        TEXT NOT NULL REFERENCES plans(plan_id),
                parent_step_id TEXT,
                description    TEXT NOT NULL,
                tool_call      TEXT,
                status         TEXT NOT NULL DEFAULT 'pending',
                outcome        TEXT,
                risk_score     REAL NOT NULL DEFAULT 0.0,
                score          REAL NOT NULL DEFAULT 0.5,
                executed_at    TEXT
            );
        """)
        self._conn.commit()

    def _load_trees(self) -> None:
        """Reconstruct in-memory graphs from SQLite on startup."""
        cursor = self._conn.execute("SELECT plan_id, goal FROM plans")
        for plan_id, goal in cursor.fetchall():
            g: nx.DiGraph = nx.DiGraph()
            g.add_node(plan_id, type="root", goal=goal)
            rows = self._conn.execute(
                "SELECT step_id, parent_step_id, description, tool_call, "
                "status, outcome, risk_score, score FROM steps WHERE plan_id=?",
                (plan_id,),
            ).fetchall()
            for row in rows:
                (
                    step_id, parent_step_id, desc, tool_call,
                    status, outcome, risk_score, score,
                ) = row
                g.add_node(
                    step_id,
                    description=desc,
                    tool_call=tool_call,
                    status=StepStatus(status),
                    outcome=outcome,
                    risk_score=risk_score,
                    score=score,
                )
                g.add_edge(parent_step_id or plan_id, step_id)
            self._trees[plan_id] = g

    def _node_to_step(self, g: nx.DiGraph, node_id: str) -> PlanStep:
        d = g.nodes[node_id]
        return PlanStep(
            step_id=node_id,
            description=d["description"],
            tool_call=d.get("tool_call"),
            status=d.get("status", StepStatus.PENDING),
            outcome=d.get("outcome"),
            risk_score=d.get("risk_score", 0.0),
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def decompose(
        self, goal: str, depth: int = 0, parent_plan_id: Optional[str] = None
    ) -> Plan:
        plan = Plan(goal=goal, depth=depth, parent_plan_id=parent_plan_id)
        self._conn.execute(
            "INSERT INTO plans VALUES (?, ?, ?, ?, ?)",
            (plan.plan_id, goal, depth, parent_plan_id, plan.created_at.isoformat()),
        )
        self._conn.commit()
        g: nx.DiGraph = nx.DiGraph()
        g.add_node(plan.plan_id, type="root", goal=goal)
        self._trees[plan.plan_id] = g
        return plan

    def add_step(
        self,
        plan_id: str,
        description: str,
        tool_call: Optional[str] = None,
        risk_score: float = 0.0,
        parent_step_id: Optional[str] = None,
    ) -> PlanStep:
        """
        Add a candidate step to the plan tree.

        parent_step_id=None → child of root (first step or alternative first step).
        parent_step_id=<id>  → child of that step (sequential or alternative branch).

        Multiple steps with the same parent are competing alternatives; beam search
        picks the best one.
        """
        g = self._trees[plan_id]
        parent = parent_step_id or plan_id
        if parent not in g:
            raise KeyError(f"parent_step_id {parent!r} not found in plan {plan_id!r}")

        node_score = _score(risk_score, tool_call)
        step = PlanStep(
            description=description,
            tool_call=tool_call,
            risk_score=risk_score,
        )

        self._conn.execute(
            "INSERT INTO steps VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (step.step_id, plan_id, parent_step_id, description, tool_call,
             StepStatus.PENDING.value, None, risk_score, node_score, None),
        )
        self._conn.commit()

        g.add_node(
            step.step_id,
            description=description,
            tool_call=tool_call,
            status=StepStatus.PENDING,
            outcome=None,
            risk_score=risk_score,
            score=node_score,
        )
        g.add_edge(parent, step.step_id)
        return step

    def commit_step(
        self, plan_id: str, step_id: str, outcome: str, success: bool
    ) -> PlanStep:
        g = self._trees[plan_id]
        if step_id not in g:
            raise KeyError(step_id)

        status = StepStatus.COMPLETED if success else StepStatus.FAILED
        now = datetime.utcnow().isoformat()

        if not success:
            # Penalise score so beam search avoids this branch
            old_score = g.nodes[step_id]["score"]
            g.nodes[step_id]["score"] = max(0.0, old_score - _FAIL_PENALTY)
            self._conn.execute(
                "UPDATE steps SET score=? WHERE step_id=?",
                (g.nodes[step_id]["score"], step_id),
            )

        g.nodes[step_id]["status"] = status
        g.nodes[step_id]["outcome"] = outcome
        self._conn.execute(
            "UPDATE steps SET status=?, outcome=?, executed_at=? WHERE step_id=?",
            (status.value, outcome, now, step_id),
        )
        self._conn.commit()
        return self._node_to_step(g, step_id)

    def backtrack(self, plan_id: str) -> list[PlanStep]:
        """
        After a step failure, return sibling steps (same parent, still PENDING)
        as alternative candidates. Resets FAILED steps to PENDING so they are
        eligible for retry with different inputs.
        """
        g = self._trees[plan_id]
        failed = [
            n for n, d in g.nodes(data=True)
            if d.get("status") == StepStatus.FAILED
        ]
        alternatives: list[str] = []

        for node in failed:
            # Collect pending siblings
            for parent in g.predecessors(node):
                siblings = [
                    s for s in g.successors(parent)
                    if s != node and g.nodes[s].get("status") == StepStatus.PENDING
                ]
                alternatives.extend(siblings)

            # Reset failed step so beam search can reconsider it
            g.nodes[node]["status"] = StepStatus.PENDING
            g.nodes[node]["outcome"] = None
            self._conn.execute(
                "UPDATE steps SET status='pending', outcome=NULL WHERE step_id=?",
                (node,),
            )

        self._conn.commit()
        return [self._node_to_step(g, s) for s in dict.fromkeys(alternatives)]

    def best_path(self, plan_id: str, k: int = 1) -> list[list[PlanStep]]:
        """
        Beam search through the plan tree; returns top-k complete paths ordered
        by cumulative score (highest first).

        A "complete path" is a root-to-leaf walk. If the tree has only one level
        (all steps are children of root), each step is its own candidate path and
        the caller receives [[best_step]] as the top-1 result.
        """
        g = self._trees[plan_id]

        # beam entry: (node_ids_from_root, cumulative_score)
        beam: list[tuple[list[str], float]] = [([plan_id], 0.0)]
        complete: list[tuple[list[str], float]] = []

        while beam:
            next_beam: list[tuple[list[str], float]] = []
            for path, cum in beam:
                children = [c for c in g.successors(path[-1])]
                if not children:
                    # leaf
                    step_ids = path[1:]  # drop root
                    if step_ids:
                        complete.append((step_ids, cum))
                    continue
                # Sort children by score descending, keep top-k
                ranked = sorted(
                    children,
                    key=lambda n: g.nodes[n].get("score", 0.0),
                    reverse=True,
                )[:k]
                for child in ranked:
                    child_score = g.nodes[child].get("score", 0.0)
                    next_beam.append((path + [child], cum + child_score))

            next_beam.sort(key=lambda x: x[1], reverse=True)
            beam = next_beam[:k]

        complete.sort(key=lambda x: x[1], reverse=True)
        return [
            [self._node_to_step(g, sid) for sid in ids]
            for ids, _ in complete[:k]
        ]

    def get_next_step(self, plan_id: str) -> Optional[PlanStep]:
        """Returns the first PENDING step on the current best path."""
        paths = self.best_path(plan_id, k=1)
        if not paths:
            return None
        for step in paths[0]:
            if step.status == StepStatus.PENDING:
                return step
        return None  # all steps on best path are completed

    def verify_plan(self, plan_id: str) -> tuple[bool, str]:
        """
        Basic safety verification (stub for Logos GoalContract integration).
        Production: POST to Logos /tools/verify_argument with the plan as premise.
        """
        g = self._trees[plan_id]
        step_nodes = [
            (d["risk_score"], d["description"])
            for n, d in g.nodes(data=True)
            if n != plan_id
        ]
        if not step_nodes:
            return False, "Plan has no steps"
        high_risk = [desc for risk, desc in step_nodes if risk >= 0.8]
        if high_risk:
            return False, f"High-risk steps: {high_risk}"
        return True, "Plan passes basic safety check"

    def get_plan(self, plan_id: str) -> Plan:
        row = self._conn.execute(
            "SELECT goal, depth, parent_plan_id, created_at FROM plans WHERE plan_id=?",
            (plan_id,),
        ).fetchone()
        if not row:
            raise KeyError(plan_id)
        goal, depth, parent_plan_id, created_at = row
        paths = self.best_path(plan_id, k=1)
        return Plan(
            plan_id=plan_id,
            goal=goal,
            depth=depth,
            parent_plan_id=parent_plan_id,
            steps=paths[0] if paths else [],
            created_at=datetime.fromisoformat(created_at),
        )
