# Telos

Goal stability monitoring and drift detection for the Noesis AGI stack.

## MCP tools

| Tool | Purpose |
|------|---------|
| `register_goal` | Register a `GoalContract` that subsequent actions will be checked against. |
| `check_action_alignment` | Test whether a proposed action conflicts with any active goal; every call is appended to the drift log. |
| `get_drift_score` | Return the mean drift score over the last `window` alignment checks. |
| `list_active_goals` | Enumerate every currently-active `GoalContract`. |

All tools are exposed over FastMCP SSE and wrapped with Kairos tracing
spans via `telos.tracing.get_tracer().span(...)`.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | none | liveness probe |
| `/sse` | bearer | MCP SSE transport |
| `/messages/{session_id}` | bearer | MCP bidirectional channel |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `TELOS_SECRET` | yes | static bearer token required on `/sse` and `/messages/*` |
| `TELOS_ALLOWED_HOSTS` | yes | comma-separated DNS-rebinding allowlist (e.g. `telos.example.railway.app`) |
| `TELOS_LOG_LEVEL` | no | Python log level; defaults to `INFO` |
| `TELOS_TRACE_ENABLED` | no | set to `0`/`false` to disable Kairos span emission; defaults to on |
| `KAIROS_URL` | no | base URL of the Kairos tracing service; spans are no-ops if unset |
| `PORT` | no (Railway-injected) | HTTP listen port; defaults to `8000` |

## Run locally

```bash
cd services/telos
pip install -e ".[dev]"
TELOS_SECRET=dev TELOS_ALLOWED_HOSTS=localhost python -m telos.mcp_server_http
```

## Tests

```bash
pytest  # contract + core tests
```

CI matrix: Python 3.11 + 3.12, ruff, mypy --strict, Docker build.
