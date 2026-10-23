# Backend image for Render; also runs locally or on a Docker Space.
#
# Spaces refuses to run a container as root and routes traffic to port 7860, so
# both are fixed here rather than left to the platform. The image is fully
# self-contained: the built DuckDB warehouse and both trained boosters are
# committed to the repository, so nothing is fetched, extracted, or trained at
# build or start time and no credentials are required to serve a prediction.

FROM python:3.12-slim

# OCI annotations. `image.source` is not decorative: GHCR reads it to attach
# the published package to this repository and to inherit its visibility and
# access rules. Without it the package is an orphan the repo never links to.
LABEL org.opencontainers.image.source="https://github.com/yash-rai-93/argo-data-platform" \
      org.opencontainers.image.description="Argo backend: FastAPI serving XGBoost Cox survival predictions over a bundled DuckDB warehouse." \
      org.opencontainers.image.licenses="MIT"

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# UID 1000 is the identity Spaces expects. HOME must exist and be writable
# before any tool that caches under it runs.
RUN useradd --create-home --uid 1000 user

WORKDIR /app
RUN mkdir -p /home/user/.cache/matplotlib && chown user:user /app

# UV_NO_CACHE keeps uv's download cache out of the image: without it the sync
# layer carries both the wheels and the unpacked environment, roughly doubling
# it. UV_PYTHON points at the interpreter this base image already ships so uv
# does not fetch a managed second copy.
ENV UV_PYTHON=/usr/local/bin/python3.12 \
    UV_PYTHON_DOWNLOADS=never \
    UV_NO_CACHE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/home/user \
    XDG_CACHE_HOME=/home/user/.cache \
    MPLCONFIGDIR=/home/user/.cache/matplotlib

# Switch before installing so every file is created owned by the runtime user.
# A trailing `chown -R` over the virtualenv instead would rewrite every file
# into a new layer and add well over a gigabyte to the image.
USER user

# Dependencies resolve from the lockfile in their own layer, so editing source
# does not re-resolve 146 packages.
COPY --chown=user:user pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Runtime code. ml/ carries both model artifacts; api/routers/predict.py
# lazily imports ml.train_churn and ml.train_classifier to rebuild the Breslow
# baseline and score the holdout, so the trainers must ship even though no
# training happens here.
COPY --chown=user:user api/ ./api/
COPY --chown=user:user ml/ ./ml/
COPY --chown=user:user transform/argo.duckdb ./transform/argo.duckdb

# Run the interpreter from the virtualenv directly instead of through `uv run`.
# uv wants a writable project directory to re-verify the environment on every
# invocation, and --no-sync only suppresses part of that. PYTHONPATH is
# explicit because sys.path[0] becomes the uvicorn script's directory, not the
# working directory, so `import api` would otherwise fail.
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH=/app

EXPOSE 7860

# Cloud Run injects $PORT and requires the container to honour it; 7860 is the
# fallback so the image still runs locally and on a Hugging Face Docker Space
# with no environment set. exec replaces the shell so uvicorn is PID 1 and
# receives SIGTERM directly -- without it, shutdown waits for the platform's
# kill timeout on every revision.
CMD ["sh", "-c", "exec uvicorn api.main:app --host 0.0.0.0 --port ${PORT:-7860}"]
