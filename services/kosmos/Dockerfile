FROM python:3.11-slim
WORKDIR /app

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty), Dockerfile Path = services/kosmos/Dockerfile
# Locally:   docker build -f services/kosmos/Dockerfile -t kosmos .
#
# If this COPY fails with "schemas: not found", your build context is wrong.
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos tracing client ─────────────────────────────────────────────────────
COPY kairos/ /kairos
RUN pip install /kairos

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/kosmos/pyproject.toml .
COPY services/kosmos/src/ src/
# Strip the file:// URL from noesis-schemas dep — it's already installed above.
RUN sed -i 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' pyproject.toml && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD python -m kosmos.mcp_server_http
