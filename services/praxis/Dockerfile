FROM python:3.11-slim
WORKDIR /app

# Build context must be the repo root (Railway: Root Directory = /)
#
# If this COPY fails with "schemas: not found", your build context is wrong.
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos tracing client ─────────────────────────────────────────────────────
COPY kairos/ /kairos
RUN pip install /kairos

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/praxis/pyproject.toml .
COPY services/praxis/src/ src/
# Strip the file:// URL from noesis-schemas dep — it's already installed above.
# The file:// reference is only needed for local editable installs.
RUN sed -i 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' pyproject.toml && pip install .

# ── Runtime ───────────────────────────────────────────────────────────────────
RUN mkdir -p /data
ENV PRAXIS_DATA_DIR=/data
EXPOSE 8000
CMD python -m praxis.mcp_server_http
