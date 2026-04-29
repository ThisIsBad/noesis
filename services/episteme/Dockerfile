FROM python:3.11-slim
WORKDIR /app

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty), Dockerfile Path = services/episteme/Dockerfile
# Locally:   docker build -f services/episteme/Dockerfile -t episteme .
#
# If this COPY fails with "schemas: not found", your build context is wrong.
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos tracing client ─────────────────────────────────────────────────────
COPY kairos/ /kairos
RUN pip install /kairos

# ── Shared service clients (bearer middleware, persistence helpers) ───────────
COPY clients/ /clients
RUN pip install /clients

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/episteme/pyproject.toml .
COPY services/episteme/src/ src/
# Strip file:// URLs from shared-package deps — they're already installed above.
RUN sed -i \
    -e 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' \
    -e 's|noesis-clients @ file://[^"]*|noesis-clients|g' \
    pyproject.toml \
 && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD python -m episteme.mcp_server_http
