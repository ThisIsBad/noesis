FROM python:3.11-slim
WORKDIR /app

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root (same convention as services/*).
# In Railway: Settings → Build → Root Directory = (empty),
#             Dockerfile Path = kairos/Dockerfile
# Locally:   docker build -f kairos/Dockerfile -t kairos .
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos package ────────────────────────────────────────────────────────────
COPY kairos/pyproject.toml .
COPY kairos/src/ src/
RUN sed -i 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' pyproject.toml && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
# FastAPI app at kairos.mcp_server_http:app — span sink + query API.
# Railway supplies PORT; fall back to 8000 elsewhere.
EXPOSE 8000
CMD ["sh", "-c", "uvicorn kairos.mcp_server_http:app --host 0.0.0.0 --port ${PORT:-8000}"]
