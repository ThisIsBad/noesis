# Techne

Verified skill library and strategy reuse for the Noesis AGI stack.

## MCP tools

| Tool | Purpose |
|------|---------|
| `store_skill` | Register a reusable skill, optionally backed by a Logos `ProofCertificate` that marks it verified. |
| `retrieve_skill` | Return the top-k skills matching a task description, ordered by success rate, with optional verified-only filter. |
| `record_use` | Update a skill's rolling success rate after it runs. |

All tools are exposed over FastMCP SSE and wrapped with Kairos tracing
spans via `techne.tracing.get_tracer().span(...)`.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | none | liveness probe |
| `/sse` | bearer | MCP SSE transport |
| `/messages/{session_id}` | bearer | MCP bidirectional channel |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `TECHNE_SECRET` | yes | static bearer token required on `/sse` and `/messages/*` |
| `TECHNE_ALLOWED_HOSTS` | yes | comma-separated DNS-rebinding allowlist (e.g. `techne.example.railway.app`) |
| `TECHNE_LOG_LEVEL` | no | Python log level; defaults to `INFO` |
| `TECHNE_TRACE_ENABLED` | no | set to `0`/`false` to disable Kairos span emission; defaults to on |
| `KAIROS_URL` | no | base URL of the Kairos tracing service; spans are no-ops if unset |
| `PORT` | no (Railway-injected) | HTTP listen port; defaults to `8000` |

## Run locally

```bash
cd services/techne
pip install -e ".[dev]"
TECHNE_SECRET=dev TECHNE_ALLOWED_HOSTS=localhost python -m techne.mcp_server_http
```

## Tests

```bash
pytest  # contract + core tests
```

CI matrix: Python 3.11 + 3.12, ruff, mypy --strict, Docker build.
