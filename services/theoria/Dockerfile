FROM python:3.11-slim
WORKDIR /app

# ── Service ───────────────────────────────────────────────────────────────────
# Build context MUST be the repo root (same as other services).
# In Railway: Settings → Build → Root Directory = (empty),
#             Dockerfile Path = services/theoria/Dockerfile
# Locally:   docker build -f services/theoria/Dockerfile -t theoria .
#
# Theoria is zero-dep at runtime; we install it purely for the entrypoint
# script and proper package resolution.
COPY services/theoria/pyproject.toml .
COPY services/theoria/src/ src/
RUN pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
# Railway supplies PORT — fall back to 8000 when run elsewhere.
ENV THEORIA_HOST=0.0.0.0
EXPOSE 8000
CMD ["sh", "-c", "theoria serve --host 0.0.0.0 --port ${PORT:-8000}"]
