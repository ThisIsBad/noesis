# Praxis

Hierarchical planning and Tree-of-Thoughts search for the Noesis AGI stack.

## MCP tools

| Tool | Purpose |
|------|---------|
| `decompose_goal` | Open a new plan for a goal, optionally as a sub-plan of an existing plan. |
| `evaluate_step` | Propose a candidate step; sibling alternatives enable Tree-of-Thoughts branching. |
| `commit_step` | Record a step's execution outcome; failures penalise the branch score. |
| `backtrack` | After a failure, surface pending sibling alternatives to failed steps. |
| `verify_plan` | Safety-check a plan before execution (Logos `GoalContract` stub). |
| `get_next_step` | Return the first `PENDING` step on the current best path. |
| `best_path` | Return the top-k highest-scoring root-to-leaf paths through the tree. |
| `get_plan` | Fetch a plan with its best path populated. |

All tools are exposed over FastMCP SSE and wrapped with Kairos tracing
spans via `praxis.tracing.get_tracer().span(...)`.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | none | liveness probe |
| `/sse` | bearer | MCP SSE transport |
| `/messages/{session_id}` | bearer | MCP bidirectional channel |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `PRAXIS_SECRET` | yes | static bearer token required on `/sse` and `/messages/*` |
| `PRAXIS_ALLOWED_HOSTS` | yes | comma-separated DNS-rebinding allowlist (e.g. `praxis.example.railway.app`) |
| `PRAXIS_DATA_DIR` | no | on-disk root for `praxis.db` (SQLite); defaults to `/data` |
| `PRAXIS_LOG_LEVEL` | no | Python log level; defaults to `INFO` |
| `PRAXIS_TRACE_ENABLED` | no | set to `0`/`false` to disable Kairos span emission; defaults to on |
| `KAIROS_URL` | no | base URL of the Kairos tracing service; spans are no-ops if unset |
| `PORT` | no (Railway-injected) | HTTP listen port; defaults to `8000` |

## Run locally

```bash
cd services/praxis
pip install -e ".[dev]"
PRAXIS_SECRET=dev PRAXIS_ALLOWED_HOSTS=localhost python -m praxis.mcp_server_http
```

## Tests

```bash
pytest  # contract + core tests
```

CI matrix: Python 3.11 + 3.12, ruff, mypy --strict, Docker build.
