# Backend image for Hugging Face Spaces.
#
# Spaces refuses to run a container as root and routes traffic to port 7860, so
# both are fixed here rather than left to the platform. The image is fully
# self-contained: the built DuckDB warehouse and both trained boosters are
# committed to the repository, so nothing is fetched, extracted, or trained at
# build or start time and no credentials are required to serve a prediction.

FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UID 1000 is the identity Spaces expects. HOME must exist and be writable
# before any tool that caches under it runs.
RUN useradd --create-home --uid 1000 user

WORKDIR /app

ENV UV_PYTHON=3.12 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Dependencies resolve from the lockfile in their own layer, so editing source
# does not re-resolve 146 packages.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Runtime code. ml/ carries both model artifacts; api/routers/predict.py
# lazily imports ml.train_churn and ml.train_classifier to rebuild the Breslow
# baseline and score the holdout, so the trainers must ship even though no
# training happens here.
COPY api/ ./api/
COPY ml/ ./ml/
COPY transform/argo.duckdb ./transform/argo.duckdb

# Run the interpreter from the virtualenv directly instead of through `uv run`.
# uv wants a writable project directory to re-verify the environment; a
# non-root user does not have one, and --no-sync only suppresses part of it.
# PYTHONPATH is explicit because sys.path[0] becomes the uvicorn script's
# directory, not the working directory, so `import api` would otherwise fail.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app \
    HOME=/home/user \
    XDG_CACHE_HOME=/home/user/.cache \
    MPLCONFIGDIR=/home/user/.cache/matplotlib

# shap imports matplotlib at module load, which writes a font cache on first
# use. Without a writable target it warns on every cold start.
RUN mkdir -p /home/user/.cache/matplotlib && chown -R user:user /app /home/user

USER user

EXPOSE 7860

CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "7860"]
