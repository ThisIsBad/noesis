"""Theoria — decision-logic visualization for the Noesis ecosystem.

Theoria (θεωρία, "contemplation / viewing") ingests structured
reasoning traces from other Noesis services (Logos policy decisions,
Praxis plan trees, Telos goal-drift checks, Z3 proofs, ...) and renders
them as an interactive reasoning graph in a browser.
"""

from theoria.models import (
    DecisionTrace,
    ReasoningStep,
    StepKind,
    StepStatus,
    Edge,
    Outcome,
)

__all__ = [
    "DecisionTrace",
    "ReasoningStep",
    "StepKind",
    "StepStatus",
    "Edge",
    "Outcome",
]

__version__ = "0.1.0"
