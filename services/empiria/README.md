# Empiria

Experience accumulation and lesson extraction for the Noesis AGI stack.

## MCP tools

| Tool | Purpose |
|------|---------|
| `record_experience` | Log a `(context, action, outcome)` triple plus a distilled lesson, with success flag and confidence. |
| `retrieve_lessons` | Return the top-k lessons most relevant to a new context, optionally scoped by domain. |
| `successful_patterns` | Return every recorded lesson whose `success` is true, optionally scoped by domain. |

All tools are exposed over FastMCP SSE and wrapped with Kairos tracing
spans via `empiria.tracing.get_tracer().span(...)`.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | none | liveness probe |
| `/sse` | bearer | MCP SSE transport |
| `/messages/{session_id}` | bearer | MCP bidirectional channel |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `EMPIRIA_SECRET` | yes | static bearer token required on `/sse` and `/messages/*` |
| `EMPIRIA_ALLOWED_HOSTS` | yes | comma-separated DNS-rebinding allowlist (e.g. `empiria.example.railway.app`) |
| `EMPIRIA_LOG_LEVEL` | no | Python log level; defaults to `INFO` |
| `EMPIRIA_TRACE_ENABLED` | no | set to `0`/`false` to disable Kairos span emission; defaults to on |
| `KAIROS_URL` | no | base URL of the Kairos tracing service; spans are no-ops if unset |
| `PORT` | no (Railway-injected) | HTTP listen port; defaults to `8000` |

## Run locally

```bash
cd services/empiria
pip install -e ".[dev]"
EMPIRIA_SECRET=dev EMPIRIA_ALLOWED_HOSTS=localhost python -m empiria.mcp_server_http
```

## Tests

```bash
pytest  # contract + core tests
```

CI matrix: Python 3.11 + 3.12, ruff, mypy --strict, Docker build.
