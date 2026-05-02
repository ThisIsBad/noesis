"""Goal stability and drift detection.

Drift detection scores a proposed action's semantic proximity to the
*forbidding* postconditions of every active GoalContract. A "forbidding"
postcondition is one phrased as a prohibition — "never delete user
data", "do not exfiltrate secrets", "avoid destructive operations" —
from which we strip the negation to obtain the target concept the goal
wants to prevent. The action is flagged whenever its similarity to any
such target clears ``_CONFLICT_THRESHOLD``; ``drift_score`` is the
fraction of active goals that got flagged.

The similarity function is pluggable via the ``SimilarityFn`` protocol
so a sentence-transformer (or cross-service Mneme retrieval) can
replace the lexical default without changing the MCP surface.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from datetime import datetime
from typing import Protocol

from noesis_schemas import GoalConstraint, GoalContract

_NEGATION_PATTERN = re.compile(
    r"\b(?:do\s+not|does\s+not|don't|doesn't|never|no(?:t)?|avoid|"
    r"prevent|forbid|refuse|disallow|reject)\b",
    flags=re.IGNORECASE,
)

_STOPWORDS = frozenset(
    {
        "a",
        "an",
        "the",
        "to",
        "of",
        "in",
        "on",
        "at",
        "for",
        "with",
        "and",
        "or",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "that",
        "this",
        "it",
        "from",
        "by",
        "as",
        "into",
        "onto",
        "out",
        "up",
        "down",
        "over",
        "under",
        "will",
        "shall",
        "should",
        "would",
        "could",
        "may",
        "might",
        "can",
        "i",
        "you",
        "he",
        "she",
        "we",
        "they",
        "me",
        "them",
        "us",
        "my",
        "your",
        "his",
        "her",
        "our",
        "their",
        "its",
    }
)

_TOKEN_PATTERN = re.compile(r"[a-z0-9']+", flags=re.IGNORECASE)

_CONFLICT_THRESHOLD = 0.3
"""Jaccard overlap above which an action is treated as conflicting with a
forbidding postcondition. Tuned to flag obvious overlap ("delete user data"
vs "delete the user's data") while ignoring stopword co-occurrence."""


class SimilarityFn(Protocol):
    """Symmetric similarity in [0, 1]. Inject a real embedder to upgrade."""

    def __call__(self, a: str, b: str) -> float: ...


def _tokens(text: str) -> set[str]:
    return {
        t.lower() for t in _TOKEN_PATTERN.findall(text) if t.lower() not in _STOPWORDS
    }


def _token_overlap_similarity(a: str, b: str) -> float:
    """Jaccard similarity over content-word token sets.

    Lexical-only — flags "delete user data" against "delete user records"
    (0.5) but misses "erase customer info" (0.0). Good enough to beat the
    substring stub; a sentence-transformer should replace it for true
    semantic drift detection.
    """
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _strip_negation(text: str) -> str:
    """Collapse negation markers so "do not delete X" → "delete X".

    The postcondition *says* what must not happen; the action *describes*
    what will happen. To compare them meaningfully we need both sides on
    the same polarity — strip the negation from the postcondition."""
    return _NEGATION_PATTERN.sub(" ", text).strip()


def _is_forbidding(pc: GoalConstraint) -> bool:
    return bool(_NEGATION_PATTERN.search(pc.description))


class AlignmentResult:
    def __init__(
        self,
        aligned: bool,
        drift_score: float,
        reason: str | None = None,
    ) -> None:
        self.aligned = aligned
        self.drift_score = drift_score
        self.reason = reason


class TelosCore:
    def __init__(self, similarity_fn: SimilarityFn | None = None) -> None:
        self._goals: dict[str, GoalContract] = {}
        self._drift_log: list[tuple[datetime, str, float]] = []
        self._similarity = similarity_fn or _token_overlap_similarity

    def register(self, contract: GoalContract) -> GoalContract:
        self._goals[contract.goal_id] = contract
        return contract

    def check_alignment(self, action_description: str) -> AlignmentResult:
        active = [g for g in self._goals.values() if g.active]
        if not active:
            return AlignmentResult(aligned=True, drift_score=0.0)

        conflicts: list[tuple[GoalContract, GoalConstraint, float]] = []
        for goal in active:
            best = self._best_forbidding_match(action_description, goal.postconditions)
            if best is not None:
                conflicts.append((goal, best[0], best[1]))

        drift = len(conflicts) / len(active)
        reason = self._format_reason(conflicts)
        self._drift_log.append((datetime.utcnow(), action_description, drift))
        return AlignmentResult(
            aligned=drift == 0.0,
            drift_score=drift,
            reason=reason,
        )

    def _best_forbidding_match(
        self, action: str, postconditions: Iterable[GoalConstraint]
    ) -> tuple[GoalConstraint, float] | None:
        """Highest-similarity forbidding postcondition above threshold, if any."""
        best: tuple[GoalConstraint, float] | None = None
        for pc in postconditions:
            if not _is_forbidding(pc):
                continue
            score = self._similarity(action, _strip_negation(pc.description))
            if score >= _CONFLICT_THRESHOLD and (best is None or score > best[1]):
                best = (pc, score)
        return best

    @staticmethod
    def _format_reason(
        conflicts: list[tuple[GoalContract, GoalConstraint, float]],
    ) -> str | None:
        if not conflicts:
            return None
        # Most-similar conflict first; caller sees the strongest signal.
        top = max(conflicts, key=lambda c: c[2])
        goal, pc, score = top
        return (
            f"conflicts with goal '{goal.description}' "
            f"postcondition '{pc.description}' (similarity={score:.2f})"
        )

    def get_drift_score(self, window: int = 20) -> float:
        recent = self._drift_log[-window:]
        if not recent:
            return 0.0
        return sum(d for _, _, d in recent) / len(recent)

    def list_active(self) -> list[GoalContract]:
        return [g for g in self._goals.values() if g.active]
