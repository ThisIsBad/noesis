"""ALFWorld-style benchmark harness for Praxis.

This package provides a CI-runnable scaffold that mirrors the ALFWorld
contract (text-based task environment, episode loop, success/failure
reward) without pulling in TextWorld / Lua / heavyweight game-engine
dependencies. A real ALFWorld environment can plug in later behind the
``Environment`` Protocol.

Acceptance targets (from docs/ROADMAP.md, Praxis Stage 3):
    - ALFWorld success rate >= 50%
    - Backtrack-recovery >= 50% on 50 injected step-failures
    - Plan depth <= 8 without tool hallucination
"""
from .env import MockAlfworldEnv, Task, build_default_suite, build_stage3_suite
from .memory_suite import build_memory_suite
from .metrics import BenchmarkMetrics, EpisodeResult
from .praxis_planner import PraxisCorePlanner
from .runner import Planner, ScriptedPlanner, run_episode, run_suite

__all__ = [
    "BenchmarkMetrics",
    "EpisodeResult",
    "MockAlfworldEnv",
    "Planner",
    "PraxisCorePlanner",
    "ScriptedPlanner",
    "Task",
    "build_default_suite",
    "build_memory_suite",
    "build_stage3_suite",
    "run_episode",
    "run_suite",
]
