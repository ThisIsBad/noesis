FROM python:3.11-slim
WORKDIR /app

# Build context must be the repo root (Railway: Root Directory = /)
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
COPY services/praxis/pyproject.toml .
COPY services/praxis/src/ src/
# Strip file:// URLs from shared-package deps — they're already installed above.
# The file:// references are only needed for local editable installs.
RUN sed -i \
    -e 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' \
    -e 's|noesis-clients @ file://[^"]*|noesis-clients|g' \
    pyproject.toml \
 && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
RUN mkdir -p /data
ENV PRAXIS_DATA_DIR=/data
EXPOSE 8080
CMD python -m praxis.mcp_server_http
