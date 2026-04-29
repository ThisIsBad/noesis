"""Typed assumption state management for long-horizon reasoning."""

from __future__ import annotations

import json
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
from typing import Callable

from logos.schema_utils import (
    load_json_object,
    require_dict,
    require_list,
    require_optional_str,
    require_str,
)

SCHEMA_VERSION = "1.0"


class AssumptionKind(Enum):
    """Typed assumption categories."""

    FACT = "fact"
    ASSUMPTION = "assumption"
    HYPOTHESIS = "hypothesis"


class AssumptionStatus(Enum):
    """Lifecycle states for assumptions."""

    ACTIVE = "active"
    EXPIRED = "expired"
    RETRACTED = "retracted"


@dataclass(frozen=True)
class AssumptionEntry:
    """Single assumption with provenance and lifecycle metadata."""

    assumption_id: str
    statement: str
    kind: AssumptionKind
    source: str
    timestamp: str
    scope: str | None = None
    expires_at: str | None = None
    status: AssumptionStatus = AssumptionStatus.ACTIVE


@dataclass(frozen=True)
class AssumptionConsistency:
    """Consistency result over active assumptions."""

    consistent: bool
    active_statements: list[str]
    solver_status: str | None = None
    reason: str | None = None


class AssumptionSet:
    """Manage typed assumptions with deterministic lifecycle operations."""

    def __init__(self, schema_version: str = SCHEMA_VERSION) -> None:
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported assumption schema version '{schema_version}'")
        self.schema_version = schema_version
        self._entries: dict[str, AssumptionEntry] = {}

    def add(
        self,
        assumption_id: str,
        statement: str,
        kind: AssumptionKind,
        source: str,
        scope: str | None = None,
        expires_at: str | None = None,
        timestamp: str | None = None,
    ) -> AssumptionEntry:
        """Add a new active assumption entry."""
        if assumption_id in self._entries:
            raise ValueError(f"Assumption '{assumption_id}' already exists")

        if not assumption_id:
            raise ValueError("Assumption id cannot be empty")
        if not statement:
            raise ValueError("Assumption statement cannot be empty")
        if not source:
            raise ValueError("Assumption source cannot be empty")

        entry = AssumptionEntry(
            assumption_id=assumption_id,
            statement=statement,
            kind=kind,
            source=source,
            timestamp=timestamp or _utc_now_iso(),
            scope=scope,
            expires_at=expires_at,
            status=AssumptionStatus.ACTIVE,
        )
        self._entries[assumption_id] = entry
        return entry

    def activate(self, assumption_id: str) -> AssumptionEntry:
        """Activate an expired assumption."""
        return self._transition(assumption_id, AssumptionStatus.ACTIVE)

    def expire(self, assumption_id: str) -> AssumptionEntry:
        """Expire an active assumption."""
        return self._transition(assumption_id, AssumptionStatus.EXPIRED)

    def retract(self, assumption_id: str) -> AssumptionEntry:
        """Retract an assumption (idempotent)."""
        entry = self._get_required(assumption_id)
        if entry.status is AssumptionStatus.RETRACTED:
            return entry

        updated = replace(entry, status=AssumptionStatus.RETRACTED)
        self._entries[assumption_id] = updated
        return updated

    def get(self, assumption_id: str) -> AssumptionEntry | None:
        """Get an assumption by id."""
        return self._entries.get(assumption_id)

    def list_entries(self) -> list[AssumptionEntry]:
        """List all entries in insertion order."""
        return list(self._entries.values())

    def active_entries(self) -> list[AssumptionEntry]:
        """Return currently active assumptions."""
        return [entry for entry in self._entries.values() if entry.status is AssumptionStatus.ACTIVE]

    def active_statements(self) -> list[str]:
        """Return active assumption statements."""
        return [entry.statement for entry in self.active_entries()]

    def belief_payload(self) -> list[dict[str, str]]:
        """Export active assumptions as belief-style labeled assertions."""
        return [{"label": entry.assumption_id, "assertion": entry.statement} for entry in self.active_entries()]

    def check_consistency(
        self,
        checker: Callable[[list[str]], bool],
    ) -> AssumptionConsistency:
        """Run an external consistency checker on active statements.

        For a Z3-backed checker, use ``check_consistency_z3`` instead.
        """
        statements = self.active_statements()
        return AssumptionConsistency(
            consistent=checker(statements),
            active_statements=statements,
        )

    def check_consistency_z3(
        self,
        variables: dict[str, str] | None = None,
        timeout_ms: int = 30000,
    ) -> AssumptionConsistency:
        """Check active assumption consistency using Z3.

        Each active statement is parsed as a Z3 constraint via
        ``Z3Session.assert_constraint``. If the conjunction is
        unsatisfiable, the assumptions are contradictory.

        Parameters
        ----------
        variables : dict[str, str] | None
            Variable declarations as ``{name: sort}`` pairs.
            If ``None``, variables are inferred as ``Int`` from
            single-letter identifiers found in the statements
            (best-effort heuristic for simple cases).
        timeout_ms : int
            Z3 solver timeout in milliseconds.

        Returns
        -------
        AssumptionConsistency
            With ``consistent=True`` if all active statements can be
            simultaneously satisfied, ``False`` if Z3 proves UNSAT or
            returns ``unknown``. The solver outcome is exposed via
            ``solver_status`` and ``reason``.

        Raises
        ------
        ValueError
            If a statement cannot be parsed as a Z3 constraint.
        """
        from logos.z3_session import Z3Session

        statements = self.active_statements()
        if not statements:
            return AssumptionConsistency(
                consistent=True,
                active_statements=[],
                solver_status="sat",
            )

        session = Z3Session(timeout_ms=timeout_ms)

        if variables is not None:
            for var_name, sort in variables.items():
                session.declare(var_name, sort)
        else:
            _auto_declare_variables(session, statements)

        for statement in statements:
            session.assert_constraint(statement)

        result = session.check()
        return AssumptionConsistency(
            consistent=result.satisfiable is True,
            active_statements=statements,
            solver_status=result.status,
            reason=result.reason,
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize to a JSON-safe dictionary."""
        return {
            "schema_version": self.schema_version,
            "assumptions": [
                {
                    "assumption_id": entry.assumption_id,
                    "statement": entry.statement,
                    "kind": entry.kind.value,
                    "source": entry.source,
                    "timestamp": entry.timestamp,
                    "scope": entry.scope,
                    "expires_at": entry.expires_at,
                    "status": entry.status.value,
                }
                for entry in self._entries.values()
            ],
        }

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, payload: dict[str, object]) -> "AssumptionSet":
        """Deserialize from dictionary payload."""
        schema_version = require_str(
            payload.get("schema_version"),
            "Assumption payload requires string field 'schema_version'",
        )
        assumptions = require_list(
            payload.get("assumptions"),
            "Assumption payload requires list field 'assumptions'",
        )

        instance = cls(schema_version=schema_version)

        for item in assumptions:
            item_dict = require_dict(item, "Assumption entries must be objects")

            assumption_id = require_str(
                item_dict.get("assumption_id"),
                "Assumption field 'assumption_id' must be a string",
            )
            statement = require_str(
                item_dict.get("statement"),
                "Assumption field 'statement' must be a string",
            )
            kind = require_str(
                item_dict.get("kind"),
                "Assumption field 'kind' must be a string",
            )
            source = require_str(
                item_dict.get("source"),
                "Assumption field 'source' must be a string",
            )
            timestamp = require_str(
                item_dict.get("timestamp"),
                "Assumption field 'timestamp' must be a string",
            )
            scope = require_optional_str(
                item_dict.get("scope"),
                "Assumption field 'scope' must be a string or null",
            )
            expires_at = require_optional_str(
                item_dict.get("expires_at"),
                "Assumption field 'expires_at' must be a string or null",
            )
            status = require_str(
                item_dict.get("status"),
                "Assumption field 'status' must be a string",
            )

            entry = AssumptionEntry(
                assumption_id=assumption_id,
                statement=statement,
                kind=AssumptionKind(kind),
                source=source,
                timestamp=timestamp,
                scope=scope,
                expires_at=expires_at,
                status=AssumptionStatus(status),
            )
            instance._entries[assumption_id] = entry

        return instance

    @classmethod
    def from_json(cls, raw_json: str) -> "AssumptionSet":
        """Deserialize from JSON string."""
        payload = load_json_object(
            raw_json,
            invalid_error="Invalid assumptions JSON",
            object_error="Assumptions JSON must be an object",
        )
        return cls.from_dict(payload)

    def _transition(self, assumption_id: str, target: AssumptionStatus) -> AssumptionEntry:
        entry = self._get_required(assumption_id)

        if entry.status is AssumptionStatus.RETRACTED:
            raise ValueError("Retracted assumptions cannot change lifecycle state")

        if target is AssumptionStatus.ACTIVE and entry.status is not AssumptionStatus.EXPIRED:
            raise ValueError("Only expired assumptions can be activated")

        if target is AssumptionStatus.EXPIRED and entry.status is not AssumptionStatus.ACTIVE:
            raise ValueError("Only active assumptions can be expired")

        updated = replace(entry, status=target)
        self._entries[assumption_id] = updated
        return updated

    def _get_required(self, assumption_id: str) -> AssumptionEntry:
        entry = self._entries.get(assumption_id)
        if entry is None:
            raise ValueError(f"Unknown assumption id '{assumption_id}'")
        return entry


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _auto_declare_variables(session: object, statements: list[str]) -> None:
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
