# Episteme

Metacognition and uncertainty calibration for the Noesis AGI stack.

## MCP tools

| Tool | Purpose |
|------|---------|
| `log_prediction` | Record a claim and a confidence estimate to be resolved later. |
| `log_outcome` | Resolve a previously-logged prediction with the observed outcome. |
| `get_calibration` | Return ECE, Brier score, bias, and sharpness for resolved predictions (optionally scoped by domain). |
| `should_escalate` | Decide whether a decision at a given confidence should be handed off, using per-domain calibration bias. |

All tools are exposed over FastMCP SSE and wrapped with Kairos tracing
spans via `episteme.tracing.get_tracer().span(...)`.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | none | liveness probe |
| `/sse` | bearer | MCP SSE transport |
| `/messages/{session_id}` | bearer | MCP bidirectional channel |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `EPISTEME_SECRET` | yes | static bearer token required on `/sse` and `/messages/*` |
| `EPISTEME_ALLOWED_HOSTS` | yes | comma-separated DNS-rebinding allowlist (e.g. `episteme.example.railway.app`) |
| `EPISTEME_LOG_LEVEL` | no | Python log level; defaults to `INFO` |
| `EPISTEME_TRACE_ENABLED` | no | set to `0`/`false` to disable Kairos span emission; defaults to on |
| `KAIROS_URL` | no | base URL of the Kairos tracing service; spans are no-ops if unset |
| `PORT` | no (Railway-injected) | HTTP listen port; defaults to `8000` |

## Run locally

```bash
cd services/episteme
pip install -e ".[dev]"
EPISTEME_SECRET=dev EPISTEME_ALLOWED_HOSTS=localhost python -m episteme.mcp_server_http
```

## Tests

```bash
pytest  # contract + core tests
```

CI matrix: Python 3.11 + 3.12, ruff, mypy --strict, Docker build.
