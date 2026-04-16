FROM python:3.12-slim
WORKDIR /app
COPY /schemas /schemas
RUN pip install -e /schemas
COPY pyproject.toml .
RUN pip install -e .
COPY src/ src/
EXPOSE 8000
CMD ["python", "-m", "kosmos.mcp_server_http"]
