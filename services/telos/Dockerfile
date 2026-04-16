FROM python:3.11-slim
WORKDIR /app

# Build context must be the repo root (Railway: Root Directory = /)
COPY schemas/ /schemas
RUN pip install /schemas

COPY services/telos/pyproject.toml .
RUN pip install .

COPY services/telos/src/ src/

EXPOSE 8000
CMD ["python", "-m", "telos.mcp_server_http"]
