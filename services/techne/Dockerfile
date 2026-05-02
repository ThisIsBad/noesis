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

# ── Shared HTTP clients + test/auth helpers (bearer middleware, persistence) ──
COPY clients/ /clients
RUN pip install /clients

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/techne/pyproject.toml .
COPY services/techne/src/ src/
# Strip the file:// URL from noesis-schemas dep — it's already installed above.
RUN sed -i 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' pyproject.toml && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
# Techne now has durable state (SQLite + ChromaDB). Railway must mount a
# volume at $TECHNE_DATA_DIR (default /data) for persistence across deploys;
# alternatively set TECHNE_DATABASE_URL=sqlite:///<path> to override the
# SQLite location (Chroma still uses <TECHNE_DATA_DIR>/techne_chroma).
EXPOSE 8080
CMD python -m techne.mcp_server_http
