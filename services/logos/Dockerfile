FROM python:3.11-slim
WORKDIR /app

# ── Kairos tracing client ─────────────────────────────────────────────────────
# Build context MUST be the repo root (same as mneme/telos/praxis).
# In Railway: Settings → Build → Root Directory = (empty),
#             Dockerfile Path = services/logos/Dockerfile
# Locally:   docker build -f services/logos/Dockerfile -t logos .
COPY kairos/ /kairos
RUN pip install /kairos

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/logos/pyproject.toml .
COPY services/logos/src/ src/
RUN pip install ".[http]"

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["python", "-m", "logos.mcp_server_http"]
