FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

COPY pyproject.toml uv.lock ./
COPY api/ ./api/
COPY ml/ ./ml/
COPY transform/argo.duckdb ./transform/argo.duckdb

ENV UV_PYTHON=3.12

RUN uv sync --frozen --no-dev --no-install-project

EXPOSE 8000

CMD ["uv", "run", "--no-sync", "uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
