FROM python:3.11-slim
WORKDIR /app

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root (same as mneme/telos/praxis).
# In Railway: Settings → Build → Root Directory = (empty),
#             Dockerfile Path = services/logos/Dockerfile
# Locally:   docker build -f services/logos/Dockerfile -t logos .
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos tracing client ─────────────────────────────────────────────────────
COPY kairos/ /kairos
RUN pip install /kairos

# ── Shared service clients (noesis-clients: bearer_middleware, ...) ───────────
COPY clients/ /clients
RUN pip install /clients

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/logos/pyproject.toml .
COPY services/logos/src/ src/
# Strip file:// URLs from shared-package deps — they're already installed above.
RUN sed -i \
    -e 's|noesis-clients @ file://[^"]*|noesis-clients|g' \
    pyproject.toml \
 && pip install ".[http]"

# ── Runtime ───────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["python", "-m", "logos.mcp_server_http"]
