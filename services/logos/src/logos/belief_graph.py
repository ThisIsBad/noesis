"""Causal and temporal belief graph for long-horizon reasoning."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Iterator, overload

from logos.z3_session import CheckResult
from logos.uncertainty import ConfidenceLevel, UncertaintyCalibrator


class BeliefEdgeType(Enum):
    """Typed causal edge labels for belief relations."""

    SUPPORTS = "supports"
    CONTRADICTS = "contradicts"
    DERIVED_FROM = "derived_from"
    OBSERVED_AT = "observed_at"


class ContradictionStatus(Enum):
    """Outcome of Z3-backed contradiction detection."""

    CONSISTENT = "consistent"
    CONTRADICTION = "contradiction"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class BeliefNode:
    """One belief node with temporal validity metadata."""

    belief_id: str
    statement: str
    valid_from: datetime
    valid_until: datetime | None = None
    ttl_seconds: int | None = None


@dataclass(frozen=True)
class BeliefEdge:
    """Directed relation between two belief nodes."""

    source_id: str
    target_id: str
    edge_type: BeliefEdgeType


@dataclass(frozen=True)
class ContradictionExplanation:
    """Explicit contradiction explanation as two support paths."""

    left_id: str
    right_id: str
    left_support_path: tuple[str, ...]
    right_support_path: tuple[str, ...]
    witness_ids: tuple[str, ...] = ()
    status: ContradictionStatus = ContradictionStatus.CONTRADICTION
    reason: str | None = None


@dataclass(frozen=True)
class ContradictionCheckResult:
    """Sequence-like contradiction result with explicit solver status."""

    pairs: tuple[tuple[str, str], ...]
    status: ContradictionStatus
    reason: str | None = None

    def __iter__(self) -> Iterator[tuple[str, str]]:
        return iter(self.pairs)

    def __len__(self) -> int:
        return len(self.pairs)

    @overload
    def __getitem__(self, index: int) -> tuple[str, str]: ...

    @overload
    def __getitem__(self, index: slice) -> tuple[tuple[str, str], ...]: ...

    def __getitem__(self, index: int | slice) -> tuple[str, str] | tuple[tuple[str, str], ...]:
        return self.pairs[index]

    def __eq__(self, other: object) -> bool:
        if isinstance(other, ContradictionCheckResult):
            return (
                self.pairs == other.pairs
                and self.status is other.status
                and self.reason == other.reason
            )
        if isinstance(other, tuple):
            return self.pairs == other
        return False


class BeliefGraph:
    """Track causal provenance and temporal validity for beliefs."""

    def __init__(self) -> None:
        self._nodes: dict[str, BeliefNode] = {}
        self._edges: list[BeliefEdge] = []
        self._confidence: dict[str, ConfidenceLevel] = {}
        self._explanations: dict[tuple[str, str], ContradictionExplanation] = {}

    def add_belief(
        self,
        belief_id: str,
        statement: str,
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
        ttl_seconds: int | None = None,
    ) -> BeliefNode:
        """Add a belief node with temporal metadata."""
        if belief_id in self._nodes:
            raise ValueError(f"Belief '{belief_id}' already exists")
        if not belief_id:
            raise ValueError("Belief id cannot be empty")
        if not statement:
            raise ValueError("Belief statement cannot be empty")
        if ttl_seconds is not None and ttl_seconds <= 0:
            raise ValueError("Belief ttl_seconds must be > 0")

        node = BeliefNode(
            belief_id=belief_id,
            statement=statement,
            valid_from=valid_from or datetime.now(timezone.utc),
            valid_until=valid_until,
            ttl_seconds=ttl_seconds,
        )
        self._nodes[belief_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, edge_type: BeliefEdgeType) -> BeliefEdge:
        """Add a typed edge between existing beliefs."""
        if source_id not in self._nodes:
            raise ValueError(f"Unknown belief id '{source_id}'")
        if target_id not in self._nodes:
            raise ValueError(f"Unknown belief id '{target_id}'")

        edge = BeliefEdge(source_id=source_id, target_id=target_id, edge_type=edge_type)
        if edge not in self._edges:
            self._edges.append(edge)
        return edge

    def get_belief(self, belief_id: str) -> BeliefNode:
        """Get belief node by id."""
        if belief_id not in self._nodes:
            raise ValueError(f"Unknown belief id '{belief_id}'")
        return self._nodes[belief_id]

    def beliefs(self) -> tuple[BeliefNode, ...]:
        """Return all beliefs sorted by id for deterministic iteration."""
        return tuple(self._nodes[key] for key in sorted(self._nodes))

    def edges(self) -> tuple[BeliefEdge, ...]:
        """Return all edges sorted deterministically."""
        return tuple(
            sorted(
                self._edges,
                key=lambda edge: (edge.edge_type.value, edge.source_id, edge.target_id),
            )
        )

    def minimal_support_set(self, belief_id: str) -> tuple[str, ...]:
        """Return minimal supporting root beliefs for a target belief."""
        self.get_belief(belief_id)
        support_types = {BeliefEdgeType.SUPPORTS, BeliefEdgeType.DERIVED_FROM}
        roots: set[str] = set()
        queue: deque[str] = deque([belief_id])
        seen: set[str] = set()

        while queue:
            current = queue.popleft()
            if current in seen:
                continue
            seen.add(current)

            parents = [
                edge.source_id
                for edge in self._edges
                if edge.target_id == current and edge.edge_type in support_types
            ]
            if not parents:
                roots.add(current)
                continue
            for parent in parents:
                queue.append(parent)

        return tuple(sorted(roots))

    def stale_dependencies(self, at_time: datetime | None = None) -> tuple[str, ...]:
        """Return stale dependencies that still support/derive other beliefs."""
        now = at_time or datetime.now(timezone.utc)
        support_types = {BeliefEdgeType.SUPPORTS, BeliefEdgeType.DERIVED_FROM}
        candidates = {
            edge.source_id
            for edge in self._edges
            if edge.edge_type in support_types
        }

        stale = [belief_id for belief_id in candidates if self._is_stale(self._nodes[belief_id], now)]
        return tuple(sorted(stale))

    def contradiction_frontier(self) -> tuple[tuple[str, str], ...]:
        """Return explicit contradictory belief pairs."""
        pairs: set[tuple[str, str]] = set()
        for edge in self._edges:
            if edge.edge_type is not BeliefEdgeType.CONTRADICTS:
                continue
            pair_values = sorted((edge.source_id, edge.target_id))
            left, right = pair_values[0], pair_values[1]
            pairs.add((left, right))
        return tuple(sorted(pairs))

    def explain_contradiction(self, left_id: str, right_id: str) -> ContradictionExplanation:
        """Explain contradiction with explicit support paths for both beliefs."""
        pair_values = sorted((left_id, right_id))
        pair = (pair_values[0], pair_values[1])
        if pair not in self.contradiction_frontier():
            raise ValueError(f"Beliefs '{left_id}' and '{right_id}' are not contradictory")

        cached = self._explanations.get(pair)
        if cached is not None:
            return cached

        return ContradictionExplanation(
            left_id=left_id,
            right_id=right_id,
            left_support_path=self._support_path_to_root(left_id),
            right_support_path=self._support_path_to_root(right_id),
            witness_ids=tuple(sorted(set(self._support_closure(left_id)) | set(self._support_closure(right_id)))),
        )

    def ingest_assumptions(self, assumptions: object) -> tuple[str, ...]:
        """Integration hook: ingest active assumptions as beliefs.

        The method accepts ``AssumptionSet`` to avoid hard coupling in typing.
        """
        active_entries = getattr(assumptions, "active_entries")
        if not callable(active_entries):
            raise ValueError("assumptions object must provide active_entries()")

        entries_obj = active_entries()
        if not isinstance(entries_obj, Iterable):
            raise ValueError("assumptions active_entries() must return an iterable")

        ingested: list[str] = []
        entries = entries_obj
        for entry in entries:
            belief_id = str(getattr(entry, "assumption_id"))
            statement = str(getattr(entry, "statement"))
            if belief_id not in self._nodes:
                self.add_belief(belief_id=belief_id, statement=statement)
            ingested.append(belief_id)
        return tuple(sorted(ingested))

    def calibrate_confidence(
        self,
        belief_id: str,
        calibrator: UncertaintyCalibrator,
        verified: bool,
        evidence_count: int = 1,
        conflicting_signals: bool = False,
    ) -> ConfidenceLevel:
        """Integration hook: attach calibrated confidence to one belief."""
        self.get_belief(belief_id)
        level = calibrator.classify(
            verified=verified,
            evidence_count=evidence_count,
            conflicting_signals=conflicting_signals,
        )
        self._confidence[belief_id] = level
        return level

    def confidence(self, belief_id: str) -> ConfidenceLevel | None:
        """Get stored confidence level for a belief."""
        self.get_belief(belief_id)
        return self._confidence.get(belief_id)

    def detect_contradictions_z3(
        self,
        variables: dict[str, str] | None = None,
        timeout_ms: int = 30000,
    ) -> ContradictionCheckResult:
        """Detect contradictory belief pairs using Z3.

        For every pair of beliefs, checks whether the combined support
        closures of both beliefs are jointly unsatisfiable. If so, adds a
        CONTRADICTS edge, stores a minimized Z3-derived witness, and
        includes the pair in the result. If Z3 returns ``unknown`` for any
        candidate pair, the overall status is surfaced explicitly.

        Parameters
        ----------
        variables : dict[str, str] | None
            Variable declarations as ``{name: sort}`` pairs.
            If ``None``, single-letter identifiers are auto-declared as Int.
        timeout_ms : int
            Z3 solver timeout per pair check.

        Returns
        -------
        ContradictionCheckResult
            Sequence-like contradiction pairs plus explicit solver status.
        """
        nodes = list(self._nodes.values())
        found: set[tuple[str, str]] = set()
        unknown_reason: str | None = None
        self._explanations.clear()

        for i in range(len(nodes)):
            for j in range(i + 1, len(nodes)):
                left, right = nodes[i], nodes[j]
                support_ids = tuple(
                    sorted(set(self._support_closure(left.belief_id)) | set(self._support_closure(right.belief_id)))
                )
                result = _check_belief_subset(self, support_ids, variables=variables, timeout_ms=timeout_ms)
                if result.satisfiable is False:
                    pair_sorted = sorted((left.belief_id, right.belief_id))
                    pair = (pair_sorted[0], pair_sorted[1])
                    found.add(pair)
                    self.add_edge(left.belief_id, right.belief_id, BeliefEdgeType.CONTRADICTS)
                    witness_ids = _minimize_unsat_witness(
                        self,
                        result.unsat_core or list(support_ids),
                        variables=variables,
                        timeout_ms=timeout_ms,
                    )
                    self._explanations[pair] = ContradictionExplanation(
                        left_id=left.belief_id,
                        right_id=right.belief_id,
                        left_support_path=self._support_path_to_root(left.belief_id),
                        right_support_path=self._support_path_to_root(right.belief_id),
                        witness_ids=witness_ids,
                    )
                elif result.satisfiable is None and unknown_reason is None:
                    unknown_reason = result.reason

        status = ContradictionStatus.UNKNOWN if unknown_reason is not None else (
            ContradictionStatus.CONTRADICTION if found else ContradictionStatus.CONSISTENT
        )
        return ContradictionCheckResult(tuple(sorted(found)), status=status, reason=unknown_reason)

    def _is_stale(self, node: BeliefNode, at_time: datetime) -> bool:
        valid_until = self._effective_valid_until(node)
        if valid_until is None:
            return False
        return at_time > valid_until

    def _effective_valid_until(self, node: BeliefNode) -> datetime | None:
        if node.valid_until is not None:
            return node.valid_until
        if node.ttl_seconds is not None:
            return node.valid_from + timedelta(seconds=node.ttl_seconds)
        return None

    def _support_path_to_root(self, belief_id: str) -> tuple[str, ...]:
        support_types = {BeliefEdgeType.SUPPORTS, BeliefEdgeType.DERIVED_FROM}
        path: list[str] = [belief_id]
        current = belief_id

        while True:
            parents = sorted(
                [
                    edge.source_id
                    for edge in self._edges
                    if edge.target_id == current and edge.edge_type in support_types
                ]
            )
            if not parents:
                break
            current = parents[0]
            path.append(current)

        return tuple(path)

    def _support_closure(self, belief_id: str) -> tuple[str, ...]:
        support_types = {BeliefEdgeType.SUPPORTS, BeliefEdgeType.DERIVED_FROM}
        closure: set[str] = set()
        queue: deque[str] = deque([belief_id])

        while queue:
            current = queue.popleft()
            if current in closure:
                continue
            closure.add(current)
            for edge in self._edges:
                if edge.target_id == current and edge.edge_type in support_types:
                    queue.append(edge.source_id)

        return tuple(sorted(closure))


def _check_belief_subset(
    graph: BeliefGraph,
    belief_ids: Iterable[str],
    *,
    variables: dict[str, str] | None,
    timeout_ms: int,
    track_unsat_core: bool = False,
) -> CheckResult:
    from logos.z3_session import Z3Session

    ordered_ids = tuple(sorted(set(belief_ids)))
    session = Z3Session(timeout_ms=timeout_ms, track_unsat_core=track_unsat_core)

    statements = [graph.get_belief(belief_id).statement for belief_id in ordered_ids]
    if variables is not None:
        for var_name, sort in variables.items():
            session.declare(var_name, sort)
    else:
        _auto_declare_belief_variables(session, statements)

    for belief_id in ordered_ids:
        session.assert_constraint(graph.get_belief(belief_id).statement, name=belief_id)

    return session.check()


def _minimize_unsat_witness(
    graph: BeliefGraph,
    belief_ids: Iterable[str],
    *,
    variables: dict[str, str] | None,
    timeout_ms: int,
) -> tuple[str, ...]:
    witness = list(dict.fromkeys(sorted(set(belief_ids))))
    if len(witness) <= 1:
        return tuple(witness)

    index = 0
    while index < len(witness):
        candidate = witness[:index] + witness[index + 1 :]
        if not candidate:
            index += 1
            continue
        result = _check_belief_subset(graph, candidate, variables=variables, timeout_ms=timeout_ms)
        if getattr(result, "satisfiable") is False:
            witness = candidate
            continue
        index += 1
    return tuple(witness)


def _auto_declare_belief_variables(session: object, statements: list[str]) -> None:
    """Best-effort auto-declare single-letter variables as Int."""
    import re

    declare = getattr(session, "declare")
    declared: set[str] = set()
    for statement in statements:
        for match in re.finditer(r"\b([a-z])\b", statement):
            name = match.group(1)
            if name not in declared:
                declare(name, "Int")
                declared.add(name)
