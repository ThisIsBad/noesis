FROM python:3.11-slim
WORKDIR /app

# ── UI client (not a Noesis service) ──────────────────────────────────────────
# Theoria is the human-facing visualizer for Noesis decision traces. It lives
# under ui/ because it's a reader over the data other services produce, not a
# cognitive-gap-closing service like Logos/Praxis/Telos.
#
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty),
#             Dockerfile Path = ui/theoria/Dockerfile
# Locally:   docker build -f ui/theoria/Dockerfile -t theoria .
#
# Zero-dep at runtime; pip install is purely for the entry-point script.
COPY ui/theoria/pyproject.toml .
COPY ui/theoria/src/ src/
RUN pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
# Railway supplies PORT — fall back to 8000 when run elsewhere.
# THEORIA_SECRET: if set, bearer-token auth is required on every non-health,
#                 non-static, non-stream request. Leave unset for local dev.
ENV THEORIA_HOST=0.0.0.0
EXPOSE 8000
CMD ["sh", "-c", "theoria serve --host 0.0.0.0 --port ${PORT:-8000}"]
