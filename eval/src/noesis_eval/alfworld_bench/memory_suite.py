"""Mneme-favouring task suite: cross-episode memory is the only path.

The stage3 suite (50 recovery tasks) stresses Praxis's backtrack-plan
machinery but doesn't differentiate memory-armed agents from
memory-blind ones: everything needed for each task is visible in the
initial observation. A positive delta on stage3 could be "Noesis
helps" or "MCP tools reduce prompt confusion" — the signal is
ambiguous.

This suite is built from **linked pairs** of tasks. A *plant* task
puts a nonce-shaped fact in the initial observation (e.g.
``"The vault code is K42-N9T."``) and asks the agent to do an
unrelated physical action. A *query* task ships seven tasks later,
asks for the nonce, and the env only accepts the exact nonce string
as the terminating action.

Cross-episode memory is the ONLY path from plant to query:

* MockAlfworldEnv resets per task — history inside a single episode
  can't cross the gap.
* The MCPAgent prompt carries only the within-episode history, not
  observations from prior tasks. Claude alone has zero access to the
  earlier observation on the query turn.
* A Mneme-equipped treatment can ``store_memory`` during the plant,
  then ``retrieve_memory`` during the query. The baseline (no Mneme)
  has to guess a random-looking nonce; expected baseline success on
  a query task is effectively 0.

Run-pollution note: nonces here are hard-coded, not per-run random.
That means a second A/B run sees the same task_ids and the pooled
``ab history`` stays meaningful across runs. The tradeoff is that
memories planted in run N survive into run N+1 on the shared Mneme
— which is fine, because the baseline can't reach them either, so
it's a *ceiling* advantage for treatment, not a confounder.

Design constraints followed:

* Plant tasks are solvable by any agent (trivial physical goal) —
  the Mneme store happens as a side effect. Failing to store just
  bites later.
* Query tasks have a single canonical action: the exact nonce. A
  baseline agent has essentially 0% chance of guessing.
* Task IDs use a ``mem_<phase>_<pair>`` convention so the
  planted/queried pairing is visible in the JSONL records and
  in ``ab diff`` output.

Keep this suite small (6 tasks = 3 pairs) until the first real
measurement tells us whether the signal we expect shows up.
"""

from __future__ import annotations

from .env import Task

# Each pair is ``(nonce, plant_observation_suffix, plant_physical_goal,
# plant_canonical_action, query_goal, query_observation)``. The nonce
# is baked into both the plant observation and the query canonical
# plan, so only memory bridges them.
_PAIRS: list[tuple[str, str, str, str, str, str]] = [
    (
        "K42-N9T",
        "You overhear the vault code is K42-N9T. ",
        "walk from the lobby to the conference room",
        "walk to conference room",
        "enter the vault — the keypad waits for the code you overheard earlier",
        "A keypad glows at the vault door. Enter the code you heard in the lobby.",
    ),
    (
        "AZURE-17",
        "A tag reads: the sample cabinet combination is AZURE-17. ",
        "tidy the lab bench by putting the flasks back on the shelf",
        "place flasks on shelf",
        "unlock the sample cabinet — the combination is what the tag said in the lab",
        "The sample cabinet is locked; its combination was printed on the tag you saw.",
    ),
    (
        "INV-2024-31B",
        "The janitor mentions that store-room crate INV-2024-31B "
        "holds the cleaning solvent. ",
        "deliver the envelope from reception to the mailroom",
        "deliver envelope to mailroom",
        "retrieve the cleaning solvent — the janitor named a specific crate",
        "The store-room has dozens of crates. Which crate holds the cleaning solvent?",
    ),
]


def build_memory_suite() -> list[Task]:
    """6-task Mneme-favouring suite: 3 plant + 3 query tasks, interleaved.

    The interleaving (plant 1 → plant 2 → plant 3 → query 1 → query 2
    → query 3) puts two other plants between each plant and its
    query, so a model that only recalls its most recent turn can't
    win via short-term memory alone. It has to genuinely persist
    across several tasks.
    """
    suite: list[Task] = []
    for i, (_nonce, obs_suffix, phys_goal, phys_action, _, _) in enumerate(_PAIRS):
        suite.append(
            Task(
                task_id=f"mem_plant_{i}",
                goal=phys_goal,
                initial_observation=obs_suffix + (f"To finish this task, {phys_goal}."),
                canonical_plan=(phys_action,),
            )
        )
    for i, (nonce, _, _, _, query_goal, query_obs) in enumerate(_PAIRS):
        suite.append(
            Task(
                task_id=f"mem_query_{i}",
                goal=query_goal,
                initial_observation=query_obs,
                canonical_plan=(nonce.lower(),),
            )
        )
    return suite


__all__ = ["build_memory_suite"]
