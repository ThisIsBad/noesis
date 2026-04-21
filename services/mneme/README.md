# Mneme

Persistent episodic and semantic memory for the Noesis AGI stack.

## MCP tools

| Tool | Purpose |
|------|---------|
| `store_memory` | Store an episodic or semantic memory with confidence, tags, source, and optional Logos `ProofCertificate`. |
| `retrieve_memory` | Semantic search over stored memories by query, top-k, with a minimum-confidence filter. |
| `forget_memory` | Delete a memory and record the reason in the audit log. |
| `list_proven_beliefs` | Enumerate memories backed by a valid Logos `ProofCertificate`. |
| `consolidate_memories` | Merge near-duplicate memories under a cosine-distance threshold, keeping the higher-confidence copy. |

All tools are exposed over FastMCP SSE and wrapped with Kairos tracing
spans via `mneme.tracing.get_tracer().span(...)`.

## Endpoints

| Path | Auth | Purpose |
|------|------|---------|
| `GET /health` | none | liveness probe |
| `/sse` | bearer | MCP SSE transport |
| `/messages/{session_id}` | bearer | MCP bidirectional channel |

## Environment variables

| Variable | Required | Purpose |
|----------|----------|---------|
| `MNEME_SECRET` | yes | static bearer token required on `/sse` and `/messages/*` |
| `MNEME_ALLOWED_HOSTS` | yes | comma-separated DNS-rebinding allowlist (e.g. `mneme.example.railway.app`) |
| `MNEME_DATA_DIR` | no | on-disk root for `mneme.db` (SQLite) and `chroma/` (vector store); defaults to `/data` |
| `MNEME_LOG_LEVEL` | no | Python log level; defaults to `INFO` |
| `MNEME_TRACE_ENABLED` | no | set to `0`/`false` to disable Kairos span emission; defaults to on |
| `KAIROS_URL` | no | base URL of the Kairos tracing service; spans are no-ops if unset |
| `PORT` | no (Railway-injected) | HTTP listen port; defaults to `8000` |

## Run locally

```bash
cd services/mneme
pip install -e ".[dev]"
MNEME_SECRET=dev MNEME_ALLOWED_HOSTS=localhost python -m mneme.mcp_server_http
```

## Tests

```bash
pytest  # contract + core tests
```

CI matrix: Python 3.11 + 3.12, ruff, mypy --strict, Docker build.
