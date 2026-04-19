"""Minimal text-based environment that mirrors ALFWorld's contract.

Each ``Task`` is a deterministic state-machine: the agent receives the
goal + observation, issues a textual action, and the env returns the
next observation, a reward, and a ``done`` flag. ``inject_failure_at``
forces the env to return a failure for a specific step index, used to
benchmark backtrack-recovery.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


@dataclass(frozen=True)
class Task:
    task_id: str
    goal: str
    initial_observation: str
    canonical_plan: tuple[str, ...]
    # Step index (0-based) at which the env should reject the canonical
    # action and demand an alternative. None disables injection.
    inject_failure_at: Optional[int] = None
    # Alternative actions accepted at the failure index. Empty tuple =
    # no recovery is possible (the episode will fail).
    recovery_actions: tuple[str, ...] = ()


@dataclass
class StepResult:
    observation: str
    reward: float
    done: bool
    info: dict[str, object] = field(default_factory=dict)


class MockAlfworldEnv:
    """In-memory deterministic env. One env instance per task.

    Contract mirrors ALFWorld's textworld interface:
        env.reset() -> observation: str
        env.step(action: str) -> StepResult
    """

    def __init__(self, task: Task) -> None:
        self.task = task
        self._cursor: int = 0
        self._injected_recovered: bool = False
        self._done: bool = False

    def reset(self) -> str:
        self._cursor = 0
        self._injected_recovered = False
        self._done = False
        return f"Goal: {self.task.goal}\n{self.task.initial_observation}"

    def step(self, action: str) -> StepResult:
        if self._done:
            raise RuntimeError("step() called after episode terminated")

        action = action.strip().lower()
        plan = self.task.canonical_plan
        idx = self._cursor

        # Failure injection: at the marked index, reject the canonical
        # action and force the agent to use a recovery action instead.
        injecting = (
            self.task.inject_failure_at == idx
            and not self._injected_recovered
        )
        if injecting:
            if action in {a.lower() for a in self.task.recovery_actions}:
                self._injected_recovered = True
                self._cursor += 1
                done = self._cursor >= len(plan)
                self._done = done
                return StepResult(
                    observation=f"Recovered. Next: {self._next_hint()}",
                    reward=1.0 if done else 0.0,
                    done=done,
                    info={"recovered": True},
                )
            options = list(self.task.recovery_actions) or ["(no recovery)"]
            return StepResult(
                observation=(
                    f"Action '{action}' failed. Try one of: {options}"
                ),
                reward=-1.0,
                done=False,
                info={"failed": True, "step": idx},
            )

        if idx < len(plan) and action == plan[idx].lower():
            self._cursor += 1
            done = self._cursor >= len(plan)
            self._done = done
            return StepResult(
                observation=(
                    f"Done. Goal '{self.task.goal}' achieved."
                    if done
                    else f"OK. Next: {self._next_hint()}"
                ),
                reward=1.0 if done else 0.0,
                done=done,
            )

        return StepResult(
            observation=f"Action '{action}' is not valid here.",
            reward=-1.0,
            done=False,
            info={"failed": True, "step": idx},
        )

    def _next_hint(self) -> str:
        if self._cursor >= len(self.task.canonical_plan):
            return "(complete)"
        return self.task.canonical_plan[self._cursor]


def build_default_suite() -> list[Task]:
    """Five hand-built tasks covering the success / failure / recovery axes.

    Two clean tasks (no injection), two with recoverable failures, one
    with an unrecoverable failure. Lets a runner exercise both nominal
    success rate and backtrack-recovery rate from a single suite.
    """
    return [
        Task(
            task_id="t1_apple_to_fridge",
            goal="put the apple in the fridge",
            initial_observation=(
                "You are in the kitchen. A table holds an apple. "
                "A closed fridge is nearby."
            ),
            canonical_plan=(
                "pick up apple",
                "open fridge",
                "put apple in fridge",
                "close fridge",
            ),
        ),
        Task(
            task_id="t2_book_to_shelf",
            goal="place the book on the shelf",
            initial_observation=(
                "You are in the study. A book lies on the desk. "
                "An empty shelf is on the wall."
            ),
            canonical_plan=(
                "pick up book",
                "walk to shelf",
                "place book on shelf",
            ),
        ),
        Task(
            task_id="t3_recover_locked_drawer",
            goal="retrieve the key from the drawer",
            initial_observation=(
                "You are in the office. A drawer is locked. A "
                "paperclip lies on the floor."
            ),
            canonical_plan=(
                "open drawer",
                "take key from drawer",
            ),
            inject_failure_at=0,
            recovery_actions=(
                "pick up paperclip",
                "pick paperclip and unlock drawer",
            ),
        ),
        Task(
            task_id="t4_recover_blocked_path",
            goal="reach the exit",
            initial_observation=(
                "You are in a hallway. A box blocks the door. "
                "An alternative side passage is visible."
            ),
            canonical_plan=(
                "walk through door",
                "exit building",
            ),
            inject_failure_at=0,
            recovery_actions=("take side passage",),
        ),
        Task(
            task_id="t5_unrecoverable_locked_room",
            goal="enter the vault",
            initial_observation=(
                "You are in a corridor. The vault door requires a "
                "biometric scan you cannot pass."
            ),
            canonical_plan=("open vault",),
            inject_failure_at=0,
            recovery_actions=(),
        ),
    ]
