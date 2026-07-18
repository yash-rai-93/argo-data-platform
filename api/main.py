"""ARGO Product Intelligence API."""

from __future__ import annotations

from fastapi import FastAPI

from api.routers import intelligence, metrics, predict

app = FastAPI(title="ARGO Product Intelligence API")

app.include_router(metrics.router)
app.include_router(intelligence.router)
app.include_router(predict.router)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok"}
