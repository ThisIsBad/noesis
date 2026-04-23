"""Aggregate statistics over a collection of DecisionTraces.

Used by ``GET /api/stats`` to give operators a one-glance dashboard of
what's flowing through Theoria: counts by source/kind/verdict/status,
per-day rollups, and the most common triggered rules / failing
conclusions.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Iterable, Sequence

from theoria.models import DecisionTrace, ReasoningStep, StepKind, StepStatus


@dataclass
class TraceStats:
    """Aggregate view of a trace collection."""

    total: int = 0
    by_source: dict[str, int] = field(default_factory=dict)
    by_kind: dict[str, int] = field(default_factory=dict)
    by_verdict: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)
    by_day: dict[str, int] = field(default_factory=dict)
    top_triggered_rules: list[dict[str, Any]] = field(default_factory=list)
    top_failed_conclusions: list[dict[str, Any]] = field(default_factory=list)
    mean_confidence: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_stats(
    traces: Iterable[DecisionTrace],
    *,
    top_n: int = 5,
) -> TraceStats:
    """Fold ``traces`` into a :class:`TraceStats`.

    Single pass, O(total step count). Safe to call on empty input.
    """
    stats = TraceStats()
    by_source: Counter[str] = Counter()
    by_kind: Counter[str] = Counter()
    by_verdict: Counter[str] = Counter()
    by_status: Counter[str] = Counter()
    by_day: Counter[str] = Counter()
    triggered_rules: Counter[str] = Counter()
    failed_conclusions: Counter[str] = Counter()
    confidence_total = 0.0
    confidence_count = 0

    for trace in traces:
        stats.total += 1
        by_source[trace.source] += 1
        by_kind[trace.kind] += 1
        if trace.outcome is not None:
            by_verdict[trace.outcome.verdict] += 1
            if trace.outcome.confidence is not None:
                confidence_total += float(trace.outcome.confidence)
                confidence_count += 1
        day = _day_bucket(trace.created_at)
        if day is not None:
            by_day[day] += 1

        for step in trace.steps:
            by_status[step.status.value] += 1
            _collect_rule_or_conclusion(step, triggered_rules, failed_conclusions)

    stats.by_source = dict(by_source.most_common())
    stats.by_kind = dict(by_kind.most_common())
    stats.by_verdict = dict(by_verdict.most_common())
    stats.by_status = dict(by_status.most_common())
    # Keep day rollup in chronological order so consumers can chart it.
    stats.by_day = dict(sorted(by_day.items()))
    stats.top_triggered_rules = [
        {"label": label, "count": count}
        for label, count in triggered_rules.most_common(top_n)
    ]
    stats.top_failed_conclusions = [
        {"label": label, "count": count}
        for label, count in failed_conclusions.most_common(top_n)
    ]
    stats.mean_confidence = (
        confidence_total / confidence_count if confidence_count > 0 else None
    )
    return stats


def _collect_rule_or_conclusion(
    step: ReasoningStep,
    triggered_rules: Counter[str],
    failed_conclusions: Counter[str],
) -> None:
    # "Triggered rules" = rule_check/constraint steps in TRIGGERED or FAILED state.
    if step.kind in (StepKind.RULE_CHECK, StepKind.CONSTRAINT):
        if step.status in (StepStatus.TRIGGERED, StepStatus.FAILED):
            triggered_rules[step.label] += 1
    # "Failed conclusions" = conclusion steps in FAILED state.
    if step.kind is StepKind.CONCLUSION and step.status is StepStatus.FAILED:
        failed_conclusions[step.label] += 1


def _day_bucket(created_at: str) -> str | None:
    """Return the UTC date (YYYY-MM-DD) for an ISO-8601 string, or None."""
    raw = created_at.strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return dt.date().isoformat()


__all__: Sequence[str] = ("TraceStats", "compute_stats")
