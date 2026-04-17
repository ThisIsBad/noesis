FROM python:3.11-slim
WORKDIR /app

# ── Service ───────────────────────────────────────────────────────────────────
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty), Dockerfile Path = services/logos/Dockerfile
# Locally:   docker build -f services/logos/Dockerfile -t logos .
COPY services/logos/pyproject.toml .
COPY services/logos/src/ src/
RUN pip install --no-cache-dir ".[http]"

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["python", "-m", "logos.mcp_server_http"]
