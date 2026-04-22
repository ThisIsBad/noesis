FROM python:3.11-slim
WORKDIR /app

# Build tools needed by chromadb/hnswlib native extensions
RUN apt-get update && apt-get install -y --no-install-recommends gcc g++ && rm -rf /var/lib/apt/lists/*

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty), Dockerfile Path = services/mneme/Dockerfile
# Locally:   docker build -f services/mneme/Dockerfile -t mneme .
#
# If this COPY fails with "schemas: not found", your build context is wrong.
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos tracing client ─────────────────────────────────────────────────────
COPY kairos/ /kairos
RUN pip install /kairos

# ── Shared service clients (noesis-clients: LogosClient, …) ───────────────────
COPY clients/ /clients
RUN pip install /clients

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/mneme/pyproject.toml .
COPY services/mneme/src/ src/
# Strip file:// URLs from shared-package deps — they're already installed above.
# The file:// references are only needed for local editable installs.
RUN sed -i \
    -e 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' \
    -e 's|noesis-clients @ file://[^"]*|noesis-clients|g' \
    pyproject.toml \
 && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
RUN mkdir -p /data
ENV MNEME_DATA_DIR=/data
EXPOSE 8000
CMD python -m mneme.mcp_server_http
