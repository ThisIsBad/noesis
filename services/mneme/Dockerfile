FROM python:3.11-slim
WORKDIR /app

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty), Dockerfile Path = services/mneme/Dockerfile
# Locally:   docker build -f services/mneme/Dockerfile -t mneme .
#
# If this COPY fails with "schemas: not found", your build context is wrong.
COPY schemas/ /schemas
RUN pip install /schemas

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/mneme/pyproject.toml .
COPY services/mneme/src/ src/
RUN pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
RUN mkdir -p /data
ENV MNEME_DATA_DIR=/data
EXPOSE 8000
CMD python -m mneme.mcp_server_http
