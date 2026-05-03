FROM python:3.11-slim
WORKDIR /app

# ── Shared schemas ────────────────────────────────────────────────────────────
# Build context MUST be the repo root.
# In Railway: Settings → Build → Root Directory = (empty), Dockerfile Path = services/hegemonikon/Dockerfile
# Locally:   docker build -f services/hegemonikon/Dockerfile -t hegemonikon .
#
# If this COPY fails with "schemas: not found", your build context is wrong.
COPY schemas/ /schemas
RUN pip install /schemas

# ── Kairos tracing client ─────────────────────────────────────────────────────
COPY kairos/ /kairos
RUN pip install /kairos

# ── Shared service clients (bearer middleware, persistence helpers) ───────────
COPY clients/ /clients
RUN pip install /clients

# ── Theoria models reused for DecisionTrace + SVG renderer (vendored as path) ─
# Hegemonikon imports `theoria.models` to construct DecisionTrace objects and
# serves the renderer's static/app.js to the browser. We don't pip-install
# theoria — it's a stdlib zero-dep app — but we need its source on disk
# so PYTHONPATH can import the models module.
COPY ui/theoria/src/ /theoria_src/
ENV PYTHONPATH=/theoria_src

# ── Service ───────────────────────────────────────────────────────────────────
COPY services/hegemonikon/pyproject.toml .
COPY services/hegemonikon/src/ src/
# Strip file:// URLs from shared-package deps — they're already installed above.
RUN sed -i \
    -e 's|noesis-schemas @ file://[^"]*|noesis-schemas|g' \
    -e 's|noesis-clients @ file://[^"]*|noesis-clients|g' \
    pyproject.toml \
 && pip install .

# ── UI assets (chat shell + Theoria renderer reference) ───────────────────────
COPY ui/hegemonikon/ /app/ui/hegemonikon/

# ── Runtime ───────────────────────────────────────────────────────────────────
# Hegemonikon reads NOESIS_<SVC>_URL and NOESIS_<SVC>_SECRET for all 8 services
# at boot. ANTHROPIC_API_KEY (or claude-cli auth) is required for the SDK to
# spawn Claude. HEGEMONIKON_SECRET gates non-/health requests. See
# docs/operations/hegemonikon.md for the full env envelope.
EXPOSE 8000
CMD ["python", "-m", "hegemonikon.mcp_server_http"]
