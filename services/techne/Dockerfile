FROM python:3.11-slim
WORKDIR /app

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty), Dockerfile Path = services/techne/Dockerfile
# Locally:   docker build -f services/techne/Dockerfile -t techne .
#
# If this COPY fails with "schemas: not found", your build context is wrong.
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos tracing client ─────────────────────────────────────────────────────
COPY kairos/ /kairos
RUN pip install /kairos

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/techne/pyproject.toml .
COPY services/techne/src/ src/
# Strip the file:// URL from noesis-schemas dep — it's already installed above.
RUN sed -i 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' pyproject.toml && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD python -m techne.mcp_server_http
