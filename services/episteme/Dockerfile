FROM python:3.11-slim
WORKDIR /app

# Build context must be the repo root (Railway: Root Directory = /)
COPY schemas/ /schemas
RUN pip install /schemas

COPY services/episteme/pyproject.toml .
RUN pip install .

COPY services/episteme/src/ src/

EXPOSE 8000
CMD ["python", "-m", "episteme.mcp_server_http"]
