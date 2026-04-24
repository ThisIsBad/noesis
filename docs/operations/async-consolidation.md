# Async consolidation — design doc for T3.7

> **Status: design draft, 2026-04-23.** Written as part of Tier-3
> T3.7 in [`docs/architect-review-2026-04-23.md`](../architect-review-2026-04-23.md).
> Not implemented. Mneme is production-deployed; the refactor needs
> your eyes before it goes in.

## Problem

`MnemeCore.consolidate(similarity_threshold)` is a synchronous loop
over every row in the `memories` table, each iteration running a
ChromaDB `query()` + a merge-or-skip decision. At the current scale
(< 1 k memories) it finishes in well under a second and the
`consolidate_memories` MCP tool completes fast enough that nobody
notices.

At the ROADMAP's Stage-4 target — 100 k memories with daily
consolidation — the same implementation is a ~30-60 s blocking call.
That's well past the default MCP client timeout (most HTTP clients
timeout at 30 s) and past any user's patience for a "fire and
forget" agent call. The current synchronous contract **will break**
as Mneme scales.

## Architect's decision

From the T3.7 discussion in the review: **don't add a job queue.**
Celery / Dramatiq / Temporal add Redis + worker processes + a
distributed-systems failure model to solve what's ultimately a
single-service, single-call problem.

The right shape is **in-process asyncio.create_task** with a
polling status endpoint. Treat consolidation as a long-running
HTTP operation; same pattern as any REST API with a `task_id`.
Survives at the current scale, and when we do eventually need
cross-restart durability, **that's the moment** to add a queue —
not before.

## The shape

### Two new MCP tools

```
consolidate_memories_async(
    similarity_threshold: float = 0.5,
) -> {"task_id": "...", "started_at": "..."}

get_consolidation_status(task_id: str) -> {
    "task_id": "...",
    "status": "pending" | "running" | "complete" | "failed",
    "started_at": "...",
    "completed_at": "..." | None,
    "merged_count": 42,      # when complete
    "error": "..." | None,   # when failed
}
```

### Back-compat: keep the existing tool

`consolidate_memories(similarity_threshold)` stays as-is, **runs
synchronously**, and returns the merged count. It's fine for small
stores and for callers that want the current contract. The new async
tool is opt-in; the sync tool doesn't disappear.

### Storage of task state

Task state lives in a new `consolidation_tasks` SQLite table owned
by Mneme:

```sql
CREATE TABLE consolidation_tasks (
    task_id      TEXT PRIMARY KEY,
    status       TEXT NOT NULL,
    started_at   TEXT NOT NULL,
    completed_at TEXT,
    merged_count INTEGER,
    error        TEXT,
    params_json  TEXT NOT NULL
);
```

**Survival across restart:** A service restart mid-task transitions
the row from `running` to `failed` with `error="service restarted"`
on boot (a `WHERE status='running'` sweep). The client's next poll
sees the failure and can retry. *That is the explicit limitation
relative to a real job queue:* durability only in the sense that
started tasks are reflected in the DB, not that work survives a
crash.

### Cancellation (v1: no)

Explicit `cancel_consolidation(task_id)` deferred to v2. In v1 the
task runs to completion regardless. Acceptable because consolidation
is idempotent-ish (every run just merges whatever near-duplicates
exist now).

### Concurrency (v1: one task at a time)

The `consolidate_memories_async` tool checks the
`consolidation_tasks` table for a row with `status IN ('pending',
'running')` and refuses to start a second task — returns the
existing `task_id` instead. Simple, avoids races on the memory store.

## Implementation plan

1. **Table + migration.** Add `consolidation_tasks` to
   `MnemeCore._setup_schema` (idempotent CREATE).
2. **`MnemeCore.start_consolidation(similarity_threshold)`** —
   writes a row, returns `task_id`.
3. **`MnemeCore.run_consolidation(task_id)`** — called from the
   async task body; marks `running` → runs existing `consolidate()`
   logic → marks `complete` or `failed`.
4. **`MnemeCore.get_consolidation_status(task_id)`** — SELECT by id.
5. **Boot-time cleanup:** on `MnemeCore.__init__`, `UPDATE
   consolidation_tasks SET status='failed', error='service restart'
   WHERE status='running'`. Runs before any tool is served.
6. **MCP tools:** `consolidate_memories_async` dispatches
   `asyncio.create_task(core.run_consolidation(tid))` inside a
   FastMCP tool handler and returns the `task_id`.
   `get_consolidation_status` just calls the core.
7. **Tests:** end-to-end pytest covering happy path,
   concurrent-request dedup, boot-time cleanup of stuck tasks,
   failure surfacing.

Estimated effort: ~1 day including tests. Touches only Mneme —
contract additions, not changes.

## Why this is deferred

Mneme is production-deployed. The refactor wants:

- A dedicated PR so reviewers can eyeball the schema change.
- Coordinated Railway env-config verification (nothing to change,
  but worth a line of the PR description saying so).
- A post-deploy smoke check: the existing `consolidate_memories`
  tool must still work unchanged. I have unit tests for that, but
  touching production without the author's review is wrong.

## What gets sync consolidation to 100 k anyway

The O(N²) pattern (row-loop × Chroma query) is what blows up. A
smarter consolidate has:

- Batched Chroma query (one call, all rows).
- Union-find on the similarity pairs.
- Single-transaction delete of the losers.

That's a separate optimisation PR and an order-of-magnitude improvement
on its own — would push the "MCP call actually blocks" horizon from
10 k memories to 1 M. Worth considering **before** the async refactor:
if the sync path is fast enough at realistic scale, the async tool
becomes a nice-to-have rather than a forcing need.

**Recommendation for sequencing:**

1. Profile `consolidate()` at 10 k and 100 k synthetic memories. If
   it's under 5 s at 100 k, park T3.7.
2. If it's not, optimise the sync path first (batched query +
   union-find). Profile again.
3. If *that* still doesn't give us headroom, ship the async shape
   above.

This is the kind of call that's cheaper to make with a profile than
without one.

## Open questions

1. **Default similarity threshold.** `consolidate` defaults to 0.15
   in the core and 0.5 at the MCP surface — inconsistent. Worth
   reconciling before the async tool lands so we don't enshrine the
   mismatch.
2. **Rate limiting.** Should the async tool accept multiple
   concurrent requests for *different* parameter sets? v1 says no
   (one task at a time, period); a stricter reading of "idempotent
   consolidation" says yes. No strong opinion yet.
3. **TTL on task rows.** Do we keep rows forever, or sweep old ones
   after 30 days? Affects the `consolidation_tasks` table size at
   scale.
