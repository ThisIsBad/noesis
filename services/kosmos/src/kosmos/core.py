from typing import Any


class KosmosCore:
    """Causal graph with Do-calculus. Production: replace with pgmpy BayesianNetwork."""

    def __init__(self) -> None:
        # adjacency: cause -> {effect: weight}
        self._graph: dict[str, dict[str, float]] = {}

    def add_edge(self, cause: str, effect: str, strength: float = 1.0) -> None:
        self._graph.setdefault(cause, {})[effect] = strength

    def compute_intervention(self, variable: str, value: Any) -> dict[str, float]:
        """do(variable=value) — returns downstream effect scores."""
        downstream: dict[str, float] = {}
        if variable not in self._graph:
            return downstream
        queue = list(self._graph[variable].items())
        while queue:
            node, weight = queue.pop()
            if node not in downstream:
                downstream[node] = weight
                for child, child_weight in self._graph.get(node, {}).items():
                    queue.append((child, weight * child_weight))
        return downstream

    def query_causes(self, effect: str) -> list[str]:
        return [cause for cause, effects in self._graph.items() if effect in effects]

    def counterfactual(self, cause: str, effect: str) -> float | None:
        """Returns causal path strength from cause to effect, or None if no path."""
        if cause not in self._graph:
            return None
        downstream = self.compute_intervention(cause, True)
        return downstream.get(effect)
