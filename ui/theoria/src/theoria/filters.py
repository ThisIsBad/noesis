"""Predicate-based filtering and full-text search over DecisionTraces.

Used by ``GET /api/traces`` query-string filters and by the
``theoria list`` CLI. Kept as a pure-function module so it's trivial
to test and reuse.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Sequence

from theoria.models import DecisionTrace


@dataclass(frozen=True)
class TraceFilter:
    """Declarative filter over a collection of DecisionTraces.

    All fields are optional — an empty filter matches every trace. Fields
    combine with AND semantics; list-valued fields (``tags``) with OR.
    """

    source: str | None = None
    kind: str | None = None
    verdict: str | None = None
    tags: Sequence[str] = ()
    text: str | None = None  # case-insensitive substring search
    since: datetime | None = None  # created_at >= since
    until: datetime | None = None  # created_at <= until

    def matches(self, trace: DecisionTrace) -> bool:
        if self.source and trace.source != self.source:
            return False
        if self.kind and trace.kind != self.kind:
            return False
        if self.verdict:
            if trace.outcome is None or trace.outcome.verdict != self.verdict:
                return False
        if self.tags and not any(t in trace.tags for t in self.tags):
            return False
        if self.text:
            needle = self.text.lower()
            haystack_parts = [
                trace.title or "",
                trace.question or "",
                " ".join(s.label for s in trace.steps),
                " ".join(s.detail or "" for s in trace.steps),
                " ".join(trace.tags),
            ]
            haystack = " ".join(haystack_parts).lower()
            if needle not in haystack:
                return False
        if self.since is not None or self.until is not None:
            created = _parse_iso(trace.created_at)
            if created is None:
                return False
            if self.since is not None and created < self.since:
                return False
            if self.until is not None and created > self.until:
                return False
        return True


def apply_filter(
    traces: Iterable[DecisionTrace],
    flt: TraceFilter | None,
    *,
    limit: int | None = None,
) -> list[DecisionTrace]:
    """Apply ``flt`` (if any) and cap the result at ``limit``."""
    it = iter(traces) if flt is None else (t for t in traces if flt.matches(t))
    if limit is None:
        return list(it)
    out: list[DecisionTrace] = []
    for trace in it:
        out.append(trace)
        if len(out) >= limit:
            break
    return out


def filter_from_query(query: dict[str, list[str]]) -> tuple[TraceFilter, int | None]:
    """Build a filter + optional limit from parsed query-string params.

    ``query`` is the output of ``urllib.parse.parse_qs``; every value is a
    list. We take the first value for scalar fields and keep all values for
    list-valued fields (``tag``).
    """

    def first(name: str) -> str | None:
        values = query.get(name)
        return values[0] if values else None

    tags: list[str] = []
    for name in ("tag", "tags"):
        tags.extend(query.get(name, []))
    # Support comma-separated values too, e.g. tag=a,b → [a, b].
    flat: list[str] = []
    for t in tags:
        flat.extend(part.strip() for part in t.split(",") if part.strip())

    since_raw = first("since")
    until_raw = first("until")
    limit_raw = first("limit")
    limit = int(limit_raw) if limit_raw and limit_raw.isdigit() else None

    return (
        TraceFilter(
            source=first("source"),
            kind=first("kind"),
            verdict=first("verdict"),
            tags=tuple(flat),
            text=first("q") or first("text"),
            since=_parse_iso(since_raw) if since_raw else None,
            until=_parse_iso(until_raw) if until_raw else None,
        ),
        limit,
    )


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    # datetime.fromisoformat handles offsets on 3.11+. Fallback-normalize a
    # trailing "Z" so callers can pass UTC instants naturally.
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None
