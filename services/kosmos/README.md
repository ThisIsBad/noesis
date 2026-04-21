# Kosmos

Causal world model with Do-calculus for the Noesis AGI stack.

## MCP tools

| Tool | Purpose |
|------|---------|
| `add_causal_edge` | Register a directed `cause → effect` edge with a multiplicative strength weight. |
| `compute_intervention` | Compute downstream effect weights under `do(variable = value)`. |
| `counterfactual` | Return cumulative causal-path strength between two variables. |
| `query_causes` | Enumerate every variable with a direct edge into a given effect. |

All tools are exposed over FastMCP SSE and wrapped with Kairos tracing
spans via `kosmos.tracing.get_tracer().span(...)`.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | none | liveness probe |
| `/sse` | bearer | MCP SSE transport |
| `/messages/{session_id}` | bearer | MCP bidirectional channel |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `KOSMOS_SECRET` | yes | static bearer token required on `/sse` and `/messages/*` |
| `KOSMOS_ALLOWED_HOSTS` | yes | comma-separated DNS-rebinding allowlist (e.g. `kosmos.example.railway.app`) |
| `KOSMOS_LOG_LEVEL` | no | Python log level; defaults to `INFO` |
| `KOSMOS_TRACE_ENABLED` | no | set to `0`/`false` to disable Kairos span emission; defaults to on |
| `KAIROS_URL` | no | base URL of the Kairos tracing service; spans are no-ops if unset |
| `PORT` | no (Railway-injected) | HTTP listen port; defaults to `8000` |

## Run locally

```bash
cd services/kosmos
pip install -e ".[dev]"
KOSMOS_SECRET=dev KOSMOS_ALLOWED_HOSTS=localhost python -m kosmos.mcp_server_http
```

## Tests

```bash
pytest  # contract + core tests
```

CI matrix: Python 3.11 + 3.12, ruff, mypy --strict, Docker build.
