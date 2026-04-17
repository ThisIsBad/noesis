"""In-memory verified proof memory with query and lifecycle management."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone

import z3

from logos.certificate import PROPOSITIONAL_CLAIM, ProofCertificate, SCHEMA_VERSION
from logos.models import Connective, LogicalExpression, Proposition
from logos.parser import parse_argument, parse_expression
from logos.schema_utils import load_json_object, require_dict, require_int, require_optional_str, require_str
from logos.verifier import PropositionalVerifier


@dataclass(frozen=True)
class StoredCertificate:
    """A certificate with store metadata."""

    store_id: str
    certificate: ProofCertificate
    tags: dict[str, str]
    stored_at: str
    invalidated_at: str | None = None
    invalidation_reason: str | None = None

    def to_dict(self) -> dict[str, object]:
        """Serialize a stored certificate."""
        return {
            "store_id": self.store_id,
            "certificate": self.certificate.to_dict(),
            "tags": dict(self.tags),
            "stored_at": self.stored_at,
            "invalidated_at": self.invalidated_at,
            "invalidation_reason": self.invalidation_reason,
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "StoredCertificate":
        """Deserialize a stored certificate."""
        store_id = require_str(data.get("store_id"), "StoredCertificate field 'store_id' must be a string")
        certificate_raw = require_dict(
            data.get("certificate"),
            "StoredCertificate field 'certificate' must be an object",
        )
        tags_raw = require_dict(data.get("tags", {}), "StoredCertificate field 'tags' must be an object")
        stored_at = require_str(data.get("stored_at"), "StoredCertificate field 'stored_at' must be a string")
        invalidated_at = require_optional_str(
            data.get("invalidated_at"),
            "StoredCertificate field 'invalidated_at' must be a string or null",
        )
        invalidation_reason = require_optional_str(
            data.get("invalidation_reason"),
            "StoredCertificate field 'invalidation_reason' must be a string or null",
        )

        tags: dict[str, str] = {}
        for key, value in tags_raw.items():
            if not isinstance(value, str):
                raise ValueError("StoredCertificate tags must map strings to strings")
            tags[str(key)] = value

        return cls(
            store_id=store_id,
            certificate=ProofCertificate.from_dict({str(key): value for key, value in certificate_raw.items()}),
            tags=tags,
            stored_at=stored_at,
            invalidated_at=invalidated_at,
            invalidation_reason=invalidation_reason,
        )


@dataclass(frozen=True)
class StoreStats:
    """Aggregate statistics about the certificate store."""

    total: int
    valid: int
    invalidated: int
    by_claim_type: dict[str, int]
    by_method: dict[str, int]

    def to_dict(self) -> dict[str, object]:
        """Serialize aggregate statistics."""
        return {
            "total": self.total,
            "valid": self.valid,
            "invalidated": self.invalidated,
            "by_claim_type": dict(self.by_claim_type),
            "by_method": dict(self.by_method),
        }

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "StoreStats":
        """Deserialize aggregate statistics."""
        by_claim_type_raw = require_dict(
            data.get("by_claim_type", {}),
            "StoreStats field 'by_claim_type' must be an object",
        )
        by_method_raw = require_dict(
            data.get("by_method", {}),
            "StoreStats field 'by_method' must be an object",
        )
        return cls(
            total=require_int(data.get("total"), "StoreStats field 'total' must be an integer"),
            valid=require_int(data.get("valid"), "StoreStats field 'valid' must be an integer"),
            invalidated=require_int(
                data.get("invalidated"),
                "StoreStats field 'invalidated' must be an integer",
            ),
            by_claim_type=_deserialize_counter_map(by_claim_type_raw, "by_claim_type"),
            by_method=_deserialize_counter_map(by_method_raw, "by_method"),
        )


@dataclass(frozen=True)
class CompactionResult:
    """Result of a Z3-verified store compaction."""

    removed_count: int
    retained_count: int
    removed_ids: tuple[str, ...]
    verification_passed: bool


@dataclass(frozen=True)
class ConsistencyFilterResult:
    """Result of a Z3 consistency-filtered query."""

    consistent: list[StoredCertificate]
    inconsistent_count: int
    premises_contradictory: bool


@dataclass(frozen=True)
class RankedCertificate:
    """A stored certificate with a relevance score."""

    entry: StoredCertificate
    score: float


@dataclass(frozen=True)
class RelevanceResult:
    """Result of a relevance-ranked query."""

    results: list[RankedCertificate]
    total_candidates: int


class CertificateStore:
    """In-memory store for proof certificates with query and lifecycle management."""

    def __init__(self) -> None:
        self._entries: dict[str, StoredCertificate] = {}

    def store(self, certificate: ProofCertificate, tags: dict[str, str] | None = None) -> str:
        """Store a certificate and return its deterministic store id."""
        _validate_tags(tags)
        store_id = _store_id(certificate)
        existing = self._entries.get(store_id)
        merged_tags = _merge_tags(existing.tags if existing is not None else {}, tags or {})

        if existing is not None:
            if merged_tags != existing.tags:
                self._entries[store_id] = StoredCertificate(
                    store_id=existing.store_id,
                    certificate=existing.certificate,
                    tags=merged_tags,
                    stored_at=existing.stored_at,
                    invalidated_at=existing.invalidated_at,
                    invalidation_reason=existing.invalidation_reason,
                )
            return store_id

        self._entries[store_id] = StoredCertificate(
            store_id=store_id,
            certificate=certificate,
            tags=merged_tags,
            stored_at=_utc_now_iso(),
        )
        return store_id

    def get(self, store_id: str) -> StoredCertificate | None:
        """Retrieve a stored certificate by id."""
        return self._entries.get(store_id)

    def query(
        self,
        *,
        claim_pattern: str | None = None,
        method: str | None = None,
        verified: bool | None = None,
        tags: dict[str, str] | None = None,
        include_invalidated: bool = False,
        since: str | None = None,
        limit: int = 50,
    ) -> list[StoredCertificate]:
        """Query stored certificates sorted by newest first."""
        if limit < 0:
            raise ValueError("query() limit must be non-negative")
        _validate_tags(tags)
        since_dt = _parse_iso(since) if since is not None else None

        matches: list[StoredCertificate] = []
        for entry in self._entries.values():
            if not include_invalidated and entry.invalidated_at is not None:
                continue
            if claim_pattern is not None and claim_pattern not in _claim_text(entry.certificate):
                continue
            if method is not None and entry.certificate.method != method:
                continue
            if verified is not None and entry.certificate.verified is not verified:
                continue
            if tags is not None and not all(entry.tags.get(key) == value for key, value in tags.items()):
                continue
            if since_dt is not None and _parse_iso(entry.stored_at) < since_dt:
                continue
            matches.append(entry)

        matches.sort(key=lambda item: _parse_iso(item.stored_at), reverse=True)
        return matches[:limit]

    def invalidate(self, store_id: str, *, reason: str) -> StoredCertificate:
        """Mark a certificate as invalidated."""
        if not reason:
            raise ValueError("invalidate() reason cannot be empty")
        entry = self._entries.get(store_id)
        if entry is None:
            raise ValueError(f"Unknown certificate store id '{store_id}'")
        if entry.invalidated_at is not None:
            return entry

        updated = StoredCertificate(
            store_id=entry.store_id,
            certificate=entry.certificate,
            tags=dict(entry.tags),
            stored_at=entry.stored_at,
            invalidated_at=_utc_now_iso(),
            invalidation_reason=reason,
        )
        self._entries[store_id] = updated
        return updated

    def prune(self, *, max_age_seconds: float | None = None, invalidated_only: bool = False) -> int:
        """Physically remove matching entries and return the number pruned."""
        now = datetime.now(timezone.utc)
        removable: list[str] = []

        for store_id, entry in self._entries.items():
            age_matches = True
            invalidation_matches = True

            if max_age_seconds is not None:
                age_matches = (now - _parse_iso(entry.stored_at)).total_seconds() > max_age_seconds
            if invalidated_only:
                invalidation_matches = entry.invalidated_at is not None

            if age_matches and invalidation_matches:
                removable.append(store_id)

        for store_id in removable:
            del self._entries[store_id]
        return len(removable)

    def stats(self) -> StoreStats:
        """Return aggregate statistics about the store."""
        by_claim_type: dict[str, int] = {}
        by_method: dict[str, int] = {}
        valid = 0
        invalidated = 0

        for entry in self._entries.values():
            by_claim_type[entry.certificate.claim_type] = by_claim_type.get(entry.certificate.claim_type, 0) + 1
            by_method[entry.certificate.method] = by_method.get(entry.certificate.method, 0) + 1
            if entry.invalidated_at is None:
                valid += 1
            else:
                invalidated += 1

        return StoreStats(
            total=len(self._entries),
            valid=valid,
            invalidated=invalidated,
            by_claim_type=by_claim_type,
            by_method=by_method,
        )

    def clear(self) -> None:
        """Remove all entries."""
        self._entries.clear()

    def compact(self) -> CompactionResult:
        """Remove logically redundant propositional certificates via Z3 entailment."""
        candidates = self._compaction_candidates()
        if not candidates:
            return CompactionResult(
                removed_count=0,
                retained_count=len(self._entries),
                removed_ids=(),
                verification_passed=True,
            )

        candidate_ids = sorted(candidates)
        retained_ids = list(candidate_ids)
        removed_ids: list[str] = []

        for target_id in candidate_ids:
            if target_id not in retained_ids:
                continue
            remaining_ids = [store_id for store_id in retained_ids if store_id != target_id]
            if not remaining_ids:
                continue
            if _check_propositional_entailment(
                premises_conclusions=[candidates[store_id] for store_id in remaining_ids],
                target_conclusion=candidates[target_id],
            ):
                retained_ids.remove(target_id)
                removed_ids.append(target_id)

        verification_passed = all(
            _check_propositional_entailment(
                premises_conclusions=[candidates[store_id] for store_id in retained_ids],
                target_conclusion=candidates[store_id],
            )
            for store_id in candidate_ids
        )

        if verification_passed:
            for store_id in removed_ids:
                del self._entries[store_id]

        return CompactionResult(
            removed_count=len(removed_ids) if verification_passed else 0,
            retained_count=len(self._entries) if verification_passed else len(self._entries),
            removed_ids=tuple(removed_ids) if verification_passed else (),
            verification_passed=verification_passed,
        )

    def query_consistent(
        self,
        premises: list[str],
        *,
        verified: bool | None = None,
        tags: dict[str, str] | None = None,
        include_invalidated: bool = False,
        limit: int = 50,
    ) -> ConsistencyFilterResult:
        """Query certificates filtered by Z3 consistency with given premises."""
        if limit < 0:
            raise ValueError("query_consistent() limit must be non-negative")
        _validate_tags(tags)

        if premises and not _check_consistency(premises, None):
            return ConsistencyFilterResult(
                consistent=[],
                inconsistent_count=0,
                premises_contradictory=True,
            )

        candidates: list[StoredCertificate] = []
        for entry in self.query(
            verified=verified,
            tags=tags,
            include_invalidated=include_invalidated,
            limit=len(self._entries),
        ):
            if entry.certificate.claim_type != PROPOSITIONAL_CLAIM:
                continue
            if not isinstance(entry.certificate.claim, str):
                continue
            candidates.append(entry)

        if not premises:
            return ConsistencyFilterResult(
                consistent=candidates[:limit],
                inconsistent_count=0,
                premises_contradictory=False,
            )

        consistent: list[StoredCertificate] = []
        inconsistent_count = 0
        for entry in candidates:
            assert isinstance(entry.certificate.claim, str)
            conclusion = _extract_conclusion_text(entry.certificate.claim)
            if _check_consistency(premises, conclusion):
                consistent.append(entry)
            else:
                inconsistent_count += 1

        return ConsistencyFilterResult(
            consistent=consistent[:limit],
            inconsistent_count=inconsistent_count,
            premises_contradictory=False,
        )

    def query_ranked(
        self,
        query: str,
        *,
        verified: bool | None = None,
        tags: dict[str, str] | None = None,
        include_invalidated: bool = False,
        limit: int = 10,
    ) -> RelevanceResult:
        """Query certificates ranked by token-overlap relevance to *query*.

        Scoring uses Jaccard similarity over lowercased alphanumeric tokens
        extracted from the query and each certificate's claim text.
        """
        if limit < 0:
            raise ValueError("query_ranked() limit must be non-negative")
        if not query.strip():
            raise ValueError("query_ranked() query must be non-empty")
        _validate_tags(tags)

        query_tokens = _tokenize(query)
        candidates = self.query(
            verified=verified,
            tags=tags,
            include_invalidated=include_invalidated,
            limit=len(self._entries),
        )

        scored: list[RankedCertificate] = []
        for entry in candidates:
            claim_tokens = _tokenize(_claim_text(entry.certificate))
            score = _jaccard(query_tokens, claim_tokens)
            if score > 0.0:
                scored.append(RankedCertificate(entry=entry, score=score))

        scored.sort(key=lambda r: (-r.score, r.entry.stored_at))
        return RelevanceResult(
            results=scored[:limit],
            total_candidates=len(scored),
        )

    def to_dict(self) -> dict[str, object]:
        """Serialize the full store."""
        return {
            "schema_version": SCHEMA_VERSION,
            "entries": [entry.to_dict() for entry in self.query(include_invalidated=True, limit=len(self._entries))],
        }

    def to_json(self) -> str:
        """Serialize the full store to JSON."""
        return json.dumps(self.to_dict(), sort_keys=True)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "CertificateStore":
        """Deserialize a full store."""
        schema_version = require_str(
            data.get("schema_version"),
            "CertificateStore field 'schema_version' must be a string",
        )
        if schema_version != SCHEMA_VERSION:
            raise ValueError(f"Unsupported certificate store schema version '{schema_version}'")
        entries_raw = data.get("entries")
        if not isinstance(entries_raw, list):
            raise ValueError("CertificateStore field 'entries' must be a list")

        instance = cls()
        for item in entries_raw:
            item_dict = require_dict(item, "CertificateStore entries must be objects")
            entry = StoredCertificate.from_dict({str(key): value for key, value in item_dict.items()})
            instance._entries[entry.store_id] = entry
        return instance

    @classmethod
    def from_json(cls, raw_json: str) -> "CertificateStore":
        """Deserialize a full store from JSON."""
        payload = load_json_object(
            raw_json,
            invalid_error="Invalid certificate store JSON",
            object_error="Certificate store JSON must be an object",
        )
        return cls.from_dict(payload)

    def _compaction_candidates(self) -> dict[str, str]:
        candidates: dict[str, str] = {}
        for store_id in sorted(self._entries):
            entry = self._entries[store_id]
            if entry.invalidated_at is not None:
                continue
            if not entry.certificate.verified:
                continue
            if entry.certificate.claim_type != PROPOSITIONAL_CLAIM:
                continue
            if not isinstance(entry.certificate.claim, str):
                continue
            candidates[store_id] = _extract_conclusion_text(entry.certificate.claim)
        return candidates


def _store_id(certificate: ProofCertificate) -> str:
    return hashlib.sha256(certificate.to_json().encode()).hexdigest()


def _check_propositional_entailment(
    premises_conclusions: list[str],
    target_conclusion: str,
) -> bool:
    if not premises_conclusions:
        return False

    verifier = PropositionalVerifier()
    premise_exprs = [parse_argument(f"{conclusion} |- {conclusion}").conclusion for conclusion in premises_conclusions]
    target_expr = parse_argument(f"{target_conclusion} |- {target_conclusion}").conclusion

    atoms: set[str] = set()
    for premise in premise_exprs:
        verifier._collect_atoms_from_expr(premise, atoms)
    verifier._collect_atoms_from_expr(target_expr, atoms)

    z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}
    solver = z3.Solver()
    for premise in premise_exprs:
        solver.add(verifier._to_z3(premise, z3_vars))
    solver.add(z3.Not(verifier._to_z3(target_expr, z3_vars)))
    return bool(solver.check() == z3.unsat)


def _check_consistency(premises: list[str], conclusion: str | None) -> bool:
    verifier = PropositionalVerifier()
    premise_exprs = [parse_expression(premise) for premise in premises]
    conclusion_expr = parse_argument(f"{conclusion} |- {conclusion}").conclusion if conclusion is not None else None

    atoms: set[str] = set()
    for premise in premise_exprs:
        verifier._collect_atoms_from_expr(premise, atoms)
    if conclusion_expr is not None:
        verifier._collect_atoms_from_expr(conclusion_expr, atoms)

    z3_vars = {label: z3.Bool(label) for label in sorted(atoms)}
    solver = z3.Solver()
    for premise in premise_exprs:
        solver.add(verifier._to_z3(premise, z3_vars))
    if conclusion_expr is not None:
        solver.add(verifier._to_z3(conclusion_expr, z3_vars))
    return bool(solver.check() == z3.sat)


def _extract_conclusion_text(claim: str) -> str:
    return _expression_to_ascii(parse_argument(claim).conclusion)


def _expression_to_ascii(expr: Proposition | LogicalExpression) -> str:
    if isinstance(expr, Proposition):
        return expr.label
    if expr.connective is Connective.NOT:
        return f"~({_expression_to_ascii(expr.left)})"
    if expr.right is None:
        raise AssertionError("Binary expression requires right operand")
    left = _expression_to_ascii(expr.left)
    right = _expression_to_ascii(expr.right)
    if expr.connective is Connective.AND:
        return f"({left} & {right})"
    if expr.connective is Connective.OR:
        return f"({left} | {right})"
    if expr.connective is Connective.IMPLIES:
        return f"({left} -> {right})"
    if expr.connective is Connective.IFF:
        return f"({left} <-> {right})"
    raise AssertionError(f"Unsupported connective {expr.connective}")


def _merge_tags(existing: dict[str, str], new: dict[str, str]) -> dict[str, str]:
    merged = dict(existing)
    merged.update(new)
    return merged


def _validate_tags(tags: dict[str, str] | None) -> None:
    if tags is None:
        return
    for key, value in tags.items():
        if not isinstance(key, str) or not isinstance(value, str):
            raise ValueError("CertificateStore tags must be dict[str, str]")


def _claim_text(certificate: ProofCertificate) -> str:
    if isinstance(certificate.claim, str):
        return certificate.claim
    return json.dumps(certificate.claim, sort_keys=True)


def _deserialize_counter_map(data: dict[str, object], field_name: str) -> dict[str, int]:
    result: dict[str, int] = {}
    for key, value in data.items():
        if not isinstance(value, int):
            raise ValueError(f"StoreStats field '{field_name}' must map strings to integers")
        result[str(key)] = value
    return result


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _tokenize(text: str) -> set[str]:
    """Extract lowercased alphanumeric tokens from *text*."""
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _jaccard(a: set[str], b: set[str]) -> float:
    """Jaccard similarity between two token sets."""
    if not a or not b:
        return 0.0
    intersection = a & b
    union = a | b
    return len(intersection) / len(union)
