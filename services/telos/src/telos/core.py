from datetime import datetime

from noesis_schemas import GoalContract


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
    def __init__(self) -> None:
        self._goals: dict[str, GoalContract] = {}
        self._drift_log: list[tuple[datetime, str, float]] = []

    def register(self, contract: GoalContract) -> GoalContract:
        self._goals[contract.goal_id] = contract
        return contract

    def check_alignment(self, action_description: str) -> AlignmentResult:
        active = [g for g in self._goals.values() if g.active]
        if not active:
            return AlignmentResult(aligned=True, drift_score=0.0)

        # Stub: keyword-conflict heuristic.
        # Production: Logos z3_check per postcondition.
        action_lower = action_description.lower()
        conflicts = [
            g for g in active
            if any(
                pc.description.lower() in action_lower
                for pc in g.postconditions
                if "not" in pc.description.lower()
                or "prevent" in pc.description.lower()
            )
        ]
        drift = len(conflicts) / len(active)
        self._drift_log.append((datetime.utcnow(), action_description, drift))
        return AlignmentResult(aligned=drift == 0.0, drift_score=drift)

    def get_drift_score(self, window: int = 20) -> float:
        recent = self._drift_log[-window:]
        if not recent:
            return 0.0
        return sum(d for _, _, d in recent) / len(recent)

    def list_active(self) -> list[GoalContract]:
        return [g for g in self._goals.values() if g.active]
