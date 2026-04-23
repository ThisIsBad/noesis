# Persistence — current state and migration path

> **Status: 2026-04-23.** Written as part of Tier-3 T3.5 preparation
> in [`docs/architect-review-2026-04-23.md`](../architect-review-2026-04-23.md).

## Current state

Two services have durable state:

| Service | Storage |
|---------|---------|
| **Mneme** | SQLite (`mneme.db`) + ChromaDB (persistent client at `<DATA_DIR>/mneme_chroma`) |
| **Praxis** | SQLite (`praxis.db`) |

Both read a service-specific env var:

```
MNEME_DATA_DIR   (default /data)   → Mneme SQLite + Chroma live here
PRAXIS_DATA_DIR  (default /data)   → Praxis SQLite lives here
```

Every other service (Logos, Telos, Episteme, Kosmos, Empiria, Techne)
is in-memory today. The dict-of-X MVPs for the three thinnest services
(Kosmos, Empiria, Techne) will gain persistence as they're promoted
toward production — see the T3.9 triage in the architect review.

## Why this needs changing

The directory-plus-filename convention can't describe anything other
than local SQLite. When we eventually need:

- **Postgres** (T3.5) for HA / horizontal scale,
- **pgvector** to replace the Chroma store,
- a **test fixture** pointing at an ephemeral SQLite file,

… we're staring down a 9-way-inconsistent env-var fork. Better to
stabilise the shape *before* that happens.

## The convention (prep landed, adoption pending)

Each service should, over time, move to reading a single
**`<SVC>_DATABASE_URL`** env var in SQLAlchemy style:

```
MNEME_DATABASE_URL   = sqlite:////data/mneme.db
PRAXIS_DATABASE_URL  = sqlite:////data/praxis.db
```

Four slashes means absolute POSIX path; three slashes means relative.
Non-SQLite URLs (`postgresql://…`) are rejected today — the Postgres
handling path lands with T3.5. The point of defining the shape now is
that the **env-var flip is a one-line deploy change** when the code
catches up.

## Helper — `noesis_clients.persistence.resolve_sqlite_path`

Shared helper in `clients/src/noesis_clients/persistence.py`:

```python
from noesis_clients.persistence import resolve_sqlite_path

db_path = resolve_sqlite_path(
    url_env="MNEME_DATABASE_URL",
    data_dir_env="MNEME_DATA_DIR",
    default_data_dir="/data",
    default_filename="mneme.db",
)
```

Resolution order:

1. If `MNEME_DATABASE_URL=sqlite:///<path>` is set, return `<path>`.
2. If the URL has a non-SQLite scheme, raise — don't silently fall back.
3. Otherwise read `MNEME_DATA_DIR` (default `/data`) + join
   `mneme.db` onto it.

8 contract tests in `clients/tests/test_persistence.py` pin the
behaviour — URL precedence, whitespace tolerance, fallback chain,
unsupported-scheme rejection.

## Adoption checklist

- [x] Helper + contract tests landed (2026-04-23).
- [x] Docs — this file.
- [ ] Mneme migration — one-line replace of the `os.path.join` call
      with `resolve_sqlite_path(...)`. **Deferred:** Mneme is
      production-deployed and the sweep belongs on its own PR with
      explicit review. Railway env config needs a simultaneous
      update (either keep `MNEME_DATA_DIR` + add nothing, or set
      `MNEME_DATABASE_URL` and retire `MNEME_DATA_DIR`).
- [ ] Praxis migration — same pattern; MVP status means lower risk
      than Mneme.
- [ ] New services adopt the URL form from day one — no need to
      support the `<SVC>_DATA_DIR` fallback.

## Forward path — when T3.5 lands

When the decision to go Postgres is made, this module grows a sibling
`resolve_database_url` that parses `postgresql://` URLs and returns a
DSN / connection string. Services import the new function instead of
`resolve_sqlite_path`. The env var already carries the DSN, so the
deploy rolls forward in-place:

```
# Before:
MNEME_DATABASE_URL=sqlite:////data/mneme.db

# After (same var name):
MNEME_DATABASE_URL=postgresql://mneme_user:pw@pg.railway.internal/mneme
```

Zero application-code change for the switchover beyond the import, and
callers that already use `resolve_sqlite_path` get a clear failure at
boot time if they forgot to update their resolver import.

## What's out of scope

- **ChromaDB.** Vector storage stays behind its own `<SVC>_CHROMA_PATH`
  convention for now. When pgvector arrives it joins the same
  `<SVC>_DATABASE_URL` knob.
- **Connection pooling.** SQLite doesn't need it; we'll add the helper
  when Postgres is real.
- **Migrations.** Out of scope for this helper. Services own their
  schema evolution today (Mneme via `_setup_schema`, Praxis via the
  same pattern). Migration tooling lands when Postgres arrives.
